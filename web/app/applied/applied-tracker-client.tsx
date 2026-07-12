"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useMemo, useState, useTransition } from "react";
import {
  APPLICATION_STAGES,
  applicationStageLabel,
  type AppliedTrackerData,
  type ApplicationStage,
  type TrackedApplication
} from "@/lib/data/applications";
import { ManualIntakeCards } from "@/app/manual-intake-cards";
import {
  updateApplicationDetails,
  updateApplicationStage
} from "./actions";

type Props = {
  data: AppliedTrackerData;
  userEmail: string;
};

const stageStyles: Record<ApplicationStage, string> = {
  preparing: "border-chart-muted/35 bg-chart-muted/10 text-chart-muted",
  applied: "border-chart-tealDeep/60 bg-chart-tealDeep/15 text-chart-teal",
  recruiter_screen: "border-chart-teal/40 bg-chart-teal/10 text-chart-teal",
  interviewing: "border-chart-gold/40 bg-chart-gold/10 text-chart-gold",
  final_round: "border-chart-rust/45 bg-chart-rust/10 text-chart-rust",
  offer: "border-chart-green/45 bg-chart-green/10 text-chart-green",
  rejected: "border-white/10 bg-white/[0.02] text-chart-faint",
  withdrawn: "border-white/10 bg-white/[0.02] text-chart-faint"
};

const funnelColors: Record<ApplicationStage, string> = {
  preparing: "bg-chart-muted",
  applied: "bg-chart-tealDeep",
  recruiter_screen: "bg-chart-teal",
  interviewing: "bg-chart-gold",
  final_round: "bg-chart-rust",
  offer: "bg-chart-green",
  rejected: "bg-chart-faint",
  withdrawn: "bg-chart-faint"
};

export function AppliedTrackerClient({ data, userEmail }: Props) {
  const [drawerId, setDrawerId] = useState<number | null>(null);
  const drawerApplication = useMemo(
    () => data.applications.find((application) => application.id === drawerId) ?? null,
    [data.applications, drawerId]
  );

  return (
    <main className="flex min-h-screen bg-chart-page text-chart-ink">
      <AppliedSideNav
        activeCount={data.stats.active + data.stats.inInterview + data.stats.offers}
        userEmail={userEmail}
      />
      <section className="relative min-w-0 flex-1 overflow-hidden">
        <div className="pointer-events-none fixed bottom-0 left-56 right-0 top-0 bg-[linear-gradient(rgba(87,182,196,.028)_1px,transparent_1px),linear-gradient(90deg,rgba(87,182,196,.028)_1px,transparent_1px)] bg-[length:56px_56px]" />
        <div className="relative mx-auto max-w-[1380px] px-8 py-8 pb-24">
          <header className="flex items-end justify-between gap-8">
            <div>
              <h1 className="font-serif text-[32px] font-medium tracking-wide">Applied</h1>
              <p className="mt-1 font-mono text-[11px] text-chart-faint">
                pipeline · click a row for history + original evaluation
              </p>
            </div>
            <StatStrip data={data} />
          </header>

          {data.loadError ? <LoadError error={data.loadError} /> : null}
          <ManualIntakeCards entries={data.manualEntries} />
          {data.applications.length ? (
            <>
              <Funnel data={data} />
              <ApplicationTable applications={data.applications} onOpen={setDrawerId} />
            </>
          ) : (
            <EmptyApplied hasError={Boolean(data.loadError)} />
          )}
        </div>
      </section>
      {drawerApplication ? (
        <ApplicationDrawer
          application={drawerApplication}
          key={drawerApplication.id}
          onClose={() => setDrawerId(null)}
        />
      ) : null}
    </main>
  );
}

function AppliedSideNav({ activeCount, userEmail }: { activeCount: number; userEmail: string }) {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-white/10 px-3.5 py-5">
      <div className="flex items-baseline gap-2 px-2.5 pb-6">
        <span className="font-serif text-[21px] font-medium italic tracking-wide">Sextant</span>
        <span className="relative -top-0.5 h-2 w-2 rotate-45 bg-chart-tealDeep" />
      </div>
      <nav className="flex flex-col gap-1">
        <NavItem href="/" label="Potential Matches" />
        <NavItem href="/add-role" label="Add a role" />
        <NavItem href="/to-apply" label="To Apply" />
        <NavItem active href="/applied" label="Applied" value={String(activeCount)} />
        <NavItem href="/profile" label="Profile" />
      </nav>
      <div className="mt-auto border-t border-white/10 px-2.5 pt-4 font-mono text-[10.5px] leading-6 text-chart-faint">
        <div>internal working tracker</div>
        <div>immutable stage history</div>
        <div className="truncate text-white/30">owner · {userEmail}</div>
      </div>
    </aside>
  );
}

function NavItem({
  active = false,
  href,
  label,
  value = ""
}: {
  active?: boolean;
  href?: string;
  label: string;
  value?: string;
}) {
  const content = (
    <>
      <span className="font-medium">{label}</span>
      <span
        className={`font-mono text-[10px] uppercase tracking-[0.14em] ${
          active ? "text-chart-teal" : "text-chart-faint"
        }`}
      >
        {value}
      </span>
    </>
  );
  const classes = `flex items-center justify-between rounded-md px-2.5 py-2 text-[13.5px] ${
    active ? "bg-chart-teal/10 text-chart-ink" : "text-chart-muted"
  } ${href ? "transition hover:bg-white/[0.03] hover:text-chart-ink" : ""}`;
  return href ? (
    <Link className={classes} href={href}>
      {content}
    </Link>
  ) : (
    <div className={classes}>{content}</div>
  );
}

function StatStrip({ data }: { data: AppliedTrackerData }) {
  const stats = [
    ["active", data.stats.active],
    ["in interview", data.stats.inInterview],
    ["offers", data.stats.offers],
    ["closed", data.stats.closed]
  ] as const;
  return (
    <div className="flex font-mono">
      {stats.map(([label, count]) => (
        <div className="border-l border-white/10 px-4 text-right" key={label}>
          <div className="text-[17px] text-chart-ink">{count}</div>
          <div className="mt-0.5 text-[9.5px] uppercase tracking-[0.08em] text-chart-faint">
            {label}
          </div>
        </div>
      ))}
    </div>
  );
}

function Funnel({ data }: { data: AppliedTrackerData }) {
  const maxCount = Math.max(1, ...data.funnel.map((item) => item.count));
  return (
    <section className="mt-7 flex gap-6 overflow-x-auto rounded-lg border border-white/10 bg-chart-panel px-5 py-4">
      {data.funnel.map((item) => (
        <div className="min-w-[92px] flex-1" key={item.stage}>
          <div
            className={`font-mono text-[17px] ${
              item.count ? "text-chart-ink" : "text-white/20"
            }`}
          >
            {item.count}
          </div>
          <div className="mt-0.5 whitespace-nowrap text-[9.5px] uppercase tracking-[0.1em] text-chart-faint">
            {applicationStageLabel(item.stage)}
          </div>
          <div className="mt-2 h-[3px] rounded-full bg-white/5">
            <div
              className={`h-[3px] rounded-full ${funnelColors[item.stage]}`}
              style={{ width: `${Math.max(item.count ? 12 : 0, (item.count / maxCount) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </section>
  );
}

function ApplicationTable({
  applications,
  onOpen
}: {
  applications: TrackedApplication[];
  onOpen: (id: number) => void;
}) {
  return (
    <div className="mt-5 overflow-x-auto rounded-[10px] border border-white/10 bg-chart-panel">
      <table className="min-w-[1240px] table-fixed text-left">
        <thead>
          <tr className="font-mono text-[9.5px] uppercase tracking-[0.11em] text-chart-faint">
            <TableHead width="w-[120px]">Company</TableHead>
            <TableHead width="w-[210px]">Role</TableHead>
            <TableHead width="w-[130px]">Location</TableHead>
            <TableHead width="w-[140px]">Stage</TableHead>
            <TableHead width="w-[105px]">Applied on</TableHead>
            <TableHead width="w-[190px]">Next action</TableHead>
            <TableHead width="w-[90px]">Due</TableHead>
            <TableHead width="w-[130px]">Contact</TableHead>
            <TableHead width="w-[100px]">Salary</TableHead>
            <TableHead width="w-[180px]">Notes</TableHead>
          </tr>
        </thead>
        <tbody>
          {applications.map((application) => {
            const closed = ["rejected", "withdrawn"].includes(application.stage);
            return (
              <tr
                className={`cursor-pointer border-t border-white/5 text-[12.5px] transition hover:bg-white/[0.025] focus:bg-white/[0.035] focus:outline-none ${
                  closed ? "text-chart-faint" : "text-chart-ink"
                }`}
                key={application.id}
                onClick={() => onOpen(application.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onOpen(application.id);
                  }
                }}
                tabIndex={0}
              >
                <TableCell className="font-semibold">{application.company}</TableCell>
                <TableCell className="truncate text-[#cfd8da]">{application.role}</TableCell>
                <TableCell className="line-clamp-2 text-[11.5px] text-chart-faint">
                  {application.location}
                </TableCell>
                <TableCell>
                  <StagePill stage={application.stage} />
                </TableCell>
                <TableCell className="font-mono text-[10.5px] text-chart-faint">
                  {formatAppliedOn(application)}
                </TableCell>
                <TableCell className="truncate font-medium">
                  {application.nextAction || "—"}
                </TableCell>
                <TableCell className={`font-mono text-[10.5px] ${dueTone(application.due)}`}>
                  {formatDue(application.due)}
                </TableCell>
                <TableCell className="truncate text-[11.5px] text-chart-muted">
                  {application.contact || "—"}
                </TableCell>
                <TableCell className="truncate font-mono text-[10.5px] text-chart-muted">
                  {application.salary || "—"}
                </TableCell>
                <TableCell className="truncate text-[11.5px] text-chart-faint">
                  {application.notes || "—"}
                </TableCell>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TableHead({ children, width }: { children: React.ReactNode; width: string }) {
  return <th className={`${width} px-4 py-3 font-normal`}>{children}</th>;
}

function TableCell({
  children,
  className = ""
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <td className={`px-4 py-3 ${className}`}>{children}</td>;
}

function StagePill({ stage }: { stage: ApplicationStage }) {
  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-md border px-2 py-1 font-mono text-[9.5px] uppercase tracking-[0.04em] ${stageStyles[stage]}`}
    >
      {applicationStageLabel(stage)}
    </span>
  );
}

function ApplicationDrawer({
  application,
  onClose
}: {
  application: TrackedApplication;
  onClose: () => void;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState("");

  function changeStage(stage: ApplicationStage) {
    setMessage("");
    startTransition(async () => {
      const result = await updateApplicationStage(application.id, stage);
      setMessage(result.message);
      if (result.ok) {
        router.refresh();
      }
    });
  }

  function saveDetails(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setMessage("");
    startTransition(async () => {
      const result = await updateApplicationDetails(application.id, {
        nextAction: String(form.get("nextAction") ?? ""),
        due: String(form.get("due") ?? ""),
        contact: String(form.get("contact") ?? ""),
        salary: String(form.get("salary") ?? ""),
        notes: String(form.get("notes") ?? "")
      });
      setMessage(result.message);
      if (result.ok) {
        router.refresh();
      }
    });
  }

  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-30 flex justify-end bg-[rgba(4,10,14,.62)]"
      onClick={onClose}
      role="dialog"
    >
      <aside
        className="h-full w-full max-w-[500px] overflow-y-auto border-l border-white/10 bg-chart-panel px-7 py-7 shadow-[-24px_0_60px_rgba(0,0,0,.45)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <StagePill stage={application.stage} />
          <button
            aria-label="Close application details"
            className="rounded border border-white/10 px-2 py-1 font-mono text-[12px] text-chart-faint transition hover:border-white/25 hover:text-chart-ink"
            onClick={onClose}
            type="button"
          >
            ✕
          </button>
        </div>
        <h2 className="mt-3 font-serif text-[23px] font-medium leading-7">
          {application.company} — {application.role}
        </h2>
        {application.url ? (
          <a
            className="mt-2 inline-flex font-mono text-[10.5px] text-chart-teal transition hover:text-[#7fd0dc]"
            href={application.url}
            rel="noreferrer"
            target="_blank"
          >
            Open source ↗
          </a>
        ) : null}
        <div className="mt-4 grid grid-cols-2 gap-x-5 gap-y-3 text-[12px]">
          <DrawerFact label="Applied">{formatAppliedOn(application)}</DrawerFact>
          <DrawerFact label="Contact">{application.contact || "—"}</DrawerFact>
          <DrawerFact label="Next action">{application.nextAction || "—"}</DrawerFact>
          <DrawerFact label="Due">{formatDue(application.due)}</DrawerFact>
        </div>

        <section className="mt-7 border-t border-white/10 pt-5">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-chart-muted">
              Update pipeline
            </h3>
            <span className="font-mono text-[9.5px] text-chart-faint">
              every stage change is logged
            </span>
          </div>
          <label className="mt-3 block font-mono text-[9.5px] uppercase tracking-[0.1em] text-chart-faint">
            Stage
            <select
              className="mt-1.5 w-full rounded-md border border-white/10 bg-chart-card px-3 py-2 text-[12.5px] normal-case text-chart-ink outline-none focus:border-chart-teal/45"
              disabled={pending}
              onChange={(event) => changeStage(event.target.value as ApplicationStage)}
              value={application.stage}
            >
              {APPLICATION_STAGES.map((stage) => (
                <option key={stage} value={stage}>
                  {applicationStageLabel(stage)}
                </option>
              ))}
            </select>
          </label>
          <form className="mt-4 grid grid-cols-2 gap-3" onSubmit={saveDetails}>
            <TextField defaultValue={application.nextAction} label="Next action" name="nextAction" />
            <TextField defaultValue={application.due ?? ""} label="Due" name="due" type="date" />
            <TextField defaultValue={application.contact} label="Contact" name="contact" />
            <TextField defaultValue={application.salary} label="Salary" name="salary" />
            <label className="col-span-2 font-mono text-[9.5px] uppercase tracking-[0.1em] text-chart-faint">
              Notes
              <textarea
                className="mt-1.5 min-h-24 w-full resize-y rounded-md border border-white/10 bg-chart-card px-3 py-2 font-sans text-[12.5px] normal-case leading-5 text-chart-ink outline-none focus:border-chart-teal/45"
                defaultValue={application.notes}
                maxLength={4000}
                name="notes"
              />
            </label>
            <div className="col-span-2 flex items-center gap-3">
              <button
                className="rounded-md bg-chart-tealDeep px-3 py-2 text-[12px] font-semibold text-chart-ink transition hover:bg-chart-tealDeep/80 disabled:opacity-50"
                disabled={pending}
                type="submit"
              >
                {pending ? "Saving…" : "Save working details"}
              </button>
              {message ? <span className="text-[11.5px] text-chart-muted">{message}</span> : null}
            </div>
          </form>
        </section>

        <StageHistory application={application} />
        <EvaluationSnapshot application={application} />
      </aside>
    </div>
  );
}

function DrawerFact({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <div>
      <div className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-chart-faint">
        {label}
      </div>
      <div className="mt-1 text-chart-ink">{children}</div>
    </div>
  );
}

function TextField({
  defaultValue,
  label,
  name,
  type = "text"
}: {
  defaultValue: string;
  label: string;
  name: string;
  type?: "date" | "text";
}) {
  return (
    <label className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-chart-faint">
      {label}
      <input
        className="mt-1.5 w-full rounded-md border border-white/10 bg-chart-card px-3 py-2 font-sans text-[12.5px] normal-case text-chart-ink outline-none focus:border-chart-teal/45"
        defaultValue={defaultValue}
        maxLength={500}
        name={name}
        type={type}
      />
    </label>
  );
}

function StageHistory({ application }: { application: TrackedApplication }) {
  return (
    <section className="mt-8">
      <div className="flex items-center gap-3">
        <h3 className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-chart-muted">
          Stage history
        </h3>
        <span className="h-px flex-1 bg-white/10" />
        <span className="font-mono text-[9.5px] text-chart-faint">immutable</span>
      </div>
      <div className="ml-1 mt-4 flex flex-col gap-4 border-l border-white/10 pl-5">
        {application.events.map((event) => (
          <div className="relative" key={event.id}>
            <span className="absolute -left-[24px] top-1.5 h-[7px] w-[7px] rounded-full bg-chart-tealDeep" />
            <div className="font-mono text-[9.5px] text-chart-faint">
              {formatDateTime(event.occurredAt)} · {event.actor}
            </div>
            <div className="mt-1 text-[12.5px] leading-5 text-[#cfd8da]">
              {event.previousStage
                ? `${applicationStageLabel(event.previousStage)} → ${applicationStageLabel(event.newStage)}`
                : `created at ${applicationStageLabel(event.newStage)}`}
            </div>
          </div>
        ))}
        {!application.events.length ? (
          <div className="text-[12px] text-chart-faint">No stage events recorded.</div>
        ) : null}
      </div>
    </section>
  );
}

function EvaluationSnapshot({ application }: { application: TrackedApplication }) {
  const snapshot = application.snapshot;
  return (
    <section className="mt-8">
      <div className="flex items-center gap-3">
        <h3 className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-chart-muted">
          Original evaluation
        </h3>
        <span className="h-px flex-1 bg-white/10" />
        <span className="font-mono text-[9.5px] text-chart-faint">
          {formatDateTime(snapshot.capturedAt)}
        </span>
      </div>
      <div className="mt-4 rounded-lg border border-white/5 bg-chart-card px-4 py-4">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[20px] text-chart-teal">{snapshot.fitScore}</span>
          <span className="text-[12px] text-chart-faint">
            fit at evaluation · {snapshot.recommendation.replaceAll("_", " ")}
          </span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 font-mono text-[9.5px] text-chart-faint">
          <span className="break-all">scored by {snapshot.modelVersion}</span>
          {snapshot.isEarlierEvaluator ? (
            <span className="rounded border border-chart-gold/30 bg-chart-gold/10 px-1.5 py-0.5 uppercase tracking-[0.08em] text-chart-gold">
              earlier evaluator
            </span>
          ) : null}
        </div>
        <div className="mt-4 flex flex-col gap-3">
          {snapshot.alignments.map((alignment, index) => (
            <div className="flex gap-2 text-[12.5px] leading-5" key={`alignment-${index}`}>
              <span className="text-chart-green">✓</span>
              <span className="text-[#cfd8da]">
                {alignment.jobRequirement} → {alignment.candidateEvidence}
                <span className="ml-2 font-mono text-[9px] uppercase text-chart-faint">
                  {alignment.evidenceStrength}
                </span>
              </span>
            </div>
          ))}
          {snapshot.gaps.map((gap, index) => (
            <div className="flex gap-2 text-[12.5px] leading-5" key={`gap-${index}`}>
              <span className="text-chart-gold">△</span>
              <span className="text-chart-muted">
                {gap.gap} {gap.mitigation ? `Mitigation: ${gap.mitigation}` : ""}
              </span>
            </div>
          ))}
          {!snapshot.alignments.length && !snapshot.gaps.length ? (
            <div className="text-[12px] text-chart-faint">No evidence rows in the snapshot.</div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function LoadError({ error }: { error: NonNullable<AppliedTrackerData["loadError"]> }) {
  return (
    <div className="mt-6 rounded-lg border border-chart-warn/30 bg-chart-warn/10 px-4 py-4">
      <div className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-chart-warn">
        {error.title}
      </div>
      <p className="mt-2 text-sm leading-6 text-chart-muted">{error.message}</p>
    </div>
  );
}

function EmptyApplied({ hasError }: { hasError: boolean }) {
  return (
    <div className="mt-20 text-center">
      <div className="font-serif text-[22px] italic text-chart-muted">
        {hasError ? "The tracker is not ready yet." : "Nothing applied yet."}
      </div>
      <p className="mt-2 text-sm text-chart-faint">
        {hasError
          ? "Apply the A3 migration, then reload this page."
          : "Applications appear here only after Mark applied creates the calibrated snapshot."}
      </p>
    </div>
  );
}

function formatAppliedOn(application: TrackedApplication) {
  return `${formatShortDate(application.appliedAt)} · W${String(application.appliedCalendarWeek).padStart(2, "0")}`;
}

function formatShortDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short" }).format(date);
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value || "unknown";
  }
  return new Intl.DateTimeFormat("en", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    year: "numeric"
  }).format(date);
}

function formatDue(value: string | null) {
  if (!value) {
    return "—";
  }
  const date = new Date(`${value}T12:00:00Z`);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short" }).format(date);
}

function dueTone(value: string | null) {
  if (!value) {
    return "text-chart-faint";
  }
  const due = new Date(`${value}T23:59:59`);
  const now = new Date();
  if (due.getTime() < now.getTime()) {
    return "text-chart-warn";
  }
  if (due.getTime() - now.getTime() <= 3 * 24 * 60 * 60 * 1000) {
    return "text-chart-gold";
  }
  return "text-chart-muted";
}
