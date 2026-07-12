# Codex Brief — Coverage Expansion (B-27) · Stage 1.9

**The largest recall gap in the project.** The agent scans **31 of 92** watchlist companies (34%). Tier 1 is **10/20 — half the companies the owner would actually accept an offer from are invisible.** Dark Tier-1s include **Google · Apple · Amazon/AWS · Netflix · Uber · DoorDash · Canva · Atlassian · SafetyCulture · NEURA Robotics**. Uber is an `apply_now` anchor in the labeling rubric — and the agent has never once looked at it.

**Framing (owner + Otto, 2026-07-11):** *calibration improves the precision of what you see; coverage determines what you can see.* We have spent weeks sharpening a lens pointed at a third of the room.

## Targets — tier-weighted, NOT blended (owner gate before Stage 2.0)

| Tier | Now | Target | Why |
|---|---|---|---|
| **Tier 1** | 10/20 (50%) | **≥90%** (18/20) | The companies the owner would actually take. Non-negotiable. |
| **Tier 2** | 13/45 (29%) | **≥80%** | The solid middle. |
| **Tier 3** | 8/27 (30%) | **≥60%** / best-effort | Low value — `brand_floor` says Tier 3 is only worth it for unusually strong fit. Don't burn engineering time; the Ashby batch likely carries it. |

**A blended percentage is a vanity metric.** Climbing to 59% by adding Tier-2/3 feeds while every dark Tier-1 stays invisible is *worse than useless* — it makes the Profile page report progress that the owner cannot act on. Report and gate on **tier-weighted** coverage.

## Three tracks

### Track 1 — The quick win (do first; already scoped by Codex)
Repair 3 existing-adapter sources (DoorDash, SafetyCulture, Glean) · validate and enable the **14 audited Ashby feeds** in bounded batches of 3–5 · add **SmartRecruiters** (currently appears to unlock Canva, Wise, Grab, ServiceNow, Nearmap, Delivery Hero). Roughly doubles blended coverage. **Roll out in small batches** and watch volume, LLM spend, runtime, and connector health after each — a bad feed that 10×'s the posting count will blow the spend cap.

### Track 2 — Tier-1 ATS audit (highest value per hour)
The 61 dark companies are marked `ats_type: unknown` because **the Stage-0 audit never checked** — not because it checked and failed. **Systematically audit all 10 dark Tier-1s** and identify each one's actual ATS. It is entirely plausible several are already on Greenhouse/Lever/Ashby and are missing nothing but a `source_key` — free wins on the highest-value companies. Sequence adapter work by **which unlocks the most Tier-1s**, not by which unlocks the most companies.

### Track 3 — Email-sourced discovery (B-14) — the only path to the unscrapable
Google, Apple, and Amazon run bespoke career sites. Building and maintaining a scraper per company is a treadmill and a compliance risk. **The Tier-1 ≥90% target makes B-14 a requirement, not a someday.**

**Design change (owner decision 2026-07-11): a dedicated alerts mailbox, not the owner's personal inbox.**
- The owner creates a **separate email account used ONLY to subscribe to job alerts** — never for applications, never given to recruiters.
- **Least privilege:** the agent's Gmail OAuth read scope is then confined to a mailbox containing nothing but job alerts — no bank mail, no personal correspondence, no live recruiter threads. This matches the discipline applied everywhere else (read-only MCP, RLS owner-gate, no service-role key).
- **Clean signal:** ~100% of that mailbox is job alerts, so the parser has almost no noise to filter.
- **Account-locked alerts** (e.g. LinkedIn, tied to the owner's identity) are handled with a **forwarding filter** from the personal account, not a duplicate account.
- Subscribe it to: the dark Tier-1 career sites (Google, Apple, Amazon, Netflix, Uber, DoorDash, Canva, Atlassian) + aggregators (Otta / Welcome to the Jungle, Built In, LinkedIn via forwarding).
- Parsed roles run through the **same evaluator and the same gates**, flagged `source_type: "email"`. Compliant: reads the owner's own mail via OAuth — **not** LinkedIn scraping (an explicit non-goal).

**Alerts accumulate while the ingestion is built**, so the owner should create the mailbox and start subscribing *now* — it yields a real corpus to test the parser against instead of waiting.

## Guardrails
- **Catalog parity:** binary "enabled" is not coverage. A feed that returns 12 of a company's 300 roles *overstates* recall. Add a parity/sanity check per source (expected vs fetched volume) so a partial feed can't quietly masquerade as covered.
- **Fail loudly** — no silent zero-job scans (existing principle; Atlassian's dead feed proved its worth).
- **Spend + runtime:** each new batch of sources multiplies postings → LLM spend. Watch the monthly cap after every rollout.
- **Manual URL/text intake stays an explicit bridge**, not counted as automated coverage.

## Definition of done
Tier-weighted targets met (T1 ≥90% · T2 ≥80% · T3 ≥60%), reported on the Profile page **by tier**, with catalog-parity checks in place and connector health green. This is the gate to Stage 2.0.
