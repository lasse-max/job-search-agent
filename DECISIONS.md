# Decisions

## 2026-06-23

### Create the project under the current writable workspace

- Decision: Created `job-search-agent/` under the current workspace rather than a sibling folder.
- Alternatives: Request broader filesystem access and create `owner_home/PM Projects/Job Search Agent`.
- Reason: The current sandbox allows writes inside the existing workspace, and this is reversible.
- Reversibility: Move the folder into a standalone repository later.
- Owner approval: Not required for Stage 0.

### Treat `Owner_Tracker.xlsx` as the current master tracker

- Decision: Used `sanitized_tracker_reference` for Stage 0 inspection.
- Alternatives: Use `Job_Search_Tracker_Master.xlsx` or `Job_Search_Tracker_Master (1).xlsx`.
- Reason: It is the most recent and richest workbook found, with Dashboard, Pipeline, Company Watchlist, and History sheets.
- Reversibility: Re-run the Stage 0 import against another workbook.
- Owner approval: Needed only if this assumption is wrong.

### Limit source audit probes to public Greenhouse, Lever, and Ashby feeds

- Decision: Checked only the three Stage 1 approved adapter families.
- Alternatives: Probe Workday, SmartRecruiters, custom search APIs, or browser-rendered sites.
- Reason: The PRD explicitly says to avoid brittle scraping and publish unsupported coverage before adding custom exceptions.
- Reversibility: Add approved high-value exceptions later.
- Owner approval: Required before any browser automation or unsupported custom connector.

### Keep benchmark labels as a draft until owner confirmation

- Decision: Created `data/evaluation_set/initial_benchmark.yaml` from Pipeline rows with draft labels inferred from tracker status and priority score.
- Alternatives: Block Stage 0 until 20-30 owner-labelled examples are manually supplied.
- Reason: The tracker has enough signal to create a useful placeholder, but the PRD requires owner-labelled benchmark roles before acceptance tests.
- Reversibility: Replace inferred labels with confirmed labels.
- Owner approval: Required before using these labels as acceptance criteria.

### Treat generated audit/config files as private

- Decision: Keep the current Stage 0 audit and watchlist as private job-search artifacts.
- Alternatives: Sanitize immediately for a public GitHub demo.
- Reason: The PRD warns against leaking private application data, contacts, or real job-search details.
- Reversibility: Create a sanitized demo dataset before publishing.
- Owner approval: Required before public release.

