import { NextRequest, NextResponse } from "next/server";
import { authConfig, sessionCookieName } from "@/lib/auth/config";
import { endSessionUrl } from "@/lib/auth/oidc";
import { getSession, revokeSession } from "@/lib/auth/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// POST only: a logout link cannot be triggered cross-site (SameSite=Lax
// cookies are not sent on cross-site POSTs, and Origin is checked).
export async function POST(request: NextRequest) {
  const config = authConfig();
  const origin = request.headers.get("origin");
  if (origin && origin !== config.baseUrl.origin) {
    return NextResponse.json({ code: "BAD_ORIGIN" }, { status: 403 });
  }
  const session = await getSession().catch(() => null);
  let target: string = new URL("/", config.baseUrl).toString();
  if (session) {
    await revokeSession(session.hash);
    target = (await endSessionUrl(session.idToken).catch(() => null)) ?? target;
  }
  const response = NextResponse.redirect(target, { status: 303 });
  response.cookies.delete(sessionCookieName(config));
  response.cookies.delete("ld_org");
  return response;
}
