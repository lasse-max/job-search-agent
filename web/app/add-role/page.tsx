import { requireOwner } from "@/lib/auth";
import {
  AddRoleClient,
  type AddRoleInitialValues
} from "./add-role-client";

type AddRoleSearchParams = Record<string, string | string[] | undefined>;

export default async function AddRolePage({
  searchParams
}: {
  searchParams: Promise<AddRoleSearchParams>;
}) {
  const user = await requireOwner();
  const initialValues = initialValuesFromSearchParams(await searchParams);
  return <AddRoleClient initialValues={initialValues} userEmail={user.email ?? "owner"} />;
}

function initialValuesFromSearchParams(params: AddRoleSearchParams): AddRoleInitialValues {
  const destination = one(params.destination);
  const replaceId = Number(one(params.replaceId));
  return {
    mode: "url",
    company: bounded(one(params.company), 200),
    title: bounded(one(params.title), 300),
    location: bounded(one(params.location), 300),
    url: bounded(one(params.url), 2000),
    destination: ["potential_matches", "to_apply", "applied"].includes(destination)
      ? (destination as AddRoleInitialValues["destination"])
      : "potential_matches",
    proposeWatchlist: one(params.proposeWatchlist) === "1",
    replaceSubmissionId: Number.isSafeInteger(replaceId) && replaceId > 0 ? replaceId : null
  };
}

function one(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function bounded(value: string, maxLength: number) {
  return value.slice(0, maxLength);
}
