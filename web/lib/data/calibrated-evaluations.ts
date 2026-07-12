import type { createSupabaseServerClient } from "@/lib/supabase/server";
import type { Database } from "@/types/database";
import { ROLE_MAX_AGE_DAYS, recencyCutoffDate } from "@/lib/recency";
import { loadOpenManualIntakes, type ManualIntakeEntry } from "@/lib/data/manual-intake";

export const CURRENT_EVALUATOR_VERSION = "hybrid_claude_v4";
export const CURRENT_EVALUATOR_VERSION_SUFFIX = `%|${CURRENT_EVALUATOR_VERSION}`;

type AppSupabaseClient = Awaited<ReturnType<typeof createSupabaseServerClient>>;
type CurrentEvaluationRow =
  Database["public"]["Views"]["current_opportunity_evaluations"]["Row"];
type SkipRow = Database["public"]["Tables"]["evaluation_skips"]["Row"];
type PostingRow = Pick<
  Database["public"]["Tables"]["job_postings"]["Row"],
  "id" | "company_id" | "title" | "locations_json" | "source_url" | "availability_state"
>;
type CompanyRow = Pick<Database["public"]["Tables"]["companies"]["Row"], "id" | "name" | "tier">;
type ScanRunRow = Pick<
  Database["public"]["Tables"]["source_runs"]["Row"],
  "started_at" | "fetched_count" | "status"
>;

export type Recommendation = "apply_now" | "consider" | "stretch" | "skip" | "blocked";
export type MatchBand = "apply_now" | "consider" | "stretch" | "low_priority";
export type SurfacedBand = Exclude<MatchBand, "low_priority">;

export type AlignmentEvidence = {
  jobRequirement: string;
  candidateEvidence: string;
  evidenceStrength: "strong" | "medium" | "weak" | string;
};

export type GapEvidence = {
  gap: string;
  severity: "low" | "medium" | "high" | string;
  mitigation: string;
};

export type PotentialMatch = {
  id: number;
  stableId: string;
  company: string;
  title: string;
  department: string;
  sourceUrl: string | null;
  locations: string[];
  locationsLabel: string;
  tier: number;
  recommendation: Recommendation;
  band: MatchBand;
  fitScore: number;
  confidencePct: number;
  estimatedLevel: "L3" | "L4" | "L5" | "L6" | "L7+" | "unknown";
  levelConfidence: number;
  levelRationale: string;
  feasibilityPct: number;
  feasibilityState: string;
  feasibilityReason: string;
  summary: string;
  topAlignment: string;
  topGap: string;
  alignments: AlignmentEvidence[];
  gaps: GapEvidence[];
  hardBlockers: string[];
  firstSeenAt: string;
  postedAt: string | null;
  evaluatedAt: string;
  reviewState: string;
  skipReason: string | null;
};

export type AuditRow = {
  id: string;
  fitScore: number | null;
  company: string;
  title: string;
  reason: string;
  source: "evaluation" | "gate";
  createdAt: string;
};

export type PotentialMatchesData = {
  generatedAtLabel: string;
  scanReach: {
    fetchedCount: number | null;
    companyCount: number | null;
    latestScanAt: string | null;
  };
  bands: Record<SurfacedBand, PotentialMatch[]>;
  auditRows: AuditRow[];
  manualEntries: ManualIntakeEntry[];
  counts: {
    applyNow: number;
    consider: number;
    stretch: number;
    audit: number;
  };
  includeOlder: boolean;
  maxAgeDays: number;
  initialExpandedId: number | null;
  loadError: {
    title: string;
    message: string;
  } | null;
};

export async function listCurrentEvaluationRefs(
  supabase: AppSupabaseClient,
  limit = 25
) {
  return supabase
    .from("current_opportunity_evaluations")
    .select("job_id, role_evaluation_id, model_version")
    .like("model_version", CURRENT_EVALUATOR_VERSION_SUFFIX)
    .order("evaluated_at", { ascending: false })
    .limit(limit);
}

export async function loadPotentialMatches(
  supabase: AppSupabaseClient,
  options: { includeOlder?: boolean } = {}
): Promise<PotentialMatchesData> {
  let evaluationQuery = supabase
    .from("current_opportunity_evaluations")
    .select("*")
    .eq("availability_state", "open")
    .like("model_version", CURRENT_EVALUATOR_VERSION_SUFFIX)
    .order("evaluated_at", { ascending: false })
    .limit(500);
  if (!options.includeOlder) {
    const cutoff = recencyCutoffDate();
    evaluationQuery = evaluationQuery.or(
      `posted_at.gte.${cutoff},and(posted_at.is.null,first_seen_at.gte.${cutoff})`
    );
  }
  const { data: evaluationRows, error } = await evaluationQuery;

  if (error) {
    throw new Error(`Unable to load calibrated evaluations: ${error.message}`);
  }

  const allCurrentMatches = collapseLocationVariants(
    (evaluationRows ?? [])
      .map(normalizeCurrentEvaluation)
      .filter((role): role is PotentialMatch => role !== null)
  );
  const reviewableMatches = allCurrentMatches.filter((role) => role.reviewState === "new");
  const surfacedMatches = reviewableMatches.filter((role) =>
    ["apply_now", "consider", "stretch"].includes(role.recommendation)
  );
  const bands: Record<SurfacedBand, PotentialMatch[]> = {
    apply_now: surfacedMatches.filter((role) => role.recommendation === "apply_now"),
    consider: surfacedMatches.filter((role) => role.recommendation === "consider"),
    stretch: surfacedMatches.filter((role) => role.recommendation === "stretch")
  };

  const [skipAuditRows, scanReach, manualEntries] = await Promise.all([
    loadSkipAuditRows(supabase),
    loadScanReach(supabase),
    loadOpenManualIntakes(supabase, "potential_matches")
  ]);
  const evaluatedAuditRows = allCurrentMatches
    .map((role) => matchToAuditRow(role))
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt));
  const auditRows = [...evaluatedAuditRows, ...skipAuditRows].slice(0, 160);
  const firstExpandable =
    bands.apply_now[0]?.id ?? bands.consider[0]?.id ?? bands.stretch[0]?.id ?? null;

  return {
    generatedAtLabel: formatDateTime(new Date().toISOString()),
    scanReach,
    bands,
    auditRows,
    manualEntries,
    counts: {
      applyNow: bands.apply_now.length,
      consider: bands.consider.length,
      stretch: bands.stretch.length,
      audit: auditRows.length
    },
    includeOlder: Boolean(options.includeOlder),
    maxAgeDays: ROLE_MAX_AGE_DAYS,
    initialExpandedId: firstExpandable,
    loadError: null
  };
}

export function emptyPotentialMatchesData(loadError: PotentialMatchesData["loadError"] = null) {
  return {
    generatedAtLabel: formatDateTime(new Date().toISOString()),
    scanReach: {
      fetchedCount: null,
      companyCount: null,
      latestScanAt: null
    },
    bands: {
      apply_now: [],
      consider: [],
      stretch: []
    },
    auditRows: [],
    manualEntries: [],
    counts: {
      applyNow: 0,
      consider: 0,
      stretch: 0,
      audit: 0
    },
    includeOlder: false,
    maxAgeDays: ROLE_MAX_AGE_DAYS,
    initialExpandedId: null,
    loadError
  } satisfies PotentialMatchesData;
}

export function normalizeCurrentEvaluation(row: CurrentEvaluationRow): PotentialMatch | null {
  const evaluation = parseJsonObject(row.evaluation_json);
  if (!evaluation || isFallbackEvaluation(evaluation)) {
    return null;
  }

  const recommendation = normalizeRecommendation(readString(evaluation.recommendation));
  const fitScore = clampPercent(readNumber(evaluation.role_fit_score), 0);
  const confidencePct = normalizePercent(readNumber(evaluation.confidence), 0);
  const estimatedLevel = normalizeEstimatedLevel(readString(evaluation.estimated_level));
  const levelConfidence = clampPercent(readNumber(evaluation.level_confidence), 0);
  const levelRationale =
    readString(evaluation.level_rationale) || "Insufficient evidence to estimate level.";
  const feasibility = asRecord(evaluation.feasibility);
  const feasibilityState = readString(feasibility?.state) || "unknown";
  const feasibilityReason = readString(feasibility?.reason) || "No feasibility note recorded.";
  const locations = parseLocations(row.locations_json);
  const alignments = readAlignments(evaluation.alignments);
  const gaps = readGaps(evaluation.gaps);
  const hardBlockers = readHardBlockers(evaluation.hard_blockers);
  const summary = readString(evaluation.summary) || "No summary recorded.";
  const sourceUrl = safeHttpUrl(row.source_url);
  const topAlignment = formatTopAlignment(alignments[0]);
  const topGap = gaps[0]?.gap || hardBlockers[0] || "No major gap recorded.";

  return {
    id: row.job_id,
    stableId: `${row.source_type}:${row.source_key}:${row.source_job_id}`,
    company: row.company,
    title: row.title,
    department: row.department ?? "",
    sourceUrl,
    locations,
    locationsLabel: locations.length ? locations.join(", ") : "Unknown location",
    tier: row.company_tier,
    recommendation,
    band: recommendationToBand(recommendation),
    fitScore,
    confidencePct,
    estimatedLevel,
    levelConfidence,
    levelRationale,
    feasibilityPct: feasibilityStateToPct(feasibilityState),
    feasibilityState,
    feasibilityReason,
    summary,
    topAlignment,
    topGap,
    alignments,
    gaps,
    hardBlockers,
    firstSeenAt: row.first_seen_at,
    postedAt: row.posted_at,
    evaluatedAt: row.evaluated_at,
    reviewState: row.review_state,
    skipReason: skipReasonForEvaluation(recommendation, hardBlockers, gaps, row.review_state)
  };
}

export function collapseLocationVariants(roles: PotentialMatch[]): PotentialMatch[] {
  const recommendationRank: Record<Recommendation, number> = {
    apply_now: 0,
    consider: 1,
    stretch: 2,
    skip: 3,
    blocked: 4
  };
  const ranked = [...roles].sort(
    (left, right) =>
      recommendationRank[left.recommendation] - recommendationRank[right.recommendation] ||
      right.fitScore - left.fitScore
  );
  const merged = new Map<string, PotentialMatch>();
  for (const role of ranked) {
    const baseTitle = stripLocationSuffix(role.title, role.locations);
    const isLocationVariant = baseTitle.toLocaleLowerCase() !== role.title.trim().toLocaleLowerCase();
    const materialSignature = locationVariantMaterialSignature(role);
    const key = [role.company, baseTitle, role.department, materialSignature]
      .map((value) => value.toLocaleLowerCase().trim())
      .join("|");
    const existing = merged.get(key);
    if (!existing) {
      merged.set(key, { ...role, title: baseTitle });
      continue;
    }
    const existingIsLocationVariant =
      stripLocationSuffix(existing.title, existing.locations).toLocaleLowerCase() !==
      existing.title.trim().toLocaleLowerCase();
    const existingLocations = new Set(existing.locations.map(normalWords));
    const addsDistinctLocation = role.locations.some(
      (location) => !existingLocations.has(normalWords(location))
    );
    if (!isLocationVariant && !existingIsLocationVariant && !addsDistinctLocation) {
      merged.set(`${key}|job:${role.id}`, role);
      continue;
    }
    const locations = [...existing.locations];
    for (const location of role.locations) {
      if (!locations.includes(location)) locations.push(location);
    }
    merged.set(key, {
      ...existing,
      locations,
      locationsLabel: locations.length ? locations.join(", ") : "Unknown location"
    });
  }
  return [...merged.values()];
}

function locationVariantMaterialSignature(role: PotentialMatch) {
  return JSON.stringify({
    recommendation: role.recommendation,
    estimatedLevel: role.estimatedLevel,
    blockers: [...role.hardBlockers].sort(),
    feasibility: role.feasibilityState,
    alignmentRequirements: role.alignments.map((alignment) => alignment.jobRequirement),
    gaps: role.gaps.map((gap) => gap.gap)
  });
}

function stripLocationSuffix(title: string, locations: string[]) {
  const match = title.trim().match(/^(.+?)(?:\s+[-–—]\s+|\s*\()([^()]+?)\)?$/);
  if (!match) return title.trim();
  const [, base, suffix] = match;
  const normalizedSuffix = normalWords(suffix);
  const knownRegions = new Set([
    "anz",
    "apac",
    "australia",
    "canada",
    "dach",
    "emea",
    "europe",
    "germany",
    "mena",
    "netherlands",
    "singapore",
    "spain",
    "sweden",
    "uk",
    "united kingdom",
    "us",
    "usa",
    "united states"
  ]);
  const isPostingLocation = locations.some((location) => {
    const normalizedLocation = normalWords(location);
    const parts = location.split(/[,/|]/).map(normalWords);
    return (
      normalizedSuffix === normalizedLocation ||
      parts.includes(normalizedSuffix) ||
      normalizedLocation.startsWith(`${normalizedSuffix} `)
    );
  });
  return knownRegions.has(normalizedSuffix) || isPostingLocation ? base.trim() : title.trim();
}

function normalWords(value: string) {
  return value.toLocaleLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function normalizeEstimatedLevel(
  value: string
): "L3" | "L4" | "L5" | "L6" | "L7+" | "unknown" {
  return ["L3", "L4", "L5", "L6", "L7+"].includes(value)
    ? (value as "L3" | "L4" | "L5" | "L6" | "L7+")
    : "unknown";
}

async function loadSkipAuditRows(supabase: AppSupabaseClient): Promise<AuditRow[]> {
  const { data: skips, error } = await supabase
    .from("evaluation_skips")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(80);

  const skipRows = (skips ?? []) as SkipRow[];
  if (error || !skipRows.length) {
    return [];
  }

  const postingIds = [...new Set(skipRows.map((skip) => skip.job_posting_id))];
  const { data: postings } = await supabase
    .from("job_postings")
    .select("*")
    .in("id", postingIds);
  const postingRows = (postings ?? []) as PostingRow[];
  const postingsById = new Map(postingRows.map((posting) => [posting.id, posting]));
  const companyIds = [...new Set(postingRows.map((posting) => posting.company_id))];
  const { data: companies } = companyIds.length
    ? await supabase.from("companies").select("*").in("id", companyIds)
    : { data: [] as CompanyRow[] };
  const companyRows = (companies ?? []) as CompanyRow[];
  const companiesById = new Map(companyRows.map((company) => [company.id, company]));

  return skipRows.map((skip) => skipToAuditRow(skip, postingsById, companiesById));
}

async function loadScanReach(supabase: AppSupabaseClient) {
  const [{ data: runs }, { count }] = await Promise.all([
    supabase
      .from("source_runs")
      .select("*")
      .order("id", { ascending: false })
      .limit(96),
    supabase.from("companies").select("id", { count: "exact", head: true }).eq("enabled", 1)
  ]);

  const runRows = (runs ?? []) as ScanRunRow[];
  const latestSuccessful = runRows.find((run) => run.status === "success" || run.status === "degraded");
  if (!latestSuccessful) {
    return { fetchedCount: null, companyCount: count ?? null, latestScanAt: null };
  }

  const latestDay = latestSuccessful.started_at.slice(0, 10);
  const fetchedCount = runRows
    .filter((run) => run.started_at.slice(0, 10) === latestDay)
    .reduce((total, run) => total + run.fetched_count, 0);

  return {
    fetchedCount,
    companyCount: count ?? null,
    latestScanAt: latestSuccessful.started_at
  };
}

function skipToAuditRow(
  skip: SkipRow,
  postingsById: Map<number, PostingRow>,
  companiesById: Map<number, CompanyRow>
): AuditRow {
  const posting = postingsById.get(skip.job_posting_id);
  const company = posting ? companiesById.get(posting.company_id) : undefined;
  return {
    id: `gate-${skip.id}`,
    fitScore: null,
    company: company?.name ?? "Unknown company",
    title: posting?.title ?? `Posting ${skip.job_posting_id}`,
    reason: humanizeReason(skip.reason),
    source: "gate",
    createdAt: skip.created_at
  };
}

function matchToAuditRow(role: PotentialMatch): AuditRow {
  return {
    id: `evaluation-${role.id}`,
    fitScore: role.fitScore,
    company: role.company,
    title: role.title,
    reason: role.skipReason ?? `${humanizeRecommendation(role.recommendation)} · ${role.reviewState}`,
    source: "evaluation",
    createdAt: role.evaluatedAt
  };
}

function parseJsonObject(value: string): Record<string, unknown> | null {
  try {
    return asRecord(JSON.parse(value));
  } catch {
    return null;
  }
}

function parseLocations(value: string): string[] {
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.map((item) => String(item)).filter(Boolean);
  } catch {
    return [];
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function readString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function readNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function readAlignments(value: unknown): AlignmentEvidence[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => asRecord(item))
    .filter((item): item is Record<string, unknown> => item !== null)
    .map((item) => ({
      jobRequirement: readString(item.job_requirement) || "Requirement not specified",
      candidateEvidence: readString(item.candidate_evidence) || "Evidence not recorded",
      evidenceStrength: readString(item.evidence_strength) || "medium"
    }));
}

function readGaps(value: unknown): GapEvidence[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => asRecord(item))
    .filter((item): item is Record<string, unknown> => item !== null)
    .map((item) => ({
      gap: readString(item.gap) || "Gap not specified",
      severity: readString(item.severity) || "medium",
      mitigation: readString(item.mitigation) || "Mitigation not recorded"
    }));
}

function readHardBlockers(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => {
      const record = asRecord(item);
      if (!record) {
        return "";
      }
      const type = readString(record.type) || "blocker";
      const evidence = readString(record.evidence);
      return evidence ? `${type}: ${evidence}` : type;
    })
    .filter(Boolean);
}

function isFallbackEvaluation(evaluation: Record<string, unknown>) {
  const provenance = asRecord(evaluation.provenance);
  const fallbackQuality = readString(provenance?.fallback_quality).toLowerCase();
  const isFallback = readString(provenance?.is_fallback).toLowerCase();
  const modelVersion = readString(provenance?.model_version).toLowerCase();
  const evaluatorVersion = readString(provenance?.evaluator_version).toLowerCase();
  return (
    fallbackQuality === "true" ||
    isFallback === "true" ||
    modelVersion.includes("deterministic_fallback") ||
    evaluatorVersion.includes("deterministic_fallback")
  );
}

function normalizeRecommendation(value: string): Recommendation {
  if (value === "apply_now" || value === "consider" || value === "stretch" || value === "blocked") {
    return value;
  }
  return "skip";
}

function recommendationToBand(recommendation: Recommendation): MatchBand {
  if (recommendation === "apply_now" || recommendation === "consider" || recommendation === "stretch") {
    return recommendation;
  }
  return "low_priority";
}

function normalizePercent(value: number | null, fallback: number) {
  if (value === null) {
    return fallback;
  }
  return clampPercent(value <= 1 ? Math.round(value * 100) : Math.round(value), fallback);
}

function clampPercent(value: number | null, fallback: number) {
  if (value === null || !Number.isFinite(value)) {
    return fallback;
  }
  return Math.max(0, Math.min(100, Math.round(value)));
}

function feasibilityStateToPct(state: string) {
  const normalized = state.toLowerCase();
  if (normalized === "viable") {
    return 90;
  }
  if (normalized === "sponsorship_required") {
    return 70;
  }
  if (normalized === "uncertain") {
    return 45;
  }
  if (normalized === "blocked") {
    return 0;
  }
  return 50;
}

function formatTopAlignment(alignment: AlignmentEvidence | undefined) {
  if (!alignment) {
    return "No alignment recorded.";
  }
  return `${alignment.jobRequirement} -> ${alignment.candidateEvidence}`;
}

function skipReasonForEvaluation(
  recommendation: Recommendation,
  hardBlockers: string[],
  gaps: GapEvidence[],
  reviewState: string
) {
  if (hardBlockers.length) {
    return `blocked: ${hardBlockers[0]}`;
  }
  if (recommendation === "skip" || recommendation === "blocked") {
    return gaps[0]?.gap ? `${recommendation}: ${gaps[0].gap}` : humanizeRecommendation(recommendation);
  }
  if (reviewState !== "new") {
    return `review state: ${reviewState}`;
  }
  return null;
}

function humanizeReason(value: string) {
  return value.replaceAll("_", " ").replace(/\s+/g, " ").trim();
}

export function humanizeRecommendation(value: Recommendation | string) {
  if (value === "apply_now") {
    return "Apply now";
  }
  if (value === "consider") {
    return "Consider";
  }
  if (value === "stretch") {
    return "Stretch";
  }
  if (value === "blocked") {
    return "Blocked";
  }
  return "Skip";
}

function safeHttpUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export function formatDateTime(value: string | null) {
  if (!value) {
    return "unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short"
  }).format(date);
}
