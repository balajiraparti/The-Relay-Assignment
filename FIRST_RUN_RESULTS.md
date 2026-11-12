# First runnable baseline — 12 November 2026

Development observations, not the final assignment benchmark. No measured improvement or tail-latency claim is made.

## Corpus and pipeline

The three required PDF versions produced 600 page-preserving recursive chunks across 120 pages. RecursiveCharacterTextSplitter uses the embedding tokenizer as its length function: 200-token size and 30-token target overlap, fitting MiniLM's 256-token input window. BM25 and normalized FAISS results are fused, then a local cross encoder reranks candidates. R2 supplies up to five passages to Groq openai/gpt-oss-120b.

## Real service observations

Raw evidence: `runtime/probes/20261112T135123Z/observations.json`. Same short generic citation prompt; 22 seconds between calls. Timings include client/network overhead; first content is provider content, not UI delivery.

| Probe | First content (ms) | Total (ms) | Input tokens | Completion tokens | Outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 15954.2 | 15999.5 | 82 | 28 | Success |
| 2 | 776.0 | 790.2 | 82 | 29 | Success |
| 3 | 791.1 | 829.6 | 82 | 37 | Success |

Headers advertised request-limit 1000 and token-limit 8000, corroborating configured daily-request and minute-token budgets, not establishing saturation thresholds experimentally. RPM, daily tokens, concurrency capacity and 429 recovery remain unmeasured. The slow first request has no established cause. Three samples cannot support useful p95/p99 claims.

One subsequent R2 question, “How does Moshi support simultaneous listening and speaking?”, returned an answer citing PDF pages 6 and 17. Request `965358f5-dfd4-42ff-8238-8b7c3bc8a8c0`: pipeline 1992.0 ms, provider first-content 999.3 ms, input 1214 tokens, completion 148 tokens. Models were loaded; this excludes startup and UI delivery. Evidence is in SQLite and `runtime/last_answer.json` (overwritten by the next CLI ask). Manual inspection found the core explanation supported; this is not a graded dataset. Two earlier paper runs rejected valid IDs using Unicode brackets. The gate now normalizes only that exact bracket syntax, still rejecting unknown IDs.

## Initial calibration

`runtime/calibration.json` contains paired first-delay and remaining-duration samples from the probes. Set `$env:STANDIN_CALIBRATION='runtime/calibration.json'` before starting the stand-in. Latency samples are empirical; error probabilities, quotas, worker count and overload behaviour remain synthetic settings. Fixture content, approximate token accounting and in-memory rolling quotas do not reproduce model reasoning, answer quality, exact provider resets/scheduling or token-dependent throughput. Never combine synthetic and real results.

## Checks and next steps

13 automated tests passed: validation, replay, budget reservations, citation checks, synthetic streaming, 429 and midstream failure. API and UI health returned 200. Streamlit AppTest rendered the form and submitted a clarification question without exceptions; no full browser/visual test is claimed.

UI progress uses polling and answers are buffered until citation-format checks pass. Internal provider streaming works; public SSE/replay remains pending. Citation checks cannot prove semantic grounding or guarantee zero hallucinations.

Next freeze a small question set across all papers, comparison questions, ambiguity and unsupported requests. Manually label expected evidence before running it. Compare R1/R2/R3 with identical questions and index revisions, retaining failures and recording citations, quality, latency, usage and source separately. Then exercise concurrency and faults against the stand-in and recalibrate from additional modest real calls. Do not vary chunking and retrieval together. Full experiment CSV aggregation and the final submission report remain pending.
