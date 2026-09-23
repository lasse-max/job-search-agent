# Pre-Backfill Calibration: Cato Handoff

Date: 2026-09-23. Status: built for independent review; full backfill held.

## Scope

One calibration commit for the owner's request: fix company-boilerplate false
blocks, resolve districts for the existing 14-city allowlist, and submit the
[Deliveroo Greenhouse proposal](deliveroo-greenhouse-replacement.md) alongside.
No source enablement, live database writes, migration, paid model calls or workflow
dispatch belongs to this commit. Deliveroo and Delivery Hero remain disabled.

## Mechanism

- Shared requirement scoping recognizes qualification, responsibility, company,
  optional and legal sections, including adapter-flattened text. Candidate-owned
  requirements remain enforceable even when placed after a company/legal heading.
  Headingless evidence keeps the existing technical-depth and local-negation rules.
- Government/defense exclusion requires title/function, qualification or nearby
  duty/mandatory context. Exporter obligations and EEO military/veteran status do
  not establish the candidate's role scope. Clearance checks use the same scoped
  fragments, not a separate whole-JD regex. No employer-name exemptions.
- Qualification context persists across bullets; generic responsibilities do not
  make an otherwise optional degree mandatory. Graded preferences such as a
  'strong plus' stay attached to comma-separated credential alternatives, while a
  following mandatory coding clause blocks. Inline company 'requirements' nouns
  do not create headings; employee/employment clearance conditions remain enforced.
- `location_policy_v4` contains a curated district map for all 14 current cities,
  with primary-source links. Search-only expansion runs before location matching
  and market feasibility. Stored locations, material hashes and display text stay
  unchanged. Matching is per location, token-boundary aware and conservative about
  ambiguous names/foreign context. This is not an exhaustive address geocoder.
- Four already-allowed European cities missing from market lookup are mapped to
  the existing policy; no new city or authorization rule is introduced.
- Location-policy revision reopens only fresh eligible records under existing
  backfill rules. Persistence now includes location/scoring-policy versions in the
  model key so corrected evaluations append rather than collide with old history.
  The calibrated `|hybrid_claude_v4` suffix, prompt and profile versions are unchanged.

## Review Focus

1. ServiceNow export-control and Plaid EEO regressions, both multiline and flattened;
   generic company/platform prose must not silently become a qualification heading.
2. Genuine government titles, required clearance/residency, technical degrees and
   production coding still block. Optional/negated statements do not erase a
   separate real requirement. No label edits, per-role or per-employer exceptions.
3. One gate regression per city; false substring matches, ambiguous Docklands,
   conflicting countries and cross-location context do not gain a city alias.
4. Old policy skips reopen only inside the 21-day window. Two policy revisions
   persist distinct historical evaluations; replay does not duplicate either.
5. Review Deliveroo's proposal separately: preserve identity, age, human decisions
   and new-role alert semantics across the ATS move. This is not permission for a
   config-only switch.

## Verification

- Python 3.12: `python -m unittest discover -s tests` passes **269 tests**;
  focused final requirement/evaluator regressions pass 50 tests, and the 14-city
  alias matrix also checks feasibility equivalence with each canonical city.
- `python -m ruff check .` and `git diff --check` pass.
- Web: tests (3/3), lint, typecheck and production build pass; generated Profile
  config was regenerated and the YAML/JSON drift check passes.
- Public full-JD rechecks: ServiceNow posting `744000147147349` (Singapore) and
  Plaid posting `a53bfb4f-ae6a-4d3f-8267-32978ccfc5c6` (London) pass the relevance
  gate; their exporter/EEO boilerplate triggers neither technical nor clearance/
  government blockers. No paid provider or database writes were used.
- Final `python -m app.cli benchmark` passes offline. Curated 33: Apply/Consider
  recall **100%**, precision **94.7%**, blocker accuracy **100%**, fit-band agreement
  **90.9%**, feasibility **100%**, exact recommendation **20/33 (60.6%)**.
  Uniform 150: gate recall **100%**. Gate-passer 150: Apply/Consider recall
  **6/6 (100%)**, precision **6/6 (100%)**, all-surfaced including Stretch precision
  **6/8 (75%)**; positive blocker cases **3/3**. The small positive denominator is
  not evidence of broad real-world perfection.
- Reports identify evaluator and label sets. This remains explicitly **historical
  cached Claude replay**, not a newly paid profile-v4/prompt-v7 model benchmark.
  Labels, cache snapshots, scoring bands and thresholds are unchanged. Gate-recall
  and precision per-row reports are republished; curated reports are byte-identical.

## Cost And Launch Gate

Owner-reported MTD is **$11.63** on September 23, not a fresh provider reconciliation
performed by the builder. The stated estimates give **$11.63 + $9 + $3.39 = $24.02**,
leaving **$5.98** under the $30 cap before retries/further routine discovery.
These figures are a planning scenario, not a guaranteed month-end bill.

The held 255-role count and the 113 new-feed candidates are dated snapshots, not
the launch plan. Alias/boilerplate fixes can admit more roles, while recency,
deduplication and intervening scheduled scans can reduce the outstanding set.
At the existing 20-second estimate, 368 evaluations would take about 123 minutes
plus fetching/database overhead. **Refresh count, ETA and incremental spend from
the authoritative production state after Cato clearance and before the single
owner-authorized full backfill.** Do not blindly score both snapshots or count
already processed roles twice. Keep the cap and cost ledger active.

Daily scheduling is unchanged. Its normal bounded stale-evaluation processing is
not the held full-backfill dispatch; pushing the policy revision makes it eligible
on the next scheduled run. Cato review is requested before that run. No manual
scan or full-backfill dispatch is launched here.
