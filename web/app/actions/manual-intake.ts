"use server";

import { revalidatePath } from "next/cache";
import { requireOwner } from "@/lib/auth";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { intakeActionError, type IntakeRpcError } from "@/lib/manual-intake-errors";

export async function removeManualIntake(submissionId: number) {
  if (!Number.isSafeInteger(submissionId) || submissionId <= 0) {
    return { ok: false, message: "That pending role could not be identified." };
  }

  await requireOwner();
  const supabase = await createSupabaseServerClient();
  const rpc = supabase.rpc.bind(supabase) as unknown as (
    name: string,
    args: Record<string, number>
  ) => PromiseLike<{ error: IntakeRpcError | null }>;
  const { error } = await rpc("remove_manual_intake", {
    p_submission_id: submissionId
  });

  if (error) {
    console.warn("manual_intake_remove_failed", { code: error.code ?? "unknown" });
    return {
      ok: false,
      message: intakeActionError(error, "remove")
    };
  }

  revalidateManualIntakePages();
  return { ok: true, message: "Pending role removed." };
}

function revalidateManualIntakePages() {
  revalidatePath("/");
  revalidatePath("/to-apply");
  revalidatePath("/applied");
  revalidatePath("/add-role");
}
