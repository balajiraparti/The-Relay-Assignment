import hashlib
import json
import os
import re
from pathlib import Path
import numpy as np
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi
from relay.config import ROOT

PAPERS = {'1706.03762':7, '2410.00037':1, '2507.07955':2}


def tokens(text):
    return re.findall(r'\w+', text.lower())


def local_models(cfg, rerank=True):
    os.environ.setdefault('HF_HOME', str(ROOT / '.cache' / 'huggingface'))
    from sentence_transformers import SentenceTransformer, CrossEncoder
    emb = SentenceTransformer(cfg.embedding_model, device='cpu')
    cross = CrossEncoder(cfg.reranker_model, device='cpu') if rerank else None
    return emb, cross


def ingest(cfg, chunk_size=200, overlap=30):
    """Page-wise recursive splitting; tokenizer cap prevents embedding truncation."""
    model, _ = local_models(cfg, False)
    size = min(chunk_size, model.max_seq_length-16)
    if not 0 <= overlap < size:
        raise ValueError('invalid_overlap')
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size, chunk_overlap=overlap,
        length_function=lambda s: len(model.tokenizer.encode(s, add_special_tokens=False)),
        separators=['\n\n','\n',' ',''], add_start_index=True)
    chunks, manifest, seen = [], [], set()
    for path in sorted((ROOT/'data').glob('*.pdf')):
        reader = PdfReader(path)
        pages = [p.extract_text() or '' for p in reader.pages]
        compact = re.sub(r'\s+', '', '\n'.join(pages[:2]))
        found = [(pid,v) for pid,v in PAPERS.items() if f'{pid}v{v}' in compact]
        if len(found) != 1:
            raise ValueError(f'Exact arXiv version could not be verified for {path.name}')
        pid, version = found[0]
        if pid in seen:
            raise ValueError('duplicate_paper')
        seen.add(pid)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.append({'paper_id':pid,'version':version,'sha256':digest,'file':path.name,'pages':len(pages)})
        for page_no,text in enumerate(pages,1):
            for doc in splitter.create_documents([text]):
                start = doc.metadata['start_index']
                cid = hashlib.sha256(f'{digest}:{page_no}:{start}:{doc.page_content}'.encode()).hexdigest()[:20]
                chunks.append({'id':cid,'paper_id':pid,'version':version,'page':page_no,
                               'offset':start,'text':doc.page_content})
    if seen != set(PAPERS):
        raise ValueError('Missing required paper')
    matrix = model.encode([c['text'] for c in chunks], normalize_embeddings=True, show_progress_bar=True)
    import faiss
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(np.asarray(matrix,dtype='float32'))
    cfg.runtime.mkdir(parents=True,exist_ok=True)
    payload = {'papers':manifest,'embedding_model':cfg.embedding_model,'chunk_size':size,'overlap':overlap,'chunks':chunks}
    revision = hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:16]
    folder = cfg.runtime/'indexes'/revision
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'manifest.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    faiss.write_index(index,str(folder/'vectors.faiss'))
    (cfg.runtime/'active.tmp').write_text(revision,encoding='utf-8')
    os.replace(cfg.runtime/'active.tmp',cfg.runtime/'active.txt')
    return {'revision':revision,'papers':manifest,'chunks':len(chunks),'chunk_size_tokens':size}


class Retriever:
    def __init__(self,cfg):
        import faiss
        self.revision = (cfg.runtime/'active.txt').read_text().strip()
        folder = cfg.runtime/'indexes'/self.revision
        data = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        self.chunks, self.papers = data['chunks'], data['papers']
        self.embedding, self.cross = local_models(cfg)
        if data['embedding_model'] != cfg.embedding_model:
            raise ValueError('embedding_model_mismatch')
        self.index = faiss.read_index(str(folder/'vectors.faiss'))
        if self.index.ntotal != len(self.chunks):
            raise ValueError('index_mapping_mismatch')
        self.bm25 = BM25Okapi([tokens(c['text']) for c in self.chunks])

    def search(self,question,query=None,setting='R2'):
        query = query or question
        count = min(12,len(self.chunks))
        lexical = np.argsort(self.bm25.get_scores(tokens(query)))[::-1][:count].tolist()
        if setting == 'R1':
            chosen = lexical[:4]
        else:
            vector = self.embedding.encode([query],normalize_embeddings=True)
            _, ids = self.index.search(np.asarray(vector,dtype='float32'),count)
            scores = {}
            for ranking in [lexical,ids[0].tolist()]:
                for rank,i in enumerate(ranking,1):
                    if i >= 0: scores[i] = scores.get(i,0)+1/(60+rank)
            candidates = sorted(scores,key=scores.get,reverse=True)[:16]
            pairs = [(question,self.chunks[i]['text']) for i in candidates]
            # Refuse silent pair truncation, including long original questions.
            if any(len(self.cross.tokenizer.encode(q,t)) > self.cross.max_length for q,t in pairs):
                raise ValueError('reranker_input_too_long')
            values = self.cross.predict(pairs)
            chosen = [i for _,i in sorted(zip(values,candidates),reverse=True)][:5 if setting=='R2' else 6]
        return [self.chunks[i] for i in chosen]
