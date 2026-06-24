# Decision Log (ADR-style)

Each entry: decision, alternatives, reason, reversibility. New non-blocking assumptions made during the build are appended here rather than expanding scope. Consequential or blocking decisions are escalated to the owner.

| # | Date | Decision | Alternatives | Reason | Reversible? |
|---|------|----------|--------------|--------|-------------|
| 1 | 2026-06-23 | **Deterministic-first; LLM only for semantics** (interpretation, evidence mapping, gaps, summary). | Pure agentic loop. | Reliability + cost; normalization/diffing/blocking must not depend on a model. | Yes |
| 2 | 2026-06-23 | **ATS public APIs before scraping** (Greenhouse, Lever, Ashby). | Browser scraping everywhere. | ~80% coverage with no brittle automation; publish unsupported coverage instead of faking it. | Yes |
| 3 | 2026-06-23 | **Stage 1 is headless Python; SQLite state.** Web app deferred to Stage 2. | Build the Next.js + Supabase app first. | Right-sizes v1 to the builder (owner + coding agent, basic Python); ships value in days, not weeks. | Yes — repo/ORM boundaries keep a Postgres migration cheap. |
| 4 | 2026-06-23 | **Never write to the source spreadsheet in Stage 1.** | Two-way sync. | Avoids fragile sync; one-way controlled migration happens in Stage 2. | Yes |
| 5 | 2026-06-23 | **Human approval gates every consequential action.** No auto-add, auto-status, outreach, or submission. | Auto-add above a score threshold; auto-status from email. | Misclassification is costly; control is the product boundary. | No (core principle) |
| 6 | 2026-06-23 | **Four separate evaluation outputs** (fit · feasibility · strategic priority · recommendation). | One blended score. | Stops company prestige or location from hiding weak role fit. | Yes |
| 7 | 2026-06-23 | **Narrow true blockers; everything else is a penalty.** | Hard title-based exclusions. | Title-only blocks hide good roles with unusual titles; use penalties + the review queue. | Yes |
| 8 | 2026-06-23 | **Status from email, never from a dead URL.** | Infer "closed/rejected" when a posting 404s. | Postings get reposted and URLs persist; the inbox is the real signal (Stage 3). | No |
| 9 | 2026-06-23 | **No multi-agent framework.** A scheduled workflow + narrow services. | CrewAI / LangGraph multi-agent. | Simpler, cheaper, testable; avoids a novelty demo. | Yes |
| 10 | 2026-06-23 | **Benchmark calibrated on owner-labelled history** (~30 roles). | Trust the prompt as-is. | The differentiator is encoding the owner's judgment; measure it, don't assume it. | Yes |
| 11 | 2026-06-23 | **Email via a transactional provider; Gmail is read-only (Stage 3).** | Gmail app-password/SMTP to send. | Never request Gmail write scopes just to send a digest; least-privilege. | Yes |
| 12 | 2026-06-23 | **Supabase Cron for production scheduling (Stage 2); GitHub Actions only for CI + Stage 1.** | GitHub Actions as the production scheduler. | Scheduled GH runs can be delayed/dropped and disabled on inactive repos. | Yes |

> Template for new entries: **Decision · Alternatives · Reason · Reversibility · Owner approval (if needed).**

## Stage 0 import addendum

| # | Date | Decision | Alternatives | Reason | Reversible? |
|---|------|----------|--------------|--------|-------------|
| 13 | 2026-06-23 | **Use the earlier scaffold docs/data as the source for README, roadmap, decision log, architecture, evaluation docs, benchmark set, and tracker snapshot.** | Keep the generated Stage 0 docs only. | The owner identified these files as prior work that cannot be regenerated. | Yes |
| 14 | 2026-06-23 | **Keep generated code/config/audit files from the current Stage 0 build.** | Replace the whole repository with the earlier scaffold. | The owner asked to use prior versions only for specific files and keep the current code. | Yes |
| 15 | 2026-06-23 | **Include the authoritative PRD as `docs/PRD.md`.** | Leave the README link broken or point to Downloads. | The repo should be self-contained before pushing. | Yes |
| 16 | 2026-06-23 | **Push only to a private GitHub repository.** | Public portfolio repo immediately. | The current repo contains private tracker-derived strategy, warm-path indicators, and real job-search data. | Yes, after creating a sanitized demo dataset |
| 17 | 2026-06-23 | **Use a deterministic development evaluator for Checkpoint B.** | Block the vertical slice until live LLM credentials are configured. | This proves fetch, normalize, dedupe, persistence, review state, source health, availability, and digest behavior without spending tokens or requiring secrets. | Yes, replace with the schema-validated LLM evaluator in Stage 1 |
| 18 | 2026-06-23 | **Evaluate target-scope roles only in the first Databricks slice.** | Evaluate all fetched Databricks postings. | The live feed has hundreds of jobs; the first slice should prove relevance without creating a noisy digest. | Yes |
| 19 | 2026-06-23 | **Rewrite Git history to purge the real tracker and owner/path PII.** | Delete the file only in a new commit. | A normal delete would leave the private workbook and home path recoverable from earlier commits. | No, except by another history rewrite |
| 20 | 2026-06-23 | **Replace the real tracker with a schema-only sanitized workbook.** | Keep the real tracker in a private repository. | The reviewer identified the tracker as containing PII; the code only needs a representative workbook shape for now. | Yes |
| 21 | 2026-06-23 | **Commit scan run/health state before digest rendering.** | Keep scan and digest in one transaction. | A digest/template failure must not erase a successful fetch, posting upsert, evaluation pass, or source-run record. | Yes |
| 22 | 2026-06-23 | **Use a small configurable relevance pre-filter and record skip reasons.** | Score every fetched posting; or keep role-family signals hard-coded only. | The Databricks feed is large, but skipped jobs must be auditable. Full YAML-driven scoring remains deferred to Checkpoint C. | Yes |
| 23 | 2026-06-23 | **Stamp placeholder evaluator output as `uncalibrated_dev_stub_v1`.** | Keep `role_evaluation_v1`/policy literals as if the output were calibrated. | The deterministic evaluator proves the pipeline only; scores are not trusted until benchmarked against owner-labelled roles. | Yes |
| 24 | 2026-06-23 | **Apply the owner-approved visa stance in both config and deterministic feasibility.** | Keep Sydney/London as uncertain until full config loading. | The approved correction says only the US is high-friction; Australia timing is represented as `arrival_plus_3_months` because no arrival date is configured yet. | Yes |
| 25 | 2026-06-23 | **Cap stretch-family roles at consider/stretch unless a warm path or explicit exceptional-upside flag exists.** | Let raw fit score push Deployment Strategist/FDE-style roles to apply-now. | The reviewer flagged the stretch ladder as too optimistic; exceptional upside is a parameter, not auto-inferred in this dev evaluator. | Yes |
| 26 | 2026-06-23 | **Ashby C1 uses the live public `jobs` payload shape and `includeCompensation=false`.** | Infer shape from the audit only. | Live OpenAI/Airwallex pulls confirmed top-level `jobs` with posting `id`, title, department/team, employment type, locations, URLs, published date, and descriptions. The compensation flag keeps fixtures focused on discovery fields. | Yes |
| 27 | 2026-06-23 | **Ashby fetch sends a browser-like User-Agent.** | Use bare `urllib` headers. | The live Ashby endpoint returned 403 to bare Python urllib but succeeded with a normal User-Agent; this is connector compatibility, not scraping. | Yes |
| 28 | 2026-06-23 | **Lever source metadata can be derived, but Lever companies stay disabled until C2.** | Leave enabled audit rows runnable before an adapter exists. | C1 only ships Greenhouse + Ashby adapters; known Lever source keys remain useful evidence but must not be scanned until the Lever adapter is implemented. | Yes |
