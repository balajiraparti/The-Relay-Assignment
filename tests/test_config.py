import pytest
from pydantic import ValidationError
from relay.config import Settings


def test_secret_is_hidden():
    cfg = Settings(_env_file=None, groq_api_key='synthetic-secret')
    assert 'synthetic-secret' not in repr(cfg)


def test_invalid_limit_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, groq_tpm=0)


def test_provider_requirement_and_local_origin():
    cfg=Settings(_env_file=None,groq_api_key='')
    with pytest.raises(ValueError,match='missing_api_key'): cfg.require_provider()
    Settings(_env_file=None,groq_api_key='',relay_backend='stand-in').require_provider()
    with pytest.raises(ValidationError): Settings(_env_file=None,relay_backend='other')
    for url in ('https://example.com','http://user:secret@localhost','http://localhost/path'):
        with pytest.raises(ValidationError) as error:
            Settings(_env_file=None,relay_api_url=url)
        assert url not in str(error.value)
