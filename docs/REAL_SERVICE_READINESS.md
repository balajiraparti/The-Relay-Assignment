# Real-service measurement readiness — November 13, 2026

## Verdict

Logger and Groq authentication/streaming are ready for controlled smoke probes. The full percentile and recovery experiment is not implemented yet. The existing stand-in is preliminary: latency has only a tiny real sample, while failure, quota and overload behaviour are still synthetic assumptions. Collect real measurements before further calibrating it.

## Readiness check actually executed

One real call to openai/gpt-oss-120b, with one maximum attempt and no retries:

| Field | Observation |
| --- | --- |
| N in this readiness run | 1 |
| Upstream HTTP status | 200 |
| First content token | 660.9 ms |
| Total streamed completion | 799.9 ms |
| Prompt / completion tokens | 82 / 26 |
| Local waiting | 0.086 ms |
| Real rate-limit response | Not observed |
| Empirical recovery delay | Not measured |

Raw observation: runtime/probes/20261112T185340Z-a5cd37ca/observations.json. Matching JSONL: runtime/logs/cli.89f8e1e110d3443691307898ebc3b185.0000.jsonl. Request ID: 4cdbf81f-d516-4fd1-bf12-2a3a40b1a866. UTC paths use November 12; the local date is November 13.

The run's model_started/model_completed events have unique event IDs, timestamps and matching correlation IDs. The recorded upstream HTTP 200 matches the observation. Twenty-one focused logger/provider/HTTP tests passed in 6.80 seconds, including redaction, bounded writer failure/overflow, shutdown flush, streaming and local synthetic faults. Those synthetic fault tests are not real 429 observations.

The probe now explicitly records model, measurement version, actual successful HTTP status, maximum attempts, retry count and local wait. Local quota rejection is distinct from an upstream HTTP response; a local 429-like status must not be described as Groq rejecting the request. Timing starts at gateway submission, so it includes client/network/local admission and ends after stream consumption. It is neither provider-internal compute time nor user-visible UI TTFT.

## Published limits versus measured limits

Official [Groq documentation](https://console.groq.com/docs/rate-limits), checked November 13, lists GPT-OSS 120B free defaults of 30 RPM, 8,000 TPM, 1,000 RPD and 200,000 TPD. This run's headers confirm advertised RPD=1,000 and TPM=8,000. We have not experimentally established enforcement thresholds, RPM/TPD account overrides, separate input/output sublimits, or recovery behaviour. Account limits can differ; quotas are organization-wide. See GROQ_LIMITS.md.

Use this truthful report wording now:

> The published free-plan limits were 30 RPM, 8,000 TPM, 1,000 RPD and 200,000 TPD. Response headers corroborated RPD and TPM. In this readiness run, N=1 real call returned HTTP 200, with TTFT 660.9 ms, total time 799.9 ms and token usage 82 input / 26 output. No real rate-limit response was observed; recovery delay was not measured. This is a readiness sample, not a percentile benchmark.

## What remains before percentile calibration

The current probe is capped at 1–5 calls, waits 22 seconds between calls and stops on failure. It does not generate percentile tables or measure recovery. Do not pool its historical samples across measurement versions or mix generic prompts with paper-answer runs.

Next implement a separately reviewable real measurement runner, not more stand-in behaviour. Freeze a run manifest with model/settings, prompt-profile hash, output cap, code revision, seed where applicable, arrival schedule and timestamp definition. Record one structured row per attempt plus a final row per logical request. Retain all failures and unknown usage; record sample counts for each latency population.

A feasible initial target is 50 sequential short-prompt calls at a conservative rate below both configured RPM and TPM, then a separate paper-sized prompt profile paced for its larger token budget. This is a proposed run, not executed work. Report p50/p90 and exploratory p95 with sample sizes; p99 from such a small sample is not a dependable tail estimate. Separate startup/client connection effects, prompt/output lengths and real versus synthetic sources. Keep transport retries disabled for the primary latency sample or report each attempt separately.

For recovery, a real provider 429 must be distinguished from our local limiter. Retain its HTTP status and allowlisted headers, including Retry-After if supplied. Retry-After is an advertised wait, not observed recovery. A bounded later successful request measures recovery from the observed rejection; report polling resolution and stop conditions. Do not try to exhaust daily quotas or remove gateway protections merely to manufacture a 429. If none occurs, keep both response and recovery as unobserved/unmeasured.

Calibrate first-token and post-first-token timing from the same real profile, retaining paired samples and source hashes. More detailed streaming simulation needs real chunk timing/size observations. Fault rates, congestion response and quota semantics remain explicit assumptions unless those behaviours are actually observed. No new latency profile was fitted from this single readiness call.
