import LoginForm from "./login-form";

export default async function LoginPage({
  searchParams
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const params = await searchParams;

  return (
    <main className="flex min-h-screen items-center justify-center bg-chart-page px-6 text-chart-ink">
      <div className="w-full max-w-md rounded-[10px] border border-white/10 bg-chart-panel p-7">
        <div className="flex items-baseline gap-2">
          <h1 className="font-serif text-[28px] font-medium italic">Sextant</h1>
          <span className="relative -top-1 h-2 w-2 rotate-45 bg-chart-tealDeep" />
        </div>
        <p className="mt-3 text-sm leading-6 text-chart-muted">
          Private owner-only access. Sign in with the owner email and password configured in
          Supabase Auth.
        </p>
        <LoginForm error={params.error} />
      </div>
    </main>
  );
}
