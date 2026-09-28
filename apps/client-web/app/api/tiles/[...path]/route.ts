import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const MARTIN_URL = process.env.MARTIN_URL ?? "http://127.0.0.1:3002";
const ALLOWED = new Set([
  "ibge_censo2022_setores",
  "jp_lotes",
  "jp_curvas_nivel_2022",
]);

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const source = path[0];
  if (!source || !ALLOWED.has(source)) {
    return NextResponse.json(
      { code: "TILE_SOURCE_NOT_ALLOWED" },
      { status: 404 },
    );
  }

  const suffix = path.map(encodeURIComponent).join("/");
  try {
    const upstream = await fetch(`${MARTIN_URL}/${suffix}`, {
      headers: {
        accept: request.headers.get("accept") ?? "*/*",
      },
      signal: AbortSignal.timeout(15_000),
      cache: "no-store",
    });

    if (!upstream.ok) {
      return new NextResponse(null, { status: upstream.status });
    }

    const body = await upstream.arrayBuffer();
    return new NextResponse(body, {
      status: 200,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ??
          "application/x-protobuf",
        "cache-control": "public, max-age=300, s-maxage=3600",
      },
    });
  } catch {
    return new NextResponse(null, { status: 502 });
  }
}
