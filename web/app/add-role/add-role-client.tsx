"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import {
  submitManualIntake,
  type ManualIntakeDestination,
  type ManualIntakeMode
} from "./actions";

const modes: Array<{ key: ManualIntakeMode; label: string; help: string }> = [
  { key: "url", label: "Job URL", help: "Best first try. The agent fetches, parses and evaluates it." },
  { key: "text", label: "Paste JD text", help: "Full evaluation for login-walled or JavaScript-heavy career sites." },
  { key: "manual", label: "Manual line", help: "Last resort only. Saved clearly as not evaluated." }
];

export function AddRoleClient({ userEmail }: { userEmail: string }) {
  const [mode, setMode] = useState<ManualIntakeMode>("url");
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);

  return (
    <main className="flex min-h-screen bg-chart-page text-chart-ink">
      <aside className="flex w-56 shrink-0 flex-col border-r border-white/10 px-3.5 py-5">
        <div className="flex items-baseline gap-2 px-2.5 pb-6">
          <span className="font-serif text-[21px] font-medium italic">Sextant</span>
          <span className="h-2 w-2 rotate-45 bg-chart-tealDeep" />
        </div>
        <Link className="rounded-md px-2.5 py-2 text-[13.5px] text-chart-muted" href="/">Potential Matches</Link>
        <Link className="rounded-md bg-chart-teal/10 px-2.5 py-2 text-[13.5px]" href="/add-role">Add a role</Link>
        <Link className="rounded-md px-2.5 py-2 text-[13.5px] text-chart-muted" href="/to-apply">To Apply</Link>
        <Link className="rounded-md px-2.5 py-2 text-[13.5px] text-chart-muted" href="/applied">Applied</Link>
        <div className="mt-auto truncate border-t border-white/10 px-2.5 pt-4 font-mono text-[10px] text-white/30">owner · {userEmail}</div>
      </aside>
      <section className="relative min-w-0 flex-1">
        <div className="mx-auto max-w-[860px] px-10 py-8 pb-24">
          <h1 className="font-serif text-[32px] font-medium">Add a role</h1>
          <p className="mt-1 font-mono text-[11px] text-chart-faint">one evaluator · three intake paths · no PDF upload</p>

          <div className="mt-7 grid grid-cols-3 gap-3">
            {modes.map((item) => (
              <button
                className={`rounded-lg border p-4 text-left ${mode === item.key ? "border-chart-teal/50 bg-chart-teal/10" : "border-white/10 bg-chart-card"}`}
                key={item.key}
                onClick={() => setMode(item.key)}
                type="button"
              >
                <div className="text-sm font-semibold">{item.label}</div>
                <p className="mt-2 text-[11px] leading-5 text-chart-muted">{item.help}</p>
              </button>
            ))}
          </div>

          <form
            className="mt-5 rounded-[10px] border border-white/10 bg-chart-panel p-6"
            onSubmit={(event) => {
              event.preventDefault();
              const formElement = event.currentTarget;
              const form = new FormData(formElement);
              startTransition(async () => {
                const result = await submitManualIntake({
                  mode,
                  company: String(form.get("company") ?? ""),
                  title: String(form.get("title") ?? ""),
                  location: String(form.get("location") ?? ""),
                  url: String(form.get("url") ?? ""),
                  jdText: String(form.get("jdText") ?? ""),
                  note: String(form.get("note") ?? ""),
                  destination: String(form.get("destination")) as ManualIntakeDestination,
                  proposeWatchlist: form.get("proposeWatchlist") === "on"
                });
                setMessage(result.message);
                if (result.ok) formElement.reset();
              });
            }}
          >
            <div className="grid grid-cols-2 gap-4">
              <Field label="Company" name="company" required />
              <Field label="Role title" name="title" required />
              <Field label="Location" name="location" />
              <Field
                label={mode === "url" ? "Job URL" : "Source URL (optional)"}
                name="url"
                required={mode === "url"}
                type="url"
              />
            </div>
            {mode === "text" ? (
              <TextArea label="Job description text" name="jdText" required rows={12} />
            ) : null}
            <TextArea
              label={mode === "manual" ? "Note / context (not evaluated)" : "Private note"}
              name="note"
              rows={4}
            />
            <div className="mt-5 grid grid-cols-[1fr_auto] items-end gap-5">
              <label className="text-[12px] text-chart-muted">
                Destination
                <select className="mt-2 block w-full rounded border border-white/10 bg-chart-card px-3 py-2 text-chart-ink" name="destination">
                  <option value="potential_matches">Potential Matches</option>
                  <option value="to_apply">To Apply</option>
                  <option value="applied">Applied</option>
                </select>
              </label>
              <button className="rounded-md bg-chart-rust px-5 py-2.5 text-sm font-semibold disabled:opacity-50" disabled={pending} type="submit">
                {pending ? "Saving…" : mode === "manual" ? "Save unscored role" : "Queue evaluation"}
              </button>
            </div>
            <label className="mt-4 flex items-center gap-2 text-[12px] text-chart-muted">
              <input name="proposeWatchlist" type="checkbox" />
              Propose this company for the watchlist if it is currently off-list
            </label>
            {message ? <div className="mt-4 rounded border border-chart-teal/25 bg-chart-teal/10 px-3 py-2 text-sm text-chart-teal">{message}</div> : null}
          </form>
        </div>
      </section>
    </main>
  );
}

function Field({ label, name, required = false, type = "text" }: { label: string; name: string; required?: boolean; type?: string }) {
  return <label className="text-[12px] text-chart-muted">{label}<input className="mt-2 block w-full rounded border border-white/10 bg-chart-card px-3 py-2 text-chart-ink" name={name} required={required} type={type} /></label>;
}

function TextArea({ label, name, required = false, rows }: { label: string; name: string; required?: boolean; rows: number }) {
  return <label className="mt-4 block text-[12px] text-chart-muted">{label}<textarea className="mt-2 block w-full rounded border border-white/10 bg-chart-card px-3 py-2 text-chart-ink" name={name} required={required} rows={rows} /></label>;
}
