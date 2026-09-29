import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const WMS =
  "https://barueri.geopixel.com.br/geoserver-barueri/barueri/wms";

const ALLOWED = new Set([
  "eixo_logradouro",
  "faixa_de_dutos_transpetro_edif",
  "obras_edif",
  "tic_oeste_anteprojeto_edif",
  "licenciamento",
]);

export async function GET(request: NextRequest) {
  const layer = request.nextUrl.searchParams.get("layer") ?? "";
  const bbox = request.nextUrl.searchParams.get("bbox") ?? "";

  if (!ALLOWED.has(layer)) {
    return NextResponse.json(
      { code: "BARUERI_WMS_LAYER_NOT_ALLOWED" },
      { status: 404 },
    );
  }

  if (!/^-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?$/.test(bbox)) {
    return NextResponse.json(
      { code: "INVALID_BBOX" },
      { status: 400 },
    );
  }

  const params = new URLSearchParams({
    service: "WMS",
    request: "GetMap",
    version: "1.1.1",
    layers: layer,
    styles: "",
    format: "image/png",
    transparent: "true",
    width: "256",
    height: "256",
    srs: "EPSG:3857",
    bbox,
  });

  try {
    const upstream = await fetch(WMS + "?" + params.toString(), {
      signal: AbortSignal.timeout(15_000),
      cache: "no-store",
    });
    if (!upstream.ok) {
      return new NextResponse(null, { status: upstream.status });
    }
    return new NextResponse(await upstream.arrayBuffer(), {
      status: 200,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "image/png",
        "cache-control": "public, max-age=300, s-maxage=1800",
      },
    });
  } catch {
    return new NextResponse(null, { status: 502 });
  }
}
