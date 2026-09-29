import "server-only";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { authConfig } from "./config";
import { getSession } from "./session";

const PLATFORM_API_URL = process.env.PLATFORM_API_URL ?? "http://127.0.0.1:3000";
const UUID = /^[0-9a-f-]{36}$/i;

export class NotAuthenticated extends Error {}

/**
 * Server-side call to the platform API with the user's access token. The
 * token never reaches the browser.
 */
export async function platformFetch(
  path: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<Response> {
  const config = authConfig();
  const headers = new Headers(init.headers);
  headers.set("accept", "application/json");
  if (config.mode === "oidc") {
    const session = await getSession();
    if (!session) throw new NotAuthenticated();
    headers.set("authorization", `Bearer ${session.accessToken}`);
    const org = (await cookies()).get("ld_org")?.value;
    if (org && UUID.test(org)) headers.set("x-org-id", org);
  }
  return fetch(`${PLATFORM_API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
    signal: AbortSignal.timeout(init.timeoutMs ?? 30_000),
  });
}

/** For state-changing BFF routes: same-origin requests only. */
export function sameOrigin(request: NextRequest): boolean {
  const config = authConfig();
  const origin = request.headers.get("origin");
  return origin === null || origin === config.baseUrl.origin;
}

/** Proxy a BFF route to an authenticated platform API endpoint. */
export async function authedProxy(
  request: NextRequest,
  path: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<NextResponse> {
  if (request.method !== "GET" && !sameOrigin(request)) {
    return NextResponse.json({ code: "BAD_ORIGIN" }, { status: 403 });
  }
  try {
    const response = await platformFetch(path, init);
    if (response.status === 204) return new NextResponse(null, { status: 204 });
    const body = await response.json().catch(() => ({}));
    return NextResponse.json(body, {
      status: response.status,
      headers: { "cache-control": "no-store" },
    });
  } catch (error) {
    if (error instanceof NotAuthenticated) {
      return NextResponse.json(
        { code: "AUTH_REQUIRED", message: "Sua sessão expirou. Entre novamente." },
        { status: 401 },
      );
    }
    return NextResponse.json(
      { code: "PLATFORM_API_UNAVAILABLE", message: "Serviço temporariamente indisponível." },
      { status: 502 },
    );
  }
}

/**
 * Expensive public-data BFF routes (parcel dossier, point context) are part
 * of the product: require a signed-in session before spending upstream
 * resources. Returns a response to send, or null to continue.
 */
export async function requireSessionForBff(): Promise<NextResponse | null> {
  if (authConfig().mode !== "oidc") return null;
  if (await getSession().catch(() => null)) return null;
  return NextResponse.json(
    { code: "AUTH_REQUIRED", message: "Sua sessão expirou. Entre novamente." },
    { status: 401 },
  );
}
