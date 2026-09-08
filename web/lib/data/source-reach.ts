type Company = { id: number; name: string };
type Source = {
  id: number;
  company_id: number;
  source_type: string;
  source_key: string;
  health_status: string;
};
type Run = {
  id: number;
  job_source_id: number;
  started_at: string;
  fetched_count: number;
  status: string;
};
type ConfiguredCompany = {
  name: string;
  enabled: boolean;
  atsType: string;
  sourceKey: string | null;
};

export function currentSourceRuns<S extends Source, R extends Run>(
  companies: Company[], sources: S[], runs: R[], configured: ConfiguredCompany[]
) {
  const names = new Map(companies.map((company) => [company.id, company.name]));
  const active = new Map(configured.filter((company) => company.enabled).map((company) => [company.name, company]));
  const currentSources = sources.filter((source) => {
    const config = active.get(names.get(source.company_id) ?? "");
    return config && source.health_status !== "disabled" && source.source_type !== "manual"
      && source.source_type === config.atsType && source.source_key === config.sourceKey;
  });
  const sourceIds = new Set(currentSources.map((source) => source.id));
  const latest = new Map<number, R>();
  for (const run of [...runs].sort((a, b) => b.id - a.id)) {
    if (sourceIds.has(run.job_source_id) && !latest.has(run.job_source_id)) {
      latest.set(run.job_source_id, run);
    }
  }
  return { sources: currentSources, runs: [...latest.values()] };
}

export function scanReach(sources: Source[], runs: Run[]) {
  const latestScanAt = runs.map((run) => run.started_at).sort().at(-1) ?? null;
  if (!latestScanAt) return { fetchedCount: null, companyCount: null, latestScanAt };
  // The scanner has no durable batch ID yet. Use each current source's latest
  // attempt on the latest UTC scan day, never multiple retries or older days.
  const today = runs.filter((run) => run.started_at.slice(0, 10) === latestScanAt.slice(0, 10));
  const companyBySource = new Map(sources.map((source) => [source.id, source.company_id]));
  return {
    fetchedCount: today.reduce((total, run) => total + run.fetched_count, 0),
    companyCount: new Set(today.map((run) => companyBySource.get(run.job_source_id))).size,
    latestScanAt
  };
}
