import Link from "next/link";
import type { ReactNode } from "react";
import type { ProfileData } from "@/lib/data/profile";

export function ProfileClient({ data, userEmail }: { data: ProfileData; userEmail: string }) {
  const { config } = data;
  return (
    <main className="flex min-h-screen bg-chart-page text-chart-ink">
      <ProfileNav userEmail={userEmail} />
      <section className="relative min-w-0 flex-1 overflow-hidden">
        <div className="pointer-events-none fixed bottom-0 left-56 right-0 top-0 bg-[linear-gradient(rgba(87,182,196,.028)_1px,transparent_1px),linear-gradient(90deg,rgba(87,182,196,.028)_1px,transparent_1px)] bg-[length:56px_56px]" />
        <div className="relative mx-auto max-w-[1120px] px-10 py-8 pb-24">
          <header className="flex items-end justify-between gap-6">
            <div>
              <h1 className="font-serif text-[32px] font-medium tracking-wide">Profile</h1>
              <p className="mt-1 font-mono text-[11px] text-chart-faint">
                real search criteria · read-only — edit via config
              </p>
            </div>
            <div className="text-right font-mono text-[9.5px] leading-5 text-chart-faint">
              <div>{config.versions.candidate}</div>
              <div>{config.versions.location} · {config.versions.scoring}</div>
            </div>
          </header>

          {data.loadError ? (
            <div className="mt-6 rounded-lg border border-chart-warn/30 bg-chart-warn/10 px-4 py-3 text-sm text-chart-warn">
              {data.loadError}
            </div>
          ) : null}

          <ScanStrip data={data} />
          <div className="mt-6 grid grid-cols-2 gap-5">
            <Panel title="Target role families">
              <BulletList items={config.targetRoleFamilies} />
              <Subhead>Approved stretch</Subhead>
              <BulletList items={config.approvedStretchFamilies} tone="gold" />
            </Panel>
            <Panel title="Seniority · L4–L5">
              <ChipList items={config.seniority.preferredLevels} />
              <p className="mt-4 text-[13px] leading-6 text-chart-muted">{config.seniority.principle}</p>
              <p className="mt-3 text-[13px] leading-6 text-chart-muted">{config.seniority.inScopeNote}</p>
              <p className="mt-3 border-l-2 border-chart-gold/50 pl-3 text-[13px] leading-6 text-chart-gold">
                {config.seniority.ceilingRule}
              </p>
            </Panel>
            <Panel title="Locations + work authorization">
              <Subhead>Allowlist</Subhead>
              <ChipList items={config.locations.allowedMetros} />
              <p className="mt-3 font-mono text-[10.5px] text-chart-faint">
                Tier-1 only: {config.locations.tier1Only.join(", ")} · High-friction: {config.locations.highFriction.join(", ")}
              </p>
              <div className="mt-5 flex flex-col gap-3">
                {config.locations.markets.map((market) => (
                  <div className="border-t border-white/5 pt-3" key={market.name}>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[13px] font-semibold">{market.name}</span>
                      <span className="font-mono text-[9.5px] uppercase text-chart-teal">
                        {market.authorization.replaceAll("_", " ")}
                      </span>
                    </div>
                    <p className="mt-1 text-[12px] leading-5 text-chart-muted">{market.notes}</p>
                  </div>
                ))}
              </div>
            </Panel>
            <Panel title="Language + scoring bands">
              <div className="flex gap-3">
                {config.languages.map((language) => (
                  <div className="rounded-lg border border-chart-teal/25 bg-chart-teal/10 px-3 py-2" key={language.name}>
                    <div className="text-[13px] font-semibold">{language.name}</div>
                    <div className="mt-1 font-mono text-[9.5px] uppercase text-chart-teal">{language.level}</div>
                  </div>
                ))}
              </div>
              <Subhead>Tools + skills</Subhead>
              <div className="flex flex-col gap-2">
                {Object.entries(config.toolsAndSkills).map(([tool, evidence]) => (
                  <div className="rounded border border-white/10 bg-chart-card px-3 py-2" key={tool}>
                    <span className="font-mono text-[10px] text-chart-teal">{tool}</span>
                    <span className="ml-2 text-[11.5px] leading-5 text-chart-muted">{evidence}</span>
                  </div>
                ))}
              </div>
              <Subhead>Monotonic fit bands</Subhead>
              <div className="grid grid-cols-3 gap-3">
                <Threshold label="Apply now" value={config.thresholds.applyNow} tone="rust" />
                <Threshold label="Consider" value={config.thresholds.consider} tone="teal" />
                <Threshold label="Stretch" value={config.thresholds.stretch} tone="gold" />
              </div>
              <Subhead>Hard blockers</Subhead>
              <BulletList items={config.hardBlockers} tone="warn" />
            </Panel>
          </div>

          <WatchlistCoverage data={data} />
        </div>
      </section>
    </main>
  );
}

function ScanStrip({ data }: { data: ProfileData }) {
  const stats = [
    ["config companies", data.config.watchlist.total],
    ["enabled in config", data.config.watchlist.enabled],
    ["coverage", `${data.config.watchlist.coverage.percentage}%`],
    ["postings last scan", data.live.fetchedPostings],
    ["companies last scan", data.live.scannedCompanies]
  ] as const;
  return (
    <div className="mt-6 flex rounded-lg border border-white/10 bg-chart-panel px-2 py-3">
      {stats.map(([label, value]) => (
        <div className="flex-1 border-l border-white/10 px-4 first:border-0" key={label}>
          <div className="font-mono text-[17px]">{value ?? "—"}</div>
          <div className="mt-1 text-[9px] uppercase tracking-[0.08em] text-chart-faint">{label}</div>
        </div>
      ))}
      <div className="flex-1 border-l border-white/10 px-4">
        <div className="font-mono text-[11px] leading-6">{formatDate(data.live.latestScanAt)}</div>
        <div className="text-[9px] uppercase tracking-[0.08em] text-chart-faint">last scan</div>
      </div>
    </div>
  );
}

function WatchlistCoverage({ data }: { data: ProfileData }) {
  const { coverage, companies } = data.config.watchlist;
  const scanReach =
    data.live.fetchedPostings === null || data.live.scannedCompanies === null
      ? "Latest scan reach is unavailable."
      : `Scanned ${data.live.fetchedPostings.toLocaleString("en-GB")} postings across ${data.live.scannedCompanies} companies this run.`;

  return (
    <Panel className="mt-5" title="Watchlist coverage · B-27">
      <div className="grid grid-cols-[220px_1fr] gap-5">
        <div className={`rounded-lg border bg-chart-card p-5 ${coverageTone(coverage.tone)}`}>
          <div className="font-mono text-[10px] uppercase tracking-[0.14em]">Coverage</div>
          <div className="mt-2 font-mono text-[42px] leading-none">{coverage.percentage}%</div>
          <div className="mt-3 text-[12px] leading-5 text-chart-muted">
            {coverage.scanned} of {coverage.total} companies scanned
          </div>
        </div>
        <div>
          <div className="grid grid-cols-3 gap-3">
            {coverage.byTier.map((tier) => (
              <div
                className={`rounded-lg border bg-chart-card p-4 ${coverageTone(tier.tone)}`}
                key={tier.tier}
              >
                <div className="font-mono text-[9.5px] uppercase tracking-[0.12em]">
                  Tier {tier.tier}
                </div>
                <div className="mt-2 font-mono text-[21px]">
                  {tier.scanned}/{tier.total} <span className="text-[12px]">({tier.percentage}%)</span>
                </div>
                <div className="mt-1 text-[10px] text-chart-faint">{tier.dark} dark</div>
              </div>
            ))}
          </div>
          <p className="mt-4 font-mono text-[10.5px] text-chart-muted">{scanReach}</p>
          {data.live.enabledCountMismatch ? (
            <p className="mt-2 text-[11px] leading-5 text-chart-warn">
              Config/database drift. Missing or disabled in Postgres: {data.live.missingConfiguredCompanies.join(", ") || "none"}. Extra enabled in Postgres: {data.live.extraDatabaseEnabledCompanies.join(", ") || "none"}. Coverage uses config.
            </p>
          ) : null}
        </div>
      </div>

      <Subhead>All companies by tier · scan status</Subhead>
      {[1, 2, 3].map((tier) => {
        const tierCompanies = companies.filter((company) => company.tier === tier);
        const scannedCount = tierCompanies.filter((company) => company.enabled).length;
        return (
          <details className="border-t border-white/5 py-3" key={tier} open={tier === 1}>
            <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.14em] text-chart-teal">
              Tier {tier} · {scannedCount}/{tierCompanies.length} scanned
            </summary>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {tierCompanies.map((company) => (
                <div className="rounded border border-white/5 bg-chart-card px-3 py-3" key={company.name}>
                  <div className="flex items-start justify-between gap-3">
                    <a
                      className="text-[12.5px] text-chart-ink hover:text-chart-teal"
                      href={company.careersUrl ?? "#"}
                      rel="noreferrer"
                      target="_blank"
                    >
                      {company.name}
                    </a>
                    <span className={`font-mono text-[8.5px] uppercase ${companyStatusTone(data.live.companyStatuses[company.name]?.status, company.enabled)}`}>
                      {company.enabled
                        ? `${data.live.companyStatuses[company.name]?.status ?? "enabled · status unavailable"} · ${company.atsType}`
                        : darkReasonLabel(company)}
                    </span>
                  </div>
                  {!company.enabled && company.manualFallback ? (
                    <p className="mt-2 text-[10.5px] leading-5 text-chart-faint">
                      {company.manualFallback}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </details>
        );
      })}
    </Panel>
  );
}

function coverageTone(tone: string) {
  if (tone === "red") return "border-chart-warn/45 text-chart-warn";
  if (tone === "amber") return "border-chart-gold/45 text-chart-gold";
  return "border-chart-green/45 text-chart-green";
}

function companyStatusTone(status: string | undefined, enabled: boolean) {
  if (!enabled || status === "failure") return "text-chart-warn";
  if (status === "degraded" || status?.includes("not run") || status?.includes("no source")) {
    return "text-chart-gold";
  }
  return "text-chart-green";
}

function darkReasonLabel(
  company: ProfileData["config"]["watchlist"]["companies"][number]
) {
  if (company.darkReasonCode === "dead_feed") {
    return `dead feed · ${company.atsType}:${company.sourceKey ?? "unknown"}`;
  }
  if (company.darkReasonCode === "adapter_ready_disabled") {
    return `${company.supportedAdapter ?? company.atsType} ready · disabled`;
  }
  if (company.darkReasonCode === "missing_source") {
    if (company.atsType === "unknown" && company.sourceKey === null) {
      return "ats_type: unknown · source_key: null";
    }
    if (company.atsType === "unknown") return "ats_type: unknown";
    return "source_key: null";
  }
  return "manual only";
}

function Panel({ children, className = "", title }: { children: ReactNode; className?: string; title: string }) {
  return <section className={`rounded-[10px] border border-white/10 bg-chart-panel p-5 ${className}`}><h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-chart-teal">{title}</h2><div className="mt-4">{children}</div></section>;
}

function Subhead({ children }: { children: ReactNode }) {
  return <h3 className="mb-2 mt-5 font-mono text-[9.5px] uppercase tracking-[0.14em] text-chart-faint">{children}</h3>;
}

function BulletList({ items, tone = "teal" }: { items: string[]; tone?: "gold" | "teal" | "warn" }) {
  const color = tone === "gold" ? "text-chart-gold" : tone === "warn" ? "text-chart-warn" : "text-chart-teal";
  return <ul className="flex flex-col gap-2 text-[13px] leading-5 text-chart-muted">{items.map((item) => <li className="flex gap-2" key={item}><span className={color}>·</span><span>{item}</span></li>)}</ul>;
}

function ChipList({ items }: { items: string[] }) {
  return <div className="flex flex-wrap gap-1.5">{items.map((item) => <span className="rounded border border-white/10 px-2 py-1 font-mono text-[10px] text-chart-muted" key={item}>{item}</span>)}</div>;
}

function Threshold({ label, tone, value }: { label: string; tone: "gold" | "rust" | "teal"; value: number }) {
  const color = tone === "rust" ? "text-chart-rust" : tone === "gold" ? "text-chart-gold" : "text-chart-teal";
  return <div className="rounded-lg border border-white/10 bg-chart-card p-3"><div className={`font-mono text-[20px] ${color}`}>{value}+</div><div className="mt-1 text-[10px] text-chart-faint">{label}</div></div>;
}

function ProfileNav({ userEmail }: { userEmail: string }) {
  const links = [["Potential Matches", "/"], ["Add a role", "/add-role"], ["To Apply", "/to-apply"], ["Applied", "/applied"], ["Profile", "/profile"]] as const;
  return <aside className="flex w-56 shrink-0 flex-col border-r border-white/10 px-3.5 py-5"><div className="flex items-baseline gap-2 px-2.5 pb-6"><span className="font-serif text-[21px] font-medium italic tracking-wide">Sextant</span><span className="relative -top-0.5 h-2 w-2 rotate-45 bg-chart-tealDeep" /></div><nav className="flex flex-col gap-1">{links.map(([label, href]) => <Link className={`rounded-md px-2.5 py-2 text-[13.5px] ${href === "/profile" ? "bg-chart-teal/10 text-chart-ink" : "text-chart-muted"}`} href={href} key={href}>{label}</Link>)}</nav><div className="mt-auto border-t border-white/10 px-2.5 pt-4 font-mono text-[10.5px] leading-6 text-chart-faint"><div>read-only · edit via config</div><div className="truncate text-white/30">owner · {userEmail}</div></div></aside>;
}

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}
