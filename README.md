# Sextant — Job Search Agent

**Find the right roles early. Put your time into landing them.**

A relevant opportunity is easier to act on when it reaches you promptly. LinkedIn reports up to a **fourfold increase in the chance of a response** for applications made within ten minutes of a LinkedIn job notification. [Source: LinkedIn Learning, Career Services guide](https://learning.linkedin.com/content/dam/me/learning/resources/pdfs/HED.Strategy.Guidev2.pdf).

Finding a promising role soon after it opens takes persistence: checking company sites, repeating searches, and reading job descriptions every day. Keeping that up across a serious company watchlist can consume the time you need for interview preparation, learning, and better applications.

Sextant takes on that daily discovery work. In its current live setup, it scans a pool of **6,000+ roles each day** and delivers relevant opportunities straight to the inbox. It matches the work against a detailed candidate profile: career experience, skills, target seniority, company priorities, and practical constraints.

The companion web app helps turn a promising role into a prepared application. Clear fit bands make the list easier to prioritise. Role-level evidence surfaces strengths and potential gaps to address. Shortlisting and application tracking keep the next action visible.

**Live and in active testing.** The system is being used in a real job search, with feedback shaping its coverage, matching, and workflow.

Built by Lasse as part of Layline, with AI-assisted implementation and review. This repository contains both the agent and the Sextant web application.

## Screenshots

The operational app requires owner authentication because it contains personal job-search data. There is no public interactive demo at present.

These screenshots were captured from live testing on **8 September 2026**. Counts, coverage and recommendations are snapshots of the displayed runs.

### See the scan at a glance

![Sextant scan overview showing 7,527 postings across 34 companies, with 3 apply, 20 consider and 13 stretch recommendations](https://raw.githubusercontent.com/lasse-max/lasse-max/main/assets/sextant/scan-overview.png)

The overview groups surfaced opportunities by recommendation and shows the scanned catalog alongside sorting and filtering controls.

### Review the roles worth your attention

![Sextant ranked matches showing role fit, company tiers, feasibility, confidence and mark-to-apply controls](https://raw.githubusercontent.com/lasse-max/lasse-max/main/assets/sextant/ranked-matches.png)

Each card keeps role fit, feasibility, company priority and supporting context visible. The user chooses whether to mark a role to apply, dismiss it or snooze it.

### Inspect the search criteria

![Sextant profile showing configured role families, seniority criteria and source coverage](https://raw.githubusercontent.com/lasse-max/lasse-max/main/assets/sextant/search-profile.png)

The read-only profile makes the configured target roles, seniority rules and source coverage inspectable. Changes to these criteria are made through configuration.

The images are hosted in the public profile repository so the showcase remains accessible if this working repository becomes private. A short video walkthrough is planned.

## Built around your search

A matching job title is only a starting point. Two roles with the same title can demand different skills, carry different responsibilities, and lead to different careers.

Sextant is configurable around the candidate's actual direction:

- **Company priorities:** focus the search around a tiered watchlist of employers.
- **Experience and skills:** compare the substance of a role with the candidate's background and evidence.
- **Career goals and constraints:** account for role family, seniority, location, and feasibility.
- **Application preparation:** identify relevant strengths and gaps to address in written materials or interview preparation.

The aim is to give candidates more time for the opportunities worth pursuing.

## A clear order of attention

| Fit score | Recommendation | How to use it |
|---|---|---|
| Below 60 | Skip | Move past weak fits and protect your attention. |
| 60–69 | Stretch | Look at the opportunity and the gaps you would need to bridge. |
| 70–79 | Consider | Review the evidence and decide whether it advances your goals. |
| 80–89 | Apply now | Prioritise a timely, tailored application. |
| 90–100 | Apply now — strongest fit | Treat these as strong-apply opportunities and give them your earliest attention. |

Scores of 90+ are the strongest end of the app's **Apply now** category. Fit scores are prioritisation signals, not probabilities of an interview or offer, and feasibility checks still apply.

## What is implemented

| Capability | What it does |
|---|---|
| Daily discovery | Scans 6,000+ roles in the current setup, normalises postings, removes duplicates, and records source health. |
| Evaluation | Combines deterministic relevance and feasibility rules with Claude's structured assessment of job-description evidence. |
| Potential Matches | Presents stored recommendations and their supporting evidence. |
| To Apply | Maintains an owner-selected shortlist. |
| Applied | Tracks application stages and next actions while preserving the evaluation recorded when a role was added. |
| Profile | Displays the current search criteria in a read-only view. |
| Manual intake | Accepts a URL, pasted description, or an explicitly unscored manual entry; URL/text evaluation is queued for the scanner. |
| Email digest | Delivers a bounded summary and source-health information through Resend. |

Manual intake requires its database migrations to be applied. Deployment setup is documented in [web/README.md](https://github.com/lasse-max/job-search-agent/blob/main/web/README.md).

## Product and engineering decisions

**Make the criteria inspectable.** Fit, feasibility, and strategic priority are represented separately. Explicit constraints remain visible rather than being hidden inside a single persuasive score.

**Keep one evaluation implementation.** The Python agent owns scoring. The web app reads stored results and records owner decisions, avoiding a second scoring system that could drift from the digest.

**Preserve the reason for past decisions.** Current recommendations use the active evaluation version. Historical application records retain their snapshots, so changing the evaluator does not erase the basis for a past decision.

**Measure both missed opportunities and noise.** Evaluation uses labelled examples and live-feed samples. Precision alone can look good while useful roles disappear; recall alone can flood the inbox. Both matter.

**Keep actions with the owner.** The system recommends and organises. Shortlisting, application tracking, and other consequential actions require an explicit user action; it does not submit job applications.

## Architecture

```text
Daily GitHub Actions scan + queued manual intake
    → ATS adapters: Greenhouse / Lever / Ashby / SmartRecruiters
    → normalise, deduplicate, and record source health
    → deterministic rules + structured Claude evaluation
    → Supabase Postgres
        → Sextant web app: review, shortlist, track
        → Resend email digest
```

Adapter support does not mean every watchlist company is covered or enabled. Unsupported sources and coverage gaps remain part of the operating picture.

**Agent:** Python, HTTPX, Pydantic, SQLAlchemy, YAML configuration, and Claude.

**Application:** Next.js, React, TypeScript, Tailwind CSS, Supabase Auth/Postgres, and Vercel. Owner access is enforced through authentication, database policies, and restricted write operations.

SQLite remains available for local development; the deployed application reads the shared Postgres store. The configured scheduled workflow runs once daily.

## Evaluation and current limits

The repository includes adapter, unit, integration, and benchmark tests. GitHub Actions runs Python lint and automated tests. These checks support development; they do not establish that every live recommendation is correct.

- The LinkedIn timing statistic describes its own job notifications. Sextant scans daily; its effect on response or interview rates has not yet been measured.
- The evaluation is tailored to one person's strategy; generalisation to other candidates has not been established.
- Coverage depends on available feeds and enabled sources. A healthy scheduled run does not imply complete market coverage.
- Job descriptions and model interpretations can be incomplete or wrong. Recommendations need human review.
- This is currently an owner-only application. A reusable open-source setup and a video walkthrough are future work; the screenshots above provide a public preview.

## What's next

Use live feedback to improve the relevance of recommendations and the experience of acting on them. Then package the system as an **open-source setup that candidates can configure and run for their own job search**, with their own company priorities, background, skills, and goals.

That reusable release is planned; a supported public setup and open-source licence are not yet available.

## Development

Requires Python 3.12 or later. From an authorised checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
```

Configure local values in `.env`. Use a separate development database and sample inputs. Live evaluation requires an Anthropic API key; email delivery additionally requires Resend configuration. Development fallback evaluations are not evidence of calibrated model quality.

Run the same Python checks used by CI:

```bash
python -m ruff check .
python -m unittest discover -s tests
```

For the web app, database setup, authentication, and deployment, see [web/README.md](https://github.com/lasse-max/job-search-agent/blob/main/web/README.md).

## Repository guide

| Directory | Contents |
|---|---|
| `app/` | Discovery adapters, evaluation, state, CLI, and notifications |
| `web/` | Sextant interface and owner-authorised actions |
| `config/` | Search criteria, watchlist, and scoring policy |
| `migrations/` | Database schema and access policies |
| `tests/` | Automated behaviour and regression checks |
| `data/evaluation_set/` | Evaluation inputs and reports |
| `docs/` | Product decisions, architecture, and operating notes |

Some planning documents contain historical stages; this README describes the implemented system reviewed in September 2026. See [ROADMAP.md](https://github.com/lasse-max/job-search-agent/blob/main/ROADMAP.md) for planned work and [DECISIONS.md](https://github.com/lasse-max/job-search-agent/blob/main/DECISIONS.md) for the decision history.

## Usage

Personal project. No open-source licence is granted by this README.
