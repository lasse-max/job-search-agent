# Roadmap

Staged delivery. Each stage stands alone and delivers value before the next begins. Build only the current approved stage; pause at each checkpoint for owner review. Estimates are focused build-days for an owner using a coding agent — multiply for calendar time.

## Stage 0 — Source audit & setup · _in progress_
**Goal:** know exactly what we can cover before writing adapters.
- Repository + config schemas (done in scaffold)
- Read the master tracker; build a source-coverage matrix for every target company
- Select the first 10–15 Tier 1/2 companies on Greenhouse/Lever/Ashby
- Confirm the labelled evaluation set (≥20–30 roles) — see [`data/evaluation_set/`](./data/evaluation_set/evaluation_set.yaml)

**Exit (Checkpoint A):** every company has a documented source status (`Supported` / `Needs configuration` / `Manual fallback` / `Unsupported`); ≥1 ATS company chosen for the first vertical slice; profile, location, and benchmark configs version-controlled. **Stop and show the owner the audit before broad implementation.**

## Stage 1 — Operational discovery MVP · _next_
**Goal:** a headless service that gives an early-application edge with nothing to maintain but a few adapters.
- Greenhouse / Lever / Ashby adapters + manual URL/text intake
- Normalize, dedupe (idempotent), source-health model
- Deterministic blockers → structured LLM evaluation (4 outputs) → SQLite
- Scan every 6h; one consolidated morning digest; optional urgent alert
- Review CLI + CSV exports

**Checkpoints:** B — one-source vertical slice working end-to-end · C — all three adapters + health + schedule + review CLI · D — benchmark calibration + live digest.
**Exit (PRD §10.2):** the 12-point acceptance test passes, incl. ≥95% recall on owner-labelled Apply/Consider roles and zero silent connector failures. **Stop and wait for explicit approval before Stage 2.**

## Stage 2 — Web app & database tracker · _after owner approval_
Next.js + Supabase Postgres. Opportunity Inbox + Application Tracker, approval gate, immutable event history, controlled migration of the spreadsheet + Stage 1 data. The spreadsheet becomes export/backup only.

## Stage 3 — Gmail-assisted updates · _after Stage 2 is stable_
Read-only Gmail OAuth → classify → suggest status updates in a review queue. No email-derived update changes state before approval. Disconnect/delete flow included.

## Stage 4 — Future (not approved)
CV/cover-letter copilot · interview-prep packs · outreach drafts · conversion analysis by CV version · discovery beyond the watchlist. Never: auto-apply.

---

### Guiding constraints
- Build a working **vertical slice** before broad coverage.
- **Deterministic first**, LLM only for semantics.
- **Fail loudly** — no silent zero-job scans.
- **Human approval** gates every consequential action.
- **Timebox.** Stop after Stage 1 if it is already delivering value; the search comes first.
