"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { removeManualIntake } from "@/app/actions/manual-intake";
import type { ManualIntakeEntry } from "@/lib/data/manual-intake";

export function ManualIntakeCards({ entries }: { entries: ManualIntakeEntry[] }) {
  const router = useRouter();
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  if (!entries.length) return null;

  function remove(entry: ManualIntakeEntry) {
    if (!window.confirm(`Remove ${entry.company} · ${entry.title}?`)) return;
    setPendingId(entry.id);
    startTransition(async () => {
      const result = await removeManualIntake(entry.id);
      setFeedback(result.message);
      setPendingId(null);
      if (result.ok) router.refresh();
    });
  }

  return (
    <section className="mt-7">
      <div className="mb-3 font-mono text-[10px] uppercase tracking-[0.16em] text-chart-gold">
        Manual intake · pending / unscored
      </div>
      {feedback ? (
        <div
          aria-live="polite"
          className="mb-3 rounded border border-chart-teal/25 bg-chart-teal/10 px-3 py-2 text-[12px] text-chart-teal"
        >
          {feedback}
        </div>
      ) : null}
      <div className="flex flex-col gap-2">
        {entries.map((entry) => {
          const manageable = entry.status !== "processing";
          return (
            <article
              className="rounded-lg border border-chart-gold/25 bg-chart-gold/5 px-4 py-3"
              key={entry.id}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <span className="font-semibold">{entry.company}</span>
                  <span className="ml-2 text-chart-muted">{entry.title}</span>
                  <div className="mt-1 font-mono text-[10px] text-chart-faint">
                    {entry.location}
                  </div>
                  <p className="mt-2 text-[12px] font-medium text-chart-gold">
                    {statusMessage(entry.status)}
                  </p>
                  {entry.status === "queued" ? (
                    <p className="mt-1 font-mono text-[10px] text-chart-faint">
                      Next automated scan: daily at 06:00 UTC (about 07:00–08:00 in
                      Europe).
                    </p>
                  ) : null}
                  {entry.note ? (
                    <p className="mt-2 text-[12px] text-chart-muted">{entry.note}</p>
                  ) : null}
                  {entry.error ? (
                    <p className="mt-2 text-[11px] text-chart-warn">{entry.error}</p>
                  ) : null}
                </div>
                <div className="shrink-0 text-right">
                  <div className="font-mono text-[9px] uppercase text-chart-gold">
                    {entry.status === "manual_unscored"
                      ? "not evaluated"
                      : entry.status.replaceAll("_", " ")}
                  </div>
                  {entry.proposeWatchlist ? (
                    <div className="mt-1 font-mono text-[9px] text-chart-teal">
                      watchlist proposed
                    </div>
                  ) : null}
                  {entry.url ? (
                    <a
                      className="mt-2 block text-[11px] text-chart-teal"
                      href={entry.url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Source ↗
                    </a>
                  ) : null}
                  {manageable ? (
                    <div className="mt-3 flex items-center justify-end gap-2">
                      <Link
                        className="rounded border border-chart-teal/25 px-2.5 py-1.5 text-[10px] text-chart-teal transition hover:border-chart-teal/50"
                        href={redoHref(entry)}
                      >
                        Redo via URL
                      </Link>
                      <button
                        className="rounded border border-white/10 px-2.5 py-1.5 text-[10px] text-chart-muted transition hover:border-chart-warn/40 hover:text-chart-warn disabled:opacity-50"
                        disabled={pending}
                        onClick={() => remove(entry)}
                        type="button"
                      >
                        {pendingId === entry.id ? "Removing…" : "Remove"}
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function statusMessage(status: ManualIntakeEntry["status"]) {
  switch (status) {
    case "queued":
      return "Will be evaluated on the next scan.";
    case "processing":
      return "Evaluation is running now.";
    case "needs_text":
      return "The job page could not be read. Remove it or redo it with a corrected URL.";
    case "failed":
      return "Evaluation failed. Remove it or redo it via the URL path.";
    case "manual_unscored":
      return "Saved without evaluation.";
    default:
      return "Manual intake status is unavailable.";
  }
}

function redoHref(entry: ManualIntakeEntry) {
  const params = new URLSearchParams({
    mode: "url",
    replaceId: String(entry.id),
    company: entry.company,
    title: entry.title,
    location: entry.location === "Location not listed" ? "" : entry.location,
    url: entry.url ?? "",
    destination: entry.destination,
    proposeWatchlist: entry.proposeWatchlist ? "1" : "0"
  });
  return `/add-role?${params.toString()}`;
}
