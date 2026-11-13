import hashlib
import json
import os
import re
import shutil
import time
import uuid
from importlib.metadata import version
import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi
from relay.config import ROOT
from relay.extraction import PAPERS, canonical, checksum, extract, save_audit
from relay.telemetry import current


def tokens(text): return re.findall(r'\w+',text.lower())


def local_models(cfg, rerank=True):
    os.environ.setdefault('HF_HOME',str(ROOT/'.cache'/'huggingface'))
    from sentence_transformers import SentenceTransformer,CrossEncoder
    emb=SentenceTransformer(cfg.embedding_model,device='cpu')
    return emb,CrossEncoder(cfg.reranker_model,device='cpu') if rerank else None


def model_identity(model):
    return {'max_seq_length':model.max_seq_length,
            'tokenizer_sha256':hashlib.sha256(canonical(model.tokenizer.get_vocab())).hexdigest(),
            'weights_sha256':weights_checksum(model),
            'revision':getattr(model[0].auto_model.config,'_commit_hash',None)}


def weights_checksum(model):
    digest=hashlib.sha256()
    for name,tensor in sorted(model.state_dict().items()):
        digest.update(name.encode()); digest.update(str(tuple(tensor.shape)).encode())
        digest.update(str(tensor.dtype).encode())
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def split_pages(audit,model,size,overlap):
    if not 0 < size <= model.max_seq_length-16 or not 0 <= overlap < size:
        raise ValueError('invalid_chunk_budget')
    length=lambda text: len(model.tokenizer.encode(text,add_special_tokens=False,truncation=False))
    splitter=RecursiveCharacterTextSplitter(chunk_size=size,chunk_overlap=overlap,
        length_function=length,separators=['\n\n','\n',' ',''])
    hashes={p['paper_id']:p['sha256'] for p in audit['papers']}
    chunks=[]
    for page in audit['pages']:
        previous=-1
        for text in splitter.split_text(page['text']):
            # Library start_index mixes character offsets with token overlap.
            start=page['text'].find(text,previous+1)
            if start<0: raise ValueError('chunk_source_mapping_failed')
            previous=start; count=length(text)
            if count>size or len(model.tokenizer.encode(text,truncation=False))>model.max_seq_length:
                raise ValueError('chunk_token_limit')
            cid=hashlib.sha256(f"{hashes[page['paper_id']]}:{page['page']}:{start}:{text}".encode()).hexdigest()[:20]
            chunks.append({'id':cid,'paper_id':page['paper_id'],'version':page['version'],
                'page':page['page'],'offset':start,'end_offset':start+len(text),'tokens':count,'text':text})
    if not chunks or len({c['id'] for c in chunks})!=len(chunks): raise ValueError('invalid_chunk_ids')
    return chunks


def load_artifacts(folder,revision):
    import faiss
    raw=(folder/'manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()[:16]!=revision: raise ValueError('manifest_checksum_mismatch')
    data=json.loads(raw)
    if data.get('schema_version')!=2: raise ValueError('index_schema_mismatch_reingest')
    for name in ('vectors.faiss','keywords.json','pages.json'):
        if checksum(folder/name)!=data['artifacts'][name]: raise ValueError('artifact_checksum_mismatch: '+name)
    audit=json.loads((folder/'pages.json').read_bytes())
    pages={(p['paper_id'],p['page']):p for p in audit['pages']}
    chunks=data['chunks']
    if not chunks or len({c['id'] for c in chunks})!=len(chunks): raise ValueError('chunk_mapping_mismatch')
    for c in chunks:
        page=pages[(c['paper_id'],c['page'])]
        if c['offset']<0 or page['text'][c['offset']:c['end_offset']]!=c['text']:
            raise ValueError('chunk_source_mapping_failed')
    keywords=json.loads((folder/'keywords.json').read_bytes())
    if keywords != [tokens(c['text']) for c in chunks]: raise ValueError('keyword_mapping_mismatch')
    index=faiss.read_index(str(folder/'vectors.faiss'))
    if index.ntotal!=len(chunks) or index.d!=data['dimensions']: raise ValueError('index_mapping_mismatch')
    return data,index,keywords


def ingest(cfg,chunk_size=200,overlap=30):
    audit=extract(ROOT/'data'); save_audit(audit,cfg.runtime)
    model,_=local_models(cfg,False)
    size=min(chunk_size,model.max_seq_length-16)
    chunks=split_pages(audit,model,size,overlap)
    matrix=np.asarray(model.encode([c['text'] for c in chunks],normalize_embeddings=True,show_progress_bar=True),dtype='float32')
    if matrix.ndim!=2 or not np.isfinite(matrix).all() or not np.allclose(np.linalg.norm(matrix,axis=1),1,atol=1e-4):
        raise ValueError('invalid_embeddings')
    import faiss
    index=faiss.IndexFlatIP(matrix.shape[1]); index.add(matrix)
    base=cfg.runtime/'indexes'; base.mkdir(parents=True,exist_ok=True)
    temp=base/('.building-'+uuid.uuid4().hex); temp.mkdir()
    try:
        (temp/'pages.json').write_bytes(canonical(audit))
        (temp/'keywords.json').write_bytes(canonical([tokens(c['text']) for c in chunks]))
        faiss.write_index(index,str(temp/'vectors.faiss'))
        payload={'schema_version':2,'papers':audit['papers'],'embedding_model':cfg.embedding_model,
            'model_identity':model_identity(model),'chunk_size':size,'overlap':overlap,'chunks':chunks,
            'dimensions':matrix.shape[1],'normalization':'l2',
            'packages':{p:version(p) for p in ('pypdf','langchain-text-splitters','sentence-transformers','faiss-cpu')},
            'artifacts':{name:checksum(temp/name) for name in ('pages.json','keywords.json','vectors.faiss')}}
        raw=canonical(payload); revision=hashlib.sha256(raw).hexdigest()[:16]
        (temp/'manifest.json').write_bytes(raw); load_artifacts(temp,revision)
        destination=base/revision
        if destination.exists(): load_artifacts(destination,revision)
        else: temp.rename(destination)
        pointer=cfg.runtime/('active-'+uuid.uuid4().hex+'.tmp')
        pointer.write_text(revision,encoding='utf-8'); os.replace(pointer,cfg.runtime/'active.txt')
        log=current()
        if log: log.emit('index_published',index_revision=revision,chunks=len(chunks),pages=len(audit['pages']))
        return {'revision':revision,'papers':audit['papers'],'chunks':len(chunks),'chunk_size_tokens':size,
                'warnings':sum(len(p['warnings']) for p in audit['pages'])}
    finally:
        if temp.exists(): shutil.rmtree(temp)


def fuse(rankings,limit=16):
    scores={}
    for ranking in rankings:
        for rank,i in enumerate(dict.fromkeys(ranking),1):
            if i>=0: scores[i]=scores.get(i,0)+1/(60+rank)
    return sorted(scores,key=lambda i:(-scores[i],i))[:limit],scores


class Retriever:
    def __init__(self,cfg):
        self.revision=(cfg.runtime/'active.txt').read_text().strip()
        if not re.fullmatch('[a-f0-9]{16}',self.revision): raise ValueError('invalid_index_revision')
        data,self.index,keywords=load_artifacts(cfg.runtime/'indexes'/self.revision,self.revision)
        if data['embedding_model']!=cfg.embedding_model: raise ValueError('embedding_model_mismatch')
        self.chunks,self.papers=data['chunks'],data['papers']
        self.embedding,self.cross=local_models(cfg)
        self.reranker_identity={'model':cfg.reranker_model,'revision':getattr(self.cross.model.config,'_commit_hash',None),
                               'weights_sha256':weights_checksum(self.cross.model)}
        if data['model_identity']!=model_identity(self.embedding): raise ValueError('embedding_revision_mismatch')
        self.bm25=BM25Okapi(keywords)

    def search(self,question,query=None,setting='R2',diagnostics=None):
        if setting not in ('R1','R2','R3'): raise ValueError('invalid_retrieval_setting')
        query=query or question
        if not tokens(query): return []
        if setting!='R1' and len(self.embedding.tokenizer.encode(query,truncation=False))>self.embedding.max_seq_length:
            raise ValueError('query_input_too_long')
        start=time.perf_counter(); count=min(12,len(self.chunks))
        lexical_scores=self.bm25.get_scores(tokens(query))
        lexical=sorted(range(len(self.chunks)),key=lambda i:(-lexical_scores[i],i))[:count]
        lexical_ms=(time.perf_counter()-start)*1000
        vector_ids=[]; scores={}; rerank_scores={}; vector_ms=0; rerank_ms=0
        if setting=='R1': candidates=lexical; chosen=lexical[:4]
        else:
            tick=time.perf_counter()
            vector=self.embedding.encode([query],normalize_embeddings=True)
            _,ids=self.index.search(np.asarray(vector,dtype='float32'),count)
            vector_ids=[i for i in ids[0].tolist() if 0<=i<len(self.chunks)]
            vector_ms=(time.perf_counter()-tick)*1000
            candidates,scores=fuse([lexical,vector_ids])
            pairs=[(question,self.chunks[i]['text']) for i in candidates]
            cap=self.cross.max_length or self.cross.tokenizer.model_max_length
            if any(len(self.cross.tokenizer.encode(q,t,truncation=False))>cap for q,t in pairs):
                raise ValueError('reranker_input_too_long')
            tick=time.perf_counter(); values=np.asarray(self.cross.predict(pairs)).reshape(-1)
            if len(values)!=len(candidates) or not np.isfinite(values).all(): raise ValueError('invalid_reranker_scores')
            rerank_scores=dict(zip(candidates,map(float,values)))
            chosen=sorted(candidates,key=lambda i:(-rerank_scores[i],i))[:5 if setting=='R2' else 6]
            rerank_ms=(time.perf_counter()-tick)*1000
        detail={'setting':setting,'index_revision':self.revision,'bm25_ms':lexical_ms,'vector_ms':vector_ms,
                'reranker_identity':getattr(self,'reranker_identity',None),
                'rerank_ms':rerank_ms,'total_ms':(time.perf_counter()-start)*1000,
                'candidates':[{'chunk_id':self.chunks[i]['id'],'bm25_rank':lexical.index(i)+1 if i in lexical else None,
                    'vector_rank':vector_ids.index(i)+1 if i in vector_ids else None,'rrf_score':scores.get(i),
                    'rerank_score':rerank_scores.get(i),'selected':i in chosen} for i in candidates]}
        if diagnostics is not None: diagnostics.update(detail)
        log=current()
        if log: log.emit('retrieval_ranked',**detail)
        return [self.chunks[i] for i in chosen]
