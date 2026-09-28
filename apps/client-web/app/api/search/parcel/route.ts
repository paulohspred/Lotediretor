import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const PLATFORM_API_URL =
  process.env.PLATFORM_API_URL ?? "http://127.0.0.1:3000";

export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get("q")?.trim() ?? "";
  const ibge = request.nextUrl.searchParams.get("ibge") ?? "3550308";

  if (q.length < 3 || q.length > 80) {
    return NextResponse.json({ results: [] });
  }

  const params = new URLSearchParams({
    municipality_ibge: ibge,
    q,
  });

  try {
    const response = await fetch(
      `${PLATFORM_API_URL}/parcel/search?${params}`,
      {
        headers: { accept: "application/json" },
        signal: AbortSignal.timeout(30_000),
        cache: "no-store",
      },
    );

    if (!response.ok) {
      return NextResponse.json({ results: [] }, { status: 200 });
    }

    const body = await response.json();
    return NextResponse.json(body, {
      headers: { "cache-control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      {
        results: [],
        warning: "Busca cadastral temporariamente indisponível.",
      },
      { status: 200 },
    );
  }
}
