import asyncio
import json
from types import SimpleNamespace
import pytest
from relay.preparation import prepare,preserves_intent
from relay.backends import ModelError


class Fake:
    pending=0
    def __init__(self,result=None): self.calls=0; self.result=result
    async def generate(self,*args,**kwargs):
        self.calls+=1
        if isinstance(self.result,Exception): raise self.result
        return {'text':self.result}


def test_direct_disabled_and_missing_referent_skip_model():
    for question,mode,route in [('How does Moshi work?','auto','direct'),('please explain Moshi','off','direct'),('How is it trained?','off','clarify')]:
        gateway=Fake(); result=asyncio.run(prepare(question,mode,gateway,'r'))
        assert result.route==route and gateway.calls==0


def test_safe_once_and_busy_bypass():
    gateway=Fake(json.dumps({'route':'refine','retrieval_query':'explain how Moshi works'}))
    result=asyncio.run(prepare('Could you please explain how Moshi works','auto',gateway,'r'))
    assert result.route=='refine' and gateway.calls==1
    gateway.pending=2
    assert asyncio.run(prepare('please explain Moshi','auto',gateway,'r')).reason=='busy_bypass'
    assert gateway.calls==1


@pytest.mark.parametrize('candidate',['Moshi has 32 layers','Moshi does use text','attention is better than Moshi'])
def test_intent_change_rejected(candidate):
    assert not preserves_intent('Please explain why Moshi does not use 16 layers',candidate)


def test_internal_pronouns_and_decimal_values_preserved():
    assert not preserves_intent('Please explain how Moshi hears you','explain how Moshi hears')
    assert not preserves_intent('Please explain the 1.5 threshold','explain the 1,5 threshold')


@pytest.mark.parametrize('value',['[]','bad json','{"route":"refine","retrieval_query":12}',ModelError('transport_timeout')])
def test_bad_preparation_falls_back(value):
    question='please explain Moshi'; gateway=Fake(value)
    result=asyncio.run(prepare(question,'auto',gateway,'r'))
    assert result.query==question and result.route=='direct' and gateway.calls==1


def test_timeout_fallback(monkeypatch):
    from relay import preparation
    monkeypatch.setattr(preparation,'PREPARATION_TIMEOUT',.03)
    class Slow:
        async def generate(self,*args,**kwargs): await asyncio.sleep(10)
    assert asyncio.run(prepare('please explain Moshi','auto',Slow(),'r')).reason=='preparation_failed_fallback'
