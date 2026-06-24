# Job Search Agent

A single-user system that detects strong, freshly-posted roles at a fixed company watchlist within hours, evaluates each one against a real, encoded career strategy, and keeps an accurate application pipeline — **without taking any consequential action silently.**

> **Status:** Stage 1 Checkpoint B started: one-source Databricks/Greenhouse vertical slice is implemented locally. See [ROADMAP.md](./ROADMAP.md).

---

## Why this exists

High-quality roles at a finite set of target companies appear irregularly, use inconsistent titles, and close quickly. Manual career-page checks are repetitive and generic job alerts are noise. This system detects roles early, explains fit with evidence from the candidate's actual background, and reduces tracker maintenance while keeping the human in control of every decision that matters.

## What makes it different

It is **not** a generic CV-to-JD matcher. Its value is that it encodes and *tests* a specific decision logic, benchmarked against ~30 historically-labelled roles ([`data/evaluation_set/`](./data/evaluation_set/evaluation_set.yaml)):

- Clean fit vs. strategic stretch (e.g. Deployment Strategist is a *stretch*, not core)
- Strategy/operations work vs. Customer Success (a different career, deprioritized)
- Right seniority and ownership (associate-scope roles are penalized regardless of title)
- Location/work-authorization feasibility (a strong role can still be `blocked` on visa)
- Company priority and warm-path value (a warm intro can lift a stretch to `apply_now`)
- Honest technical and domain gaps

Crucially, fit, feasibility, and company priority are scored **separately**, so brand or location can never hide a weak role fit.

## How it works (Stage 1)

```
 scheduler (every 6h)
        │
        ▼
 [adapters] Greenhouse · Lever · Ashby  +  manual URL/text intake
        │  fetch → normalize → dedupe (idempotent)
        ▼
 [source health]  fail loudly: a broken connector ≠ a zero-job success
        │
        ▼
 [deterministic blockers + feasibility policy]   ← code, not the LLM
        │
        ▼
 [LLM evaluator]  4 outputs: fit · feasibility · strategic priority · recommendation
        │  (structured JSON, schema-validated)
        ▼
 [SQLite state]  postings · evaluations · review decisions · runs
        │
        ▼
 [morning digest]  Apply now / Consider / Stretch / Low / Source failures  → email
```

The existing spreadsheet remains the manually-maintained tracker during Stage 1; the system never writes to it. Stage 2 migrates state into a web app + Postgres.

## Repository layout

```
docs/        PRD (authoritative spec), architecture, evaluation guide
config/      watchlist · candidate_profile · location_policy · scoring_policy (YAML, versioned)
data/        evaluation_set (benchmark labels) · fixtures (saved ATS payloads)
app/         adapters · services · models · prompts · templates · cli
tests/       unit · integration · adapters · evaluation benchmark
scripts/     tracker import · CSV export
.github/     CI, scheduled-scan workflow, issue/PR templates
```

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # fill locally; never commit .env

job-agent scan                # run a discovery scan (writes a local digest)
job-agent scan-all            # scheduled-style scan + digest notification/fallback
job-agent review list         # review surfaced opportunities
job-agent add-url <job-url>   # manually evaluate any role
```

Development sends no email by default — the digest is written to
`output/latest_digest.html`. Live delivery uses Resend when `RESEND_API_KEY` is
set. Required for live delivery: `DIGEST_RECIPIENT_EMAIL` (for example,
`you@example.com`). Optional: `DIGEST_FROM_EMAIL`.

### MVP commands

Run the deterministic fixture slice:

```bash
python -m app.cli scan --fixture data/fixtures/greenhouse/databricks_jobs.json
python -m app.cli review list
```

Run the live Databricks Greenhouse slice:

```bash
python -m app.cli scan
```

The current evaluator is a deterministic development evaluator. It produces the required structured evaluation shape and proves the ingestion, dedupe, health, persistence, review, and digest path. The final LLM-backed evaluator is still a Stage 1 follow-up.

## Documentation

| Doc | Purpose |
|-----|---------|
| [`docs/PRD.md`](./docs/PRD.md) | Authoritative product & build spec (the source of truth). |
| [`ROADMAP.md`](./ROADMAP.md) | Staged delivery, checkpoints, and exit criteria. |
| [`DECISIONS.md`](./DECISIONS.md) | Architecture decision log (ADR-style). |
| [`docs/architecture.md`](./docs/architecture.md) | System design and data flow. |
| [`docs/evaluation.md`](./docs/evaluation.md) | How the fit benchmark works. |

## Guardrails (non-negotiable)

- Nothing consequential happens silently — no application creation, status change, outreach, or submission without explicit approval.
- Deterministic logic first; the LLM only interprets, maps evidence, and explains.
- ATS APIs before scraping; unsupported coverage is published, not faked.
- Secrets stay server-side; no real application or email data in the repo.
- The system serves the job search — it must not become the job search.

## License

Private, single-user project. Not for redistribution.
