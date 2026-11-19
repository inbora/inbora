/** Base URL of this panel, used in links sent by email. */
export function siteUrl(): string {
  const env = process.env.NEXT_PUBLIC_SITE_URL;
  if (env) return env.replace(/\/$/, "");
  return typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
}
