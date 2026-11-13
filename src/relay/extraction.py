"""Audit immutable inputs and retain exact extracted pages before chunking."""
import hashlib
import json
import re
from pathlib import Path
from pypdf import PdfReader
from relay.telemetry import current

PAPERS = {'1706.03762': 7, '2410.00037': 1, '2507.07955': 2}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_audit(audit,runtime):
    raw=canonical(audit); revision=hashlib.sha256(raw).hexdigest()
    folder=Path(runtime)/'corpus'; folder.mkdir(parents=True,exist_ok=True)
    path=folder/(revision+'.json')
    if path.exists():
        if path.read_bytes()!=raw: raise ValueError('corpus_audit_corrupted')
    else:
        with path.open('xb') as stream: stream.write(raw)
    return path


def extract(data_dir, expected=None):
    data_dir=Path(data_dir)
    expected=expected if expected is not None else json.loads((data_dir/'corpus.lock.json').read_text())
    papers=[]; pages=[]; seen=set()
    log=current()
    if log: log.emit('extraction_started',paper_count=len(expected))
    paths=sorted(data_dir.glob('*.pdf'))
    if {p.name for p in paths} != set(expected): raise ValueError('corpus_file_set_mismatch')
    for path in paths:
        digest=checksum(path)
        if digest != expected[path.name]['sha256']: raise ValueError('corpus_checksum_mismatch: '+path.name)
        reader=PdfReader(path)
        if reader.is_encrypted: raise ValueError('encrypted_pdf: '+path.name)
        texts=[page.extract_text() or '' for page in reader.pages]
        compact=re.sub(r'\s+','', '\n'.join(texts[:2]))
        markers=set(re.findall(r'(\d{4}\.\d{4,5})v(\d+)',compact))
        found=[(pid, int(v)) for pid,v in markers if pid in PAPERS]
        wanted=expected[path.name]
        if found != [(wanted['paper_id'],wanted['version'])] or PAPERS.get(wanted['paper_id']) != wanted['version']:
            raise ValueError('paper_version_mismatch: '+path.name)
        pid=wanted['paper_id']
        if pid in seen: raise ValueError('duplicate_paper')
        seen.add(pid)
        if not texts or not any(t.strip() for t in texts): raise ValueError('empty_pdf: '+path.name)
        paper={'paper_id':pid,'version':wanted['version'],'sha256':digest,'file':path.name,'pages':len(texts)}
        papers.append(paper)
        for number,text in enumerate(texts,1):
            warnings=[]
            if not text.strip(): warnings.append('empty_page_no_ocr')
            elif len(text.strip())<40: warnings.append('sparse_page')
            if '\ufffd' in text or '\x00' in text: warnings.append('suspicious_characters')
            pages.append({'paper_id':pid,'version':wanted['version'],'page':number,'text':text,
                          'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'warnings':warnings})
        if log: log.emit('paper_extracted',paper_id=pid,pages=len(texts),checksum=digest,
                         warnings=sum(len(p['warnings']) for p in pages if p['paper_id']==pid))
    if seen != set(PAPERS): raise ValueError('missing_required_paper')
    return {'schema_version':1,'papers':papers,'pages':pages,
            'limitations':['No OCR or table/equation reconstruction; reading order requires manual review.']}
