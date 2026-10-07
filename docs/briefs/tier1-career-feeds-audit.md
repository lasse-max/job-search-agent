# Codex Brief: Tier-1 career-site feed audit (read-only)

Date: 2026-10-03. Author: Otto. Effort: **high** (it decides the coverage strategy). **Read-only. Enable nothing, write nothing to production, add no secrets.**

## Why

Tier-1 coverage is **12/20 (60 %)**. The Stage 2.0 gate is **≥ 90 % (18/20)**. The eight dark Tier-1s in `config/watchlist.yaml`:

| Company | Current `ats_type` | Notes |
|---|---|---|
| Google | custom | |
| Amazon / AWS | custom | |
| Apple | custom | |
| Uber | custom | |
| Netflix | eightfold | |
| Atlassian | lever (disabled, 0 jobs) | B-20: the real feed is unknown |
| SafetyCulture | lever (disabled) | Empty/404 on recheck |
| NEURA Robotics | jobshop | |

The July plan treated the bespoke sites as reachable **only** through email alerts (B-14), because a scraper per company looked like a maintenance treadmill and a compliance risk. **That premise is untested.**

Most large career sites render their listings from a structured data endpoint the page itself calls: public JSON, Workday "cxs", Eightfold, SuccessFactors and so on. Reading that endpoint once a day is the same pattern as our Greenhouse, Lever, Ashby and SmartRecruiters adapters. If it works for six of the eight, **Tier 1 reaches 90 % without the email pipeline**, and B-14 becomes a fallback.

## Scope

1. **All eight dark Tier-1s** above.
2. **Dark Tier-2s** in `config/watchlist.yaml`. Note which ones share a platform (especially **Workday**), so one adapter can unlock several.

## For each company, report

- **Source:** the platform and the listing endpoint the careers page actually uses (URL pattern, method, pagination, whether a location filter exists server-side). Say how you found it.
- **Fields available:** title, locations, department, posting or updated date (needed for the 21-day policy and the freshness chip), job URL, description (inline or a second request), and a stable job ID for dedup.
- **Catalog size and parity:** total open roles, and roles in our 14 allowed metros plus Dublin. Compare against the visible careers site, so a partial feed can't pass as covered (catalog-parity guardrail).
- **Request budget:** requests per daily scan, including detail pages for new roles only.
- **Rules:** what `robots.txt` says for that path, and anything in the site terms about automated access. Quote the relevant line. Flag "disallowed" plainly. Don't interpret it away.
- **Protection:** any bot protection (Cloudflare challenge, CAPTCHA, signed tokens). **If access needs getting past protection, the answer is "not viable". Do not bypass, spoof or use stealth proxies.**
- **Stability:** a documented or long-lived endpoint, or one likely to change. Note any signs it's internal-only.
- **Verdict:** `adapter` (direct endpoint) · `platform adapter` (Workday, Eightfold and so on, with a list of who else it unlocks) · `render fallback` (needs a headless render or a service like Firecrawl) · `email alerts only` · `manual intake only`.

## Rules for the audit itself

- Polite and minimal: a handful of requests per company, an identifying user agent, no parallel hammering.
- Use the Firecrawl connection only to **inspect** pages if it helps. No Firecrawl in the pipeline, and no API keys in code. If a `render fallback` is recommended, estimate monthly credits. Firecrawl Hobby is $16/month for 5,000 credits.
- No real candidate data in requests. No logging in to any site.
- No commits that change scanning behaviour.

## Deliverable

`docs/source_coverage_tier1_feed_audit_2026-10.md`, containing:

1. The table above with verdicts.
2. The recommended build order, ranked by **Tier-1 coverage unlocked per adapter**, then Tier-2s unlocked (for example: "Workday adapter: 0 T1, 7 T2").
3. Projected tier-weighted coverage if the recommendation is built.
4. What still needs email alerts (B-14) or manual intake.
5. A rough effort estimate per adapter.

**Then stop.** The owner decides what to build. Each new adapter later goes through a PR, Cato review, and a read-only preflight before the owner enables it in batches (existing coverage rules). No source is enabled by this brief.

## Also, as a separate small item (not part of the audit)

Note whether a render service could make **manual intake "Add a role" from a link** work for Google, Apple and other JS-heavy job pages, which today fall back to pasted text. A one-paragraph assessment is enough.
