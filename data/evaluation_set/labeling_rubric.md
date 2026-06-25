# Live-noise labeling rubric

Goal: label two ~150-role samples so the benchmark can separate **gate recall**
from **digest precision** against your actual judgment.

## Run it

```
job-agent sample-live-noise
# writes data/evaluation_set/live_noise_labels.yaml
# uniform random feed sample, used for gate-recall checks

job-agent sample-live-noise --gate-passers --out data/evaluation_set/live_noise_precision_set.yaml
# writes the gate-passer sample, used for digest precision
```

For each item, fill three fields:

- `expected_recommendation:` → one of `apply_now | consider | stretch | skip | blocked`
- `expected_feasibility:` → one of `viable | sponsorship_required | uncertain | blocked`
- `hard_blockers:` → list, only if a true blocker applies (usually `[]`)

Leave `notes` blank unless a role is genuinely ambiguous — those notes are gold for the next calibration loop.

## The decision tree (run top to bottom; stop at the first that fires)

**1. Is it the right *function*?** (read the title + department first, that's the strongest signal)
Target families: Strategy & Ops · Business Ops · Product Ops · Product Strategy · GTM / Sales Strategy & Ops · RevOps (at the right level) · Business Transformation · Strategic Programs.
Approved stretch: Deployment Strategist / Forward-Deployed Strategy / implementation-heavy AI-transformation **where business problem-solving > production engineering**.
→ If it's clearly **none of these** — Payroll, Legal, pure Sales/SDR/AE, HR/People, Engineering, Marketing, Design, Finance/Accounting → **`skip`**. (Most of the 150 land here. Blast through them.)

**2. Is the *level* right?** Manager / Lead / Senior IC with real ownership and ambiguity.
→ Clearly junior / associate / analyst scope (regardless of a fancy title) → **`skip`**.

**3. Any *true blocker*?** (be strict — explicit evidence only)
- Posting explicitly says no sponsorship / requires existing local work authorization
- Mandatory active security/government clearance you can't obtain
- Production software/ML engineering is a **central** duty
- Genuinely impossible location
→ Set `expected_recommendation: blocked` and add the blocker to `hard_blockers`.

**4. Among the survivors, pick the band:**
- **`apply_now`** — clean target-family fit, right level, feasible, Tier 1/2.
- **`consider`** — on-target but with a real gap, ambiguous scope, or Tier 3.
- **`stretch`** — approved-stretch family (Deployment Strategist etc.), or a true reach worth it only with a warm path / exceptional upside.
- **`skip`** — anything that fits on paper but you wouldn't actually pursue (e.g. strong-fit role at a brand you'd step *down* to take).

## Feasibility (from your policy, DECISIONS #24 — set independently of the recommendation)

| Location | `expected_feasibility` | Note |
|---|---|---|
| EU / Germany | `viable` | citizen |
| UK | `sponsorship_required` | routine — do **not** down-rank the recommendation for this |
| Singapore | `sponsorship_required` | available through sponsoring employers — don't penalize |
| Australia | `viable` (or `uncertain` if timing matters) | ~3 months after arrival |
| US | `sponsorship_required` | and `blocked` **only** if the posting explicitly rules out sponsorship |

## Anchors (from your existing 33-role benchmark)

- `apply_now`: Spotify Markets S&O Manager · Uber Sr Strategy & Ops Manager · Airbnb BizOps & Growth Lead · Personio Sr RevOps & Strategy.
- `consider`: Salesforce Sr Mgr Sales S&O · Mistral AI Deployment Strategist.
- `stretch`: Palantir Deployment Strategist · Stripe S&O Global Partnerships · Roblox Lead Strategic Initiatives.
- `skip`: any Customer Success Manager · GTM Ops **Associate** (junior) · "Manager, RevOps" with associate-level scope · AutoScout24 AI Process Transformation Lead (brand step-down).
- `blocked`: Disney Principal Streaming S&O (US, no sponsorship) · Plaid Integration Ops PM (US) · Roblox PM Consumer Payments (native-PM/technical).

## Speed tips

- Uniform `live_noise_labels.yaml`: most roles are off-function → fast `skip`.
  This catches any good roles the title/department gate would wrongly hide.
- Gate-passer `live_noise_precision_set.yaml`: spend more attention here. This
  is the evaluator/digest precision denominator.
- Don't overthink apply_now vs consider — that fine line is the LLM's job to calibrate. Getting *in-digest (apply/consider) vs out (stretch/skip/blocked)* right is what the precision metric needs.
- One sitting: title → department → 2-second excerpt skim → label. ~150 in well under an hour once the skips fly by.
