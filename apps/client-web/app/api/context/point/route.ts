import { NextRequest, NextResponse } from "next/server";

import { requireSessionForBff } from "@/lib/auth/api";

export const runtime = "nodejs";

const PLATFORM_API_URL =
  process.env.PLATFORM_API_URL ?? "http://127.0.0.1:3000";

export async function POST(request: NextRequest) {
  const denied = await requireSessionForBff();
  if (denied) return denied;
  const body = (await request.json().catch(() => null)) as {
    lat?: unknown;
    lng?: unknown;
  } | null;
  if (!body || typeof body.lat !== "number" || typeof body.lng !== "number") {
    return NextResponse.json(
      { code: "INVALID_COORDINATE", message: "Coordenadas inválidas." },
      { status: 400 },
    );
  }
  try {
    // Only lat/lng are forwarded; the municipality is resolved server-side.
    const response = await fetch(`${PLATFORM_API_URL}/context/point`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({ lat: body.lat, lng: body.lng }),
      signal: AbortSignal.timeout(115_000),
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    return NextResponse.json(payload, { status: response.status });
  } catch {
    return NextResponse.json(
      {
        code: "PLATFORM_API_UNAVAILABLE",
        message: "O contexto territorial está temporariamente indisponível.",
        retryable: true,
      },
      { status: 502 },
    );
  }
}
