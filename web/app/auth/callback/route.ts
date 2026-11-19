import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";

/** Link target for signup confirmation and password reset (PKCE "?code=" links). */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const code = searchParams.get("code");
  const next = safeNext(searchParams.get("next"));

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(`${origin}${next}`);
  }
  return NextResponse.redirect(`${origin}/login`);
}

function safeNext(v: string | null): string {
  // Only allow local paths, never an outside URL.
  return v && v.startsWith("/") && !v.startsWith("//") ? v : "/inbox";
}
