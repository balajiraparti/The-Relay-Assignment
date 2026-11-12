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
