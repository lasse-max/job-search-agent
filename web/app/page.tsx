import { requireOwner } from "@/lib/auth";
import {
  emptyPotentialMatchesData,
  loadPotentialMatches
} from "@/lib/data/calibrated-evaluations";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { PotentialMatchesClient } from "./potential-matches-client";

export default async function HomePage({
  searchParams
}: {
  searchParams: Promise<{ older?: string }>;
}) {
  const user = await requireOwner();
  const { older } = await searchParams;
  const data = await loadPotentialMatchesOrFallback(older === "1");

  return <PotentialMatchesClient data={data} userEmail={user.email ?? "owner"} />;
}

async function loadPotentialMatchesOrFallback(includeOlder: boolean) {
  try {
    const supabase = await createSupabaseServerClient();
    return await loadPotentialMatches(supabase, { includeOlder });
  } catch {
    return emptyPotentialMatchesData({
      title: "Couldn't load data",
      message:
        "Sextant could not read the calibrated opportunities view. Is the Supabase database migrated, and are the web app environment variables set?"
    });
  }
}
