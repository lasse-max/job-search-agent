"use server";

import { revalidatePath } from "next/cache";
import { requireOwner } from "@/lib/auth";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function removeManualIntake(submissionId: number) {
  if (!Number.isSafeInteger(submissionId) || submissionId <= 0) {
    return { ok: false, message: "That pending role could not be identified." };
  }

  await requireOwner();
  const supabase = await createSupabaseServerClient();
  const rpc = supabase.rpc.bind(supabase) as unknown as (
    name: string,
    args: Record<string, number>
  ) => PromiseLike<{ error: { message: string } | null }>;
  const { error } = await rpc("remove_manual_intake", {
    p_submission_id: submissionId
  });

  if (error) {
    return {
      ok: false,
      message: error.message.includes("currently processing")
        ? "This role is being evaluated now and can no longer be removed."
        : "Could not remove this role. Is migration 009 applied?"
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
