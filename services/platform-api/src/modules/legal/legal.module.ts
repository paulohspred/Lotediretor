import {
  BadRequestException,
  Controller,
  Get,
  Injectable,
  Module,
  Query,
} from "@nestjs/common";
import { Database } from "../database/database.module.js";
import { IBGE_CODE } from "../territory/capabilities.js";

export type EffectiveRule = {
  rule_id: string;
  parameter: string;
  use_condition: string;
  value: string | null;
  unit: string;
  no_restriction: boolean;
  status: "CONFIRMED" | "CONFLICTING" | "CANDIDATE";
  valid_from: string | null;
  valid_to: string | null;
  document_title: string;
  provision_path: string;
  page_start: number | null;
  evidence_excerpt: string;
  canonical_url: string | null;
};

export const PARAMETER_LABEL: Record<string, string> = {
  CA_MINIMO: "Coeficiente de aproveitamento mínimo",
  CA_BASICO: "Coeficiente de aproveitamento básico",
  CA_MAXIMO: "Coeficiente de aproveitamento máximo",
  TO_MAXIMA: "Taxa de ocupação máxima",
  TP_MINIMA: "Taxa de permeabilidade mínima",
  GABARITO_M: "Altura máxima",
  PAVIMENTOS_MAX: "Número máximo de pavimentos",
  RECUO_FRONTAL_M: "Recuo frontal",
  RECUO_LATERAL_M: "Recuo lateral",
  RECUO_FUNDOS_M: "Recuo de fundos",
  LOTE_MINIMO_M2: "Lote mínimo",
  TESTADA_MINIMA_M: "Testada mínima",
};

const UNIT_LABEL: Record<string, string> = {
  ratio: "",
  percent: "%",
  m: "m",
  m2: "m²",
  count: "",
};

export function formatRuleValue(rule: EffectiveRule): string {
  if (rule.no_restriction) return "Sem restrição";
  const n = Number(rule.value);
  const text = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 }).format(n);
  const unit = UNIT_LABEL[rule.unit] ?? rule.unit;
  return unit === "%" ? `${text}%` : unit ? `${text} ${unit}` : text;
}

function isoDate(raw?: string): string {
  if (raw === undefined || raw === "") return new Date().toISOString().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw) || Number.isNaN(Date.parse(raw))) {
    throw new BadRequestException({
      code: "INVALID_DATE",
      message: "Use a data no formato AAAA-MM-DD.",
    });
  }
  return raw;
}

function assertIbge(ibge?: string): string {
  if (!ibge || !IBGE_CODE.test(ibge)) {
    throw new BadRequestException({
      code: "INVALID_IBGE_CODE",
      message: "Código IBGE deve ter 7 dígitos.",
    });
  }
  return ibge;
}

@Injectable()
export class LegalService {
  constructor(private readonly db: Database) {}

  async rules(ibge: string, zone: string, date?: string, includeCandidates = false) {
    assertIbge(ibge);
    if (!zone || zone.length > 40) {
      throw new BadRequestException({ code: "INVALID_ZONE", message: "Zona inválida." });
    }
    return this.db.query<EffectiveRule>(
      `SELECT rule_id, parameter, use_condition, value::text, unit, no_restriction,
              status, valid_from::text, valid_to::text, document_title,
              provision_path, page_start, evidence_excerpt, canonical_url
       FROM ld_api.effective_urban_rules($1, $2, $3::date, $4)`,
      [ibge, zone, isoDate(date), includeCandidates],
    );
  }

  async search(q: string | undefined, ibge: string | undefined, date?: string, limit = 10) {
    const query = (q ?? "").trim();
    if (query.length < 3 || query.length > 200) {
      throw new BadRequestException({
        code: "INVALID_QUERY",
        message: "Informe de 3 a 200 caracteres.",
      });
    }
    return this.db.query<{
      provision_id: string;
      document_title: string;
      document_kind: string;
      jurisdiction_level: string;
      version_label: string;
      path: string;
      page_start: number | null;
      excerpt: string;
      rank: number;
      canonical_url: string | null;
      review_status: string;
    }>(
      `SELECT * FROM ld_api.search_provisions($1, $2, $3::date, $4)`,
      [query, assertIbge(ibge), isoDate(date), Math.min(Math.max(limit, 1), 20)],
    );
  }

  async documents(ibge: string) {
    assertIbge(ibge);
    return this.db.query<{
      document_id: string;
      title: string;
      kind: string;
      number: string | null;
      subject: string[];
      canonical_url: string | null;
      text_versions: number;
    }>(
      `SELECT d.document_id, d.title, d.kind, d.number, d.subject, d.canonical_url,
              count(v.version_id) FILTER (WHERE v.text_available
                                            AND v.superseded_at IS NULL)::int AS text_versions
       FROM ld_legal.document d
       LEFT JOIN ld_legal.document_version v USING (document_id)
       WHERE d.ibge_code = $1
       GROUP BY d.document_id
       ORDER BY d.title`,
      [ibge],
    );
  }

  /** Dossier section for a zone: confirmed values first; candidates flagged. */
  async zoneParameterSection(ibge: string, zone: string) {
    const rows = await this.rules(ibge, zone, undefined, true);
    const confirmed = rows.filter((r) => r.status !== "CANDIDATE");
    const candidates = rows.filter((r) => r.status === "CANDIDATE");
    const item = (r: EffectiveRule, prefix = "") => ({
      label:
        `${prefix}${PARAMETER_LABEL[r.parameter] ?? r.parameter}` +
        (r.use_condition !== "GERAL" ? ` · ${r.use_condition}` : ""),
      value:
        `${formatRuleValue(r)} — ${r.document_title}, ${r.provision_path}` +
        (r.status === "CONFLICTING" ? " (conflito entre fontes: revisar)" : ""),
    });
    const items = [
      ...confirmed.map((r) => item(r)),
      ...candidates.map((r) => item(r, "[Aguardando revisão] ")),
    ];
    if (items.length === 0) {
      items.push({
        label: `Zona ${zone}`,
        value: "Nenhum parâmetro estruturado para esta zona ainda.",
      });
    } else if (confirmed.length === 0) {
      items.unshift({
        label: "Situação",
        value:
          "Parâmetros extraídos automaticamente do texto legal, ainda não " +
          "conferidos por um profissional. Não use para decisão.",
      });
    }
    return {
      section: {
        id: "urban_parameters",
        title: `Parâmetros urbanísticos · ${zone}`,
        order: 3,
        type: "DETAIL",
        items,
      },
      confirmed: confirmed.length,
      candidates: candidates.length,
    };
  }
}

@Controller("legal")
class LegalController {
  constructor(private readonly legal: LegalService) {}

  @Get("rules")
  rules(
    @Query("ibge") ibge: string,
    @Query("zone") zone: string,
    @Query("date") date?: string,
    @Query("include_candidates") include?: string,
  ) {
    return this.legal
      .rules(ibge, zone, date, include === "true")
      .then((rules) => ({ rules }));
  }

  @Get("search")
  search(
    @Query("q") q?: string,
    @Query("ibge") ibge?: string,
    @Query("date") date?: string,
    @Query("limit") limit?: string,
  ) {
    return this.legal
      .search(q, ibge, date, Number(limit ?? 10) || 10)
      .then((results) => ({ results }));
  }

  @Get("documents")
  documents(@Query("ibge") ibge: string) {
    return this.legal.documents(ibge).then((documents) => ({ documents }));
  }
}

@Module({
  controllers: [LegalController],
  providers: [LegalService],
  exports: [LegalService],
})
export class LegalModule {}
