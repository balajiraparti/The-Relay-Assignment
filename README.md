# The Relay — first runnable version

Local Streamlit interface + FastAPI backend. No sign-in. Uses the three PDFs in `data/`, page-preserving recursive token-counted splitting, BM25 + FAISS reciprocal-rank fusion, local cross-encoder reranking, and GPT-OSS 120B through a shared gateway. No corrective generation loop.

## Setup (PowerShell)

```powershell
uv venv .venv --python 3.11
uv pip install --python .venv/Scripts/python.exe -e '.[dev]'
.venv/Scripts/python.exe -m relay.cli check
.venv/Scripts/python.exe -m relay.cli migrate
.venv/Scripts/python.exe -m relay.cli audit
.venv/Scripts/python.exe -m relay.cli ingest
```

Use the existing `.env`, or copy `.env.example` manually and supply your key. Do not share or commit it. The check command prints only key presence. First ingestion downloads local model weights, verifies exact arXiv version markers and records file checksums. Failed verification stops ingestion. Models/indexes are cached under the project.

## Run

Terminal 1:

```powershell
.venv/Scripts/python.exe -m relay.cli serve
```

Terminal 2:

```powershell
.venv/Scripts/python.exe -m streamlit run ui/app.py --server.address 127.0.0.1 --server.port 8501
```

Open http://127.0.0.1:8501. API explorer: http://127.0.0.1:8000/docs. Keep both services local. API starts with unavailable readiness if ingestion/model loading failed; complete ingestion then restart it.

Try: "How does Moshi support simultaneous listening and speaking?" Inspect the actual cited excerpts. A valid citation identifier does not establish semantic correctness; manual grading remains required.

## Safe small measurements

See docs/REAL_SERVICE_READINESS.md before a larger measurement run. The logger and live Groq path are verified, but the existing 1–5-call probe is not a percentile/recovery runner. Probe measurement version 2 disables retries, explicitly records upstream HTTP status and distinguishes local rejection from provider status. N=1 or N=3 cannot establish useful tail percentiles. Further stand-in calibration should follow a separately recorded real experiment.

```powershell
.venv/Scripts/python.exe -m relay.cli probe --count 3
.venv/Scripts/python.exe -m relay.cli export-events
.venv/Scripts/python.exe -m pytest -q
```

Probe accepts 1–5 requests, spaces them by 22 seconds, and stops on failure. It records provider content TTFT (not UI TTFT), total call time, usage and allowlisted headers under `runtime/probes/`. It does not intentionally force 429s or deplete daily quota. The prompt is a small generic calibration prompt, not a paper-answer quality benchmark. No answer quality can be inferred from it. Configuration limits remain provisional until corroborated by account observations.

## Synthetic backend

Start the stand-in in another terminal:

```powershell
.venv/Scripts/python.exe -m uvicorn relay.standin:app --host 127.0.0.1 --port 8001
```

Then start the main backend with `$env:RELAY_BACKEND='stand-in'`. Reset this environment variable or set it to `groq` before real runs. Supported initial stand-in controls: STANDIN_WORKERS, STANDIN_RPM, STANDIN_FIRST_DELAY, STANDIN_CHUNK_DELAY, STANDIN_FAILURE_RATE, STANDIN_SEED. Defaults are synthetic assumptions; the stand-in returns explicit fixture content and cannot answer research questions. Never treat its outputs as Groq quality measurements.

## v0.1 boundaries

F04–F08 are now verified. Source checksums are pinned by data/corpus.lock.json. Full extracted pages and warnings live in runtime/corpus; immutable index artifacts contain checksummed pages, keyword tokens and FAISS vectors. Exact chunk offsets, tokenizer limits and loaded model-weight hashes are checked before publication/readiness. Old revisions remain. Rebuild legacy indexes with `ingest`; runtime/active.txt records the selected revision. `scripts/verify_index_build.py` checks two identical builds, and `scripts/verify_retrieval.py` performs nine offline expected-paper checks, not a quality benchmark.

Additional stand-in controls: STANDIN_QUEUE_LIMIT, STANDIN_TPM/RPD/TPD, STANDIN_LOAD_FACTOR, STANDIN_FAIL_FIRST_REQUESTS and STANDIN_FAIL_AFTER_CHUNKS. Set STANDIN_CALIBRATION to a measured profile JSON path to use paired delay samples. The seed and request ID select repeatable faults; fail-first injection depends on arrival order. Restart to change profiles. Windows timer granularity can coalesce very short chunk delays.

`tests/test_gateway_http.py` starts isolated HTTP/SSE servers and checks streaming, failures, cooldown persistence, deadlines/cancellation, queues and retry-slot release. It never calls Groq. The assignment's custom stand-in requires no Postman install; evidence boundaries are in docs/standin.context.yaml.

The detailed design documents remain the target; this first slice is not their full implementation. Current simplifications:

- Numbered transactional SQLite migrations use the standard library. Schema 3 adds persistent provider cooldowns, with verified upgrade backups. Corpus metadata is stored in immutable audit/index files; relational corpus materialization and evaluation schemas remain pending.
- Correlated, redacted telemetry now uses a bounded background JSONL writer under `runtime/logs/`, with unique per-process run files, rotation, explicit failures and graceful flush. SQLite diagnostic export remains available; durable outbox delivery, complete module instrumentation and retention are later milestones.
- Conservative rolling 60-second/24-hour reservations, using a UTF-8 byte bound for input tokens; no account-reset reconciliation or separate ITPM/OTPM yet.
- At most ten active API tasks. The gateway defaults to two simultaneous calls, ten queued calls, an eight-second cumulative slot/backoff wait budget per logical call, and a 45-second call deadline. The pipeline also has a 45-second overall deadline. End-to-end dispatcher fairness and separate user queue timing remain later API/load work.
- All initial retrieval settings share the 200-token recursive index (30 target overlap) to fit the small embedding model; R1 is BM25 top 4, R2 hybrid/rerank top 5, R3 hybrid/rerank top 6. The proposed 500/700-token index variants are not implemented.
- Preparation routes clear/off/busy queries without an LLM, clarifies known missing-referent patterns, and permits one optional five-second JSON rewrite. Only courtesy-prefix removal preserving substantive tokens/order is accepted; unsafe, malformed or failed rewrites use the original. General paraphrase equivalence and multi-query decomposition are not implemented.
- Citation validation checks allowed IDs and sentence coverage. Malformed/unsupported answers refuse without regeneration. This is not semantic entailment: docs/F09_F12_VERIFICATION.md records an observed overbroad novelty claim despite valid citations.
- Polling request API and Streamlit work first. SSE replay, signed cursors, exhaustive endpoint catalogue, retention, full experiment runner and submission tables remain pending.

See PROJECT_STATUS.md for executed checks, measurements and the next incremental task. No UI metric should be reported as provider speed, and no fixture test should be reported as a real-service result.

F09–F12 are verified: provider JSON mode, measured calibration with source hashes, conservative preparation, one-pass release/refusal, aggregate attempt usage and local access/readiness. See docs/GROQ_LIMITS.md for published versus observed quotas. Unknown usage makes request totals null while preserving known subtotals. The supported launcher binds loopback and disables proxy-header trust. Readiness checks configuration/storage/models, not remote connectivity. Local history is shared; there are no sign-in endpoints. An opt-in live evaluation script, `scripts/verify_live_rag.py`, makes one provider request and stores its draft separately under runtime/evaluation; ordinary operational logs exclude drafts.
