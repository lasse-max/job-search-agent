import type { ManualIntakeEntry } from "@/lib/data/manual-intake";

export function ManualIntakeCards({ entries }: { entries: ManualIntakeEntry[] }) {
  if (!entries.length) return null;
  return (
    <section className="mt-7">
      <div className="mb-3 font-mono text-[10px] uppercase tracking-[0.16em] text-chart-gold">
        Manual intake · pending / unscored
      </div>
      <div className="flex flex-col gap-2">
        {entries.map((entry) => (
          <article className="rounded-lg border border-chart-gold/25 bg-chart-gold/5 px-4 py-3" key={entry.id}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <span className="font-semibold">{entry.company}</span>
                <span className="ml-2 text-chart-muted">{entry.title}</span>
                <div className="mt-1 font-mono text-[10px] text-chart-faint">{entry.location}</div>
                {entry.note ? <p className="mt-2 text-[12px] text-chart-muted">{entry.note}</p> : null}
                {entry.error ? <p className="mt-2 text-[11px] text-chart-warn">{entry.error}</p> : null}
              </div>
              <div className="shrink-0 text-right">
                <div className="font-mono text-[9px] uppercase text-chart-gold">
                  {entry.status === "manual_unscored" ? "not evaluated" : entry.status.replaceAll("_", " ")}
                </div>
                {entry.proposeWatchlist ? <div className="mt-1 font-mono text-[9px] text-chart-teal">watchlist proposed</div> : null}
                {entry.url ? <a className="mt-2 block text-[11px] text-chart-teal" href={entry.url} rel="noreferrer" target="_blank">Source ↗</a> : null}
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
