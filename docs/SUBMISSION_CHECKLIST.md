# Submission and author review

The exact assignment brief was recovered from the original conversation attachment on November 13. Its required headings, in order, are:

1. What I built and why
2. The real service and my stand-in
3. Results
4. Where the time goes
5. When a limit is hit
6. Retrieval: quality versus cost
7. How this library will mislead a naive retriever
8. Retries
9. What the person sees
10. What I'm unsure about, what I left out, what I learned
11. Your feedback on Vaani
12. How I worked with the assistant

The report generator uses these headings and creates exactly two pages. The brief asks for a half-page assistant reflection within that same limit. Tables use measured CSV rows; missing fields remain “not measured.” The required CSV cannot encode peak queue or limit-discovery provenance, so those cannot honestly be reconstructed from it. This conflict is disclosed rather than addressed by fabricating values. Manifests/events provide additional trace evidence.

## Author actions before final submission

- Review every provisional assistant evidence grade against the actual cited source. No runtime LLM evaluator or corrective loop was added. `scripts/grade_run.py` records your explicit grade, reviewer and rationale.
- Add your own Vaani website feedback. “Interesting and a bit difficult to understand” was feedback about the assignment; it is not misrepresented as a website review.
- Verify the first-person reflection. The prompt export is a verbatim snapshot of available user-message objects, not a fabricated cleaned-up conversation or a full final-turn transcript. Use the app's complete export if available.
- Decide whether to measure a genuine upstream rate limit and recovery with an additional bounded, compliant experiment. No quota guard was disabled, and local rejections are not Groq HTTP 429s. Unknown values stay explicit.
- Check the Saturday November 14 deadline with the assignment sender; it is less than four days after Thursday November 12.

## Reproduction

The measured question set is frozen at `data/evaluation_questions.v1.json` and its SHA matches the run manifest. The author's live edits to `data/evaluation_questions.json` are a separate working draft and were not part of these results. Packaging reads committed Git blobs, not uncommitted working drafts, so simultaneous editing cannot silently alter a submission artifact.

Use Python 3.11 and the pinned `requirements.lock.txt` for the measured Windows environment, then install the repository editable without resolving dependencies again. Preserve or recreate `.env` privately; audit/ingest the pinned source PDFs; migrate before starting the API. The local model files are pinned by recorded weight/tokenizer hashes, not bundled in the submission. Download access is required on a clean machine.

Run `python -m relay.experiments quality --interval 30` for a new 45-arrival real experiment. It uses the shared persistent quota ledger, so do not reset the DB to bypass limits. Run it without concurrent interactive hosted traffic. Run `python -m relay.experiments load` for synthetic profiles. Both save new UUID run directories, never overwrite prior raw trials. Quality runs may take more than twenty minutes and consume account tokens. `--scenario` limits the synthetic runner to named scenarios; it does not select real traffic.

`python scripts/collect_evidence.py` copies only IDs in `data/experiment_selection.json` to curated evidence. `python scripts/report_tables.py` recomputes tables from the combined exact-column CSV. `python scripts/build_report.py` builds the PDF using reportlab 4.4.9. Ordinary app dependencies do not require PDF tooling. `python scripts/package_submission.py` produces a secret-checked ZIP from tracked source plus the curated evidence/report. Operational databases, logs, caches and `.env` are excluded.

Unknown token usage is never replaced by zero. Zero on a local pre-dispatch refusal means no provider attempt occurred. Real quality grades are absent for capacity failures; percentages use all offered questions, exposing lost availability. Stand-in `ok` means a synthetic fixture completion, not correctness on research papers. Full response timing is measured by the runner consuming committed public events; it is not browser receipt. The existing tiny generic probe calibration remains distinct from the larger paper-sized experiment.
