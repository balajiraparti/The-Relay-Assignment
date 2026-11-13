"""Author's explicit offline grade entry. Never invokes a model."""
import argparse,json,uuid
from relay.config import settings
from relay.experiments import GRADES,write_json

parser=argparse.ArgumentParser()
parser.add_argument('run_id'); parser.add_argument('request_id')
parser.add_argument('--grade',required=True,choices=sorted(GRADES))
parser.add_argument('--rationale',required=True); parser.add_argument('--reviewer',required=True)
args=parser.parse_args()
folder=settings().runtime/'runs'/str(uuid.UUID(args.run_id))
rows=[json.loads(line) for line in (folder/'raw.jsonl').read_text(encoding='utf-8').splitlines()]
if not any(r['request_id']==args.request_id and r['status']=='ok' for r in rows): parser.error('No completed answer/refusal for that request')
path=folder/'grades.json'; grades=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
grades[args.request_id]={'grade':args.grade,'rationale':args.rationale,'reviewer':args.reviewer,'author_verified':True}
write_json(path,grades)
print('Grade saved; rerun export to regenerate tables.')
