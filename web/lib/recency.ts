import profileConfig from "@/generated/profile-config.json";

const DAY_MS = 24 * 60 * 60 * 1000;

export const ROLE_MAX_AGE_DAYS = profileConfig.recency.maxAgeDays;

export function recencyCutoffDate() {
  return new Date(Date.now() - ROLE_MAX_AGE_DAYS * DAY_MS).toISOString().slice(0, 10);
}

export function effectiveRoleDate(role: { postedAt: string | null; firstSeenAt: string }) {
  return role.postedAt || role.firstSeenAt;
}

export function roleIsOlderThanPolicy(role: { postedAt: string | null; firstSeenAt: string }) {
  const timestamp = new Date(effectiveRoleDate(role)).getTime();
  if (!Number.isFinite(timestamp)) return true;
  return Date.now() - timestamp > ROLE_MAX_AGE_DAYS * DAY_MS;
}

export function freshnessLabel(role: { postedAt: string | null; firstSeenAt: string }) {
  const timestamp = new Date(effectiveRoleDate(role)).getTime();
  if (!Number.isFinite(timestamp)) return role.postedAt ? "posted date unknown" : "first seen unknown";
  const days = Math.max(0, Math.floor((Date.now() - timestamp) / DAY_MS));
  const prefix = role.postedAt ? "posted" : "first seen";
  return days === 0 ? `${prefix} today` : `${prefix} ${days}d ago`;
}
