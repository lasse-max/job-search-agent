import type { SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "@/types/database";

export const CURRENT_EVALUATOR_VERSION = "hybrid_claude_v2";
export const CURRENT_EVALUATOR_VERSION_SUFFIX = `%|${CURRENT_EVALUATOR_VERSION}`;

export async function listCurrentEvaluationRefs(
  supabase: SupabaseClient<Database>,
  limit = 25
) {
  return supabase
    .from("current_opportunity_evaluations")
    .select("job_id, role_evaluation_id, model_version")
    .like("model_version", CURRENT_EVALUATOR_VERSION_SUFFIX)
    .order("evaluated_at", { ascending: false })
    .limit(limit);
}
