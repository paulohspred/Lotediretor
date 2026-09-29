import {
  BadGatewayException,
  BadRequestException,
  Body,
  Controller,
  HttpCode,
  Injectable,
  Module,
  Post,
} from "@nestjs/common";
import { humanValues } from "../geo/parcel-engine.service.js";
import { TerritoryModule, TerritoryService } from "../territory/territory.module.js";

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : {};
}

export interface PointContextInput {
  lat: number;
  lng: number;
}

/**
 * Federal/state context for a point anywhere in Brazil. The municipality is
 * resolved here from the IBGE mesh (trusted), never taken from the client.
 */
@Injectable()
export class PointContextService {
  private readonly engineBase =
    process.env.PARCEL_ENGINE_BASE_URL ?? "http://127.0.0.1:8765";

  constructor(private readonly territory: TerritoryService) {}

  async build(input: PointContextInput) {
    if (
      typeof input?.lat !== "number" ||
      typeof input?.lng !== "number" ||
      !Number.isFinite(input.lat) ||
      !Number.isFinite(input.lng)
    ) {
      throw new BadRequestException({
        code: "INVALID_COORDINATE",
        message: "Latitude e longitude válidas são obrigatórias.",
      });
    }
    const municipality = await this.territory.resolve(
      String(input.lat),
      String(input.lng),
    );

    const params = new URLSearchParams({
      lat: String(input.lat),
      lng: String(input.lng),
      municipality_ibge: municipality.ibge_code,
    });
    let response: Response;
    try {
      response = await fetch(`${this.engineBase}/v1/point-context?${params}`, {
        headers: { Accept: "application/json" },
        signal: AbortSignal.timeout(110_000),
      });
    } catch {
      throw new BadGatewayException({
        code: "CONTEXT_ENGINE_UNAVAILABLE",
        message: "Contexto territorial temporariamente indisponível.",
        retryable: true,
      });
    }
    const raw = object(await response.json().catch(() => ({})));
    if (!response.ok) {
      throw new BadGatewayException({
        code: "CONTEXT_ENGINE_ERROR",
        message: "Falha ao consultar o contexto territorial.",
        retryable: response.status >= 500,
      });
    }

    const sections = (Array.isArray(raw.sections) ? raw.sections : [])
      .map((section, index) => {
        const s = object(section);
        return {
          id: String(s.id ?? `section-${index}`),
          title: String(s.title ?? "Contexto"),
          order: index,
          type: "DETAIL",
          items: humanValues(s.items),
        };
      })
      .filter((section) => section.items.length > 0);

    return {
      found: true,
      mode: "POINT_CONTEXT",
      municipality,
      analysis_area: object(raw.analysis_area),
      dossier: {
        title: `Contexto do ponto · ${municipality.name} · ${municipality.uf}`,
        sections,
      },
      unavailable_sources: Array.isArray(raw.unavailable_sources)
        ? raw.unavailable_sources.map(String)
        : [],
      queried_at: raw.queried_at ?? null,
      interpretation: raw.interpretation ?? null,
      disclaimer:
        "Contexto federal e estadual no entorno do ponto. Não identifica o " +
        "lote nem substitui consulta à prefeitura, certidões ou vistoria.",
    };
  }
}

@Controller("context")
class PointContextController {
  constructor(private readonly context: PointContextService) {}

  @Post("point")
  @HttpCode(200)
  point(@Body() body: PointContextInput) {
    return this.context.build(body);
  }
}

@Module({
  imports: [TerritoryModule],
  controllers: [PointContextController],
  providers: [PointContextService],
})
export class PointContextModule {}
