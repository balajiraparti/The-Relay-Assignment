"""Render the two-page report from recomputed tables, with explicit author-review gaps."""
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab import rl_config
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak

ROOT=Path(__file__).resolve().parents[1]; base=ROOT/'evidence/2026-11-13'
rl_config.invariant=1
tables=json.loads((base/'tables.json').read_text(encoding='utf-8'))
output=ROOT/'output/pdf'; output.mkdir(parents=True,exist_ok=True)
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyCompact',fontName='Helvetica',fontSize=8,leading=9.3,spaceAfter=3))
styles.add(ParagraphStyle(name='HeadingCompact',fontName='Helvetica-Bold',fontSize=9.1,leading=10.5,spaceBefore=5,spaceAfter=2))
styles.add(ParagraphStyle(name='CellCompact',fontName='Helvetica',fontSize=6.2,leading=7.1))
story=[]
def para(text): story.append(Paragraph(text,styles['BodyCompact']))
def heading(text): story.append(Paragraph(escape(text),styles['HeadingCompact']))
def table(header,rows,widths):
    data=[[Paragraph(escape(str(v)).replace('not measured','not<br/>measured'),styles['CellCompact']) for v in row] for row in [header,*rows]]
    value=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    value.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eef4')),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('GRID',(0,0),(-1,-1),.3,colors.HexColor('#b5c1cc')),('LEFTPADDING',(0,0),(-1,-1),3),
        ('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
    story.append(value); story.append(Spacer(1,3))

story.append(Paragraph('The Relay Assignment',styles['Title']))
para('<b>Measured prototype / author-review draft.</b> Source, raw CSV, grades, event traces and verbatim prompt snapshot accompany this report. Provisional evidence grades were reviewed by the assistant, not independently hand-verified by the author.')
heading('1. What I built and why')
para('A local Streamlit/FastAPI assistant prepares a query, retrieves/reranks paper passages, generates once with Groq GPT-OSS 120B, then releases a cited answer or refuses. Recursive chunks retain exact PDF pages and offsets. The shaping decision is to buffer the candidate for citation checks: users see progress early, but answer content arrives near completion. Citation syntax cannot prove entailment. No sign-in or corrective generation loop.')
heading('2. The real service and my stand-in')
para('Table 1 separates published limits from observed headers; local budget refusals are not provider HTTP 429s. Groq documentation: console.groq.com/docs/rate-limits (checked November 13). The stand-in replays paired first-content/tail delays from the original tiny generic probe and adds explicit queues, faults and quotas. Its load multiplier and failure probability are assumptions; it cannot reproduce shared tenancy, real model quality or hidden provider scheduling. Larger paper-sized observations are exported separately, not pooled into the bootstrap calibration.')
table(['Table 1: limit','Value','How found','Confidence'],tables['table1'],[115,64,267,65])
heading('3. Results')
para('Tables 2a/2b include every offered arrival, including failures. Percentiles use linear interpolation; small-sample p99 is descriptive, not a service guarantee. First-token latency is the runner observing committed validated answer content, not provider TTFT or browser receipt. Succeeded means completed execution, including refusals. Duration includes drain; offered/min is observed inter-arrival rate. Empty usage remains unknown. Synthetic runs use fixed retrieval evidence and therefore isolate gateway/provider capacity, not real retrieval throughput.')
main_a=[]
for row in tables['table2a']:
    if row[0].startswith('retry_'): continue
    population=next(p for p in tables['populations'] if (p['scenario'],p['source'])==(row[0],row[1]))
    main_a.append([*row[:2],row[2]+'/'+str(population['first_token_n']),*row[3:]])
main_b=[r for r in tables['table2b'] if not r[0].startswith('retry_')]
table(['Table 2a scenario','Source','N / TTFT n','Duration s','Offered/min','First p50/95/99 ms','Total p50/95/99 ms'],main_a,[85,39,28,41,49,134,135])
table(['Table 2b scenario','OK %','Limit %','Timeout %','Retries/req','Peak queue','Tokens/answer','USD/1000'],[[r[0]+' ('+r[1]+')',*r[2:]] for r in main_b],[115,37,38,43,48,63,84,83])
heading('4. Where the time goes')
para('The slowest answered real request is decomposed below using its recorded same-process durations. Working includes retrieval and model/network time; the residual includes validation, storage and observer overhead. Almost all time elapsed before validated content. Provider queueing versus network delay cannot be separated. Request ID and raw events: evidence/TRACE.md.')
trace=json.loads((base/'trace.json').read_text())
table(['Trace: retrieval','Gateway wait','Model/network','Retry','Residual','Verified first','Total ms'],
    [[f'{trace[k]:.1f}' for k in ('retrieval_work_ms','gateway_wait_ms','model_network_and_work_ms','retry_ms','validation_storage_and_observer_overhead_ms','validated_first_token_ms','total_ms')]],
    [73]*7)
heading('5. When a limit is hit')
para('The gateway reserves a conservative UTF-8-byte input bound plus completion budget before dispatch. It bounds concurrency, queued work and wait time, and persists upstream cooldowns. Near quota, optional refinement is skipped under load; no uncited weaker answer or synthetic fallback is substituted. Daily exhaustion produces a capacity outcome. Actual provider reset/recovery remains unmeasured. Peak queue is not derivable from the required CSV, so the table reports not measured; sampled queue proxies are in manifests.')

story.append(PageBreak())
heading('Retrieval: quality versus cost')
para('All settings hold the page-preserving recursive index at 200 embedding tokens with 30 overlap. R1 uses BM25; R2/R3 use dense + BM25 fusion and a cross-encoder. Table 3 compares different fetched-piece counts, not different chunk sizes. Keep R2 provisionally: the larger R3 context encountered local token-budget refusals. This paced shared-budget experiment is operational evidence, not an isolated statistical quality ranking. Capacity failures remain ungraded; valid citations can still support a wrong claim.')
table(['Table 3 setting','N','Correct cited %','Wrong %','Correct refusal %','Tokens/answer','First p50/95 ms','Total p50/95 ms'],tables['table3'],[112,20,43,35,49,65,93,94])
heading('How this library will mislead a naive retriever')
para('<b>Term collision:</b> “Does dynamic chunking improve RAG retrieval?” H-Net learns sequence boundaries, not document retrieval chunks. <b>Split evidence:</b> “Why sinusoidal position encodings?” formula and extrapolation rationale span separate chunks. <b>Incomparable tasks:</b> “Is Moshi faster than the Transformer?” speech dialogue latency and machine-translation throughput are not a common benchmark.')
heading('6. Retries')
para('Retry only transient pre-content transport/429/5xx failures, within the wait/deadline budget and a maximum of three attempts; release the concurrency slot during backoff. Never retry a partial candidate as a second answer. The controlled synthetic comparison below used identical initial-failure injection; retries improved completion but worsened tail time. An earlier random-fault comparison produced no retries and is retained locally rather than presented as causal evidence.')
retry_a=[r for r in tables['table2a'] if r[0].startswith('retry_')]
retry_b=[r for r in tables['table2b'] if r[0].startswith('retry_')]
table(['Policy','N','Total p50/95/99 ms','OK %','Retries/request'],[[a[0].replace('retry_comparison_',''),a[2],a[6],b[2],b[5]] for a,b in zip(retry_a,retry_b)],[116,25,205,65,100])
heading('7. What the person sees')
para('At daily exhaustion the UI shows a capacity failure, retains the request in shared local history, and does not invent an answer or reset time. A new attempt is explicit. Cancel stops local work; it cannot guarantee that already dispatched provider work is unbilled. History pagination, source excerpts and run downloads remain usable without sign-in.')
heading("8. What I'm unsure about, what I left out, what I learned")
para('The least certain assumption is that the tiny bootstrap latency sample resembles paper-sized calls; if false, simulated overload timings are misleading. Public deployment and semantic chunking were deliberately omitted. The useful systems lesson is that adding concurrency does not add token capacity: a conservative admission bound may reject work even when observed token usage is lower. A citation checker also cannot detect a reversed causal direction. These are prototype findings, not a zero-hallucination guarantee.')
heading('Your feedback on Vaani')
para('The author explicitly deferred website feedback until results, tables and experiments were complete. This section awaits the author\'s own view of what stood out, what confused them and one change they would make. It has not been replaced with the assistant\'s opinion. Website: https://www.vaani.dev/.')
heading('How I worked with the assistant')
para('<b>Author-review draft, based on the actual prompt record.</b> Three prompts drove the work. First, asking for modular features and a project tracker constrained implementation to reviewable increments and prevented a design document from counting as a live integration. Second, asking to measure Groq before calibrating the stand-in made the simulator depend on observations rather than invented latency. Third, asking for structured event logging made source, timing, tokens and failures inspectable across the pipeline. The supplied prompt snapshot preserves the available user messages verbatim; it is not a cleaned-up reconstruction of the conversation.')
para('The author overruled the proposed corrective RAG loop and removed sign-in, chose a Streamlit interface, selected Groq GPT-OSS 120B, and chose recursive splitting before semantic-chunking experiments. Those decisions are distinctly the author\'s. The author also explicitly caught the unwanted sign-in option in the proposed flow and asked for its removal. During verification, the assistant found that its first random retry comparison had produced no retries, so it retained that trial and ran an explicit failure-injection comparison. Another observed failure was an answer whose citation syntax passed but whose attention-flow direction was reversed; the provisional grade counts it wrong. The author must verify the grades and this reflection rather than submit an invented personal account of checks they did not perform.')

def footer(canvas,doc):
    canvas.setFont('Helvetica',7); canvas.setFillColor(colors.HexColor('#526273'))
    canvas.drawString(42,24,'The Relay | measured prototype | author review required')
    canvas.drawRightString(A4[0]-42,24,str(doc.page))
doc=SimpleDocTemplate(str(output/'The_Relay_Assignment_Report.pdf'),pagesize=A4,
    leftMargin=42,rightMargin=42,topMargin=28,bottomMargin=35)
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(output/'The_Relay_Assignment_Report.pdf')
