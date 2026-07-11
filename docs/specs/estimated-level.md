# Spec — Estimated Level (Google-equivalent)

**Status:** approved by owner 2026-07-10 · **Owner:** Otto · **Build:** folds into Calibration Sweep 3 (evaluator) + a small A2 UI change.

## Problem
Over-level roles surface without being legible as such (live example: **Quantium — "Executive Manager, Financial Services"**, Tier 3, fit 70, sitting in Consider — "Executive Manager" in Australian corporate reads around senior-manager/director, likely above the owner's band). Today the system handles seniority as a **crude title-based penalty that suppresses** the role. Two problems with that:

1. **Titles are meaningless without context.** Ladders differ by company, size, and geography (Meta IC5, Amazon L6 ≈ Google L5, Australian "Executive Manager", startups have no ladder). A title-token penalty is noise.
2. **It optimizes the wrong thing.** The costs are asymmetric: a too-senior role that surfaces costs the owner ~5 seconds to skip; a strong role silently filtered out costs an opportunity he never learns about.

**Salary is not a viable primary signal** for this search: the owner targets W. Europe / UK / Singapore / Australia, where most postings carry no pay band. (US states and expanding pay-transparency rules mean coverage should improve over time — keep salary as a cross-check where present, but never build the detector on it.)

## Decision (log to DECISIONS.md)
> **Seniority is a FLAG, not a FILTER. Levels are normalized to the owner's Google ladder. Recall > precision on seniority.**
> The evaluator estimates a role's Google-equivalent level and *shows* it with its reasoning. It may modestly down-rank an out-of-band role; it must **never suppress** one. The owner decides.

This is consistent with the product's core stance — the system surfaces and explains, the human decides (PRD §11.2, DECISIONS #5) — and with strict monotonic bands (#61): the level delta feeds the *fit score*, it does not create a separate band override.

## The feature
A role's estimated level, expressed **in Google terms** (the owner's native reference frame, ex-Google, ~8 yrs), because "what level is this" is meaningless in the abstract — "what would this be at Google" is instantly actionable.

### New evaluator outputs
- `estimated_level` — coarse scale: **L3 · L4 · L5 · L6 · L7+ · unknown**. No false precision.
- `level_confidence` — 0–100.
- `level_rationale` — the evidence, one or two lines (e.g. *"requires 12+ yrs; manages a team of managers; reports to CFO"*).

Slots in as an additional dimension of the existing hybrid LLM evaluator (semantic judgment with evidence — the same shape as `alignments`/`gaps`).

### Signals (ranked; none depend on salary)
1. **Years of experience required** — "5–8 yrs" vs "12+ yrs". The strongest universal signal; present in nearly every JD.
2. **Management scope** — senior IC / manages ICs / **manages managers** (manager-of-managers ⇒ L6+).
3. **Reporting line** — reports to a VP or the CEO ⇒ senior; reports to a Head of X ⇒ in-band.
4. **Title × company size/stage** — the essential normalization: "Head of Strategy" at a 40-person startup is L4–L5 work; at a 5,000-person company it's a VP. Title alone is noise. (Matches the owner's own standing rule: *"Head of is too senior — unless small start-up."*)
5. **Posted salary band, when present** — a strong cross-check where it exists (parser already built, `f965590`/`1cd4066`). Bonus, not foundation.

### Scoring
- Compute the **delta from the owner's target band (L4–L5)**.
- Out-of-band ⇒ **modest fit down-rank** — enough to sort it below in-band peers, *not* enough to bury it below the surfacing threshold.
- **Replaces** the current crude title-based over-level suppression / hard cap.
- Bands stay strict and monotonic — fit remains the single source of truth; only the magnitude of one penalty changes.

### Display
- **Role card:** a chip — `est. L6 ▲ above band` — colour-coded: in-band neutral, above-band amber, below-band grey. Low confidence ⇒ render as `est. L? · low confidence` rather than guessing.
- **Slide-over:** the `level_rationale` alongside alignments/gaps.
- **Profile page (A4):** display the target band (L4–L5) so the comparison is legible.

## Guardrails
- It is an **estimate** and will be wrong sometimes — startups (no ladder) and cross-geography titles especially. **Always show confidence.**
- **Never hard-blocks.** No level estimate may move a role to `skip`/`blocked` on its own.
- **Coarse scale only.** L4/L5/L6/L7+, never "L5.3".
- Calibrated like everything else: owner disagreements from daily triage go to `live_calibration_notes.md` and tune it.

## Non-goals
Precise numeric levelling · compensation estimation · modelling other companies' internal ladders (we translate *to* Google, we don't reproduce theirs) · using level as a blocker.

## Success criteria
- The owner can triage seniority in ~2 seconds from the card, without opening the JD.
- **Zero good roles silently dropped for level** (the recall bar).
- Estimated level agrees with the owner's judgment on a labelled sample often enough to be trusted (measure once there's live triage history; target ≥80% within ±1 level).
