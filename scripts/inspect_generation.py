"""Explicit evaluation-only draft capture; never used by normal UI requests."""
import asyncio
import json
import uuid
from relay.config import settings
from relay.store import Store
from relay.corpus import Retriever
from relay.gateway import Gateway


async def main():
    cfg=settings(); store=Store(cfg.runtime/'relay.db'); retriever=Retriever(cfg)
    evidence=retriever.search('How does Moshi support simultaneous listening and speaking?')
    context='\n\n'.join(f"[{c['id']}] {c['text']}" for c in evidence)
    rid=str(uuid.uuid4()); store.operation(rid)
    result=await Gateway(cfg,store).generate(rid,[
        {'role':'system','content':'Answer only from evidence. Return JSON {"answer": string, "refused": boolean}. Each factual sentence must cite exact supplied bracketed chunk IDs. Use one paragraph. Refuse if evidence insufficient.'},
        {'role':'user','content':'How does Moshi support simultaneous listening and speaking?\nEVIDENCE:\n'+context}])
    folder=cfg.runtime/'evaluation'; folder.mkdir(exist_ok=True)
    (folder/'citation_diagnostic.json').write_text(json.dumps({'draft':result['text'],'evidence':evidence},indent=2),encoding='utf-8')
    print(result['text'])


asyncio.run(main())
