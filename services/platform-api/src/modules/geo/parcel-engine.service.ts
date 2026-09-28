import {
  BadGatewayException,
  BadRequestException,
  Injectable,
  NotFoundException,
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

type JsonObject = Record<string, unknown>;

type HumanValue = {
  label: string;
  value: unknown;
  unit?: string;
};

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : {};
}

function text(value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  return String(value);
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function humanValues(value: unknown): HumanValue[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => object(item))
    .filter(
      (item) =>
        typeof item.label === "string" &&
        item.label.trim().length > 0 &&
        item.value !== null &&
        item.value !== undefined &&
        item.value !== "",
    )
    .map((item) => ({
      label: String(item.label),
      value: item.value,
      ...(item.unit ? { unit: String(item.unit) } : {}),
    }));
}

@Injectable()
export class ParcelEngineService {
  private readonly engineBase =
    process.env.PARCEL_ENGINE_BASE_URL ?? "http://127.0.0.1:8765";

  private async resolveRaw(input: ParcelResolveInput): Promise<JsonObject> {
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

    const body = object(await response.json().catch(() => ({})));
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

  async resolve(input: ParcelResolveInput): Promise<JsonObject> {
    const raw = await this.resolveRaw(input);
    const feature = object(raw.feature);
    const properties = object(feature.properties);
    const report = object(raw.report);
    const persistence = object(raw.persistence);
    const sections = Array.isArray(report.sections) ? report.sections : [];

    const dossierSections = sections
      .map((section) => object(section))
      .map((section) => ({
        id: text(section.id) ?? "section",
        title: text(section.title) ?? "Informações",
        order: numberValue(section.order) ?? 999,
        type: text(section.section_type) ?? "DETAIL",
        items: humanValues(section.actual_values),
      }))
      .filter((section) => section.items.length > 0)
      .sort((a, b) => a.order - b.order);

    return {
      found: Boolean(raw.found),
      parcel: {
        geometry: feature.geometry ?? null,
        address: {
          street: text(properties.street),
          number: text(properties.number),
          complement: text(properties.complement),
        },
        identifiers: {
          fiscal_registration: text(properties.sql_reference),
          real_estate_code: text(properties.cib),
        },
        land_area_m2: numberValue(properties.land_area_m2),
        built_area_m2: numberValue(properties.built_area_m2),
        use: text(properties.use_description),
        cadastral_status:
          text(properties.parcel_status) ?? text(properties.cib_status),
      },
      dossier: {
        title: text(report.title) ?? "Dossiê do imóvel",
        sections: dossierSections,
      },
      analysis: {
        run_id: text(persistence.analysis_run_id),
        audit_available: Boolean(text(persistence.analysis_run_id)),
        lineage_status:
          text(persistence.lineage_status) === "SOURCE_SNAPSHOTS_COMPLETE"
            ? "Snapshots individuais por fonte"
            : "Snapshot agregado do dossiê público",
        municipality_ibge: input.municipality_ibge,
        lat: input.lat,
        lng: input.lng,
        analysis_date: input.analysis_date ?? null,
      },
    };
  }

  async evidence(analysisRunId: string): Promise<JsonObject> {
    if (
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
        analysisRunId,
      )
    ) {
      throw new BadRequestException({
        code: "INVALID_ANALYSIS_RUN_ID",
        message: "Identificador de análise inválido.",
      });
    }

    let response: Response;
    try {
      response = await fetch(
        `${this.engineBase}/v1/analysis/${encodeURIComponent(
          analysisRunId,
        )}/evidence`,
        {
          headers: { Accept: "application/json" },
          signal: AbortSignal.timeout(30_000),
        },
      );
    } catch {
      throw new BadGatewayException({
        code: "EVIDENCE_ENGINE_UNAVAILABLE",
        message: "Trilha de evidência temporariamente indisponível.",
        retryable: true,
      });
    }

    if (response.status === 404) {
      throw new NotFoundException({
        code: "ANALYSIS_RUN_NOT_FOUND",
        message: "Execução de análise não encontrada.",
      });
    }

    const body = object(await response.json().catch(() => ({})));
    if (!response.ok) {
      throw new BadGatewayException({
        code: "EVIDENCE_ENGINE_ERROR",
        message: "Falha ao consultar a trilha de evidência.",
        retryable: response.status >= 500,
      });
    }
    return body;
  }
}
