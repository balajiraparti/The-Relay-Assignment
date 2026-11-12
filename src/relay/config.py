from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore', hide_input_in_errors=True)
    groq_api_key: SecretStr = SecretStr('')
    groq_model: str = 'openai/gpt-oss-120b'
    groq_rpm: int = Field(30, gt=0)
    groq_tpm: int = Field(8000, gt=0)
    groq_rpd: int = Field(1000, gt=0)
    groq_tpd: int = Field(200000, gt=0)
    relay_backend: Literal['groq', 'stand-in'] = 'groq'
    relay_api_url: str = 'http://127.0.0.1:8000'
    runtime: Path = ROOT / 'runtime'
    embedding_model: str = 'sentence-transformers/all-MiniLM-L6-v2'
    reranker_model: str = 'cross-encoder/ms-marco-MiniLM-L6-v2'

    @field_validator('relay_api_url')
    @classmethod
    def local_url(cls, value):
        url = urlsplit(value)
        if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost') or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
            raise ValueError('relay_api_url must be a local HTTP origin')
        _ = url.port
        return value.rstrip('/')

    def require_provider(self):
        if self.relay_backend == 'groq' and not self.groq_api_key.get_secret_value().strip():
            raise ValueError('missing_api_key')


def settings() -> Settings:
    return Settings()
