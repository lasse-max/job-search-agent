# Brief: Scoring v2, score the core job, not the requirement count

Date: 2026-10-07. Owner proposal (Lasse), refined by Otto. Status: **Phases 0 to 2 can start now** (no evaluator change). Phase 3 is an evaluator version bump: a PR, Cato at xhigh effort, then a backfill.

## 1. The problem, confirmed in code

The owner's diagnosis is right, and the cause is visible:

- **Fit is an average.** `config/scoring_policy.yaml` computes fit as a weighted average: role-family fit 30, evidence strength 30, scope and seniority 25, gap manageability 15. Matching eight of ten bullets lifts the average even when the two misses are the job. Gaps carry 15 %.
- **The profile itself feeds the over-scoring.** `candidate_profile.yaml` tells the model to translate commercial operations into revenue-operations evidence, *including territory management*, and lists Salesforce as *"admin, managed territory budgets"*. That's how a role whose core is quota allocation and territory design (Apple Carrier Business Analyst) reads as a strong match. The owner has confirmed he has **not** done quota, territory or sales-comp ownership. **Fix the input first** (charter rule 5).
- **Hidden gates are only partly deterministic.** Location and work rights are code. Language, certification, degree, years in a specific domain and clearance are left to the model's reading, so Mandarin (ElevenLabs Singapore) and a PMI certificate (WesTrac) can slip through.

Known misses to keep in the test set: Amazon AU Global Store Program Manager (rejected after the hiring manager screen), Apple Carrier Business Analyst, Rio Tinto Senior Advisor GIS Data, ElevenLabs Singapore, OpenAI Order to Cash, WesTrac.

## 2. The v2 method (owner spec, with Otto's refinements in bold)

1. **Core job, from the JD alone** (call A, cached per posting by JD hash, never sees the profile):
   - `core_job`: "This person is hired to..."
   - `core_work`: the 2 to 4 things they actually do every week
   - `hard_gates`: location or remote rules, work rights or sponsorship, language, certification, degree, years in a specific domain, clearance
   - `nice_to_haves`
   - `title_mismatch`, with a reason
2. **Gate check: pass / fail / unclear.**
   - **Code decides each gate, not the model.** The model extracts the gate (for example, "Mandarin, required"). Code compares it to profile facts (languages, certifications, degree, years, work rights from `location_policy.yaml`).
   - **`unclear` never auto-fails.** It shows as a flag. Recall comes before precision on things we can't audit (rule 6).
3. **Match each core item** (call B: the core job plus the profile): direct / transferable / stretch / none.
   - **"Direct" must cite an evidence ID from the profile, and code checks the ID exists.** A free-text quote isn't enough, because a quote can be invented. Each profile evidence line gets a stable ID.
   - A "not done" profile item can never be cited as direct.
4. **Verdict computed in code from the ratings** (weakest link, as specified):
   - Any gate fails → **No**
   - Any core item rated none → **No**
   - Any core item rated stretch → **Stretch**
   - All core items direct → **Strong**
   - Otherwise direct with at most one transferable → **Good**
   - Two or more transferable, and no stretch or none → **Good**. **Spec gap, closed here.** The Phase 2 results confirm or change this.
   - Nice-to-haves only order roles *within* a band.
   - `level_fit`: below / match / above, from the existing `estimated_level` logic.

**Output per role:** `core_job`, `core_work[]` (rating, evidence ID, translation note), `gates[]`, `verdict`, `level_fit`, `title_mismatch`, `top_gap` (one line), `why_apply` (one line). Low temperature, strict JSON, schema validated (the B-12 pattern).

**How v2 changes the product:**

- **Bands:** Strong / Good / Stretch / No replace the 80/70/60 fit bands. Within a band, order by number of direct items, then nice-to-haves, then freshness.
- **B-39 merges into v2.** The verdict replaces "Screening odds". "Career value" stays (config facts). The four signals become: **Verdict, Career value, Level fit, and gates plus title mismatch as flags.**
- **Daily email:** `top_gap` next to each role.
- **The app:** the evidence drawer mockup (`docs/design/directions/logbook-pages/01-evidence-drawer.png`) is already designed for this structure.

## 3. Evaluation before anything ships

### Phase 0: owner, now

- **Profile answers (owner, 7 Oct):**

| Item | Answer | How v2 uses it |
|---|---|---|
| Direct reports | Managed **vendor teams and temporary staff**. No permanent direct reports. | "Manage a team of N" with permanent line management → **transferable** at best, never direct. Vendor or contractor management → direct. |
| Financial modelling from scratch | **Adjacent.** Built a spend-forecasting framework from scratch, but it was never the core of the role. | Forecasting frameworks → direct. A core FP&A, deal or valuation modelling job → **transferable**, never direct. |
| Budget management | **Yes.** Managed spend budgets for every region and product area globally (owner, 7 Oct). | Budget allocation, spend tracking, spend forecasting and cost control → **direct**. This is regional *spend*, not sales territories: sales-territory design, quota setting and sales comp stay **not done**. |
| Mining or resources domain | **No.** | A required domain → **gate fail**. A preferred one → nice-to-have only. |
| CSAT or NPS ownership | **No** (confirmed 7 Oct). | Owning a customer-satisfaction target → **stretch**. |
| Management-consulting background | **No** (confirmed 7 Oct). Already in `honest_gaps`. | "2+ years at a consulting firm" as a requirement → **gate unclear** (shown as a flag, not an automatic fail). |

- **Profile corrections, the owner to approve them via the Phase 1 report:**
  - Remove "territory management" from the revenue-operations translation in `positioning`.
  - Reword the Salesforce line, keeping the real experience: *"managed global spend budgets across all regions and product areas in Salesforce (allocation, tracking, forecasting)"*. The word "territory" there meant regions, and it was being read as sales-territory design.
- Write gut calls (apply / maybe / skip) for the eval set **before seeing any model output**.

### Phase 1: Codex, read-only, small

1. **Export the eval set:** about 30 roles from the last two weeks, 10 high / 10 mid / 10 low, plus every applied role with a known outcome. Include the six named misses: if a role isn't in the database, the owner provides the JD text, or Codex uses `data/evaluation_set/jd_cache` if present.
   - **Two files, so reviewers stay blind:**
     - `eval_v2_roles.csv`: id, company, title, location, URL, full JD text.
     - `eval_v2_key.csv`: id, current score, band, reasoning, outcome.
   - Put both in `data/evaluation_set/v2/`. JD text may already be private repo data; no candidate PII beyond what the profile holds.
2. **Profile contradiction report:** every line in `candidate_profile.yaml` that implies a "not done" item (territory, quota, sales comp, ERP, plus the five pending items). List them only; the owner approves the edits.
3. No evaluator, config or workflow change in this phase.

### Phase 2: blind reviews

- **Claude:** a *fresh* Claude chat, not this Otto session, which has seen Sextant's scores. Use the reviewer prompt in the appendix with `eval_v2_roles.csv`.
- **ChatGPT:** the same prompt and the same file.
- **Owner:** gut calls already written, plus real outcomes.
- **Otto compares:**
  - where v1 over-scored and under-scored, and why;
  - where the two reviewers disagree, which points to an unclear spec, not a wrong answer;
  - where the owner's gut call disagrees with both.

**Ground truth is the owner's call and real outcomes.** Two models agreeing measures how consistent the method is, not whether it's right.

### Success bar, to ship v2

- Zero gate failures among the top 10.
- At least 8 of 10 "Strong" roles rated Good or better by both reviewers and the owner.
- No role rejected at the hiring manager stage rated Strong.
- **Recall guard (added):**
  - no role the owner marked "apply" is rated No;
  - at least 80 % of owner-"apply" roles are rated Good or Strong.
  - A weakest-link rule can over-correct, and silently losing good roles is the worst failure for this tool.
- **Regression:** the existing benchmarks (curated 33, uniform 150, gate-passer 150) don't lose blocker recall.

### Phase 3: Codex, PR, Cato at xhigh effort

Implement v2 in **shadow mode**:

- Compute v2 next to v1 for a week. The app and email keep showing v1, and a daily comparison report goes out.
- Store both, with version provenance (ADR #68: live reads version-filtered, history validated).
- Model choice for call A is a test output: run the eval set on Haiku 4.5 and on Sonnet 5. The core-job read is the crux judgement, and only call A (cached per posting) would use the bigger model. Report the cost difference.
- Re-run the 30 roles and the benchmarks. Meet the bar, then the owner flips the switch, then a 14-day backfill with the existing runtime guards.

## 4. Order against everything else

- **Now, in parallel:** Phases 0 to 2. The Tier-1 feed audit continues (read-only).
- **After v2's output shape is final:** the builder brief for the redesign, so the UI isn't built twice.
- **Independent:** the contrast fix PR.

## Appendix: reviewer prompt (paste into a fresh chat with `eval_v2_roles.csv`)

```
You are scoring job postings for one candidate, using a fixed method. Score each row of the attached CSV independently.

Candidate: Strategy & Operations / BizOps professional, about 8 years at Google (Devices & Services), two promotions. Has done: global commercial operations and transformation programmes, product operations, cross-functional programme leadership, executive reporting with SQL/BigQuery/Looker/Tableau, Salesforce administration, managing global spend budgets across all regions and product areas (allocation, tracking, forecasting), pricing execution, forecasting and reporting cadence, partner work, vendor management. Languages: German (native), English (fluent). Work rights: EU citizen; UK and Singapore need sponsorship; Australia via spousal visa; not US. Has NOT done: quota, territory or sales-comp ownership; SAP or ERP rollout; permanent line management (has managed vendor teams and temporary staff only); mining or resources industry; management-consulting firm experience; owning customer-satisfaction (CSAT/NPS) targets. Financial modelling: built a spend-forecasting framework from scratch, but FP&A or deal modelling was never the core job, so treat core modelling roles as transferable at best. Level: L4 to L5 (manager, senior manager, lead, senior IC). No certifications (no PMI/PMP).

For each role:
1. From the job description ONLY (before thinking about the candidate):
   core_job: one sentence, "This person is hired to..."
   core_work: the 2 to 4 things they actually do every week
   hard_gates: location or remote, work rights or sponsorship, language, certification, degree, years in a specific domain, clearance
   title_mismatch: yes or no, with a reason
2. Gate check: pass / fail / unclear for each gate.
3. Rate each core_work item against the candidate: direct (has done it), transferable (adjacent, say what translates), stretch (not done, learnable), none.
4. Verdict from the weakest core item: any gate fail = No; any item none = No; any item stretch = Stretch; all direct = Strong; otherwise Good.
5. level_fit: below / match / above. top_gap: one line. why_apply: one line.

Return one JSON object per row: {"id", "core_job", "core_work":[{"task","rating","why"}], "gates":[{"gate","result"}], "title_mismatch", "verdict", "level_fit", "top_gap", "why_apply"}. Do not guess hidden information; if the JD is silent, mark the gate unclear.
```
