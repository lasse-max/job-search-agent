import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";

function loadTypeScript(path, dependencies = {}) {
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
  });
  const exports = {};
  vm.runInNewContext(outputText, {
    exports, URL, require: (name) => {
      assert.ok(name in dependencies, `unmocked module: ${name}`);
      return dependencies[name];
    }
  });
  return exports;
}

const companies = [
  { id: 1, name: "Enabled", enabled: 1 },
  { id: 2, name: "Disabled in config", enabled: 1 },
  { id: 3, name: "Disabled in DB", enabled: 0 },
  { id: 4, name: "Removed from config", enabled: 1 }
];
const configured = [
  { name: "Enabled", enabled: true, atsType: "ashby", sourceKey: "current" },
  { name: "Disabled in config", enabled: false, atsType: "lever", sourceKey: "disabled" },
  { name: "Disabled in DB", enabled: true, atsType: "lever", sourceKey: "disabled-db" }
];
const sources = [
  { id: 1, company_id: 1, source_type: "ashby", source_key: "current", health_status: "healthy" },
  { id: 2, company_id: 1, source_type: "lever", source_key: "old", health_status: "healthy" },
  { id: 3, company_id: 1, source_type: "ashby", source_key: "current", health_status: "disabled" },
  { id: 4, company_id: 1, source_type: "ashby", source_key: "current", health_status: "retired" },
  { id: 5, company_id: 1, source_type: "ashby", source_key: "current", health_status: "failing" },
  { id: 6, company_id: 1, source_type: "ashby", source_key: "current", health_status: "degraded" },
  { id: 7, company_id: 2, source_type: "lever", source_key: "disabled", health_status: "healthy" },
  { id: 8, company_id: 3, source_type: "lever", source_key: "disabled-db", health_status: "healthy" },
  { id: 9, company_id: 3, source_type: "manual", source_key: "manual", health_status: "healthy" },
  { id: 10, company_id: 4, source_type: "ashby", source_key: "removed", health_status: "healthy" },
  { id: 11, company_id: 4, source_type: "manual", source_key: "manual", health_status: "retired" }
];
const sourceReach = loadTypeScript("../lib/data/source-reach.ts");
const liveSources = loadTypeScript("../lib/data/live-sources.ts", {
  "@/generated/profile-config.json": { default: { watchlist: { companies: configured } } },
  "@/lib/data/source-reach": sourceReach
});
const manualIntake = { loadOpenManualIntakes: async () => [] };
const evaluations = loadTypeScript("../lib/data/calibrated-evaluations.ts", {
  "@/lib/data/source-reach": sourceReach,
  "@/lib/data/live-sources": liveSources,
  "@/lib/data/manual-intake": manualIntake,
  "@/generated/profile-config.json": { default: { watchlist: { companies: configured } } },
  "@/lib/recency": { ROLE_MAX_AGE_DAYS: 21, recencyCutoffDate: () => "2026-09-07" }
});
const shortlist = loadTypeScript("../lib/data/shortlist.ts", {
  "@/lib/data/live-sources": liveSources,
  "@/lib/data/calibrated-evaluations": evaluations,
  "@/lib/data/manual-intake": manualIntake
});
const applications = loadTypeScript("../lib/data/applications.ts", {
  "@/lib/data/calibrated-evaluations": evaluations,
  "@/lib/data/manual-intake": manualIntake
});
const expectedIds = [1, 5, 6, 9];
const evaluation = {
  role_fit_score: 85, recommendation: "apply_now", confidence: 0.9,
  feasibility: { state: "viable" }, provenance: { is_fallback: false },
  alignments: [], gaps: [], hard_blockers: []
};

function database(reviewState = "new") {
  const postings = sources.map((source) => ({
    id: source.id, job_id: source.id, source_id: source.id, company_id: source.company_id,
    company: companies.find((company) => company.id === source.company_id).name,
    company_tier: 1, title: `Business Operations ${source.id}`, department: "Operations",
    source_type: source.source_type, source_key: source.source_key, source_job_id: `${source.id}`,
    source_url: "https://example.com/job", locations_json: '["London"]', availability_state: "open",
    model_version: "claude|hybrid_claude_v4", review_state: reviewState,
    evaluation_json: JSON.stringify(evaluation), evaluated_at: "2026-09-28T06:00:00Z",
    first_seen_at: "2026-09-28T06:00:00Z", posted_at: "2026-09-28T06:00:00Z",
    effective_at: "2026-09-28T06:00:00Z"
  }));
  return {
    companies, job_sources: sources, current_opportunity_evaluations: postings,
    job_postings: postings, source_runs: [],
    evaluation_skips: postings.map((posting) => ({
      id: posting.id, job_posting_id: posting.id, reason: "off_location",
      created_at: "2026-09-28T06:00:00Z"
    })),
    applications: [{
      id: 42, company: "Enabled", role: "Historical role", location: "London",
      stage: "applied", source_posting_id: 4,
      applied_at: "2026-08-01", applied_calendar_week: 31,
      eval_snapshot_json: { model_version: "claude|hybrid_claude_v2", evaluation }
    }],
    application_events: []
  };
}

function client(rows, errorTable = null) {
  return {
    from(table) {
      let result = [...(rows[table] ?? [])];
      let rowLimit = Infinity;
      return {
        select() { return this; },
        eq(key, value) { result = result.filter((row) => row[key] === value); return this; },
        in(key, values) { result = result.filter((row) => values.includes(row[key])); return this; },
        like(key, pattern) { result = result.filter((row) => row[key].endsWith(pattern.slice(1))); return this; },
        order() { return this; },
        limit(limit) { rowLimit = limit; return this; },
        gte(key, value) {
          assert.equal(key, "effective_at", "recency must use the typed UTC view column");
          result = result.filter((row) => Date.parse(row[key]) >= Date.parse(value));
          return this;
        },
        or() { return this; },
        then(resolve, reject) {
          return Promise.resolve({ data: result.slice(0, rowLimit), error: table === errorTable ? { message: "failed" } : null })
            .then(resolve, reject);
        }
      };
    }
  };
}

test("current sources exclude disabled, retired, removed and replaced boards, not degraded/failing or manual", () => {
  const actual = sourceReach.currentLiveSources(companies, sources, configured);
  assert.deepEqual(Array.from(actual, (source) => source.id), expectedIds);
});

test("Matches, detail payloads, all-roles audit, refs and shortlist never expose retired sources", async () => {
  const matches = await evaluations.loadPotentialMatches(client(database()));
  assert.deepEqual(Array.from(matches.bands.apply_now, (role) => role.id), expectedIds);
  assert.deepEqual(Array.from(matches.auditRows, (row) => row.id).sort(),
    expectedIds.flatMap((id) => [`evaluation-${id}`, `gate-${id}`]).sort());
  const refs = await evaluations.listCurrentEvaluationRefs(client(database()));
  assert.deepEqual(Array.from(refs.data, (row) => row.job_id), expectedIds);
  const interested = await shortlist.loadShortlist(client(database("interested")));
  assert.deepEqual(Array.from(interested.roles, (role) => role.id), expectedIds);
});

test("an empty eligible source set returns no live rows and failed source lookup fails closed", async () => {
  const data = database();
  data.job_sources = sources.map((source) => ({ ...source, health_status: "retired" }));
  const matches = await evaluations.loadPotentialMatches(client(data));
  assert.equal(matches.counts.applyNow, 0);
  assert.equal(matches.auditRows.length, 0);
  await assert.rejects(() => evaluations.loadPotentialMatches(client(database(), "job_sources")), /verify current sources/);
  await assert.rejects(() => shortlist.loadShortlist(client(database(), "companies")), /verify current sources/);
});

test("retirement never hides an immutable Applied snapshot, including older evaluators", async () => {
  const tracked = await applications.loadAppliedTracker(client(database()));
  assert.equal(tracked.applications.length, 1);
  assert.equal(tracked.applications[0].sourcePostingId, 4);
  assert.equal(tracked.applications[0].snapshot.modelVersion, "claude|hybrid_claude_v2");
});

test("browse applies the UTC cutoff to mixed-offset history and null-posted fallbacks before LIMIT", async () => {
  const data = database();
  const original = data.current_opportunity_evaluations[0];
  const row = (id, postedAt, firstSeenAt, effectiveAt) => ({
    ...original, job_id: id, source_job_id: `${id}`, title: `UTC boundary role ${id}`,
    posted_at: postedAt, first_seen_at: firstSeenAt, effective_at: effectiveAt
  });
  data.current_opportunity_evaluations = [
    ...Array.from({ length: 500 }, (_, index) => row(
      1000 + index, "2026-09-07T00:30:00+01:00", "2026-09-28", "2026-09-06T23:30:00Z"
    )),
    row(2001, "2026-09-06T20:00:00-04:00", "2026-09-28", "2026-09-07T00:00:00Z"),
    row(2002, null, "2026-09-06T23:30:00-04:00", "2026-09-07T03:30:00Z")
  ];
  const matches = await evaluations.loadPotentialMatches(client(data));
  assert.deepEqual(Array.from(matches.bands.apply_now, (role) => role.id), [2001, 2002]);
  const older = await evaluations.loadPotentialMatches(client(data), { includeOlder: true });
  assert.equal(older.counts.applyNow, 500);
});
