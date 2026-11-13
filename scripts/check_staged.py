"""Check staged contents without printing credentials or document contents."""
import subprocess
from pathlib import Path
from relay.config import ROOT,settings
secret=settings().groq_api_key.get_secret_value().encode()
names=subprocess.check_output(['git','diff','--cached','--name-only','--diff-filter=ACMR','-z'],cwd=ROOT).decode().split('\0')
count=0
for name in filter(None,names):
    path=Path(name)
    assert not any(part in ('.env','runtime','.cache','.venv','.git','__pycache__') for part in path.parts),'Unsafe staged path'
    data=subprocess.check_output(['git','show',':'+name],cwd=ROOT)
    assert not secret or secret not in data,'Configured credential found in staged content'
    if name.startswith('evidence/'):
        assert data==(ROOT/path).read_bytes(),'Evidence bytes changed by Git filters'
    count+=1
print('PASS:',count,'staged files scanned; no configured key or runtime paths; evidence bytes preserved.')
