import profileConfig from "@/generated/profile-config.json";

const DAY_MS = 24 * 60 * 60 * 1000;

export const ROLE_MAX_AGE_DAYS = profileConfig.recency.maxAgeDays;

export function recencyCutoffDate(now = new Date()) {
  return new Date(now.getTime() - ROLE_MAX_AGE_DAYS * DAY_MS).toISOString().slice(0, 10);
}

export function effectiveRoleDate(role: { postedAt: string | null; firstSeenAt: string }) {
  return role.postedAt || role.firstSeenAt;
}

export function roleIsOlderThanPolicy(
  role: { postedAt: string | null; firstSeenAt: string },
  now = new Date()
) {
  const timestamp = normalizeTimestamp(effectiveRoleDate(role));
  if (!Number.isFinite(timestamp)) return true;
  return timestamp < utcDayTimestamp(now.getTime()) - ROLE_MAX_AGE_DAYS * DAY_MS;
}

export function freshnessLabel(
  role: { postedAt: string | null; firstSeenAt: string },
  now = new Date()
) {
  const timestamp = normalizeTimestamp(effectiveRoleDate(role));
  if (!Number.isFinite(timestamp)) return role.postedAt ? "posted date unknown" : "first seen unknown";
  const days = Math.max(0, (utcDayTimestamp(now.getTime()) - utcDayTimestamp(timestamp)) / DAY_MS);
  const prefix = role.postedAt ? "posted" : "first seen";
  return days === 0 ? `${prefix} today` : `${prefix} ${days}d ago`;
}

export function normalizeTimestamp(value: string) {
  const iso = value.trim().replace(" ", "T");
  if (!iso) return Number.NaN;
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return Date.parse(`${iso}T00:00:00Z`);
  // Historical timestamps without an offset are UTC, never the browser's zone.
  const zoned = /(?:[Zz]|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
  return Date.parse(zoned);
}

function utcDayTimestamp(timestamp: number) {
  return Math.floor(timestamp / DAY_MS) * DAY_MS;
}
