# Source Coverage Expansion Audit — 2026-07-12

Scope: B-27 build-and-audit pass. Public ATS endpoints and official careers pages were checked on 2026-07-12. **No source was enabled and no posting was persisted or LLM-scored.** Current automated coverage therefore remains **31/92 (34%)**: Tier 1 **10/20**, Tier 2 **13/45**, Tier 3 **8/27**.

## What is now ready

| Company | Tier | Source | Current catalog | State | Catalog/parity note |
|---|---:|---|---:|---|---|
| DoorDash | 1 | Greenhouse `doordashaustralia` | 29 | Disabled; owner gate | Australia board is complete for that token. Separate `doordashusa` board returned 454; the Australia token is not global catalog parity. |
| SafetyCulture | 1 | Lever `safetyculture-2` | 33 | Disabled; owner gate | Official careers page points to this live Lever feed; replaces the dead Ashby token. |
| Canva | 1 | SmartRecruiters `Canva` | 223 | Disabled; owner gate | Public list `totalFound` reconciles to 223 fetched details. |
| Glean | 2 | Greenhouse `gleanwork` | 132 | Disabled; owner gate | Live full Greenhouse board; `glean` is the wrong token. |
| Wise | 2 | SmartRecruiters `Wise` | 406 | Disabled; owner gate | Public list count validated. |
| Grab | 2 | SmartRecruiters `Grab` | 338 | Disabled; owner gate | Public list count validated. |
| ServiceNow / Moveworks | 2 | SmartRecruiters `ServiceNow` | 417 | Disabled; owner gate | ServiceNow catalog validated; Moveworks parity is not established. |
| Nearmap | 3 | SmartRecruiters `Nearmap` | 29 | Disabled; owner gate | Full live adapter proof: 29 listed, 29 detailed and normalized in 2.8s. |
| Delivery Hero | 3 | SmartRecruiters `DeliveryHero` | 1,086 | Disabled; explicit volume gate | Largest candidate feed; deliberately a poor first rollout. |

The SmartRecruiters adapter paginates the public list, retrieves every posting detail with bounded concurrency, and fails the source if `totalFound` does not equal the complete detail set. Saved fixtures cover valid, zero, malformed JSON, malformed shape, and id-less postings. The shared HTTP-error and timeout contract now covers all four ATS adapters.

Existing expected-volume health remains the run-time parity alarm: audit catalog counts seed each source's minimum baseline, and a major drop is surfaced as degraded rather than a zero-role success. This catches later feed collapse; it does not make the partial DoorDash Australia token a global catalog.

## Disabled Ashby validation

All non-dead Ashby tokens returned valid current payloads and remain disabled for bounded owner rollout.

| Tier 2 | Jobs | Tier 2 | Jobs | Tier 3 | Jobs |
|---|---:|---|---:|---|---:|
| Aleph Alpha | 10 | Cognition | 74 | Skyscanner | 12 |
| Cohere | 130 | Decagon | 115 | Plaid | 113 |
| DeepL | 24 | Deliveroo | 196 |  |  |
| Encord | 51 | ElevenLabs | 176 |  |  |
| Lovable | 70 | Magentic | 6 |  |  |
| Quantexa | 30 | Synthesia | 73 |  |  |

Vercel's Ashby token still returns a structurally valid zero-job response. It stays manual fallback and must not be enabled. SafetyCulture's old Ashby token also remains zero, but the company is repaired through Lever.

## Tier-1 audit

| Company | Finding | Best next path |
|---|---|---|
| Google | Bespoke public Google Careers search; no supported ATS feed identified. | Dedicated alerts mailbox + manual URL/text. Do not build a Google-only scraper first. |
| DoorDash | Greenhouse found and validated. | First enablement batch after owner approval. Decide whether Australia-only catalog is sufficient. |
| Uber | Public role pages are indexable, but the official list rejects the scanner client; no supported feed identified. | Alerts mailbox first; revisit a custom adapter only with a stable public list contract. |
| Canva | SmartRecruiters found and adapter built. | First enablement batch after owner approval. |
| Atlassian | Dead Lever key confirmed; official custom careers page exposes no stable supported feed. | Alerts mailbox + manual intake; keep B-20 open. |
| Amazon / AWS | Bespoke Amazon Jobs search. | Alerts mailbox + manual intake. |
| Apple | Custom, Workday-backed applicant experience without a reusable public feed identified. | Alerts mailbox + manual intake. |
| Netflix | Eightfold careers site with embedded posting summaries. | Alerts mailbox first; Eightfold is the strongest reusable next-adapter candidate if alerts prove insufficient. |
| SafetyCulture | Live Lever source repaired. | First enablement batch after owner approval. |
| NEURA Robotics | JobShop-hosted catalog; only one current watchlist company uses it. | Alerts/manual intake; a one-company adapter is lower leverage than B-14. |

After the three viable Tier-1 sources above are enabled, Tier-1 automated coverage becomes **13/20 (65%)**, not 14/20: Atlassian has a nominal supported-adapter label but its actual feed is dead. Reaching the **18/20** gate still requires at least **five of the remaining seven** bespoke companies. That makes B-14 alerts-mailbox ingestion a requirement, not optional polish.

## Efficient rollout order

### Batch 1 — highest owner value

DoorDash + SafetyCulture + Canva: **285 catalog postings**. A dry preflight found **146 fresh postings**, **74 gate-passers overall**, and **38 both fresh and gate-eligible** (DoorDash 4, SafetyCulture 3, Canva 31). At the configured assumptions this is approximately **12.7 minutes** of sequential evaluation and **$0.15** maximum first-pass model spend before cache reuse. This batch moves Tier 1 from 10/20 to 13/20.

### Batch 2 — low-volume, one-call feeds

Glean plus Aleph Alpha, Magentic, DeepL, Quantexa, and Encord: **253 catalog postings** across six Tier-2 companies. Ashby costs one HTTP response per company and is operationally cheaper than detail-per-role SmartRecruiters. Enable three to five at a time, then inspect fetched count, fresh gate-pass count, spend, runtime, and digest precision.

### Batch 3 — remaining adapter-ready Tier 2

Cohere, ElevenLabs, Synthesia, Lovable, Cognition, Decagon, Deliveroo, then Grab/Wise/ServiceNow. The three SmartRecruiters feeds total **1,161 postings**, so they belong after the smaller Ashby batch proves the new coverage does not crowd the surfaced set or exhaust runtime.

### Defer

Delivery Hero (1,086 jobs) is low-tier and high-volume. Nearmap, Plaid, and Skyscanner improve Tier 3 but do not help the non-negotiable Tier-1 gate. They should not displace alerts-mailbox work.

## Coverage ceiling from this pass

If every currently validated non-dead source were enabled, the projected ceiling is roughly:

- Tier 1: **13/20 (65%)** — still five short of the gate.
- Tier 2: **29/45 (64%)** — still seven short of the gate.
- Tier 3: **12/27 (44%)** — still four short of the gate.

The efficient sequence is therefore: approve Batch 1, build B-14 against the dedicated alerts mailbox for bespoke Tier-1s, then consume low-volume Ashby candidates. Enabling every large feed first would raise the blended headline while leaving the decisive Tier-1 gap open.
