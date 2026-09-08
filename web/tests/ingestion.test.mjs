import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";

function loadTypeScript(path) {
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
  });
  const exports = {};
  vm.runInNewContext(outputText, { exports });
  return exports;
}

const errors = loadTypeScript("../lib/manual-intake-errors.ts");
const { currentSourceRuns, scanReach } = loadTypeScript("../lib/data/source-reach.ts");

test("intake errors distinguish missing RPC, ownership, changed state and unknown failure", () => {
  assert.match(errors.intakeActionError({ code: "PGRST202", message: "missing" }, "remove"), /database update/);
  assert.match(errors.intakeActionError({ code: "42501", message: "denied" }, "remove"), /Sign in/);
  assert.match(errors.intakeActionError({ code: "55000", message: "changed" }, "replace"), /Refresh/);
  assert.doesNotMatch(errors.intakeActionError({ code: "57014", message: "timeout" }, "remove"), /database update/);
  assert.doesNotMatch(errors.intakeEvaluationError("LLMProviderError: 400 Bad Request: private text"), /private text|LLMProviderError/);
});

test("scan reach excludes stale sources, manual companies, disabled companies and repeat scans", () => {
  const companies = [{ id: 1, name: "Current" }, { id: 2, name: "Disabled" }, { id: 3, name: "Manual" }];
  const configured = [
    { name: "Current", enabled: true, atsType: "ashby", sourceKey: "current" },
    { name: "Disabled", enabled: false, atsType: "lever", sourceKey: "disabled" }
  ];
  const sources = [
    { id: 1, company_id: 1, source_type: "ashby", source_key: "current", health_status: "healthy" },
    { id: 2, company_id: 1, source_type: "lever", source_key: "old", health_status: "degraded" },
    { id: 3, company_id: 2, source_type: "lever", source_key: "disabled", health_status: "degraded" },
    { id: 4, company_id: 3, source_type: "manual", source_key: "manual", health_status: "healthy" }
  ];
  const runs = [
    { id: 10, job_source_id: 1, fetched_count: 12, status: "success", started_at: "2026-09-08T06:00:00Z" },
    { id: 11, job_source_id: 1, fetched_count: 15, status: "success", started_at: "2026-09-08T08:00:00Z" },
    ...[2, 3, 4].map((id) => ({ id: 20 + id, job_source_id: id, fetched_count: 999, status: "success", started_at: "2026-09-08T09:00:00Z" }))
  ];
  const current = currentSourceRuns(companies, sources, runs, configured);
  const reach = scanReach(current.sources, current.runs);
  assert.equal(current.sources.length, 1);
  assert.equal(current.runs.length, 1);
  assert.equal(reach.fetchedCount, 15);
  assert.equal(reach.companyCount, 1);
  assert.equal(reach.latestScanAt, "2026-09-08T08:00:00Z");
});

test("latest-day reach includes a failed attempt but never yesterday's volume", () => {
  const sources = [1, 2].map((id) => ({ id, company_id: id }));
  const runs = [
    { id: 1, job_source_id: 1, fetched_count: 100, status: "success", started_at: "2026-09-07T06:00:00Z" },
    { id: 2, job_source_id: 2, fetched_count: 0, status: "failure", started_at: "2026-09-08T06:00:00Z" }
  ];
  assert.equal(scanReach(sources, runs).fetchedCount, 0);
  assert.equal(scanReach(sources, runs).companyCount, 1);
  assert.equal(scanReach([], []).companyCount, null);
});
