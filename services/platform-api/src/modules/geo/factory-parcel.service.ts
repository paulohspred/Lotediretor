import { BadRequestException, Injectable } from "@nestjs/common";
import { Database } from "../database/database.module.js";
import { PointContextService } from "../context/point-context.module.js";
import { LegalService } from "../legal/legal.module.js";

type ParcelRow = {
  upstream_key: string;
  fiscal_reference: string | null;
  street: string | null;
  house_number: string | null;
  neighborhood: string | null;
  land_area_m2: string | null;
  attributes: Record<string, unknown>;
  geometry: unknown;
  computed_area_m2: string;
  source_id: string;
  authority: string;
  license: string | null;
  captured_at: string;
  snapshot_id: string;
  feature_count: number;
};

type ZoneRow = {
  zone_code: string;
  zone_name: string | null;
  overlap_ratio: number;
  authority: string;
  captured_at: string;
};

const LOAD_META = `
  JOIN ld_catalog.municipal_layer_load l USING (load_id)
  JOIN ld_catalog.snapshot sn ON sn.snapshot_id = l.snapshot_id
  JOIN ld_catalog.source src ON src.source_id = l.source_id`;

const RESTRICTION_THEME_LABELS: Record<string, string> = {
  INDIGENOUS_LAND: "Terra indígena",
  CONSERVATION_UNIT: "Unidade de conservação",
  MINING_PROCESS: "Processo minerário",
  HYDROGRAPHY: "Hidrografia",
  HYDROGRAPHIC_BASIN: "Bacia hidrográfica",
  DEFORESTATION: "PRODES/DETER",
  TRANSMISSION_LINE: "Linha de transmissão",
  SUBSTATION: "Subestação",
  CULTURAL_HERITAGE: "Patrimônio cultural",
  GEOLOGY: "Geologia",
  GEOLOGICAL_RISK: "Risco geológico",
};

function pct(ratio: number): string {
  return `${Math.round(ratio * 1000) / 10}%`.replace(".", ",");
}

function dateBr(iso: string): string {
  return new Date(iso).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
}

/**
 * Parcel resolution for municipalities onboarded through the factory
 * (data/connectors/municipal/*.json → ld_domain.municipal_parcel). Answers
 * from PostGIS only; no live calls to municipal servers on the request path.
 */
@Injectable()
export class FactoryParcelService {
  constructor(
    private readonly db: Database,
    private readonly pointContext: PointContextService,
    private readonly legal: LegalService,
  ) {}

  async hasParcels(ibge: string): Promise<boolean> {
    if (!this.db.available) return false;
    const rows = await this.db.query<{ ok: boolean }>(
      `SELECT EXISTS (
         SELECT 1 FROM ld_catalog.municipal_layer_load
         WHERE ibge_code = $1 AND role = 'parcels' AND is_current
       ) AS ok`,
      [ibge],
    );
    return Boolean(rows[0]?.ok);
  }

  async search(ibge: string, q: string) {
    if (!(await this.hasParcels(ibge))) return null;
    const rows = await this.db.query<{
      fiscal_reference: string | null;
      street: string | null;
      house_number: string | null;
      lat: number;
      lng: number;
    }>(
      `WITH k AS (
         SELECT replace(replace(replace(ld_api.search_key($2),
                '\\', '\\\\'), '%', '\\%'), '_', '\\_') AS key
       )
       SELECT p.fiscal_reference, p.street, p.house_number,
              ST_Y(ST_PointOnSurface(p.geom)) AS lat,
              ST_X(ST_PointOnSurface(p.geom)) AS lng
       FROM ld_domain.municipal_parcel p
       JOIN ld_catalog.municipal_layer_load l USING (load_id), k
       WHERE l.is_current AND p.ibge_code = $1
         AND (ld_api.search_key(p.fiscal_reference) LIKE k.key || '%'
              OR ld_api.search_key(coalesce(p.street, '') || ' ' ||
                                   coalesce(p.house_number, '')) LIKE '%' || k.key || '%')
       ORDER BY p.fiscal_reference NULLS LAST
       LIMIT 10`,
      [ibge, q],
    );
    return {
      results: rows.map((row) => {
        const address = row.street
          ? `${row.street}${row.house_number ? `, ${row.house_number}` : ""}`
          : null;
        return {
          kind: "parcel",
          display_name: [address, row.fiscal_reference && `Cadastro ${row.fiscal_reference}`]
            .filter(Boolean)
            .join(" · "),
          lat: row.lat,
          lng: row.lng,
          primary_reference: { label: "Referência cadastral", value: row.fiscal_reference },
          secondary_reference: null,
          matched_by: null,
        };
      }),
    };
  }

  async resolve(ibge: string, lat: number, lng: number) {
    if (!(await this.hasParcels(ibge))) {
      throw new BadRequestException({
        code: "UNSUPPORTED_MUNICIPALITY",
        message: "Município ainda não habilitado no Parcel Resolver.",
      });
    }

    const parcels = await this.db.query<ParcelRow>(
      `SELECT p.upstream_key, p.fiscal_reference, p.street, p.house_number,
              p.neighborhood, p.land_area_m2::text, p.attributes,
              ST_AsGeoJSON(p.geom)::json AS geometry,
              round(ST_Area(p.geom::geography)::numeric, 2)::text AS computed_area_m2,
              src.source_id, src.authority, src.license, sn.captured_at,
              sn.snapshot_id, l.feature_count
       FROM ld_api.municipal_parcel_at($1, $2, $3) p
       ${LOAD_META}`,
      [ibge, lng, lat],
    );
    if (parcels.length === 0) {
      return { found: false, parcel: null, dossier: null };
    }
    const parcel = parcels[0];

    const zones = await this.db.query<ZoneRow>(
      `SELECT z.zone_code, z.zone_name, z.overlap_ratio,
              src.authority, sn.captured_at
       FROM ld_api.municipal_zones_for(
              $1,
              (SELECT geom FROM ld_api.municipal_parcel_at($1, $2, $3))
            ) z
       ${LOAD_META}`,
      [ibge, lng, lat],
    );

    // Federal context is complementary: its failure must not hide the parcel.
    let federal: { sections: unknown[]; unavailable: string[] } = {
      sections: [],
      unavailable: [],
    };
    try {
      const context = await this.pointContext.build({ lat, lng });
      federal = {
        sections: context.dossier.sections,
        unavailable: context.unavailable_sources,
      };
    } catch {
      federal.unavailable = ["Contexto federal (indisponível nesta consulta)"];
    }

    const restrictionRows = await this.db.query<{
      layer_key: string;
      theme: string;
      authority: string;
      source_url: string;
      source_updated_at: string | null;
      loaded_at: string | null;
      upstream_key: string;
      label: string | null;
      category: string | null;
      intersects: boolean;
      distance_m: number;
    }>(
      `SELECT layer_key, theme, authority, source_url, source_updated_at, loaded_at,
              upstream_key, label, category, intersects, distance_m
       FROM ld_api.restrictions_for_geometry(
         ST_SetSRID(ST_GeomFromGeoJSON($1), 4674), 5000
       )`,
      [JSON.stringify(parcel.geometry)],
    );
    const restrictionItems = restrictionRows.map((r) => ({
      label: [
        RESTRICTION_THEME_LABELS[r.theme] ?? r.theme,
        r.label ?? r.upstream_key,
        r.category,
      ].filter(Boolean).join(" · "),
      value:
        `${r.intersects ? "Intersecta o lote" : `A ${Math.round(Number(r.distance_m) * 10) / 10} m do lote`}. ` +
        `Fonte: ${r.authority}. Carga: ${r.loaded_at ? dateBr(r.loaded_at) : "não informada"}` +
        (r.source_updated_at ? `. Atualização da fonte: ${dateBr(r.source_updated_at)}` : ""),
    }));
    const federalSections = (federal.sections as Array<Record<string, unknown>>)
      .filter((section) => section.id !== "restrictions");
    if (restrictionItems.length === 0) {
      const [state] = await this.db.query<{ active: number; unavailable: number }>(
        `SELECT count(*) FILTER (WHERE status = 'ACTIVE')::int AS active,
                count(*) FILTER (WHERE status <> 'ACTIVE')::int AS unavailable
         FROM ld_core.restriction_layer`,
      );
      restrictionItems.push({
        label: "Restrições nacionais",
        value: Number(state?.unavailable ?? 0) > 0
          ? "Sem conclusão completa: há camadas nacionais ainda não carregadas ou indisponíveis."
          : Number(state?.active ?? 0) > 0
            ? "Nenhuma feição das camadas nacionais ativas foi encontrada até 5 km do lote."
            : "Camadas nacionais ainda não carregadas.",
      });
    }
    federalSections.unshift({
      id: "restrictions",
      title: "Restrições nacionais",
      type: "DETAIL",
      items: restrictionItems,
    });

    const declared = parcel.land_area_m2 === null ? null : Number(parcel.land_area_m2);
    const computed = Number(parcel.computed_area_m2);
    const identity = [
      { label: "Referência cadastral", value: parcel.fiscal_reference },
      { label: "Identificador na camada municipal", value: parcel.upstream_key },
      { label: "Bairro", value: parcel.neighborhood },
      { label: "Área do terreno (cadastro municipal)", value: declared, unit: "m²" },
      { label: "Área calculada da geometria (geodésica)", value: computed, unit: "m²" },
      ...Object.entries(parcel.attributes ?? {}).map(([k, v]) => ({
        label: `Atributo municipal · ${k}`,
        value: v,
      })),
    ].filter((item) => item.value !== null && item.value !== undefined && item.value !== "");

    const zoning = zones.length
      ? zones.map((z) => ({
          label: z.zone_name ? `${z.zone_code} · ${z.zone_name}` : z.zone_code,
          value: `${pct(z.overlap_ratio)} do lote`,
        }))
      : [{ label: "Zoneamento", value: "Nenhuma zona da camada municipal intersecta o lote" }];

    const parameters = zones[0]
      ? await this.legal.zoneParameterSection(ibge, zones[0].zone_code)
      : null;

    const provenance = [
      {
        label: "Lote · fonte",
        value: `${parcel.authority} (camada capturada em ${dateBr(parcel.captured_at)})`,
      },
      { label: "Lote · licença", value: parcel.license ?? "Não informada pela fonte" },
      ...(zones[0]
        ? [{
            label: "Zoneamento · fonte",
            value: `${zones[0].authority} (capturado em ${dateBr(zones[0].captured_at)})`,
          }]
        : []),
      {
        label: "Parâmetros urbanísticos (CA, TO, recuos)",
        value: !parameters
          ? "Sem zona identificada: parâmetros não aplicáveis"
          : parameters.confirmed > 0
            ? `${parameters.confirmed} parâmetro(s) conferido(s) por profissional`
            : parameters.candidates > 0
              ? "Somente parâmetros extraídos automaticamente, aguardando revisão"
              : "Legislação da zona ainda não estruturada",
      },
    ];

    return {
      found: true,
      parcel: {
        geometry: parcel.geometry,
        address: {
          street: parcel.street,
          number: parcel.house_number,
          complement: null,
        },
        identifiers: {
          primary: { label: "Referência cadastral", value: parcel.fiscal_reference },
          fiscal_registration: parcel.fiscal_reference,
          real_estate_code: null,
        },
        land_area_m2: declared ?? computed,
        built_area_m2: null,
        use: null,
        cadastral_status: null,
      },
      dossier: {
        title: "Dossiê do imóvel",
        sections: [
          { id: "identity", title: "Identificação cadastral", order: 1, type: "DETAIL", items: identity },
          { id: "zoning", title: "Zoneamento municipal", order: 2, type: "DETAIL", items: zoning },
          ...(parameters ? [parameters.section] : []),
          ...federalSections.map((s, i) => ({ ...s, order: 10 + i })),
          { id: "provenance", title: "Fontes e limitações", order: 99, type: "DETAIL", items: provenance },
        ],
      },
      unavailable_sources: federal.unavailable,
      analysis: {
        run_id: null,
        audit_available: false,
        persistence_status: "not_persisted",
        audit_warning: null,
        lineage_status: `Snapshot ${parcel.snapshot_id} da camada municipal`,
        municipality_ibge: ibge,
        lat,
        lng,
        analysis_date: new Date().toISOString().slice(0, 10),
      },
    };
  }
}
