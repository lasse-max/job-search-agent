import { requireOwner } from "@/lib/auth";
import {
  emptyAppliedTrackerData,
  loadAppliedTracker
} from "@/lib/data/applications";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { AppliedTrackerClient } from "./applied-tracker-client";

export default async function AppliedPage() {
  const user = await requireOwner();
  const data = await loadAppliedTrackerOrFallback();

  return <AppliedTrackerClient data={data} userEmail={user.email ?? "owner"} />;
}

async function loadAppliedTrackerOrFallback() {
  try {
    const supabase = await createSupabaseServerClient();
    return await loadAppliedTracker(supabase);
  } catch {
    return emptyAppliedTrackerData({
      title: "Couldn't load the application tracker",
      message:
        "Sextant could not read the application tables. Is migration 003 applied to Supabase?"
    });
  }
}
