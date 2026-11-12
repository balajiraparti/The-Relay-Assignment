import asyncio
import json
import time
import uuid
import httpx


class ModelError(Exception):
    def __init__(self, code, status=None, retry_after=None):
        super().__init__(code)
        self.code, self.status, self.retry_after = code, status, retry_after


class Gateway:
    def __init__(self,cfg,store):
        self.cfg, self.store = cfg,store
        self.slots = asyncio.Semaphore(2)
        self.cooldown_until = 0.0

    async def generate(self,rid,messages,stage='generation',cap=1024):
        cfg = self.cfg
        if cfg.relay_backend not in ('groq','stand-in'):
            raise ModelError('invalid_backend')
        if cfg.relay_backend == 'groq' and not cfg.groq_api_key.get_secret_value():
            raise ModelError('missing_api_key')
        # Conservative UTF-8 byte bound rather than a falsely precise tokenizer guess.
        estimate = sum(len(m['content'].encode('utf-8'))+32 for m in messages)+cap
        limits = (cfg.groq_rpm,cfg.groq_tpm,cfg.groq_rpd,cfg.groq_tpd)
        start = time.perf_counter()
        for attempt in range(1,4):
            if self.cooldown_until > time.monotonic():
                raise ModelError('provider_cooldown',429)
            async with self.slots:
                try:
                    cid = self.store.reserve(rid,cfg.relay_backend,estimate,limits)
                except ValueError as e:
                    raise ModelError(str(e),429) from None
                self.store.event(rid,'model_started',call_id=cid,stage=stage,attempt=attempt,estimated_tokens=estimate,source=cfg.relay_backend)
                self.store.call_state(cid,'dispatched')
                endpoint = 'https://api.groq.com/openai/v1/chat/completions' if cfg.relay_backend=='groq' else 'http://127.0.0.1:8001/v1/chat/completions'
                headers = {'X-Request-ID':rid}
                if cfg.relay_backend=='groq':
                    headers['Authorization'] = 'Bearer '+cfg.groq_api_key.get_secret_value()
                payload = {'model':cfg.groq_model,'messages':messages,'stream':True,
                           'max_completion_tokens':cap,'reasoning_effort':'low'}
                content, usage, first, finish, chunks = '',None,None,None,0
                safe_headers = {}
                try:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(30,connect=8)) as client:
                        async with client.stream('POST',endpoint,headers=headers,json=payload) as response:
                            safe_headers = {k:v for k,v in response.headers.items() if k.startswith('x-ratelimit-') or k in ('retry-after','x-request-id')}
                            self.store.event(rid,'provider_headers',call_id=cid,http_status=response.status_code,headers=safe_headers)
                            if response.status_code != 200:
                                retry = safe_headers.get('retry-after')
                                delay = float(retry) if retry and retry.replace('.','',1).isdigit() else None
                                if response.status_code==429:
                                    self.cooldown_until=time.monotonic()+(delay or 60)
                                raise ModelError('provider_http_error',response.status_code,delay)
                            async for line in response.aiter_lines():
                                if not line.startswith('data: '): continue
                                raw = line[6:]
                                if raw=='[DONE]': break
                                obj=json.loads(raw)
                                if obj.get('error'): raise ModelError('stream_error')
                                usage = obj.get('usage') or obj.get('x_groq',{}).get('usage') or usage
                                for choice in obj.get('choices',[]):
                                    piece=choice.get('delta',{}).get('content') or ''
                                    if piece:
                                        first = first if first is not None else (time.perf_counter()-start)*1000
                                        content+=piece
                                        chunks+=1
                                    finish=choice.get('finish_reason') or finish
                    self.store.call_state(cid,'succeeded',usage)
                    elapsed=(time.perf_counter()-start)*1000
                    self.store.event(rid,'model_completed',call_id=cid,stage=stage,first_content_ms=first,total_ms=elapsed,usage=usage,finish_reason=finish,chunks=chunks)
                    if not content or finish not in ('stop',):
                        raise ModelError('incomplete_response')
                    return {'text':content,'usage':usage,'headers':safe_headers,'first_model_token_ms':first,'total_ms':elapsed,'retries':attempt-1}
                except asyncio.CancelledError:
                    self.store.call_state(cid,'unknown')
                    raise
                except (httpx.HTTPError, json.JSONDecodeError, ModelError) as exc:
                    code=exc.code if isinstance(exc,ModelError) else type(exc).__name__
                    self.store.event(rid,'model_failed',call_id=cid,error_code=code)
                    if code=='incomplete_response': raise
                    self.store.call_state(cid,'unknown')
                    # Retrying streams after content risks duplicate remote work; stop.
                    retryable = not content and (not isinstance(exc,ModelError) or (exc.status is not None and exc.status>=500))
                    if not retryable or attempt==3:
                        raise ModelError(code,getattr(exc,'status',None),getattr(exc,'retry_after',None)) from None
            await asyncio.sleep(min(2,0.5*2**(attempt-1)))
        raise ModelError('retry_exhausted')
