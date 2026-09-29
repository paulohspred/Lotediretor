import { NextRequest, NextResponse } from "next/server";
import { authConfig, loginStateCookieName } from "@/lib/auth/config";
import { keyFromSecret, openFromString } from "@/lib/auth/crypto";
import { completeLogin, type LoginState } from "@/lib/auth/oidc";
import { createSession, sessionCookieOptions } from "@/lib/auth/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_LOGIN_AGE_MS = 10 * 60_000;

function fail(config: ReturnType<typeof authConfig>, reason: string) {
  const url = new URL("/entrar", config.baseUrl);
  url.searchParams.set("erro", reason);
  const response = NextResponse.redirect(url);
  response.cookies.delete(loginStateCookieName(config));
  return response;
}

export async function GET(request: NextRequest) {
  const config = authConfig();
  const login = openFromString<LoginState>(
    keyFromSecret(config.sessionSecret),
    request.cookies.get(loginStateCookieName(config))?.value,
    "login-state",
  );
  if (!login || Date.now() - login.createdAt > MAX_LOGIN_AGE_MS) {
    return fail(config, "sessao-expirada");
  }
  if (request.nextUrl.searchParams.get("error")) {
    return fail(config, "login-cancelado");
  }

  // Rebuild the callback URL on the public origin (the app runs behind a proxy).
  const callbackUrl = new URL("/auth/callback", config.baseUrl);
  callbackUrl.search = request.nextUrl.search;

  let tokens;
  try {
    tokens = await completeLogin(callbackUrl, login);
  } catch (error) {
    console.error("OIDC callback failed", error instanceof Error ? error.message : error);
    return fail(config, "falha-na-autenticacao");
  }

  const session = await createSession(tokens);
  const response = NextResponse.redirect(new URL(login.returnTo, config.baseUrl));
  response.cookies.set({ ...sessionCookieOptions(session.maxAgeSeconds), value: session.id });
  response.cookies.delete(loginStateCookieName(config));
  response.headers.set("cache-control", "no-store");
  return response;
}
