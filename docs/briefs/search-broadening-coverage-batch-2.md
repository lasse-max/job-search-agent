# Codex Brief — Search broadening (Program Mgmt + Transformation) + Coverage batch 2

**Owner request 2026-09-15:** "get more roles connected, and include more Program Manager and Business Transformation roles."
Two workstreams, separate commits. Effort: **high** for the search change (it's gate logic with a flood risk), **medium** for coverage.

---

## Workstream A — Broaden the search (config + gate; separate commit)

### Why
The owner's own performance record (`docs/`-referenced reviews) repeatedly cites program-management capability — he program-managed the Fitbit cutover (93/96 partners), the deductions remediation ($50M→$11M), and the Zenith rollout. Yet the current gate barely lets program roles through, and "transformation" matches only one literal phrase.

### A1. Promote Program Management from stretch → **primary** (scoped)
Currently `approved_stretch_families` + narrow patterns (`strategic program manager`, `business|transformation program|project manager`, TPM only with business-context words within 500 chars). A plain **"Senior Program Manager"** or **"Operations Program Manager"** never matches.

- Add **"Program Management (business / operations / GTM / strategic programs)"** to `primary_role_families`.
- Broaden `role_family_patterns.primary` to catch, e.g.:
  `\b(?:senior |sr\.? |lead |principal )?program(?:me)? manager\b`, `\bprogram(?:me)? management\b`, `\bprogram(?:me)? lead\b`, `\b(?:operations|gtm|go-to-market|business|strategic|commercial|transformation) program(?:me)?s?\b`, `\bpmo\b` (UK "programme" spelling throughout).
- **Scope guard — keep, do not loosen:** engineering-delivery program roles stay *stretch* with the existing business-context requirement. Explicitly keep as stretch/deprioritized: **Technical Program Manager / TPM**, **Engineering Program Manager**, **Software/Hardware Program Manager**, **Release/Delivery Manager**, anything whose scope is SDLC delivery. The owner wants a *way in* via business programs, not a flood of engineering TPM reqs. Add negative examples to the test set.

### A2. Broaden Business Transformation
Currently only `\bbusiness transformation\b`. Extend to the transformation / operational-excellence family:
- `\b(?:business|operational|operations|process|commercial|finance|digital|enterprise) transformation\b`, `\btransformation (?:manager|lead|program(?:me)?|office)\b`, `\boperational excellence\b`, `\bprocess (?:excellence|improvement|optimi[sz]ation)\b`, `\bcontinuous improvement\b`, `\bchange management\b`, `\bbusiness process\b`.
- **Noise guard:** `continuous improvement` / `process excellence` skew toward Lean-Six-Sigma manufacturing roles. Don't exclude them at the gate (recall > precision, owner rule) — let the **evaluator's function-fit + level scoring** do the filtering, and add 2–3 manufacturing/plant-CI roles to the benchmark as expected-`skip` counterexamples so we can see the noise level.

### A3. Make the change actually take effect
- **Bump the candidate-profile version** (`candidate_profile_v2` → `v3`) so previously **gate-skipped** program/transformation roles get re-evaluated. Per migration 006, versioned skips re-evaluate on a profile-version change; the **21-day recency policy** bounds it to fresh roles, so this is cheap. **Report item count + ETA + projected spend before running**, as always.
- Re-run cached + live benchmarks. Expect *more* surfaced roles; verify bands hold and precision doesn't collapse. Log the family promotion in `DECISIONS.md`.

---

## Workstream B — Coverage batch 2 (config; separate commit)

Per `docs/source_coverage_rollout_2026-09-08.md` "Most Efficient Next Work":
1. **Next Ashby batch, 3–5 feeds, Tier 2 before high-volume Tier 3** (e.g. hold Delivery Hero). Run the standard **count / ETA / cost preflight** and report before enabling. Do **not** enable without the owner seeing the preflight.
2. **Re-check SafetyCulture** (still empty) — if a working feed exists now, enable; otherwise leave disabled with a note.
3. **B-14 email-alert ingestion for the bespoke Tier-1s** (Google, Apple, Amazon, Uber, Netflix, Atlassian): build the parser against the **dedicated alerts mailbox** design in `coverage-expansion.md`. **Owner-gated:** this can only be built and tested once the owner has created the mailbox and it has accumulated alert emails. If the mailbox doesn't exist yet, scaffold the ingestion and stop; do not point it at a personal inbox.

Report resulting tier-weighted coverage (target T1 ≥90% · T2 ≥80% · T3 ≥60%).

---

## Standing rules (unchanged)
Migrations: Codex writes, owner applies by hand. Never write to the live DB. Blocker-class findings stay on the board until fixed or formally accepted. Report count + ETA before any long job. Push, back to Cato.
