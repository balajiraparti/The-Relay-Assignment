"""Streamlit interaction checks with HTTP boundary fixtures, never Groq."""
import httpx
from relay.config import ROOT
from streamlit.testing.v1 import AppTest


def test_form_rerun_clarification_and_history(monkeypatch):
    calls=[]
    rid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    def request(self,method,url,**kwargs):
        calls.append((method,url,kwargs))
        if url.endswith('/capabilities'): data={'source':'stand-in','model':'fixture','version':'test'}
        elif method=='POST': data={'id':rid,'status':'queued'}
        elif '/requests/'+rid in url:
            data={'id':rid,'status':'needs_clarification','question':'Why is it better?',
                'result':{'message':'Which paper and method do you mean?','total_ms':1,'source':'stand-in'}}
        elif '/requests' in url: data={'items':[],'has_more':False,'next_cursor':None}
        else: data={'items':[],'has_more':False,'next_cursor':None}
        return httpx.Response(200,json=data,request=httpx.Request(method,url))
    monkeypatch.setattr(httpx.Client,'request',request)
    app=AppTest.from_file(ROOT/'ui/app.py',default_timeout=10).run()
    assert not app.exception
    app.text_area[0].set_value('Why is it better?')
    next(b for b in app.button if b.label=='Ask').click().run()
    assert not app.exception
    assert any('Which paper' in w.value for w in app.warning)
    app.run()
    assert sum(method=='POST' for method,_,_ in calls)==1
    next(b for b in app.button if b.label=='Answer this clarification').click().run()
    assert app.session_state['clarification_parent']==rid
    next(b for b in app.button if b.label=='Refresh history').click().run()
    assert next(b for b in app.button if b.label=='Next history page').disabled


def test_ambiguous_submit_retains_same_key(monkeypatch):
    keys=[]
    def request(self,method,url,**kwargs):
        if method=='POST':
            keys.append(kwargs['headers']['Idempotency-Key'])
            raise httpx.ReadTimeout('response lost')
        return httpx.Response(200,json={'source':'groq','model':'fixture','version':'test'},request=httpx.Request(method,url))
    monkeypatch.setattr(httpx.Client,'request',request)
    app=AppTest.from_file(ROOT/'ui/app.py',default_timeout=10).run()
    app.text_area[0].set_value('A full question about Moshi')
    next(b for b in app.button if b.label=='Ask').click().run()
    next(b for b in app.button if b.label=='Ask').click().run()
    assert len(keys)==2 and keys[0]==keys[1]
