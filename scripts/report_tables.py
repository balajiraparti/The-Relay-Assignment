"""Recompute submission tables from the exact-column CSV, without filling gaps."""
import csv,json
from datetime import datetime
from relay.config import ROOT
from relay.experiments import percentile,write_json

base=ROOT/'evidence/2026-11-13'
with (base/'results.csv').open(encoding='utf-8',newline='') as stream: rows=list(csv.DictReader(stream))
def number(value): return float(value) if value not in ('',None) else None
def fmt(value): return 'not measured' if value is None else f'{value:.1f}'
def pct(values,key): return [percentile([number(r[key]) for r in values if number(r[key]) is not None],p) for p in (.5,.95,.99)]
def triplet(values): return ' / '.join(fmt(v) for v in values) if values[0] is not None else 'not measured'
def delivered(group):
    return sum(r['answer_grade'] in ('correct','wrong') if r['source']=='real' else r['status']=='ok' for r in group)
def usage(group):
    count=delivered(group)
    complete=all(r['tokens_in']!='' and r['tokens_out']!='' for r in group)
    tin=sum(number(r['tokens_in']) or 0 for r in group); tout=sum(number(r['tokens_out']) or 0 for r in group)
    return ((tin+tout)/count if count and complete else None,
            (tin*.15+tout*.60)/1000/count if count and complete and group[0]['source']=='real' else None)

latency=[]; outcomes=[]; population=[]
order={'steady':0,'burst':1,'sustained_overload':2,'per_minute_limit_halved':3,'daily_budget_exhausted':4}
for source,scenario in sorted({(r['source'],r['scenario']) for r in rows},key=lambda pair:(pair[0],order.get(pair[1],5),pair[1])):
    group=[r for r in rows if (r['source'],r['scenario'])==(source,scenario)]
    starts=[datetime.fromisoformat(r['start_time']).timestamp() for r in group]
    duration=max(start+(number(r['total_ms']) or 0)/1000 for start,r in zip(starts,group))-min(starts)
    span=max(starts)-min(starts); rate=60*(len(group)-1)/span if span else None
    latency.append([scenario,source,str(len(group)),fmt(duration),fmt(rate),triplet(pct(group,'first_token_ms')),triplet(pct(group,'total_ms'))])
    tokens,cost=usage(group)
    outcomes.append([scenario,source,*[fmt(100*sum(r['status']==status for r in group)/len(group)) for status in ('ok','rate_limited','timeout')],
        fmt(sum(int(r['retries'] or 0) for r in group)/len(group)),'not measured',fmt(tokens),fmt(cost)])
    population.append({'scenario':scenario,'source':source,'n':len(group),'first_token_n':sum(r['first_token_ms']!='' for r in group),
        'errors':sum(r['status']=='error' for r in group),'graded':sum(bool(r['answer_grade']) for r in group)})
quality=[]
for setting,pieces,rerank in [('R1',4,'no'),('R2',5,'yes'),('R3',6,'yes')]:
    group=[r for r in rows if r['source']=='real' and r['retrieval_setting']==setting]
    if not group: continue
    tokens,_=usage(group)
    quality.append([f'{setting}: 200 tokens, {pieces}, {rerank}',str(len(group)),
        *[fmt(100*sum(r['answer_grade']==grade for r in group)/len(group)) for grade in ('correct','wrong','refused_correctly')],
        fmt(tokens),' / '.join(fmt(v) for v in pct(group,'first_token_ms')[:2]),' / '.join(fmt(v) for v in pct(group,'total_ms')[:2])])
tables={'table1':[
    ['Requests/minute','30','Official free-tier documentation','medium'],
    ['Tokens/minute','8000','Documentation + response header','high'],
    ['Requests/day','1000','Documentation + response header','high'],
    ['Tokens/day','200000','Official free-tier documentation','medium'],
    ['Requests in flight','not measured','Local cap is not provider capacity','low'],
    ['Limit response','not measured','Local refusals are not upstream 429','low'],
    ['Recovery time','not measured','No upstream limit/recovery observation','low']],
    'table2a':latency,'table2b':outcomes,'table3':quality,'populations':population,
    'method':'Linear interpolation (n-1)*p. Total includes all outcomes; first_token only observed released answers. Offered rate is empirical arrival rate (n-1)/arrival span, not intended schedule. Duration includes final drain.',
    'limitations':'Queue cannot be derived from the required CSV columns: table reports not measured; sampled queue proxies are separately in manifests. Stand-in quality is not evaluated. Empty grades on capacity failures are not refusals. Assistant-reviewed real grades need author verification.'}
write_json(base/'tables.json',tables)
lines=['# Recomputed results tables','',tables['method'],'',tables['limitations'],'']
headers={
    'table1':['Limit','Value','Method','Confidence'],
    'table2a':['Scenario','Source','N','Duration s','Offered/min','First p50/p95/p99 ms','Total p50/p95/p99 ms'],
    'table2b':['Scenario','Source','Succeeded %','Rate-limited %','Timeout %','Retries/request','Peak queue','Tokens/answer','USD/1000 answers'],
    'table3':['Setting','Questions','Correct cited %','Wrong %','Correct refusal %','Tokens/answer','First p50/p95 ms','Total p50/p95 ms']}
for key,header in headers.items():
    lines.extend(['## '+key,'','| '+' | '.join(header)+' |','| '+' | '.join(['---']*len(header))+' |'])
    lines.extend('| '+' | '.join(row)+' |' for row in tables[key]); lines.append('')
(base/'TABLES.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
print('Tables regenerated from',len(rows),'CSV rows')
