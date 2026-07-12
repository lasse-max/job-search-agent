"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useMemo, useState, useTransition } from "react";
import { markToApply } from "@/app/actions/opportunities";
import type {
  AlignmentEvidence,
  AuditRow,
  GapEvidence,
  MatchBand,
  PotentialMatch,
  PotentialMatchesData
} from "@/lib/data/calibrated-evaluations";
import { formatDateTime, humanizeRecommendation } from "@/lib/data/calibrated-evaluations";
import { freshnessLabel, roleIsOlderThanPolicy } from "@/lib/recency";

type Props = {
  data: PotentialMatchesData;
  userEmail: string;
};

const bandMeta: Record<
  MatchBand,
  { label: string; shortLabel: string; accent: string; border: string; bg: string; text: string }
> = {
  apply_now: {
    label: "Apply now",
    shortLabel: "apply",
    accent: "bg-chart-rust",
    border: "border-chart-rust/45",
    bg: "bg-chart-rust/10",
    text: "text-chart-rust"
  },
  consider: {
    label: "Consider",
    shortLabel: "consider",
    accent: "bg-chart-teal",
    border: "border-chart-teal/45",
    bg: "bg-chart-teal/10",
    text: "text-chart-teal"
  },
  stretch: {
    label: "Stretch / reach",
    shortLabel: "stretch",
    accent: "bg-chart-gold",
    border: "border-chart-gold/45",
    bg: "bg-chart-gold/10",
    text: "text-chart-gold"
  },
  low_priority: {
    label: "Low priority",
    shortLabel: "low",
    accent: "bg-chart-faint",
    border: "border-white/10",
    bg: "bg-white/[0.03]",
    text: "text-chart-faint"
  }
};

export function PotentialMatchesClient({ data, userEmail }: Props) {
  const [auditOpen, setAuditOpen] = useState(false);
  const [stretchOpen, setStretchOpen] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(data.initialExpandedId);
  const [detailId, setDetailId] = useState<number | null>(null);
  const allCards = useMemo(
    () => [
      ...data.bands.apply_now,
      ...data.bands.consider,
      ...data.bands.stretch
    ],
    [data.bands]
  );
  const detailRole = allCards.find((role) => role.id === detailId) ?? null;

  return (
    <main className="flex min-h-screen bg-chart-page text-chart-ink">
      <SideNav data={data} userEmail={userEmail} />
      <section className="relative flex-1 overflow-hidden">
        <div className="pointer-events-none fixed bottom-0 left-56 right-0 top-0 bg-[linear-gradient(rgba(87,182,196,.028)_1px,transparent_1px),linear-gradient(90deg,rgba(87,182,196,.028)_1px,transparent_1px)] bg-[length:56px_56px]" />
        <div className="relative mx-auto max-w-[1020px] px-10 py-8 pb-24">
          <header className="flex items-end justify-between gap-6">
            <div>
              <h1 className="font-serif text-[32px] font-medium tracking-wide">
                Potential matches
              </h1>
              <p className="mt-1 font-mono text-[11px] text-chart-faint">
                generated {data.generatedAtLabel} · current calibrated evaluator only
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Link
                className="rounded-md border border-white/10 bg-white/[0.03] px-3 py-2 font-mono text-[11px] text-chart-muted transition hover:border-chart-teal/35 hover:text-chart-teal"
                href={data.includeOlder ? "/" : "/?older=1"}
              >
                {data.includeOlder
                  ? `hide roles older than ${data.maxAgeDays}d`
                  : "view older roles"}
              </Link>
              <button
              className="rounded-md border border-white/10 bg-white/[0.03] px-3 py-2 font-mono text-[11px] text-chart-muted transition hover:border-chart-teal/35 hover:text-chart-teal"
              onClick={() => setAuditOpen((value) => !value)}
              type="button"
            >
              {auditOpen ? "back to matches" : `skipped / all roles · ${data.counts.audit}`}
              </button>
            </div>
          </header>

          <SummaryBar data={data} />

          {data.loadError ? <DataLoadErrorBanner error={data.loadError} /> : null}

          {auditOpen ? (
            <AuditView rows={data.auditRows} />
          ) : (
            <div className="mt-8">
              <BandSection
                expandedId={expandedId}
                onExpand={setExpandedId}
                onOpenDetail={setDetailId}
                roles={data.bands.apply_now}
                type="apply_now"
              />
              <BandSection
                expandedId={expandedId}
                onExpand={setExpandedId}
                onOpenDetail={setDetailId}
                roles={data.bands.consider}
                type="consider"
              />
              <BandSection
                collapsed={!stretchOpen}
                expandedId={expandedId}
                onCollapseToggle={() => setStretchOpen((value) => !value)}
                onExpand={setExpandedId}
                onOpenDetail={setDetailId}
                roles={data.bands.stretch}
                type="stretch"
              />
              {!allCards.length ? <EmptyMatches /> : null}
            </div>
          )}
        </div>
      </section>
      {detailRole ? <RoleSlideOver onClose={() => setDetailId(null)} role={detailRole} /> : null}
    </main>
  );
}

function DataLoadErrorBanner({
  error
}: {
  error: NonNullable<PotentialMatchesData["loadError"]>;
}) {
  return (
    <div className="mt-6 rounded-lg border border-chart-warn/30 bg-chart-warn/10 px-4 py-4">
      <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-chart-warn">
        {error.title}
      </div>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-chart-muted">{error.message}</p>
    </div>
  );
}

function SideNav({ data, userEmail }: Props) {
  const navItems = [
    {
      label: "Potential Matches",
      count: data.counts.applyNow + data.counts.consider + data.counts.stretch,
      href: "/"
    },
    { label: "To Apply", count: "", href: "/to-apply" },
    { label: "Applied", count: "", href: "/applied" },
    { label: "Profile", count: "", href: "/profile" }
  ];
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-white/10 px-3.5 py-5">
      <div className="flex items-baseline gap-2 px-2.5 pb-6">
        <span className="font-serif text-[21px] font-medium italic tracking-wide">Sextant</span>
        <span className="relative -top-0.5 h-2 w-2 rotate-45 bg-chart-tealDeep" />
      </div>
      <nav className="flex flex-col gap-1">
        {navItems.map((item, index) => (
          item.href ? (
            <Link
              className={`flex items-center justify-between rounded-md px-2.5 py-2 text-[13.5px] transition hover:bg-white/[0.03] hover:text-chart-ink ${
                index === 0 ? "bg-chart-teal/10 text-chart-ink" : "text-chart-muted"
              }`}
              href={item.href}
              key={item.label}
            >
              <span className="font-medium">{item.label}</span>
              <span
                className={`font-mono text-[10px] uppercase tracking-[0.14em] ${
                  index === 0 ? "text-chart-teal" : "text-chart-faint"
                }`}
              >
                {item.count}
              </span>
            </Link>
          ) : (
            <div
              className="flex items-center justify-between rounded-md px-2.5 py-2 text-[13.5px] text-chart-muted"
              key={item.label}
            >
              <span className="font-medium">{item.label}</span>
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-chart-faint">
                {item.count}
              </span>
            </div>
          )
        ))}
      </nav>
      <div className="mt-auto border-t border-white/10 px-2.5 pt-4 font-mono text-[10.5px] leading-6 text-chart-faint">
        <div>last scan · {formatDateTime(data.scanReach.latestScanAt)}</div>
        <div>
          {formatNumber(data.scanReach.fetchedCount)} postings ·{" "}
          {formatNumber(data.scanReach.companyCount)} cos.
        </div>
        <div className="truncate text-white/30">owner · {userEmail}</div>
      </div>
    </aside>
  );
}

function SummaryBar({ data }: { data: PotentialMatchesData }) {
  return (
    <div className="mt-6 flex items-center justify-between gap-4 rounded-lg border border-white/10 bg-chart-panel px-4 py-3">
      <div className="flex flex-wrap items-center gap-5 text-[13px]">
        <SummaryDot count={data.counts.applyNow} label="apply" type="apply_now" />
        <SummaryDot count={data.counts.consider} label="consider" type="consider" />
        <SummaryDot count={data.counts.stretch} label="stretch" type="stretch" />
      </div>
      <div className="flex items-center gap-3 font-mono text-[10.5px] text-chart-faint">
        <span>
          scanned {formatNumber(data.scanReach.fetchedCount)} postings across{" "}
          {formatNumber(data.scanReach.companyCount)} companies
        </span>
        <span className="rounded border border-white/10 px-2 py-1">sort · fit ↓</span>
        <span className="rounded border border-white/10 px-2 py-1">filter · all</span>
      </div>
    </div>
  );
}

function SummaryDot({ count, label, type }: { count: number; label: string; type: MatchBand }) {
  return (
    <span className="flex items-center gap-2">
      <span className={`h-2 w-2 rounded-full ${bandMeta[type].accent}`} />
      <span className="font-mono text-chart-ink">{count}</span>
      <span className="text-chart-muted">{label}</span>
    </span>
  );
}

function BandSection({
  collapsed = false,
  expandedId,
  onCollapseToggle,
  onExpand,
  onOpenDetail,
  roles,
  type
}: {
  collapsed?: boolean;
  expandedId: number | null;
  onCollapseToggle?: () => void;
  onExpand: (id: number | null) => void;
  onOpenDetail: (id: number) => void;
  roles: PotentialMatch[];
  type: MatchBand;
}) {
  if (!roles.length && type !== "apply_now") {
    return null;
  }
  const meta = bandMeta[type];
  return (
    <section className="mb-8">
      <div className="mb-3 flex items-center gap-3">
        <span className={`h-[3px] w-4 ${meta.accent}`} />
        <h2 className={`font-mono text-[12px] uppercase tracking-[0.18em] ${meta.text}`}>
          {meta.label}
        </h2>
        <span className="font-mono text-[11px] text-chart-faint">{roles.length}</span>
        <span className="h-px flex-1 bg-white/10" />
        {type === "stretch" ? (
          <button
            className="font-mono text-[11px] text-chart-faint transition hover:text-chart-teal"
            onClick={onCollapseToggle}
            type="button"
          >
            {collapsed ? "show stretch" : "collapse stretch"}
          </button>
        ) : null}
      </div>
      {type === "stretch" && collapsed && roles.length ? (
        <button
          className="w-full rounded-lg border border-dashed border-chart-gold/35 bg-chart-gold/5 px-4 py-4 text-left text-sm text-chart-gold transition hover:border-chart-gold/55"
          onClick={onCollapseToggle}
          type="button"
        >
          {roles.length} stretch roles collapsed. Open when you want lower-confidence reach cards.
        </button>
      ) : (
        <div className="flex flex-col gap-2.5">
          {roles.map((role) => (
            <RoleCard
              expanded={expandedId === role.id}
              key={`${type}-${role.id}`}
              onExpand={() => onExpand(expandedId === role.id ? null : role.id)}
              onOpenDetail={() => onOpenDetail(role.id)}
              role={role}
            />
          ))}
        </div>
      )}
      {!roles.length && type === "apply_now" ? (
        <div className="rounded-lg border border-white/10 bg-chart-card px-4 py-5 text-sm text-chart-muted">
          No apply-now cards in the current calibrated view.
        </div>
      ) : null}
    </section>
  );
}

function RoleCard({
  expanded,
  onExpand,
  onOpenDetail,
  role
}: {
  expanded: boolean;
  onExpand: () => void;
  onOpenDetail: () => void;
  role: PotentialMatch;
}) {
  const meta = bandMeta[role.band];
  return (
    <article className="flex gap-4 rounded-[10px] border border-white/10 bg-chart-card px-4 py-4 transition hover:border-white/20">
      <FitBadge role={role} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <h3 className="text-[15px] font-semibold">{role.company}</h3>
          <span className="text-[14px] text-chart-muted">{role.title}</span>
        </div>
        <ChipRow role={role} />
        <p className="mt-3 line-clamp-2 max-w-2xl text-[13px] leading-5 text-chart-muted">
          {role.summary}
        </p>
        {expanded ? (
          <div className="mt-3 flex flex-col gap-2 rounded-lg border border-white/5 bg-chart-panel px-3.5 py-3">
            <EvidenceLine tone="good" text={role.topAlignment} />
            <EvidenceLine tone="gap" text={role.topGap} />
            <button
              className="self-start text-[12px] text-chart-teal transition hover:text-[#7fd0dc]"
              onClick={onOpenDetail}
              type="button"
            >
              Full evidence →
            </button>
          </div>
        ) : null}
      </div>
      <div className="flex w-32 shrink-0 flex-col items-end justify-between gap-3">
        <div className={`rounded-md border px-2 py-1 font-mono text-[10px] uppercase ${meta.border} ${meta.bg} ${meta.text}`}>
          {humanizeRecommendation(role.recommendation)}
        </div>
        <div className="flex flex-col items-end gap-2">
          <MarkToApplyButton jobPostingId={role.id} />
          <div className="flex gap-2 text-[11px]">
            <button className="rounded border border-white/10 px-2 py-1 text-chart-faint" disabled type="button">
              Dismiss
            </button>
            <button className="rounded border border-white/10 px-2 py-1 text-chart-faint" disabled type="button">
              Snooze
            </button>
          </div>
          {role.sourceUrl ? (
            <a
              className="font-mono text-[11px] text-chart-faint transition hover:text-chart-teal"
              href={role.sourceUrl}
              rel="noreferrer"
              target="_blank"
            >
              Source ↗
            </a>
          ) : null}
          <button
            className="font-mono text-[11px] text-chart-teal transition hover:text-[#7fd0dc]"
            onClick={onExpand}
            type="button"
          >
            {expanded ? "less ▴" : "details ▾"}
          </button>
        </div>
      </div>
    </article>
  );
}

function FitBadge({ role }: { role: PotentialMatch }) {
  const meta = bandMeta[role.band];
  return (
    <div
      className={`flex h-[54px] w-[54px] shrink-0 flex-col items-center justify-center rounded-lg border ${meta.border} ${meta.bg}`}
    >
      <span className={`font-mono text-[20px] font-medium ${meta.text}`}>{role.fitScore}</span>
      <span className="font-mono text-[8px] uppercase tracking-[0.14em] text-chart-faint">fit</span>
    </div>
  );
}

function ChipRow({ role }: { role: PotentialMatch }) {
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      <Chip>{role.locationsLabel}</Chip>
      <Chip tone={role.tier === 1 ? "teal" : "muted"}>Tier {role.tier}</Chip>
      <Chip tone={pctTone(role.feasibilityPct)}>feasibility {role.feasibilityPct}%</Chip>
      <Chip tone={pctTone(role.confidencePct)}>confidence {role.confidencePct}%</Chip>
      <Chip tone={roleIsOlderThanPolicy(role) ? "warn" : "green"}>{freshnessLabel(role)}</Chip>
      <LevelChip role={role} />
    </div>
  );
}

function LevelChip({ role }: { role: PotentialMatch }) {
  if (role.levelConfidence < 50 || role.estimatedLevel === "unknown") {
    return <Chip>est. L? · low confidence</Chip>;
  }
  if (role.estimatedLevel === "L6" || role.estimatedLevel === "L7+") {
    return <Chip tone="gold">est. {role.estimatedLevel} ▲ above band</Chip>;
  }
  if (role.estimatedLevel === "L3") {
    return <Chip>est. L3 ▼ below band</Chip>;
  }
  return <Chip tone="teal">est. {role.estimatedLevel} · in band</Chip>;
}

function Chip({
  children,
  tone = "muted"
}: {
  children: ReactNode;
  tone?: "green" | "gold" | "muted" | "teal" | "warn";
}) {
  const styles = {
    green: "border-chart-green/25 text-chart-green",
    gold: "border-chart-gold/25 text-chart-gold",
    muted: "border-white/10 text-chart-muted",
    teal: "border-chart-teal/25 text-chart-teal",
    warn: "border-chart-warn/25 text-chart-warn"
  };
  return (
    <span className={`rounded border px-2 py-0.5 font-mono text-[10.5px] ${styles[tone]}`}>
      {children}
    </span>
  );
}

function EvidenceLine({ text, tone }: { text: string; tone: "gap" | "good" }) {
  return (
    <div className="flex gap-2 text-[12.5px] leading-5">
      <span className={tone === "good" ? "text-chart-green" : "text-chart-gold"}>
        {tone === "good" ? "✓" : "△"}
      </span>
      <span className={tone === "good" ? "text-[#cfd8da]" : "text-chart-muted"}>{text}</span>
    </div>
  );
}

function AuditView({ rows }: { rows: AuditRow[] }) {
  return (
    <section className="mt-8 overflow-hidden rounded-[10px] border border-white/10 bg-chart-panel">
      <div className="flex items-baseline justify-between gap-3 px-4 py-3">
        <div className="flex items-baseline gap-3">
          <h2 className="font-mono text-[12px] uppercase tracking-[0.18em] text-chart-muted">
            Skipped / all evaluated
          </h2>
          <span className="font-mono text-[11px] text-chart-faint">
            {rows.length} rows with stored reasons
          </span>
        </div>
        <span className="font-mono text-[10.5px] text-chart-faint">
          gate skips + current calibrated evaluations
        </span>
      </div>
      <div className="grid grid-cols-[60px_160px_1fr_1.15fr] gap-3 border-t border-white/10 px-4 py-2 font-mono text-[9.5px] uppercase tracking-[0.12em] text-chart-faint">
        <span>Fit</span>
        <span>Company</span>
        <span>Role</span>
        <span>Reason</span>
      </div>
      <div>
        {rows.map((row) => (
          <div
            className="grid grid-cols-[60px_160px_1fr_1.15fr] gap-3 border-t border-white/5 px-4 py-2.5 text-[12.5px]"
            key={row.id}
          >
            <span className="font-mono text-chart-faint">{row.fitScore ?? "gate"}</span>
            <span className="truncate font-medium text-chart-ink">{row.company}</span>
            <span className="truncate text-chart-muted">{row.title}</span>
            <span className="text-chart-faint">{row.reason}</span>
          </div>
        ))}
        {!rows.length ? (
          <div className="border-t border-white/5 px-4 py-8 text-center text-sm text-chart-muted">
            No audit rows yet. Once the scan cache lands in Postgres, gate skips and evaluated
            skip/blocked roles will appear here.
          </div>
        ) : null}
      </div>
    </section>
  );
}

function RoleSlideOver({ onClose, role }: { onClose: () => void; role: PotentialMatch }) {
  const meta = bandMeta[role.band];
  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-[rgba(4,10,14,.62)]" onClick={onClose}>
      <aside
        className="h-full w-[490px] overflow-y-auto border-l border-white/10 bg-chart-panel px-7 py-7 shadow-[-24px_0_60px_rgba(0,0,0,.45)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className={`font-mono text-[11px] uppercase tracking-[0.18em] ${meta.text}`}>
              {meta.label}
            </div>
            <h2 className="mt-2 font-serif text-[23px] font-medium leading-7">
              {role.company} — {role.title}
            </h2>
          </div>
          <button
            className="rounded border border-white/10 px-2 py-1 font-mono text-[12px] text-chart-faint transition hover:border-white/25 hover:text-chart-ink"
            onClick={onClose}
            type="button"
          >
            ✕
          </button>
        </div>
        <div className="mt-4 flex items-start gap-4">
          <div className="min-w-0 flex-1">
            <ChipRow role={role} />
            <p className="mt-4 text-[13px] leading-6 text-chart-muted">{role.summary}</p>
            <p className="mt-3 text-[12px] leading-5 text-chart-faint">
              Feasibility: {role.feasibilityState} · {role.feasibilityReason}
            </p>
            <p className="mt-2 text-[12px] leading-5 text-chart-faint">
              Estimated level: {role.estimatedLevel} · confidence {role.levelConfidence}% ·{" "}
              {role.levelRationale}
            </p>
          </div>
          <FitBadge role={role} />
        </div>

        <EvidenceSection alignments={role.alignments} />
        <GapSection gaps={role.gaps} hardBlockers={role.hardBlockers} />

        <div className="mt-8 flex items-center gap-3 border-t border-white/10 pt-5">
          <MarkToApplyButton jobPostingId={role.id} />
          <button className="rounded border border-white/10 px-3 py-2 text-[12px] text-chart-faint" disabled type="button">
            Dismiss
          </button>
          <button className="rounded border border-white/10 px-3 py-2 text-[12px] text-chart-faint" disabled type="button">
            Snooze
          </button>
          {role.sourceUrl ? (
            <a
              className="ml-auto font-mono text-[11px] text-chart-teal transition hover:text-[#7fd0dc]"
              href={role.sourceUrl}
              rel="noreferrer"
              target="_blank"
            >
              Open source ↗
            </a>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function EvidenceSection({ alignments }: { alignments: AlignmentEvidence[] }) {
  return (
    <section className="mt-7">
      <div className="flex items-center gap-3">
        <h3 className="font-mono text-[11px] uppercase tracking-[0.18em] text-chart-green">
          Why it fits
        </h3>
        <span className="h-px flex-1 bg-white/10" />
      </div>
      <p className="mt-1 font-mono text-[10.5px] text-chart-faint">
        JD requirement → your evidence
      </p>
      <div className="mt-3 flex flex-col gap-3">
        {alignments.map((alignment, index) => (
          <div className="flex gap-3 rounded-lg border border-white/5 bg-chart-card p-3" key={index}>
            <StrengthPip strength={alignment.evidenceStrength} />
            <div>
              <div className="text-[12px] leading-5 text-chart-muted">
                {alignment.jobRequirement}
              </div>
              <div className="mt-1 flex gap-2 text-[12.5px] leading-5 text-chart-ink">
                <span className="text-chart-teal">→</span>
                <span>{alignment.candidateEvidence}</span>
              </div>
              <div className="mt-2 font-mono text-[9.5px] uppercase tracking-[0.12em] text-chart-faint">
                {alignment.evidenceStrength}
              </div>
            </div>
          </div>
        ))}
        {!alignments.length ? (
          <div className="rounded-lg border border-white/5 bg-chart-card p-3 text-sm text-chart-muted">
            No alignment evidence recorded.
          </div>
        ) : null}
      </div>
    </section>
  );
}

function GapSection({ gaps, hardBlockers }: { gaps: GapEvidence[]; hardBlockers: string[] }) {
  return (
    <section className="mt-7">
      <div className="flex items-center gap-3">
        <h3 className="font-mono text-[11px] uppercase tracking-[0.18em] text-chart-gold">
          Gaps & mitigations
        </h3>
        <span className="h-px flex-1 bg-white/10" />
      </div>
      <div className="mt-3 flex flex-col gap-3">
        {hardBlockers.map((blocker, index) => (
          <div className="rounded-lg border border-chart-warn/25 p-3" key={`blocker-${index}`}>
            <div className="text-[12.5px] leading-5 text-chart-warn">Hard blocker: {blocker}</div>
          </div>
        ))}
        {gaps.map((gap, index) => (
          <div className="rounded-lg border border-chart-gold/25 p-3" key={index}>
            <div className="flex gap-2 text-[12.5px] leading-5 text-chart-ink">
              <span className="text-chart-gold">△</span>
              <span>{gap.gap}</span>
            </div>
            <div className="mt-2 text-[12px] leading-5 text-chart-muted">{gap.mitigation}</div>
            <div className="mt-2 font-mono text-[9.5px] uppercase tracking-[0.12em] text-chart-faint">
              severity · {gap.severity}
            </div>
          </div>
        ))}
        {!gaps.length && !hardBlockers.length ? (
          <div className="rounded-lg border border-white/5 bg-chart-card p-3 text-sm text-chart-muted">
            No gaps recorded.
          </div>
        ) : null}
      </div>
    </section>
  );
}

function StrengthPip({ strength }: { strength: string }) {
  const normalized = strength.toLowerCase();
  const color =
    normalized === "strong"
      ? "bg-chart-green"
      : normalized === "weak"
        ? "bg-chart-warn"
        : "bg-chart-gold";
  return <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${color}`} />;
}

function MarkToApplyButton({ jobPostingId }: { jobPostingId: number }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  return (
    <div className="flex flex-col items-end gap-1">
      <button
        className="rounded-md bg-chart-rust px-3 py-2 text-[12px] font-semibold text-white/95 transition hover:bg-[#b85f45] disabled:opacity-50"
        disabled={pending}
        onClick={() => {
          startTransition(async () => {
            const result = await markToApply(jobPostingId);
            setMessage(result.message);
            if (result.ok) {
              router.refresh();
            }
          });
        }}
        type="button"
      >
        {pending ? "Adding…" : "Mark to apply"}
      </button>
      {message ? <span className="max-w-36 text-right text-[10px] text-chart-faint">{message}</span> : null}
    </div>
  );
}

function EmptyMatches() {
  return (
    <div className="mt-14 text-center">
      <div className="font-serif text-[22px] italic text-chart-muted">No calibrated matches yet.</div>
      <p className="mt-2 text-sm text-chart-faint">
        After the evaluator-v3 migration and the next scan, current hybrid Claude v3 evaluations will
        appear here.
      </p>
    </div>
  );
}

function pctTone(value: number): "green" | "gold" | "warn" {
  if (value >= 70) {
    return "green";
  }
  if (value >= 40) {
    return "gold";
  }
  return "warn";
}

function formatNumber(value: number | null) {
  return typeof value === "number" ? value.toLocaleString("en-US") : "—";
}
