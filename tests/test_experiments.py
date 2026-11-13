import json
import pytest
from relay.experiments import export,write_json,percentile,COLUMNS
from tests.test_api import client


def fixture_run(folder,state='completed',kind='quality'):
    folder.mkdir(parents=True)
    write_json(folder/'manifest.json',{'id':folder.name,'kind':kind,'state':state,'source':'real',
        'created_at':'2026-11-13T00:00:00Z','expected_arrivals':2})
    rows=[{'request_id':str(i),'scenario':'steady','source':'real','start_time':'2026-11-13T00:00:00Z',
        'first_token_ms':None if i else 9,'total_ms':10+i*10,'status':'ok' if i==0 else 'timeout',
        'retries':i,'tokens_in':3 if i==0 else None,'tokens_out':1 if i==0 else None,
        'retrieval_setting':'R2','answer_grade':None,'outcome':'answered' if i==0 else 'timed_out'} for i in range(2)]
    (folder/'raw.jsonl').write_text('\n'.join(json.dumps(r) for r in rows),encoding='utf-8')
    return rows


def test_exports_preserve_unknowns_and_require_grades(tmp_path):
    folder=tmp_path/'run'; fixture_run(folder)
    with pytest.raises(ValueError): export(folder)
    result=export(folder,True)
    summary=result['summaries'][0]
    assert not result['graded'] and summary['first_token_n']==1 and summary['total_p50']==15
    assert summary['tokens_per_answer'] is None and summary['paid_equivalent_usd_per_1000_answers'] is None
    write_json(folder/'grades.json',{str(i):{'grade':'correct' if i==0 else 'refused_wrongly','reviewer':'test','rationale':'fixture only'} for i in range(2)})
    assert export(folder)['graded']
    first=(folder/'results.csv').read_bytes(); export(folder)
    assert first==(folder/'results.csv').read_bytes()
    assert first.decode().splitlines()[0]==','.join(COLUMNS)


def test_incomplete_and_duplicate_arrivals(tmp_path):
    folder=tmp_path/'run'; rows=fixture_run(folder,state='incomplete',kind='load')
    with pytest.raises(ValueError): export(folder)
    assert not export(folder,True)['complete']
    with (folder/'raw.jsonl').open('a') as out: out.write('\n'+json.dumps(rows[0]))
    with pytest.raises(ValueError,match='duplicate'): export(folder,True)


def test_percentile_boundaries():
    assert percentile([], .95) is None
    assert percentile([10],.99)==10
    assert percentile([10,20],.95)==19.5


def test_run_endpoints_refuse_ungraded_and_path_traversal(client):
    from relay import api
    rid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    folder=api.app.state.cfg.runtime/'runs'/rid
    fixture_run(folder)
    assert client.get('/v1/runs').json()['items'][0]['id']==rid
    assert client.get(f'/v1/runs/{rid}/results.csv').status_code==409
    response=client.get(f'/v1/runs/{rid}/results.csv?allow_incomplete=true')
    assert response.status_code==200 and 'incomplete' in response.headers['content-disposition']
    assert client.get('/v1/runs/not-a-uuid').status_code==404
    assert client.get(f'/v1/runs/{rid}/events').status_code==200
