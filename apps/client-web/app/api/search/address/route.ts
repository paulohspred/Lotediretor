import { NextRequest, NextResponse } from "next/server";
import { cityByIbge } from "@/lib/cities";

export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get("q")?.trim() ?? "";
  const ibge = request.nextUrl.searchParams.get("ibge") ?? "3550308";
  if (q.length < 3) {
    return NextResponse.json({ results: [] });
  }

  const city = cityByIbge(ibge);
  const params = new URLSearchParams({
    q: `${q}, ${city.name} - ${city.uf}, Brasil`,
    format: "jsonv2",
    limit: "5",
    countrycodes: "br",
    addressdetails: "1",
  });

  try {
    const response = await fetch(
      `https://nominatim.openstreetmap.org/search?${params}`,
      {
        headers: {
          accept: "application/json",
          "accept-language": "pt-BR",
          "user-agent": "LoteDiretor/1.0 (+https://lotediretor.com)",
        },
        signal: AbortSignal.timeout(12_000),
        next: { revalidate: 86400 },
      },
    );
    if (!response.ok) throw new Error("geocoder_error");
    const data = (await response.json()) as Array<Record<string, unknown>>;
    return NextResponse.json({
      results: data.map((item) => ({
        display_name: item.display_name,
        lat: Number(item.lat),
        lng: Number(item.lon),
        address: item.address ?? {},
      })),
    });
  } catch {
    return NextResponse.json(
      {
        results: [],
        warning: "Busca de endereço temporariamente indisponível.",
      },
      { status: 200 },
    );
  }
}
