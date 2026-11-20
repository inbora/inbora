// Server-side only (uses the session cookie).
import { createClient } from "@/lib/supabase/server";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export type Me = {
  user: { id: string; email: string; is_super_admin: boolean; full_name: string };
  tenant: { id: string; name: string; slug: string; default_language: string; status: string; role: string };
  channel_alerts?: { type: "whatsapp" | "instagram" | "email" | "widget"; display_name: string | null }[];
  plan: {
    code: string;
    name: string;
    billing_period: "one_time" | "monthly";
    conversation_quota: number;
    conversations_used: number;
    max_channels: number;
    kb_char_limit: number;
    seats?: number;
    show_branding: boolean;
    period_end: string | null;
  } | null;
};

/** Calls the Inbora API as the logged-in user. Returns null on any failure. */
export async function apiGet<T>(path: string): Promise<T | null> {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) return null;
  try {
    const res = await fetch(`${API_URL}${path}`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
