from relay.pipeline import validate_answer,parse_json,normalize_citations
from relay.api import Ask
import pytest


def test_citation_gate():
    cid='a'*20
    assert validate_answer(f'Claim [{cid}]',[{'id':cid}])
    assert not validate_answer('Claim without evidence',[{'id':cid}])
    assert not validate_answer(f'Claim [{"b"*20}]',[{'id':cid}])
    assert not validate_answer(f'Claim [{cid}]\n\nUncited paragraph',[{'id':cid}])


def test_request_validation():
    with pytest.raises(ValueError): Ask(question='   ')
    with pytest.raises(ValueError): Ask(question='hello',model='override')
    assert Ask(question='  question  ').question=='question'


def test_unicode_citations_preserve_identity():
    cid='a'*20
    answer=normalize_citations(f'Claim 【{cid}】')
    assert answer==f'Claim [{cid}]'
    assert validate_answer(answer,[{'id':cid}])
    assert not validate_answer(answer,[{'id':'b'*20}])
    assert normalize_citations('【not a source】')=='【not a source】'


@pytest.mark.parametrize('http_status,expected',[(408,'timed_out'),(429,'rate_limited'),(503,'failed')])
def test_gateway_outcome_maps_to_request_state(tmp_path,http_status,expected):
    import asyncio
    from types import SimpleNamespace
    from relay.pipeline import Pipeline
    from relay.backends import ModelError
    from relay.store import Store
    store=Store(tmp_path/'db'); rid,_=store.create('key','hash',{'question':'test'})
    class Unavailable:
        async def generate(self,*args,**kwargs): raise ModelError('fixture',http_status)
    chunk={'id':'a'*20,'paper_id':'paper','version':1,'page':1,'text':'evidence'}
    retriever=SimpleNamespace(revision='fixture',search=lambda *args:[chunk])
    pipeline=Pipeline(SimpleNamespace(relay_backend='stand-in'),store,Unavailable(),retriever)
    asyncio.run(pipeline.run(rid,{'question':'test','refinement':'off','retrieval_setting':'R2'}))
    assert store.get(rid)['status']==expected


def test_sentence_coverage_and_unknown_citation():
    cid='a'*20; evidence=[{'id':cid}]
    assert not validate_answer(f'Uncited sentence. Cited sentence [{cid}].',evidence)
    assert validate_answer(f'First sentence [{cid}]. Second sentence. [{cid}]',evidence)
    assert not validate_answer(f'Claim [{cid}] [invented].',evidence)
    assert not validate_answer(f'[{cid}]',evidence)


@pytest.mark.parametrize('answer,refused,status',[
    ('Supported ['+'a'*20+'].',False,'answered'),
    ('Unsupported claim.',True,'refused'),
    ('Invented ['+'b'*20+'].',False,'refused'),
    ('Uncited. Supported ['+'a'*20+'].',False,'refused')])
def test_single_generation_gate(tmp_path,answer,refused,status):
    import asyncio,json
    from types import SimpleNamespace
    from relay.pipeline import Pipeline
    from relay.store import Store
    store=Store(tmp_path/'db'); rid,_=store.create('key','hash',{'question':'test'})
    class Model:
        calls=0
        async def generate(self,*args,**kwargs):
            self.calls+=1
            return {'text':json.dumps({'answer':answer,'refused':refused}),'first_model_token_ms':1,'usage':None}
    model=Model(); evidence=[{'id':'a'*20,'paper_id':'p','version':1,'page':1,'text':'Supported'}]
    pipeline=Pipeline(SimpleNamespace(relay_backend='stand-in',groq_model='fixture'),store,model,
                      SimpleNamespace(revision='fixture',search=lambda *args:evidence))
    asyncio.run(pipeline.run(rid,{'question':'test','refinement':'off','retrieval_setting':'R2'}))
    row=store.get(rid)
    assert row['status']==status and model.calls==1
    if status=='refused': assert row['result']['citations']==[] and answer not in row['result']['answer']


def test_usage_aggregates_preparation_and_retries(tmp_path):
    from relay.store import Store
    s=Store(tmp_path/'db'); s.operation('r')
    for incoming,outgoing in [(10,5),(30,15)]:
        cid=s.reserve('r','groq',100,(10,1000,10,1000)); s.call_state(cid,'succeeded',{'prompt_tokens':incoming,'completion_tokens':outgoing})
    assert s.usage_summary('r')['prompt_tokens']==40
    assert s.usage_summary('r')['completion_tokens']==20
    cid=s.reserve('r','groq',100,(10,1000,10,1000)); s.call_state(cid,'unknown')
    summary=s.usage_summary('r')
    assert summary['prompt_tokens'] is None and summary['known_prompt_tokens']==40 and summary['unknown_usage_calls']==1


@pytest.mark.parametrize('evidence,output,expected_calls,reason',[(False,'{}',0,'no_evidence'),(True,'invalid JSON',1,'invalid_answer_schema')])
def test_absent_evidence_and_malformed_drafts_fail_closed(tmp_path,evidence,output,expected_calls,reason):
    import asyncio
    from types import SimpleNamespace
    from relay.pipeline import Pipeline
    from relay.store import Store
    s=Store(tmp_path/'db'); rid,_=s.create('key','hash',{'question':'test'})
    class Model:
        calls=0
        async def generate(self,*args,**kwargs):
            self.calls+=1; return {'text':output}
    model=Model(); chunk={'id':'a'*20,'paper_id':'p','version':1,'page':1,'text':'source'}
    p=Pipeline(SimpleNamespace(relay_backend='stand-in'),s,model,SimpleNamespace(revision='fixture',search=lambda *a:[chunk] if evidence else []))
    asyncio.run(p.run(rid,{'question':'test','refinement':'off','retrieval_setting':'R2'}))
    assert s.get(rid)['status']=='refused' and s.get(rid)['result']['reason']==reason and model.calls==expected_calls


def test_refinement_keeps_original_for_generation_and_reranking(tmp_path):
    import asyncio,json
    from types import SimpleNamespace
    from relay.pipeline import Pipeline
    from relay.store import Store
    s=Store(tmp_path/'db'); original='Could you please explain Moshi'; rid,_=s.create('key','hash',{'question':original})
    calls=[]; search=[]; cid='a'*20
    class Model:
        async def generate(self,rid,messages,stage='generation',**kwargs):
            calls.append((stage,messages))
            value={'route':'refine','retrieval_query':'explain Moshi'} if stage=='preparation' else {'answer':f'Moshi description [{cid}].','refused':False}
            return {'text':json.dumps(value),'first_model_token_ms':1}
    chunk={'id':cid,'paper_id':'p','version':1,'page':1,'text':'Moshi description'}
    def retrieve(*args): search.append(args); return [chunk]
    p=Pipeline(SimpleNamespace(relay_backend='stand-in',groq_model='fixture'),s,Model(),SimpleNamespace(revision='fixture',search=retrieve))
    asyncio.run(p.run(rid,{'question':original,'refinement':'auto','retrieval_setting':'R2'}))
    assert s.get(rid)['status']=='answered'
    assert search[0][:2]==(original,'explain Moshi')
    assert [x[0] for x in calls]==['preparation','generation']
    assert original in calls[-1][1][-1]['content']
