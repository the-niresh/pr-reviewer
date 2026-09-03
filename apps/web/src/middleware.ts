import { NextResponse, type NextRequest } from "next/server";

// A signed-in visitor landing on "/" gets bounced straight to the dashboard: showing the
// sign-in button again "as if nothing happened" (see apps/web/src/app/page.tsx) is exactly
// the confusion task 4 rules out. Matches the OAuth callback's own destination
// (github_oauth.py's ALLOWED_RETURN_TO_PATHS default), so a repeat visit lands the same
// place a fresh sign-in would.
//
// The cookie's mere presence is enough for this redirect. It is not a substitute for the
// real, cryptographic check /dashboard's own server component already runs via
// fetchReviews/fetchProfile: an expired or tampered cookie just falls through to that
// page's own sign-in prompt instead of ever granting anything here.
const SIGN_IN_COOKIE = "gh_live_sign_in";

export function middleware(request: NextRequest) {
  if (request.cookies.has(SIGN_IN_COOKIE)) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: "/",
};
