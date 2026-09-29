import { NextRequest, NextResponse } from "next/server";

import { requireSessionForBff } from "@/lib/auth/api";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  const denied = await requireSessionForBff();
  if (denied) return denied;
  const payload = await request.json().catch(() => null);
  if (!payload || typeof payload !== "object") {
    return NextResponse.json(
      { code: "INVALID_JSON", message: "Requisição inválida." },
      { status: 400 },
    );
  }
  const platformApi =
    process.env.PLATFORM_API_URL ?? "http://127.0.0.1:3000";

  try {
    const response = await fetch(`${platformApi}/parcel/resolve`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "application/json",
      },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(115_000),
      cache: "no-store",
    });
    const body = await response.json().catch(() => ({}));
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json(
      {
        code: "PLATFORM_API_UNAVAILABLE",
        message: "A análise territorial está temporariamente indisponível.",
        retryable: true,
      },
      { status: 502 },
    );
  }
}
