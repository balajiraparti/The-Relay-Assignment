"""Bounded experiments, immutable raw records, and deterministic CSV aggregation.

Run explicitly with python -m relay.experiments. No model-based grading.
"""
import argparse
import asyncio
import csv
import hashlib
import json
import math
import time
import uuid
from datetime import datetime,timezone
from pathlib import Path

from relay.config import ROOT,settings
from relay.store import Store,TERMINAL
from relay.gateway import Gateway
from relay.pipeline import Pipeline
from relay.telemetry import Telemetry

COLUMNS='request_id,scenario,source,start_time,first_token_ms,total_ms,status,retries,tokens_in,tokens_out,retrieval_setting,answer_grade'.split(',')
GRADES={'correct','wrong','refused_correctly','refused_wrongly'}


def write_json(path,data):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')
    temporary.replace(path)


def percentile(values,p):
    values=sorted(values)
    if not values: return None
    position=(len(values)-1)*p; low=math.floor(position); high=math.ceil(position)
    return values[low]+(values[high]-values[low])*(position-low)


def export(folder,allow_incomplete=False):
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    raw=[json.loads(line) for line in (folder/'raw.jsonl').read_text(encoding='utf-8').splitlines()]
    grades=json.loads((folder/'grades.json').read_text(encoding='utf-8')) if (folder/'grades.json').exists() else {}
    complete=manifest['state']=='completed' and len(raw)==manifest['expected_arrivals']
    graded=all(r['status']!='ok' or r['request_id'] in grades for r in raw) if manifest['kind']=='quality' else True
    if not allow_incomplete and (not complete or not graded): raise ValueError('run_not_exportable_incomplete_or_ungraded')
    ids=[r['request_id'] for r in raw]
    if len(ids)!=len(set(ids)): raise ValueError('duplicate_request_rows')
    rows=[]
    for record in raw:
        row={key:record.get(key) for key in COLUMNS}
        grade=grades.get(record['request_id'])
        if grade:
            if grade.get('grade') not in GRADES or not grade.get('rationale') or not grade.get('reviewer'): raise ValueError('invalid_grade')
            row['answer_grade']=grade['grade']
        rows.append(row)
    name='results.csv' if complete and graded else 'results.incomplete.csv'
    with (folder/name).open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=COLUMNS); writer.writeheader(); writer.writerows(rows)
    summaries=[]
    for group in sorted({(r['source'],r['scenario'],r['retrieval_setting']) for r in rows}):
        subset=[r for r in rows if (r['source'],r['scenario'],r['retrieval_setting'])==group]
        times=[r['total_ms'] for r in subset if r['total_ms'] is not None]
        first=[r['first_token_ms'] for r in subset if r['first_token_ms'] is not None]
        known=all(r['tokens_in'] is not None and r['tokens_out'] is not None for r in subset)
        delivered=sum(r.get('outcome')=='answered' for r in raw if (r['source'],r['scenario'],r['retrieval_setting'])==group)
        total_in=sum(r['tokens_in'] or 0 for r in subset); total_out=sum(r['tokens_out'] or 0 for r in subset)
        summaries.append({'source':group[0],'scenario':group[1],'setting':group[2],'n':len(subset),
            'first_token_n':len(first),'total_n':len(times),'answered':delivered,
            **{f'total_p{p}':percentile(times,p/100) for p in (50,95,99)},
            **{f'first_token_p{p}':percentile(first,p/100) for p in (50,95,99)},
            **{f'{status}_pct':100*sum(r['status']==status for r in subset)/len(subset) for status in ('ok','rate_limited','timeout','error')},
            'retries':sum(r['retries'] or 0 for r in subset),'usage_complete':known,
            'tokens_per_answer':(total_in+total_out)/delivered if known and delivered else None,
            'paid_equivalent_usd_per_1000_answers':(total_in*.15+total_out*.6)/1000/delivered if known and delivered and group[0]=='real' else None,
            'grades':{g:sum(r['answer_grade']==g for r in subset) for g in sorted(GRADES)}})
    report={'complete':complete,'graded':graded,'expected_arrivals':manifest['expected_arrivals'],'recorded':len(raw),
        'percentile_method':'linear interpolation (n-1)*p; small-sample tails are descriptive only',
        'population':'total includes every terminal outcome; first_token only observed validated answer emissions',
        'cost_basis':'Listed paid-equivalent, no cached-token discount assumed; not actual Free-tier billing.',
        'summaries':summaries}
    write_json(folder/'summary.json',report)
    return report


async def quality(cfg,selected,interval):
    from relay.corpus import Retriever
    questions_path=ROOT/'data/evaluation_questions.json'
    questions=json.loads(questions_path.read_text(encoding='utf-8'))
    cfg.require_provider()
    store=Store(cfg.runtime/'relay.db'); retriever=await asyncio.to_thread(Retriever,cfg)
    pipeline=Pipeline(cfg,store,Gateway(cfg,store),retriever)
    run_id=str(uuid.uuid4()); folder=cfg.runtime/'runs'/run_id; folder.mkdir(parents=True)
    manifest={'id':run_id,'kind':'quality','state':'running','source':'real' if cfg.relay_backend=='groq' else 'stand-in',
        'created_at':datetime.now(timezone.utc).isoformat(),'expected_arrivals':len(questions)*len(selected),
        'settings':selected,'interval_seconds':interval,'index_revision':retriever.revision,
        'question_sha256':hashlib.sha256(questions_path.read_bytes()).hexdigest(),
        'measurement_scope':'Full pipeline; first_token_ms is observed public-event consumption, not provider TTFT or browser receipt',
        'model':cfg.groq_model,'refinement':'off','max_attempts':cfg.model_max_attempts}
    write_json(folder/'manifest.json',manifest); (folder/'raw.jsonl').touch()
    print('Run:',folder,flush=True)
    offered=0
    try:
        # Question-major order reduces drift bias between settings.
        for question in questions:
            for setting in selected:
                if (folder/'stop.requested').exists(): raise asyncio.CancelledError()
                started=time.perf_counter(); start_utc=datetime.now(timezone.utc).isoformat()
                body={'question':question['question'],'retrieval_setting':setting,'refinement':'off',
                      'index_revision':retriever.revision,'source':cfg.relay_backend,'model':cfg.groq_model}
                rid,_=store.create(f'{run_id}:{question["id"]}:{setting}',uuid.uuid4().hex,body)
                task=asyncio.create_task(pipeline.run(rid,body)); first=None; cursor=0
                while True:
                    for event in store.public_events(rid,cursor):
                        cursor=event['seq']
                        if event['event']=='answer_delta' and first is None: first=(time.perf_counter()-started)*1000
                    if task.done():
                        # Drain the final atomic publication on the next iteration if necessary.
                        if not store.public_events(rid,cursor): break
                    await asyncio.sleep(.01)
                await task
                resource=store.get(rid); result=resource['result'] or {}; usage=store.usage_summary(rid)
                row={'request_id':rid,'question_id':question['id'],'question':question['question'],'scenario':'steady',
                    'source':manifest['source'],'start_time':start_utc,'first_token_ms':first,
                    'total_ms':(time.perf_counter()-started)*1000,'outcome':resource['status'],
                    'status':{'rate_limited':'rate_limited','timed_out':'timeout','failed':'error','cancelled':'error'}.get(resource['status'],'ok'),
                    'retries':max(0,usage['attempts']-1),'tokens_in':usage['prompt_tokens'],'tokens_out':usage['completion_tokens'],
                    'retrieval_setting':setting,'answer_grade':None,'resource':resource}
                with (folder/'raw.jsonl').open('a',encoding='utf-8') as stream: stream.write(json.dumps(row,ensure_ascii=False)+'\n')
                offered+=1
                print(f'{offered}/{manifest["expected_arrivals"]} {question["id"]} {setting}: {resource["status"]}',flush=True)
                if offered<manifest['expected_arrivals']: await asyncio.sleep(max(0,interval-(time.perf_counter()-started)))
        manifest['state']='completed'
    except BaseException:
        manifest['state']='incomplete'; raise
    finally:
        write_json(folder/'manifest.json',manifest); export(folder,allow_incomplete=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['quality','export','load'])
    parser.add_argument('--run'); parser.add_argument('--allow-incomplete',action='store_true')
    parser.add_argument('--settings',nargs='+',choices=['R1','R2','R3'],default=['R1','R2','R3'])
    parser.add_argument('--interval',type=float,default=30)
    parser.add_argument('--scenario',action='append')
    args=parser.parse_args(); cfg=settings()
    if args.command=='export':
        if not args.run: parser.error('--run required')
        folder=cfg.runtime/'runs'/str(uuid.UUID(args.run)); print(json.dumps(export(folder,args.allow_incomplete),indent=2)); return
    if args.command=='quality' and (not math.isfinite(args.interval) or args.interval<22): parser.error('Real quality runs require at least 22 seconds between starts')
    with Telemetry(cfg.runtime/'logs',service='experiments',secrets=[cfg.groq_api_key.get_secret_value()]):
        if args.command=='quality': asyncio.run(quality(cfg,args.settings,args.interval))
        else:
            from relay.load_experiments import run
            asyncio.run(run(cfg,args.scenario))


if __name__=='__main__': main()
