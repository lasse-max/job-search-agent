"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { removeFromShortlist } from "@/app/actions/opportunities";
import { markApplied } from "@/app/applied/actions";
import type { ShortlistData, ShortlistedRole } from "@/lib/data/shortlist";
import { freshnessLabel } from "@/lib/recency";

export function ToApplyClient({ data, userEmail }: { data: ShortlistData; userEmail: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [status, setStatus] = useState<string | null>(null);

  function act(action: () => Promise<{ ok: boolean; message: string }>) {
    startTransition(async () => {
      const result = await action();
      setStatus(result.message);
      if (result.ok) {
        router.refresh();
      }
    });
  }

  return (
    <main className="flex min-h-screen bg-chart-page text-chart-ink">
      <ToApplyNav count={data.roles.length} userEmail={userEmail} />
      <section className="relative min-w-0 flex-1 overflow-hidden">
        <div className="pointer-events-none fixed bottom-0 left-56 right-0 top-0 bg-[linear-gradient(rgba(87,182,196,.028)_1px,transparent_1px),linear-gradient(90deg,rgba(87,182,196,.028)_1px,transparent_1px)] bg-[length:56px_56px]" />
        <div className="relative mx-auto max-w-[1040px] px-10 py-8 pb-24">
          <header>
            <h1 className="font-serif text-[32px] font-medium tracking-wide">To Apply</h1>
            <p className="mt-1 font-mono text-[11px] text-chart-faint">
              a small working shortlist · nothing advances without your click
            </p>
          </header>
          {data.loadError ? (
            <div className="mt-6 rounded-lg border border-chart-warn/30 bg-chart-warn/10 px-4 py-3 text-sm text-chart-warn">
              {data.loadError}
            </div>
          ) : null}
          {status ? (
            <div className="mt-5 rounded border border-chart-teal/25 bg-chart-teal/10 px-3 py-2 text-sm text-chart-teal">
              {status}
            </div>
          ) : null}
          <div className="mt-7 flex flex-col gap-3">
            {data.roles.map((role) => (
              <ShortlistCard
                disabled={pending}
                key={role.id}
                onApply={() => act(() => markApplied(role.id))}
                onRemove={() => act(() => removeFromShortlist(role.id))}
                role={role}
              />
            ))}
          </div>
          {!data.roles.length && !data.loadError ? <EmptyShortlist /> : null}
        </div>
      </section>
    </main>
  );
}

function ShortlistCard({
  disabled,
  onApply,
  onRemove,
  role
}: {
  disabled: boolean;
  onApply: () => void;
  onRemove: () => void;
  role: ShortlistedRole;
}) {
  return (
    <article className="rounded-[10px] border border-white/10 bg-chart-card px-5 py-4">
      <div className="flex items-start gap-5">
        <div className="flex h-[54px] w-[54px] shrink-0 flex-col items-center justify-center rounded-lg border border-chart-teal/35 bg-chart-teal/10">
          <span className="font-mono text-[20px] text-chart-teal">{role.fitScore}</span>
          <span className="font-mono text-[8px] uppercase tracking-[0.14em] text-chart-faint">fit</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <h2 className="text-[15px] font-semibold">{role.company}</h2>
            <span className="text-[14px] text-chart-muted">{role.title}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-2 font-mono text-[10.5px] text-chart-faint">
            <span>{role.locationsLabel}</span>
            <span>·</span>
            <span>{ageLabel(role.flaggedAt)}</span>
            <span>·</span>
            <span>{freshnessLabel(role)}</span>
          </div>
          <p className="mt-3 text-[13px] leading-5 text-chart-muted">
            {role.note || "No note added."}
          </p>
        </div>
        <div className="flex w-36 shrink-0 flex-col items-stretch gap-2">
          <button
            className="rounded-md bg-chart-rust px-3 py-2 text-[12px] font-semibold text-white/95 disabled:opacity-50"
            disabled={disabled}
            onClick={onApply}
            type="button"
          >
            Mark applied
          </button>
          <button
            className="rounded border border-white/10 px-3 py-2 text-[11px] text-chart-muted transition hover:border-white/25 hover:text-chart-ink disabled:opacity-50"
            disabled={disabled}
            onClick={onRemove}
            type="button"
          >
            Remove
          </button>
          {role.sourceUrl ? (
            <a
              className="text-center font-mono text-[10.5px] text-chart-teal"
              href={role.sourceUrl}
              rel="noreferrer"
              target="_blank"
            >
              Open source ↗
            </a>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function EmptyShortlist() {
  return (
    <div className="mt-20 text-center">
      <div className="font-serif text-[22px] italic text-chart-muted">
        Nothing shortlisted — mark roles from Potential Matches.
      </div>
      <Link className="mt-4 inline-block text-sm text-chart-teal" href="/">
        Back to matches →
      </Link>
    </div>
  );
}

function ToApplyNav({ count, userEmail }: { count: number; userEmail: string }) {
  const links = [
    ["Potential Matches", "/", ""],
    ["To Apply", "/to-apply", String(count)],
    ["Applied", "/applied", ""],
    ["Profile", "/profile", ""]
  ] as const;
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-white/10 px-3.5 py-5">
      <div className="flex items-baseline gap-2 px-2.5 pb-6">
        <span className="font-serif text-[21px] font-medium italic tracking-wide">Sextant</span>
        <span className="relative -top-0.5 h-2 w-2 rotate-45 bg-chart-tealDeep" />
      </div>
      <nav className="flex flex-col gap-1">
        {links.map(([label, href, value]) => (
          <Link
            className={`flex items-center justify-between rounded-md px-2.5 py-2 text-[13.5px] ${
              href === "/to-apply" ? "bg-chart-teal/10 text-chart-ink" : "text-chart-muted"
            }`}
            href={href}
            key={href}
          >
            <span className="font-medium">{label}</span>
            <span className="font-mono text-[10px] text-chart-teal">{value}</span>
          </Link>
        ))}
      </nav>
      <div className="mt-auto border-t border-white/10 px-2.5 pt-4 font-mono text-[10.5px] leading-6 text-chart-faint">
        <div>owner-gated shortlist</div>
        <div className="truncate text-white/30">owner · {userEmail}</div>
      </div>
    </aside>
  );
}

function ageLabel(value: string) {
  const elapsedDays = Math.max(
    0,
    Math.floor((Date.now() - new Date(value).getTime()) / (24 * 60 * 60 * 1000))
  );
  return elapsedDays === 0 ? "flagged today" : `flagged ${elapsedDays}d ago`;
}
