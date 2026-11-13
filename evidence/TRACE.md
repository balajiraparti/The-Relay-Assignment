# Slow real request trace

Request: 6eebe80c-484c-49b4-972c-eaa1393edcb8

| Component | ms |
| --- | --- |
| total_ms | 2786.648 |
| retrieval_work_ms | 979.048 |
| gateway_wait_ms | 0.065 |
| model_network_and_work_ms | 1308.888 |
| retry_ms | 0.000 |
| validation_storage_and_observer_overhead_ms | 498.647 |
| gateway_first_content_ms | 981.957 |
| model_after_first_content_ms | 326.996 |
| validated_first_token_ms | 2781.304 |

The disjoint decomposition is retrieval + gateway wait + model/network work + retries + validation/storage/observer overhead = runner total. Gateway first content is measured from gateway entry, not request arrival. The first validated answer is released after generation and validation. Network time and remote inference are not separately identified; provider timing metadata is retained without pretending it uses the same clock. No retries occurred in this selected request.