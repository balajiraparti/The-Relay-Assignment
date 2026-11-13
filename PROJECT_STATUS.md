# The Relay — project status and incremental build plan

Last reviewed: November 13, 2026 (F04–F08 work began November 12).

## Current state

**Golden dataset v2 preparation: Done (artifact remains an author-review draft).** Updated all 18 questions, preserved the author's wording and original expectations, added reference evidence and grading criteria. No retrieval, chunking, provider or runner code changed; v1 and previous measurements are unchanged. V2 has not been executed. Next task: author review of labels/ambiguity policy, then a separately authorized implementation cycle for section-aware chunking and fixed hybrid/reranked comparisons.

**Reproducibility:** the runner uses `data/evaluation_questions.v1.json`, verified byte-for-byte against the actual 15-question run SHA. The author's subsequent Q16–Q18 additions are now incorporated into the separate v2 working dataset with original wording retained. Packaging reads committed blobs only. Draft PR: https://github.com/balajiraparti/The-Relay-Assignment/pull/1. Existing packaged reports still describe v1; they were not regenerated for this unexecuted dataset.

**Active cycle: F13–F16 (November 13).** F13 and F15 implemented and verified; F14 experiment execution/export implemented with author grade verification pending; F16 report/package implementation with final author feedback/reflection pending. The user explicitly authorized all four milestones and asked to leave Vaani feedback until the end. No user opinion is invented.

Version control: Git initialized with origin https://github.com/balajiraparti/The-Relay-Assignment.git. Main holds baseline f775d3b; dev contains project import b554b4a, successfully pushed to GitHub. Future important completed features are committed and pushed on dev after checks. Pull-request merges remain separate. Secrets and generated runtime artifacts are excluded. This setup does not complete another product milestone.

**Phase: F01–F13 and F15 complete within their documented implementation scope; F14/F16 await final evidence/author review. Overall submission is not yet final.** Product/package version remains 0.1.0; database schema is 4. See this cycle's verification below; earlier three-call evidence remains historical, separate from the new evaluation.

Workspace now contains the Python package under src/relay, Streamlit UI, tests, README, dependency manifest and runtime evidence. Original PDFs and .env have been preserved. Version markers in all three PDFs matched the brief; SHA-256 checksums were recorded. Groq key presence and three successful real calls were verified without printing the key.

| Area | State | Evidence / remaining work |
| --- | --- | --- |
| Product and architecture | Documented | PRODUCT_REQUIREMENTS.md |
| API contracts | F13 implemented | Atomic SSE replay, signed pagination, clarification parents, citations/pages, run views/exports; exact scope and deferred retention in API_DESIGN.md |
| Database design | Schema 4 verified | Transactional public events and terminal uniqueness; immutable corpus/evaluation artifacts deliberately remain files |
| Source PDFs | Audited and durably extracted | Exact version markers and pinned data/corpus.lock.json hashes; 120 pages, 600 recursive chunks; full page text and warnings retained in immutable artifacts |
| Local configuration | Verified for controlled evaluation | 32 hosted completions in the new run; key never printed; 10 local quota refusals and 3 no-call clarifications retained |
| Backend, retrieval and model integration | Partial first version verified | Real paper answer with two citations recorded in FIRST_RUN_RESULTS.md; broader quality grading pending |
| Persistence | F03 foundation complete | Constraints, migration rollback, preserved legacy data and concurrent quota reservations tested |
| Stand-in, logging and experiments | Executed; author grading review pending | 100 selected synthetic arrivals plus 45 real-pipeline arrivals; raw data/grades/tables retained; real upstream 429/recovery not measured |
| UI | F15 verified and running | Streamlit interaction checks and live health/API replay/citation/page/download checks passed on ports 8501/8000 |
| Build tracking | Complete | This file and AGENTS.md |

**Completed implementation milestones: F01–F13 and F15 (14 of 16); F14/F16 implemented with review gaps.** The latest full suite has 93 passing tests; a subsequent focused suite has 28 passes. This count is not an effort percentage. The new evaluation retains wrong answers, false refusals and local quota rejections rather than excluding them.

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

Current milestone states: F01–F13 Done; F14 Implemented — author verification pending; F15 Done; F16 Implemented — final author content/package review pending. The table preserves full acceptance criteria.

| ID | Feature / boundary | Dependencies | Acceptance / demonstrable output |
| --- | --- | --- | --- |
| F01 | Project skeleton and safe configuration: package layout, dependency manifest, test runner, .gitignore, .env.example, config loader | None | Package imports; configuration validates missing/invalid values without printing secrets; test discovery works; existing .env preserved |
| F02 | Structured telemetry: run/request IDs, JSON events, redaction, timings, bounded writer, shutdown flush | F01 | One traced fixture request; concurrent contexts stay separate; synthetic secrets redacted; write failure visible |
| F03 | Persistence foundation: DB connection, migrations, repositories, transaction helpers | F01–02 | Fresh DB upgrades repeatably; FK/unique/check constraints reject invalid data; no provider calls while holding write transactions |
| F04 | Corpus audit and extraction: version/checksum verification, page text and metadata | F01–03 | All three required versions verified; page provenance and extraction warnings stored; mismatch fails visibly |
| F05 | Recursive text splitting and indexes: token-counted RecursiveCharacterTextSplitter, immutable chunk IDs, embeddings, FAISS and BM25 artifacts | fF04 | Repeatable manifest; page/offset mapping and tokenizer limits checked; corrupted index blocks readiness; old revision retained; semantic chunking deferred |
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

**Current next task:** verify provisional grades against the 15 fixed questions and cited PDFs, then supply the author's Vaani website feedback and approve the assistant reflection. The original brief was recovered from its conversation attachment; all exact headings are in the two-page report generator. F14 also explicitly lacks a real upstream 429/recovery observation. The local gateway was not disabled to manufacture one. Full fresh-machine dependency/model download has not been executed; pinned dependencies pass compatibility checks. These are genuine limitations, not completed live integrations.

### F13–F16 changed-file and verification evidence

- **F13:** `migrations.py`, `store.py`, `pagination.py`, `api.py`, `pipeline.py`; atomic public events, unique terminal done, signed snapshot/filter cursors, citation/page endpoints, safe errors and local/provider status distinction. `test_public_events.py` exercises 20 cancel/finalize races and transactional rollback; API tests replay without inference, malformed input and cursors. U01/U03/U04/U05/U06; E23–E27. Automatic retention and broad diagnostic outbox remain deferred in API/DB contracts.
- **F14:** `experiments.py`, `load_experiments.py`, frozen `data/evaluation_questions.json`, exact-column export, explicit offline `grade_run.py`, `collect_evidence.py`, `report_tables.py`. Seven selected stand-in runs cover the five required scenarios and controlled retry comparison; first random retry trials remain in runtime and were not used to claim an effect. Model results/grades and manifests are separate. Unknown token usage and capacity outcomes are preserved. Small samples, simultaneous local synthetic/real activity, and a single fixed chunk size limit inference.
- **F15:** `ui/app.py`, `tests/test_ui.py`; clarification parent, polling stops on terminal outcome, paginated history, source/usage display, operator run list/detail/stop/download, understandable capacity states. Executed Streamlit AppTest proves form rerun idempotency, ambiguous-response key reuse and clarification/history controls. This is interaction-test evidence, not a browser latency benchmark.
- **F16:** `requirements.lock.txt`, `docs/SUBMISSION_CHECKLIST.md`, verbatim user-message snapshot `docs/assistant-prompts.json`, report/table/package scripts, curated `evidence/` and `output/pdf/`. Two-page PDF rendered and visually inspected; report is explicitly an author-review draft. The user requested Vaani feedback be deferred to the end. Prompt export is a bounded snapshot, not a fictional complete final-turn transcript.

The following readiness-audit notes describe the prior milestone, not the current next action:

**Readiness audit complete (November 13).** Logger and Groq are verified for controlled probes. F09 measurement hardening now records explicit successful upstream status, disables probe retries and separates local/provider errors. One real call returned 200 with 660.9 ms TTFT, 799.9 ms total and 82/26 tokens; matching JSONL was verified. No real 429 or recovery was measured. The full percentile/recovery runner remains F14 work. User priority: collect real evidence before further stand-in calibration; see docs/REAL_SERVICE_READINESS.md.

**Next proposed priority: a bounded real-service measurement runner before further stand-in calibration.** This readiness audit did not implement the full F14 runner. F13 durable request API/resumable events and the remaining F14–F16 work stay pending. Earlier API readiness/UI-render checks do not imply full UI flows or ongoing provider availability.

### F09–F12 completion evidence

| Feature | Evidence | Verified scope / remaining limitations |
| --- | --- | --- |
| F09 | backends.py, calibration.py, cli.py, test_provider.py, docs/GROQ_LIMITS.md | Current live generic probe succeeded (996.8 ms); content-only stream, usage and allowlisted headers recorded. Original three-sample calibration validated with SHA-256 provenance. Published/observed quotas separated; actual RPM/TPD, sublimits, reset algorithm and high-load behaviour remain unknown. |
| F10 | preparation.py, test_preparation.py, pipeline tests | Clear/off/busy bypass; missing-referent clarification; one bounded rewrite; prefix-only conservative intent guard; malformed/timeout/fault fallback. Original question retained for reranking/generation. No general semantic rewrite/decomposition claim. |
| F11 | pipeline.py, store.py, test_pipeline.py, scripts/verify_live_rag.py | Single generation with JSON mode; sentence citation gates; safe refusal; all-attempt usage totals; cancelled retrieval retains worker capacity until completion. Live cited answer passed format checks; semantic overstatement documented rather than hidden or scored as correct. |
| F12 | local_access.py, api.py, config.py, cli.py, ui/app.py, API tests | Loopback launcher; peer/Host/Origin/body checks; safe readiness; validated UI backend origin; no sign-in; shared local history. Real readiness 200 and Streamlit rendering passed. No public deployment or full browser validation. |

See docs/F09_F12_VERIFICATION.md for measured successes/failures and evidence paths. Raw runtime/evaluation artifacts remain local and ignored by Git. No blocker remains for these four scoped milestones; F14 must measure semantic correctness and preserve the known novelty-overstatement example.

### F04–F08 completion evidence

Final verification: 54 tests passed in 16.95 s. Two final independent builds returned revision 532f423d5a5967b8 with 600 chunks and valid page offsets; all nine offline expected-paper/retrieval-setting smoke checks passed using real cached local models. Full extracted pages and weight/tokenizer fingerprints are retained. Extraction found zero empty/sparse/replacement-character warnings; scientific reading order still requires grading. No Groq requests were made.

| Feature | Changed-file evidence | Scope and limitations |
| --- | --- | --- |
| F04 | extraction.py, data/corpus.lock.json, CLI audit, test_corpus.py | Checks exact file set, pinned hashes and version markers; stores pages and extraction warnings. No OCR or reconstruction of tables/equations; warning-free extraction is not proof of layout correctness. |
| F05 | corpus.py, test_corpus.py, scripts/verify_index_build.py | Exact source spans; final token caps; tokenizer/loaded-weight fingerprints; canonical manifests; checksums before FAISS loading; atomic publication; old revisions retained. Full page/corpus metadata uses immutable JSON artifacts rather than duplicate SQLite rows. |
| F06 | corpus.py, pipeline.py, scripts/verify_retrieval.py | 12 lexical/12 dense candidates, top-16 RRF, top-5/6 cross-encoder evidence; original-question reranking, deterministic ties, bounded input checks and correlated diagnostics. Nine expected-paper smoke checks are not manual evidence/answer grading. |
| F07 | backends.py, standin.py, test_standin.py, test_gateway_http.py, docs/standin.context.yaml | One streamed event contract; isolated seeded profiles; worker/queue limits; load delay; quota/503/midstream faults; optional empirical latency profile. Fault tests use synthetic settings and real loopback HTTP, not Groq or a Postman deployment. |
| F08 | gateway.py, store.py, migrations.py, config.py, pipeline.py, gateway/store/pipeline tests | Shared bounded call admission, cumulative waiting and total deadline, maximum three transport attempts, no retries after content, backoff outside slots, persisted source-specific cooldown and rolling budgets, conservative crash/cancel accounting. Exact provider reset reconciliation and real concurrency limits remain F09 evidence work. |

Remaining scope boundaries: the eight-second gateway wait budget is per logical call; end-to-end dispatcher admission/fairness belongs to F13/F14. CPU extraction/retrieval jobs are not forcibly terminated by cancelling their awaiting coroutine. Complete benchmark capture/quality grading and API SSE replay remain pending.

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
| 2026-11-13 | Real-service readiness audit | Focused telemetry/provider/gateway tests; `relay.cli probe --count 1`; correlate observation and JSONL by request ID | 21 tests passed in 6.80 s; real HTTP 200, TTFT 660.9 ms, total 799.9 ms, 82/26 tokens, zero retries; no 429/recovery evidence; larger percentile run not executed |
| 2026-11-13 | F09–F12 regression | `.venv/Scripts/python.exe -m pytest -q` with loopback permission | 82 passed in 14.04 s; preparation, sentence citation/refusal, usage, Groq envelope and local-readiness checks plus prior regressions |
| 2026-11-13 | F09 live probe/calibration | `relay.cli probe --count 1`; regenerate profile from original observations | 996.8 ms total, 974.2 ms first content, 82/42 tokens; old n=3 calibration retains paired delays plus source hash; no percentile claims |
| 2026-11-13 | F11 real pipeline | CLI ask then explicit live evaluation after JSON-mode code change | First run refused invalid schema (14537.9 ms); separate revised run passed citation format (1967.6 ms, 1238/185 tokens); novelty overstatement retained for grading |
| 2026-11-13 | F12 integration | `relay.cli serve`, HTTP readiness, Streamlit AppTest | Readiness 200, correct index/source and connectivity-not-probed label; UI render without exceptions |
| 2026-11-12 | F04–F08 regression | `.venv/Scripts/python.exe -m pytest -q` with loopback permission | 54 passed in 16.95 s; includes 13 real loopback HTTP scenarios plus parser/unit/integration checks; no Groq calls |
| 2026-11-12 | F04–F05 real corpus/reproducibility | `HF_HUB_OFFLINE=1` then `scripts/verify_index_build.py` | Two matching builds: 532f423d5a5967b8; 120 pages, 600 chunks; valid source spans; pinned source/tokenizer/weight/artifact hashes; old indexes retained; runtime/verification/index_build.json |
| 2026-11-12 | F06 actual local models | `HF_HUB_OFFLINE=1` then `scripts/verify_retrieval.py` | 9/9 expected-paper and bounded-evidence checks across R1/R2/R3; runtime/verification/retrieval.json; not a quality benchmark |
| 2026-11-12 | F08 durable state | `relay.cli migrate` and existing-history check | Schema 3 applied after verified backup; all five existing requests retained; cooldown/recovery/day-budget tests pass |
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

### November 13 — golden dataset v2 only

Changed: `data/evaluation_questions.json`, `data/evaluation_questions.manifest.json`, `data/GOLDEN_DATASET.md`, PRD, DB design and tracker. Q16 covers corpus scope, Q17 adversarial credential disclosure, Q18 a scoped two-paper comparison or warranted clarification. No runtime changes or hosted calls. Proposed future section-aware 300/3, 500/4, 800/5 comparisons share hybrid retrieval and reranking; overlap/model capacities remain open.

Verification actually executed: read-only Python validation checked 18 unique IDs, exact preservation of all author questions/expectations, required fields, 16 exact page-text locators, the three pinned PDF hashes, dataset SHA, null grades/unexecuted states, Q17/Q18 policies and byte-identical v1 versus Git. All passed. Source references are extraction-checked, not independently human-verified; out-of-scope labels and Q18 alternatives require author review. No app test rerun was needed for this dataset/documentation-only change. This does not close the existing real concurrency/429/recovery or final author-review gaps.

### November 13 F13–F16 verification ledger supplement

| Check actually executed | Result | Limitation |
| --- | --- | --- |
| Full `pytest -q` after API/export/UI implementation | 93 passed in 14.54 s | Fixture/local HTTP tests do not establish hosted quality |
| Focused pipeline/UI/API suite after final capacity/status messages | 28 passed in 11.71 s | No new hosted calls |
| `relay.experiments quality --interval 30` | 45 arrivals, 15 questions x 3 settings; 32 hosted completions, 10 local quota rejections, 3 no-call clarifications | 35 provisional assistant-reviewed completed outputs; independent author hand-verification pending; no real 429/recovery |
| `relay.experiments load` plus explicit retry comparison | Five required load scenarios and controlled one/three-attempt comparison; 100 selected arrivals | Tiny bootstrap calibration, synthetic evidence/retrieval; load-dependent parameters not calibrated; earlier no-retry comparison retained in runtime |
| `scripts/verify_submission.py` | 145 unique exact-column CSV rows match raw records; all hashes valid; tables regenerate byte-for-byte; PDF has two pages | Author-review draft; raw runtime artifacts remain untracked; curated secret-checked evidence is intentional |
| PDF render + visual inspection | Both pages inspected, no clipping/overlap | Dense two-page assignment format |
| `uv --cache-dir .cache/uv pip check --python .venv/Scripts/python.exe` | All 97 installed packages compatible; 96 dependencies pinned excluding editable project | Clean-machine downloads/setup not executed |
| Live API/UI checks | Ready 200, Streamlit health 200; no-call clarification; SSE exactly one done; retained citation/page and completed CSV endpoints 200 | Browser delivery latency not measured; no additional Groq requests |

Changed-file evidence: API/DB/PRD/README contracts, `src/relay/{api,store,migrations,pagination,experiments,load_experiments,pipeline}.py`, `ui/app.py`, tests, frozen questions/review/selection, reporting/packaging scripts, lockfile, curated evidence, two-page report and verbatim prompt snapshot. F13/F15 Done; F14/F16 remain implemented with the author-review and measurement gaps listed above. Next action: review grades/reflection and add the deferred Vaani feedback; do not claim a final submission until then.

| Date | Change | Implementation impact |
| --- | --- | --- |
| 2026-11-13 | Hardened probe measurement metadata and explicit upstream status; verified live JSONL; added real-service readiness report and experiment prerequisites | F09 follow-up only; no additional milestone completed, no stand-in changes or percentile claims; future calibration follows real observations |
| 2026-11-13 | Completed F09–F12 with validated calibration, bounded preparation, sentence citation gate/JSON mode, aggregate usage and local readiness; aligned PRD/API/DB/README and evidence reports | F01–F12 Done; 82 tests pass; three hosted checks with failure retained; F13 next; no corrective loop or authentication |
| 2026-11-12 | Completed F04–F08: audited corpus lock/pages, immutable checked indexes, retrieval diagnostics, backend event adapter, isolated stand-in, bounded gateway and schema-3 cooldowns; updated PRD/API/DB/README/examples | F01–F08 Done; 54 tests pass; real local corpus/model checks pass; no hosted load or fabricated results; F09 is next |
| 2026-11-12 | Initialized Git, configured origin/main/dev and documented ongoing commit/push workflow in AGENTS.md | Reviewed 32 staged project files; configured Groq key absent; .env, caches, virtual environment and runtime evidence excluded; no product behaviour change |
| 2026-11-12 | Audited/completed F01–F03; added telemetry.py and migrations.py, tightened config, wired API/CLI, added regression tests; aligned PRD/API/DB/README | F01–F03 Done; 24 passing tests; runtime schema 2 with verified backup; no new model calls; remaining milestones unchanged |
| 2026-11-12 | Implemented src/relay, ui/app.py, tests, pyproject.toml, README and local index/probe evidence | F01 complete; working first-version modules with documented gaps; no fabricated benchmark tables |
| 2026-11-12 | Created modular backlog, status tracker and project workflow rule | Documentation only; F01 is next |
| 2026-11-12 | Updated PRODUCT_REQUIREMENTS.md, API_DESIGN.md, DATABASE_DESIGN.md and this tracker for Streamlit | Documentation only; F15 split into reviewable UI increments; F01 remains next; 0/16 implementation milestones complete |
| 2026-11-12 | Expanded PRODUCT_REQUIREMENTS.md with U01–U08, D01–D05 and E01–E36 coverage; updated this tracker | Documentation only; feature verification should reference applicable flow/case IDs; F01 remains next |

| 2026-11-12 | Removed sign-in/account/session requirements across PRD, API and DB designs; replaced F12 with local access checks; added latency targets and chunking decision | Documentation only; F01 remains next; no benchmarks claimed |
| 2026-11-12 | Selected recursive splitter baseline; researched later chunking alternatives and defined controlled comparison in PRD | Documentation only; F05 clarified; no implementation or measured improvement claimed |
