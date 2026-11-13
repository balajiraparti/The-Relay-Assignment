import asyncio
import random
import time
from relay.backends import HTTPBackend, ModelError


class Gateway:
    def __init__(self,cfg,store,backend=None):
        self.cfg,self.store=cfg,store
        self.backend=backend or HTTPBackend(cfg)
        self.slots=asyncio.Semaphore(cfg.model_concurrency)
        self.cooldown_until=0.; self.pending=0

    async def generate(self,rid,messages,stage='generation',cap=1024,response_format=None):
        try: self.cfg.require_provider()
        except ValueError: raise ModelError('missing_api_key') from None
        if not isinstance(cap,int) or cap<1: raise ModelError('invalid_completion_cap')
        if self.pending>=self.cfg.model_queue_limit+self.cfg.model_concurrency:
            raise ModelError('model_queue_full',429)
        self.pending+=1
        try:
            async with asyncio.timeout(self.cfg.model_deadline):
                return await self._generate(rid,messages,stage,cap,response_format)
        except TimeoutError: raise ModelError('model_deadline',408) from None
        finally: self.pending-=1

    async def _generate(self,rid,messages,stage,cap,response_format):
        cfg=self.cfg; start=time.perf_counter(); waited=0.
        estimate=sum(len(m['content'].encode())+32 for m in messages)+cap
        limits=(cfg.groq_rpm,cfg.groq_tpm,cfg.groq_rpd,cfg.groq_tpd)
        for attempt in range(1,cfg.model_max_attempts+1):
            delay=max(0.,self.cooldown_until-time.monotonic(),self.store.cooldown(cfg.relay_backend))
            if delay:
                if waited+delay>=cfg.model_wait_budget: raise ModelError('provider_cooldown',429,delay)
                await asyncio.sleep(delay); waited+=delay
            queued=time.perf_counter()
            try:
                async with asyncio.timeout(max(0.,cfg.model_wait_budget-waited)):
                    await self.slots.acquire()
            except TimeoutError: raise ModelError('model_queue_deadline',408) from None
            waited+=time.perf_counter()-queued
            cid=None; dispatched=False; content=''; usage=None; first=None; finish=None; done=False; headers={}; chunks=0; http_status=None
            retry=None
            try:
                # A sibling may have observed 429 while this call waited for a slot.
                if self.cooldown_until>time.monotonic():
                    raise ModelError('provider_cooldown',429,self.cooldown_until-time.monotonic())
                try: cid=self.store.reserve(rid,cfg.relay_backend,estimate,limits)
                except ValueError as exc:
                    self.store.event(rid,'quota_rejected',reason_code=str(exc),source=cfg.relay_backend)
                    raise ModelError(str(exc),429) from None
                self.store.event(rid,'model_started',call_id=cid,stage=stage,attempt=attempt,
                                 estimated_tokens=estimate,source=cfg.relay_backend,wait_ms=waited*1000)
                self.store.call_state(cid,'dispatched'); dispatched=True
                options={'response_format':response_format} if response_format is not None else {}
                async for event in self.backend.stream(rid,messages,cap,**options):
                    if event.kind=='http_status': http_status=event.value
                    elif event.kind=='headers': headers=event.value
                    elif event.kind=='content':
                        first=first if first is not None else (time.perf_counter()-start)*1000
                        content+=event.value; chunks+=1
                        if len(content)>1_000_000: raise ModelError('response_too_large')
                    elif event.kind=='usage':
                        value=event.value
                        if isinstance(value,dict) and all(type(value.get(k)) is int and value[k]>=0 for k in ('prompt_tokens','completion_tokens')): usage=value
                    elif event.kind=='finish': finish=event.value
                    elif event.kind=='done': done=True
                if not done or not content or finish!='stop': raise ModelError('incomplete_response')
                self.store.call_state(cid,'succeeded',usage)
                elapsed=(time.perf_counter()-start)*1000
                self.store.event(rid,'model_completed',call_id=cid,stage=stage,first_content_ms=first,
                                 total_ms=elapsed,usage=usage,finish_reason=finish,chunks=chunks,headers=headers,http_status=http_status)
                return {'text':content,'usage':usage,'headers':headers,'first_model_token_ms':first,
                        'total_ms':elapsed,'retries':attempt-1,'wait_ms':waited*1000,'http_status':http_status}
            except ModelError as exc:
                if cid: self.store.call_state(cid,'unknown' if dispatched else 'released',usage)
                self.store.event(rid,'model_failed',call_id=cid,error_code=exc.code,http_status=http_status,local_status=exc.status,headers=headers)
                if exc.status==429 and exc.code=='provider_http_error':
                    self.cooldown_until=max(self.cooldown_until,time.monotonic()+(exc.retry_after if exc.retry_after is not None else 60))
                    self.store.cooldown(cfg.relay_backend,exc.retry_after if exc.retry_after is not None else 60)
                retryable=not content and (exc.code in ('transport_error','transport_timeout') or
                    exc.code=='provider_http_error' and (exc.status==429 or exc.status>=500))
                if not retryable or attempt==cfg.model_max_attempts: raise
                retry=exc.retry_after if exc.status==429 and exc.retry_after is not None else min(2.,cfg.retry_base_delay*2**(attempt-1))*random.uniform(0.8,1.2)
                if exc.status==429: retry=max(retry,self.cooldown_until-time.monotonic())
                if waited+retry>=cfg.model_wait_budget or time.perf_counter()-start+retry>=cfg.model_deadline: raise
            except BaseException:
                if cid: self.store.call_state(cid,'unknown' if dispatched else 'released',usage)
                raise
            finally: self.slots.release()
            self.store.event(rid,'retry_scheduled',attempt=attempt+1,delay_ms=retry*1000)
            await asyncio.sleep(retry); waited+=retry
        raise ModelError('retry_exhausted')
