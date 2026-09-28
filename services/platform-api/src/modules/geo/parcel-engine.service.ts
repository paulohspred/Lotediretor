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

export interface ParcelSearchInput {
  municipality_ibge: string;
  q: string;
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

function formattedAddress(
  street: string | null,
  number: string | null,
): string | null {
  if (!street) return null;
  if (!number) return street;
  const normalizedStreet = street.toLowerCase().replace(/\s+/g, " ");
  const normalizedNumber = number.toLowerCase().trim();
  if (
    normalizedStreet.endsWith(` ${normalizedNumber}`) ||
    normalizedStreet.includes(`, ${normalizedNumber}`)
  ) {
    return street;
  }
  return `${street}, ${number}`;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function primaryReference(
  properties: JsonObject,
  municipalityIbge: string,
): { label: string; value: string | null } {
  if (municipalityIbge === "3550308") {
    return {
      label: "Inscrição fiscal",
      value: text(properties.sql_reference),
    };
  }
  if (municipalityIbge === "2611606") {
    return {
      label: "Inscrição fiscal",
      value: text(properties.dsqfl) ?? text(properties.sql_reference),
    };
  }
  if (municipalityIbge === "3304557") {
    if (text(properties.inscricao_imobiliaria)) {
      return {
        label: "Inscrição imobiliária",
        value: text(properties.inscricao_imobiliaria),
      };
    }
    if (text(properties.rgi)) {
      return {
        label: "Referência cadastral RGI",
        value: text(properties.rgi),
      };
    }
    if (text(properties.matricula)) {
      return {
        label: "Matrícula cadastral",
        value: text(properties.matricula),
      };
    }
    return {
      label: "Referência cadastral",
      value: text(properties.sql_reference),
    };
  }
  if (municipalityIbge === "3106200") {
    return {
      label: "Identificação cadastral do lote",
      value: text(properties.ctm_number) ?? text(properties.sql_reference),
    };
  }
  if (municipalityIbge === "2507507") {
    return {
      label: "Código cartográfico",
      value: text(properties.cartographic_code) ?? text(properties.sql_reference),
    };
  }
  return {
    label: "Referência cadastral",
    value: text(properties.sql_reference),
  };
}

function friendlyLabel(raw: string): string {
  const exact: Record<string, string> = {
    "CEP": "Código postal (CEP)",
    "CA básico": "Coeficiente de aproveitamento básico",
    "CA máximo": "Coeficiente de aproveitamento máximo",
    "Planta CP": "Referência da planta cadastral (CP)",
    "Cadastro IPTU 2026":
      "Cadastro fiscal imobiliário 2026 (IPTU)",
    "Nota legal · permeabilidade x TO":
      "Nota legal · permeabilidade versus taxa de ocupação",
    "RCL ajustada para limites de endividamento · RREO 2025":
      "Receita Corrente Líquida ajustada para limites de endividamento · Relatório Resumido da Execução Orçamentária 2025",
  };
  if (exact[raw]) return exact[raw];

  return raw
    .replaceAll(
      "(ANA/IBGE)",
      "(Agência Nacional de Águas e Saneamento Básico / Instituto Brasileiro de Geografia e Estatística)",
    )
    .replaceAll(
      " · RREO 2025",
      " · Relatório Resumido da Execução Orçamentária 2025",
    )
    .replaceAll(
      "Arrecadação municipal de IPTU",
      "Arrecadação municipal do Imposto Predial e Territorial Urbano (IPTU)",
    )
    .replaceAll(
      "Arrecadação municipal de ITBI",
      "Arrecadação municipal do Imposto sobre Transmissão de Bens Imóveis (ITBI)",
    )
    .replaceAll(
      "Transações de ITBI",
      "Transações do Imposto sobre Transmissão de Bens Imóveis (ITBI)",
    )
    .replaceAll(
      "Como interpretar o histórico de ITBI",
      "Como interpretar o histórico do Imposto sobre Transmissão de Bens Imóveis (ITBI)",
    )
    .replace(
      /^ITBI #(\d+) · /,
      "Transmissão imobiliária #$1 (ITBI) · ",
    )
    .replaceAll(
      "(SGB)",
      "(Serviço Geológico do Brasil)",
    )
    .replaceAll(
      " do SGB",
      " do Serviço Geológico do Brasil",
    )
    .replace(
      /^SGB · /,
      "Serviço Geológico do Brasil · ",
    )
    .replaceAll(
      "(OSM)",
      "(OpenStreetMap)",
    );
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
      label: friendlyLabel(String(item.label)),
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

  async search(input: ParcelSearchInput): Promise<JsonObject> {
    const slug = MUNICIPALITY_SLUG[input.municipality_ibge];
    const query = input.q?.trim() ?? "";
    if (!slug) {
      throw new BadRequestException({
        code: "UNSUPPORTED_MUNICIPALITY",
        message: "Município ainda não habilitado no Parcel Resolver.",
      });
    }
    if (query.length < 3 || query.length > 80) {
      throw new BadRequestException({
        code: "INVALID_PARCEL_QUERY",
        message: "Informe uma referência cadastral válida.",
      });
    }

    let response: Response;
    try {
      const params = new URLSearchParams({ q: query });
      response = await fetch(
        `${this.engineBase}/v1/${slug}/search?${params}`,
        {
          headers: { Accept: "application/json" },
          signal: AbortSignal.timeout(30_000),
        },
      );
    } catch {
      throw new BadGatewayException({
        code: "PARCEL_SEARCH_UNAVAILABLE",
        message: "Busca cadastral temporariamente indisponível.",
        retryable: true,
      });
    }

    if (response.status === 400) {
      return { results: [] };
    }

    const raw = object(await response.json().catch(() => ({})));
    if (!response.ok) {
      throw new BadGatewayException({
        code: "PARCEL_SEARCH_ERROR",
        message: "Falha na busca cadastral.",
        retryable: response.status >= 500,
      });
    }

    const matches = Array.isArray(raw.matches) ? raw.matches : [];
    const results = matches
      .map((match) => object(match))
      .map((match) => {
        const feature = object(match.feature);
        const props = object(feature.properties);
        const point = object(match.representative_point);
        const lat = numberValue(point.lat);
        const lng = numberValue(point.lng);
        if (lat === null || lng === null) return null;

        const primary = primaryReference(
          props,
          input.municipality_ibge,
        );
        const fiscalReference =
          primary.value ??
          text(props.matricula);
        const secondaryReference =
          text(props.cib) ??
          text(props.rgi) ??
          text(props.seqimovel);
        const street =
          text(props.street) ??
          text(props.street_name) ??
          text(props.logradouro);
        const number = text(props.number);

        const address = formattedAddress(street, number);
        const reference = fiscalReference
          ? `Cadastro ${fiscalReference}`
          : secondaryReference
            ? `Referência ${secondaryReference}`
            : "Lote cadastral";

        return {
          kind: "parcel",
          display_name: address
            ? `${address} · ${primary.label} ${fiscalReference ?? ""}`.trim()
            : `${primary.label} ${fiscalReference ?? ""}`.trim(),
          lat,
          lng,
          primary_reference: {
            label: primary.label,
            value: fiscalReference,
          },
          secondary_reference: secondaryReference,
        };
      })
      .filter((item) => item !== null);

    return { results };
  }

  async resolve(input: ParcelResolveInput): Promise<JsonObject> {
    const raw = await this.resolveRaw(input);
    const feature = object(raw.feature);
    const properties = object(feature.properties);
    const report = object(raw.report);
    const persistence = object(raw.persistence);
    const primary = primaryReference(properties, input.municipality_ibge);
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
          primary,
          fiscal_registration:
            input.municipality_ibge === "3550308" ||
            input.municipality_ibge === "2611606"
              ? primary.value
              : null,
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
