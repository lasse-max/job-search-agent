import { requireOwner } from "@/lib/auth";
import { emptyShortlistData, loadShortlist } from "@/lib/data/shortlist";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { ToApplyClient } from "./to-apply-client";

export default async function ToApplyPage() {
  const user = await requireOwner();
  const data = await loadShortlistOrFallback();
  return <ToApplyClient data={data} userEmail={user.email ?? "owner"} />;
}

async function loadShortlistOrFallback() {
  try {
    const supabase = await createSupabaseServerClient();
    return await loadShortlist(supabase);
  } catch {
    return emptyShortlistData(
      "Couldn't load the shortlist. Is migration 004 applied to Supabase?"
    );
  }
}
