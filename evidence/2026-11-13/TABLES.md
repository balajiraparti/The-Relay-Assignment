# Recomputed results tables

Linear interpolation (n-1)*p. Total includes all outcomes; first_token only observed released answers. Offered rate is empirical arrival rate (n-1)/arrival span, not intended schedule. Duration includes final drain.

Queue cannot be derived from the required CSV columns: table reports not measured; sampled queue proxies are separately in manifests. Stand-in quality is not evaluated. Empty grades on capacity failures are not refusals. Assistant-reviewed real grades need author verification.

## table1

| Limit | Value | Method | Confidence |
| --- | --- | --- | --- |
| Requests/minute | 30 | Official free-tier documentation | medium |
| Tokens/minute | 8000 | Documentation + response header | high |
| Requests/day | 1000 | Documentation + response header | high |
| Tokens/day | 200000 | Official free-tier documentation | medium |
| Requests in flight | not measured | Local cap is not provider capacity | low |
| Limit response | not measured | Local refusals are not upstream 429 | low |
| Recovery time | not measured | No upstream limit/recovery observation | low |

## table2a

| Scenario | Source | N | Duration s | Offered/min | First p50/p95/p99 ms | Total p50/p95/p99 ms |
| --- | --- | --- | --- | --- | --- | --- |
| steady | real | 45 | 1322.3 | 2.0 | 1918.3 / 2448.1 / 2714.7 | 1215.8 / 2227.7 / 2665.7 |
| steady | stand-in | 8 | 33.8 | 40.0 | 19773.2 / 23892.8 / 23981.5 | 11852.6 / 23749.3 / 23956.4 |
| burst | stand-in | 16 | 18.4 | 6251.0 | 17627.5 / 18310.0 / 18370.6 | 9335.0 / 17821.9 / 18276.0 |
| sustained_overload | stand-in | 24 | 17.0 | 581.3 | 16514.6 / 16825.8 / 16853.5 | 4496.4 / 14982.7 / 16706.3 |
| per_minute_limit_halved | stand-in | 12 | 17.7 | 296.5 | 16912.3 / 17290.7 / 17324.3 | 8162.6 / 17105.3 / 17290.3 |
| daily_budget_exhausted | stand-in | 8 | 1.8 | 498.8 | not measured | 814.4 / 1075.0 / 1120.1 |
| retry_comparison_one_attempt | stand-in | 16 | 6.8 | 601.7 | 3207.3 / 5050.5 / 5224.3 | 1797.5 / 4912.5 / 5201.0 |
| retry_comparison_three_attempts | stand-in | 16 | 8.7 | 565.3 | 4995.8 / 7618.1 / 8502.8 | 4083.9 / 7347.8 / 8452.4 |

## table2b

| Scenario | Source | Succeeded % | Rate-limited % | Timeout % | Retries/request | Peak queue | Tokens/answer | USD/1000 answers |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| steady | real | 77.8 | 22.2 | 0.0 | 0.0 | not measured | 3199.1 | 0.6 |
| steady | stand-in | 50.0 | 0.0 | 50.0 | 0.0 | not measured | 177.0 | not measured |
| burst | stand-in | 18.8 | 18.8 | 62.5 | 0.0 | not measured | 177.0 | not measured |
| sustained_overload | stand-in | 8.3 | 50.0 | 41.7 | 0.0 | not measured | 177.0 | not measured |
| per_minute_limit_halved | stand-in | 25.0 | 0.0 | 75.0 | 0.0 | not measured | 177.0 | not measured |
| daily_budget_exhausted | stand-in | 0.0 | 100.0 | 0.0 | 0.0 | not measured | not measured | not measured |
| retry_comparison_one_attempt | stand-in | 62.5 | 0.0 | 0.0 | 0.0 | not measured | not measured | not measured |
| retry_comparison_three_attempts | stand-in | 81.2 | 18.8 | 0.0 | 0.4 | not measured | not measured | not measured |

## table3

| Setting | Questions | Correct cited % | Wrong % | Correct refusal % | Tokens/answer | First p50/p95 ms | Total p50/p95 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1: 200 tokens, 4, no | 15 | 13.3 | 6.7 | 33.3 | 4643.3 | 1129.5 / 1142.8 | 936.2 / 1276.4 |
| R2: 200 tokens, 5, yes | 15 | 33.3 | 13.3 | 33.3 | 2500.6 | 1918.3 / 2168.1 | 1762.0 / 2316.9 |
| R3: 200 tokens, 6, yes | 15 | 13.3 | 6.7 | 33.3 | 3384.7 | 2013.4 / 2704.5 | 1028.7 / 2379.7 |
