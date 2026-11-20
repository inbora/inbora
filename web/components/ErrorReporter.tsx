"use client";

import { useEffect } from "react";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
let sent = 0;

/** Sends errors in the panel (in the browser) to Inbora's error monitoring. */
export function reportClientError(message: string, stack?: string | null) {
  if (sent >= 5) return;                  // a few per page load is enough
  sent += 1;
  try {
    fetch(`${API_URL}/public/client-error`, {
      method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true,
      body: JSON.stringify({ message: message.slice(0, 1000), page: window.location.pathname, stack: stack?.slice(0, 8000) ?? null }),
    }).catch(() => {});
  } catch {}
}

export default function ErrorReporter() {
  useEffect(() => {
    const onError = (e: ErrorEvent) => reportClientError(e.message || "Error", e.error?.stack);
    const onRejection = (e: PromiseRejectionEvent) => {
      const r = e.reason;
      // Failed API calls are already shown on the page and recorded by the server.
      if (r && typeof r === "object" && "status" in r) return;
      reportClientError(r instanceof Error ? `${r.name}: ${r.message}` : String(r), r instanceof Error ? r.stack : null);
    };
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);
  return null;
}
