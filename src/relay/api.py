import asyncio
import base64
import hashlib
import json
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from relay.config import settings
from relay.store import Store
from relay.gateway import Gateway
from relay.corpus import Retriever
from relay.pipeline import Pipeline
from relay.telemetry import Telemetry


class Ask(BaseModel):
    model_config=ConfigDict(extra='forbid')
    question: str = Field(min_length=1,max_length=4000)
    retrieval_setting: Literal['R1','R2','R3']='R2'
    refinement: Literal['auto','off']='auto'

    @field_validator('question')
    @classmethod
    def clean(cls,value):
        value=value.strip()
        if not value or any(ord(c)<32 and c not in '\n\t\r' for c in value):
            raise ValueError('invalid_question')
        return value


@asynccontextmanager
async def service_lifespan(app):
    cfg=settings(); store=Store(cfg.runtime/'relay.db',initialize=False); store.recover()
    app.state.cfg=cfg; app.state.store=store; app.state.tasks={}
    app.state.ready_error=None; app.state.pipeline=None
    try:
        retriever=await asyncio.to_thread(Retriever,cfg)
        app.state.pipeline=Pipeline(cfg,store,Gateway(cfg,store),retriever)
    except Exception as e:
        app.state.ready_error=type(e).__name__
    yield
    for task in list(app.state.tasks.values()): task.cancel()
    await asyncio.gather(*app.state.tasks.values(),return_exceptions=True)


@asynccontextmanager
async def lifespan(app):
    cfg=settings()
    with Telemetry(cfg.runtime/'logs',service='api',secrets=[cfg.groq_api_key.get_secret_value()]) as telemetry:
        app.state.telemetry=telemetry
        async with service_lifespan(app): yield


app=FastAPI(title='The Relay',version='0.1.0',lifespan=lifespan)


@app.middleware('http')
async def local_guard(request: Request,call_next):
    from fastapi.responses import JSONResponse
    host=request.headers.get('host','').split(':')[0]
    if host not in ('127.0.0.1','localhost','testserver'):
        return JSONResponse({'error':{'code':'local_only'}},403)
    if request.headers.get('origin') and request.headers['origin'] not in ('http://localhost:8501','http://127.0.0.1:8501'):
        return JSONResponse({'error':{'code':'origin_rejected'}},403)
    if request.method=='POST':
        body=await request.body()
        if len(body)>16384: return JSONResponse({'error':{'code':'payload_too_large'}},413)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    return response


@app.get('/health/live')
def live(): return {'status':'alive'}


@app.get('/health/ready')
def ready():
    if not app.state.pipeline: raise HTTPException(503,'index_or_models_unavailable: run ingestion first')
    return {'status':'ready','source':app.state.cfg.relay_backend}


@app.get('/v1/capabilities')
def capabilities():
    return {'model':app.state.cfg.groq_model,'source':app.state.cfg.relay_backend,
            'settings':['R1','R2','R3'],'authentication':False,'version':'0.1.0'}


@app.post('/v1/requests',status_code=202)
async def create(body: Ask,idempotency_key: str=Header(min_length=16,max_length=128)):
    if app.state.telemetry.failed: raise HTTPException(503,'telemetry_unavailable')
    if not app.state.pipeline: raise HTTPException(503,'index_unavailable')
    data=body.model_dump(); digest=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    try: rid,fresh=app.state.store.create(idempotency_key,digest,data)
    except ValueError: raise HTTPException(409,'idempotency_conflict') from None
    if fresh:
        if len(app.state.tasks)>=10:
            app.state.store.update(rid,'rate_limited',{'reason':'queue_full'})
            raise HTTPException(429,detail={'code':'queue_full','resource_id':rid})
        app.state.store.event(rid,'request_received',source=app.state.cfg.relay_backend)
        task=asyncio.create_task(app.state.pipeline.run(rid,data))
        app.state.tasks[rid]=task
        task.add_done_callback(lambda _task: app.state.tasks.pop(rid,None))
    return {'id':rid,'status':app.state.store.get(rid)['status'],'replayed':not fresh}


@app.get('/v1/requests')
def history(limit:int=Query(20,ge=1,le=100),cursor:str|None=None):
    before=None
    if cursor:
        try:
            before=json.loads(base64.urlsafe_b64decode(cursor))
            if len(before)!=2 or not isinstance(before[0],(float,int)) or not isinstance(before[1],str): raise ValueError()
        except Exception: raise HTTPException(400,'invalid_cursor') from None
    rows=app.state.store.history(limit+1,before)
    more=len(rows)>limit; rows=rows[:limit]
    nxt=base64.urlsafe_b64encode(json.dumps([rows[-1]['created_at'],rows[-1]['id']]).encode()).decode() if more else None
    return {'items':rows,'has_more':more,'next_cursor':nxt}


@app.get('/v1/requests/{rid}')
def get(rid:str):
    row=app.state.store.get(rid)
    if not row: raise HTTPException(404,'not_found')
    return row


@app.post('/v1/requests/{rid}/cancel')
def cancel(rid:str):
    if not app.state.store.get(rid): raise HTTPException(404,'not_found')
    if app.state.store.update(rid,'cancelled',{'reason':'user_cancelled'}):
        task=app.state.tasks.get(rid)
        if task: task.cancel()
    return app.state.store.get(rid)


@app.get('/v1/papers')
def papers():
    if not app.state.pipeline: raise HTTPException(503,'index_unavailable')
    return {'items':app.state.pipeline.retriever.papers}
