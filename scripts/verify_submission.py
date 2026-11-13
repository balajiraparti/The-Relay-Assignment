"""Offline consistency checks against retained raw evidence; no provider calls."""
import csv,hashlib,json,math,subprocess,sys
from datetime import datetime
from pypdf import PdfReader
from relay.config import ROOT
from relay.experiments import COLUMNS,GRADES

base=ROOT/'evidence/2026-11-13'
with (base/'results.csv').open(encoding='utf-8',newline='') as file:
    reader=csv.DictReader(file); assert reader.fieldnames==COLUMNS; rows=list(reader)
assert len({r['request_id'] for r in rows})==len(rows)
raw={}
for path in base.glob('*/raw.jsonl'):
    records=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    manifest=json.loads((path.parent/'manifest.json').read_text())
    assert manifest['state']=='completed' and len(records)==manifest['expected_arrivals']
    raw.update((r['request_id'],r) for r in records)
assert set(raw)=={r['request_id'] for r in rows}
for row in rows:
    assert row['source'] in ('real','stand-in') and row['status'] in ('ok','rate_limited','timeout','error')
    assert not row['answer_grade'] or row['answer_grade'] in GRADES
    assert datetime.fromisoformat(row['start_time']).utcoffset().total_seconds()==0
    for key in ('first_token_ms','total_ms','tokens_in','tokens_out','retries'):
        actual=raw[row['request_id']].get(key)
        assert (row[key]=='' and actual is None) or (row[key]!='' and math.isfinite(float(row[key])) and float(row[key])>=0 and float(row[key])==actual)
provenance=json.loads((base/'provenance.json').read_text())
for name,digest in provenance['files'].items(): assert hashlib.sha256((base/name).read_bytes()).hexdigest()==digest,name
before=(base/'tables.json').read_bytes(),(base/'TABLES.md').read_bytes()
subprocess.run([sys.executable,str(ROOT/'scripts/report_tables.py')],check=True,capture_output=True)
assert before==((base/'tables.json').read_bytes(),(base/'TABLES.md').read_bytes())
assert len(PdfReader(ROOT/'output/pdf/The_Relay_Assignment_Report.pdf').pages)==2
questions={raw[row['request_id']]['question_id'] for row in rows if row['source']=='real'}
assert len(questions)>=15
frozen=ROOT/'data/evaluation_questions.v1.json'
quality_manifest=json.loads((base/'4bbf5470-b3b6-45fd-957e-16a01dc24aff/manifest.json').read_text())
assert hashlib.sha256(frozen.read_bytes()).hexdigest()==quality_manifest['question_sha256']
print(f'PASS: {len(rows)} unique CSV rows match raw records; {len(questions)} questions; tables reproduce byte-for-byte; hashes valid; report is two pages.')
