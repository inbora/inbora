import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { publicOrigin } from "@/lib/origin";

// Pages anyone can open without logging in.
const PUBLIC_PATHS = ["/login", "/signup", "/forgot-password", "/auth"];
// Pages a logged-in user should be sent away from.
const GUEST_ONLY = ["/login", "/signup", "/forgot-password"];

const startsWithAny = (path: string, list: string[]) =>
  list.some((p) => path === p || path.startsWith(p + "/"));

export async function updateSession(request: NextRequest) {
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL || !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY) {
    return new NextResponse(
      "Inbora: NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are not set. " +
        "Add them to the web service's environment and redeploy.",
      { status: 500 },
    );
  }

  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(toSet) {
          toSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          toSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        },
      },
    },
  );

  // Refreshes the session cookie if needed. Do not remove.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const path = request.nextUrl.pathname;

  if (!user && !startsWithAny(path, PUBLIC_PATHS)) {
    return NextResponse.redirect(new URL("/login", publicOrigin(request)));
  }

  if (user && startsWithAny(path, GUEST_ONLY)) {
    return NextResponse.redirect(new URL("/inbox", publicOrigin(request)));
  }

  return response;
}
