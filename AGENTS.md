# Working on The Relay

Read PROJECT_STATUS.md before implementation. Follow PRODUCT_REQUIREMENTS.md, API_DESIGN.md and DATABASE_DESIGN.md for behaviour and contracts.

The user wants small, separately reviewable increments. Implement one backlog feature per work cycle unless the user explicitly requests more. Do not infer authorization to complete the entire backlog from a request to begin its next feature.

Before feature work, mark the chosen row/status In progress and state its scope in PROJECT_STATUS.md. After every feature change, update status, changed-file evidence, checks actually executed, limitations, blockers and next task. Update the verification ledger and change log. Never count a design, fixture-only test or unexecuted plan as a completed live integration.

Preserve the user's .env and source PDFs. Never print or commit credentials. Run meaningful checks for the feature. No corrective-RAG generation loop or LLM answer evaluator is in scope. All hosted calls must pass through the shared quota gateway.

Keep status statements consistent with repository evidence. When requirements change, update the relevant design document and tracker together. Make routine implementation decisions within approved scope; reserve open questions for meaningful unresolved choices.

## Version control workflow

Remote: https://github.com/balajiraparti/The-Relay-Assignment.git. Work on `dev`. After an important feature or milestone, run its meaningful checks, update the tracker and relevant documents, review staged changes for secrets/generated files, then create a focused descriptive commit and push `dev`. The user has authorized these routine commits and pushes. Keep `.env`, caches, databases, logs and local runtime artifacts untracked. Never force-push or merge into `main` without explicit authorization. Use a pull request into `main` when the requested feature set is ready for review; do not merge automatically.
