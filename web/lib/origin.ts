import type { NextRequest } from "next/server";

/** The address the visitor actually used (e.g. https://app.inbora.ai).
 *  Behind Render's proxy, request.nextUrl.origin is the internal
 *  http://localhost:10000, so redirects must not be built from it. */
export function publicOrigin(request: NextRequest): string {
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  if (host && !/^(localhost|127\.0\.0\.1|0\.0\.0\.0)(:|$)/.test(host)) {
    const proto = (request.headers.get("x-forwarded-proto") ?? "https").split(",")[0].trim();
    return `${proto}://${host.split(",")[0].trim()}`;
  }
  const site = process.env.NEXT_PUBLIC_SITE_URL;
  if (site) return site.replace(/\/$/, "");
  return request.nextUrl.origin;
}
