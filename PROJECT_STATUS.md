# The Relay — project status and incremental build plan

Last reviewed: November 12, 2026.

## Current state

Version control: Git initialized with origin https://github.com/balajiraparti/The-Relay-Assignment.git. Main holds a minimal repository baseline; dev is the active development branch. Both remote branches exist. Project import is being committed/pushed on dev; future important completed features are committed and pushed there after checks. Pull-request merges remain separate. Secrets and generated runtime artifacts are excluded. This setup does not complete another product milestone.

**Phase: first runnable baseline; F01–F03 complete. Overall project is not complete.** The user authorized these three foundation features together. Their acceptance checks passed; remaining full-contract milestones remain partial or pending. Product/package version is 0.1.0, database schema version is 2. No hosted measurements were added in this work cycle.

Workspace now contains the Python package under src/relay, Streamlit UI, tests, README, dependency manifest and runtime evidence. Original PDFs and .env have been preserved. Version markers in all three PDFs matched the brief; SHA-256 checksums were recorded. Groq key presence and three successful real calls were verified without printing the key.

| Area | State | Evidence / remaining work |
| --- | --- | --- |
| Product and architecture | Documented | PRODUCT_REQUIREMENTS.md |
| API contracts | Partially implemented | Request create/get/history/cancel, capabilities, papers and readiness; full contract still pending |
| Database design | Foundation complete; later schemas pending | Numbered migrations, verified backups, constrained operations/requests/calls/events; corpus/evaluation/outbox schema remains pending |
| Source PDFs | Version-marker verified and indexed | 120 PDF pages, 600 recursive chunks; runtime/indexes/8f3dd356072f433e/manifest.json contains checksums |
| Local configuration | Verified for first probe | Key presence checked; three real calls succeeded |
| Backend, retrieval and model integration | Partial first version verified | Real paper answer with two citations recorded in FIRST_RUN_RESULTS.md; broader quality grading pending |
| Persistence | F03 foundation complete | Constraints, migration rollback, preserved legacy data and concurrent quota reservations tested |
| Stand-in, logging and experiments | Telemetry foundation complete; rest partial | Bounded redacted JSONL writer; synthetic fault controls; initial real probes/calibration; experiment runner pending |
| UI | Initial Streamlit screen verified | Prior health/form checks passed; current running state not asserted; full browser/interaction coverage pending |
| Build tracking | Complete | This file and AGENTS.md |

**Completed milestones: F01, F02, F03 (3 of 16).** The current suite has 24 passing tests. This is a count of finished milestones, not an effort percentage. Initial real measurements exist; answer-quality and load benchmarks are not complete.

## How to use this file

This is the source of truth for work status, dependencies, verification evidence and the next task. Product behaviour remains defined in the PRD and detailed contracts. Update both when an approved design decision changes implementation scope.

States: `Not started`, `In progress`, `Blocked`, `Implemented — verification pending`, `Done`, `Deferred`. Done means the feature works, its relevant acceptance checks passed, and the evidence is recorded here. A blocked row must state the blocker and the next safe action. Avoid speculative completion percentages.

For each feature:

1. Mark only the selected feature In progress and record its scope before implementation.
2. Implement its smallest useful version behind a module boundary; use fixtures for dependencies that are not ready.
3. Run the listed acceptance checks and record the exact command, outcome, date and limitations.
4. Update this file with changed files, decisions and remaining work. Never mark passing tests or successful live calls without having run them.
5. Hand off the feature for review before starting the next milestone unless the user explicitly requests several milestones together.

No feature silently adds paid services, replaces the selected architecture, restores the corrective loop, or expands to public multi-user deployment.

## Modular implementation backlog

Current milestone states: F01 Done; F02 Done (telemetry foundation); F03 Done (persistence foundation). F04–F13 remain partial; F14 partial provider probe only; F15a has basic form verification; F15b/F15c and F16 pending. The table preserves full acceptance criteria.

| ID | Feature / boundary | Dependencies | Acceptance / demonstrable output |
| --- | --- | --- | --- |
| F01 | Project skeleton and safe configuration: package layout, dependency manifest, test runner, .gitignore, .env.example, config loader | None | Package imports; configuration validates missing/invalid values without printing secrets; test discovery works; existing .env preserved |
| F02 | Structured telemetry: run/request IDs, JSON events, redaction, timings, bounded writer, shutdown flush | F01 | One traced fixture request; concurrent contexts stay separate; synthetic secrets redacted; write failure visible |
| F03 | Persistence foundation: DB connection, migrations, repositories, transaction helpers | F01–02 | Fresh DB upgrades repeatably; FK/unique/check constraints reject invalid data; no provider calls while holding write transactions |
| F04 | Corpus audit and extraction: version/checksum verification, page text and metadata | F01–03 | All three required versions verified; page provenance and extraction warnings stored; mismatch fails visibly |
| F05 | Recursive text splitting and indexes: token-counted RecursiveCharacterTextSplitter, immutable chunk IDs, embeddings, FAISS and BM25 artifacts | F04 | Repeatable manifest; page/offset mapping and tokenizer limits checked; corrupted index blocks readiness; old revision retained; semantic chunking deferred |
| F06 | Hybrid retrieval and cross-encoder reranking | F05 | Bounded candidates, RRF fusion/deduplication and reranked evidence; fixture questions produce inspectable source chunks; timings logged |
| F07 | Backend interface and controllable stand-in service | F01–02 | Common streaming/usage/error contract; deterministic fixture responses, delays, failures, 429s, worker queue slowdown and midstream interruption; initially uncalibrated |
| F08 | Shared model gateway: quota reservations, daily counters, concurrency, deadlines, transport retries | F03, F07 | Concurrent reservations cannot overspend; retry waits release call slots; deadlines/cancellation respected; unknown remote usage stays conservative |
| F09 | Real Groq adapter and modest calibration probe | F08 | GPT-OSS 120B content stream/usage/allowlisted headers recorded; account limits documented with provenance; small live sample saved; stand-in calibration gaps stated |
| F10 | Conditional input preparation | F08–09 | Clear query bypasses preparation; vague query refined once with intent preserved; missing referent yields clarification; malformed output falls back safely |
| F11 | Single-pass grounded RAG pipeline and citation checks | F06, F08–10 | Retrieve → rerank → one generation → release/refuse works; no evaluator or regeneration loop; unsupported fixture and invalid citation cases handled; semantic limitations documented |
| F12 | Local access and readiness integration | F03 | Loopback bindings, configured backend URL, no auth screens/endpoints, safe readiness errors and shared-history behaviour |
| F13 | Durable request API and resumable events | F11–12 | Idempotent submit, status/history, cancel, citation retrieval, cursor pagination, SSE replay and error contracts; cancellation/finalization race tested |
| F14 | Evaluation, scheduled load runner and reproducible exports | F09, F13 | At least 15 graded questions, three retrieval settings, five scenario rows, raw real/stand-in evidence; tables generated without invented metrics |
| F15 | Streamlit UI through FastAPI | F13 | F15a: question/progress/cited answer; F15b: clarification/cancel/paginated history; F15c: operator run views/downloads. Local-only access and rerun idempotency checked; real/stand-in source visible |
| F16 | Submission and reproducibility check | F14–15 | Clean setup/run instructions, two-page report with required headings/tables, source versions, raw evidence and assistant history; no secrets in deliverables |

F09 has a real-service prerequisite; F07–08 can be implemented and tested without consuming Groq quota. F15 is required by the user's product scope even though the assignment does not mandate a UI. Start F15a after F13; complete F15b/F15c in separate increments alongside the later experiment work. F14 remains mandatory and must not be displaced by UI polish. Fixture questions and evidence capture start earlier.

## Module boundaries

| Module | Owns | Must not own |
| --- | --- | --- |
| config | Validated settings and safe summaries | Printing credentials |
| telemetry | Correlation, redaction, event writing | Product decisions or inference |
| persistence | Schema, repositories, atomic state transitions | Slow remote calls inside transactions |
| ingestion | Version checks, PDF extraction, chunk/index manifests | Answer generation |
| retrieval / reranker | Local search, fusion, ranking, bounded evidence | Provider quota or authentication logic |
| backends | Groq/stand-in stream and error translation | Independent retries or bypassing gateway |
| gateway / budget | All model admission, reservations, retries and usage | Citation decisions |
| preparation | At most one initial refine/decompose/clarify decision | Answer scoring or post-answer rewrite |
| pipeline / validation | Stage orchestration, evidence-only draft, citation release/refusal | Raw provider access outside gateway |
| API | Local access, request validation and HTTP/SSE contracts | Duplicate pipeline implementation |
| experiments / reporting | Arrival schedules, grading, deterministic aggregation | Manufacturing measurements |
| Streamlit UI | Display, session-scoped API client, idempotent forms and progress polling | Provider secrets, direct Groq/DB access, globally cached authenticated clients |

## Next work item

**Next: F04 corpus audit/extraction acceptance review.** Preserve the existing index; verify extraction warnings and durable page metadata before marking F04 complete. No additional feature has been started. Fixed-question grading and load experiments remain later work.

### F01–F03 completion evidence

| Feature | Status | Changed-file evidence | Checks and limitations |
| --- | --- | --- | --- |
| F01 | Done | src/relay/config.py; tests/test_config.py; existing package/manifest/config examples | Import/test discovery, secret masking, invalid limits/backend/URL rejection and hosted-key requirement pass. Missing key remains allowed for offline operations. Existing .env and PDFs were not edited. |
| F02 | Done — infrastructure | src/relay/telemetry.py; store.py; api.py; cli.py; tests/test_telemetry.py | Versioned correlated events, timed spans, thread/async context separation, central nested redaction, bounded QueueHandler, non-overwriting rotation, explicit overflow/disk failure and graceful flush tested. API/CLI integrate it. Complete later-module event instrumentation, durable outbox delivery, retention and measured overhead remain later work; no full benchmark capture is claimed. |
| F03 | Done — foundation | src/relay/migrations.py; store.py; cli.py; api.py; scripts/inspect_generation.py; tests/test_migrations.py; test_store.py; test_api.py | Fresh/repeat/legacy upgrade, verified backup, rollback, FK/unique/CHECK enforcement, terminal protection and concurrent reservations tested. Runtime database upgraded to schema 2 with rows preserved. Uses sqlite3 numbered migrations rather than the earlier proposed ORM stack; design documents updated. Rich corpus/evaluation/state contracts remain later features. |

No current blocker for F01–F03. API server startup was not repeated in this cycle; API lifespan and admission were exercised by fixture integration tests. The previous cycle's automatic-approval usage-limit error affected its server restart, not the current foundation verification.

The user explicitly requested a runnable initial version and real measurements in this work cycle. Full contract milestones remain partial where the README lists simplifications. No feature is marked complete solely because a file exists.

## Decisions and unresolved points

- Initial chunker implemented: recursive splitting with embedding-token-counted size 200 and target overlap 30, preserving pages. This supersedes the earlier 300/50 proposal because of the chosen embedding window. Other strategies remain later controlled experiments.

- Use existing PRD/API/DB contracts: hybrid BM25 + vector retrieval, cross-encoder reranker, optional input refinement, single generation, citation checks; no corrective loop.
- No sign-in or accounts. Streamlit and FastAPI form a single local demo with shared history; SQLite and one backend process remain the initial deployment.
- Groq availability verified by three successful probes. Headers report 1,000 requests/day and 8,000 tokens/minute; RPM, TPD, concurrency and enforced recovery behaviour remain unmeasured.
- Paper version markers verified: Attention v7 (15 pages), Dynamic Chunking v2 (39 pages), Moshi v1 (66 pages). Actual baseline is 200 embedding-token chunks with 30 target overlap due to model input limits.
- Resolve CSV-only versus supplementary evidence needs before final reporting; base CSV fields cannot independently encode every requested statistic.
- Confirm the deadline from the actual submission instructions. November 14, 2026 is Saturday, two calendar days after November 12; the earlier 8:14 a.m. time was tentative.
- UI framework: Streamlit calling FastAPI. Initial UI implemented; no sign-in.

## Verification ledger

| Date | Scope | Check | Result |
| --- | --- | --- | --- |
| 2026-11-12 | F01–F03 final regression | `.venv/Scripts/python.exe -m pytest -q` with loopback permission | 24 passed in 2.44 s; tests use fixtures, no hosted calls |
| 2026-11-12 | F03 runtime upgrade | `relay.cli migrate`, repeated upgrade and comparison with pre-v2 backup | Schema 2; integrity/FK checks pass; request/call/event row counts preserved |
| 2026-11-12 | F01 configuration | `relay.cli check` | Key presence and index presence true; no secret output |
| 2026-11-12 | First-version tests | `.venv/Scripts/python.exe -m pytest -q` with loopback permission | 12 passed in 1.87 s; includes API replay/validation, store quotas, citation gates and stand-in streaming/429/midstream error |
| 2026-11-12 | Corpus | `.venv/Scripts/python.exe -m relay.cli ingest` | Exact version markers found; 600 chunks; normalized local embeddings and FAISS/BM25 artifacts built |
| 2026-11-12 | Live Groq | `.venv/Scripts/python.exe -m relay.cli probe --count 3` | 3/3 success; total times 15999.5, 790.2, 829.6 ms; small generic prompt only |
| 2026-11-12 | Calibration | `relay.cli calibrate --observations runtime/probes/20261112T135123Z/observations.json` | Empirical first-delay/tail samples saved; n=3, not representative of full RAG/provider load |
| 2026-11-12 | Service health | GET API /health/ready and UI /_stcore/health | Both HTTP 200 on ports 8000/8501 |
| 2026-11-12 | Initial inventory | Enumerated top-level files and searched for application source/config manifests | Three design documents, data/ and .env present; no Python application or dependency manifest found |
| 2026-11-12 | Streamlit documentation alignment | Reviewed PRD/API/DB/tracker UI references and official Streamlit session/fragment docs | UI framework, auth boundary, polling and rerun behaviour specified; no implementation tests claimed |
| 2026-11-12 | User/data flows and edge-case coverage | Reviewed PRD headings and added sections 18–20 against existing API/DB/UI decisions | Eight user flows, five data-flow sections and 36 edge cases mapped to features; planned acceptance checks, not executed application tests |

Add feature-specific executed checks here; planned checks belong in the backlog until run.

## Change log

| Date | Change | Implementation impact |
| --- | --- | --- |
| 2026-11-12 | Initialized Git, configured origin/main/dev and documented ongoing commit/push workflow in AGENTS.md | Reviewed 32 staged project files; configured Groq key absent; .env, caches, virtual environment and runtime evidence excluded; no product behaviour change |
| 2026-11-12 | Audited/completed F01–F03; added telemetry.py and migrations.py, tightened config, wired API/CLI, added regression tests; aligned PRD/API/DB/README | F01–F03 Done; 24 passing tests; runtime schema 2 with verified backup; no new model calls; remaining milestones unchanged |
| 2026-11-12 | Implemented src/relay, ui/app.py, tests, pyproject.toml, README and local index/probe evidence | F01 complete; working first-version modules with documented gaps; no fabricated benchmark tables |
| 2026-11-12 | Created modular backlog, status tracker and project workflow rule | Documentation only; F01 is next |
| 2026-11-12 | Updated PRODUCT_REQUIREMENTS.md, API_DESIGN.md, DATABASE_DESIGN.md and this tracker for Streamlit | Documentation only; F15 split into reviewable UI increments; F01 remains next; 0/16 implementation milestones complete |
| 2026-11-12 | Expanded PRODUCT_REQUIREMENTS.md with U01–U08, D01–D05 and E01–E36 coverage; updated this tracker | Documentation only; feature verification should reference applicable flow/case IDs; F01 remains next |

| 2026-11-12 | Removed sign-in/account/session requirements across PRD, API and DB designs; replaced F12 with local access checks; added latency targets and chunking decision | Documentation only; F01 remains next; no benchmarks claimed |
| 2026-11-12 | Selected recursive splitter baseline; researched later chunking alternatives and defined controlled comparison in PRD | Documentation only; F05 clarified; no implementation or measured improvement claimed |
