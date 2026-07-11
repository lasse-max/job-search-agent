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
const companies = watchlist.companies.map((company) => ({
  name: company.name,
  tier: company.tier,
  enabled: Boolean(company.enabled),
  coverageState: company.coverage_state,
  targetLocations: company.target_locations ?? []
}));

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
    companies
  }
};

const outputPath = join(webRoot, "generated", "profile-config.json");
mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");
console.log(`Generated ${outputPath}`);
