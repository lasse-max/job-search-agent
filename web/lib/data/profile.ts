import profileConfig from "@/generated/profile-config.json";
import type { createSupabaseServerClient } from "@/lib/supabase/server";
import type { Database } from "@/types/database";

type AppSupabaseClient = Awaited<ReturnType<typeof createSupabaseServerClient>>;
type CompanyRow = Database["public"]["Tables"]["companies"]["Row"];
type JobSourceRow = Database["public"]["Tables"]["job_sources"]["Row"];
type SourceRunRow = Database["public"]["Tables"]["source_runs"]["Row"];

export type ProfileData = {
  config: typeof profileConfig;
  live: {
    databaseCompanies: number | null;
    enabledCompanies: number | null;
    latestScanAt: string | null;
    fetchedPostings: number | null;
    successfulSources: number | null;
    scannedCompanies: number | null;
    enabledCountMismatch: boolean;
    missingConfiguredCompanies: string[];
    extraDatabaseEnabledCompanies: string[];
    companyStatuses: Record<string, { status: string; lastRunAt: string | null }>;
  };
  loadError: string | null;
};

export async function loadProfileData(supabase: AppSupabaseClient): Promise<ProfileData> {
  const [companies, sources, runs] = await Promise.all([
    supabase.from("companies").select("*"),
    supabase.from("job_sources").select("*"),
    supabase.from("source_runs").select("*").order("id", { ascending: false }).limit(500)
  ]);

  if (companies.error || sources.error || runs.error) {
    throw new Error(
      companies.error?.message ??
        sources.error?.message ??
        runs.error?.message ??
        "Profile stats unavailable"
    );
  }
  const companyRows = (companies.data ?? []) as CompanyRow[];
  const sourceRows = (sources.data ?? []) as JobSourceRow[];
  const runRows = (runs.data ?? []) as SourceRunRow[];
  const configuredEnabledNames = new Set(
    profileConfig.watchlist.companies
      .filter((company) => company.enabled)
      .map((company) => company.name)
  );
  const configuredCompanyIds = new Set(
    companyRows
      .filter((company) => configuredEnabledNames.has(company.name))
      .map((company) => company.id)
  );
  const relevantSources = sourceRows.filter(
    (source) => configuredCompanyIds.has(source.company_id) && source.source_type !== "manual"
  );
  const relevantSourceIds = new Set(relevantSources.map((source) => source.id));
  const relevantRuns = runRows.filter((run) => relevantSourceIds.has(run.job_source_id));
  const latestRunBySource = new Map<number, SourceRunRow>();
  for (const run of relevantRuns) {
    if (!latestRunBySource.has(run.job_source_id)) {
      latestRunBySource.set(run.job_source_id, run);
    }
  }
  const latestRuns = [...latestRunBySource.values()];
  const latestScanAt = latestRuns[0]?.started_at ?? null;
  const sourceCompanyById = new Map(
    relevantSources.map((source) => [source.id, source.company_id])
  );
  const scannedCompanyIds = new Set(
    latestRuns
      .map((run) => sourceCompanyById.get(run.job_source_id))
      .filter((companyId): companyId is number => companyId !== undefined)
  );
  const databaseEnabledCompanies = companyRows.filter((company) => company.enabled === 1).length;
  const databaseEnabledNames = new Set(
    companyRows.filter((company) => company.enabled === 1).map((company) => company.name)
  );
  const missingConfiguredCompanies = [...configuredEnabledNames]
    .filter((name) => !databaseEnabledNames.has(name))
    .sort();
  const extraDatabaseEnabledCompanies = [...databaseEnabledNames]
    .filter((name) => !configuredEnabledNames.has(name))
    .sort();
  const companyStatuses = Object.fromEntries(
    profileConfig.watchlist.companies.map((configured) => {
      if (!configured.enabled) {
        return [configured.name, { status: "not scanned", lastRunAt: null }];
      }
      const company = companyRows.find((row) => row.name === configured.name);
      const companySources = company
        ? relevantSources.filter((source) => source.company_id === company.id)
        : [];
      const companyRuns = companySources
        .map((source) => latestRunBySource.get(source.id))
        .filter((run): run is SourceRunRow => run !== undefined)
        .sort((left, right) => right.started_at.localeCompare(left.started_at));
      const status = worstRunStatus(companyRuns.map((run) => run.status));
      return [
        configured.name,
        {
          status: status ?? (companySources.length ? "enabled · not run" : "enabled · no source"),
          lastRunAt: companyRuns[0]?.started_at ?? null
        }
      ];
    })
  );

  return {
    config: profileConfig,
    live: {
      databaseCompanies: companyRows.length,
      enabledCompanies: databaseEnabledCompanies,
      latestScanAt,
      fetchedPostings: latestRuns.length
        ? latestRuns.reduce((total, run) => total + run.fetched_count, 0)
        : null,
      successfulSources: latestRuns.length || null,
      scannedCompanies: latestRuns.length ? scannedCompanyIds.size : null,
      enabledCountMismatch:
        missingConfiguredCompanies.length > 0 || extraDatabaseEnabledCompanies.length > 0,
      missingConfiguredCompanies,
      extraDatabaseEnabledCompanies,
      companyStatuses
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
      successfulSources: null,
      scannedCompanies: null,
      enabledCountMismatch: false,
      missingConfiguredCompanies: [],
      extraDatabaseEnabledCompanies: [],
      companyStatuses: {}
    },
    loadError: message
  };
}

function worstRunStatus(statuses: string[]) {
  for (const status of ["failure", "degraded", "success"]) {
    if (statuses.includes(status)) return status;
  }
  return statuses[0] ?? null;
}
