"use server";

import { revalidatePath } from "next/cache";
import { requireOwner } from "@/lib/auth";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export type OpportunityActionResult = {
  ok: boolean;
  message: string;
};

export async function markToApply(
  jobPostingId: number,
  note = ""
): Promise<OpportunityActionResult> {
  if (!isPositiveInteger(jobPostingId) || note.trim().length > 1000) {
    return { ok: false, message: "That shortlist request is not valid." };
  }
  await requireOwner();
  const supabase = await createSupabaseServerClient();
  const { error } = await callOpportunityRpc(supabase, "mark_opportunity_interested", {
    p_job_posting_id: jobPostingId,
    p_note: note.trim() || null
  });
  if (error) {
    return { ok: false, message: "Could not shortlist this current calibrated role." };
  }
  revalidatePath("/");
  revalidatePath("/to-apply");
  return { ok: true, message: "Added to To Apply." };
}

export async function removeFromShortlist(
  jobPostingId: number
): Promise<OpportunityActionResult> {
  if (!isPositiveInteger(jobPostingId)) {
    return { ok: false, message: "That posting is not valid." };
  }
  await requireOwner();
  const supabase = await createSupabaseServerClient();
  const { error } = await callOpportunityRpc(supabase, "remove_opportunity_interest", {
    p_job_posting_id: jobPostingId
  });
  if (error) {
    return { ok: false, message: "Could not remove this role from the shortlist." };
  }
  revalidatePath("/");
  revalidatePath("/to-apply");
  return { ok: true, message: "Returned to Potential Matches." };
}

function isPositiveInteger(value: number) {
  return Number.isInteger(value) && value > 0;
}

async function callOpportunityRpc(
  supabase: Awaited<ReturnType<typeof createSupabaseServerClient>>,
  name: "mark_opportunity_interested" | "remove_opportunity_interest",
  args: Record<string, string | number | null>
) {
  const rpc = supabase.rpc.bind(supabase) as unknown as (
    functionName: string,
    functionArgs: Record<string, string | number | null>
  ) => PromiseLike<{ error: { message: string } | null }>;
  return rpc(name, args);
}
