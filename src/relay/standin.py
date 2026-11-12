"""Explicitly synthetic streaming provider; defaults are uncalibrated assumptions."""
import asyncio
import json
import os
import random
import re
import time
from pathlib import Path
from collections import deque
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app=FastAPI(title='Relay stand-in (synthetic)')
workers=asyncio.Semaphore(int(os.getenv('STANDIN_WORKERS','2')))
arrivals=deque()
lock=asyncio.Lock()
rng=random.Random(int(os.getenv('STANDIN_SEED','42')))
calibration_path=os.getenv('STANDIN_CALIBRATION')
calibration=json.loads(Path(calibration_path).read_text()) if calibration_path else None


@app.post('/v1/chat/completions')
async def completion(request: Request):
    body=await request.json()
    now=time.monotonic()
    async with lock:
        while arrivals and arrivals[0][0]<now-86400: arrivals.popleft()
        token_reservation=sum(len(m.get('content','')) for m in body.get('messages',[]))//4+body.get('max_completion_tokens',256)
        for window,req_env,tok_env,req_default,tok_default in [(60,'STANDIN_RPM','STANDIN_TPM',30,8000),(86400,'STANDIN_RPD','STANDIN_TPD',1000,200000)]:
            active=[a for a in arrivals if a[0]>now-window]
            if len(active)>=int(os.getenv(req_env,str(req_default))) or sum(a[1] for a in active)+token_reservation>int(os.getenv(tok_env,str(tok_default))):
                return JSONResponse({'error':'simulated_rate_limit'},429,headers={'retry-after':'5'})
        arrivals.append((now,token_reservation))
        fail=rng.random()<float(os.getenv('STANDIN_FAILURE_RATE','0'))
        sample=rng.randrange(calibration['sample_count']) if calibration else None
    if fail: return JSONResponse({'error':'simulated_failure'},503)
    text=' '.join(m['content'] for m in body.get('messages',[]))
    if 'PREPARE_QUERY' in text:
        answer=json.dumps({'route':'direct','query':body['messages'][-1]['content']})
    else:
        ids=re.findall(r'\[([a-f0-9]{20})\]',text)
        answer=json.dumps({'answer':f'Synthetic test response [{ids[0]}]' if ids else 'No fixture evidence.', 'refused':not bool(ids)})
    async def stream():
        async with workers:
            delay=calibration['first_delay_samples_seconds'][sample] if calibration else float(os.getenv('STANDIN_FIRST_DELAY','0.2'))
            tail=calibration['tail_samples_seconds'][sample] if calibration else None
            await asyncio.sleep(delay)
            for i in range(0,len(answer),16):
                if int(os.getenv('STANDIN_FAIL_AFTER_CHUNKS','0')) and i//16>=int(os.environ['STANDIN_FAIL_AFTER_CHUNKS']):
                    yield 'data: '+json.dumps({'error':'injected_midstream_failure'})+'\n\n'
                    return
                yield 'data: '+json.dumps({'choices':[{'delta':{'content':answer[i:i+16]}}]})+'\n\n'
                await asyncio.sleep(tail/max(1,(len(answer)+15)//16) if tail is not None else float(os.getenv('STANDIN_CHUNK_DELAY','0.02')))
            yield 'data: '+json.dumps({'choices':[{'delta':{},'finish_reason':'stop'}], 'usage':{'prompt_tokens':len(text)//4,'completion_tokens':len(answer)//4}})+'\n\n'
            yield 'data: [DONE]\n\n'
    return StreamingResponse(stream(),media_type='text/event-stream')
