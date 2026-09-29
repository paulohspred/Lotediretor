import {
  BadRequestException,
  Body,
  Controller,
  Get,
  Injectable,
  Module,
  NotFoundException,
  Param,
  Patch,
  Post,
  Query,
  UseGuards,
} from "@nestjs/common";
import { Database, type TxQuery } from "../database/database.module.js";
import { AccountGuard, CurrentAccount, type Account } from "../auth/account.module.js";
import { CurrentPrincipal, RequireMfa, RequireRole, type Principal } from "../auth/auth.guard.js";

export const ADMIN_ROLE = process.env.ADMIN_ROLE ?? "platform-admin";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ORG_STATUSES = ["TRIAL", "ACTIVE", "PAST_DUE", "RESTRICTED", "SUSPENDED", "CANCELLED"];
const LEAD_STATUSES = ["NEW", "CONTACTED", "QUALIFIED", "DISCARDED"];
const DECISIONS: Record<string, string> = {
  confirm: "CONFIRMED",
  reject: "REJECTED",
  conflict: "CONFLICTING",
};

function reason(value: unknown, min = 10): string {
  if (typeof value !== "string" || value.trim().length < min || value.length > 2000) {
    throw new BadRequestException({
      code: "REASON_REQUIRED",
      message: `Descreva o motivo (mínimo ${min} caracteres).`,
    });
  }
  return value.trim();
}

function limitOf(raw: string | undefined, max = 200): number {
  return Math.min(Math.max(Number(raw ?? 50) || 50, 1), max);
}

function actorLabel(p: Principal): string {
  return [p.name, p.email].filter(Boolean).join(" · ") || p.subject;
}

@Injectable()
export class AdminService {
  constructor(private readonly db: Database) {}

  private audit(
    q: TxQuery,
    account: Account,
    principal: Principal,
    action: string,
    objectType: string,
    objectId: string,
    why: string,
    before: unknown,
    after: unknown,
  ) {
    return q(
      `INSERT INTO ld_app.audit_log
         (actor_user_id, actor_label, action, object_type, object_id, reason, before_state, after_state)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
      [account.user_id, actorLabel(principal), action, objectType, objectId, why,
       JSON.stringify(before), JSON.stringify(after)],
    );
  }

  async overview() {
    const [row] = await this.db.query<Record<string, unknown>>(`
      SELECT
        (SELECT count(*)::int FROM ld_app.organization) AS organizations,
        (SELECT jsonb_object_agg(status, n) FROM (
           SELECT status, count(*)::int n FROM ld_app.organization GROUP BY status) s) AS organizations_by_status,
        (SELECT count(*)::int FROM ld_app.app_user) AS users,
        (SELECT count(*)::int FROM ld_app.app_user WHERE last_login_at > now() - interval '30 days') AS users_active_30d,
        (SELECT count(*)::int FROM ld_core.municipality) AS municipalities,
        (SELECT count(DISTINCT ibge_code)::int FROM ld_catalog.municipal_layer_load
          WHERE role = 'parcels' AND is_current) AS municipalities_with_parcels,
        (SELECT count(*)::int FROM ld_catalog.source WHERE retired_at IS NULL) AS sources,
        (SELECT count(*)::int FROM ld_legal.document) AS legal_documents,
        (SELECT jsonb_object_agg(status, n) FROM (
           SELECT status, count(*)::int n FROM ld_legal.urban_rule
           WHERE superseded_at IS NULL GROUP BY status) r) AS rules_by_status,
        (SELECT count(*)::int FROM ld_ai.trace WHERE created_at > now() - interval '24 hours') AS ai_answers_24h,
        (SELECT jsonb_object_agg(mode, n) FROM (
           SELECT mode, count(*)::int n FROM ld_ai.trace
           WHERE created_at > now() - interval '7 days' GROUP BY mode) m) AS ai_by_mode_7d,
        (SELECT round(avg(latency_ms))::int FROM ld_ai.trace
          WHERE created_at > now() - interval '7 days' AND mode = 'LLM') AS ai_avg_latency_ms_7d,
        (SELECT coalesce(sum(input_tokens), 0)::bigint + coalesce(sum(output_tokens), 0)::bigint
           FROM ld_ai.trace WHERE created_at > now() - interval '30 days') AS ai_tokens_30d,
        (SELECT count(*)::int FROM ld_ai.trace WHERE feedback = 1) AS ai_feedback_up,
        (SELECT count(*)::int FROM ld_ai.trace WHERE feedback = -1) AS ai_feedback_down,
        (SELECT count(*)::int FROM ld_ai.trace
          WHERE 'downgraded_no_valid_citation' = ANY(validator_flags)
            AND created_at > now() - interval '7 days') AS ai_downgrades_7d,
        (SELECT count(*)::int FROM ld_app.lead WHERE status = 'NEW') AS leads_new
    `);
    return row;
  }

  organizations(q: string | undefined, limit: number) {
    return this.db.query(
      `SELECT o.org_id, o.name, o.kind, o.status, o.created_at,
              count(m.user_id)::int AS members,
              (SELECT count(*)::int FROM ld_ai.trace t
                WHERE t.org_id = o.org_id AND t.created_at > now() - interval '30 days') AS ai_30d
       FROM ld_app.organization o
       LEFT JOIN ld_app.membership m USING (org_id)
       WHERE $1::text IS NULL OR o.name ILIKE '%' || $1 || '%'
       GROUP BY o.org_id
       ORDER BY o.created_at DESC
       LIMIT $2`,
      [q?.trim() || null, limit],
    );
  }

  async setOrganizationStatus(account: Account, principal: Principal, id: string, body: { status?: unknown; reason?: unknown }) {
    if (!UUID.test(id)) throw new NotFoundException({ code: "NOT_FOUND" });
    const status = String(body?.status ?? "");
    if (!ORG_STATUSES.includes(status)) {
      throw new BadRequestException({ code: "INVALID_STATUS", message: "Situação inválida." });
    }
    const why = reason(body?.reason);
    return this.db.transaction(async (q) => {
      const [before] = await q<{ status: string; name: string }>(
        "SELECT status, name FROM ld_app.organization WHERE org_id = $1 FOR UPDATE", [id]);
      if (!before) throw new NotFoundException({ code: "NOT_FOUND", message: "Organização não encontrada." });
      await q("UPDATE ld_app.organization SET status = $2 WHERE org_id = $1", [id, status]);
      await this.audit(q, account, principal, "organization.status", "organization", id, why,
        { status: before.status }, { status });
      return { org_id: id, status };
    });
  }

  users(q: string | undefined, limit: number) {
    return this.db.query(
      `SELECT u.user_id, u.email, u.display_name, u.status, u.created_at, u.last_login_at,
              coalesce(jsonb_agg(jsonb_build_object('org', o.name, 'role', m.role))
                FILTER (WHERE o.org_id IS NOT NULL), '[]') AS memberships
       FROM ld_app.app_user u
       LEFT JOIN ld_app.membership m USING (user_id)
       LEFT JOIN ld_app.organization o USING (org_id)
       WHERE $1::text IS NULL OR u.email ILIKE '%' || $1 || '%' OR u.display_name ILIKE '%' || $1 || '%'
       GROUP BY u.user_id
       ORDER BY u.created_at DESC
       LIMIT $2`,
      [q?.trim() || null, limit],
    );
  }

  rules(ibge: string | undefined, status: string | undefined, zone: string | undefined, limit: number) {
    if (ibge && !/^\d{7}$/.test(ibge)) throw new BadRequestException({ code: "INVALID_IBGE_CODE" });
    return this.db.query(
      `SELECT r.rule_id, r.ibge_code, m.name AS municipality, r.zone_code, r.parameter,
              r.use_condition, r.value::text, r.unit, r.no_restriction, r.status,
              r.evidence_excerpt, r.extracted_by, r.reviewed_by, r.reviewed_at, r.review_note,
              p.path AS provision_path, p.page_start, d.title AS document_title, d.canonical_url,
              p.text AS provision_text
       FROM ld_legal.urban_rule r
       JOIN ld_core.municipality m USING (ibge_code)
       JOIN ld_legal.provision p USING (provision_id)
       JOIN ld_legal.document_version v USING (version_id)
       JOIN ld_legal.document d USING (document_id)
       WHERE r.superseded_at IS NULL
         AND ($1::text IS NULL OR r.ibge_code = $1)
         AND r.status = coalesce($2, 'CANDIDATE')
         AND ($3::text IS NULL OR r.zone_code = $3)
       ORDER BY m.name, r.zone_code, r.parameter, r.use_condition
       LIMIT $4`,
      [ibge || null, status || null, zone || null, limit],
    );
  }

  async reviewRule(account: Account, principal: Principal, id: string, body: { decision?: unknown; note?: unknown }) {
    if (!UUID.test(id)) throw new NotFoundException({ code: "NOT_FOUND" });
    const next = DECISIONS[String(body?.decision ?? "")];
    if (!next) throw new BadRequestException({ code: "INVALID_DECISION", message: "Decisão inválida." });
    const note = reason(body?.note);
    const reviewer = actorLabel(principal);
    return this.db.transaction(async (q) => {
      const [rule] = await q<{ status: string; value: string | null; parameter: string }>(
        "SELECT status, value::text, parameter FROM ld_legal.urban_rule WHERE rule_id = $1 FOR UPDATE",
        [id],
      );
      if (!rule) throw new NotFoundException({ code: "NOT_FOUND", message: "Regra não encontrada." });
      await q(
        `UPDATE ld_legal.urban_rule
         SET status = $2, reviewed_by = $3, reviewed_at = now(), review_note = $4
         WHERE rule_id = $1`,
        [id, next, reviewer, note],
      );
      await q(
        `INSERT INTO ld_legal.rule_review_event (rule_id, from_status, to_status, reviewer, note)
         VALUES ($1, $2, $3, $4, $5)`,
        [id, rule.status, next, reviewer, note],
      );
      await this.audit(q, account, principal, "legal.rule.review", "urban_rule", id, note,
        { status: rule.status }, { status: next });
      return { rule_id: id, status: next };
    });
  }

  aiTraces(limit: number) {
    return this.db.query(
      `SELECT t.trace_id, t.created_at, o.name AS organization, m.name AS municipality,
              t.mode, t.status, t.model, t.latency_ms, t.input_tokens, t.output_tokens,
              cardinality(t.retrieved_provisions) + cardinality(t.retrieved_rules) AS retrieved,
              cardinality(t.cited_provisions) + cardinality(t.cited_rules) AS cited,
              t.validator_flags, t.feedback, t.question_chars
       FROM ld_ai.trace t
       LEFT JOIN ld_app.organization o USING (org_id)
       LEFT JOIN ld_core.municipality m USING (ibge_code)
       ORDER BY t.created_at DESC
       LIMIT $1`,
      [limit],
    );
  }

  leads(status: string | undefined, limit: number) {
    if (status && !LEAD_STATUSES.includes(status)) throw new BadRequestException({ code: "INVALID_STATUS" });
    return this.db.query(
      `SELECT lead_id, name, email, organization, segment, message, status, source_page, created_at
       FROM ld_app.lead WHERE $1::text IS NULL OR status = $1
       ORDER BY created_at DESC LIMIT $2`,
      [status || null, limit],
    );
  }

  async setLeadStatus(account: Account, principal: Principal, id: string, body: { status?: unknown }) {
    if (!UUID.test(id)) throw new NotFoundException({ code: "NOT_FOUND" });
    const status = String(body?.status ?? "");
    if (!LEAD_STATUSES.includes(status)) throw new BadRequestException({ code: "INVALID_STATUS" });
    return this.db.transaction(async (q) => {
      const [before] = await q<{ status: string }>(
        "SELECT status FROM ld_app.lead WHERE lead_id = $1 FOR UPDATE", [id]);
      if (!before) throw new NotFoundException({ code: "NOT_FOUND" });
      await q("UPDATE ld_app.lead SET status = $2 WHERE lead_id = $1", [id, status]);
      await this.audit(q, account, principal, "lead.status", "lead", id, "Atualização de funil",
        before, { status });
      return { lead_id: id, status };
    });
  }

  auditLog(limit: number) {
    return this.db.query(
      `SELECT audit_id, created_at, actor_label, action, object_type, object_id, reason,
              before_state, after_state
       FROM ld_app.audit_log ORDER BY audit_id DESC LIMIT $1`,
      [limit],
    );
  }

  coverage() {
    return this.db.query(
      `SELECT m.ibge_code, m.name, s.uf,
              bool_or(l.role = 'parcels') AS parcels,
              bool_or(l.role = 'zoning') AS zoning,
              max(l.loaded_at) AS last_load,
              (SELECT count(*)::int FROM ld_legal.document d WHERE d.ibge_code = m.ibge_code) AS legal_documents,
              (SELECT count(*)::int FROM ld_legal.urban_rule r
                WHERE r.ibge_code = m.ibge_code AND r.status = 'CONFIRMED') AS confirmed_rules
       FROM ld_core.municipality m
       JOIN ld_core.state s USING (uf_code)
       LEFT JOIN ld_catalog.municipal_layer_load l ON l.ibge_code = m.ibge_code AND l.is_current
       WHERE l.ibge_code IS NOT NULL
          OR EXISTS (SELECT 1 FROM ld_legal.document d WHERE d.ibge_code = m.ibge_code)
       GROUP BY m.ibge_code, m.name, s.uf
       ORDER BY m.name`,
    );
  }
}

@Controller("admin")
@UseGuards(AccountGuard)
@RequireRole(ADMIN_ROLE)
@RequireMfa()
class AdminController {
  constructor(private readonly admin: AdminService) {}

  @Get("overview")
  overview() {
    return this.admin.overview();
  }

  @Get("organizations")
  organizations(@Query("q") q?: string, @Query("limit") limit?: string) {
    return this.admin.organizations(q, limitOf(limit)).then((items) => ({ items }));
  }

  @Patch("organizations/:id")
  setOrgStatus(
    @CurrentAccount() account: Account,
    @CurrentPrincipal() principal: Principal,
    @Param("id") id: string,
    @Body() body: { status?: unknown; reason?: unknown },
  ) {
    return this.admin.setOrganizationStatus(account, principal, id, body);
  }

  @Get("users")
  users(@Query("q") q?: string, @Query("limit") limit?: string) {
    return this.admin.users(q, limitOf(limit)).then((items) => ({ items }));
  }

  @Get("rules")
  rules(
    @Query("ibge") ibge?: string,
    @Query("status") status?: string,
    @Query("zone") zone?: string,
    @Query("limit") limit?: string,
  ) {
    if (status && !["CANDIDATE", "CONFIRMED", "CONFLICTING", "REJECTED"].includes(status)) {
      throw new BadRequestException({ code: "INVALID_STATUS" });
    }
    return this.admin.rules(ibge, status, zone, limitOf(limit, 500)).then((items) => ({ items }));
  }

  @Post("rules/:id/review")
  review(
    @CurrentAccount() account: Account,
    @CurrentPrincipal() principal: Principal,
    @Param("id") id: string,
    @Body() body: { decision?: unknown; note?: unknown },
  ) {
    return this.admin.reviewRule(account, principal, id, body);
  }

  @Get("ai/traces")
  traces(@Query("limit") limit?: string) {
    return this.admin.aiTraces(limitOf(limit)).then((items) => ({ items }));
  }

  @Get("leads")
  leads(@Query("status") status?: string, @Query("limit") limit?: string) {
    return this.admin.leads(status, limitOf(limit)).then((items) => ({ items }));
  }

  @Patch("leads/:id")
  setLead(
    @CurrentAccount() account: Account,
    @CurrentPrincipal() principal: Principal,
    @Param("id") id: string,
    @Body() body: { status?: unknown },
  ) {
    return this.admin.setLeadStatus(account, principal, id, body);
  }

  @Get("audit")
  audit(@Query("limit") limit?: string) {
    return this.admin.auditLog(limitOf(limit)).then((items) => ({ items }));
  }

  @Get("coverage")
  coverage() {
    return this.admin.coverage().then((items) => ({ items }));
  }
}

@Module({
  controllers: [AdminController],
  providers: [AdminService],
})
export class AdminModule {}
