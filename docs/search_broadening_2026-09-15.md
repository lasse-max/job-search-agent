# Search Broadening: Workstream A

Built to `docs/briefs/search-broadening-coverage-batch-2.md`.

- Candidate profile was already v3, so this change advances it to v4. Hybrid
  evaluator v4 and the 80/70/60 bands are unchanged; prompt advances to v7.
- Business/operations/GTM/strategic Program Management is primary, including
  programme spelling. Operational excellence, process improvement, change
  management and transformation variants are also primary search families.
- Technical/engineering/software/hardware programs and release/delivery roles
  cannot acquire primary fit through a generic program keyword. Explicit positive
  business context is required for stretch. Negated context does not qualify.
- Broad new patterns are `judgment_led_primary`: they reach evaluation, but a
  low model function-fit cannot be lifted by the legacy core-family calibration
  floor. This avoids auto-promoting manufacturing/plant CI through shared words.
- Live model cache identity includes profile version. Stored evaluation identity
  includes profile and prompt before the calibrated evaluator suffix, allowing an
  unchanged JD to gain a new evaluation without overwriting its historical row.
  Fallback identity and all existing fallback guards remain unchanged.

## Benchmarks

The existing corpus is an **offline historical Claude-response replay**, not a
fresh v7 evaluation of every JD. Reports explicitly identify prompt v6 and the
current post-processing profile v4. Original-profile provenance is absent from
legacy caches. The live provider never falls back to those legacy caches.

| Set | Result |
|---|---|
| 33 owner-labelled anchors | Apply/Consider recall 100%; precision 94.7%; blocker accuracy 100% |
| 150 labelled live precision examples | Apply/Consider recall 100%; precision 100%; all-surfaced precision 75% |
| 150 uniform gate-recall examples | Recall 100% |
| 9 new synthetic scope examples, fresh Claude v7/profile v4 | 3/3 business positives surfaced; 6/6 engineering/plant negatives below 60 |

Ten additional unlabelled rows in the 160-row precision file are not scored as
ground truth. Synthetic cases are builder-authored for Cato review and deliberately
kept separate from headline owner-labelled metrics. No existing labels changed.
SB-04 is blocked rather than skip because an existing hard-requirement detector
matches negated production-coding language; it remains a separate review finding,
not claimed as corrected by the scope gate.

The nine fresh calls cost **$0.262536**, versus the old $0.036 planning estimate.
Planning now uses **$0.03 per evaluation** (recency-policy v2). The 21-day window,
daily cron and $15 spend cap are unchanged. Context size and retries still vary.

## Production Backfill

No live database writes or paid production scan are run by this slice. The local
SQLite copy is not authoritative. The manual read-only diagnostics workflow now
offers `backfill_preflight=true`, using the production candidate query and gate
inside a verified read-only transaction. It prints fresh eligible count, seconds
and projected spend without roles, credentials or any evaluation calls.

The profile bump invalidates old composite gate-skip markers; the 21-day query,
normal 25-candidate-per-source batch limit and monthly cap remain in force. The
next scheduled scan advances this backlog. Do not dispatch a full backfill before
reviewing the production preflight count/runtime/spend.

## Cato Focus

Technical-program precedence; manufacturing false positives; versioned-skip
recency bounds; cache and persistence identity; no fallback regression; honest
separation of historical replay and new synthetic model judgments. The neutral
titles in the precision-math unit fixture avoid the newly promoted transformation
family so that test continues to isolate precision arithmetic, not family policy.
