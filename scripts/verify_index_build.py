"""Rebuild twice offline to verify content-addressed index reproducibility."""
import json
from relay.config import settings
from relay.corpus import ingest

cfg=settings()
first=ingest(cfg); print('First build:',first['revision'],flush=True)
second=ingest(cfg); print('Second build:',second['revision'],flush=True)
assert first==second,'non-repeatable index build'
path=cfg.runtime/'verification'/'index_build.json'; path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps({'repeated_build_match':True,'result':second},indent=2),encoding='utf-8')
