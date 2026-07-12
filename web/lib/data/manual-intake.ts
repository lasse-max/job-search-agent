import type { createSupabaseServerClient } from "@/lib/supabase/server";
import type { Database } from "@/types/database";

type AppSupabaseClient = Awaited<ReturnType<typeof createSupabaseServerClient>>;
type ManualRow = Database["public"]["Tables"]["manual_intake_submissions"]["Row"];

export type ManualIntakeEntry = {
  id: number;
  company: string;
  title: string;
  location: string;
  url: string | null;
  note: string;
  mode: ManualRow["intake_mode"];
  status: ManualRow["status"];
  destination: ManualRow["destination"];
  proposeWatchlist: boolean;
  error: string | null;
  createdAt: string;
};

export async function loadOpenManualIntakes(
  supabase: AppSupabaseClient,
  destination: ManualRow["destination"]
): Promise<ManualIntakeEntry[]> {
  const { data, error } = await supabase
    .from("manual_intake_submissions")
    .select("*")
    .eq("destination", destination)
    .in("status", ["queued", "processing", "needs_text", "manual_unscored", "failed"])
    .order("created_at", { ascending: false })
    .limit(50);
  if (error) {
    // Migration 008 is owner-applied; existing pages stay available until then.
    if (error.message.includes("manual_intake_submissions")) return [];
    throw new Error(`Unable to load manual intake: ${error.message}`);
  }
  return ((data ?? []) as ManualRow[]).map((row) => ({
    id: row.id,
    company: row.company,
    title: row.title,
    location: row.location || "Location not listed",
    url: safeHttpUrl(row.source_url),
    note: row.note || "",
    mode: row.intake_mode,
    status: row.status,
    destination: row.destination,
    proposeWatchlist: row.propose_watchlist,
    error: row.error_summary,
    createdAt: row.created_at
  }));
}

function safeHttpUrl(value: string | null) {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.toString() : null;
  } catch {
    return null;
  }
}
