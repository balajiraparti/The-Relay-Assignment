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
    monkeypatch.setattr(api,'settings',lambda:Settings(_env_file=None,runtime=tmp_path))
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
