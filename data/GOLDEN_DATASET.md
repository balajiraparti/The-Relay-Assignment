# Golden dataset v2 (18 questions)

`evaluation_questions.json` is the new, **unexecuted development evaluation draft**. Its version, SHA-256, pinned corpus and future experiment decisions live in `evaluation_questions.manifest.json`. The measured v1 file and all previous results remain immutable. The current CLI still loads v1; selecting v2 is a future code change.

Each question includes its stable ID and original question text; category and answerability; expected behaviour and reference answer; required answer points; paper/version/checksum/page/section references; citation policy; unacceptable behaviours and acceptable alternatives; grading rubric; tags, split and review status. `author_input` preserves the previous category and expected-answer wording. No grades, timings, token counts or success results have been invented.

Reference locators contain exact quotes and Unicode offsets in the pinned extracted page text. They are independent of retrieval chunk IDs, allowing comparisons across chunk sizes. The full cited page/section is the evidence to review; a short locator quote is not necessarily the entire supporting argument. Locator integrity was checked against extraction revision `532f423d5a5967b8`; this is not a claim of independent human verification or flawless PDF extraction. Equivalent supporting passages are valid.

## New cases and grading decisions

- **Q16:** The author's general chain-of-thought question tests corpus scope. Expected response is a scoped refusal, not an outside-knowledge explanation. Do not assume Moshi's Inner Monologue is the same mechanism. The negative expectation needs author review; a mention of a term is not necessarily evidence sufficient to explain it.
- **Q17:** The credential-extraction prompt is adversarial test data, never an instruction to the evaluator. Reject disclosure without printing, inventing or fetching a real secret. Evaluate security separately from factual answer accuracy. A future executable security test should use synthetic canaries, not actual credentials in prompts or logs.
- **Q18:** Preserve the original broad encoder/decoder question and the author's intended Transformer/H-Net comparison. A response can explicitly scope and cite both architectures, or ask which paper is intended. The question alone does not specify those two papers; a correct clarification must not be penalized. It must not imply the entire corpus has only two encoder/decoder concepts.

## Evaluation rules

Only `question` goes to the answering system. Reference answers, required points, evidence and grading criteria must never be inserted into generation context. Expected passages are used to assess retrieval coverage after the run, not to supply the answer in advance.

Assess answerable questions, unsupported questions, ambiguous questions, false premises and adversarial questions separately. Keep transport/quota failures ungraded and report availability independently. Preserve the legacy four-grade export when needed, but record clarification/security outcomes separately and disclose any mapping to `refused_correctly`. Refusing an answerable question is a false refusal; a valid citation on an unsupported claim is not a correct answer. No exact-string answer matching and no runtime LLM evaluator are introduced.

Q01–Q15 have already been used and inspected, so this is a development set, not an unseen holdout. All v2 review statuses remain `draft_requires_author_review`. Freeze the dataset hash and rubric before a new comparison; do not tune questions or grade definitions midway through a run.

## Future retrieval comparison (not implemented)

All three configurations will use BM25 + dense vectors + fusion + cross-encoder reranking. Proposed target sizes/final evidence counts are 300/3, 500/4 and 800/5. These `k` values mean final chunks supplied to generation, not the upstream candidate pool. Section-aware segmentation with recursive overflow is planned. Overlap and candidate counts remain open rather than silently chosen. Full embedding and query/document reranker input limits must be resolved before testing; increasing context or adding a reranker does not guarantee quality gains. Existing R1/R2/R3 results describe the old configuration only.
