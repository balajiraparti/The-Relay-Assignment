"""Allowlisted, credential-scanned source/evidence archive. Does not publish it."""
import hashlib,json,subprocess,zipfile
from pathlib import Path
from relay.config import ROOT,settings

cfg=settings(); secret=cfg.groq_api_key.get_secret_value()
paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
files=[]
for name in paths:
    if not name: continue
    p=Path(name)
    if p.name.startswith('.env') and p.name!='.env.example': raise RuntimeError('tracked_environment_file')
    if any(part in ('runtime','.cache','.venv','.git','.codex','.agents','__pycache__') for part in p.parts): raise RuntimeError('tracked_runtime_file')
    if p.suffix in ('.db','.bak','.zip'): continue
    raw=(ROOT/p).read_bytes()
    if secret and secret.encode() in raw: raise RuntimeError('credential_found')
    files.append((name,raw))
out=ROOT/'output'; out.mkdir(exist_ok=True)
archive=out/'The_Relay_Submission.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
    for name,raw in files: bundle.writestr(name,raw)
    bundle.writestr('PACKAGE_MANIFEST.json',json.dumps({'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in files},
        'status':'Author-review draft; see docs/SUBMISSION_CHECKLIST.md'},indent=2))
print('Packaged',len(files),'files:',archive)
