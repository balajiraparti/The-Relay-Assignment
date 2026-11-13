"""Copy explicitly selected sanitized evidence; never databases, keys or general logs."""
import csv
import hashlib
import json
import os
import platform
import shutil
import sqlite3
from pathlib import Path
from relay.config import ROOT,settings
from relay.experiments import COLUMNS,export,write_json

cfg=settings(); selection=json.loads((ROOT/'data/experiment_selection.json').read_text())
destination=ROOT/'evidence'/'2026-11-13'; destination.mkdir(parents=True,exist_ok=True)
all_rows=[]; observations=[]
for run_id in [selection['quality'],*selection['load']]:
    source=cfg.runtime/'runs'/run_id; target=destination/run_id; target.mkdir(exist_ok=True)
    summary=export(source,allow_incomplete=True)
    raw=[json.loads(line) for line in (source/'raw.jsonl').read_text(encoding='utf-8').splitlines()]
    for name in ('manifest.json','raw.jsonl','grades.json','summary.json','provider_events.json'):
        if (source/name).exists(): shutil.copyfile(source/name,target/name)
    csv_name='results.csv' if summary['complete'] and summary['graded'] else 'results.incomplete.csv'
    obsolete=target/('results.incomplete.csv' if csv_name=='results.csv' else 'results.csv')
    if obsolete.exists(): obsolete.unlink()
    shutil.copyfile(source/csv_name,target/csv_name)
    with (source/csv_name).open(encoding='utf-8',newline='') as stream: all_rows.extend(csv.DictReader(stream))
    db_path=source/'load.db' if (source/'load.db').exists() else cfg.runtime/'relay.db'
    db=sqlite3.connect(db_path); db.row_factory=sqlite3.Row; events=[]; calls=[]
    try:
        for row in raw:
            rid=row['request_id']
            for event in db.execute('SELECT * FROM events WHERE request_id=? ORDER BY seq',(rid,)):
                item=dict(event); item['payload']=json.loads(item['payload']); events.append(item)
                if row['source']=='real' and item['event']=='model_completed':
                    p=item['payload']
                    observations.append({'request_id':rid,'source':'groq','status':'ok',
                        'first_token_ms':p.get('first_content_ms'),'total_ms':p.get('total_ms'),
                        'measurement_scope':'successful gateway call; includes queue/retry waits; censored failures excluded'})
            calls.extend(dict(call) for call in db.execute('SELECT * FROM calls WHERE request_id=?',(rid,)))
    finally: db.close()
    write_json(target/'events.json',events); write_json(target/'calls.json',calls)
with (destination/'results.csv').open('w',encoding='utf-8',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=COLUMNS); writer.writeheader(); writer.writerows(all_rows)
write_json(destination/'real_gateway_observations.json',observations)
if observations:
    from relay.calibration import calibrate
    paper_profile=calibrate(destination/'real_gateway_observations.json')
    paper_profile['limitations']='Successful paper-sized generation calls only; failed/local-rejected arrivals excluded. Includes client/network and gateway overhead; no provider failure probability or quota recovery calibration. This new profile has not been used for the reported load runs, which retain the original bootstrap profile.'
    write_json(destination/'paper_calibration.json',paper_profile)
if (cfg.runtime/'calibration.json').exists(): shutil.copyfile(cfg.runtime/'calibration.json',destination/'bootstrap_calibration.json')
write_json(destination/'provenance.json',{'selection':selection,'python':platform.python_version(),'platform':platform.platform(),
    'processor':platform.processor(),'logical_cpus':os.cpu_count(),'rows':len(all_rows),
    'grade_status':'Assistant evidence review is provisional; author must verify hand-grades before submission.',
    'measurement_limits':'Small samples; concurrent synthetic tests may contend for CPU during real run. No production SLO inference.',
    'hash_scope':'Raw run exports, calibration and manifests; derived tables and trace are regenerated separately.',
    'dependency_lock_sha256':hashlib.sha256((ROOT/'requirements.lock.txt').read_bytes()).hexdigest(),
    'files':{str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(destination.rglob('*')) if p.is_file() and p.name not in ('provenance.json','tables.json','TABLES.md','trace.json')}})
secret=cfg.groq_api_key.get_secret_value()
for p in destination.rglob('*'):
    if p.is_file() and secret and secret.encode() in p.read_bytes(): raise RuntimeError('credential_found_in_evidence')
print('Evidence rows:',len(all_rows),'successful gateway observations:',len(observations))

# A single slow real request decomposed using same-process durations.
quality_folder=destination/selection['quality']
quality_rows=[json.loads(line) for line in (quality_folder/'raw.jsonl').read_text(encoding='utf-8').splitlines()]
successful=[r for r in quality_rows if r['outcome']=='answered']
if successful:
    slow=max(successful,key=lambda r:r['total_ms'])
    selected=[e for e in json.loads((quality_folder/'events.json').read_text()) if e['request_id']==slow['request_id']]
    retrieval=sum(e['payload']['duration_ms'] for e in selected if e['event']=='retrieval_completed')
    starts=[e['payload'] for e in selected if e['event']=='model_started']
    completions=[e['payload'] for e in selected if e['event']=='model_completed']
    if len(starts)==len(completions)==1:
        model=completions[0]; wait=starts[0]['wait_ms']; overhead=slow['total_ms']-retrieval-model['total_ms']
        trace={'request_id':slow['request_id'],'total_ms':slow['total_ms'],'retrieval_work_ms':retrieval,
            'gateway_wait_ms':wait,'model_network_and_work_ms':model['total_ms']-wait,
            'retry_ms':0,'validation_storage_and_observer_overhead_ms':overhead,
            'gateway_first_content_ms':model['first_content_ms'],'model_after_first_content_ms':model['total_ms']-model['first_content_ms'],
            'validated_first_token_ms':slow['first_token_ms']}
        write_json(destination/'trace.json',trace)
        lines=['# Slow real request trace','',f"Request: {slow['request_id']}",'',
            '| Component | ms |','| --- | --- |',*[f'| {k} | {v:.3f} |' for k,v in trace.items() if k!='request_id'],'',
            'The disjoint decomposition is retrieval + gateway wait + model/network work + retries + validation/storage/observer overhead = runner total. Gateway first content is measured from gateway entry, not request arrival. The first validated answer is released after generation and validation. Network time and remote inference are not separately identified; provider timing metadata is retained without pretending it uses the same clock. No retries occurred in this selected request.']
        (ROOT/'evidence/TRACE.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
