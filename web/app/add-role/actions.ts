"use server";

import { revalidatePath } from "next/cache";
import { requireOwner } from "@/lib/auth";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export type ManualIntakeMode = "url" | "text" | "manual";
export type ManualIntakeDestination = "potential_matches" | "to_apply" | "applied";

export type ManualIntakeInput = {
  mode: ManualIntakeMode;
  company: string;
  title: string;
  location: string;
  url: string;
  jdText: string;
  note: string;
  destination: ManualIntakeDestination;
  proposeWatchlist: boolean;
};

export async function submitManualIntake(input: ManualIntakeInput) {
  const validated = validateInput(input);
  if (!validated.ok) return validated;
  await requireOwner();
  const supabase = await createSupabaseServerClient();
  const rpc = supabase.rpc.bind(supabase) as unknown as (
    name: string,
    args: Record<string, string | boolean | null>
  ) => PromiseLike<{ error: { message: string } | null }>;
  const { error } = await rpc("submit_manual_intake", {
    p_intake_mode: input.mode,
    p_company: input.company.trim(),
    p_title: input.title.trim(),
    p_location: input.location.trim() || null,
    p_source_url: input.url.trim() || null,
    p_jd_text: input.jdText.trim() || null,
    p_note: input.note.trim() || null,
    p_destination: input.destination,
    p_propose_watchlist: input.proposeWatchlist
  });
  if (error) {
    return { ok: false, message: "Could not queue this role. Is migration 008 applied?" };
  }
  revalidatePath("/");
  revalidatePath("/to-apply");
  revalidatePath("/applied");
  revalidatePath("/add-role");
  return {
    ok: true,
    message:
      input.mode === "manual"
        ? "Saved as not evaluated."
        : "Queued for the existing agent evaluator on the next scan."
  };
}

function validateInput(input: ManualIntakeInput) {
  if (!input.company.trim() || !input.title.trim()) {
    return { ok: false, message: "Company and title are required." };
  }
  if (input.company.length > 200 || input.title.length > 300 || input.note.length > 4000) {
    return { ok: false, message: "One or more fields are too long." };
  }
  if (input.mode === "url" || input.url.trim()) {
    try {
      const url = new URL(input.url);
      if (!["http:", "https:"].includes(url.protocol)) throw new Error("invalid protocol");
    } catch {
      return { ok: false, message: "Enter a valid http(s) job URL." };
    }
  }
  if (input.mode === "text" && input.jdText.trim().length < 120) {
    return { ok: false, message: "Paste at least 120 characters of JD text." };
  }
  return { ok: true, message: "Valid." };
}
