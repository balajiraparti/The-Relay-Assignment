from fastapi.testclient import TestClient
from relay import standin
import pytest


def test_stream_and_limit(monkeypatch):
    monkeypatch.setenv('STANDIN_RPM','1')
    monkeypatch.setenv('STANDIN_FIRST_DELAY','0')
    monkeypatch.setenv('STANDIN_CHUNK_DELAY','0')
    with TestClient(standin.app) as client:
        body={'messages':[{'content':'fixture'}],'max_completion_tokens':10}
        r=client.post('/v1/chat/completions',json=body)
        assert r.status_code==200 and '[DONE]' in r.text
        r=client.post('/v1/chat/completions',json=body)
        assert r.status_code==429 and int(r.headers['retry-after'])>0


def test_midstream_error(monkeypatch):
    monkeypatch.setenv('STANDIN_FAIL_AFTER_CHUNKS','1')
    monkeypatch.setenv('STANDIN_FIRST_DELAY','0')
    monkeypatch.setenv('STANDIN_CHUNK_DELAY','0')
    with TestClient(standin.app) as client:
        r=client.post('/v1/chat/completions',json={'messages':[{'content':'fixture'}]})
        assert 'injected_midstream_failure' in r.text
        assert '[DONE]' not in r.text


def test_profiles_are_isolated_and_seeded(tmp_path):
    def run():
        profile=standin.Profile(first_delay=0,chunk_delay=0,failure_rate=.5,log_dir=tmp_path)
        with TestClient(standin.create_app(profile)) as client:
            response=client.post('/v1/chat/completions',json={'messages':[{'content':'fixture'}]},headers={'X-Request-ID':'same-seed'})
            return response.status_code,response.text
    assert run()==run()
    with pytest.raises(ValueError): standin.Profile(failure_rate=2)


def test_request_validation(tmp_path):
    with TestClient(standin.create_app(standin.Profile(log_dir=tmp_path))) as client:
        assert client.post('/v1/chat/completions',json={'messages':[]}).status_code==422
        assert client.post('/v1/chat/completions',json={'messages':[{'content':'x'}],'max_completion_tokens':-1}).status_code==422
