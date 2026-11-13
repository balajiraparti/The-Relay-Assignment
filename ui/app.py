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
            st.error(f'Backend returned {r.status_code}: {r.json().get("error",{}).get("code","Request failed")}')
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
    if st.session_state.get('clarification_parent'):
        st.caption('Clarification follow-up: include the paper and the full question; previous messages are not model memory.')
    question=st.text_area('Your question',max_chars=4000,placeholder='How does Moshi support simultaneous listening and speaking?')
    left,right=st.columns(2)
    setting=left.selectbox('Retrieval setting',['R2','R1','R3'])
    refine=right.checkbox('Refine long or vague questions',value=True)
    submitted=st.form_submit_button('Ask')
if submitted and question.strip():
    payload={'question':question,'retrieval_setting':setting,'refinement':'auto' if refine else 'off'}
    if st.session_state.get('clarification_parent'): payload['parent_request_id']=st.session_state.clarification_parent
    if st.session_state.get('pending_payload')!=payload:
        st.session_state.pending_payload=payload
        st.session_state.pending_key=str(uuid.uuid4())
    result=call('POST','/v1/requests',json=payload,headers={'Idempotency-Key':st.session_state.pending_key})
    if result:
        st.session_state.active_id=result['id']
        st.session_state.poll_active=True
        st.session_state.pop('clarification_parent',None)
        st.session_state.pop('pending_payload',None)


@st.fragment(run_every='1s' if st.session_state.get('poll_active') else None)
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
        if st.session_state.get('poll_active'):
            st.session_state.poll_active=False
            st.rerun()
        result=row.get('result') or {}
        if row['status']=='answered':
            st.markdown(result.get('answer',''))
            for c in result.get('citations',[]):
                with st.expander(f"{c['paper_id']}v{c['version']} · PDF page {c['page']} · {c['id']}"):
                    st.text(c['text'])
        else:
            reason=result.get('reason')
            if row['status']=='rate_limited':
                message='The daily model budget is exhausted. Your request is saved. Please try again after capacity resets; the reset time is not known.' if reason=='local_quota_day' else 'Model capacity is temporarily unavailable. Your request is saved; please try again later. No answer was generated for this request.'
            elif row['status']=='timed_out': message='This request exceeded its waiting or response deadline. You can try again explicitly.'
            elif row['status']=='cancelled': message='Request cancelled. Already dispatched provider work may still consume quota.'
            elif row['status']=='failed': message='The request failed. Its details are retained in history; no unverified answer was released.'
            else: message=result.get('answer') or result.get('message') or reason or row['status']
            st.warning(message)
        if row['status']=='needs_clarification' and st.button('Answer this clarification'):
            st.session_state.clarification_parent=rid; st.rerun()
        if result.get('total_ms') is not None: st.caption(f"Backend total: {result['total_ms']:.0f} ms. Citation checks do not prove semantic correctness.")
        with st.expander('Timing and usage'):
            st.json({'source':result.get('source') or row.get('body',{}).get('source'),
                'provider_first_content_ms':result.get('first_model_token_ms'),
                'pipeline_total_ms':result.get('total_ms'),'usage':result.get('usage')})
            st.caption('Provider first content precedes validation. These numbers do not measure browser receipt. Null means unavailable.')

progress()
with st.expander('Request history'):
    if st.button('Refresh history'):
        st.session_state.history_cursors=[None]
        st.session_state.history=call('GET','/v1/requests?limit=20')
    history=st.session_state.get('history') or {}
    previous,next_column=st.columns(2)
    cursors=st.session_state.get('history_cursors',[None])
    if previous.button('Previous history page',disabled=len(cursors)<2):
        cursors.pop(); st.session_state.history_cursors=cursors
        st.session_state.history=call('GET','/v1/requests',params={'limit':20,**({'cursor':cursors[-1]} if cursors[-1] else {})}); st.rerun()
    if next_column.button('Next history page',disabled=not history.get('has_more')):
        cursors.append(history['next_cursor']); st.session_state.history_cursors=cursors
        st.session_state.history=call('GET','/v1/requests',params={'limit':20,'cursor':cursors[-1]}); st.rerun()
    for row in (st.session_state.get('history') or {}).get('items',[]):
        if st.button(f"{row['status']} — {row['question'][:90]}",key=row['id']):
            st.session_state.active_id=row['id']; st.session_state.poll_active=True; st.rerun()

with st.expander('Experiments and downloads'):
    st.caption('Runs are started from the CLI. Synthetic runs measure capacity behaviour, not model answer quality.')
    if st.button('Refresh experiments'):
        st.session_state.runs=call('GET','/v1/runs?limit=20')
    run_page=st.session_state.get('runs') or {}
    if st.button('Next experiment page',disabled=not run_page.get('has_more')):
        st.session_state.runs=call('GET','/v1/runs',params={'limit':20,'cursor':run_page['next_cursor']}); st.rerun()
    for run in run_page.get('items',[]):
        if st.button(f"{run['source']} · {run.get('scenario',run['kind'])} · {run['state']} · {run['id'][:8]}",key='run-'+run['id']):
            st.session_state.selected_run=run['id']
    selected=st.session_state.get('selected_run')
    if selected:
        detail=call('GET',f'/v1/runs/{selected}')
        if detail:
            st.json(detail)
            if detail['state']=='running':
                if st.button('Stop future arrivals'):
                    call('POST',f'/v1/runs/{selected}/stop'); st.rerun()
            else:
                incomplete=st.checkbox('Allow explicitly incomplete or ungraded export',value=False)
                if st.button('Prepare CSV download'):
                    try:
                        with httpx.Client(timeout=10,trust_env=False) as client:
                            response=client.get(API+f'/v1/runs/{selected}/results.csv',params={'allow_incomplete':str(incomplete).lower()})
                        if response.status_code==200:
                            st.download_button('Download results',response.content,
                                file_name='results.incomplete.csv' if incomplete and not detail.get('summary',{}).get('graded') else 'results.csv',mime='text/csv')
                        else: st.warning('Run is incomplete or ungraded. Review it before final export.')
                    except httpx.HTTPError: st.warning('Download unavailable; retry after the backend reconnects.')
