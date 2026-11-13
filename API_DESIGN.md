# The Relay API design

## F13–F16 implemented contract (November 13, 2026)

This section supersedes conflicting aspirational details below. The local API has no authentication. Requests retain the existing nested `result` response for compatibility; `body` contains question/settings/optional clarification parent and pinned source/model/index, and `updated_at` is added. Timestamps in request resources remain Unix seconds; experiment CSV timestamps are UTC ISO-8601. Chunk IDs are 20 hexadecimal characters, index revisions 16, request/run IDs UUIDs.

Schema 4 atomically writes state plus public events in the same transaction. `done` is unique per request; cancellation and finalization use first-terminal-wins. SSE replays durable, sanitized status/validated-answer/citation-ID/clarification/error/done events; Last-Event-ID must belong to that request. Heartbeats have no IDs. Old terminal requests receive a migration `done` event; their complete answers remain available through GET. Events are retained without automatic expiry in this assignment version. No draft or reasoning is published. A disconnected subscriber never cancels inference.

History supports `limit`, signed one-hour `cursor`, and `status` (filter-bound, snapshot cutoff, keyset ordering). Papers, runs and run events are paginated. Citation lookup accepts optional `revision` for retained immutable indexes. Paper metadata/page text, settings, local quota snapshot, run details/stop/results.csv/events are implemented. Run creation stays CLI-only. Run stop stops future arrivals and lets already active work finish. There is no request-history `run_id` filter; use the run detail/export. Run events provide sanitized request summaries or provider simulation events, not arbitrary log searching. Unknown query fields fail 422.

Validation errors omit input values. Missing resources return 404; malformed JSON 400; unknown fields 422; incompatible body media type 415; conflicting idempotency body 409. Completed/ungraded runs require `allow_incomplete=true` and return an explicitly named incomplete CSV; active runs always return 409. Required CSV columns remain exact; nullable measurements/grades are empty cells with reasons in raw JSON/manifest. `X-Request-ID` identifies HTTP operations, distinct from the durable RAG ID. Idempotency keys and request content are retained indefinitely locally; automatic purge/410 expiry are deferred, not claimed.

The stand-in's implemented internal endpoint is `/v1/chat/completions` on a loopback-only listener, with no extra secret and no Groq credentials forwarded. Profiles are startup-only. This supersedes the earlier proposed `/internal/completions` secret scheme. One active API process is supported; do not run multiple web workers. Experiment processes share the persistent real quota ledger, but process-local concurrency semaphores are not a distributed dispatcher: run hosted experiments without interactive hosted traffic for controlled comparisons.

Status: implementation contract draft, November 12, 2026. Source: [PRD](PRODUCT_REQUIREMENTS.md). Storage contract: [Database design](DATABASE_DESIGN.md). No separate system-design file exists yet. All examples are illustrative, not measured runs.

## 1. Scope and decisions

FastAPI, one application process, a bounded async dispatcher, SQLite persistence, local retrieval/index artifacts, and Groq GPT-OSS 120B. One optional initial refinement/planning call and one answer-generation pass; no evaluator or corrective loop. Network retries remain bounded. Browser search and arbitrary paper uploads are unavailable.

The local UI is Streamlit and calls FastAPI over HTTP. The assignment demo has no accounts, sign-in, cookies, passwords or authentication endpoints. Bind both services to loopback. History is shared within this local instance; this is not a multi-user/private-history design. Public hosting requires a separate design decision.

## 2. HTTP conventions

- Base path `/v1`; UTF-8 JSON, `Content-Type: application/json` for JSON writes. Reject unsupported types with 415, malformed JSON with 400, bodies above 16 KiB with 413, and unknown JSON fields with 422.
- UUID resource identifiers; UTC RFC3339 timestamps; durations in milliseconds. Use null for unknown/unmeasured data, not zero. Zero means measured zero.
- Generate `X-Request-ID` per HTTP operation. The returned RAG resource ID is the correlation ID across its whole pipeline, distinct from subsequent HTTP operations.
- Responses containing questions, answers, or credentials use `Cache-Control: no-store`. Escape text in the UI; never render model HTML or execute document instructions.
- Validate resource IDs and inputs before access. Missing resources return 404. Use parameterized SQL and allowlisted filters/sort names.
- Runtime FastAPI schemas must generate `/openapi.json` and `/docs` matching this contract; these are local/local in the demo. No implementation or generated OpenAPI is claimed by this document.

## 3. Local access model

No login/logout/me endpoints, user accounts, session cookies, password hashes or CSRF tokens. Streamlit uses a server-side HTTP client to the loopback FastAPI service. Use a configured backend URL; users cannot supply arbitrary destinations. Keep Groq credentials exclusively in the backend. Streamlit retains only UI state, active request IDs and idempotency keys. No authentication prerequisite applies to the endpoints below. Do not enable unrestricted browser CORS or expose these services publicly; this deployment boundary is not a substitute for authentication on a public service.

## 4. Endpoint catalogue

F12 implementation update (November 13): `relay.cli serve` binds 127.0.0.1:8000 and disables proxy-header trust. Middleware verifies the actual peer plus Host/Origin and caps POST bodies while reading. Streamlit validates its backend origin and ignores environment proxies. Safe 503 readiness reasons are database_unavailable, provider_not_configured, index_or_models_unavailable and telemetry_unavailable. A ready response exposes the pinned index and explicitly states provider_connectivity=not_probed. No accounts/authentication were added; history belongs to the single local instance. Request result usage includes all persisted attempts, nullable totals, known subtotals and unknown_usage_calls. Public SSE/replay remains F13.

F04–F08 update: readiness loads only a validated schema-2 index manifest and checks all artifact hashes before model loading. Reingest old indexes. The shared gateway has separate bounded concurrency/queue admission, cumulative slot/backoff waiting and total model-call deadlines. A gateway deadline maps to timed_out; local/remote quota failures map to rate_limited. Stand-in selection is explicit; there is no automatic real-to-synthetic fallback. The provider streaming event contract is in backends.py; public API SSE/replay remains F13 work.

Foundation implementation note (November 12): run `relay.cli migrate` before API startup. Schema mismatch prevents startup. Required telemetry queue/writer failure stops new request admission with HTTP 503 (`telemetry_unavailable`); the writer emits a minimal stderr warning and an incomplete marker when storage permits. These operational checks add no login or authentication endpoints. The complete endpoint/state catalogue below remains a target beyond F01–F03.

All `/v1` endpoints are available to the local demo. Diagnostic/run actions are local tooling, not role-protected operations. Unknown filters return 422.

| Method/path | Purpose and request | Success | Important checks/errors |
| --- | --- | --- | --- |
| GET `/capabilities` | UI configuration | 200 model ID, allowed settings, library revision, refinement support, backend source | No keys or unrestricted config |
| POST `/requests` | Submit question; details below | 202 accepted with Location | 409 key conflict; 422 invalid fields; 429 admission/quota; 503 index unavailable |
| GET `/requests` | History: cursor, limit, status, run_id | 200 paginated summaries | invalid cursor 400 |
| GET `/requests/{id}` | Current state or final answer | 200 request resource | 404, 410 content expired |
| GET `/requests/{id}/events` | SSE, optional Last-Event-ID | 200 text/event-stream | 400 cursor invalid; 410 replay expired |
| POST `/requests/{id}/cancel` | Empty body | 200 current resource | 404; repeated or completed cancellation returns unchanged resource |
| GET `/papers` | Fixed paper library, cursor/limit | 200 paginated papers | Only pinned versions |
| GET `/papers/{id}` | Metadata | 200 title, arXiv ID/version, checksum, page count | 404 |
| GET `/papers/{id}/pages/{page}` | Extracted text for source viewer | 200 page text/metadata | Positive 1-based PDF page; 404 page absent |
| GET `/chunks/{id}` | Citation detail | 200 text, paper, revision, page/section | Only published/retained library revisions |
| GET `/retrieval-settings` | Immutable R1/R2/R3 versions | 200 settings list | No arbitrary runtime overrides |
| GET `/quota` | Local diagnostic snapshot | 200 observed/estimated limits, as_of, reset and pending reservations | Unknown fields null; no promise of exact upstream allowance |
| GET `/runs` | Local experiment history, cursor/limit | 200 paginated runs | Optional source/state filters |
| GET `/runs/{id}` | Local manifest and counts | 200 safe immutable configuration and current state | 404 |
| POST `/runs/{id}/stop` | Local empty body | 200 stop_requested/current terminal run | Stop new scheduled arrivals; active work drains to deadlines |
| GET `/runs/{id}/results.csv` | Local export | 200 CSV attachment | 409 run active, incomplete or ungraded; allow `allow_incomplete=true` only with explicitly marked incomplete export |
| GET `/runs/{id}/events` | Local trace inspection with cursor/limit, request_id, level | 200 paginated sanitized events | Never returns raw credentials or reasoning |

Run creation, ingestion, schema migration and provider quota configuration are local CLI operations in MVP. There is no public endpoint to launch heavy load, change the provider, or overwrite the library. A future dashboard can display runs and request cancellation using the contracts above.

`GET /health/live` returns only 200 `{ "status":"alive" }`. `GET /health/ready` is local, returns 200 when DB, index, writer and configuration are usable, otherwise 503. Neither performs billable provider calls; exhausted quota is a capacity condition, not necessarily failed readiness.

## 5. Submit, validate and deduplicate

Required `Idempotency-Key`: 16–128 printable ASCII characters, scoped to the local application and endpoint. Store canonical validated-body hash and response association atomically for 24 hours. Same key/body returns the same resource/status with `Idempotent-Replayed: true` and no new model call; same key/different body returns 409. Retain keys through resource lifetime if active past 24 hours. Store admission rejection results too. Validation errors before admission do not allocate a model request.

```json
{"question":"How does Moshi support simultaneous listening and speaking?","retrieval_setting":"R2","refinement":"auto","parent_request_id":null}
```

- `question`: trimmed, 1–4,000 Unicode characters; reject empty/whitespace, NUL and unsupported control characters. Preserve meaningful punctuation, negation and equations. Enforce total body byte limit separately.
- `retrieval_setting`: R1/R2/R3, default R2; resolve and pin an immutable version at admission.
- `refinement`: `auto` or `off`, default auto. Missing intent can still produce clarification when off.
- `parent_request_id`: optional UUID in `needs_clarification`. New question must be self-contained; this creates a new request, never resurrects or modifies the parent or adds general chat memory.
- Backend source, model, prompt, arbitrary tool URLs and token budgets are server controlled. All client attempts to supply them fail validation.
- Admission pins a ready index revision, checks bounded queue and budgets, stores the request and queues it in one coordinated operation. Defaults: ten queued requests, two active provider calls; eight-second maximum waiting budget and proposed 45-second total request deadline. These are configurable targets, not measured SLOs.

```json
{"id":"22222222-2222-4222-8222-222222222222","status":"queued","created_at":"2026-11-12T10:00:00Z","links":{"self":"/v1/requests/22222222-2222-4222-8222-222222222222","events":"/v1/requests/22222222-2222-4222-8222-222222222222/events"}}
```

Creation's 202 means accepted for processing, not answered. If work later fails, GET still returns 200 for the resource and its terminal state; do not confuse HTTP transport success with RAG success.

## 6. Request response and state machine

All request resources contain `id`, `status`, `created_at`, `updated_at`, `source`, `model`, `retrieval_setting_version`, `index_revision_id`, `route`, `answer`, `clarification_question`, `citations`, `timings`, `usage`, `error`, and `links`. Before finalization answer/error are null and citations empty. Summaries omit full question/answer. Usage includes `known_input_tokens`, `known_output_tokens`, `complete` and nullable total fields; never sum partial usage and label it complete.

Example final fragment (times intentionally unmeasured):

```json
{"status":"answered","answer":"<paper-supported text with citation>","citations":[{"chunk_id":"<uuid>","paper_id":"<uuid>","arxiv_id":"2410.00037","version":1,"page_start":3,"page_end":3,"label":"2410.00037v1 p.3","url":"/v1/chunks/<uuid>"}],"timings":{"first_token_ms":null,"total_ms":null},"usage":{"known_input_tokens":0,"known_output_tokens":0,"complete":false,"total_input_tokens":null,"total_output_tokens":null},"error":null}
```

| From | Allowed next state |
| --- | --- |
| received | queued, rate_limited, failed |
| queued | preparing, retrieving, cancelled, timed_out, rate_limited, failed |
| preparing | retrieving, needs_clarification, refused, cancelled, timed_out, rate_limited, failed |
| retrieving | reranking, refused, cancelled, timed_out, failed |
| reranking | generating, refused, cancelled, timed_out, failed |
| generating | validating, cancelled, timed_out, rate_limited, failed |
| validating | answered, refused, cancelled, timed_out, failed |

Terminal states: answered, refused, needs_clarification, cancelled, timed_out, rate_limited, failed. No terminal state returns to active. Provider backoff is an event within preparing/generating, not a rewind of the RAG pipeline. Cancellation and finalization race through a conditional DB update; the first committed terminal transition wins. A provider may continue remotely after cancellation; reconcile any later usage without changing the terminal answer.

Refusals are distinct from capacity failures. Citation failure returns `reason_code=citation_validation_failed`; do not claim it proves the papers have no answer. Source existence and citation format do not prove semantic correctness.

## 7. Streaming and reconnection

Create the resource, then open its SSE URL. SSE is one-way; cancellation uses POST. Emit IDs and event types following [MDN SSE format](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events). Proposed 15-second heartbeat comments have no event ID.

```text
id: 12
event: status
data: {"request_id":"<uuid>","status":"retrieving"}

id: 13
event: answer_delta
data: {"request_id":"<uuid>","offset":0,"text":"<validated answer fragment>"}

id: 14
event: done
data: {"request_id":"<uuid>","status":"answered","resource_url":"/v1/requests/<uuid>"}
```

Only release answer deltas after the whole candidate passes citation checks. Persist the answer before publishing deltas. Replay IDs are monotonically increasing per request; clients deduplicate by ID. Last-Event-ID replays later retained events and never starts inference. Store UI event sequence separately from diagnostic spans; do not expose model reasoning, hidden drafts, prompts or stack traces. Cap payload size at 8 KiB; final answer is authoritative via GET.

Events: `status`, `answer_delta`, `citations`, `clarification`, `error`, `done`. Every terminal outcome ends with done when connected. After headers are sent, errors use SSE error/done rather than a new HTTP status. A lost connection may miss done; GET resolves it. Terminal resources can replay their retained stream then close. Expired stream history returns 410 before opening SSE and directs the client to GET the retained resource.

Record provider first-content timing separately from first initial answer emission. Replaying events must not overwrite original timings. Client receipt is not guaranteed by a successful server write; mark server-emission timing as such and retain delivery events separately from computation completion. No subscribers means user-visible first-token time is null.

## 8. Pagination and errors

All collection endpoints use `limit` default 20, range 1–100 and opaque signed `cursor`. Response: `{ "items":[], "next_cursor":null, "has_more":false }`. No expensive exact totals by default.

Order history by `(created_at DESC,id DESC)`; events by sequence ascending. Cursor contains version, last sort tuple, first-page snapshot cutoff, filter hash and expiry (one hour). Validate signature, expiry and filter consistency; malformed/expired/mismatched cursors return 400 `invalid_cursor`. Stable sort prevents duplicates for unchanged rows; state-filtered lists are explicitly live views and can change between pages. Restart pagination to see new arrivals. History is shared within this local instance.

```json
{"error":{"code":"quota_exhausted","message":"The model token budget is temporarily exhausted.","request_id":"<http-correlation-id>","resource_id":"<rag-id-or-null>","retryable":true,"retry_after_seconds":12,"details":{"dimension":"tpm"}}}
```

| HTTP | Codes/use |
| --- | --- |
| 400 | malformed_json, invalid_cursor |
| 404 / 410 | not_found / resource_expired, replay_expired |
| 409 | idempotency_conflict, run_not_exportable |
| 413 / 415 / 422 | payload_too_large / unsupported_media_type / validation_error |
| 429 | queue_full, quota_exhausted; Retry-After only when known |
| 500 / 503 | internal_error / index_unavailable, storage_unavailable |

Details contain allowlisted field paths/reason codes, never input values/secrets. Provider timeout/error after admission is stored as a terminal resource outcome. For exhausted daily quota with unknown reset, return null retry delay; never invent a reset time. Do not automatically resubmit a newly keyed request on network uncertainty: replay its original key.

## 9. Internal stand-in boundary

Bind a separate service to loopback. Proposed internal `POST /internal/completions` accepts server-created model messages, completion cap, request/call IDs, attempt number and streaming flag. A separate internal secret in a header authenticates it; no Groq key is forwarded. Return chunks and final usage in the common backend format, or 429 with Retry-After, 5xx, timeout/disconnect according to the frozen scenario profile. Configure profiles through local CLI at run startup, not user input. Simulated quotas are independent of application quotas. No arbitrary URL proxying or public fault controls.

## 10. Acceptance and UI handoff

Verify local-only binding, missing-resource 404s, malformed bodies and enums, conflicting idempotency keys, concurrent double-submit, deadline/cancel races, replay without duplicate model calls, expired cursors, no draft leakage, redacted errors, quota responses and incomplete export rejection. Use fixture responses for each UI state.

Streamlit screens: question form with auto-refinement toggle; request progress and cancellation; cited answer/source expanders; clarification prompt creating a new request; paginated history; operator run list/detail and result download. Display stand-in source prominently, distinguish refusal from provider outage, and never display progress events as first answer tokens. No UI or endpoint has been implemented here.

Use a form submission to allocate one idempotency key, retain it across ambiguous HTTP failures, and retain the returned request ID across reruns. Initial UI refresh polls GET request state approximately once per second while active (with backoff on connection failures), stops at terminal state, and leaves cancellation responsive. Use bounded HTTP timeouts and no unbounded blocking polling loop. Browser refresh may reset UI state; recover via history rather than resubmitting. The UI reads cursor pages from the backend and clears cursors when filters change.

SSE remains a supported API transport, separately tested with API clients; Streamlit MVP uses polling. Do not equate polling render time, backend SSE emission or provider first-token time. A later SSE UI adapter must implement sequence deduplication and reconnect without starting new inference. Acceptance tests must prove reruns and refresh do not duplicate generation, cancellation/history work while requests progress.
