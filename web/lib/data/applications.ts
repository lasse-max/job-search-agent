import type { createSupabaseServerClient } from "@/lib/supabase/server";
import {
  CURRENT_EVALUATOR_VERSION,
  type AlignmentEvidence,
  type GapEvidence
} from "@/lib/data/calibrated-evaluations";
import type { Database, Json } from "@/types/database";

type AppSupabaseClient = Awaited<ReturnType<typeof createSupabaseServerClient>>;
type ApplicationDbRow = Database["public"]["Tables"]["applications"]["Row"];
type ApplicationEventDbRow = Database["public"]["Tables"]["application_events"]["Row"];

export const APPLICATION_STAGES = [
  "preparing",
  "applied",
  "recruiter_screen",
  "interviewing",
  "final_round",
  "offer",
  "rejected",
  "withdrawn"
] as const;

export const FUNNEL_STAGES = APPLICATION_STAGES.slice(0, 6);

export type ApplicationStage = (typeof APPLICATION_STAGES)[number];

export type ApplicationStageEvent = {
  id: number;
  actor: string;
  occurredAt: string;
  previousStage: ApplicationStage | null;
  newStage: ApplicationStage;
};

export type ApplicationSnapshot = {
  capturedAt: string;
  evaluatedAt: string;
  modelVersion: string;
  isEarlierEvaluator: boolean;
  fitScore: number;
  recommendation: string;
  alignments: AlignmentEvidence[];
  gaps: GapEvidence[];
};

export type TrackedApplication = {
  id: number;
  company: string;
  role: string;
  location: string;
  url: string | null;
  stage: ApplicationStage;
  appliedAt: string;
  appliedCalendarWeek: number;
  nextAction: string;
  due: string | null;
  contact: string;
  salary: string;
  notes: string;
  sourcePostingId: number;
  snapshot: ApplicationSnapshot;
  events: ApplicationStageEvent[];
};

export type AppliedTrackerData = {
  applications: TrackedApplication[];
  stats: {
    active: number;
    inInterview: number;
    offers: number;
    closed: number;
  };
  funnel: Array<{ stage: ApplicationStage; count: number }>;
  loadError: { title: string; message: string } | null;
};

export async function loadAppliedTracker(
  supabase: AppSupabaseClient
): Promise<AppliedTrackerData> {
  const { data: applicationData, error: applicationError } = await supabase
    .from("applications")
    .select("*")
    .order("updated_at", { ascending: false });

  if (applicationError) {
    throw new Error(`Unable to load applications: ${applicationError.message}`);
  }

  const applicationRows = (applicationData ?? []) as ApplicationDbRow[];
  const applicationIds = applicationRows.map((row) => row.id);
  let eventRows: ApplicationEventDbRow[] = [];
  if (applicationIds.length) {
    const { data: eventData, error: eventError } = await supabase
      .from("application_events")
      .select("*")
      .in("application_id", applicationIds)
      .order("occurred_at", { ascending: false })
      .order("id", { ascending: false });
    if (eventError) {
      throw new Error(`Unable to load application history: ${eventError.message}`);
    }
    eventRows = (eventData ?? []) as ApplicationEventDbRow[];
  }

  const eventsByApplication = new Map<number, ApplicationStageEvent[]>();
  for (const row of eventRows) {
    const normalized = normalizeEvent(row);
    if (!normalized) {
      continue;
    }
    const current = eventsByApplication.get(row.application_id) ?? [];
    current.push(normalized);
    eventsByApplication.set(row.application_id, current);
  }

  const applications = applicationRows
    .map((row) => normalizeApplication(row, eventsByApplication.get(row.id) ?? []))
    .filter((row): row is TrackedApplication => row !== null);

  return buildAppliedTrackerData(applications);
}

export function emptyAppliedTrackerData(
  loadError: AppliedTrackerData["loadError"] = null
): AppliedTrackerData {
  return buildAppliedTrackerData([], loadError);
}

function buildAppliedTrackerData(
  applications: TrackedApplication[],
  loadError: AppliedTrackerData["loadError"] = null
): AppliedTrackerData {
  const count = (stages: ApplicationStage[]) =>
    applications.filter((application) => stages.includes(application.stage)).length;

  return {
    applications,
    stats: {
      active: count(["preparing", "applied", "recruiter_screen"]),
      inInterview: count(["interviewing", "final_round"]),
      offers: count(["offer"]),
      closed: count(["rejected", "withdrawn"])
    },
    funnel: FUNNEL_STAGES.map((stage) => ({
      stage,
      count: count([stage])
    })),
    loadError
  };
}

function normalizeApplication(
  row: ApplicationDbRow,
  events: ApplicationStageEvent[]
): TrackedApplication | null {
  if (!isApplicationStage(row.stage)) {
    return null;
  }
  const snapshot = normalizeSnapshot(row.eval_snapshot_json);
  if (!snapshot) {
    return null;
  }
  return {
    id: row.id,
    company: row.company,
    role: row.role,
    location: row.location,
    url: safeHttpUrl(row.url),
    stage: row.stage,
    appliedAt: row.applied_at,
    appliedCalendarWeek: row.applied_calendar_week,
    nextAction: row.next_action ?? "",
    due: row.due,
    contact: row.contact ?? "",
    salary: row.salary ?? "",
    notes: row.notes ?? "",
    sourcePostingId: row.source_posting_id,
    snapshot,
    events
  };
}

function normalizeSnapshot(value: Json): ApplicationSnapshot | null {
  const snapshot = asRecord(value);
  const evaluation = asRecord(snapshot?.evaluation);
  const modelVersion = readString(snapshot?.model_version);
  if (
    !snapshot ||
    !evaluation ||
    !modelVersion ||
    modelVersion.toLowerCase().includes("deterministic_fallback") ||
    isFallbackEvaluation(evaluation)
  ) {
    return null;
  }
  return {
    capturedAt: readString(snapshot.captured_at),
    evaluatedAt: readString(snapshot.evaluated_at),
    modelVersion,
    isEarlierEvaluator: !modelVersion.endsWith(`|${CURRENT_EVALUATOR_VERSION}`),
    fitScore: clampPercent(readNumber(evaluation.role_fit_score)),
    recommendation: readString(evaluation.recommendation) || "unknown",
    alignments: readAlignments(evaluation.alignments),
    gaps: readGaps(evaluation.gaps)
  };
}

function normalizeEvent(row: ApplicationEventDbRow): ApplicationStageEvent | null {
  if (!isApplicationStage(row.new_stage)) {
    return null;
  }
  const previousStage = row.previous_stage;
  if (previousStage !== null && !isApplicationStage(previousStage)) {
    return null;
  }
  return {
    id: row.id,
    actor: row.actor,
    occurredAt: row.occurred_at,
    previousStage,
    newStage: row.new_stage
  };
}

export function isApplicationStage(value: string): value is ApplicationStage {
  return APPLICATION_STAGES.some((stage) => stage === value);
}

export function applicationStageLabel(stage: ApplicationStage) {
  return stage.replaceAll("_", " ");
}

function isFallbackEvaluation(evaluation: Record<string, unknown>) {
  const provenance = asRecord(evaluation.provenance);
  return (
    readBoolean(provenance?.is_fallback) ||
    readBoolean(provenance?.fallback_quality) ||
    readString(provenance?.model_version).toLowerCase().includes("deterministic_fallback") ||
    readString(provenance?.evaluator_version).toLowerCase().includes("deterministic_fallback")
  );
}

function readAlignments(value: unknown): AlignmentEvidence[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map(asRecord)
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
    .map(asRecord)
    .filter((item): item is Record<string, unknown> => item !== null)
    .map((item) => ({
      gap: readString(item.gap) || "Gap not specified",
      severity: readString(item.severity) || "medium",
      mitigation: readString(item.mitigation) || "Mitigation not recorded"
    }));
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function readString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function readNumber(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function readBoolean(value: unknown) {
  if (typeof value === "boolean") {
    return value;
  }
  return typeof value === "string" && value.toLowerCase() === "true";
}

function clampPercent(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function safeHttpUrl(value: string | null) {
  if (!value) {
    return null;
  }
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}
