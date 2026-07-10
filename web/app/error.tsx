"use client";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-chart-page px-6 text-chart-ink">
      <section className="max-w-xl rounded-[10px] border border-chart-warn/30 bg-chart-panel p-6">
        <div className="flex items-baseline gap-2">
          <span className="font-serif text-[21px] font-medium italic tracking-wide">Sextant</span>
          <span className="relative -top-0.5 h-2 w-2 rotate-45 bg-chart-tealDeep" />
        </div>
        <p className="mt-6 font-mono text-[11px] uppercase tracking-[0.18em] text-chart-warn">
          Couldn&apos;t load data
        </p>
        <h1 className="mt-2 font-serif text-[28px] font-medium">Is the database migrated?</h1>
        <p className="mt-3 text-sm leading-6 text-chart-muted">
          The app could not reach the Supabase-backed read layer. Check that the Postgres migration
          has run and that the web app environment variables are configured.
        </p>
        <button
          className="mt-5 rounded-md bg-chart-rust px-3 py-2 text-[12px] font-semibold text-white/95 transition hover:bg-[#cf5638]"
          onClick={reset}
          type="button"
        >
          Try again
        </button>
      </section>
    </main>
  );
}
