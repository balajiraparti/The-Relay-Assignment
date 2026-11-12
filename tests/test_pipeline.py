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
