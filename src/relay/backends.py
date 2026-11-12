"""One streamed event contract for real Groq and the controlled HTTP stand-in."""
import json
import math
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from datetime import datetime,timezone
import httpx


class ModelError(Exception):
    def __init__(self,code,status=None,retry_after=None):
        super().__init__(code)
        self.code,self.status,self.retry_after=code,status,retry_after


@dataclass
class BackendEvent:
    kind: str
    value: object


def retry_seconds(value):
    if not value: return None
    try:
        seconds=float(value)
        return max(0.,seconds) if math.isfinite(seconds) else None
    except ValueError:
        try: return max(0.,(parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds())
        except (ValueError,TypeError,OverflowError): return None


class HTTPBackend:
    def __init__(self,cfg,transport=None): self.cfg,self.transport=cfg,transport

    async def stream(self,rid,messages,cap,response_format=None):
        cfg=self.cfg
        endpoint='https://api.groq.com/openai/v1/chat/completions' if cfg.relay_backend=='groq' else cfg.standin_url+'/v1/chat/completions'
        headers={'X-Request-ID':rid}
        if cfg.relay_backend=='groq': headers['Authorization']='Bearer '+cfg.groq_api_key.get_secret_value()
        payload={'model':cfg.groq_model,'messages':messages,'stream':True,'max_completion_tokens':cap,'reasoning_effort':'low'}
        if response_format is not None: payload['response_format']=response_format
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(cfg.model_timeout,connect=min(8,cfg.model_timeout)),trust_env=False,transport=self.transport) as client:
                async with client.stream('POST',endpoint,headers=headers,json=payload) as response:
                    safe={k:v for k,v in response.headers.items() if k.startswith('x-ratelimit-') or k in ('retry-after','x-request-id')}
                    yield BackendEvent('headers',safe)
                    if response.status_code!=200:
                        raise ModelError('provider_http_error',response.status_code,retry_seconds(safe.get('retry-after')))
                    async for line in response.aiter_lines():
                        if not line.startswith('data:'): continue
                        raw=line[5:].strip()
                        if raw=='[DONE]': yield BackendEvent('done',None); return
                        if len(raw)>1_000_000: raise ModelError('oversized_stream_event')
                        try:
                            obj=json.loads(raw)
                            if obj.get('error'): raise ModelError('stream_error')
                            usage=obj.get('usage') or obj.get('x_groq',{}).get('usage')
                            if usage: yield BackendEvent('usage',usage)
                            for choice in obj.get('choices',[]):
                                content=choice.get('delta',{}).get('content')
                                if content:
                                    if not isinstance(content,str): raise ModelError('invalid_stream')
                                    yield BackendEvent('content',content)
                                if choice.get('finish_reason'): yield BackendEvent('finish',choice['finish_reason'])
                        except (ValueError,TypeError,AttributeError): raise ModelError('invalid_stream') from None
        except httpx.TimeoutException: raise ModelError('transport_timeout') from None
        except httpx.HTTPError: raise ModelError('transport_error') from None
