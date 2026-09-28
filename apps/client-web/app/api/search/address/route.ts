import { NextRequest, NextResponse } from "next/server";
import { cityByIbge } from "@/lib/cities";

export const runtime = "nodejs";

function norm(value: unknown): string {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get("q")?.trim() ?? "";
  const ibge = request.nextUrl.searchParams.get("ibge") ?? "3550308";
  if (q.length < 3) {
    return NextResponse.json({ results: [] });
  }

  const city = cityByIbge(ibge);
  const params = new URLSearchParams({
    street: q,
    city: city.name,
    state: city.uf,
    country: "Brasil",
    format: "jsonv2",
    limit: "10",
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
    const wanted = norm(city.name);
    const filtered = data.filter((item) => {
      const address = (item.address ?? {}) as Record<string, unknown>;
      return [address.city, address.town, address.municipality].some(
        (value) => norm(value) === wanted,
      );
    });

    return NextResponse.json({
      results: filtered.slice(0, 5).map((item) => {
        const address = (item.address ?? {}) as Record<string, unknown>;
        return {
          display_name: item.display_name,
          lat: Number(item.lat),
          lng: Number(item.lon),
          address,
          exact_house_number: Boolean(address.house_number),
        };
      }),
      warning:
        filtered.length === 0
          ? "Nenhum endereço foi localizado dentro do município selecionado."
          : undefined,
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
