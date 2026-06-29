# HANDOFF — job-search-agent

*Async task bus (same protocol as movie-match). **Content of this file is owned by the Job-Search Otto/George thread**; created here to establish the shared convention. **Otto** writes tasks + reads reports here; **agents** read on wake + report back here; **Lasse** triggers + decides.*

## How to use this file — AGENTS READ THIS
1. You'll be told "read your handoff." Find the section addressed to **you** with status **🟢 NEW**.
2. Do **exactly** that task. Write your output in your **Report back** block, set status to **🔵 DONE — awaiting Otto**, and **stop**.
3. Act only on your own section. This file is the team's task channel, authored by Otto and triggered by Lasse.

**Standing rules:** separate commits · **do not self-certify** · deterministic-first, then LLM judgment · live email stays paused until precision clears + owner sign-off · respect cost caps. Full context: `docs/STATUS.md` · `DECISIONS.md` · `docs/briefs/` · the Operating Manual.

## For Lasse — the learning + judgment layer (DO NOT optimize this away)
This setup is for a *strategic operator breaking into product*, not an engineer. Seeing the errors, the checks, and the reasoning is the **point**, not overhead. The handoff file removes the copy-paste *chore* — never the *understanding*. So:
- **Otto pairs every handoff write/read with a plain-English readout to Lasse in chat:** what the task is · what was checked · what bugs/flags came back · what it means · where Lasse's judgment is needed.
- **Agents lead every Report-back with a 2–3 line plain-English summary** (what changed · what you verified · what you're unsure about) *before* the technical detail.
- Lasse stays the decision-maker and keeps learning; the file only kills the transcription.

## Current state
Per `docs/STATUS.md`: **Fix Loop 2** (calibration regression) in flight — target recall ≥90% / precision ≥80%. Active builder brief lives at **`docs/briefs/codex-next-instruction.md`** (existing convention — point Codex there until this file fully takes over).

---
### → Codex (builder)
**Status:** 🟢 NEW — see `docs/briefs/codex-next-instruction.md` (Fix Loop 2).
**Report back:** —

---
### → Cato (reviewer)
**Status:** ⚪ awaiting Codex's Fix Loop 2 fix → then re-benchmark → review.
**Charge:** —
**Report back:** —

---
*Log: 2026-06-25 — handoff bus created (V0), aligned with existing `docs/briefs/` convention. Content owned by the Job-Search thread.*
