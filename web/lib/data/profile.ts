import profileConfig from "@/generated/profile-config.json";
import type { createSupabaseServerClient } from "@/lib/supabase/server";
import type { Database } from "@/types/database";

type AppSupabaseClient = Awaited<ReturnType<typeof createSupabaseServerClient>>;
type SourceRunRow = Database["public"]["Tables"]["source_runs"]["Row"];

export type ProfileData = {
  config: typeof profileConfig;
  live: {
    databaseCompanies: number | null;
    enabledCompanies: number | null;
    latestScanAt: string | null;
    fetchedPostings: number | null;
    successfulSources: number | null;
  };
  loadError: string | null;
};

export async function loadProfileData(supabase: AppSupabaseClient): Promise<ProfileData> {
  const [{ count: databaseCompanies, error: companiesError }, { count: enabledCompanies }, runs] =
    await Promise.all([
      supabase.from("companies").select("id", { count: "exact", head: true }),
      supabase.from("companies").select("id", { count: "exact", head: true }).eq("enabled", 1),
      supabase.from("source_runs").select("*").order("id", { ascending: false }).limit(160)
    ]);

  if (companiesError || runs.error) {
    throw new Error(companiesError?.message ?? runs.error?.message ?? "Profile stats unavailable");
  }
  const runRows = (runs.data ?? []) as SourceRunRow[];
  const successfulRuns = runRows.filter((run) =>
    ["success", "degraded"].includes(run.status)
  );
  const latestScanAt = successfulRuns[0]?.started_at ?? null;
  const latestDay = latestScanAt?.slice(0, 10);
  const latestRuns = latestDay
    ? successfulRuns.filter((run) => run.started_at.slice(0, 10) === latestDay)
    : [];

  return {
    config: profileConfig,
    live: {
      databaseCompanies: databaseCompanies ?? null,
      enabledCompanies: enabledCompanies ?? null,
      latestScanAt,
      fetchedPostings: latestDay
        ? latestRuns.reduce((total, run) => total + run.fetched_count, 0)
        : null,
      successfulSources: latestDay ? latestRuns.length : null
    },
    loadError: null
  };
}

export function profileDataWithoutStats(message: string): ProfileData {
  return {
    config: profileConfig,
    live: {
      databaseCompanies: null,
      enabledCompanies: null,
      latestScanAt: null,
      fetchedPostings: null,
      successfulSources: null
    },
    loadError: message
  };
}
