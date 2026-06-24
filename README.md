# Automated Job Search System

Stage 0 repository scaffold for a private, human-in-the-loop job search agent.

The product goal is to find strong roles at an approved company watchlist within hours of publication, evaluate them against the candidate profile and location policy, and keep the application pipeline accurate without silent consequential actions.

## Current Stage

Stage 0 only:

- Repository structure created.
- Current tracker inspected read-only.
- Company source-coverage audit produced.
- Candidate profile, location policy, scoring policy, and draft benchmark configuration added.
- No broad adapter implementation, Gmail integration, web app, document generation, or tracker mutation has started.

## Stage 0 Artifacts

- `docs/source_coverage_audit.md`: readable audit summary, selected first coverage candidates, and proposed first vertical slice.
- `output/source_coverage.csv`: full source-coverage matrix.
- `config/watchlist.yaml`: private watchlist config generated from the tracker and public feed probes.
- `config/candidate_profile.yaml`: candidate positioning and evidence config.
- `config/location_policy.yaml`: explicit market authorization policy.
- `config/scoring_policy.yaml`: recommendation and blocker rules.
- `data/evaluation_set/initial_benchmark.yaml`: draft benchmark labels inferred from the tracker. These require owner confirmation before acceptance testing.

## Proposed First Vertical Slice

Recommended first slice: Databricks via the Greenhouse feed.

Why: Databricks is Tier 1, has a warm path in the tracker, has active Deployment Strategist roles in target geographies, and exposes a supported public feed. The first slice should fetch one company, normalize postings, deduplicate, apply deterministic blockers, evaluate one eligible role, persist it, and write a local digest.

Backup if the Databricks feed is too noisy: Mistral AI via Lever.

## Local Setup

This is not fully implemented yet. Stage 1 will add runnable services after owner approval.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Read-only tracker inspection:

```bash
python scripts/import_tracker.py "/path/to/tracker.xlsx"
```

## Privacy Note

This repository currently contains private job-search configuration. Before publishing any portfolio version, sanitize company priorities, active pipeline data, warm-path indicators, contacts, and real application details.

