"""Scheduled open-loop synthetic loads using the actual HTTP stand-in and gateway."""
import asyncio
import json
import socket
import threading
import time
import uuid
from datetime import datetime,timezone
import uvicorn
from relay.standin import Profile,create_app
from relay.store import Store
from relay.gateway import Gateway,ModelError
from relay.pipeline import Pipeline
from relay.experiments import write_json,export


class FixtureRetriever:
    revision='synthetic-load-fixture'
    def search(self,*args):
        return [{'id':'0123456789abcdef0123','paper_id':'fixture','version':1,'page':1,
                 'text':'Synthetic fixture evidence for transport and capacity tests only.'}]


async def run(cfg,only=None):
    scenarios=[('steady',8,1.5,{}),('burst',16,0,{}),('sustained_overload',24,.1,{}),
        ('per_minute_limit_halved',12,.2,{'rpm':3}),('daily_budget_exhausted',8,.1,{'rpd':1}),
        ('retry_comparison_one_attempt',16,.1,{'failure_rate':0,'fail_first_requests':6,'calibration':None,'rpm':1000}),
        ('retry_comparison_three_attempts',16,.1,{'failure_rate':0,'fail_first_requests':6,'calibration':None,'rpm':1000})]
    for name,count,interval,overrides in scenarios:
        if only and name not in only: continue
        run_id=str(uuid.uuid4()); folder=cfg.runtime/'runs'/run_id; folder.mkdir(parents=True)
        calibration=cfg.runtime/'calibration.json'
        profile=Profile(_env_file=None,workers=1,queue_limit=4,rpm=6,tpm=80000,rpd=1000,tpd=2000000,
            first_delay=.4,chunk_delay=.02,load_factor=.1,seed=42,log_dir=folder/'logs',
            calibration=calibration if calibration.exists() else None).model_copy(update=overrides)
        app=create_app(profile)
        sock=socket.socket(); sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False))
        thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True); thread.start()
        deadline=time.monotonic()+10
        while not server.started:
            if not thread.is_alive() or time.monotonic()>deadline: raise RuntimeError('standin_start_failed')
            await asyncio.sleep(.02)
        local=cfg.model_copy(update={'relay_backend':'stand-in','standin_url':f'http://127.0.0.1:{port}',
            'groq_rpm':1000,'groq_tpm':1000000,'groq_rpd':10000,'groq_tpd':10000000,
            'model_max_attempts':1 if name=='retry_comparison_one_attempt' else 3})
        store=Store(folder/'load.db'); gateway=Gateway(local,store)
        pipeline=Pipeline(local,store,gateway,FixtureRetriever())
        manifest={'id':run_id,'kind':'load','state':'running','source':'stand-in','scenario':name,
            'created_at':datetime.now(timezone.utc).isoformat(),'expected_arrivals':count,'interval_seconds':interval,
            'profile':profile.model_dump(mode='json'),'max_attempts':local.model_max_attempts,
            'retrieval':'fixed synthetic fixture; isolates gateway/provider, not CPU retrieval throughput',
            'calibration_sha256':__import__('hashlib').sha256(calibration.read_bytes()).hexdigest() if calibration.exists() else None,
            'queue_peak':0,'schedule_lag_max_ms':0,'preconditioning_calls':0}
        write_json(folder/'manifest.json',manifest); (folder/'raw.jsonl').touch()
        tasks=[]
        try:
            if name=='daily_budget_exhausted':
                rid=str(uuid.uuid4()); store.operation(rid)
                try: await gateway.generate(rid,[{'role':'user','content':'Synthetic warmup'}],cap=256)
                except ModelError: pass
                manifest['preconditioning_calls']=1
            origin=time.perf_counter()
            async def one(i):
                scheduled=origin+i*interval
                await asyncio.sleep(max(0,scheduled-time.perf_counter()))
                if (folder/'stop.requested').exists(): return
                start=time.perf_counter()
                manifest['schedule_lag_max_ms']=max(manifest['schedule_lag_max_ms'],(start-scheduled)*1000)
                body={'question':'Summarize the synthetic fixture evidence.','retrieval_setting':'R2','refinement':'off'}
                rid,_=store.create(f'{run_id}:{i}',str(i),body)
                row={'request_id':rid,'scenario':name,'source':'stand-in','start_time':datetime.now(timezone.utc).isoformat(),
                    'first_token_ms':None,'retrieval_setting':'R2','answer_grade':None,'offered_index':i}
                task=asyncio.create_task(pipeline.run(rid,body)); cursor=0
                while True:
                    manifest['queue_peak']=max(manifest['queue_peak'],max(0,gateway.pending-local.model_concurrency))
                    for event in store.public_events(rid,cursor):
                        cursor=event['seq']
                        if event['event']=='answer_delta' and row['first_token_ms'] is None:
                            row['first_token_ms']=(time.perf_counter()-start)*1000
                    if task.done() and not store.public_events(rid,cursor): break
                    await asyncio.sleep(.01)
                await task
                resource=store.get(rid); usage=store.usage_summary(rid)
                row.update(total_ms=(time.perf_counter()-start)*1000,outcome=resource['status'],resource=resource,
                    status={'rate_limited':'rate_limited','timed_out':'timeout','failed':'error','cancelled':'error'}.get(resource['status'],'ok'),
                    retries=max(0,usage['attempts']-1),tokens_in=usage['prompt_tokens'],tokens_out=usage['completion_tokens'])
                with (folder/'raw.jsonl').open('a',encoding='utf-8') as stream: stream.write(json.dumps(row)+'\n')
            tasks=[asyncio.create_task(one(i)) for i in range(count)]
            await asyncio.gather(*tasks)
            manifest['state']='incomplete' if (folder/'stop.requested').exists() else 'completed'
        except BaseException:
            manifest['state']='incomplete'
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            raise
        finally:
            write_json(folder/'manifest.json',manifest)
            write_json(folder/'provider_events.json',list(app.state.observed))
            export(folder,allow_incomplete=True)
            server.should_exit=True; await asyncio.to_thread(thread.join,10); sock.close()
        print(f'{name}: {folder}',flush=True)
