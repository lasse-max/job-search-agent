"use server";

import { revalidatePath } from "next/cache";
import { requireOwner } from "@/lib/auth";
import {
  isApplicationStage,
  type ApplicationStage
} from "@/lib/data/applications";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export type ApplicationActionResult = {
  ok: boolean;
  message: string;
};

export async function markApplied(jobPostingId: number): Promise<ApplicationActionResult> {
  if (!isPositiveInteger(jobPostingId)) {
    return { ok: false, message: "That posting is not valid." };
  }
  await requireOwner();
  const supabase = await createSupabaseServerClient();
  const { error } = await callTrackerRpc(supabase, "mark_application_applied", {
    p_job_posting_id: jobPostingId
  });
  if (error) {
    return {
      ok: false,
      message: "Could not create the application from a current calibrated evaluation."
    };
  }
  revalidatePath("/");
  revalidatePath("/to-apply");
  revalidatePath("/applied");
  return { ok: true, message: "Application added at preparing." };
}

export async function updateApplicationStage(
  applicationId: number,
  stage: ApplicationStage
): Promise<ApplicationActionResult> {
  if (!isPositiveInteger(applicationId) || !isApplicationStage(stage)) {
    return { ok: false, message: "That stage change is not valid." };
  }
  await requireOwner();
  const supabase = await createSupabaseServerClient();
  const { error } = await callTrackerRpc(supabase, "change_application_stage", {
    p_application_id: applicationId,
    p_new_stage: stage
  });
  if (error) {
    return { ok: false, message: "Could not update the application stage." };
  }
  revalidatePath("/applied");
  return { ok: true, message: "Stage updated and history recorded." };
}

export async function updateApplicationDetails(
  applicationId: number,
  input: {
    nextAction: string;
    due: string;
    contact: string;
    salary: string;
    notes: string;
  }
): Promise<ApplicationActionResult> {
  if (!isPositiveInteger(applicationId) || !isDateOrBlank(input.due)) {
    return { ok: false, message: "The application details are not valid." };
  }
  const nextAction = bounded(input.nextAction, 500);
  const contact = bounded(input.contact, 300);
  const salary = bounded(input.salary, 200);
  const notes = bounded(input.notes, 4000);
  if (nextAction === null || contact === null || salary === null || notes === null) {
    return { ok: false, message: "One or more fields are too long." };
  }

  await requireOwner();
  const supabase = await createSupabaseServerClient();
  const { error } = await callTrackerRpc(supabase, "update_application_details", {
    p_application_id: applicationId,
    p_next_action: nextAction,
    p_due: input.due || null,
    p_contact: contact,
    p_salary: salary,
    p_notes: notes
  });
  if (error) {
    return { ok: false, message: "Could not save the application details." };
  }
  revalidatePath("/applied");
  return { ok: true, message: "Working details saved." };
}

function isPositiveInteger(value: number) {
  return Number.isInteger(value) && value > 0;
}

function isDateOrBlank(value: string) {
  return value === "" || /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function bounded(value: string, limit: number) {
  const normalized = value.trim();
  return normalized.length <= limit ? normalized : null;
}

async function callTrackerRpc(
  supabase: Awaited<ReturnType<typeof createSupabaseServerClient>>,
  name:
    | "change_application_stage"
    | "mark_application_applied"
    | "update_application_details",
  args: Record<string, string | number | null>
) {
  // @supabase/ssr 0.5 narrows custom RPC arguments to undefined with newer
  // supabase-js types. Keep the exception contained until the SSR package bump.
  const rpc = supabase.rpc.bind(supabase) as unknown as (
    functionName: string,
    functionArgs: Record<string, string | number | null>
  ) => PromiseLike<{ error: { message: string } | null }>;
  return rpc(name, args);
}
