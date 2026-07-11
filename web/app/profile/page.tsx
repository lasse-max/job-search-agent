import { requireOwner } from "@/lib/auth";
import { loadProfileData, profileDataWithoutStats } from "@/lib/data/profile";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { ProfileClient } from "./profile-client";

export default async function ProfilePage() {
  const user = await requireOwner();
  const data = await loadProfileOrFallback();
  return <ProfileClient data={data} userEmail={user.email ?? "owner"} />;
}

async function loadProfileOrFallback() {
  try {
    const supabase = await createSupabaseServerClient();
    return await loadProfileData(supabase);
  } catch {
    return profileDataWithoutStats(
      "Current criteria loaded from config; live scan stats are unavailable. Is Supabase migrated?"
    );
  }
}
