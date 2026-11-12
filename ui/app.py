import os
import uuid
import httpx
import streamlit as st
from relay.local_access import local_origin

st.set_page_config(page_title='The Relay',page_icon='📄',layout='wide')
try: API=local_origin(os.getenv('RELAY_API_URL','http://127.0.0.1:8000'))
except ValueError:
    st.error('Configure RELAY_API_URL as a local HTTP origin.'); st.stop()
st.title('The Relay')
st.caption('Ask about the three research papers. Answers use retrieved passages and citations.')


def call(method,path,**kwargs):
    try:
        with httpx.Client(timeout=10,trust_env=False) as client:
            r=client.request(method,API+path,**kwargs)
        if r.status_code>=400:
            st.error(f'Backend returned {r.status_code}: {r.json().get("detail","Request failed")}')
            return None
        return r.json()
    except (httpx.HTTPError,ValueError):
        st.warning('Backend unavailable. Start FastAPI using the README instructions.')
        return None


info=call('GET','/v1/capabilities')
if info:
    st.info(f"Source: {info['source']} · Model: {info['model']} · v{info['version']}")
    if info['source']=='stand-in': st.warning('Synthetic test responses: not real model answers.')

with st.form('ask'):
    question=st.text_area('Your question',max_chars=4000,placeholder='How does Moshi support simultaneous listening and speaking?')
    left,right=st.columns(2)
    setting=left.selectbox('Retrieval setting',['R2','R1','R3'])
    refine=right.checkbox('Refine long or vague questions',value=True)
    submitted=st.form_submit_button('Ask')
if submitted and question.strip():
    payload={'question':question,'retrieval_setting':setting,'refinement':'auto' if refine else 'off'}
    if st.session_state.get('pending_payload')!=payload:
        st.session_state.pending_payload=payload
        st.session_state.pending_key=str(uuid.uuid4())
    result=call('POST','/v1/requests',json=payload,headers={'Idempotency-Key':st.session_state.pending_key})
    if result:
        st.session_state.active_id=result['id']
        st.session_state.pop('pending_payload',None)


@st.fragment(run_every='1s')
def progress():
    rid=st.session_state.get('active_id')
    if not rid: return
    row=call('GET',f'/v1/requests/{rid}')
    if not row: return
    st.caption(f"Request {rid} · {row['status']}")
    if row['status'] in ('queued','preparing','retrieving','reranking','generating','validating'):
        st.info('Working on your question. Content is shown after citation checks.')
        if st.button('Cancel request',key='cancel'):
            call('POST',f'/v1/requests/{rid}/cancel')
    else:
        result=row.get('result') or {}
        if row['status']=='answered':
            st.markdown(result.get('answer',''))
            for c in result.get('citations',[]):
                with st.expander(f"{c['paper_id']}v{c['version']} · PDF page {c['page']} · {c['id']}"):
                    st.text(c['text'])
        else: st.warning(result.get('answer') or result.get('message') or result.get('reason') or row['status'])
        if result.get('total_ms') is not None: st.caption(f"Backend total: {result['total_ms']:.0f} ms. Citation checks do not prove semantic correctness.")

progress()
with st.expander('Request history'):
    if st.button('Refresh history'): st.session_state.history=call('GET','/v1/requests?limit=20')
    for row in (st.session_state.get('history') or {}).get('items',[]):
        if st.button(f"{row['status']} — {row['question'][:90]}",key=row['id']):
            st.session_state.active_id=row['id']; st.rerun()
