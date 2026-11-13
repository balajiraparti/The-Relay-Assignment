import asyncio
import base64
import hashlib
import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from relay.config import settings
from relay.store import Store
from relay.gateway import Gateway
from relay.corpus import Retriever
from relay.pipeline import Pipeline
from relay.telemetry import Telemetry
from relay.local_access import local_peer,local_host
from relay import pagination
from relay.store import TERMINAL


class Ask(BaseModel):
    model_config=ConfigDict(extra='forbid')
    question: str = Field(min_length=1,max_length=4000)
    retrieval_setting: Literal['R1','R2','R3']='R2'
    refinement: Literal['auto','off']='auto'
    parent_request_id: uuid.UUID | None=None

    @field_validator('question')
    @classmethod
    def clean(cls,value):
        value=value.strip()
        if not value or any(ord(c)<32 and c not in '\n\t\r' for c in value):
            raise ValueError('invalid_question')
        return value


@asynccontextmanager
async def service_lifespan(app):
    cfg=settings()
    app.state.cfg=cfg; app.state.store=None; app.state.tasks={}
    app.state.ready_error=None; app.state.pipeline=None
    try:
        store=Store(cfg.runtime/'relay.db',initialize=False); store.recover()
        app.state.store=store
    except Exception:
        app.state.ready_error='database_unavailable'
    try:
        if app.state.store is None: raise RuntimeError('database_unavailable')
        cfg.require_provider()
        retriever=await asyncio.to_thread(Retriever,cfg)
        app.state.pipeline=Pipeline(cfg,store,Gateway(cfg,store),retriever)
    except Exception as e:
        if app.state.ready_error is None:
            app.state.ready_error='provider_not_configured' if str(e)=='missing_api_key' else 'index_or_models_unavailable'
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


@app.exception_handler(HTTPException)
async def http_error(request,exc):
    detail=exc.detail if isinstance(exc.detail,dict) else {'code':exc.detail}
    return JSONResponse({'error':{'code':detail.get('code','request_failed'),
        'request_id':getattr(request.state,'http_id',None),'resource_id':detail.get('resource_id'),
        'retryable':exc.status_code in (429,503),'retry_after_seconds':None}},status_code=exc.status_code,headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    malformed=any(e['type']=='json_invalid' for e in exc.errors())
    return JSONResponse({'error':{'code':'malformed_json' if malformed else 'validation_error',
        'request_id':getattr(request.state,'http_id',None),
        'details':[{'field':'.'.join(map(str,e['loc'])),'reason':e['type']} for e in exc.errors()]}},400 if malformed else 422)


@app.middleware('http')
async def local_guard(request: Request,call_next):
    from fastapi.responses import JSONResponse
    request.state.http_id=str(uuid.uuid4())
    if not request.client or not local_peer(request.client.host) or not local_host(request.headers.get('host','')):
        return JSONResponse({'error':{'code':'local_only'}},403)
    if request.headers.get('origin') and request.headers['origin'] not in ('http://localhost:8501','http://127.0.0.1:8501'):
        return JSONResponse({'error':{'code':'origin_rejected'}},403)
    if request.method=='POST':
        parts=[]; size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>16384: return JSONResponse({'error':{'code':'payload_too_large'}},413)
            parts.append(chunk)
        request._body=b''.join(parts)
        if request._body and request.headers.get('content-type','').split(';')[0]!='application/json':
            return JSONResponse({'error':{'code':'unsupported_media_type'}},415)
        if request.url.path.endswith(('/cancel','/stop')) and request._body:
            try: empty=json.loads(request._body)=={}
            except ValueError: return JSONResponse({'error':{'code':'malformed_json'}},400)
            if not empty: return JSONResponse({'error':{'code':'validation_error'}},422)
    allowed={'limit','cursor'} if request.url.path in ('/v1/papers','/v1/runs') or request.url.path.endswith('/events') else set()
    if request.url.path=='/v1/requests': allowed={'limit','cursor','status'} if request.method=='GET' else set()
    if request.url.path.startswith('/v1/chunks/'): allowed={'revision'}
    if request.url.path.endswith('/results.csv'): allowed={'allow_incomplete'}
    if request.url.path.startswith('/v1/') and set(request.query_params)-allowed:
        return JSONResponse({'error':{'code':'unknown_query_parameter'}},422)
    if request.url.path.startswith('/v1/requests') and app.state.store is None:
        return JSONResponse({'error':{'code':'database_unavailable'}},503)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Request-ID']=request.state.http_id
    return response


@app.get('/health/live')
def live(): return {'status':'alive'}


@app.get('/health/ready')
def ready():
    if app.state.telemetry.failed: raise HTTPException(503,'telemetry_unavailable')
    if not app.state.pipeline: raise HTTPException(503,app.state.ready_error or 'not_ready')
    return {'status':'ready','source':app.state.cfg.relay_backend,
            'index_revision':app.state.pipeline.retriever.revision,'provider_connectivity':'not_probed'}


@app.get('/v1/capabilities')
def capabilities():
    return {'model':app.state.cfg.groq_model,'source':app.state.cfg.relay_backend,
            'settings':['R1','R2','R3'],'authentication':False,'version':'0.1.0'}


@app.post('/v1/requests',status_code=202)
async def create(body: Ask,idempotency_key: str=Header(min_length=16,max_length=128)):
    if not all(32<=ord(c)<127 for c in idempotency_key): raise HTTPException(422,'invalid_idempotency_key')
    if app.state.telemetry.failed: raise HTTPException(503,'telemetry_unavailable')
    if not app.state.pipeline: raise HTTPException(503,'index_unavailable')
    data=body.model_dump(mode='json'); digest=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    if body.parent_request_id:
        parent=app.state.store.get(str(body.parent_request_id))
        if not parent or parent['status']!='needs_clarification': raise HTTPException(422,'invalid_clarification_parent')
    data.update(index_revision=app.state.pipeline.retriever.revision,source=app.state.cfg.relay_backend,model=app.state.cfg.groq_model)
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
    return JSONResponse({'id':rid,'status':app.state.store.get(rid)['status'],'replayed':not fresh},202,
        headers={'Location':f'/v1/requests/{rid}','Idempotent-Replayed':str(not fresh).lower()})


@app.get('/v1/requests')
def history(limit:int=Query(20,ge=1,le=100),cursor:str|None=None,status:str|None=None):
    if status and status not in TERMINAL|{'queued','preparing','retrieving','reranking','generating','validating'}: raise HTTPException(422,'invalid_status')
    before=None; snapshot=time.time(); scope='requests:'+str(status)
    if cursor:
        try:
            data=pagination.decode(app.state.store.cursor_secret(),cursor,scope)
            before=data['position']; snapshot=data['snapshot']
            if len(before)!=2 or not isinstance(before[0],(float,int)) or not isinstance(before[1],str): raise ValueError()
        except Exception: raise HTTPException(400,'invalid_cursor') from None
    rows=app.state.store.history(limit+1,before,status,snapshot)
    more=len(rows)>limit; rows=rows[:limit]
    nxt=pagination.encode(app.state.store.cursor_secret(),[rows[-1]['created_at'],rows[-1]['id']],scope,snapshot) if more else None
    return {'items':rows,'has_more':more,'next_cursor':nxt}


@app.get('/v1/requests/{rid}')
def get(rid:str):
    row=app.state.store.get(rid)
    if not row: raise HTTPException(404,'not_found')
    return row


@app.post('/v1/requests/{rid}/cancel')
async def cancel(rid:str):
    if not app.state.store.get(rid): raise HTTPException(404,'not_found')
    if app.state.store.update(rid,'cancelled',{'reason':'user_cancelled'}):
        task=app.state.tasks.get(rid)
        if task: task.cancel()
    return app.state.store.get(rid)


@app.get('/v1/papers')
def papers(limit:int=Query(20,ge=1,le=100),cursor:str|None=None):
    if not app.state.pipeline: raise HTTPException(503,'index_unavailable')
    return page_items(app.state.pipeline.retriever.papers,limit,cursor,'papers:'+app.state.pipeline.retriever.revision)


def page_items(items,limit,cursor,scope):
    offset=0
    if cursor:
        try: offset=pagination.decode(app.state.store.cursor_secret(),cursor,scope)['position']
        except ValueError: raise HTTPException(400,'invalid_cursor') from None
    selected=items[offset:offset+limit]; more=offset+limit<len(items)
    return {'items':selected,'has_more':more,'next_cursor':pagination.encode(app.state.store.cursor_secret(),offset+limit,scope) if more else None}


@app.get('/v1/papers/{paper_id}')
def paper(paper_id:str):
    if not app.state.pipeline: raise HTTPException(503,'index_unavailable')
    for item in app.state.pipeline.retriever.papers:
        if item['paper_id']==paper_id: return item
    raise HTTPException(404,'not_found')


@app.get('/v1/papers/{paper_id}/pages/{page}')
def paper_page(paper_id:str,page:int):
    paper(paper_id)
    revision=app.state.pipeline.retriever.revision
    data=json.loads((app.state.cfg.runtime/'indexes'/revision/'pages.json').read_text(encoding='utf-8'))
    for item in data['pages']:
        if item['paper_id']==paper_id and item['page']==page: return item
    raise HTTPException(404,'not_found')


def run_folder(run_id):
    try: run_id=str(uuid.UUID(run_id))
    except ValueError: raise HTTPException(404,'not_found') from None
    folder=app.state.cfg.runtime/'runs'/run_id
    if not (folder/'manifest.json').is_file(): raise HTTPException(404,'not_found')
    return folder


@app.get('/v1/runs')
def runs(limit:int=Query(20,ge=1,le=100),cursor:str|None=None):
    items=[]
    for path in (app.state.cfg.runtime/'runs').glob('*/manifest.json'):
        try:
            item=json.loads(path.read_text(encoding='utf-8'))
            uuid.UUID(item['id']); items.append(item)
        except (ValueError,KeyError,OSError): continue
    items.sort(key=lambda item:(item['created_at'],item['id']),reverse=True)
    # Freeze the collection membership into the signed cursor's scope through a cutoff.
    if cursor:
        try:
            data=pagination.decode(app.state.store.cursor_secret(),cursor,'runs')
            before=data['position']; items=[i for i in items if (i['created_at'],i['id'])<tuple(before)]
        except ValueError: raise HTTPException(400,'invalid_cursor') from None
    selected=items[:limit]; more=len(items)>limit
    nxt=pagination.encode(app.state.store.cursor_secret(),[selected[-1]['created_at'],selected[-1]['id']],'runs') if more else None
    return {'items':selected,'has_more':more,'next_cursor':nxt}


@app.get('/v1/runs/{run_id}')
def run_detail(run_id:str):
    folder=run_folder(run_id)
    result=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if (folder/'summary.json').exists(): result['summary']=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    result['stop_requested']=(folder/'stop.requested').exists()
    return result


@app.post('/v1/runs/{run_id}/stop')
def stop_run(run_id:str):
    folder=run_folder(run_id); manifest=run_detail(run_id)
    if manifest['state']=='running': (folder/'stop.requested').touch()
    return run_detail(run_id)


@app.get('/v1/runs/{run_id}/results.csv')
def run_csv(run_id:str,allow_incomplete:bool=False):
    from fastapi.responses import FileResponse
    from relay.experiments import export
    folder=run_folder(run_id)
    if run_detail(run_id)['state']=='running': raise HTTPException(409,'run_not_exportable')
    try: summary=export(folder,allow_incomplete)
    except (ValueError,OSError): raise HTTPException(409,'run_not_exportable') from None
    name='results.csv' if summary['complete'] and summary['graded'] else 'results.incomplete.csv'
    return FileResponse(folder/name,media_type='text/csv',filename=name)


@app.get('/v1/runs/{run_id}/events')
def run_events(run_id:str,limit:int=Query(20,ge=1,le=100),cursor:str|None=None):
    folder=run_folder(run_id); items=[]
    if (folder/'provider_events.json').exists():
        items=json.loads((folder/'provider_events.json').read_text(encoding='utf-8'))
    else:
        # Only safe summaries, never generation drafts or complete questions.
        for line in (folder/'raw.jsonl').read_text(encoding='utf-8').splitlines():
            try:
                row=json.loads(line); items.append({key:row.get(key) for key in ('request_id','scenario','status','total_ms','source')})
            except ValueError: continue
    return page_items(items,limit,cursor,'run-events:'+run_id)


@app.get('/v1/requests/{rid}/events')
async def events(rid:str,request:Request,last_event_id:str|None=Header(None)):
    get(rid)
    try:
        after=int(last_event_id or '0')
        if after<0: raise ValueError()
        if after:
            with app.state.store.connect() as db:
                if not db.execute('SELECT 1 FROM public_events WHERE request_id=? AND seq=?',(rid,after)).fetchone(): raise ValueError()
    except ValueError: raise HTTPException(400,'invalid_cursor') from None
    async def stream():
        cursor=after; heartbeat=time.monotonic()
        while not await request.is_disconnected():
            rows=app.state.store.public_events(rid,cursor)
            for row in rows:
                cursor=row['seq']
                yield f"id: {cursor}\nevent: {row['event']}\ndata: {row['payload']}\n\n"
            if rows: continue
            if get(rid)['status'] in TERMINAL: return
            if time.monotonic()-heartbeat>=15:
                yield ': heartbeat\n\n'; heartbeat=time.monotonic()
            await asyncio.sleep(.1)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})


@app.get('/v1/chunks/{chunk_id}')
def chunk(chunk_id:str,revision:str|None=None):
    import re
    if not re.fullmatch('[a-f0-9]{20}',chunk_id): raise HTTPException(404,'not_found')
    if not app.state.pipeline: raise HTTPException(503,'index_unavailable')
    retriever=app.state.pipeline.retriever
    if revision is None or revision==retriever.revision:
        chunks=retriever.chunks; revision=retriever.revision
    else:
        if not re.fullmatch('[a-f0-9]{16}',revision): raise HTTPException(404,'not_found')
        from relay.corpus import load_artifacts
        try: chunks=load_artifacts(app.state.cfg.runtime/'indexes'/revision,revision)[0]['chunks']
        except (OSError,ValueError): raise HTTPException(404,'not_found') from None
    for value in chunks:
        if value['id']==chunk_id: return {**value,'index_revision':revision}
    raise HTTPException(404,'not_found')


@app.get('/v1/retrieval-settings')
def retrieval_settings():
    return {'items':[{'id':'R1','method':'BM25','candidates':12,'evidence':4},
        {'id':'R2','method':'BM25 + dense + RRF + cross-encoder','candidates':16,'evidence':5},
        {'id':'R3','method':'BM25 + dense + RRF + cross-encoder','candidates':16,'evidence':6}]}


@app.get('/v1/quota')
def quota():
    cfg=app.state.cfg
    return {'source':cfg.relay_backend,'as_of':time.time(),'upstream_remaining':None,
        'configured':{'rpm':cfg.groq_rpm,'tpm':cfg.groq_tpm,'rpd':cfg.groq_rpd,'tpd':cfg.groq_tpd},
        'pending_requests':len(app.state.tasks),'note':'Conservative local configuration; not exact upstream allowance.'}
