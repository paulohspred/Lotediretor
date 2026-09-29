import {
  BadRequestException,
  Controller,
  Get,
  Injectable,
  Module,
  NotFoundException,
  Param,
  Query,
} from "@nestjs/common";
import { Database } from "../database/database.module.js";
import { IBGE_CODE, parcelResolverAvailable } from "./capabilities.js";

type MunicipalityRow = {
  ibge_code: string;
  name: string;
  uf: string;
  state_name: string;
  area_km2: string | null;
  mesh_edition: string;
  bbox: [number, number, number, number] | null;
};

type SourceRow = {
  source_id: string;
  coverage_level: string;
  authority: string;
  source_type: string;
  access_class: string;
  verification_status: string;
  canonical_url: string | null;
  domains: string[];
};

const LEVEL_ORDER = ["MUNICIPAL", "SUBMUNICIPAL", "STATE", "NATIONAL"];

function parseCoordinate(raw: string | undefined, max: number): number | null {
  if (raw === undefined || raw.trim() === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) && Math.abs(value) <= max ? value : null;
}

function assertIbge(ibge: string): void {
  if (!IBGE_CODE.test(ibge)) {
    throw new BadRequestException({
      code: "INVALID_IBGE_CODE",
      message: "Código IBGE deve ter 7 dígitos.",
    });
  }
}

@Injectable()
export class TerritoryService {
  constructor(private readonly db: Database) {}

  private readonly baseSelect = `
    SELECT m.ibge_code, m.name, s.uf, s.name AS state_name,
           m.area_km2::text AS area_km2, m.mesh_edition,
           ARRAY[ST_XMin(m.geom), ST_YMin(m.geom),
                 ST_XMax(m.geom), ST_YMax(m.geom)] AS bbox
    FROM ld_core.municipality m
    JOIN ld_core.state s USING (uf_code)`;

  private present(row: MunicipalityRow) {
    return {
      ibge_code: row.ibge_code,
      name: row.name,
      uf: row.uf,
      state_name: row.state_name,
      area_km2: row.area_km2 === null ? null : Number(row.area_km2),
      bbox: row.bbox,
      mesh_edition: row.mesh_edition,
      capabilities: {
        parcel_resolver: parcelResolverAvailable(row.ibge_code),
        federal_context: true,
      },
    };
  }

  async resolve(latRaw?: string, lngRaw?: string) {
    const lat = parseCoordinate(latRaw, 90);
    const lng = parseCoordinate(lngRaw, 180);
    if (lat === null || lng === null) {
      throw new BadRequestException({
        code: "INVALID_COORDINATE",
        message: "Latitude e longitude válidas são obrigatórias.",
      });
    }
    const rows = await this.db.query<MunicipalityRow>(
      `${this.baseSelect}
       WHERE m.ibge_code = (
         SELECT ibge_code FROM ld_api.resolve_municipality($1, $2)
       )`,
      [lng, lat],
    );
    if (rows.length === 0) {
      throw new NotFoundException({
        code: "MUNICIPALITY_NOT_FOUND",
        message: "O ponto não está dentro de um município brasileiro.",
      });
    }
    return this.present(rows[0]);
  }

  async search(qRaw?: string, ufRaw?: string, limitRaw?: string) {
    const q = (qRaw ?? "").trim();
    if (q.length < 2 || q.length > 80) {
      throw new BadRequestException({
        code: "INVALID_QUERY",
        message: "Informe de 2 a 80 caracteres.",
      });
    }
    const uf = ufRaw?.trim().toUpperCase() || null;
    if (uf !== null && !/^[A-Z]{2}$/.test(uf)) {
      throw new BadRequestException({
        code: "INVALID_UF",
        message: "UF inválida.",
      });
    }
    const limit = Math.min(Math.max(Number(limitRaw ?? 10) || 10, 1), 25);
    // Prefix matches first, then substring; escaped for LIKE.
    const rows = await this.db.query<MunicipalityRow>(
      `WITH k AS (
         SELECT replace(replace(replace(ld_api.search_key($1),
                '\\', '\\\\'), '%', '\\%'), '_', '\\_') AS key
       )
       ${this.baseSelect}, k
       WHERE m.name_search LIKE '%' || k.key || '%'
         AND ($2::text IS NULL OR s.uf = $2)
       ORDER BY (m.name_search LIKE k.key || '%') DESC,
                length(m.name), m.name, s.uf
       LIMIT $3`,
      [q, uf, limit],
    );
    return { results: rows.map((row) => this.present(row)) };
  }

  async detail(ibge: string) {
    assertIbge(ibge);
    const rows = await this.db.query<MunicipalityRow>(
      `${this.baseSelect} WHERE m.ibge_code = $1`,
      [ibge],
    );
    if (rows.length === 0) {
      throw new NotFoundException({
        code: "MUNICIPALITY_NOT_FOUND",
        message: "Município não encontrado na malha do IBGE.",
      });
    }
    return this.present(rows[0]);
  }

  async coverage(ibge: string) {
    const municipality = await this.detail(ibge);
    const sources = await this.db.query<SourceRow>(
      `SELECT source_id, coverage_level, authority, source_type, access_class,
              verification_status, canonical_url, domains
       FROM ld_api.municipality_source
       WHERE ibge_code = $1
       ORDER BY coverage_level, authority, source_id`,
      [ibge],
    );

    const domains = new Map<string, Set<string>>();
    for (const source of sources) {
      for (const domain of source.domains) {
        if (!domains.has(domain)) domains.set(domain, new Set());
        domains.get(domain)!.add(source.coverage_level);
      }
    }

    return {
      municipality,
      summary: {
        total_sources: sources.length,
        by_level: Object.fromEntries(
          LEVEL_ORDER.map((level) => [
            level,
            sources.filter((s) => s.coverage_level === level).length,
          ]),
        ),
        municipal_sources_catalogued: sources.some(
          (s) => s.coverage_level === "MUNICIPAL",
        ),
        domains: Object.fromEntries(
          [...domains.entries()]
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([domain, levels]) => [domain, [...levels].sort()]),
        ),
      },
      sources: sources.sort(
        (a, b) =>
          LEVEL_ORDER.indexOf(a.coverage_level) -
          LEVEL_ORDER.indexOf(b.coverage_level),
      ),
      disclaimer:
        "Catálogo de fontes conhecidas. A presença de uma fonte não garante " +
        "que o dado exista para um imóvel específico.",
    };
  }
}

@Controller("municipalities")
class TerritoryController {
  constructor(private readonly territory: TerritoryService) {}

  // Declared before ":ibge" so "resolve" is not captured as a code.
  @Get("resolve")
  resolve(@Query("lat") lat?: string, @Query("lng") lng?: string) {
    return this.territory.resolve(lat, lng);
  }

  @Get()
  search(
    @Query("q") q?: string,
    @Query("uf") uf?: string,
    @Query("limit") limit?: string,
  ) {
    return this.territory.search(q, uf, limit);
  }

  @Get(":ibge")
  detail(@Param("ibge") ibge: string) {
    return this.territory.detail(ibge);
  }

  @Get(":ibge/coverage")
  coverage(@Param("ibge") ibge: string) {
    return this.territory.coverage(ibge);
  }
}

@Module({
  controllers: [TerritoryController],
  providers: [TerritoryService],
  exports: [TerritoryService],
})
export class TerritoryModule {}
