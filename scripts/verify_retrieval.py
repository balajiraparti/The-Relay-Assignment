"""Offline corpus/model smoke checks, not a graded answer-quality benchmark."""
import json
from relay.config import settings
from relay.corpus import Retriever

cfg=settings(); retriever=Retriever(cfg)
questions=[('1706.03762','How does scaled dot-product attention work?'),
           ('2410.00037','How does Moshi listen and speak simultaneously?'),
           ('2507.07955','How does dynamic chunking learn content-dependent boundaries?')]
rows=[]
for expected,question in questions:
    for setting in ('R1','R2','R3'):
        diagnostics={}
        evidence=retriever.search(question,setting=setting,diagnostics=diagnostics)
        assert len(evidence)<= {'R1':4,'R2':5,'R3':6}[setting]
        assert any(c['paper_id']==expected for c in evidence),'expected paper absent'
        rows.append({'question':question,'setting':setting,'expected_paper':expected,
                     'evidence':[{'id':c['id'],'paper_id':c['paper_id'],'page':c['page']} for c in evidence],
                     'diagnostics':diagnostics})
path=cfg.runtime/'verification'/'retrieval.json'; path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps({'index_revision':retriever.revision,'rows':rows},indent=2),encoding='utf-8')
print(json.dumps({'index_revision':retriever.revision,'checks':len(rows),'artifact':str(path)}))
