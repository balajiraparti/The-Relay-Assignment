# The Relay — first runnable version

Local Streamlit interface + FastAPI backend. No sign-in. Uses the three PDFs in `data/`, page-preserving recursive token-counted splitting, BM25 + FAISS reciprocal-rank fusion, local cross-encoder reranking, and GPT-OSS 120B through a shared gateway. No corrective generation loop.

## Setup (PowerShell)

```powershell
uv venv .venv --python 3.11
uv pip install --python .venv/Scripts/python.exe -e '.[dev]'
.venv/Scripts/python.exe -m relay.cli check
.venv/Scripts/python.exe -m relay.cli migrate
.venv/Scripts/python.exe -m relay.cli ingest
```

Use the existing `.env`, or copy `.env.example` manually and supply your key. Do not share or commit it. The check command prints only key presence. First ingestion downloads local model weights, verifies exact arXiv version markers and records file checksums. Failed verification stops ingestion. Models/indexes are cached under the project.

## Run

Terminal 1:

```powershell
.venv/Scripts/python.exe -m uvicorn relay.api:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
.venv/Scripts/python.exe -m streamlit run ui/app.py --server.address 127.0.0.1 --server.port 8501
```

Open http://127.0.0.1:8501. API explorer: http://127.0.0.1:8000/docs. Keep both services local. API starts with unavailable readiness if ingestion/model loading failed; complete ingestion then restart it.

Try: "How does Moshi support simultaneous listening and speaking?" Inspect the actual cited excerpts. A valid citation identifier does not establish semantic correctness; manual grading remains required.

## Safe small measurements

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

The detailed design documents remain the target; this first slice is not their full implementation. Current simplifications:

- Numbered transactional SQLite migrations use the standard library (see DATABASE_DESIGN.md). The existing database upgrades to schema 2 with a verified backup. Full corpus/evaluation schemas remain pending.
- Correlated, redacted telemetry now uses a bounded background JSONL writer under `runtime/logs/`, with unique per-process run files, rotation, explicit failures and graceful flush. SQLite diagnostic export remains available; durable outbox delivery, complete module instrumentation and retention are later milestones.
- Conservative rolling 60-second/24-hour reservations, using a UTF-8 byte bound for input tokens; no account-reset reconciliation or separate ITPM/OTPM yet.
- At most ten active request tasks, two simultaneous provider calls, 45-second overall timeout. Fine-grained eight-second queue waiting enforcement is still pending.
- All initial retrieval settings share the 200-token recursive index (30 target overlap) to fit the small embedding model; R1 is BM25 top 4, R2 hybrid/rerank top 5, R3 hybrid/rerank top 6. The proposed 500/700-token index variants are not implemented.
- Preparation is heuristic: vague referent templates clarify; long questions can make one rewrite call. Full semantic intent-preservation checks and multi-query decomposition remain pending.
- Citation validation checks allowed IDs and paragraph coverage; it cannot prove entailment or sentence-level grounding.
- Polling request API and Streamlit work first. SSE replay, signed cursors, exhaustive endpoint catalogue, retention, full experiment runner and submission tables remain pending.

See PROJECT_STATUS.md for executed checks, measurements and the next incremental task. No UI metric should be reported as provider speed, and no fixture test should be reported as a real-service result.
