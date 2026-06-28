# Automated Job Search System
## Final Product Requirements Document and Codex Build Plan

**Owner:** Owner  
**Version:** Final v4 — 23 June 2026  
**Primary builder:** Codex under human review  
**Purpose:** Find strong roles at a fixed company watchlist within hours of publication, evaluate them using Owner's actual career strategy, and maintain an accurate application pipeline without silent consequential actions.

---

# 0. Instructions to Codex

Treat this document as the authoritative product and implementation specification.

1. **Build only the current approved stage.** Start with Stage 0 and Stage 1. Do not begin the full web application, Gmail integration, or document-generation features until the prior stage passes its acceptance tests and the owner explicitly approves progression.
2. **Prioritize a working vertical slice over broad coverage.** First prove one company source end to end: fetch → normalize → deduplicate → evaluate → persist → generate digest. Then add adapters and companies.
3. **Use deterministic logic wherever possible.** The LLM is only for semantic interpretation, candidate-evidence mapping, gap analysis, and concise explanation.
4. **Do not mutate the original Excel tracker in Stage 1.** Treat it as input/reference. Store system state in SQLite and export CSV files when needed. Stage 2 performs a controlled migration to Postgres.
5. **Nothing consequential happens silently.** The system must not submit applications, contact recruiters, add applications, change application status, or generate final documents without explicit approval.
6. **Fail loudly.** A broken connector must never look like a successful scan with zero jobs. Record health, counts, errors, last successful run, and expected-volume anomalies.
7. **Keep secrets server-side.** Never commit API keys, OAuth tokens, email credentials, candidate documents, or real application data.
8. **Prefer maintainable adapters over scraping.** Use public ATS feeds first. Publish unsupported coverage rather than adding brittle browser automation unless the owner approves a specific high-value exception.
9. **Keep the code migration-ready.** Stage 1 uses SQLite, but the data model and repository boundaries must permit a later migration to Supabase/Postgres without rewriting business logic.
10. **Document assumptions.** When a requirement is ambiguous but non-blocking, choose the simplest reversible option and record the assumption in `DECISIONS.md`. Ask the owner only when a decision is consequential or blocks implementation.

---

# 1. Product summary

## 1.1 Problem

High-quality roles at a finite list of target companies appear irregularly, use inconsistent titles, and may close quickly. Manual career-page checks are repetitive, generic alerts are noisy, and the current spreadsheet requires manual maintenance. The system must detect opportunities early, evaluate them using Owner's actual career history and constraints, and help him act before roles become stale.

## 1.2 North-star outcome

> Surface the best newly posted roles at approved companies within hours, explain fit and gaps with evidence, and reduce manual application tracking while preserving human control.

## 1.3 Real differentiator

This is not a generic CV-to-job-description matcher. Its value is that it encodes and tests Owner's specific decision logic:

- Clean fit versus strategic stretch
- Product/strategy work versus generic operations or Customer Success
- Appropriate seniority and ownership
- Real candidate evidence rather than keyword overlap
- Location and work-authorization feasibility
- Company priority and warm-path value
- Honest technical and domain gaps

The matching logic must be calibrated against 20–30 historical roles already labelled by the owner.

## 1.4 Product surfaces at target state

1. **Proactive — Opportunity Inbox**  
   Newly discovered roles, fit analysis, feasibility, priority, alignments, gaps, and review actions.
2. **Reactive — Application Tracker**  
   Approved opportunities and applications, stage history, next actions, contacts, documents, and email-derived suggestions.
3. **Settings — Watchlist and Candidate Profile**  
   Company tiers, sources, role-family rules, location/work-authorization policy, and profile versions.
4. **System Health**  
   Coverage, connector failures, last scans, run history, unmatched emails, and cost usage.

---

# 2. Scope and staged delivery

The system must serve the active job search rather than become a substitute for it.

## Stage 0 — Source audit and project setup

**Estimate:** 0.5–1 focused day  
**Build now:** Yes

Deliver:

- Repository and environment setup
- Import/read the current master tracker
- Create a source-coverage matrix for all target companies
- Identify company tier, careers URL, ATS type, source key/token, supported adapter, target locations, and fallback method
- Select the first 10–15 Tier 1 and Tier 2 companies for automated coverage
- Create an initial labelled evaluation set of 20–30 historical roles

**Exit criteria:**

- Every target company has a documented source status: `Supported`, `Needs configuration`, `Manual fallback`, or `Unsupported`.
- At least one Greenhouse, Lever, or Ashby company is selected for the first vertical slice.
- Candidate profile, location policy, and benchmark labels exist as version-controlled configuration files.

## Stage 1 — Operational discovery MVP

**Estimate:** 5–8 focused build days for an owner using a coding agent  
**Build next:** Yes

Deliver a headless Python service that:

- Polls Greenhouse, Lever, and Ashby public job feeds
- Supports manual job URL or pasted job-description intake
- Normalizes and deduplicates postings
- Tracks source health and scan history
- Applies explicit deterministic blockers
- Evaluates eligible new roles with an LLM using structured output
- Separates fit, feasibility, and strategic priority
- Stores state in SQLite
- Scans once daily by default
- Sends one consolidated morning digest
- Optionally sends an urgent email for exceptional Tier 1 roles
- Provides CLI review actions and CSV exports

The existing spreadsheet remains the manually maintained application tracker during Stage 1. The system must not directly edit the workbook.

**Stage 1 is the minimum product that creates immediate job-search advantage.**

## Stage 2 — Web application and database tracker

**Estimate:** 6–10 focused build days after Stage 1 is stable  
**Build only after owner approval**

Deliver:

- Next.js + TypeScript frontend
- Supabase Postgres and authentication
- Proactive Opportunity Inbox
- Reactive Application Tracker
- Approval gate that creates an application record
- Controlled import of the current spreadsheet and Stage 1 SQLite data
- Event history, next actions, contacts, notes, and document references
- Table view first; kanban and advanced analytics are optional later
- Source coverage and health panel
- CSV/XLSX export

## Stage 3 — Gmail-assisted tracker updates

**Estimate:** 3–5 focused build days after Stage 2 is stable  
**Build only after owner approval**

Deliver:

- Read-only Gmail OAuth
- Incremental message sync
- Message classification and application linking
- Suggested tracker updates with confidence and evidence
- Review queue with `Approve` and `Ignore`
- Disconnect and stored-email-deletion flow

No email-derived update may change application state before approval.

## Stage 4 — Future enhancements

Not part of the approved build:

- Role-specific CV and cover-letter drafts
- Interview preparation packs and STAR-story selection
- Recruiter/referral outreach drafts
- Conversion analysis by CV version and role family
- Discovery outside the fixed watchlist
- Automatic application submission

---

# 3. Success measures

## Stage 1 operational metrics

| Metric | Target |
|---|---:|
| Automated or explicit fallback coverage for Tier 1/2 companies | ≥90% |
| Median detection latency for supported feeds | <6 hours |
| Recall on benchmark roles labelled Apply/Consider | ≥95% |
| Precision of surfaced digest roles after first 30 reviews | ≥80% Apply or Consider |
| Duplicate opportunity rate | <2% |
| Successful scheduled runs over rolling 30 days | ≥95% |
| Silent connector failures | 0 |
| Monthly operating cost excluding premium scraping | ≤$15 configurable cap |

## Stage 2 product metrics

| Metric | Target |
|---|---:|
| Active applications with stage and last activity | 100% |
| Active applications with next action or explicit none | 100% |
| Median first-seen-to-review time | <24 hours |
| Application record creation without duplicate events | 100% |

## Stage 3 email metrics

| Metric | Target |
|---|---:|
| Seeded email category accuracy | ≥90% |
| Incorrect silent status updates | 0 |
| Gmail disconnect removes active credentials and stops sync | 100% |

---

# 4. Candidate profile and decision policy

Store this as a versioned machine-readable profile. Professional and work-authorization information only.

## 4.1 Positioning

Strategy & Operations / Product Operations leader with approximately eight years at Google Devices & Services, two promotions, and experience scaling global commercial operations and transformation programs.

## 4.2 Core strengths

- Zero-to-one process and product design
- Cross-functional leadership across Sales, GTM, Finance, Revenue Operations, Controllership, and Engineering
- Global rollout, UAT, training, and change management
- Executive reporting and dashboarding
- Partner operations and vendor-team leadership
- Data-driven process improvement and workflow automation
- Translating frontline and functional feedback into business requirements

## 4.3 Flagship evidence

- **Zenith claims-validation product:** feature prioritization, validation logic, BRDs, Engineering partnership, UAT, training, and rollout; automated 60%+ of end-to-end claims and saved 1,500+ hours annually.
- **Claims/deductions transformation:** reduced aged deductions backlog by 95% within 12 months and recovered tens of millions in revenue.
- **Fitbit integration:** led sales-data migration for 96 partners within five months; achieved 107% of priority onboarding and 115% overall.
- **Executive analytics:** built APAC and global dashboards used by senior leadership.
- **Commercial scale:** supported operations across 120+ partners and multiple regions.

## 4.4 Primary role families

- Strategy & Operations
- Business Operations
- Product Operations
- Product Strategy
- GTM / Sales Strategy & Operations
- Revenue Operations at appropriate seniority
- Business Transformation
- Strategic Programs / Program Leadership

## 4.5 Approved stretch families

Deployment Strategist, Forward-Deployed Strategy, or implementation-heavy AI transformation roles when business problem solving, stakeholder management, process design, and execution outweigh production engineering.

## 4.6 Usually deprioritize, but do not hard-block by title alone

- Customer Success or account management without meaningful strategy/transformation scope
- Pure quota-carrying sales
- Junior analyst or associate scope
- Pure Product Manager roles requiring extensive native PM/SDLC history
- Deeply technical FDE, SWE, or ML engineering roles

## 4.7 Honest gaps

- No production software-engineering background
- Python basic and actively learning
- Product experience comes from ownership, requirements, logic design, UAT, rollout, and transformation rather than native engineering product management
- Limited direct consulting brand and classic case-team experience

## 4.8 Location and work-authorization policy

This policy must be editable and must not be inferred by the LLM. The table
below reflects the owner-approved correction recorded in DECISIONS #24.

| Market | Default state | Rule |
|---|---|---|
| EU | Authorized | German citizenship; high feasibility |
| UK | Viable | Skilled Worker sponsorship needed, but routine for a German candidate at sponsoring employers; do not down-rank |
| Australia | Viable after spousal-visa lead time | Work eligibility expected roughly three months after arrival; treat as an inconvenience flag, not a down-rank |
| Singapore | Viable with sponsorship | Sponsorship is available through ample sponsoring employers; COMPASS noted, not penalized |
| United States | Sponsorship required / high friction | No assumed ongoing work authorization; require credible sponsorship, transfer path, or warm route |

Store for each market:

- `current_authorization`
- `sponsorship_required`
- `expected_availability_date`
- `confidence`
- `last_verified_at`
- `notes`

---

# 5. Evaluation model

## 5.1 Core design

Do not use one blended score that allows company prestige or location to hide weak role fit.

Every evaluated role must produce four separate outputs:

1. **Role fit score:** 0–100
2. **Feasibility:** `viable`, `sponsorship_required`, `uncertain`, or `blocked`
3. **Strategic priority:** `tier_1`, `tier_2`, or `tier_3`, modified by freshness and warm-path information
4. **Recommendation:** `apply_now`, `consider`, `stretch`, `skip`, or `blocked`

## 5.2 Role fit dimensions

| Dimension | Weight | Meaning |
|---|---:|---|
| Role-family fit | 30 | Match to target or approved-stretch work, based on responsibilities rather than title alone |
| Evidence strength | 30 | Specificity and quality of candidate evidence mapped to stated requirements |
| Scope and seniority | 25 | Ownership, ambiguity, stakeholder level, team/vendor leadership, required experience, and level match |
| Gap manageability | 15 | Severity of functional, technical, or domain gaps; higher score means more manageable |

The total role fit score is computed deterministically from validated dimension scores.

## 5.3 True deterministic blockers

Apply a hard blocker only when the evidence is explicit:

- Posting is closed or unavailable at first discovery
- Mandatory active security/government clearance that the candidate cannot obtain
- Posting explicitly requires existing local work authorization and states sponsorship is unavailable
- Production software engineering, production coding, or deep ML engineering is a central duty
- Role is clearly junior based on responsibilities and required experience, not title alone
- Location is genuinely impossible under the current stored policy

## 5.4 Strong penalties, not automatic blockers

- Customer Success/account management without clear strategy ownership
- Quota-carrying sales
- Analyst/associate title with ambiguous level
- US role with no sponsorship information
- Pure PM role without an implementation/operations angle
- Domain experience requirement not demonstrated by the candidate

## 5.5 Recommendation logic

Default rules, configurable:

- `blocked`: any true blocker
- `apply_now`: fit ≥80, feasibility not blocked, and strategic priority Tier 1 or Tier 2
- `apply_now`: fit ≥70 for Tier 1 when there is a warm path or exceptional strategic upside
- `consider`: fit 65–79 with manageable feasibility
- `stretch`: fit 50–64 and Tier 1/2, approved stretch family, or strong warm path
- `skip`: fit <50 or severe gap burden without compensating value

The model may recommend a band, but final calculation and blocker override occur in code.

## 5.6 Required structured evaluation output

```json
{
  "role_fit_score": 0,
  "confidence": 0.0,
  "dimensions": {
    "role_family_fit": 0,
    "evidence_strength": 0,
    "scope_seniority": 0,
    "gap_manageability": 0
  },
  "feasibility": {
    "state": "viable | sponsorship_required | uncertain | blocked",
    "reason": "",
    "policy_version": ""
  },
  "strategic_priority": {
    "company_tier": "tier_1 | tier_2 | tier_3",
    "freshness": "new_today | recent | stale",
    "warm_path": false,
    "reason": ""
  },
  "recommendation": "apply_now | consider | stretch | skip | blocked",
  "hard_blockers": [
    {"type": "", "evidence": ""}
  ],
  "alignments": [
    {
      "job_requirement": "",
      "candidate_evidence": "",
      "evidence_strength": "strong | medium | weak"
    }
  ],
  "gaps": [
    {
      "gap": "",
      "severity": "low | medium | high",
      "mitigation": ""
    }
  ],
  "uncertainties": [""],
  "summary": "Maximum three concise sentences."
}
```

The system must validate this schema and reject malformed model responses.

---

# 6. Stage 0 requirements: source audit

Create `config/watchlist.yaml` or equivalent with:

- Company name
- Company tier
- Careers URL
- ATS/source type
- Source key/token
- Target locations
- Target role-family notes
- Warm contacts or warm-path flag
- Enabled/disabled state
- Coverage state
- Manual fallback

Produce a coverage report:

| Company | Tier | Careers URL | ATS | Source key | Adapter supported | Status | Fallback |
|---|---|---|---|---|---|---|---|

Do not begin broad adapter implementation until this audit is complete.

---

# 7. Stage 1 functional requirements

## FR1-01 — Source adapters

Implement first-class adapters for:

- Greenhouse
- Lever
- Ashby

Each adapter implements a shared contract:

- `fetch()` — response body, HTTP status, timing, and rate-limit metadata when available
- `normalize()` — canonical posting objects
- `identity()` — source job ID and canonical-key inputs
- `health_check()` — distinguish valid zero jobs from parser/auth/network failure
- `fixtures()` — saved representative payloads used in tests

## FR1-02 — Manual intake

Manual intake is a Stage 1 must-have.

Support:

- `job-agent add-url <url>`
- `job-agent add-text <file-or-stdin>`

The system must normalize, evaluate, store, and include manually added roles in the same review flow as discovered roles.

If URL extraction fails, preserve the URL and request pasted job-description text rather than failing silently.

## FR1-03 — Normalized posting

Store:

- Company
- Title
- Locations
- Department/team
- Employment type
- Description text
- Source type
- Source URL
- Source job ID
- Source posted date when available
- `first_seen_at`
- `last_seen_at`
- Raw payload hash
- Canonical key
- Availability state

## FR1-04 — Deduplication and grouping

Requirements:

- Replaying a scan must not duplicate postings or evaluations.
- Source job ID is the primary identity within one source.
- Canonical key should use normalized company, title, department, and underlying role identifier where available.
- Group multi-location variants when they are one underlying job while retaining all apply URLs and locations.
- Do not group genuinely distinct requisitions solely because titles match.

## FR1-05 — Availability logic

- A posting may be marked unavailable only after it is absent from two consecutive successful scans.
- A failing connector does not count as absence.
- A disappeared job must never imply rejection or alter an application state.

## FR1-06 — Source health and run monitoring

For every run and source, store:

- Start/end time
- Status
- Duration
- HTTP status
- Jobs fetched
- New jobs
- Changed jobs
- Errors
- Retry count and outcome
- Last successful scan
- Parser version
- Expected-volume baseline or anomaly flag

Health states:

- `healthy`
- `degraded`
- `failing`
- `unsupported`
- `disabled`

Failures must appear in the morning digest even when there are no opportunities.

## FR1-07 — Evaluation and caching

- Evaluate only new or materially changed eligible roles.
- Persist profile version, policy version, prompt version, model version, input hash, output, and timestamp.
- Do not rescore unchanged roles automatically.
- Provide a manual `rescore` command.
- Enforce a configurable monthly model-spend cap.

## FR1-08 — Review CLI

Provide:

- `job-agent review list`
- `job-agent review show <job_id>`
- `job-agent review approve <job_id>`
- `job-agent review dismiss <job_id> --reason <reason>`
- `job-agent review snooze <job_id> --until <date>`
- `job-agent review reopen <job_id>`

Stage 1 approval records the decision in SQLite and exposes it in exports. It does not mutate the original Excel tracker.

Review states:

- `new`
- `approved`
- `dismissed`
- `snoozed`
- `duplicate`
- `closed`

## FR1-09 — Morning digest

Send one consolidated email each morning containing only unreviewed roles discovered since the prior digest.

Sections:

1. **Apply now**
2. **Consider**
3. **Stretch / selective**
4. **Blocked or low priority** — collapsed or summarized
5. **Source failures and coverage gaps**

Each role shows:

- Company and title
- Location
- First seen and source-posted date
- Fit score and confidence
- Feasibility
- Company tier and strategic-priority reason
- 2–4 alignments
- 1–3 gaps
- Blocker, if any
- Source link
- Stable internal job ID for CLI review

Do not resend reviewed roles unless materially changed or manually reopened.

## FR1-10 — Urgent alerts

Optional, configurable.

Default trigger:

- Tier 1 company
- Fit ≥85
- No hard blocker
- First seen since previous scan

Use email first. Do not add Telegram/Slack until real usage proves necessary.

## FR1-11 — Export and backup

Provide:

- `opportunities.csv`
- `approved_roles.csv`
- `source_coverage.csv`
- `source_runs.csv`
- SQLite backup command

Exports must be readable without the application.

## FR1-12 — Scheduling

Default scan cadence: once daily.
Default digest: once every morning in the owner's configured timezone.

Stage 1 may use GitHub Actions or another simple scheduler, but:

- The workflow must support manual dispatch.
- A missed or failed run must be visible.
- The service must be runnable locally using the same command.
- Scheduling must be isolated from business logic.

## FR1-13 — Notification provider

Use a transactional email provider through an interface. Provide a development fallback that writes the digest to `output/latest_digest.html` and logs the subject.

Do not use Gmail write permissions solely to send digests.

---

# 8. Stage 1 data model

Use SQLite through a repository/ORM layer that can later target Postgres.

## Core tables

### `profile_versions`

- `id`
- `version`
- `profile_json`
- `active`
- `created_at`

### `location_policy_versions`

- `id`
- `version`
- `policy_json`
- `active`
- `created_at`

### `companies`

- `id`
- `name`
- `tier`
- `enabled`
- `warm_path`
- `notes`

### `job_sources`

- `id`
- `company_id`
- `source_type`
- `source_key`
- `source_url`
- `parser_version`
- `health_status`
- `last_success_at`
- `expected_volume_min`

### `source_runs`

- `id`
- `job_source_id`
- `started_at`
- `finished_at`
- `status`
- `http_status`
- `fetched_count`
- `new_count`
- `changed_count`
- `retry_count`
- `error_summary`

### `job_postings`

- `id`
- `company_id`
- `source_id`
- `source_job_id`
- `canonical_key`
- `title`
- `locations_json`
- `department`
- `employment_type`
- `description_text`
- `source_url`
- `posted_at`
- `first_seen_at`
- `last_seen_at`
- `raw_payload_hash`
- `availability_state`
- `missing_successful_scan_count`

### `role_evaluations`

- `id`
- `job_posting_id`
- `profile_version_id`
- `location_policy_version_id`
- `prompt_version`
- `model_version`
- `input_hash`
- `evaluation_json`
- `created_at`

### `opportunity_reviews`

- `id`
- `job_posting_id`
- `state`
- `decision_reason`
- `reviewed_at`
- `snooze_until`

### `notifications`

- `id`
- `type`
- `payload_hash`
- `sent_at`
- `status`
- `error_summary`

---

# 9. Stage 1 technical architecture

## 9.1 Recommended stack

- Python 3.12+
- Type checking with `mypy` or `pyright`
- `httpx` for HTTP
- `pydantic` for canonical schemas and structured model output
- SQLAlchemy 2.x or another repository abstraction over SQLite
- `Typer` for CLI
- `tenacity` or equivalent for bounded retries
- `Jinja2` for HTML digest templates
- `pytest` for tests
- `ruff` for linting and formatting
- GitHub Actions for CI and optional Stage 1 scheduling

## 9.2 Expected repository structure

```text
job-search-agent/
  app/
    __init__.py
    cli.py
    config.py
    db.py
    models.py
    repositories/
    adapters/
      base.py
      greenhouse.py
      lever.py
      ashby.py
      manual.py
    services/
      ingest.py
      normalize.py
      dedupe.py
      health.py
      evaluate.py
      recommend.py
      digest.py
      notify.py
    prompts/
      role_evaluation_v1.md
    templates/
      digest.html.j2
      digest.txt.j2
  config/
    watchlist.yaml
    candidate_profile.yaml
    location_policy.yaml
    scoring_policy.yaml
  data/
    fixtures/
    evaluation_set/
  tests/
    unit/
    integration/
    adapters/
    evaluation/
  scripts/
    import_tracker.py
    export_csv.py
  output/
  migrations/
  .github/workflows/
  README.md
  DECISIONS.md
  .env.example
  pyproject.toml
```

## 9.3 Processing flow

1. Scheduler starts a workflow run.
2. Load enabled sources and active configuration versions.
3. Fetch each source independently with timeout and bounded retry.
4. Normalize payloads and validate schemas.
5. Update source health and run metrics.
6. Deduplicate and update `first_seen_at` / `last_seen_at`.
7. Identify new or materially changed roles.
8. Apply true deterministic blockers and feasibility policy.
9. Evaluate eligible roles using structured LLM output.
10. Compute final fit and recommendation in code.
11. Persist evaluation snapshot and review state.
12. Generate digest from unreviewed roles.
13. Send or save digest and record notification history.

A failed source must not block other sources.

---

# 10. Stage 1 testing and acceptance

## 10.1 Test layers

### Unit tests

- Title and location normalization
- Canonical keys
- Deduplication
- Availability transitions
- Blockers and penalties
- Score calculation and recommendation bands
- Digest deduplication
- Cost-cap behavior

### Adapter contract tests

Use saved real payload fixtures for every adapter. A schema change must fail loudly instead of returning a false successful zero-job result.

Test:

- Valid response
- Zero-job response
- Malformed JSON
- Missing optional fields
- HTTP 403
- HTTP 429
- Timeout
- Duplicate records

### Integration tests

- SQLite migrations
- Idempotent scan replay
- Material-change detection
- Evaluation caching
- Review-state changes
- Digest generation
- CSV export

### Evaluation benchmark

Use 20–30 historical roles labelled by the owner:

- Clean / Apply
- Consider
- Deployment/FDS stretch
- Reach
- Customer Success deprioritize
- Below-level
- Visa uncertain or blocked
- Technical blocker

Measure:

- Apply/Consider recall
- Digest precision
- Blocker accuracy
- Fit-band agreement
- Evidence quality
- False-positive rate

False positives should be weighted more heavily than false negatives in urgent alerts, but recall should remain high in the full review queue.

## 10.2 Stage 1 acceptance test

Stage 1 is complete only when all are true:

1. A new fixture job from a supported source appears exactly once after a scan.
2. Replaying the same scan creates no duplicate posting, evaluation, review, or notification.
3. The role shows fit, feasibility, strategic priority, recommendation, alignments, gaps, and uncertainty.
4. A malformed source is marked failing and does not prevent other sources from finishing.
5. A valid zero-job response is distinguishable from a parser failure.
6. A job absent from one successful scan is not marked unavailable; after two consecutive successful absences it is.
7. A manual URL or pasted JD follows the same evaluation path.
8. The morning digest contains only new unreviewed roles and relevant failures.
9. Approved and dismissed decisions persist and do not reappear after later scans unless materially changed or reopened.
10. CSV exports and a SQLite backup are readable.
11. Benchmark recall is at least 95% for owner-labelled Apply/Consider roles.
12. No secret or private source data is committed to the repository.

---

# 11. Stage 2 requirements: web application and tracker

Stage 2 becomes the authoritative operating system. The spreadsheet becomes migration input and backup/export only.

## 11.1 Stack

- Next.js + TypeScript
- Supabase Postgres
- Supabase Auth
- Scheduled jobs in Supabase or another backend scheduler
- Existing Python discovery service may remain as a service or be migrated only when justified

## 11.2 Opportunity Inbox

Default sort:

1. Recommendation
2. Company tier
3. First-seen time

Each card shows:

- Company, title, location
- First seen and source date
- Fit score and confidence
- Feasibility
- Strategic priority
- Alignments, gaps, blockers, uncertainties
- Source health
- Actions: `Approve`, `Dismiss`, `Snooze`, `Duplicate`, `Open source`

Only `Approve` creates an application.

## 11.3 Application Tracker

Initial required view: table. Kanban is optional after the table is stable.

Fields:

- Company
- Role
- Location
- Job URL
- Current stage
- Date found
- Date approved
- Date applied
- Last activity
- Next action
- Due date
- Contact/referral
- Document references
- Notes

Stages:

- `preparing`
- `applied`
- `recruiter_screen`
- `interviewing`
- `final_round`
- `offer`
- `rejected`
- `withdrawn`
- `archived`

Every material update creates an immutable event containing actor, source, timestamp, previous value, and new value.

## 11.4 Migration

Import:

- Existing master tracker workbook
- Stage 1 companies, sources, postings, evaluations, review decisions, and scan history

Produce a migration report showing:

- Imported records
- Skipped rows
- Ambiguous mappings
- Duplicates
- Manual-review items

Never overwrite the source workbook.

## 11.5 Stage 2 acceptance

- Approving an opportunity creates exactly one `preparing` application.
- The evaluation snapshot used for approval remains reproducible.
- All stage changes create immutable events.
- Active applications show stage, last activity, and next action or explicit none.
- Exports reproduce the application tracker in readable CSV/XLSX format.
- The app requires authentication and denies anonymous access.

---

# 12. Stage 3 requirements: Gmail-assisted updates

## 12.1 Security boundary

- Read-only Gmail access only
- Server-side OAuth
- Encrypted refresh-token storage
- No compose, modify, or send scopes
- Disconnect and delete controls
- Minimize retained content

## 12.2 Incremental sync

- Store the last successful checkpoint.
- Fetch only newer relevant messages.
- Deduplicate by Gmail message ID.
- Use sender domain, title, company, ATS identifiers, thread history, and time proximity for linking.
- Do not rely on a single signal.

## 12.3 Classification categories

- Application confirmation
- Recruiter outreach
- Interview invitation
- Scheduling
- Rejection
- Offer/decision
- General update
- Unrelated

## 12.4 Stored email data

Store only:

- Message ID
- Thread ID
- Sender
- Subject
- Received timestamp
- Short evidence snippet
- Classification
- Confidence
- Linked application

Do not retain full message bodies by default.

## 12.5 Suggestion workflow

Email suggestions have states:

- `pending`
- `approved`
- `ignored`

A suggestion shows:

- Linked application
- Proposed event or status
- Confidence
- Evidence
- Approve / Ignore

No automatic mutation is permitted in this stage.

---

# 13. Non-functional requirements

1. **Reliability:** One failed source does not stop other companies.
2. **Idempotency:** Replaying any workflow creates no duplicate postings, evaluations, decisions, events, or notifications.
3. **Explainability:** Every recommendation has mapped evidence, gaps, blockers, uncertainties, confidence, and version metadata.
4. **Human control:** No application creation, tracker mutation from email, recruiter communication, document submission, or application submission without approval.
5. **Security:** Secrets server-side, encrypted transport, revocable credentials, least privilege.
6. **Privacy:** Store only job-search-related email metadata; support deletion and disconnect.
7. **Observability:** Every run records state, counts, duration, errors, retries, and last-known-good health.
8. **Maintainability:** New connectors implement the shared adapter contract and include fixtures/tests.
9. **Portability:** Core data exportable to CSV/XLSX; database migrations version-controlled.
10. **Cost control:** Score only new/materially changed roles; cache outputs; enforce model and scraper budgets.
11. **Accessibility:** Stage 2 actions keyboard usable, clearly labelled, responsive, and high contrast.
12. **Performance:** Stage 1 full scan completes within 15 minutes for the initial watchlist; Stage 2 inbox loads within two seconds for the expected single-user dataset.

---

# 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| ATS source changes silently | Fixtures, parser versions, expected-volume alerts, last-known-good data, fail loudly |
| Workday/custom sites consume too much effort | Tier companies, manual intake, native alerts, explicit unsupported coverage |
| LLM over-scores prestigious but weak-fit roles | Separate fit from company priority, benchmark set, penalties, human review |
| Hard rules hide unusual good roles | Keep true blocker set narrow; use penalties and review queue for ambiguity |
| Gmail OAuth delays project | Build only after core app is stable; manual updates remain available |
| Spreadsheet synchronization becomes fragile | No workbook writes in Stage 1; one-way controlled migration in Stage 2 |
| Portfolio work displaces real applications | Stage gates; build Stage 1 only until current Tier 1 applications and interviews are handled |
| Private data leaks in demo | Separate sanitized seed dataset; never use real emails or application details in public mode |
| Coding agent creates unnecessary complexity | Vertical slices, explicit stage boundaries, documented decisions, no multi-agent framework |

---

# 15. Build sequence and checkpoints

## Checkpoint A — Repository and coverage audit

Deliver:

- Repository skeleton
- Configuration schemas
- Tracker-import reader
- Coverage matrix
- First company selected
- Evaluation fixtures selected

Stop and show the owner the audit before broad implementation.

## Checkpoint B — One-source vertical slice

Deliver:

- One adapter
- SQLite persistence
- Normalization and dedupe
- One structured evaluation
- Local HTML digest
- Tests

This must work end to end before adding more sources.

## Checkpoint C — Complete Stage 1 adapters and health

Deliver:

- Greenhouse, Lever, Ashby
- Manual intake
- Health model
- Scheduled run
- Review CLI
- Exports

## Checkpoint D — Calibration and live digest

Deliver:

- Benchmark evaluation report
- Adjusted scoring policy
- Live email provider
- Morning digest
- Urgent alert option
- Documentation and backup procedure

Stop after Stage 1 and wait for explicit approval before Stage 2.

---

# 16. Required project documentation

The repository must include:

## `README.md`

- Product purpose
- Architecture
- Local setup
- Environment variables
- Database initialization and migration
- Importing tracker data
- Running scans
- Manual job intake
- Review commands
- Export and backup
- Scheduling
- Test commands
- Deployment
- Known coverage gaps

## `DECISIONS.md`

Record:

- Date
- Decision
- Alternatives
- Reason
- Reversibility
- Owner approval where needed

## `.env.example`

Names only, no secrets.

## Sanitized demo data

Must not contain real emails, application details, contacts, or private document text.

---

# 17. Inputs required from the owner

Codex should proceed with placeholders where possible and request only missing blockers.

Required before live operation:

- Current master tracker workbook
- Approved company tiers and watchlist
- Candidate profile configuration approval
- Location/work-authorization policy confirmation
- 20–30 labelled historical role examples
- Recipient email
- LLM API key
- Transactional email API key, if live email delivery is enabled
- Confirmation of timezone and digest time

Do not block local development on email credentials; save the digest locally until credentials are supplied.

---

# 18. Explicit non-goals

Do not implement in Stages 0–3 unless separately approved:

- Automatic job applications
- Automatic recruiter outreach
- Automatic interview scheduling or responses
- Automatic CV or cover-letter submission
- Browser automation against LinkedIn
- Access-control bypassing or anti-bot evasion
- Broad web discovery outside the watchlist
- Commercial multi-user SaaS functionality
- A multi-agent orchestration framework
- Automatic rejection inference from a dead posting URL

---

# 19. Final definition of success

The project succeeds when Owner receives a reliable morning digest of genuinely relevant new roles from his priority companies, supported by explicit source health and a calibrated explanation of fit, feasibility, and gaps; can review those roles quickly; and can later promote approved opportunities into a trustworthy application tracker without losing control of consequential decisions.

The system must improve the job search first. Portfolio value is secondary and should result from sound product judgment, not added complexity.
