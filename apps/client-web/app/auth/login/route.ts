import { NextRequest, NextResponse } from "next/server";
import { authConfig, loginStateCookieName, secureCookies } from "@/lib/auth/config";
import { keyFromSecret, safeReturnTo, sealToString } from "@/lib/auth/crypto";
import { beginLogin } from "@/lib/auth/oidc";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const LOGIN_STATE_TTL_SECONDS = 600;

export async function GET(request: NextRequest) {
  const config = authConfig();
  if (config.mode !== "oidc") {
    return NextResponse.redirect(new URL("/dashboard", config.baseUrl));
  }
  const returnTo = safeReturnTo(request.nextUrl.searchParams.get("returnTo"));
  // Optional hints for the IdP: signup screen or re-authentication.
  const extra: Record<string, string> = {};
  if (request.nextUrl.searchParams.get("signup") === "1") {
    extra.prompt = "create";
  }
  let begun;
  try {
    begun = await beginLogin(returnTo, extra);
  } catch {
    return NextResponse.json(
      { code: "IDP_UNAVAILABLE", message: "Serviço de login indisponível. Tente novamente." },
      { status: 503 },
    );
  }
  const response = NextResponse.redirect(begun.url);
  response.cookies.set({
    name: loginStateCookieName(config),
    value: sealToString(keyFromSecret(config.sessionSecret), begun.state, "login-state"),
    httpOnly: true,
    secure: secureCookies(config),
    sameSite: "lax",
    path: "/",
    maxAge: LOGIN_STATE_TTL_SECONDS,
  });
  response.headers.set("cache-control", "no-store");
  return response;
}
