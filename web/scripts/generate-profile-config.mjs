import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const configRoot = join(webRoot, "..", "config");

function readYaml(name) {
  return parse(readFileSync(join(configRoot, name), "utf8"));
}

const candidate = readYaml("candidate_profile.yaml");
const location = readYaml("location_policy.yaml");
const scoring = readYaml("scoring_policy.yaml");
const watchlist = readYaml("watchlist.yaml");
const supportedAdapters = new Set(["ashby", "greenhouse", "lever"]);

function darkReasonCode(company) {
  if (company.enabled) return null;
  if (company.job_count_at_audit === 0) return "dead_feed";
  if (!company.source_key || company.ats_type === "unknown") return "missing_source";
  if (
    company.supported_adapter &&
    supportedAdapters.has(company.supported_adapter) &&
    supportedAdapters.has(company.ats_type)
  ) {
    return "adapter_ready_disabled";
  }
  return "manual_only";
}

const companies = watchlist.companies.map((company) => ({
  name: company.name,
  tier: company.tier,
  enabled: Boolean(company.enabled),
  coverageState: company.coverage_state,
  targetLocations: company.target_locations ?? [],
  atsType: company.ats_type ?? "unknown",
  sourceKey: company.source_key ?? null,
  supportedAdapter: company.supported_adapter ?? null,
  jobCountAtAudit: company.job_count_at_audit ?? null,
  careersUrl: company.careers_url ?? null,
  sourceEvidenceUrl: company.source_evidence_url ?? null,
  manualFallback: company.manual_fallback ?? null,
  notes: company.notes ?? null,
  darkReasonCode: darkReasonCode(company)
}));

function coverageFor(companyRows) {
  const scanned = companyRows.filter((company) => company.enabled).length;
  const total = companyRows.length;
  const percentage = total ? Math.round((scanned / total) * 100) : 0;
  return {
    scanned,
    total,
    percentage,
    tone: percentage < 50 ? "red" : percentage <= 80 ? "amber" : "green",
    dark: total - scanned
  };
}

const coverage = coverageFor(companies);
coverage.byTier = [1, 2, 3].map((tier) => ({
  tier,
  ...coverageFor(companies.filter((company) => company.tier === tier))
}));
coverage.darkByReason = Object.fromEntries(
  ["missing_source", "adapter_ready_disabled", "dead_feed", "manual_only"].map((reason) => [
    reason,
    companies.filter((company) => company.darkReasonCode === reason).length
  ])
);

const output = {
  versions: {
    candidate: candidate.version,
    location: location.version,
    scoring: scoring.version
  },
  targetRoleFamilies: candidate.primary_role_families,
  approvedStretchFamilies: candidate.approved_stretch_families,
  seniority: {
    preferredLevels: candidate.target_seniority.preferred_levels,
    principle: candidate.target_seniority.principle,
    inScopeNote: candidate.target_seniority.in_scope_note,
    ceilingRule: candidate.target_seniority.ceiling_rule
  },
  languages: Object.entries(candidate.languages).map(([name, level]) => ({ name, level })),
  hardBlockers: scoring.true_blockers,
  usuallyDeprioritize: candidate.usually_deprioritize,
  thresholds: {
    applyNow: scoring.recommendation_thresholds.apply_now_min_fit,
    consider: scoring.recommendation_thresholds.consider_min_fit,
    stretch: scoring.recommendation_thresholds.stretch_min_fit
  },
  locations: {
    allowedMetros: location.profile_display.allowed_metros,
    tier1Only: location.profile_display.tier1_only,
    highFriction: location.profile_display.high_friction,
    markets: Object.entries(location.markets).map(([name, policy]) => ({
      name,
      authorization: policy.current_authorization,
      sponsorshipRequired: Boolean(policy.sponsorship_required),
      availability: policy.expected_availability_date,
      confidence: policy.confidence,
      notes: policy.notes
    }))
  },
  watchlist: {
    total: companies.length,
    enabled: companies.filter((company) => company.enabled).length,
    coverage,
    companies
  }
};

const outputPath = join(webRoot, "generated", "profile-config.json");
mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");
console.log(`Generated ${outputPath}`);
