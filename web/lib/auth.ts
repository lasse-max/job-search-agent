import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function requireOwner() {
  const supabase = await createSupabaseServerClient();
  const {
    data: { user }
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const ownerEmail = process.env.OWNER_EMAIL;
  if (!ownerEmail) {
    throw new Error("OWNER_EMAIL must be set for the single-user web app.");
  }

  if ((user.email ?? "").toLowerCase() !== ownerEmail.toLowerCase()) {
    redirect("/login?error=unauthorized");
  }

  return user;
}
