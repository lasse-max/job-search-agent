import type { createSupabaseServerClient } from "@/lib/supabase/server";
import type { Database } from "@/types/database";
import profileConfig from "@/generated/profile-config.json";
import { currentLiveSources } from "@/lib/data/source-reach";

type AppSupabaseClient = Awaited<ReturnType<typeof createSupabaseServerClient>>;
type CompanyRow = Database["public"]["Tables"]["companies"]["Row"];
type SourceRow = Database["public"]["Tables"]["job_sources"]["Row"];

export async function loadCurrentSourceIds(supabase: AppSupabaseClient): Promise<number[]> {
  const [companies, sources] = await Promise.all([
    supabase.from("companies").select("*"),
    supabase.from("job_sources").select("*")
  ]);
  if (companies.error || sources.error) {
    throw new Error("Unable to verify current sources. Please try again after the scan completes.");
  }
  return currentLiveSources(
    (companies.data ?? []) as CompanyRow[],
    (sources.data ?? []) as SourceRow[],
    profileConfig.watchlist.companies
  ).map((source) => source.id);
}
