# Retired Sources And Controlled Backfill: Cato Handoff

Date: 2026-09-28. PR only. No paid backfill, retirement or migration applied.

## Launch Status

The owner cleared `18d00e0`, but the new console-MTD field in the launch request
still contains `[paste today's number]`. The builder asked for the actual number;
neither the previous $11.63 nor the incomplete cached ledger is a fresh substitute.

The existing main workflow restores a cached spend ledger and has no reconciliation
input. Updating a local ignored file cannot seed Actions. This PR therefore includes
the minimal reviewed launch plumbing; it is not pushed onto production to bypass
the owner's new PR rule. The launch remains held for the fresh number and approval/
merge of that plumbing. Deliveroo Greenhouse stays excluded.

Read-only preflight on reviewed `main`:
[run 36417083490](https://github.com/lasse-max/job-search-agent/actions/runs/36417083490)
completed with server-enforced `transaction_read_only=on`: **46 pending roles,
920 seconds (15m20s) scoring, $1.38**, under the 21-day policy. This replaces the
dated 255-role estimate. That older preflight does not report inactive-source
counts; the extended PR preflight must supply those before launch. Its new v5
policy also reopens fresh older-policy skips, so do not reuse 46 as its launch count.

Recent completed scan artifact ledgers were $6.028048 (Sep24), $6.856984 (Sep25),
$7.562933 (Sep26), and $8.439607 (Sep27). The verified daily deltas are $0.828936,
$0.705949, and $0.876674. These are incremental planning evidence, **not console
MTD**. Reserve **$3.30** for up to three remaining September scans: maximum observed
daily cost times three, plus 25%, rounded up. Those scans took approximately
125/120/112 minutes end to end, so scoring-only ETA omits substantial fetch/DB time.

Once current MTD is supplied, calculate `MTD + fresh pending spend + $3.30` plus any
new-feed work not covered by that plan. If it exceeds $30, the owner has authorized
a sufficient September-only override in `config/model_budget.yaml`; report the
chosen amount first. October returns to the default $30. No override is guessed here.

## Changes For Review

- Python live digest/review/detail/opportunity exports/sampler/backfill and web
  matches/detail/shortlist/all-role audit exclude disabled/retired, disabled-company,
  unknown-auto and replaced ATS/key sources. Current failing/degraded feeds remain
  visible. Watchlist checks protect reads before stale DB metadata is reconciled.
- Owner-selected manual roles are independent of automatic watchlist enrollment.
  Manual and automatic sources no longer disable each other during upsert. An
  explicitly disabled manual source remains hidden and is visible in reconciliation.
- Source coverage/run exports, backups and immutable Applied history remain intact.
  These are historical/audit reads, not a live opportunity feed.
- `010_stage15_active_source_reads.sql` is owner-applied after review. Both it and
  the runtime canonical `001` view enforce source state and owner/RLS boundaries;
  a cross-check prevents the next scan's schema bootstrap from undoing 010. SQL
  cannot read YAML identity directly; web/Python checks plus explicit retirement
  cover unsynchronized config. Shortlist/new-application RPCs inherit the view guard.
- Generic export-approval noun phrases are removed before government-scope checks,
  regardless of whether the subject is applicants, the company or the role. A real
  adjacent clearance/government duty remains enforceable. `location_policy_v5`
  also adds state/canton context codes, including Oerlikon/ZH, and reopens only fresh
  stale-policy rows. No employer exceptions or model-version bump.
- Login help identifies the owner's Supabase password, not their email password;
  no signup, reset, credential exposure or authorization change.
- Actions can replace the restored current-month ledger from dated console MTD.
  It never adds MTD to tracked spend. Reruns cannot reset subsequent spend; invalid,
  nonfinite, negative or stale inputs fail before scanning. A full backfill needs
  current reconciliation proof. Receipt cache is separate so adding its path does
  not invalidate the existing ledger cache's hidden version. Cache state remains
  best-effort, not durable billing accounting.

## Explicit Retirement

Default command is read-only, including server-enforced read-only Postgres or
SQLite `mode=ro`/`query_only`. It never creates a missing SQLite DB:

```sh
job-agent retire-sources --report output/source_retirement.json
```

The report identifies each source, exclusion reason, open posting IDs and a plan
hash. Review the entire report, including any previously disabled manual sources,
before the owner explicitly applies it with the production connection configured:

```sh
job-agent retire-sources --apply-report output/source_retirement.json
```

Apply rechecks identity/current inactivity and new postings under a short write
lock. A stale/modified plan refuses; a successful replay changes zero rows. It sets
postings unavailable and source health disabled, never deletes data or changes
review decisions, dates, evaluation history or application snapshots. Any new
postings after the report require another report. No automatic retirement is added
to scanning. No builder production retirement or schema writes were performed.

## Review Gates

1. Source predicates operate before live query limits and retain failing/degraded
   sources and legitimate manual roles. Applied history is not version/source-filtered.
2. Retirement is report-first, atomic and retry-safe; no hidden historical deletion.
3. Export variants no longer false-block, but genuine mixed-clause disqualifiers do.
4. Console reconciliation replaces, preserves other months and cannot be replayed
   to lower post-seed spend. Month overrides expire and the daily cron stays 06:00 UTC.
5. Re-run the extended **read-only** production preflight, inspect excluded-source
   counts/report, then use fresh item count, full ETA and cost for the one paid run.
   Do not launch it from the unreviewed PR branch or enable Deliveroo.

Offline cached benchmarks pass unchanged: curated33 recall100%, precision94.7%,
blocker100%, exact20/33; uniform150 gate recall100%; gate-passer150 Apply/Consider
recall/precision100% (six positives), all-surfaced precision75%. These are historical
Claude-cache replays, not fresh paid prompt/profile calibration. Labels/caches unchanged.

Local validation: Python 3.12 full unittest suite passed (288 tests), followed by
22 focused tests after the final manual-source regression. Ruff and diff checks
pass. Web tests, lint, typecheck and production build pass; Profile JSON/YAML drift
checks pass. GitHub CI and the extended production preflight are recorded below
after the review branch is pushed. These builder checks do not replace Cato review.

## Production Evidence For The PR

Code commit: `a6d1507`. [PR #1](https://github.com/lasse-max/job-search-agent/pull/1).
Both Python/Ruff and web CI passed in
[run 36418815009](https://github.com/lasse-max/job-search-agent/actions/runs/36418815009).

The extended read-only production preflight completed in 3m39s:
[run 36418831448](https://github.com/lasse-max/job-search-agent/actions/runs/36418831448),
2026-09-28 12:01 UTC. It uses the **proposed PR policy**, not reviewed main:
`hybrid_claude_v4|candidate_profile_v4|location_policy_v5|scoring_policy_v2|recency_policy_v2`.

| Planning result | Count / estimate |
| --- | --- |
| Fresh current-source roles selected | 438 |
| Disabled/retired-source roles in selection | 0 |
| Fresh stale candidates excluded from inactive sources | 45 |
| Of those, relevance-gate passers excluded | 18 |
| Scoring-only ETA | 8,760 seconds / 2h26m |
| Scoring-only spend estimate | $13.14 |
| Practical end-to-end planning window | Roughly 4-5 hours, including recent fetch/DB overhead |
| Remaining September scan reserve | $3.30 |
| Month-end projection before unplanned feed growth | Actual console MTD + $16.44 |

The additional policy revision makes existing fresh older-policy evaluations/skips
stale again, explaining why this is larger than main's 46-role plan. Do not launch
the main plan and then another PR plan: after review/merge, reconcile fresh MTD,
refresh this read-only count, then launch once. The $30 cap covers this estimate only
if actual MTD is at most $13.56. No September override has been set without that input.

All 45 excluded fresh candidates (18 gate passers) are from disabled Deliveroo
Ashby. Old Mistral Lever, Black Forest Labs Greenhouse and disabled Atlassian each
have zero fresh stale candidates. Deliveroo Greenhouse remains out.

The separate all-age retirement report identifies **411 open historical-source
postings**, not 411 backfill candidates:

| Source | Open postings proposed for closure |
| --- | --- |
| Mistral AI, old Lever / mistral | 172 |
| Black Forest Labs, Greenhouse / blackforestlabs | 17 |
| Deliveroo, disabled Ashby / deliveroo | 222 |

[Download the reconciliation artifact](https://github.com/lasse-max/job-search-agent/actions/runs/36418831448/artifacts/10967294662).
Its source counts sum to 411. Plan hash:
`45fbb631dfe1ba32f352cd0d1b85991f25a176befb902656c6416f3321a4e458`.
No disabled manual source appeared in this production report. No retirement,
migration, ledger replacement, cap increase, model call or email was performed.
