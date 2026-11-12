import argparse
import asyncio
import csv
import json
import time
import uuid
from datetime import datetime, timezone
from relay.config import settings
from relay.store import Store
from relay.gateway import Gateway, ModelError


async def probe(cfg,count):
    """Small probe only; never intentionally floods or exhausts a provider quota."""
    folder=cfg.runtime/'probes'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=True)
    store=Store(cfg.runtime/'relay.db'); gateway=Gateway(cfg,store)
    rows=[]
    for i in range(count):
        rid=str(uuid.uuid4()); start=time.perf_counter()
        store.operation(rid)
        row={'request_id':rid,'source':cfg.relay_backend,'scenario':'modest_provider_probe','start_time':datetime.now(timezone.utc).isoformat(),'first_token_ms':None,'total_ms':None,'status':'error','tokens_in':None,'tokens_out':None}
        try:
            result=await gateway.generate(rid,[{'role':'user','content':'In one short sentence, explain what a citation identifies.'}],cap=256)
            row.update(first_token_ms=result['first_model_token_ms'],total_ms=result['total_ms'],status='ok',tokens_in=(result['usage'] or {}).get('prompt_tokens'),tokens_out=(result['usage'] or {}).get('completion_tokens'),headers=result['headers'])
        except ModelError as exc:
            row.update(status='rate_limited' if exc.status==429 else 'error',error_code=exc.code,http_status=exc.status,total_ms=(time.perf_counter()-start)*1000)
        rows.append(row)
        (folder/'observations.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
        print(json.dumps({'probe':i+1,'status':row['status'],'total_ms':row['total_ms']}))
        if row['status']!='ok': break
        if i<count-1: await asyncio.sleep(22)
    print('Evidence saved:',folder)


def execute():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['check','serve','audit','migrate','ingest','probe','ask','calibrate','export-events'])
    parser.add_argument('--count',type=int,default=3)
    parser.add_argument('--question',default='How does Moshi support simultaneous listening and speaking?')
    parser.add_argument('--observations')
    args=parser.parse_args(); cfg=settings()
    if args.command in ('probe','ask'): cfg.require_provider()
    if args.command=='check':
        print(json.dumps({'model':cfg.groq_model,'backend':cfg.relay_backend,'api_key_present':bool(cfg.groq_api_key.get_secret_value()),'index_present':(cfg.runtime/'active.txt').exists()}))
    elif args.command=='serve':
        import uvicorn
        uvicorn.run('relay.api:app',host='127.0.0.1',port=8000,proxy_headers=False)
    elif args.command=='audit':
        from relay.extraction import extract,save_audit
        from relay.config import ROOT
        audit=extract(ROOT/'data')
        print(json.dumps({'artifact':str(save_audit(audit,cfg.runtime)),'pages':len(audit['pages']),
                          'warnings':sum(len(p['warnings']) for p in audit['pages'])}))
    elif args.command=='migrate':
        from relay.migrations import migrate
        print(json.dumps({'schema_version':migrate(cfg.runtime/'relay.db')}))
    elif args.command=='ingest':
        from relay.corpus import ingest
        print(json.dumps(ingest(cfg),indent=2))
    elif args.command=='probe':
        if not 1<=args.count<=5: parser.error('probe count must be 1..5')
        asyncio.run(probe(cfg,args.count))
    elif args.command=='ask':
        from relay.corpus import Retriever
        from relay.pipeline import Pipeline
        store=Store(cfg.runtime/'relay.db')
        retriever=Retriever(cfg)
        data={'question':args.question,'refinement':'off','retrieval_setting':'R2'}
        rid,_=store.create(str(uuid.uuid4()),str(uuid.uuid4()),data)
        pipeline=Pipeline(cfg,store,Gateway(cfg,store),retriever)
        asyncio.run(pipeline.run(rid,data))
        result=store.get(rid)
        (cfg.runtime/'last_answer.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=True,indent=2))
    elif args.command=='calibrate':
        from pathlib import Path
        if not args.observations: parser.error('--observations is required')
        from relay.calibration import calibrate
        profile=calibrate(args.observations)
        (cfg.runtime/'calibration.json').write_text(json.dumps(profile,indent=2),encoding='utf-8')
        print(json.dumps(profile,indent=2))
    else:
        store=Store(cfg.runtime/'relay.db')
        with store.connect() as db: rows=db.execute('SELECT * FROM events ORDER BY seq').fetchall()
        target=cfg.runtime/'events.jsonl'
        with target.open('w',encoding='utf-8') as out:
            for row in rows: out.write(json.dumps(dict(row))+'\n')
        print('Exported event count:',len(rows))


def main():
    from relay.telemetry import Telemetry
    cfg=settings()
    with Telemetry(cfg.runtime/'logs',service='cli',secrets=[cfg.groq_api_key.get_secret_value()]):
        execute()


if __name__=='__main__': main()
