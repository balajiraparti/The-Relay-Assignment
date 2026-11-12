# F09–F12 verification — November 13, 2026 (Asia/Calcutta)

## Executed live observations

| Check | Result | Evidence |
| --- | --- | --- |
| Generic Groq probe | Success; first content 974.2 ms, total 996.8 ms; 82 input / 42 completion tokens | runtime/probes/20261112T184345Z-e5087f9c/observations.json |
| Initial paper pipeline | Refused invalid schema after 14537.9 ms; 1209 input / 163 completion tokens; one attempt | SQLite request f9362006-1f83-4326-8f2b-8fe800ac0126 |
| Paper pipeline with JSON-object mode | Citation-format validation passed; first provider content 1153.8 ms, pipeline total 1967.6 ms; 1238 input / 185 completion tokens; one attempt | runtime/evaluation/d3ca35ba-b4d2-473e-a0cf-1dc5b2b7f793/result.json and generation.json |

There were three hosted calls in this cycle. UTC artifact paths begin November 12 because the local calendar had advanced to November 13. These are individual observations, not throughput or percentile benchmarks. Pipeline times exclude local-model startup and UI delivery. The invalid-schema run is retained, not counted as a successful answer. No corrective loop was introduced: enabling JSON-object mode was a code change followed by a separate verification request.

The accepted answer cites Moshi pages 17 and 6 and describes the supported core mechanism. Manual inspection also found a novelty phrase broader than the paper's qualified wording (“to the best of our knowledge” and “many ... challenges”). This demonstrates why citation-format acceptance is not a semantic correctness grade. Preserve this example for F14 manual grading; do not label it a fully correct benchmark answer. No zero-hallucination guarantee is made.

## Implemented boundaries

Final automated verification: 82 tests passed in 14.04 seconds. Real API readiness returned 200 for Groq configuration and index 532f423d5a5967b8, explicitly without probing provider connectivity. Streamlit AppTest rendered against that running API without exceptions. This is not a full browser interaction or load test.

- F09: real HTTP/SSE adapter, content-only extraction, usage envelopes, allowlisted headers, explicit JSON-object mode, bounded probe, and calibration timing/provenance validation. Published versus observed limits are separated in GROQ_LIMITS.md. The earlier three-sample calibration was regenerated with its input SHA-256; new runs are not silently pooled with it.
- F10: clear/off/busy paths avoid preparation; missing-referent templates clarify. At most one five-second preparation call is allowed. Rewrites may remove courtesy prefixes only while retaining substantive token order, numbers, negation and internal pronouns. Unsafe, malformed or failed rewrites fall back to the original. This deliberately sacrifices paraphrase flexibility; arbitrary semantic equivalence is not proven.
- F11: original question retained for generation/reranking; one generation only; full answer buffered until schema and sentence-level citation checks pass. Unknown IDs, uncited sentences, malformed drafts and absent evidence refuse. The sentence splitter is deliberately conservative and can reject abbreviations or complex notation. Aggregated usage covers preparation and every attempt; totals become null when any usage is unknown, with known subtotals retained. CPU retrieval retains its slot until work actually finishes after caller cancellation.
- F12: supported launcher binds 127.0.0.1 with proxy-header trust disabled; peer IP, Host, Origin and bounded request-body checks protect the local API. UI backend URLs must be local and environment proxies are ignored. Readiness reports safe configuration/database/index/telemetry failures without probing the provider. History belongs to the local instance; there are no accounts or sign-in endpoints. This is not public-service authentication.

F13 resumable SSE/durable event contracts, F14 graded quality/load experiments, F15 remaining UI flows and F16 submission packaging remain unfinished.
