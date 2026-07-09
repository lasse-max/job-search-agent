import { requireOwner } from "@/lib/auth";
import { loadPotentialMatches } from "@/lib/data/calibrated-evaluations";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { PotentialMatchesClient } from "./potential-matches-client";

export default async function HomePage() {
  const user = await requireOwner();
  const supabase = await createSupabaseServerClient();
  const data = await loadPotentialMatches(supabase);

  return <PotentialMatchesClient data={data} userEmail={user.email ?? "owner"} />;
}
