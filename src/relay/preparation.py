"""At most one optional rewrite; conservative lexical intent guards."""
import asyncio
import json
import re
from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from relay.backends import ModelError


class Rewrite(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    route:Literal['direct','refine','clarify']
    retrieval_query:str=Field(max_length=4000)


@dataclass
class Prepared:
    query:str
    route:str='direct'
    reason:str='clear_query'
    clarification:str|None=None


FILLER={'please','could','can','you','me','i','just','um','uh','kindly'}
PREPARATION_TIMEOUT=5


def intent_tokens(text):
    words=re.findall(r"\d+(?:\.\d+)*|[a-z]+(?:['’][a-z]+)?",text.lower())
    # Courtesy removal is limited to the prefix: internal pronouns/modal words
    # may carry the question's meaning and must not disappear.
    while words and words[0] in FILLER: words.pop(0)
    return words


def preserves_intent(original,candidate):
    # Only courtesy/filler removal is accepted automatically. Entities, numeric
    # values, negations, qualifiers and word order must remain; synonyms fall back.
    return bool(candidate.strip()) and intent_tokens(original)==intent_tokens(candidate)


def missing_referent(question):
    return bool(re.fullmatch(r'\s*(?:why is (?:it|this|that) better|how does (?:it|this|that) work|explain (?:it|this|that)|how is (?:it|this|that) trained)[?.!\s]*',question,re.I))


async def prepare(question,mode,gateway,rid,on_start=None):
    if missing_referent(question):
        return Prepared(question,'clarify','missing_referent','Which paper or mechanism are you asking about?')
    if mode=='off': return Prepared(question,reason='disabled')
    needs_rewrite=len(question.split())>45 or bool(re.search(r'\b(?:please|could you|can you|um|uh)\b',question,re.I))
    if not needs_rewrite: return Prepared(question)
    if getattr(gateway,'pending',0)>=getattr(getattr(gateway,'cfg',None),'model_concurrency',2):
        return Prepared(question,reason='busy_bypass')
    if on_start: on_start()
    try:
        async with asyncio.timeout(PREPARATION_TIMEOUT):
            result=await gateway.generate(rid,[{'role':'system','content':
                'PREPARE_QUERY: Remove only courtesy/filler words from the query. Preserve all other words in order, especially entities, numbers, qualifiers and negations. Do not answer. Return JSON only: {"route":"refine" or "direct" or "clarify","retrieval_query":"..."}.'},
                {'role':'user','content':question}],stage='preparation',cap=512,response_format={'type':'json_object'})
        rewrite=Rewrite.model_validate(json.loads(result['text']))
        if rewrite.route=='clarify':
            return Prepared(question,'clarify','model_clarification','Please specify the paper and the mechanism you want explained.')
        if rewrite.route=='refine' and preserves_intent(question,rewrite.retrieval_query):
            return Prepared(rewrite.retrieval_query,'refine','guarded_rewrite')
        return Prepared(question,reason='unchanged_or_unsafe_rewrite')
    except (ValueError,TypeError,KeyError,ModelError,TimeoutError):
        return Prepared(question,reason='preparation_failed_fallback')
