import { NextRequest, NextResponse } from "next/server";
import { authConfig, secureCookies } from "@/lib/auth/config";
import { platformFetch, sameOrigin } from "@/lib/auth/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Select the active organization. The API re-checks membership on every call. */
export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ code: "BAD_ORIGIN" }, { status: 403 });
  const body = (await request.json().catch(() => null)) as { org_id?: unknown } | null;
  const orgId = typeof body?.org_id === "string" ? body.org_id : "";
  if (!/^[0-9a-f-]{36}$/i.test(orgId)) {
    return NextResponse.json({ code: "INVALID_ORG" }, { status: 400 });
  }
  const check = await platformFetch("/me", { headers: { "x-org-id": orgId } }).catch(() => null);
  if (!check?.ok) return NextResponse.json({ code: "ORG_FORBIDDEN" }, { status: 403 });
  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: "ld_org",
    value: orgId,
    httpOnly: true,
    secure: secureCookies(authConfig()),
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  return response;
}
