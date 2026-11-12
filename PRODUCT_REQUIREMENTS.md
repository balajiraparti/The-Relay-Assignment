# The Relay: Product Requirements Document

**Status:** Target specification with a partial runnable v0.1; see PROJECT_STATUS.md and README.md for implementation gaps.

**v0.1 chunking decision:** RecursiveCharacterTextSplitter, measured with the embedding tokenizer, size 200 tokens and target overlap 30, split within PDF pages. This supersedes larger proposed baseline sizes for the current 256-token embedding model. No semantic chunking or corrective generation loop. First real observations are in FIRST_RUN_RESULTS.md; they are not a completed benchmark.

**F01–F03 implementation decision:** Configuration validates backend/local URL and rejects missing keys before hosted CLI calls while allowing offline tasks. Persistence uses sqlite3 repositories with numbered transactional migrations and verified upgrade backups (superseding the proposed ORM/Alembic choice). Telemetry uses standard logging QueueHandler, contextvars, redaction and a bounded writer with non-overwriting segments and explicit failure. API/CLI events write under runtime/logs with a unique process run ID; future experiments will bind these to their run manifests. Full instrumentation of later modules, durable outbox replay, retention and measured logging overhead remain with later milestones; the foundation does not establish benchmark completeness.
**Product:** A small, evidence-grounded research-paper assistant

**Primary language:** Python 3.11+ (proposed)

**Model provider:** Groq Free tier; selected model `openai/gpt-oss-120b`
**Scope:** Assignment implementation, experiment, and reproducible submission

Detailed implementation contracts: [API design](API_DESIGN.md) and [Database design](DATABASE_DESIGN.md). These specify the resumable request API, local access without sign-in, SQLite schema, indexes, transactions and UI states. They supersede the earlier endpoint sketch in this PRD.

## 1. Product summary

The Relay is a small Retrieval-Augmented Generation (RAG) service that answers questions about exactly three research papers. It uses hybrid retrieval (dense vector search plus BM25 keyword search) and a local cross-encoder reranker before a single Groq answer-generation pass. Deterministic citation checks lead to either release or refusal. There is no corrective generation loop, LLM answer evaluator, score threshold, or answer-driven query rewriting.

The project is deliberately also a systems experiment. It must demonstrate what happens when requests arrive in bursts, model calls are slow or fail, and provider request/token budgets are near or at their limits. It must record raw per-request results so all reported tables can be recomputed.

## 2. Problem and rationale

Engineers need fast answers about a small paper library. A simple "send the question to a model" approach is not acceptable because the model may answer from general knowledge, cite nonexistent evidence, or overload a constrained free API account. A robust solution needs four properties that compete with each other:

- **Groundedness:** answers only make claims supported by the supplied paper versions.
- **Responsiveness:** users receive the first answer token quickly when an answer is possible.
- **Fairness under bursts:** one surge does not let a few requests consume all capacity.
- **Responsible degradation:** when evidence or budget is unavailable, users receive an honest, useful outcome rather than a fabricated answer or an indefinite wait.

## 3. Assignment requirements (non-negotiable)

The following are requirements from the brief, not optional product choices.

1. Build a working Python, C++, or Go pipeline with **at least four steps**, **at least one tool call**, and **at least one branch or loop**.
2. Answer only from these exact paper versions:
   - *Attention Is All You Need*, arXiv:1706.03762v7
   - *Moshi: a speech-text foundation model for real-time dialogue*, arXiv:2410.00037v1
   - *Dynamic Chunking for End-to-End Hierarchical Sequence Modeling*, arXiv:2507.07955v2
3. Cite where every answer came from. If the papers do not answer a question, say so instead of guessing.
4. Use a real hosted model on Groq's free tier with the user's own account/key. Do not include the key in source control or the submission.
5. Measure the real service modestly, then create a controlled stand-in model service. The stand-in must support slowness, failure, limit refusal, increasing slowdown under load, and piece-by-piece streaming.
6. Run at least three load shapes. The required results-table scenarios are steady, burst, sustained overload, per-minute limit halved, and daily budget exhausted.
7. Retain raw results in a file named `results.csv`, one row per request, using the brief's required columns.
8. Submit no more than two pages of prose, plus code, raw results, and unedited assistant-conversation history/prompts.
9. Include the required headings and tables, evaluate answer quality on at least 15 self-authored questions, compare at least three retrieval settings, explain three naïve-retriever failure modes, and include short feedback on Vaani.

## 4. Goals and success criteria

### Goals

- Return a cited, paper-supported answer to answerable questions.
- Correctly refuse questions unsupported by the three papers.
- Stream useful output promptly after a request is admitted.
- Remain predictable under configured request/token limits and bursty input.
- Produce a complete audit trail suitable for regenerating every reported metric.
- Keep the implementation small enough to build, test, and explain before the deadline.

### Measurable acceptance criteria

| Area | Acceptance criterion |
| --- | --- |
| Grounding | Each non-refusal answer contains at least one valid passage citation; unsupported questions result in an explicit refusal. |
| Library boundary | No answer is based on a source outside the three version-locked PDFs. |
| Pipeline | A request passes through admission, hybrid retrieval, reranking, drafting, and citation validation; validation has a release-or-refuse branch. |
| Streaming | `first_token_ms` records the first emitted answer chunk, not merely HTTP connection setup. |
| Limits | The dispatcher will not intentionally send a call when its locally tracked budget lacks a request or token reservation. |
| Failure handling | 429, timeout, and network/provider errors are recorded distinctly and follow the retry policy. |
| Stand-in | Configuration can produce slow responses, errors, 429s, queueing/slowdown, and streams. |
| Reproducibility | Each results-table value is calculated from `results.csv`; scripts regenerate tables without hand entry. |
| Evaluation | At least 15 fixed questions are hand-graded using the four allowed grades. |
| Observability | Every accepted request has correlated lifecycle events and one terminal outcome; rejected arrivals, provider attempts, quota decisions, and stand-in faults are also recorded. Benchmark logs are complete or the run is marked invalid. |

### Non-goals

- Authentication, accounts, passwords, public registration and multi-tenant sharing. This assignment app runs locally without sign-in.
- General web search, chat memory, or answers about papers outside the library.
- Maximising request volume against Groq's free tier.
- Claiming benchmark results before they have actually been measured.
- A custom React frontend or public consumer application. A local Streamlit UI is part of the product scope; CLI scripts and Postman remain useful for testing.

## 5. Users and primary journeys

### Researching engineer

1. Sends a natural-language question.
2. Receives a streamed answer with paper/page/section citations, or a clear supported-evidence refusal.
3. If overloaded, sees a short status message rather than a hung request.

### Evaluator/developer

1. Runs ingestion once from the supplied PDFs.
2. Runs a small real-service probe with an API key stored in `.env`.
3. Runs deterministic load scenarios against the stand-in.
4. Produces `results.csv`, aggregated tables, and the two-page report from recorded data.

## 6. Proposed technical design

The detailed user journeys, data ownership flows, and edge-case acceptance matrix in sections 18–20 complement this architecture. API_DESIGN.md remains the exact HTTP/state contract and DATABASE_DESIGN.md remains the persistence/transaction contract.

This section makes recommended choices that can be revised after a small spike.

### 6.1 Stack

| Concern | Proposed choice | Reason |
| --- | --- | --- |
| Language/runtime | Python 3.11+ | Fastest path for async HTTP, PDF extraction, experiments, and CSV analysis. |
| Service/API | FastAPI + Uvicorn | Minimal typed local API with async streaming support. |
| User interface | Streamlit, separate local process | Question entry, progress, citations, history and operator diagnostics through FastAPI. |
| Groq client | Official `groq` Python SDK or `httpx` | Supports streamed completions; raw headers must be captured. |
| Configuration | `python-dotenv`; `.env` ignored by Git | Keeps `GROQ_API_KEY` local and out of artifacts. |
| PDF extraction | `pypdf` or `PyMuPDF` | Extracts paper text with page boundaries. |
| Vector retrieval | FAISS + local sentence-transformer embeddings | Semantic retrieval catches paraphrases and concept questions. |
| Keyword retrieval | BM25 (`rank-bm25`) | Exact technical terms, model names, symbols, and acronyms remain retrievable. |
| Fusion | Reciprocal Rank Fusion (RRF) | Combines rank lists without pretending BM25 and vector scores share a scale. |
| Reranking | Local Hugging Face cross-encoder | Scores each query/chunk pair directly; improves final ordering without using Groq quota. |
| Validation | Pydantic models + deterministic citation checker | Makes unsupported or malformed citations detectable. |
| Metrics | standard library CSV + pandas | Simple raw logging and reproducible aggregation. |
| Tests | pytest | Fast unit/integration tests. |
| Persistence | SQLite + SQLAlchemy + Alembic | One-process durable request state, quota accounting and experiment provenance. |

**Model choice (decided):** `openai/gpt-oss-120b` hosted by Groq, for both answer generation and conditional input refinement. Read the API key from local configuration. This document specifies integration; live availability, account limits, latency, and answer quality still require measurement.

### 6.1.1 Published model specifications

Official documentation checked November 12, 2026:

| Property | Published value |
| --- | --- |
| Model | GPT-OSS 120B; MoE with 120B total and 5.1B active parameters |
| Modalities | Text input/output |
| Advertised speed | Approximately 500 tokens/second; not an end-to-end latency guarantee |
| Context / maximum output | 131,072 / 65,536 tokens |
| Listed pricing per million tokens | $0.15 input; $0.075 cached input; $0.60 output |
| Capabilities | Reasoning, tool use, JSON object/schema modes, browser search, code execution |
| Hosted quantization | Groq TruePoint Numerics |

Source: [Groq model page](https://console.groq.com/docs/model/openai/gpt-oss-120b). Prices are paid-usage reference rates, not charges incurred by this Free-tier experiment. Browser search and code execution remain disabled so answers stay within the paper library. Hosted quantization is controlled by Groq.

### 6.1.2 Integration settings (proposed)

Use the Groq chat-completions API with `model="openai/gpt-oss-120b"`. Start with `reasoning_effort="low"`, and compare medium effort only if grading shows a benefit. Groq supports low/medium/high for this model; `reasoning_format` is not supported. [Groq reasoning documentation](https://console.groq.com/docs/reasoning)

Start with a 1,024-token generation completion budget and a 512-token refinement completion budget, accounting for reasoning as well as visible output. Target a concise answer of roughly 300 visible tokens. Treat these as tunable application caps, not model maxima. Reserve full prompt and completion allowances before each call; detect length-truncated outputs and return an incomplete-response outcome instead of releasing a broken answer. Do not expose reasoning text as user-visible answer content. Keep original questions and retrieved excerpts in distinct prompt fields and treat excerpts as data, not instructions.

### 6.2 Hybrid retrieval and reranking pipeline

```text
HTTP request
  -> (1) Admission, budget reservation, and library-boundary check
  -> (2) Input preparation: direct / refine / decompose / clarify
  -> (3) Hybrid retrieval: vector top-K + BM25 top-K -> RRF fusion
  -> (4) Cross-encoder rerank -> evidence pack
  -> (5) Groq grounded draft
  -> (6) Deterministic citation validation
         -> pass: release answer
         -> fail: refusal without regeneration
```

1. **Admission and budget reservation.** Validate request size, reject non-library general-chat requests, estimate input and maximum output tokens, enforce queue capacity, and reserve capacity from request and token buckets.
2. **Input preparation.** Keep clear questions unchanged. For vague wording, refine once before retrieval while preserving intent. Combine optional decomposition with the same preparation call; ask for clarification when missing information cannot safely be inferred.
3. **Hybrid retrieval tool.** Search chunks twice: dense vector search for semantic similarity and BM25 for lexical overlap. Fuse the rank lists using Reciprocal Rank Fusion (RRF), preserving paper/version/page metadata.
4. **Cross-encoder rerank.** Score each `(question, candidate chunk)` pair locally, then retain only the most relevant chunks. This measures relevance to the query; it must **not** reward chunks merely because they appear frequently in the documents.
5. **Answer generation.** Give Groq only the question, optional plan, and bounded evidence pack. Require concise claims with stable citation IDs and an explicit evidence-boundary response when support is absent.
6. **Citation validation.** Check supplied citation IDs, paper versions, and citation coverage once. Release a passing answer or return a refusal on failure. Do not call an evaluator, rewrite the query, retrieve again, or regenerate the answer. This release-or-refuse branch satisfies the assignment's branch-or-loop requirement.

This contains more than the assignment's minimum four steps. Stage 3 is the retrieval tool call; stage 6 supplies the required branch. A correction loop is unnecessary for assignment compliance. The optional initial planning route remains separate from answer validation.

### 6.3 Initial query refinement and planning

Use a lightweight local check first. Clear queries bypass the model preparation call. Vague or multi-part queries can make at most one GPT-OSS 120B preparation call, combining routing, refinement, and optional decomposition. Suggested route labels:

| Route | Trigger | Action |
| --- | --- | --- |
| `direct` | One focused factual question | Use the original question for hybrid retrieval. |
| `refine` | Intent is recoverable but wording is vague or conversational | Produce one concise search query without introducing facts or changing intent. |
| `clarify` | Missing referent, paper, or comparison target | Ask one focused clarification question and stop retrieval for this request. |
| `decompose` | Comparison, two or more sub-questions, or cross-paper relationship | Ask Groq for a short JSON retrieval plan: 1-3 subqueries and desired paper(s). Retrieve for each subquery. |
| `refuse_out_of_scope` | The question asks for facts outside the library | Explain that the assistant can answer only from the three papers. |

Return validated JSON with `route`, `retrieval_query`, `subqueries` (at most three), and `clarification_question`. Preserve the original query for generation and logs; search with the refined query, but rerank against the original intent. A rewrite must preserve entities, numbers, negation, requested paper, and constraints. It must not invent a referent or assert an answer. For example, "in Moshi, how does it do listening and speaking together?" can become "How does Moshi support simultaneous listening and speaking?"; "Why is it better?" needs clarification.

On malformed or timed-out preparation, use the original query if its intent is usable; otherwise ask for clarification. Under load, bypass optional refinement rather than consume capacity needed for answer generation. There is no post-answer query rewriting and no corrective loop. A clear request ordinarily costs one generation call; a refined request costs one preparation plus one generation call, before transport retries. Log the preparation route, original/refined query, time, and usage; include both calls in per-request tokens and latency.

### 6.4 Hybrid retrieval and reranking contract

F10 implementation clarification (November 13): the initial rewrite schema is `route` (direct/refine/clarify) plus `retrieval_query`; multi-query decomposition is deferred. Only courtesy-prefix removal that preserves substantive lexical order, numbers and negation passes the automatic guard. Original queries remain in request storage and generation/reranking, never operational logs. Missing-referent templates clarify without an LLM; clear/off/busy paths bypass it. Preparation has a five-second cap and safe original-query fallback. This supersedes broader automatic paraphrase assumptions above; arbitrary semantic equivalence is not guaranteed.

For a question `q`, retrieve `K_vector` dense candidates and `K_bm25` lexical candidates. Fuse them using:

```text
RRF(d) = sum over retrieval lists r of 1 / (rrf_k + rank_r(d))
```

Start with `K_vector = 12`, `K_bm25 = 12`, `rrf_k = 60`, and keep the fused top 16 chunks for cross-encoder scoring. The reranker returns a final evidence pack of 4-6 chunks. These values are parameters to measure, not claimed optimal values.

The LangChain integration you shared describes the same retrieve-then-rerank pattern: fetch a larger vector candidate set, then reduce it with a cross-encoder. It notes that cross-encoders score query/document pairs directly and can improve ordering at the cost of one local inference per candidate. For this project, start with a small local English model, `cross-encoder/ms-marco-MiniLM-L6-v2`, and record its device/model version in experiment metadata. Larger rerankers are optional experiments, not a prerequisite. [LangChain cross-encoder reranker guide](https://docs.langchain.com/oss/python/integrations/document_transformers/cross_encoder_reranker)

- Use a LangChain wrapper only if it reduces implementation risk. Direct `sentence-transformers`/FAISS code is acceptable and may be simpler to instrument.
- Cache document embeddings and cross-encoder scores only for exact question/chunk-ID matches; label cache behavior in measurements.
- Keep candidate counts bounded. Cross-encoders run once per candidate and can make a small RAG system slower if `K` is unbounded.
- Preserve retrieval rank, RRF score, reranker score, and selected/not-selected status in a diagnostic event log.

### 6.5 Citation format and evidence contract

Use a machine-checkable inline citation format, for example:

```text
[1706.03762v7 p.3 c.014]
```

`c.014` is the immutable chunk identifier. The API response should include both display citations and a structured `sources` array. The verifier must reject invented IDs, wrong paper versions, and uncited factual sentences. It cannot prove semantic entailment perfectly; this limitation belongs in the report.

The generation prompt must require all of the following:

1. Use only supplied evidence excerpts; never rely on pretraining or general knowledge.
2. Cite every factual sentence with supplied IDs only.
3. If evidence does not establish the answer, return the exact evidence-boundary refusal format.
4. Do not make a claim merely because it seems likely or because the question presupposes it.

Grounding controls include bounded context, context-only prompting, citation-ID validation, and refusal on validation failure. Citation checks establish source identity and citation coverage, not semantic truth. Reranking and these checks cannot guarantee zero hallucinations; manual evidence grading measures remaining errors.

### 6.6 Single-pass release policy

F11 implementation clarification: preparation and generation request provider JSON-object mode. Output is schema-checked and validated for known citations in each detected sentence; malformed or uncited drafts refuse without regeneration. Sentence splitting is conservative and may over-refuse complex notation. Citation identity/coverage still does not prove semantic entailment; the live novelty-overstatement example in docs/F09_F12_VERIFICATION.md must remain in later grading. Request usage aggregates all persisted attempts, including preparation; unknown usage is null with known subtotals exposed.

Generate one candidate answer from the selected evidence pack. If evidence is absent, return an insufficient-evidence refusal; if citation validation fails, return a validation-failure refusal without claiming the papers definitively lack an answer. Log the selected chunks, validation result, and terminal reason. No answer-quality scores or corrective attempts are part of the runtime. Offline hand-grading remains required for the assignment.

Transport retries for failed API requests remain governed by section 9.2; they do not trigger retrieval refinement or revisions of a completed answer.

### 6.7 Retrieval configurations to compare

Implemented F04–F08 baseline: all settings use the same 200-token/30-overlap recursive index. R1 takes BM25 top 4 from 12 candidates. R2/R3 each fuse 12 lexical and 12 dense candidates, rerank at most 16 against the original question, and retain 5/6 respectively. Deterministic ties, exact offsets, model/tokenizer identities, per-candidate ranks/scores and stage timings are recorded. The larger chunk variants in the historical table below remain deferred experiments. Overlong embedding queries or reranker pairs fail explicitly instead of silently truncating evidence.

Input SHA-256 values are pinned in data/corpus.lock.json; exact PDF version markers must also match. Durable audits retain extracted text/warnings, with no OCR or reconstructed equations. Index publication is atomic after checksums/mapping validation and retains old revisions. No extraction warnings is not proof of correct scientific layout.

The F07 stand-in has isolated validated profiles, bounded workers/queue, seeded request-ID faults, arrival-count failure injection, quota refusal, load slowdown and incremental SSE. F08 uses one event-based HTTP adapter contract, at most three transport attempts, persistent source-specific budgets/cooldowns and conservative unknown usage. Slots are released during backoff. There are no retries after content or a completed/truncated candidate. Limits are configurable local safeguards, not newly measured provider limits; provider-reset reconciliation remains F09 work.

| ID | Retrieval / chunking | Candidates -> evidence | Rerank | Why test it |
| --- | --- | --- | --- | --- |
| R1 | BM25 only; 300 tokens / 50 overlap | 6 -> 4 | no | Cheap lexical baseline. |
| R2 | Hybrid RRF; 500 tokens / 75 overlap | 24 -> 5 | MiniLM cross-encoder | Proposed default: balances semantic/lexical recall and context cost. |
| R3 | Hybrid RRF; 700 tokens / 100 overlap | 32 -> 6 | MiniLM cross-encoder | Tests more context/candidate coverage against latency and token cost. |

These are starting settings, not results. Keep the actual selected setting and all test settings in each CSV row.

## 7. API and data contracts

### Streamlit interface (selected)

Topology: browser -> Streamlit server -> FastAPI -> shared model gateway / retrieval / persistence. Streamlit never calls Groq or reads SQLite/index files directly. FastAPI owns request state, quotas, logs and evidence. The Groq key stays exclusively in backend configuration.

Deliver incrementally: (1) question form, refinement toggle, real/stand-in badge, progress and cited answer; (2) clarification, cancellation, shared paginated history and source excerpts; (3) local run/usage views and exports. Handle pending, refused, failed, timed-out, rate-limited and expired-content states explicitly.

Keep the API client, active request ID and idempotency key in Streamlit UI state. Submit only on a form action; reruns must not create requests. Poll GET for progress initially; SSE remains available to API clients. Polling latency, provider latency and UI render latency are distinct.

Browser refresh may lose temporary UI state; recover through the backend's shared local history without signing in. Streamlit session state is UI memory, not an authentication session. FastAPI and Streamlit bind to loopback.

### 7.1 Local endpoint (proposed)

`POST /v1/requests` creates a durable request; `GET /v1/requests/{id}` retrieves state/results and `GET /v1/requests/{id}/events` streams progress. See API_DESIGN.md for complete validation, errors and pagination contracts.

```json
{
  "question": "What mechanism lets the Transformer attend to different positions?",
  "retrieval_setting": "R2",
  "refinement": "auto"
}
```

Terminal resource states: `answered`, `refused`, `needs_clarification`, `cancelled`, `timed_out`, `rate_limited`, `failed`. CSV status remains the brief's `ok`, `rate_limited`, `timeout`, or `error`; clarification/refusal are completed executions but not automatically correct answers. Grade separately and report outcome counts. API_DESIGN.md specifies the full transition table.

For streaming, emit Server-Sent Events (`status`, `token`, `citation`, `done`, `error`). Emit safe progress states such as `retrieving` and `verifying` immediately. Buffer answer tokens internally until the completed answer passes validation, then stream the verified answer to the caller. This deliberately trades some time-to-first-answer-token for evidence safety; record both internal first-model-token timing and user-visible `first_token_ms` in the diagnostic log. Preserve the final outcome and timings in the CSV even if the caller disconnects.

### 7.2 Required raw-results schema

The exact submission CSV columns are:

```text
request_id,scenario,source,start_time,first_token_ms,total_ms,status,retries,tokens_in,tokens_out,retrieval_setting,answer_grade
```

Use ISO-8601 UTC for `start_time`, milliseconds for time fields, `source` values `real` or `stand-in`, and the four prescribed grades: `correct`, `wrong`, `refused_correctly`, `refused_wrongly`.

Keep the required CSV columns and add clearly documented fields needed to reproduce metrics that those columns cannot express, such as peak queue length, offered load, and cached-token cost. Confirm acceptance of additive columns before submission; if an exact-column schema is enforced, disclose that these figures require companion event/manifest data rather than claiming they can be recovered from the base CSV alone. JSONL events are the detailed source for request summaries and diagnostic timelines.

### 7.3 Structured logging and request tracing (required product feature)

The logger must explain what the system did, why it made a decision, and where time and tokens were spent. Record meaningful lifecycle events and state changes throughout the application, including ingestion and the stand-in. Logging must not add a model call or a corrective loop.

**Implementation:** use Python standard-library `logging` with a JSON formatter, `QueueHandler`, a bounded queue, and a background writer. A shared `telemetry.py` exposes event emission and timed spans. Use `contextvars` to propagate request context across async tasks. Explicitly pass correlation IDs to the stand-in over HTTP. Use one application process initially; each service writes its own file to avoid multiple processes corrupting the same file.

**Correlation and event schema:** each JSONL line is a versioned JSON object with:

| Field | Purpose |
| --- | --- |
| `schema_version`, `event_id`, `event_name`, `level` | Stable schema, deduplication, event classification |
| `timestamp_utc`, `elapsed_ms`, `duration_ms` | UTC wall time for correlation; monotonic elapsed/duration values for accurate timing |
| `run_id`, `service`, `source`, `scenario` | Connect application and stand-in activity to an experiment; source is real or stand-in |
| `request_id`, `span_id`, `parent_span_id` | Trace a user request and its nested stages |
| `call_id`, `attempt`, `stage` | Distinguish preparation/generation and individual transport attempts |
| `outcome`, `reason_code`, `attributes` | Structured decisions and event-specific measurements |

Request/call fields may be null for startup or ingestion events. Use a per-service sequence number when resolving ordering; never subtract monotonic timestamps from different processes. Reason codes are stable identifiers such as `quota_tpm`, `queue_deadline`, `citation_unknown`, or `refinement_bypassed`. Avoid relying on free-text messages to compute metrics.

**Event catalogue:**

| Area | Events and data to capture |
| --- | --- |
| Startup/shutdown | Run ID, safe configuration, software/model revisions, backend, shutdown reason, flush result |
| Ingestion/indexing | Start/end/failure, paper/version/checksum, pages and chunks processed, extraction warnings, index revision, duration |
| Incoming requests | Arrival, admission/rejection, validation failure, scenario, request/query ID, terminal outcome |
| Queue/admission | Enqueue/dequeue/expiry, queue depth after each mutation, in-flight count, wait duration, capacity rejection |
| Input preparation | Direct/refine/decompose/clarify decision, preparation start/end/failure, fallback and reason, safe query reference |
| Retrieval | BM25 and vector stage timings, candidate chunk IDs/ranks/scores, fusion/deduplication counts, index/settings identifiers |
| Reranking | Start/end/failure, candidate count, selected chunk IDs/scores, model/device, duration, context truncation |
| Quotas | Reservation/wait/reconciliation, estimated vs actual tokens, allowance remaining, reset information, exhausted dimension |
| Model calls | Call/attempt start/end, model/settings, first content token, completion, finish reason, token usage, provider request ID |
| Streaming | First internal content chunk, first user-visible answer chunk, completion/interruption, chunk count, bytes and gap statistics |
| Retries/errors | Error category, safe HTTP status, timeout phase, retry schedule/backoff, exhaustion/cancellation |
| Citation validation | Pass/fail, cited/unknown chunk IDs, coverage flags, refusal reason; no claim of semantic proof |
| Request completion | Exactly one terminal summary in normal operation, duration, aggregated usage/retries, delivered outcome |
| Stand-in | Fault selected, seed/profile, simulated queue/worker events, injected delay, simulated quota refusal, response fixture ID |
| Offline evaluation | Question ID, grade, grader/rubric version, evidence references, aggregation completion/failure |

**Streaming detail:** normal runs record first/last chunk and aggregate statistics, not one disk write per token. Calibration mode may record every chunk's timestamp and byte count without its text; label this mode and use it consistently when comparing latency. Progress events and reasoning output never count as the first answer token.

**Levels:** INFO for lifecycle and decisions; WARNING for recoverable failures, rate limits, queue rejection, truncation, or validation refusal; ERROR for failed requests and logging/storage failures; DEBUG for optional candidate and chunk timing detail. Critical benchmark events must remain enabled regardless of DEBUG settings. Exceptions should include a sanitized stack trace without local variable dumps.

### 7.4 Log storage, privacy, and reliability

Store each run under `runs/<run_id>/`:

```text
manifest.json         # safe config, corpus/model versions, seed, arrival schedule
app.events.jsonl      # application lifecycle and spans
standin.events.jsonl  # simulator events, if used
results.csv           # one final row per offered user request
evaluation.jsonl      # manual grades and evidence notes
```

Operational logs contain IDs, hashes, counts, and measurements by default. Do not log API keys, Authorization headers, `.env` contents, raw request/response bodies, reasoning text, or unrestricted exception payloads. Allowlist provider headers: rate-limit/reset fields, retry-after, and request IDs. Apply redaction centrally before console and file output. The fixed evaluation corpus can store original/refined queries and answers in a separate explicitly enabled evaluation artifact for grading; normal user queries remain omitted from logs.

Provide concise console output plus full JSONL files. Proposed defaults: 10 MB file segments, 50 MB per operational run, and seven-day retention for ordinary development logs. Rotate without silently overwriting experiment evidence. Benchmark runs retain all segments until submission; if storage limits prevent complete capture, stop the benchmark and mark it incomplete. Logs and generated artifacts are ignored by Git; curated submission evidence is exported deliberately.

Use a bounded writer queue (initially 10,000 events). Under ordinary development load, optional DEBUG events may be dropped with an explicit dropped-event counter and warning. Never silently drop required benchmark events: stop further benchmark admission, flush what can be saved, and mark the run invalid on queue overflow or write failure. Emit a minimal stderr warning if the writer fails; avoid recursive logging failures. Drain the writer on graceful shutdown. After a crash, detect arrivals lacking terminal events and mark them incomplete rather than inventing outcomes or silently omitting them.

### 7.5 Metrics and logging acceptance checks

Measurement readiness decision (November 13): prioritize a real-service experiment before further stand-in calibration. The current probe remains a small readiness tool, not the F14 benchmark. It records explicit upstream status and disables hidden retries. Keep local quota rejection separate from remote 429, gateway/client timings separate from provider compute/UI delivery, and Retry-After separate from empirical recovery. The proposed larger run and required manifest/attempt records are in docs/REAL_SERVICE_READINESS.md; none of its planned percentile or recovery results is claimed as measured.

- A request ID reconstructs arrival, waits, refinement if any, retrieval, reranking, all provider attempts, validation, and completion.
- Each outbound attempt has its own call/attempt identity; optional refinement and transport retries contribute to total request usage. Missing provider usage is null/unknown, never silently zero.
- A single finalizer produces one terminal request record; the exporter deduplicates by run/request ID. Arrival reconciliation detects missing summaries and orphan spans.
- Record terminal status separately from intermediate 429 events, so a retried request that eventually succeeds is not counted as a terminal rate-limit failure.
- Preserve offered-arrival timestamps and the run schedule, including requests rejected before generation. Capture queue depth at every queue mutation to derive peak queue length.
- Generate CSV summaries from events and grading data. Keep unknown first-token times null for requests with no answer; document percentile populations and exclude missing values without hiding their counts.
- Validate synthetic secrets are redacted, async requests keep their own IDs, provider faults produce expected traces, logging saturation is visible, and graceful shutdown flushes events.
- Measure logging overhead on the same stand-in workload with logging enabled/disabled; report the difference, without claiming zero overhead in advance.

## 8. Concurrency, rate limits, and queueing

### 8.1 Dispatcher

Implement one shared async dispatcher. It owns all budget counters and the outbound Groq client; individual request handlers must not independently call Groq.

- Use separate token buckets for RPM, TPM, RPD, and TPD, configured from measured/account values.
- Enforce daily budgets with persistent counters and observed reset times; do not refill a daily allowance continuously or assume local midnight is the provider reset. Enforce separate input/output minute limits if the account exposes them.
- Reserve one request plus estimated input and capped output tokens before dispatch.
- Reconcile the reservation from actual usage after the response.
- Enforce a bounded global queue and a per-client queue limit.
- Use FIFO by default. A simple round-robin per-client policy is an optional fairness improvement only if time permits.
- Cap in-flight real requests conservatively at first, then record the limit and rationale in the report.

### 8.2 Limits policy

| Condition | System action | User experience |
| --- | --- | --- |
| Capacity available | Dispatch | Normal streamed answer. |
| Minute budget near limit | Reduce retrieval `top_k` only if the evidence remains sufficient; otherwise queue/refuse | Clear short wait/status. |
| Minute budget exhausted | Honor `retry-after`; queue only within deadline | "Temporarily busy; retry after …" |
| Daily budget exhausted | Do not call Groq; record outcome | "Today's answer budget is exhausted. Please try after reset." |
| Queue deadline reached | Drop before model call | "The queue is full; please retry." |

Never reduce citations or let the model answer from general knowledge to save budget.

### 8.3 Real-provider observations

Record Groq response headers on every real request. Groq documents that rate limits may apply to requests/tokens per minute and day, that a 429 signals a limit hit, and that `retry-after` is supplied on 429 responses. Account-specific limits may differ and can change, so the Console Limits page plus observed headers are the experimental ground truth.

### 8.4 Published quota snapshot and burst policy

The current public table lists `openai/gpt-oss-120b` at **30 RPM, 1,000 RPD, 8,000 TPM, and 200,000 TPD**. The page exposes Free/Developer selectors but also includes a conflicting Developer-plan description. Treat this as a provisional public snapshot; confirm the selected Free-plan row in the account Console before enabling live experiments. Organization limits and any stricter project limits apply. Some accounts also have input/output TPM caps. No explicit concurrency cap was verified. [Groq rate limits](https://console.groq.com/docs/rate-limits)

Groq documents HTTP 429 and `retry-after`. Its `x-ratelimit-*-requests` headers describe daily requests; token headers describe minute tokens. These do not independently confirm all quotas. Capture headers and account values with timestamps; do not label documentation as measured evidence.

**Proposed burst controls:** start with two in-flight calls, a ten-request queue, an eight-second maximum waiting budget, and a 45-second total request deadline. These are application settings. All preparation, generation, and retry calls share the dispatcher. Add a configurable 20% capacity margin; gate on every applicable budget. Browser/SSE disconnect does not cancel durable work; explicit cancellation or deadlines stop it and safely release unsent reservations. Do not assume cancelled remote work is unbilled or quota-free.

For planning only, if an answer consumes 3,000 total tokens across its calls, an 8,000 TPM budget permits about 2.7 answers/minute before safety margin; 200,000 TPD permits about 66 answers/day. These are arithmetic illustrations, not benchmark results. More concurrent calls cannot raise token quotas. When budget is depleted, queue only within the deadline or return a capacity message; test heavy bursts and daily exhaustion on the stand-in.

For a paid-equivalent estimate, compute `(uncached_input * 0.15 + cached_input * 0.075 + output * 0.60) / 1,000,000` dollars using recorded usage, then scale by delivered answers. Label this estimate separately from actual Free-tier charges and include failed/retried call usage when available. Unknown usage stays unknown.

## 9. Latency, streaming, retries, and fallback

### Definition of fast and proposed performance targets

These are initial product targets for a warmed local system under light load, not measured results or provider guarantees. Report hardware, sample count, input/output lengths and refinement route with each benchmark. Cold startup/model loading and overload are separate scenarios.

| User experience / stage | Initial target | Measurement boundary |
| --- | --- | --- |
| Submission acknowledged | within 500 ms p95 | API arrival to accepted/rejected response; UI reports immediately after receiving it |
| Hybrid retrieval plus reranking | within 1,000 ms p95 | Local search start through final evidence selection |
| Complete, citation-checked direct answer | within 5 seconds p50 and 10 seconds p95 | Arrival through final response ready; include queue time |
| Refined-query answer | within 8 seconds p50 and 15 seconds p95 | Same boundary, including preparation call |
| Progress update in Streamlit | about once per second while active | UI polling interval; not first answer token |

The 45-second overall deadline and eight-second cumulative waiting cap are failure bounds, not acceptable normal latency. Under overload, report rejection, timeout, clarification and refusal rates alongside latency; do not hide them by only reporting successful fast requests. No claim that users will tolerate these targets is established without user testing.

For speed: extract/chunk/embed/index PDFs offline; load local models and indexes once during startup; warm them before benchmark runs; cache immutable artifacts by corpus/model/settings revision. Use bounded BM25/vector candidates and reranker batches, avoid duplicate chunks, cap prompt size, and prefer a concise answer with low reasoning effort initially. Run CPU-heavy embedding/reranking work outside the async event loop with bounded worker capacity. Skip optional refinement for clear questions. Every extra provider call uses shared quota and adds latency. Measure each stage before tuning; do not assume a larger model or a semantic chunker will be faster.

Current release policy buffers the full answer for citation checks. Consequently, first user-visible answer content arrives near completion; early progress messages do not improve true answer TTFT. Immediate unvalidated streaming would change this safety trade-off and is not enabled. Polling may add up to its interval to UI visibility; record that separately. If measured targets fail, first tune candidate count, chunk/context budgets and reranker model on the fixed evaluation set while tracking quality; then revisit targets transparently.

### Chunking decision to evaluate

**Decided: use RecursiveCharacterTextSplitter for the initial implementation.** Verify the PDFs already stored in data/, extract page text, then split each page with ordered separators `['\n\n', '\n', ' ', '']`. Preserve paper ID/version, PDF page, text offsets and chunk/index revision. Starting per-page splitting simplifies exact citations, but may separate a paragraph crossing pages; record that limitation and evaluate such questions. Do not silently mix papers or discard provenance.

The library defaults measure characters, not tokens. Configure a token-counting length function using the selected embedding tokenizer, pin its version and validate final token lengths; the sizes in R1/R2/R3 are tokens, not Python character counts. A starting candidate is 300 tokens with 50 target overlap, subject to the embedding input limit and the cross-encoder's combined query/document limit. Reserve room for special tokens, query text and any heading prefix. Reduce caps if needed, save the actual configuration in the manifest, and never silently truncate source evidence. The existing 500/700-token variants are conditional experiments only if compatible with the chosen model inputs, not guaranteed safe defaults. Count the final Groq prompt separately with its applicable tokenizer/estimator.

Why this baseline: deterministic, inexpensive offline processing, easy size/overlap controls, and no extra model call to choose boundaries. It prefers paragraph/newline breaks before smaller separators, but does not understand PDF tables, equation structure or semantic completeness. Validate extraction/reading order before blaming chunking for missed evidence. Source: [LangChain recursive splitter documentation](https://docs.langchain.com/oss/python/integrations/splitters/recursive_text_splitter).

### Later chunking experiments (deferred)

| Strategy | Why it could suit research papers | Cost / limitation and priority |
| --- | --- | --- |
| Sentence-packed token windows | Avoid cutting a prose definition midway; simple alternative to recursive splitting | Abbreviations, equations and citations complicate sentence detection; inexpensive first comparator |
| Structure-aware sections with recursive overflow splitting | Keep heading context with Methods, Results or Ablations; retain table captions/headers | Requires reliable structured PDF extraction; first substantial upgrade when extraction errors dominate |
| Small child chunks with bounded parent/neighbor expansion | Retrieve a specific statement, then include nearby definitions or qualifications | Adds context tokens and mapping complexity; expanded evidence must keep exact source IDs and fit reranker/generation budgets |
| Semantic boundary detection | Split where adjacent sentence embeddings indicate a topic change | Extra offline embedding work and threshold tuning; does not inherently preserve tables/equations; test only after baseline |

Docling's hierarchical/hybrid chunkers provide a possible future implementation for document-structure and tokenizer-aware splitting; adopting that parser would be a separate experiment. Its term "hybrid chunker" is unrelated to our BM25/vector hybrid retrieval. [Docling chunking documentation](https://docling-project.github.io/docling/concepts/chunking/)

A study across retrieval/evidence/answer-generation tasks found semantic chunking did not yield consistent gains sufficient to justify its added cost in that evaluation. This is a reason to benchmark, not proof it cannot help these papers. [Qu et al., Is Semantic Chunking Worth the Computational Cost?](https://arxiv.org/abs/2410.13070)

### Fair chunking comparison

First hold extraction, embedding model, BM25/vector fusion, candidate limits, reranker, prompt budget, refinement policy and generator settings fixed; vary only chunking. Use the same questions with manually marked source spans, including prose, numeric/table questions, cross-page evidence and unsupported queries. Compare evidence recall/coverage, correct-and-cited answers, false refusals, prompt tokens, index size, ingestion duration, and warm retrieval/reranking/answer latency. Run offline retrieval checks first; spend hosted quota only on shortlisted variants. Record small-sample uncertainty; no performance data exists yet.

Overlap may create duplicate evidence, so deduplicate context and measure zero versus modest overlap separately. The existing R1/R2/R3 table changes several retrieval settings at once and is a system comparison, not proof of chunking's isolated effect. Keep alternative chunkers behind a common interface returning text plus provenance; publishing a new strategy creates a new immutable index revision. No semantic or LLM-based chunker is required for F05.

### 9.1 Timing definitions

- `queue_ms`: arrival to dispatcher admission.
- `retrieval_ms`: local retrieval start to prompt-ready.
- `refinement_ms`: initial preparation call duration, zero when bypassed; log its tokens separately and aggregate them into request totals.
- `model_wait_ms`: Groq dispatch to first received model byte/delta.
- `first_model_token_ms`: request arrival to the first token received from Groq (diagnostic event log).
- `first_token_ms`: request arrival to the first verified answer token emitted to caller (required CSV field).
- `stream_ms`: first emitted token to final token.
- `total_ms`: request arrival to final terminal outcome.
- `retry_ms`: total intentional backoff/wait time before retry.

For one slow request, report these pieces separately and show whether the delay occurred before or after first token using event timestamps.

### 9.2 Retry policy

- Retry at most twice for transient network errors, 5xx errors, and configured stand-in failures.
- For 429, use provider `retry-after` if present; otherwise use capped exponential backoff with random jitter.
- Do not retry invalid input, unsupported models, citation/evidence failures, or a request with no remaining user deadline.
- Stop retries if the waiting budget or total request deadline would be exceeded.
- Log every attempt. A retry is part of the same `request_id`, with the final retry count in CSV.

Required negative case: deliberately show one overload scenario where retries worsen p95/queueing or success rate, then explain why limiting retries was chosen.

### 9.3 Fallback policy

1. Valid evidence but provider temporarily unavailable: retry within policy, then return a short unavailable response; do not generate locally fabricated text.
2. Insufficient evidence: return an explicit paper-library refusal with relevant retrieved citations if helpful.
3. Daily quota gone: no model fallback; return the daily-budget message.
4. Stand-in experiment: label all resulting answers/metrics as `stand-in`, never as real Groq data.

## 10. Stand-in model service

Build `standin_service.py` or a small FastAPI app with an explicit configuration file/CLI flags.

| Capability | Proposed behavior |
| --- | --- |
| Streaming | Emit a fixed response in configurable chunks at a configured tokens/second rate. |
| Base latency | Sleep for a seeded sampled delay before the first chunk. |
| Load slowdown | Add delay based on active jobs and/or queue depth. |
| Failure | Return configured timeout/network-like error probability. |
| Limit refusal | Enforce synthetic RPM/TPM/RPD/TPD and emit 429 plus `retry-after`. |
| Determinism | Accept a seed and write its configuration into experiment metadata. |

Calibrate distributions only from measured real samples. Explicitly identify differences: it cannot reproduce undisclosed provider queueing, shared-tenancy effects, or all quota semantics.

## 11. Evaluation and experiment plan

### 11.1 Question set

Create and freeze at least 15 questions before comparing configurations:

- 9 clearly answerable questions distributed across the three papers;
- 3 questions not answered by the library;
- 3 misleading/ambiguous questions (shared terms, overly broad premise, or plausible but unsupported detail).

Hand-grade each output using the prescribed categories. Preserve the questions, expected evidence, and grading rationale in version-controlled test data.

### 11.2 Scenarios

| Scenario | Source | Purpose |
| --- | --- | --- |
| Steady | real, then stand-in | Establish normal latency and success baseline. |
| Sudden burst | modest real and stand-in | Observe queueing and fairness. |
| Sustained overload | stand-in | Safely observe saturation and retry effects. |
| Per-minute limit halved | stand-in | Test limit adaptation/degradation. |
| Daily budget exhausted | stand-in | Test the 3 p.m./budget-gone user response. |

Do not drive the real Free tier with deliberate heavy load. That would conflict with both the assignment's intent and provider terms.

### 11.3 Required aggregates

Generate from CSV:

- Table 1: real-service limits, discovery method, and confidence.
- Table 2a: p50/p95/p99 time-to-first-token and total time per scenario.
- Table 2b: success, rate-limit, timeout/give-up percentages; retries; peak queue; tokens/answer; cost per 1,000 answers.
- Table 3: retrieval-setting quality grades, token usage, and latency.

Use milliseconds and one decimal place for percentages. Include the request count (`n`) and the percentile method. Use `not measured` rather than an invented number.

## 12. Repository layout (proposed)

```text
.
├── data/                         # supplied, version-locked source PDFs
├── src/
│   ├── config.py
│   ├── telemetry.py              # structured events, correlation, spans, redaction, writer
│   ├── ingest.py                 # extract, normalize, chunk, index
│   ├── retrieval.py               # vector + BM25 + RRF
│   ├── reranker.py                # local cross-encoder
│   ├── router.py                  # initial direct/refine/decompose/clarify routing
│   ├── budget.py                 # token buckets and dispatcher
│   ├── groq_client.py            # streaming client + raw header capture
│   ├── pipeline.py               # hybrid retrieval + single draft + release/refuse branch
│   ├── verify.py                 # citation/evidence checks
│   ├── api.py                    # FastAPI endpoint/SSE
│   └── standin_service.py
├── tests/
├── ui/
│   ├── app.py                    # Streamlit entry point
│   └── api_client.py             # session-scoped FastAPI client
├── scripts/
│   ├── run_probe.py
│   ├── run_load.py
│   └── aggregate_results.py
├── eval/questions.jsonl
├── results.csv                   # generated; never hand-edited
├── runs/                         # required per-run logs, manifests, results and grades
├── .env.example                  # names only, no secrets
├── .gitignore
├── requirements.txt
└── PRODUCT_REQUIREMENTS.md
```

Expected `.env.example` content:

```text
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
GROQ_REASONING_EFFORT=low
GENERATION_MAX_COMPLETION_TOKENS=1024
REFINEMENT_MAX_COMPLETION_TOKENS=512
GROQ_RPM=
GROQ_RPD=
GROQ_TPM=
GROQ_TPD=
```

`.env` must be in `.gitignore`. Never print it in logs, screenshots, reports, or chat transcripts.

## 13. Testing plan

- **Unit tests:** chunk IDs/page mapping, BM25/vector/RRF determinism, cross-encoder candidate limits, citation parsing, budget reservation/reconciliation, transport retries, release/refuse branching, and CSV row validation.
- **Integration tests:** run the full pipeline against stand-in normal/slow/429/error modes; verify citation-validation failure releases a refusal and never triggers evaluator, post-answer query-rewrite, or regeneration calls.
- **Refinement tests:** clear queries bypass preparation; vague queries preserve intent; unresolved referents trigger clarification; negations and named papers survive rewriting; malformed output falls back safely; at most one preparation call occurs. Compare refinement on/off using the same questions, tracking quality, added latency, and aggregate token use.
- **Contract tests:** validate every CSV row has exactly the required columns and legal status/grade values.
- **Manual evidence tests:** inspect citations for all 15 evaluation questions against the PDFs.
- **Reproducibility test:** remove generated aggregates; regenerate results tables from raw CSV and compare.
- **Secret-safety check:** verify `.env` is ignored and no key-pattern occurs in tracked files.

## 14. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Groq quota/model availability changes | Use account limits and response headers as the source of truth; make limits/model configurable. |
| PDF extraction loses layouts/equations | Retain page identifiers; manually validate representative chunks and citations. |
| Model invents citations | Only accept citations from a supplied fixed ID list; deterministic validation and release/refuse branch. |
| Retrieval misses evidence | Compare three settings; include a refusal path; document false refusals. |
| Valid citation points to text that does not support a claim | Context-only prompting and manual evidence evaluation; document that citation validation cannot prove semantic support. |
| Retry storm during overload | Centralize retries, cap attempts, use jitter, respect deadlines. |
| Slow work blocks the API | Use async dispatcher and bounded queues; make local retrieval inexpensive. |
| Misleading synthetic results | Clearly label stand-in rows and describe calibration gaps. |
| Deadline pressure leads to fabricated measurements | Use `not measured`; preserve raw data and prioritize required scenarios. |

## 15. Open questions and decisions to make before implementation

| Question | Why it matters | Proposed default | Owner/status |
| --- | --- | --- | --- |
| Which Groq model is selected? | Controls integration and benchmarking. | `openai/gpt-oss-120b`; verify account access during the first probe. | Decided by user. |
| What exact account limits are displayed? | Dispatcher configuration and Table 1 need real values. | Record Console values and headers; do not infer. | User + measurement. |
| User interface? | Interactive demo and API testability. | Streamlit calling FastAPI; CLI/Postman remain API test clients. | Decided by user. |
| Hybrid retrieval implementation? | Affects dependencies, latency, and experiment design. | FAISS dense retrieval + BM25 + RRF, then local MiniLM cross-encoder. | Proposed. |
| Which questions need preparation? | Refinement adds quota cost and latency. | Clear queries bypass; vague/multi-part queries use one combined preparation call; genuinely missing intent triggers clarification. | Feature decided; thresholds to validate. |
| Should answer streaming be buffered? | Immediate content streaming exposes text before citation validation. | Emit progress immediately; buffer answer tokens until citation checks pass. | Proposed. |
| What is the user-facing queue deadline? | Defines when “fast” becomes a failure. | Start with 8 seconds; revise after baseline measurement. | Proposed/validate. |
| What completion cap is safe? | Reasoning also consumes completion budget. | 1,024 generation / 512 preparation tokens; target roughly 300 visible answer tokens. | Proposed/validate. |
| How is answer validation performed? | Semantic checking is imperfect. | Deterministic citation checks followed by release or refusal; no LLM evaluator or repair call. | Decided. |
| Where are source PDFs version-verified? | The assignment requires exact versions. | Verify arXiv IDs/version text before ingestion and record checksum. | Required action. |
| What counts as “cost per 1,000 answers” on Free tier? | Table requires a value. | Record actual direct charge if observable; otherwise report the documented/observed basis and avoid invented cost. | Needs report wording decision. |
| How are “given up” outcomes represented? | Brief's CSV status set does not include it. | Use `timeout` with diagnostic event reason `queue_deadline` or `retry_exhausted`. | Proposed. |

## 16. Implementation milestones

1. **Foundation:** add `.gitignore`, `.env.example`, dependency file, configuration validation, source-PDF/version audit, and structured logging with run/request IDs before implementing pipeline stages.
2. **Grounded hybrid RAG:** implement extraction, stable chunks, embeddings, BM25/RRF, cross-encoder reranking, citations, and refusal path.
3. **Provider integration:** configure GPT-OSS 120B, add conditional initial refinement/planning, one generation pass, citation validation, header/usage capture, CSV event logging, and a small real-service probe to confirm limits and tune completion budgets.
4. **Resilience and experiment:** add dispatcher/budgets/retries/stand-in, instrument all lifecycle events, validate complete traces and logging failure handling, run scenarios, grade answers, generate tables and report evidence.

## 17. Definition of done

The project is done when a reviewer can clone it, configure a fresh `.env`, ingest the supplied papers, run the service and stand-in, reproduce the experiment commands, and trace every number in the report back to `results.csv`; when every answer is cited or explicitly refused; and when the submitted code and conversation history accurately reflect the decisions, measurements, uncertainty, and limitations.

## 18. Detailed user flows

These are product acceptance requirements, not claims of implemented behaviour. Each flow specifies its entry condition, normal path, alternatives and durable outcome. The system supports independent questions; history is not automatically supplied as conversational memory.

### U01 — Open the local application

Precondition: Streamlit and FastAPI are running locally. Opening the app shows the question form immediately, along with library readiness and real/stand-in status. There is no login screen. If the API or index is unavailable, show a clear readiness message and disable submission. History is shared across browser tabs on this local instance; do not promise private user histories.

### U02 — Ask a clear, supported question

Precondition: ready local API and index. The user writes a question, leaves refinement on auto (or disables it), chooses an allowed retrieval setting, and submits once. UI validation checks basic length/emptiness; API validation is authoritative. Streamlit generates and retains an idempotency key. FastAPI persists admission and returns the request ID. The UI polls that ID while displaying queue, retrieval, reranking, generation and validation states as available; it does not claim stages happened when bypassed.

Clear questions bypass the preparation model call. The backend searches and reranks the pinned library revision, generates one candidate, validates citations, and commits answer/citations before release. The UI displays the final answer with source expanders. Retrieval setting, model/source and timings are available as details. Failed admission produces a capacity or readiness message without generation. A generation or validation failure follows U05, never a corrective loop.

### U03 — Refine a vague question or request clarification

For recoverable wording, the preparation stage produces one intent-preserving query before retrieval. The final answer still responds to the original question. Refinement must retain negation, entities, requested comparisons and paper scope. A user can view the refined query as optional request detail, not as an answer.

If the question lacks essential context (for example, "Why is it better?"), return needs_clarification with one focused question. The UI presents a new form. The user supplies a self-contained question, submitted as a new resource with parent_request_id and a new idempotency key. The original remains terminal. Do not guess the missing paper, silently use unrelated history, or repeatedly prompt the model to rewrite the same query. Preparation failure falls back to the original only when usable; lack of quota does not justify inventing intent.

### U04 — Inspect citations and previous answers

The user expands a citation to see its exact retrieved chunk, paper version and PDF page range. The source viewer resolves the original index revision even after a new revision is published. A missing source is an explicit integrity error, not a replacement passage. History uses backend cursor pagination; changed filters clear old cursors. Selecting a row loads its durable result. Browser refresh may lose UI state; shared local history restores access without generating another answer. Expired content shows an expiry message rather than a blank answer represented as success.

### U05 — Unsupported question, validation refusal or provider failure

Out-of-library questions and insufficient retrieved support receive a plain-language refusal. Use "I could not find enough supporting evidence in the retrieved passages" when retrieval is inconclusive. Citation-validation failure receives a distinct inability-to-validate message. These are separate from provider errors, timeouts and quota exhaustion. Never display a failed draft. The UI lets the user edit the question and explicitly submit a new request; it does not automatically regenerate or switch to a simulated answer. Valid citation IDs alone do not guarantee a claim is true.

### U06 — Busy queue, cancellation and disconnect

When admitted but waiting, show the current stage and elapsed wait; show no exact completion estimate without supporting measurements. Queue-full or exhausted quota produces a capacity message and known retry time, if available. Optional refinement may be bypassed under pressure only for usable questions. Clicking Cancel sends the explicit cancellation API request. First committed terminal transition wins if cancellation races with completion; UI displays the returned state. Cancellation cannot guarantee that already-dispatched provider work stops or consumes no quota.

Closing/reloading the browser, losing SSE/polling connectivity does not itself cancel a durable request. Deadlines still bound work. An uncertain submission response is retried with the same key/body; changing the body requires a new key. Reconnection queries state or replays events and never restarts inference.

### U07 — Run and inspect experiments

The operator starts versioned experiment profiles through the CLI, selecting real Groq or the controlled stand-in explicitly. The runner records the scheduled arrivals, configuration, seed and source. The UI displays the run list, counts, outcomes and sanitized traces; stand-in results remain visibly labelled. Stop requests prevent new arrivals and let active work finish within deadlines; missed planned arrivals are recorded and completeness assessed. The operator grades the fixed evaluation questions, generates tables and downloads results. Incomplete, ungraded or missing-usage runs must not masquerade as complete measurements. The optional incomplete export is clearly labelled. No UI action launches unrestricted provider load or alters quotas secretly.

### U08 — Ingest or rebuild the fixed library

The operator runs the ingestion CLI. Version and checksum verification precede extraction; warnings are recorded for malformed text/pages. Build chunk metadata, embeddings, vector and keyword indexes into a new revision. Validate artifacts before publishing the active pointer. On failure, retain the last usable revision; if none exists, readiness fails. Requests already admitted remain pinned to their original revision. The UI exposes progress/readiness through the backend; it cannot upload arbitrary new papers.

## 19. Data flows and ownership

### D01 — Offline source-to-index flow

```text
Three verified PDF versions
  -> checksum/version audit -> page extraction -> chunking
  -> immutable chunk metadata in SQLite
  -> local embeddings + FAISS index + BM25 index files
  -> manifest/checksum/mapping validation
  -> atomic active-revision publication
```

Paper/version/page/chunk identifiers accompany text throughout the flow. PDFs remain immutable inputs. Extraction errors stop publication when provenance or completeness cannot be established. Embedding/reranker models are local dependencies; their versions and preprocessing settings belong in the manifest. Runtime searches never fetch outside sources.

### D02 — Online question-to-answer flow

| Step | Input -> output | Owner / persistence |
| --- | --- | --- |
| Submit | Original question, setting, refinement choice, idempotency key -> request ID | API validates and pins setting/index; SQLite stores durable state |
| Prepare | Original query -> unchanged/refined query, subqueries or clarification | Optional gateway call; preparation usage counted; never interpreted as evidence |
| Retrieve | Search query/subqueries -> BM25/vector candidates -> fused ranking | Local retrieval; chunk IDs/ranks stored as evidence metadata |
| Rerank | Original intent and candidates -> bounded evidence pack | Local cross-encoder; selected IDs/context order retained |
| Generate | Original intent + selected source text -> buffered candidate | Groq through gateway; raw drafts/reasoning withheld from user and normal logs |
| Validate | Candidate and supplied IDs -> release or refusal | Deterministic checks; no rewriting/retrieval loop |
| Finalize | Terminal outcome + answer/citations + usage -> committed resource | Atomic backend transaction; audit/public events recorded |
| Deliver | Resource/public events -> UI result and sources | Polling or API SSE; reconnects reuse the resource |

Only the question/preparation input and selected excerpts needed for a call go to Groq. DB contents, provider secrets, whole-library text and internal logs are not appended to prompts. The refinement output and paper text are untrusted data, not instructions to override source restrictions. The Groq API key is used solely for provider authentication.

### D03 — Quota and error flow

Every provider attempt requests capacity from the same gateway. Reserve applicable request/token allowances and a concurrency slot atomically, then perform HTTP outside a database transaction. Reconcile known usage when complete. Release only clearly unsent work; preserve uncertain dispatched usage conservatively. On transient errors, back off within waiting/total deadlines and the retry cap. Provider-side 429 and local admission rejection are recorded distinctly. Real and stand-in budgets are isolated. First-token and completion timestamps, retry waits and quota decisions share the user request ID but retain separate call IDs.

### D04 — Logs, database and reporting flow

Durable transitions -> SQLite audit outbox -> sanitized JSONL export -> per-request summaries/metrics -> CSV and report tables. Optional detailed timing events use the bounded background writer. Event IDs enable deduplication after export retries. Manual grades join by request/question IDs. Reconcile offered arrivals against terminal records before export. Persist UTC for cross-service correlation and use local monotonic clocks for durations; never subtract monotonic clocks from different processes.

Raw request/answer content belongs only in access-controlled request/evaluation storage, not ordinary operational logs. Temporary UI state and durable request state have separate lifetimes. Seven-day interactive retention can remove content, but benchmark evidence is retained through submission. Missing samples or grades stay explicitly missing. Detailed traces/manifest remain necessary where the original CSV schema lacks enough fields; resolve the submission format before claiming every statistic is recoverable from CSV alone.

### D05 — Trust boundaries and data invariants

- Streamlit talks to FastAPI only; no direct Groq, SQLite or index access from UI code.
- API validation, local access constraints and idempotency apply equally to Streamlit and Postman.
- Exactly one logical answer-generation pass; transient transport retries do not authorize a corrective answer cycle.
- One pinned evidence revision per request; citations must resolve within its selected evidence.
- Public API state, execution status, answer grade and delivery state are different fields. An HTTP 200 is not proof of a correct answer or actual browser receipt.
- Known zero and unknown are distinct; provider reasoning/progress tokens are not user-visible answer tokens.

## 20. Edge cases, corner cases and acceptance coverage

The expected behaviour below must become tests within the owning feature. This matrix does not assert those tests already exist. Proposed timeout/queue values are configuration to validate, not provider guarantees.

| ID / case | Required behaviour | Feature coverage |
| --- | --- | --- |
| E01 Empty, whitespace-only, oversized or malformed question | Reject before inference with field-safe validation error; byte and character limits both enforced | F01, F13, F15 |
| E02 Unicode, equations, acronyms and negation | Preserve meaning during normalization/refinement; support symbols without injecting markup | F04–06, F10 |
| E03 Missing paper/referent, ambiguous comparison | Ask a focused clarification; no invented context or automatic chat memory | F10–11, F15 |
| E04 Clear query with refinement off | Bypass preparation call; still allow clarification if intent is unusable | F10 |
| E05 Rewrite changes numbers/entities/negation or returns invalid JSON | Reject unsafe rewrite; use original only if usable, otherwise clarify; no repeated refinement | F10 |
| E06 User asks to ignore evidence or document contains instructions | Treat question/excerpts as untrusted data; retain library/citation rules; no arbitrary tools | F10–11 |
| E07 Wrong PDF version, checksum mismatch or missing paper | Block publication; keep old valid index if available; record precise diagnostic | F04–05 |
| E08 Broken extraction, tables, formulas, column order, headers | Flag warnings, inspect representative pages, preserve page provenance; no unsupported reconstructed numbers | F04–06 |
| E09 Duplicate/overlapping chunks dominate top-k | Deduplicate stable IDs and apply bounded candidate/context selection; track paper coverage for comparisons | F05–06 |
| E10 Same technical term in different papers | Preserve requested paper scope and rerank against original intent; test misleading lexical matches | F06, F14 |
| E11 Claim exists only in a table or outside retrieved chunks | Refuse insufficient retrieved support if unavailable; do not claim the entire paper lacks it; grade false refusals | F06, F11, F14 |
| E12 Cross-paper evidence conflicts or has different conditions | Qualify supported claims and cite each source; do not invent a universal comparison/winner | F11, F14 |
| E13 Evidence exceeds reranker/model token limits | Truncate/select at documented boundaries with metadata; reserve actual prompt budget; refuse if key support is lost | F06, F08, F11 |
| E14 Corrupt/mismatched index or embedding dimensions | Fail readiness or request safely; never mix index mappings | F05, F13 |
| E15 Reranker/model files unavailable or inference fails locally | Explicit configuration/service failure; no silent switch to a different retrieval setting | F05–06 |
| E16 Provider returns empty/truncated answer or invented citation | Do not release candidate; record reason and safe failure/refusal; no answer repair call | F09, F11 |
| E17 Real citation attached to unsupported claim | Document deterministic-check limitation; manual grading must count it wrong rather than treating format as proof | F11, F14 |
| E18 Burst exceeds queue or token capacity | Bounded admission, fair configured waiting and prompt capacity response; no unbounded tasks | F08, F13–14 |
| E19 RPM available but TPM/TPD exhausted | Gate on all dimensions and all stages; optional refinement does not bypass reservations | F08 |
| E20 Other account activity consumes quota | Reconcile provider observations, respect 429/reset data; local counters are estimates | F08–09 |
| E21 Daily reset unknown, clock changes or process restarts | Do not assume local midnight; persist ledger, use observed/configured reset, duration clocks stay monotonic | F03, F08 |
| E22 Slow success, timeout, 5xx, retry-after beyond deadline | Bounded retry/backoff; stop within deadline; unknown remote usage retained | F07–09 |
| E23 Duplicate clicks, Streamlit rerun, lost POST response | Reuse original idempotency key/body; same resource, no duplicate inference; changed body with same key is 409 | F03, F13, F15 |
| E24 Cancel races with successful completion | First committed terminal update wins; reconcile late usage, no terminal-state reversal | F08, F13 |
| E25 Browser closes, polling fails, SSE reconnects | Keep work bounded by deadline; resume via resource/events; never restart generation | F13, F15 |
| E26 Multiple tabs, refresh and local shared history | No login required; prevent duplicate submission on rerun; recover through shared history without claiming per-user isolation | F12–13, F15 |
| E27 Invalid/expired cursor or filter changes | Return typed cursor error; reset pagination; no duplicate model calls when navigating | F13, F15 |
| E28 Reindex occurs during an active request | Continue on pinned revision; old citations remain resolvable | F03, F05, F13 |
| E29 DB lock, disk full, process crash or logger overflow | Bounded failure handling; no silent quota bypass; recover uncertain work conservatively and mark incomplete evidence | F02–03, F08, F14 |
| E30 JSONL export repeats after crash | Deduplicate by event ID; exactly one terminal summary per request, preserve missing-event flags | F02–03, F14 |
| E31 Zero answer tokens, missing usage, no connected subscriber | Store null unknown timing/usage; label measured zero separately; never fabricate delivered TTFT | F09, F13–14 |
| E32 Stand-in response looks like a real answer | Always label source; fixtures evaluate system behaviour, not Groq answer quality; no silent provider fallback | F07, F14–15 |
| E33 Retry storm or overload load-generator bottleneck | Cap attempts, release call slots during backoff, record scheduled vs actual arrivals and generator lag | F08, F14 |
| E34 Small sample p99, mixed settings or ungraded responses | Show sample sizes/populations; group by frozen config; label weak/unknown statistics and incomplete exports | F14 |
| E35 Purged history or benchmark evidence retention | Return content-expired state; preserve non-sensitive metrics; never auto-delete required submission evidence | F03, F13–15 |
| E36 Source/model text includes HTML or unsafe links | Render escaped text/controlled citation links; never execute retrieved code or HTML | F13, F15 |

### Coverage and implementation handoff

For each feature, add applicable U/D/E identifiers to its verification evidence in PROJECT_STATUS.md. A successful demo of the happy path is insufficient to close the associated failure cases. Test local behaviour with fixtures/stand-in first, and use real Groq only for the modest provider/quality measurements. No further feature scope or application implementation is added by this documentation update.
