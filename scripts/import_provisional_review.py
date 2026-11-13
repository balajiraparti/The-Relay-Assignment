"""Import the explicitly reviewed, frozen run mapping; never infer grades for new runs."""
import hashlib,json
from relay.config import ROOT,settings
from relay.experiments import write_json
review=json.loads((ROOT/'data/provisional_review.json').read_text(encoding='utf-8'))
folder=settings().runtime/'runs'/review['run_id']
rows=[json.loads(line) for line in (folder/'raw.jsonl').read_text(encoding='utf-8').splitlines()]
grades={}
for row in rows:
    if row['status']!='ok': continue
    grade,rationale=review['reviews'][row['question_id']+':'+row['retrieval_setting']]
    grades[row['request_id']]={'grade':grade,'rationale':rationale,'reviewer':review['reviewer'],
        'author_verified':False,'resource_sha256':hashlib.sha256(json.dumps(row['resource'],sort_keys=True).encode()).hexdigest()}
path=folder/'grades.json'
if path.exists() and any(g.get('author_verified') for g in json.loads(path.read_text()).values()):
    raise RuntimeError('Will not overwrite author-verified grades')
write_json(path,grades)
print('Imported explicit provisional reviews:',len(grades))
