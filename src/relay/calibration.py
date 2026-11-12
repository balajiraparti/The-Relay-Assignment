"""Calibration from measured successful observations, with explicit provenance."""
import hashlib
import json
import math
from pathlib import Path


def calibrate(path):
    path=Path(path); raw=path.read_bytes(); rows=json.loads(raw)
    if not isinstance(rows,list): raise ValueError('invalid_observations')
    good=[]
    for row in rows:
        if row.get('source')!='groq' or row.get('status')!='ok': continue
        first,total=row.get('first_token_ms'),row.get('total_ms')
        if any(type(v) not in (float,int) or not math.isfinite(v) for v in (first,total)) or not 0<=first<=total:
            raise ValueError('invalid_observation_timing')
        good.append(row)
    if not good: raise ValueError('no_successful_real_observations')
    return {'source_file':str(path.resolve()),'source_sha256':hashlib.sha256(raw).hexdigest(),
            'sample_count':len(good),'excluded_count':len(rows)-len(good),
            'first_delay_samples_seconds':[r['first_token_ms']/1000 for r in good],
            'tail_samples_seconds':[(r['total_ms']-r['first_token_ms'])/1000 for r in good],
            'limitations':'Small generic-prompt sample; includes network/client overhead. Does not establish paper-answer latency, quality, failure probabilities, quota recovery or load-dependent scheduling.'}
