import asyncio
import json
import httpx
import pytest
from relay.backends import HTTPBackend
from relay.calibration import calibrate
from relay.config import Settings


def test_groq_contract_content_only_usage_and_headers():
    def handle(request):
        assert str(request.url)=='https://api.groq.com/openai/v1/chat/completions'
        assert request.headers['authorization']=='Bearer synthetic-secret'
        assert json.loads(request.content)['model']=='openai/gpt-oss-120b'
        rows=[{'choices':[{'delta':{'reasoning':'private reasoning'}}]},
              {'choices':[{'delta':{'content':'answer'}}]},
              {'choices':[{'delta':{},'finish_reason':'stop'}],'x_groq':{'usage':{'prompt_tokens':10,'completion_tokens':5}}}]
        return httpx.Response(200,text=''.join('data: '+json.dumps(r)+'\n\n' for r in rows)+'data: [DONE]\n\n',
                              headers={'x-ratelimit-limit-tokens':'8000','set-cookie':'private'})
    cfg=Settings(_env_file=None,groq_api_key='synthetic-secret')
    async def run(): return [e async for e in HTTPBackend(cfg,httpx.MockTransport(handle)).stream('r',[{'role':'user','content':'q'}],10)]
    events=asyncio.run(run())
    assert next(e.value for e in events if e.kind=='http_status')==200
    assert [e.value for e in events if e.kind=='content']==['answer']
    assert next(e.value for e in events if e.kind=='usage')['prompt_tokens']==10
    assert next(e.value for e in events if e.kind=='headers')=={'x-ratelimit-limit-tokens':'8000'}
    assert events[-1].kind=='done'


def test_calibration_rejects_impossible_and_synthetic_data(tmp_path):
    path=tmp_path/'data.json'
    path.write_text(json.dumps([{'source':'groq','status':'ok','first_token_ms':20,'total_ms':30}]))
    profile=calibrate(path)
    assert profile['sample_count']==1 and profile['tail_samples_seconds']==[.01] and len(profile['source_sha256'])==64
    for row in ({'source':'stand-in','status':'ok','first_token_ms':1,'total_ms':2},
                {'source':'groq','status':'ok','first_token_ms':3,'total_ms':2}):
        path.write_text(json.dumps([row]))
        with pytest.raises(ValueError): calibrate(path)
