import json
from types import SimpleNamespace
import numpy as np
import pytest
from relay import corpus,extraction


class Tokenizer:
    def encode(self,text,other=None,**kwargs): return list(text+(other or ''))


class Embedding:
    max_seq_length=256
    tokenizer=Tokenizer()
    def encode(self,texts,**kwargs): return np.tile([1.,0.,0.],(len(texts),1))


def audit():
    return {'schema_version':1,'papers':[{'paper_id':'p','version':1,'sha256':'hash'}],
            'pages':[{'paper_id':'p','version':1,'page':1,'text':'alpha beta gamma delta '*30,'warnings':[]}],
            'limitations':[]}


@pytest.fixture
def setup_index(tmp_path,monkeypatch):
    cfg=SimpleNamespace(runtime=tmp_path,embedding_model='fixture')
    monkeypatch.setattr(corpus,'extract',lambda _:audit())
    monkeypatch.setattr(corpus,'local_models',lambda *a:(Embedding(),None))
    monkeypatch.setattr(corpus,'model_identity',lambda _: {'fixture':1})
    return cfg


def test_repeat_index_exact_offsets_and_failure_keeps_active(setup_index,monkeypatch):
    cfg=setup_index
    first=corpus.ingest(cfg,50,10); second=corpus.ingest(cfg,50,10)
    assert first['revision']==second['revision']
    folder=cfg.runtime/'indexes'/first['revision']
    data,_,_=corpus.load_artifacts(folder,first['revision'])
    assert all(c['offset']>=0 and c['tokens']<=50 for c in data['chunks'])
    old=(cfg.runtime/'active.txt').read_text()
    next_index=corpus.ingest(cfg,60,10)
    assert folder.exists() and next_index['revision']!=old
    pointer=(cfg.runtime/'active.txt').read_text()
    monkeypatch.setattr(corpus,'extract',lambda _:(_ for _ in ()).throw(ValueError('wrong version')))
    with pytest.raises(ValueError): corpus.ingest(cfg)
    assert (cfg.runtime/'active.txt').read_text()==pointer


@pytest.mark.parametrize('filename',['manifest.json','pages.json','keywords.json','vectors.faiss'])
def test_corruption_rejected_before_model_load(setup_index,filename,monkeypatch):
    cfg=setup_index; result=corpus.ingest(cfg,50,10)
    path=cfg.runtime/'indexes'/result['revision']/filename
    path.write_bytes(path.read_bytes()+b'x')
    monkeypatch.setattr(corpus,'local_models',lambda *a:pytest.fail('must validate before loading models'))
    with pytest.raises(ValueError,match='checksum'): corpus.Retriever(cfg)


def test_audit_versions_warnings_and_checksums(tmp_path,monkeypatch):
    expected={}
    for pid,v in extraction.PAPERS.items():
        path=tmp_path/(pid+'.pdf'); path.write_text(pid)
        expected[path.name]={'paper_id':pid,'version':v,'sha256':extraction.checksum(path)}
    def reader(path):
        pid=path.stem; version=extraction.PAPERS[pid]
        return SimpleNamespace(is_encrypted=False,pages=[SimpleNamespace(extract_text=lambda:f'arXiv:{pid}v{version}'),SimpleNamespace(extract_text=lambda:'')])
    monkeypatch.setattr(extraction,'PdfReader',reader)
    result=extraction.extract(tmp_path,expected)
    assert len(result['pages'])==6
    assert sum('empty_page_no_ocr' in p['warnings'] for p in result['pages'])==3
    saved=extraction.save_audit(result,tmp_path/'runtime')
    assert json.loads(saved.read_text())==result
    item=next(iter(expected)); expected[item]['version']=99
    with pytest.raises(ValueError,match='version'): extraction.extract(tmp_path,expected)
    expected[item]['sha256']='wrong'
    with pytest.raises(ValueError,match='checksum'): extraction.extract(tmp_path,expected)


def test_rrf_deduplicated_and_bounded():
    ids,scores=corpus.fuse([[1,1,2],[2,3,-1]],2)
    assert ids==[2,1] and scores[1]==1/61


def test_weight_fingerprint_detects_same_name_model_changes():
    import torch
    model=torch.nn.Linear(2,2)
    old=corpus.weights_checksum(model)
    assert corpus.weights_checksum(model)==old
    with torch.no_grad(): model.weight[0,0]+=1
    assert corpus.weights_checksum(model)!=old


def test_retrieval_bounds_original_question_and_diagnostics():
    r=corpus.Retriever.__new__(corpus.Retriever)
    r.revision='fixture'; r.chunks=[{'id':str(i),'text':str(i)} for i in range(40)]
    r.bm25=SimpleNamespace(get_scores=lambda _:np.arange(40))
    r.embedding=Embedding()
    r.index=SimpleNamespace(search=lambda v,k:(None,np.array([list(range(k))])))
    pairs=[]
    r.cross=SimpleNamespace(max_length=512,tokenizer=Tokenizer(),predict=lambda p:(pairs.extend(p) or np.arange(len(p))))
    detail={}; result=r.search('original','rewritten','R2',detail)
    assert len(result)==5 and len(pairs)<=16 and all(p[0]=='original' for p in pairs)
    assert len(detail['candidates'])<=16 and sum(c['selected'] for c in detail['candidates'])==5
    pairs.clear(); assert len(r.search('query',setting='R1'))==4 and not pairs
    assert len(r.search('query',setting='R3'))==6
    with pytest.raises(ValueError,match='too_long'): r.search('a'*513)
    with pytest.raises(ValueError): r.search('query',setting='bad')
    assert r.search('?!')==[]
