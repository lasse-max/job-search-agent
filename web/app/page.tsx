import { requireOwner } from "@/lib/auth";

const navItems = [
  { label: "Potential Matches", status: "next" },
  { label: "To Apply", status: "locked" },
  { label: "Applied", status: "locked" },
  { label: "Profile", status: "locked" }
];

export default async function HomePage() {
  const user = await requireOwner();

  return (
    <main className="flex min-h-screen bg-chart-page text-chart-ink">
      <aside className="flex w-56 shrink-0 flex-col border-r border-white/10 px-3.5 py-5">
        <div className="flex items-baseline gap-2 px-2.5 pb-6">
          <span className="font-serif text-[21px] font-medium italic tracking-wide">Sextant</span>
          <span className="relative -top-0.5 h-2 w-2 rotate-45 bg-chart-tealDeep" />
        </div>
        <nav className="flex flex-col gap-1">
          {navItems.map((item) => (
            <div
              key={item.label}
              className="flex items-center justify-between rounded-md px-2.5 py-2 text-[13.5px] text-chart-muted"
            >
              <span className="font-medium">{item.label}</span>
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-chart-faint">
                {item.status}
              </span>
            </div>
          ))}
        </nav>
        <div className="mt-auto border-t border-white/10 px-2.5 pt-4 font-mono text-[10.5px] leading-6 text-chart-faint">
          <div>foundation · step 1</div>
          <div>auth · required</div>
          <div className="text-white/30">matches · after Cato</div>
        </div>
      </aside>
      <section className="relative flex-1 overflow-hidden">
        <div className="pointer-events-none fixed bottom-0 left-56 right-0 top-0 bg-[linear-gradient(rgba(87,182,196,.028)_1px,transparent_1px),linear-gradient(90deg,rgba(87,182,196,.028)_1px,transparent_1px)] bg-[length:56px_56px]" />
        <div className="relative mx-auto max-w-5xl px-10 py-8">
          <div className="flex items-end justify-between gap-6">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-chart-faint">
                Stage 1.5 · foundation
              </p>
              <h1 className="mt-2 font-serif text-[32px] font-medium tracking-wide">
                Shared data store and private shell
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-chart-muted">
                Signed in as {user.email}. This slice stops before Potential Matches: the web app
                has auth, deployment scaffolding, and a calibrated read data layer, but no scoring
                or band logic of its own.
              </p>
            </div>
            <div className="rounded-md border border-chart-teal/30 bg-chart-teal/10 px-3 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-chart-teal">
              owner only
            </div>
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-3">
            <FoundationCard
              title="Postgres migration"
              body="SQLite rows import one-way into Supabase Postgres. Conflicts are skipped or reported as ambiguous, never overwritten."
            />
            <FoundationCard
              title="Scanner target"
              body="Set JOB_AGENT_DATABASE_URL and the existing Python scan writes to the shared Postgres store."
            />
            <FoundationCard
              title="Calibrated reads"
              body="The app data layer reads current_calibrated_role_evaluations only, filtered to the current evaluator version."
            />
          </div>

          <div className="mt-8 rounded-[10px] border border-white/10 bg-chart-panel p-5">
            <h2 className="font-serif text-[22px] font-medium">Cato checkpoint</h2>
            <p className="mt-2 text-sm leading-6 text-chart-muted">
              Step 1 is intentionally a foundation slice. Potential Matches, pipeline actions,
              tracker pages, and profile display remain locked until this migration/auth layer is
              reviewed.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}

function FoundationCard({ title, body }: { title: string; body: string }) {
  return (
    <article className="rounded-[10px] border border-white/10 bg-chart-card p-4">
      <div className="h-0.5 w-8 bg-chart-teal" />
      <h2 className="mt-4 text-[15px] font-semibold">{title}</h2>
      <p className="mt-2 text-[13px] leading-5 text-chart-muted">{body}</p>
    </article>
  );
}
