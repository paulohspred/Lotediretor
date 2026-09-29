import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PLATFORM_API_URL = process.env.PLATFORM_API_URL ?? "http://127.0.0.1:3000";
const SITE_ORIGIN = process.env.NEXT_PUBLIC_SITE_URL
  ? new URL(process.env.NEXT_PUBLIC_SITE_URL).origin
  : null;

export async function POST(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (SITE_ORIGIN && origin && origin !== SITE_ORIGIN) {
    return NextResponse.json({ code: "BAD_ORIGIN" }, { status: 403 });
  }
  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  if (!body) return NextResponse.json({ code: "INVALID_JSON" }, { status: 400 });
  const payload = Object.fromEntries(
    ["name", "email", "organization", "segment", "message", "consent_privacy", "website", "source_page"]
      .map((k) => [k, body[k]]),
  );
  try {
    const response = await fetch(`${PLATFORM_API_URL}/public/leads`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        // Forward the proxy chain; the API trusts only loopback hops and
        // takes the rightmost untrusted address (appended by our edge proxy).
        "x-forwarded-for": request.headers.get("x-forwarded-for") ?? "",
      },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(10_000),
    });
    const result = await response.json().catch(() => ({}));
    return NextResponse.json(result, { status: response.status });
  } catch {
    return NextResponse.json(
      { code: "UNAVAILABLE", message: "Não foi possível enviar agora. Tente novamente em instantes." },
      { status: 502 },
    );
  }
}
