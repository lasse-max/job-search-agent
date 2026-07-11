"use client";

import { createBrowserClient } from "@supabase/ssr";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

export default function LoginForm({
  error
}: {
  error?: string;
}) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const supabase = useMemo(
    () =>
      createBrowserClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? ""
      ),
    []
  );

  useEffect(() => {
    if (error === "unauthorized") {
      void supabase.auth.signOut();
      setMessage(null);
    }
  }, [error, supabase]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setMessage(null);
    const { error: signInError } = await supabase.auth.signInWithPassword({
      email,
      password
    });
    setSubmitting(false);
    if (signInError) {
      setMessage("Invalid email or password.");
      return;
    }
    router.replace("/");
    router.refresh();
  }

  return (
    <form className="mt-6 space-y-4" onSubmit={submit}>
      {error === "unauthorized" ? (
        <div className="rounded-md border border-chart-warn/30 bg-chart-warn/10 px-3 py-2 text-sm text-chart-warn">
          This account is not allowed for this app.
        </div>
      ) : null}
      <label className="block">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-chart-faint">
          Email
        </span>
        <input
          className="mt-2 w-full rounded-md border border-white/10 bg-chart-card px-3 py-2 text-sm text-chart-ink outline-none ring-chart-teal/40 focus:border-chart-teal focus:ring-2"
          type="email"
          value={email}
          onChange={(event) => {
            setEmail(event.target.value);
            setMessage(null);
          }}
          autoComplete="email"
          required
        />
      </label>
      <label className="block">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-chart-faint">
          Password
        </span>
        <input
          className="mt-2 w-full rounded-md border border-white/10 bg-chart-card px-3 py-2 text-sm text-chart-ink outline-none ring-chart-teal/40 focus:border-chart-teal focus:ring-2"
          type="password"
          value={password}
          onChange={(event) => {
            setPassword(event.target.value);
            setMessage(null);
          }}
          autoComplete="current-password"
          required
        />
      </label>
      <button
        className="w-full rounded-md bg-[#b8472f] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#cf5638] disabled:cursor-not-allowed disabled:opacity-60"
        type="submit"
        disabled={submitting}
      >
        {submitting ? "Signing in..." : "Sign in"}
      </button>
      {message ? <p className="text-sm text-chart-muted">{message}</p> : null}
    </form>
  );
}
