import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";

const { outputText } = ts.transpileModule(
  readFileSync(new URL("../lib/recency.ts", import.meta.url), "utf8"),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }
);
const exports = {};
vm.runInNewContext(outputText, {
  exports,
  require: () => ({ default: { recency: { maxAgeDays: 21 } } })
});

test("recency and chips normalize complete offsets before comparing UTC calendar days", () => {
  const now = new Date("2026-10-06T00:00:00Z");
  for (const [postedAt, firstSeenAt, older, label] of [
    ["2026-09-14T23:30:00-04:00", "2026-10-06", false, "posted 21d ago"],
    ["2026-09-14T20:00:00-04:00", "2026-10-06", false, "posted 21d ago"],
    ["2026-09-15T00:30:00+01:00", "2026-10-06", true, "posted 22d ago"],
    [null, "2026-09-14T23:30:00-04:00", false, "first seen 21d ago"],
    ["2026-09-15", "2026-10-06", false, "posted 21d ago"],
    ["2026-09-15T00:00:00", "2026-10-06", false, "posted 21d ago"],
    ["invalid", "2026-10-06", true, "posted date unknown"]
  ]) {
    const role = { postedAt, firstSeenAt };
    assert.equal(exports.roleIsOlderThanPolicy(role, now), older, `${postedAt} / ${firstSeenAt}`);
    assert.equal(exports.freshnessLabel(role, now), label);
  }
  assert.equal(exports.recencyCutoffDate(now), "2026-09-15");
});

test("normalization orders actual instants and does not depend on browser timezone", () => {
  assert.ok(exports.normalizeTimestamp("2026-09-15T09:00:00-04:00") >
    exports.normalizeTimestamp("2026-09-15T12:00:00+00:00"));
  assert.equal(exports.normalizeTimestamp("2026-09-15T00:00:00"),
    Date.parse("2026-09-15T00:00:00Z"));
});
