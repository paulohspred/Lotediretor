import {
  BadGatewayException,
  BadRequestException,
  Injectable,
} from "@nestjs/common";

const MUNICIPALITY_SLUG: Record<string, string> = {
  "3550308": "sp",
  "2611606": "recife",
  "3304557": "rio",
  "3106200": "bh",
  "2507507": "jp",
};

export interface ParcelResolveInput {
  municipality_ibge: string;
  lat: number;
  lng: number;
  analysis_date?: string;
}

@Injectable()
export class ParcelEngineService {
  private readonly engineBase =
    process.env.PARCEL_ENGINE_BASE_URL ?? "http://127.0.0.1:8765";

  async resolve(input: ParcelResolveInput): Promise<unknown> {
    const slug = MUNICIPALITY_SLUG[input.municipality_ibge];
    if (!slug) {
      throw new BadRequestException({
        code: "UNSUPPORTED_MUNICIPALITY",
        message: "Município ainda não habilitado no Parcel Resolver.",
      });
    }
    if (!Number.isFinite(input.lat) || !Number.isFinite(input.lng)) {
      throw new BadRequestException({
        code: "INVALID_COORDINATE",
        message: "Latitude e longitude válidas são obrigatórias.",
      });
    }

    const params = new URLSearchParams({
      lat: String(input.lat),
      lng: String(input.lng),
    });
    const url = `${this.engineBase}/v1/${slug}/parcel?${params}`;

    let response: Response;
    try {
      response = await fetch(url, {
        headers: { Accept: "application/json" },
        signal: AbortSignal.timeout(180_000),
      });
    } catch {
      throw new BadGatewayException({
        code: "PARCEL_ENGINE_UNAVAILABLE",
        message: "Engine territorial indisponível.",
        retryable: true,
      });
    }

    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new BadGatewayException({
        code: "PARCEL_ENGINE_ERROR",
        message: "Falha no engine territorial.",
        retryable: response.status >= 500,
        upstream_status: response.status,
      });
    }
    return body;
  }
}
