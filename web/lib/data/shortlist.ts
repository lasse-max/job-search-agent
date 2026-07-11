import type { createSupabaseServerClient } from "@/lib/supabase/server";
import type { Database } from "@/types/database";
import {
  CURRENT_EVALUATOR_VERSION_SUFFIX,
  normalizeCurrentEvaluation,
  type PotentialMatch
} from "@/lib/data/calibrated-evaluations";

type AppSupabaseClient = Awaited<ReturnType<typeof createSupabaseServerClient>>;
type CurrentEvaluationRow =
  Database["public"]["Views"]["current_opportunity_evaluations"]["Row"];

export type ShortlistedRole = PotentialMatch & {
  note: string | null;
  flaggedAt: string;
};

export type ShortlistData = {
  roles: ShortlistedRole[];
  loadError: string | null;
};

export async function loadShortlist(supabase: AppSupabaseClient): Promise<ShortlistData> {
  const { data, error } = await supabase
    .from("current_opportunity_evaluations")
    .select("*")
    .eq("availability_state", "open")
    .eq("review_state", "interested")
    .like("model_version", CURRENT_EVALUATOR_VERSION_SUFFIX)
    .order("reviewed_at", { ascending: true })
    .limit(200);

  if (error) {
    throw new Error(`Unable to load shortlist: ${error.message}`);
  }

  const rows = (data ?? []) as CurrentEvaluationRow[];
  const roles = rows.flatMap((row) => {
    const role = normalizeCurrentEvaluation(row);
    if (!role || role.reviewState !== "interested") {
      return [];
    }
    return [
      {
        ...role,
        note: row.decision_reason,
        flaggedAt: row.reviewed_at ?? row.evaluated_at
      }
    ];
  });

  return { roles, loadError: null };
}

export function emptyShortlistData(loadError: string | null = null): ShortlistData {
  return { roles: [], loadError };
}
