import {
  Body,
  Controller,
  Delete,
  ForbiddenException,
  Get,
  Global,
  HttpCode,
  Injectable,
  Module,
  NotFoundException,
  BadRequestException,
  Param,
  Patch,
  Post,
  UseGuards,
  createParamDecorator,
  ExecutionContext,
} from "@nestjs/common";
import { Reflector } from "@nestjs/core";
import { Database } from "../database/database.module.js";
import {
  AuthGuard,
  CurrentPrincipal,
  TokenVerifier,
  type Principal,
} from "./auth.guard.js";

export type Membership = { org_id: string; name: string; kind: string; status: string; role: string };

export type Account = {
  user_id: string;
  email: string | null;
  display_name: string | null;
  roles: string[];
  mfa: boolean;
  memberships: Membership[];
  active_org: Membership;
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Maps an authenticated principal to our user and active organization.
 * First login provisions the user and a personal workspace (trial).
 */
@Injectable()
export class AccountService {
  constructor(private readonly db: Database) {}

  async account(principal: Principal, requestedOrg?: string): Promise<Account> {
    const [user] = await this.db.query<{ user_id: string; status: string }>(
      `INSERT INTO ld_app.app_user (idp_issuer, idp_subject, email, display_name, last_login_at)
       VALUES ($1, $2, $3, $4, now())
       ON CONFLICT (idp_issuer, idp_subject) DO UPDATE
         SET email = EXCLUDED.email, display_name = EXCLUDED.display_name,
             last_login_at = now()
       RETURNING user_id, status`,
      [principal.issuer, principal.subject, principal.email, principal.name],
    );
    if (user.status !== "ACTIVE") {
      throw new ForbiddenException({ code: "USER_BLOCKED", message: "Acesso bloqueado." });
    }

    let memberships = await this.memberships(user.user_id);
    if (memberships.length === 0) {
      // Serialize first-login provisioning per user so concurrent requests
      // cannot create two personal workspaces.
      await this.db.transaction(async (q) => {
        await q("SELECT pg_advisory_xact_lock(hashtext($1))", [user.user_id]);
        await q(
          `WITH org AS (
             INSERT INTO ld_app.organization (name, kind, status)
             SELECT $2, 'PERSONAL', 'TRIAL'
             WHERE NOT EXISTS (SELECT 1 FROM ld_app.membership WHERE user_id = $1)
             RETURNING org_id
           )
           INSERT INTO ld_app.membership (org_id, user_id, role)
           SELECT org_id, $1, 'OWNER' FROM org`,
          [user.user_id, `Workspace de ${principal.name ?? principal.email ?? "usuário"}`.slice(0, 160)],
        );
      });
      memberships = await this.memberships(user.user_id);
    }

    let active = memberships[0];
    if (requestedOrg) {
      const found = memberships.find((m) => m.org_id === requestedOrg);
      if (!found) {
        throw new ForbiddenException({
          code: "ORG_FORBIDDEN",
          message: "Você não participa desta organização.",
        });
      }
      active = found;
    }
    return {
      user_id: user.user_id,
      email: principal.email,
      display_name: principal.name,
      roles: principal.roles,
      mfa: principal.mfa,
      memberships,
      active_org: active,
    };
  }

  private memberships(userId: string) {
    return this.db.query<Membership>(
      `SELECT o.org_id, o.name, o.kind, o.status, m.role
       FROM ld_app.membership m JOIN ld_app.organization o USING (org_id)
       WHERE m.user_id = $1
       ORDER BY (o.kind = 'PERSONAL'), o.created_at`,
      [userId],
    );
  }
}

type RequestWithAccount = {
  headers: Record<string, string | string[] | undefined>;
  principal?: Principal;
  account?: Account;
};

/** Auth + account resolution; attaches request.account. */
@Injectable()
export class AccountGuard extends AuthGuard {
  constructor(
    verifier: TokenVerifier,
    reflector: Reflector,
    private readonly accounts: AccountService,
  ) {
    super(verifier, reflector);
  }

  async canActivate(context: ExecutionContext): Promise<boolean> {
    await super.canActivate(context);
    const request = context.switchToHttp().getRequest<RequestWithAccount>();
    const header = request.headers["x-org-id"];
    const orgId = Array.isArray(header) ? header[0] : header;
    if (orgId !== undefined && !UUID.test(orgId)) {
      throw new BadRequestException({ code: "INVALID_ORG", message: "Organização inválida." });
    }
    request.account = await this.accounts.account(request.principal!, orgId);
    return true;
  }
}

export const CurrentAccount = createParamDecorator(
  (_data: unknown, context: ExecutionContext): Account =>
    context.switchToHttp().getRequest<RequestWithAccount>().account!,
);

type PropertyInput = {
  ibge_code?: unknown;
  label?: unknown;
  lat?: unknown;
  lng?: unknown;
  parcel_reference?: unknown;
  analysis_run_id?: unknown;
  notes?: unknown;
};

function str(v: unknown, max: number): string | null {
  if (v === undefined || v === null || v === "") return null;
  if (typeof v !== "string" || v.length > max) {
    throw new BadRequestException({ code: "INVALID_FIELD", message: "Campo inválido." });
  }
  return v.trim();
}

@Controller()
@UseGuards(AccountGuard)
class AccountController {
  constructor(private readonly db: Database) {}

  @Get("me")
  me(@CurrentAccount() account: Account, @CurrentPrincipal() principal: Principal) {
    return { ...account, subject: principal.subject };
  }

  @Get("properties")
  list(@CurrentAccount() account: Account) {
    return this.db
      .withOrg(account.active_org.org_id, (q) =>
        q(
          `SELECT sp.saved_property_id, sp.ibge_code, m.name AS municipality, st.uf,
                  sp.label, sp.lat, sp.lng, sp.parcel_reference, sp.analysis_run_id,
                  sp.notes, sp.created_at, sp.updated_at
           FROM ld_app.saved_property sp
           JOIN ld_core.municipality m USING (ibge_code)
           JOIN ld_core.state st USING (uf_code)
           ORDER BY sp.created_at DESC LIMIT 500`,
        ),
      )
      .then((properties) => ({ properties }));
  }

  @Post("properties")
  create(@CurrentAccount() account: Account, @Body() body: PropertyInput) {
    if (account.active_org.role === "VIEWER") {
      throw new ForbiddenException({ code: "READ_ONLY", message: "Perfil somente leitura." });
    }
    const ibge = str(body?.ibge_code, 7);
    const label = str(body?.label, 200);
    const lat = Number(body?.lat);
    const lng = Number(body?.lng);
    if (!ibge || !/^\d{7}$/.test(ibge) || !label || !Number.isFinite(lat) || !Number.isFinite(lng)) {
      throw new BadRequestException({
        code: "INVALID_PROPERTY",
        message: "Informe município, nome e coordenadas válidas.",
      });
    }
    const runId = str(body?.analysis_run_id, 36);
    if (runId && !UUID.test(runId)) {
      throw new BadRequestException({ code: "INVALID_FIELD", message: "Análise inválida." });
    }
    return this.db.withOrg(account.active_org.org_id, async (q) => {
      const [row] = await q<{ saved_property_id: string }>(
        `INSERT INTO ld_app.saved_property
           (org_id, created_by, ibge_code, label, lat, lng, parcel_reference, analysis_run_id, notes)
         SELECT $1, $2, ibge_code, $4, $5, $6, $7, $8, $9
         FROM ld_core.municipality WHERE ibge_code = $3
         RETURNING saved_property_id`,
        [account.active_org.org_id, account.user_id, ibge, label, lat, lng,
         str(body?.parcel_reference, 120), runId, str(body?.notes, 4000)],
      );
      if (!row) {
        throw new BadRequestException({ code: "UNKNOWN_MUNICIPALITY", message: "Município desconhecido." });
      }
      await q(
        `INSERT INTO ld_app.activity_event (org_id, user_id, kind, summary, payload)
         VALUES ($1, $2, 'property.saved', $3, jsonb_build_object('saved_property_id', $4::text))`,
        [account.active_org.org_id, account.user_id, `Imóvel salvo: ${label}`, row.saved_property_id],
      );
      return row;
    });
  }

  @Patch("properties/:id")
  update(@CurrentAccount() account: Account, @Param("id") id: string, @Body() body: PropertyInput) {
    if (!UUID.test(id)) throw new NotFoundException({ code: "NOT_FOUND" });
    if (account.active_org.role === "VIEWER") {
      throw new ForbiddenException({ code: "READ_ONLY", message: "Perfil somente leitura." });
    }
    return this.db.withOrg(account.active_org.org_id, async (q) => {
      const rows = await q(
        `UPDATE ld_app.saved_property
         SET label = coalesce($2, label), notes = coalesce($3, notes), updated_at = now()
         WHERE saved_property_id = $1 RETURNING saved_property_id`,
        [id, str(body?.label, 200), str(body?.notes, 4000)],
      );
      if (!rows.length) throw new NotFoundException({ code: "NOT_FOUND", message: "Imóvel não encontrado." });
      return rows[0];
    });
  }

  @Delete("properties/:id")
  @HttpCode(204)
  async remove(@CurrentAccount() account: Account, @Param("id") id: string) {
    if (!UUID.test(id)) throw new NotFoundException({ code: "NOT_FOUND" });
    if (!["OWNER", "ADMIN", "MEMBER"].includes(account.active_org.role)) {
      throw new ForbiddenException({ code: "READ_ONLY", message: "Perfil somente leitura." });
    }
    await this.db.withOrg(account.active_org.org_id, async (q) => {
      const rows = await q(
        `DELETE FROM ld_app.saved_property WHERE saved_property_id = $1 RETURNING label`,
        [id],
      );
      if (!rows.length) throw new NotFoundException({ code: "NOT_FOUND", message: "Imóvel não encontrado." });
    });
  }

  @Get("activity")
  activity(@CurrentAccount() account: Account) {
    return this.db
      .withOrg(account.active_org.org_id, (q) =>
        q(
          `SELECT kind, summary, created_at FROM ld_app.activity_event
           ORDER BY created_at DESC LIMIT 50`,
        ),
      )
      .then((events) => ({ events }));
  }
}

@Global()
@Module({
  controllers: [AccountController],
  providers: [TokenVerifier, AccountService, AccountGuard, AuthGuard],
  exports: [TokenVerifier, AccountService, AccountGuard, AuthGuard],
})
export class AuthModule {}
