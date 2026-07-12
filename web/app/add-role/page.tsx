import { requireOwner } from "@/lib/auth";
import { AddRoleClient } from "./add-role-client";

export default async function AddRolePage() {
  const user = await requireOwner();
  return <AddRoleClient userEmail={user.email ?? "owner"} />;
}
