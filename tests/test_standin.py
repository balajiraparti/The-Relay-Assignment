from fastapi.testclient import TestClient
from relay import standin


def test_stream_and_limit(monkeypatch):
    standin.arrivals.clear()
    monkeypatch.setenv('STANDIN_RPM','1')
    monkeypatch.setenv('STANDIN_FIRST_DELAY','0')
    monkeypatch.setenv('STANDIN_CHUNK_DELAY','0')
    with TestClient(standin.app) as client:
        body={'messages':[{'content':'fixture'}],'max_completion_tokens':10}
        r=client.post('/v1/chat/completions',json=body)
        assert r.status_code==200 and '[DONE]' in r.text
        r=client.post('/v1/chat/completions',json=body)
        assert r.status_code==429 and r.headers['retry-after']=='5'


def test_midstream_error(monkeypatch):
    standin.arrivals.clear()
    monkeypatch.setenv('STANDIN_FAIL_AFTER_CHUNKS','1')
    monkeypatch.setenv('STANDIN_FIRST_DELAY','0')
    monkeypatch.setenv('STANDIN_CHUNK_DELAY','0')
    with TestClient(standin.app) as client:
        r=client.post('/v1/chat/completions',json={'messages':[{'content':'fixture'}]})
        assert 'injected_midstream_failure' in r.text
        assert '[DONE]' not in r.text
