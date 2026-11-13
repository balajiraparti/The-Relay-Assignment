import pytest
from fastapi.testclient import TestClient
from relay import api
from relay.config import Settings


class FakeRetriever:
    revision='fixture'
    papers=[]
    def __init__(self,cfg): pass
    def search(self,*args): return []


@pytest.fixture
def client(tmp_path,monkeypatch):
    from relay.migrations import migrate
    migrate(tmp_path/'relay.db')
    monkeypatch.setattr(api,'settings',lambda:Settings(_env_file=None,runtime=tmp_path,relay_backend='stand-in'))
    monkeypatch.setattr(api,'Retriever',FakeRetriever)
    with TestClient(api.app) as client: yield client


def test_submit_replay_conflict(client):
    headers={'Idempotency-Key':'same-key-123456789'}
    body={'question':'What does the paper say?','refinement':'off'}
    r=client.post('/v1/requests',json=body,headers=headers)
    assert r.status_code==202
    rid=r.json()['id']
    replay=client.post('/v1/requests',json=body,headers=headers)
    assert replay.json()['id']==rid and replay.json()['replayed']
    assert client.post('/v1/requests',json={'question':'different'},headers=headers).status_code==409
    assert client.get('/v1/requests/'+rid).status_code==200


def test_validation_and_local_boundary(client):
    assert client.get('/v1/requests/missing').status_code==404
    assert client.get('/v1/requests?cursor=invalid').status_code==400
    assert client.post('/v1/requests',json={'question':' '},headers={'Idempotency-Key':'x'*16}).status_code==422
    assert client.get('/health/live',headers={'host':'malicious.example'}).status_code==403


def test_clarification_does_not_call_provider(client):
    r=client.post('/v1/requests',json={'question':'Why is it better?'},headers={'Idempotency-Key':'y'*16})
    import time
    for _ in range(20):
        row=client.get('/v1/requests/'+r.json()['id']).json()
        if row['status']=='needs_clarification': break
        time.sleep(.01)
    assert row['status']=='needs_clarification'


def test_readiness_origin_size_and_no_auth(client):
    assert client.get('/health/ready').json()['provider_connectivity']=='not_probed'
    assert client.post('/v1/requests',content=b'x'*17000).status_code==413
    assert client.get('/health/live',headers={'origin':'https://untrusted.example'}).status_code==403
    for path in ('/login','/logout','/v1/auth/login'):
        assert client.get(path).status_code==404
    assert client.get('/v1/capabilities').json()['authentication'] is False


def test_remote_peer_cannot_spoof_host(tmp_path,monkeypatch):
    from relay.migrations import migrate
    migrate(tmp_path/'relay.db')
    monkeypatch.setattr(api,'settings',lambda:Settings(_env_file=None,runtime=tmp_path,relay_backend='stand-in'))
    monkeypatch.setattr(api,'Retriever',FakeRetriever)
    with TestClient(api.app,client=('203.0.113.8',4567)) as client:
        assert client.get('/health/live',headers={'host':'127.0.0.1','x-forwarded-for':'127.0.0.1'}).status_code==403


@pytest.mark.parametrize('problem,expected',[('database','database_unavailable'),('key','provider_not_configured'),('index','index_or_models_unavailable')])
def test_safe_unavailable_readiness(tmp_path,monkeypatch,problem,expected):
    from relay.migrations import migrate
    if problem!='database': migrate(tmp_path/'relay.db')
    cfg=Settings(_env_file=None,runtime=tmp_path,groq_api_key='',relay_backend='groq' if problem=='key' else 'stand-in')
    monkeypatch.setattr(api,'settings',lambda:cfg)
    def broken(*args): raise ValueError('private path and secret must not leak')
    monkeypatch.setattr(api,'Retriever',broken)
    with TestClient(api.app) as client:
        response=client.get('/health/ready')
        assert response.status_code==503 and response.json()['error']['code']==expected
        assert 'private' not in response.text
        assert client.get('/health/live').status_code==200


def test_history_is_shared_local_state(client):
    row=client.post('/v1/requests',json={'question':'How does it work?'},headers={'Idempotency-Key':'shared-history-key'}).json()
    assert row['id'] in [item['id'] for item in client.get('/v1/requests').json()['items']]


def test_replay_no_inference_and_cursor_is_bound(client):
    store=api.app.state.store
    rid,_=store.create('event-key','hash',{'question':'test'})
    store.update(rid,'answered',{'answer':'Safe validated text.','citations':[]})
    events=store.public_events(rid)
    response=client.get(f'/v1/requests/{rid}/events')
    assert response.status_code==200 and response.text.count('event: done')==1
    replay=client.get(f'/v1/requests/{rid}/events',headers={'Last-Event-ID':str(events[-1]['seq'])})
    assert replay.text==''
    assert client.get(f'/v1/requests/{rid}/events',headers={'Last-Event-ID':'-1'}).status_code==400
    other,_=store.create('event-key2','hash',{'question':'other'})
    assert client.get(f'/v1/requests/{other}/events',headers={'Last-Event-ID':str(events[-1]['seq'])}).status_code==400
    page=client.get('/v1/requests?limit=1').json()
    assert page['has_more']
    next_page=client.get('/v1/requests',params={'limit':1,'cursor':page['next_cursor']}).json()
    assert page['items'][0]['id']!=next_page['items'][0]['id']
    assert client.get('/v1/requests',params={'cursor':page['next_cursor']+'x'}).status_code==400


def test_safe_request_errors(client):
    headers={'Idempotency-Key':'z'*16,'Content-Type':'application/json'}
    assert client.post('/v1/requests',content='{',headers=headers).json()['error']['code']=='malformed_json'
    assert client.post('/v1/requests',content='{}',headers={'Content-Type':'text/plain'}).status_code==415
    bad=client.post('/v1/requests',json={'question':'secret','extra':'secret'},headers=headers)
    assert bad.status_code==422 and 'secret' not in bad.text
    assert client.get('/health/live').headers['X-Request-ID']
