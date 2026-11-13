"""Explicit synthetic HTTP provider; isolated state per application instance."""
import asyncio
import hashlib
import json
import math
import random
import re
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse,StreamingResponse
from pydantic import BaseModel,Field
from pydantic_settings import BaseSettings,SettingsConfigDict
from relay.config import ROOT
from relay.telemetry import Telemetry


class Profile(BaseSettings):
    model_config=SettingsConfigDict(env_prefix='STANDIN_',extra='ignore',allow_inf_nan=False)
    workers:int=Field(2,gt=0)
    queue_limit:int=Field(32,ge=0)
    rpm:int=Field(30,gt=0)
    tpm:int=Field(8000,gt=0)
    rpd:int=Field(1000,gt=0)
    tpd:int=Field(200000,gt=0)
    first_delay:float=Field(.2,ge=0)
    chunk_delay:float=Field(.02,ge=0)
    load_factor:float=Field(.1,ge=0)
    failure_rate:float=Field(0,ge=0,le=1)
    fail_after_chunks:int=Field(0,ge=0)
    fail_first_requests:int=Field(0,ge=0)
    seed:int=42
    calibration:Path|None=None
    log_dir:Path=ROOT/'runtime'/'logs'


class Message(BaseModel):
    role:str='user'
    content:str=Field(max_length=100000)


class Completion(BaseModel):
    messages:list[Message]=Field(min_length=1,max_length=100)
    max_completion_tokens:int=Field(256,gt=0,le=32768)
    stream:bool=True


def create_app(profile=None):
    @asynccontextmanager
    async def lifespan(app):
        cfg=profile or Profile()
        app.state.profile=cfg; app.state.workers=asyncio.Semaphore(cfg.workers)
        app.state.arrivals=deque(); app.state.lock=asyncio.Lock(); app.state.active=0; app.state.waiting=0; app.state.count=0
        app.state.observed=deque(maxlen=10000)
        calibration=json.loads(cfg.calibration.read_text()) if cfg.calibration else None
        if calibration:
            n=calibration['sample_count']
            if n<1 or any(len(calibration[k])!=n or any(not math.isfinite(v) or v<0 for v in calibration[k])
                          for k in ('first_delay_samples_seconds','tail_samples_seconds')):
                raise ValueError('invalid_calibration')
        app.state.calibration=calibration
        with Telemetry(cfg.log_dir,service='standin') as log:
            app.state.log=log
            yield

    app=FastAPI(title='Relay synthetic stand-in',lifespan=lifespan)

    def event(name,rid,**fields):
        app.state.observed.append({'event':name,'request_id':rid,**fields})
        app.state.log.emit(name,request_id=rid,source='stand-in',**fields)

    @app.post('/v1/chat/completions')
    async def completion(body:Completion,request:Request):
        if not body.stream: return JSONResponse({'error':'stream_required'},400)
        cfg=app.state.profile; now=time.monotonic()
        rid=request.headers.get('x-request-id','uncorrelated')[:128]
        text=' '.join(m.content for m in body.messages)
        reservation=max(1,len(text)//4)+body.max_completion_tokens
        async with app.state.lock:
            app.state.count+=1; number=app.state.count
            while app.state.arrivals and app.state.arrivals[0][0]<=now-86400: app.state.arrivals.popleft()
            for window,req_cap,tok_cap in ((60,cfg.rpm,cfg.tpm),(86400,cfg.rpd,cfg.tpd)):
                recent=[a for a in app.state.arrivals if a[0]>now-window]
                if len(recent)>=req_cap or sum(a[1] for a in recent)+reservation>tok_cap:
                    retry=max(1,math.ceil(recent[0][0]+window-now)) if recent else window
                    event('standin_quota_refused',rid,window=window)
                    return JSONResponse({'error':'simulated_rate_limit'},429,headers={'retry-after':str(retry)})
            if app.state.active+app.state.waiting>=cfg.workers+cfg.queue_limit:
                event('standin_queue_refused',rid)
                return JSONResponse({'error':'simulated_queue_full'},429,headers={'retry-after':'1'})
            app.state.arrivals.append((now,reservation)); app.state.waiting+=1
        rng=random.Random(hashlib.sha256(f'{cfg.seed}:{rid}'.encode()).digest())
        fail=number<=cfg.fail_first_requests or rng.random()<cfg.failure_rate
        event('standin_received',rid,ordinal=number,estimated_tokens=reservation,fault=fail)
        if fail:
            app.state.waiting-=1
            return JSONResponse({'error':'simulated_failure'},503)
        if 'PREPARE_QUERY' in text: answer=json.dumps({'route':'direct','query':body.messages[-1].content})
        else:
            ids=re.findall(r'\[([a-f0-9]{20})\]',text)
            answer=json.dumps({'answer':f'Synthetic test response [{ids[0]}]' if ids else 'No fixture evidence.','refused':not bool(ids)})
        finish='stop'
        if len(answer)>body.max_completion_tokens*4:
            answer=answer[:body.max_completion_tokens*4]; finish='length'
        async def stream():
            acquired=False; waiting=True
            try:
                await app.state.workers.acquire(); acquired=True
                app.state.waiting-=1; waiting=False; app.state.active+=1
                waited=time.monotonic()-now; calibration=app.state.calibration
                sample=rng.randrange(calibration['sample_count']) if calibration else None
                delay=calibration['first_delay_samples_seconds'][sample] if calibration else cfg.first_delay
                delay*=1+cfg.load_factor*(app.state.active-1+app.state.waiting)
                tail=calibration['tail_samples_seconds'][sample] if calibration else None
                event('standin_worker_started',rid,queue_ms=waited*1000,delay_ms=delay*1000)
                await asyncio.sleep(delay)
                for i in range(0,len(answer),16):
                    if cfg.fail_after_chunks and i//16>=cfg.fail_after_chunks:
                        event('standin_stream_failed',rid,chunks=i//16)
                        yield 'data: '+json.dumps({'error':'injected_midstream_failure'})+'\n\n'; return
                    yield 'data: '+json.dumps({'choices':[{'delta':{'content':answer[i:i+16]}}]})+'\n\n'
                    chunk_delay=tail/max(1,math.ceil(len(answer)/16)) if tail is not None else cfg.chunk_delay
                    await asyncio.sleep(chunk_delay)
                yield 'data: '+json.dumps({'choices':[{'delta':{},'finish_reason':finish}],
                    'usage':{'prompt_tokens':max(1,len(text)//4),'completion_tokens':max(1,math.ceil(len(answer)/4))}})+'\n\n'
                yield 'data: [DONE]\n\n'
                event('standin_completed',rid)
            finally:
                if waiting: app.state.waiting-=1
                if acquired: app.state.active-=1; app.state.workers.release()
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'x-request-id':rid})
    return app


app=create_app()
