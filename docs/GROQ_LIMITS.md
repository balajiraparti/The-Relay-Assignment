# Groq evidence and calibration — reviewed November 13, 2026

Selected model: `openai/gpt-oss-120b`. The official [rate-limit table](https://console.groq.com/docs/rate-limits) currently lists these free-plan defaults:

| Dimension | Published default | Project setting | Account evidence |
| --- | ---: | --- | --- |
| Requests/minute | 30 | GROQ_RPM | Not established by our small probe |
| Requests/day | 1,000 | GROQ_RPD | Prior response header: 1,000 |
| Tokens/minute | 8,000 | GROQ_TPM | Prior response header: 8,000 |
| Tokens/day | 200,000 | GROQ_TPD | Not established by our small probe |

Limits apply to the organization; the account Limits page is authoritative and exceptions can apply. Request headers describe daily request limits; token headers describe minute token limits. Preserve reset headers as provider observations, not a claim of midnight reset or a fixed-window algorithm. Some accounts also have input/output sublimits. We have not established whether those apply here. The local rolling ledger counts conservatively and cannot see other clients using the organization. No account page was accessed. [Official explanation](https://console.groq.com/docs/rate-limits)

The [model page](https://console.groq.com/docs/model/openai/gpt-oss-120b) lists a 131,072-token context window and a 65,536-token output limit. These are model capabilities, not free-tier allowance or latency guarantees. Our much smaller completion caps remain intentional.

The adapter reads content-only SSE, excludes reasoning, handles both usage envelope shapes, and retains allowlisted headers. All real calls pass through the same gateway as preparation/generation. Transport attempts and unknown usage remain charged conservatively; no silent switch to synthetic answers occurs.

Existing real observations are described in FIRST_RUN_RESULTS.md. `relay.cli probe --count 1` performs one bounded generic-prompt smoke check; counts above one are spaced by 22 seconds and stop at the first failure. Saved observations include failures. `relay.cli calibrate --observations <file>` accepts only successful real samples with valid timings and records the source-file SHA-256. It does not infer failures, rate limits, token speed or load behaviour from latency samples. Synthetic service timing, seeded faults and quota semantics remain distinct assumptions. Three samples do not justify p95/p99 claims.
