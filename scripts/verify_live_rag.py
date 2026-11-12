"""One explicit live evaluation run; drafts are separate from operational logs."""
import asyncio
import json
import uuid
from relay.config import settings
from relay.corpus import Retriever
from relay.gateway import Gateway
from relay.pipeline import Pipeline
from relay.store import Store
from relay.telemetry import Telemetry

cfg=settings(); cfg.require_provider()
with Telemetry(cfg.runtime/'logs',service='evaluation',secrets=[cfg.groq_api_key.get_secret_value()]):
    retriever=Retriever(cfg); store=Store(cfg.runtime/'relay.db')
    body={'question':'How does Moshi support simultaneous listening and speaking?','refinement':'off','retrieval_setting':'R2'}
    rid,_=store.create(str(uuid.uuid4()),str(uuid.uuid4()),body)
    folder=cfg.runtime/'evaluation'/rid; folder.mkdir(parents=True)
    class Capture(Gateway):
        async def generate(self,*args,**kwargs):
            result=await super().generate(*args,**kwargs)
            (folder/'generation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            return result
    asyncio.run(Pipeline(cfg,store,Capture(cfg,store),retriever).run(rid,body))
    result=store.get(rid)
    (folder/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
