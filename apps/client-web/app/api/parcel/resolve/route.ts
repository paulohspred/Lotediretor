import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  const payload = await request.json();
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
      signal: AbortSignal.timeout(180_000),
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
