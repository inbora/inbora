"use client";

import { createClient } from "@/lib/supabase/client";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`API ${status}`);
  }
}

/** Calls the Inbora API from the browser as the logged-in user. */
export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const { data } = await createClient().auth.getSession();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${data.session?.access_token ?? ""}`,
      ...(init.headers || {}),
    },
  });
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = (await res.json()).detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}
