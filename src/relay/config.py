from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from relay.local_access import local_origin

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore', hide_input_in_errors=True, allow_inf_nan=False)
    groq_api_key: SecretStr = SecretStr('')
    groq_model: str = 'openai/gpt-oss-120b'
    groq_rpm: int = Field(30, gt=0)
    groq_tpm: int = Field(8000, gt=0)
    groq_rpd: int = Field(1000, gt=0)
    groq_tpd: int = Field(200000, gt=0)
    relay_backend: Literal['groq', 'stand-in'] = 'groq'
    relay_api_url: str = 'http://127.0.0.1:8000'
    standin_url: str = 'http://127.0.0.1:8001'
    model_concurrency: int = Field(2,gt=0,le=32)
    model_queue_limit: int = Field(10,gt=0,le=1000)
    model_wait_budget: float = Field(8,gt=0)
    model_deadline: float = Field(45,gt=0)
    model_timeout: float = Field(30,gt=0)
    model_max_attempts: int = Field(3,ge=1,le=3)
    retry_base_delay: float = Field(0.5,ge=0)
    runtime: Path = ROOT / 'runtime'
    embedding_model: str = 'sentence-transformers/all-MiniLM-L6-v2'
    reranker_model: str = 'cross-encoder/ms-marco-MiniLM-L6-v2'

    @field_validator('relay_api_url','standin_url')
    @classmethod
    def local_url(cls, value):
        return local_origin(value)

    def require_provider(self):
        if self.relay_backend == 'groq' and not self.groq_api_key.get_secret_value().strip():
            raise ValueError('missing_api_key')


def settings() -> Settings:
    return Settings()
