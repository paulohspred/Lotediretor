import {
  BadRequestException,
  Body,
  Controller,
  HttpCode,
  HttpException,
  Injectable,
  Module,
  Post,
  Req,
} from "@nestjs/common";
import { createHash } from "node:crypto";
import { Database } from "../database/database.module.js";

type LeadInput = {
  name?: unknown;
  email?: unknown;
  organization?: unknown;
  segment?: unknown;
  message?: unknown;
  consent_privacy?: unknown;
  source_page?: unknown;
  website?: unknown; // honeypot: humans never fill it
};

const WINDOW_MS = 60 * 60_000;
const MAX_PER_WINDOW = Number(process.env.LEADS_PER_IP_PER_HOUR ?? 5);

function field(v: unknown, min: number, max: number, name: string): string {
  if (typeof v !== "string" || v.trim().length < min || v.length > max) {
    throw new BadRequestException({ code: "INVALID_FIELD", field: name, message: `Verifique o campo ${name}.` });
  }
  return v.trim();
}

function optional(v: unknown, max: number): string | null {
  if (v === undefined || v === null || v === "") return null;
  if (typeof v !== "string" || v.length > max) throw new BadRequestException({ code: "INVALID_FIELD" });
  return v.trim();
}

@Injectable()
export class LeadService {
  private readonly hits = new Map<string, number[]>();

  constructor(private readonly db: Database) {}

  /** Daily-rotating salted hash: lets us rate-limit without storing IPs. */
  private clientHash(ip: string): string {
    const day = new Date().toISOString().slice(0, 10);
    const salt = process.env.LEAD_HASH_SALT ?? "lotediretor";
    return createHash("sha256").update(`${salt}|${day}|${ip}`).digest("hex");
  }

  async create(body: LeadInput, ip: string) {
    const hash = this.clientHash(ip);
    const now = Date.now();
    const recent = (this.hits.get(hash) ?? []).filter((t) => now - t < WINDOW_MS);
    if (recent.length >= MAX_PER_WINDOW) {
      throw new HttpException({ code: "RATE_LIMITED", message: "Muitas mensagens. Tente mais tarde." }, 429);
    }
    recent.push(now);
    this.hits.set(hash, recent);

    if (typeof body?.website === "string" && body.website.trim() !== "") {
      return { ok: true }; // bot: accept silently, store nothing
    }
    if (body?.consent_privacy !== true) {
      throw new BadRequestException({
        code: "CONSENT_REQUIRED",
        message: "É preciso concordar com a Política de Privacidade.",
      });
    }
    const email = field(body?.email, 5, 200, "e-mail");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      throw new BadRequestException({ code: "INVALID_FIELD", field: "e-mail", message: "E-mail inválido." });
    }
    await this.db.query(
      `INSERT INTO ld_app.lead
         (name, email, organization, segment, message, consent_privacy, source_page, client_hash)
       VALUES ($1, $2, $3, $4, $5, true, $6, $7)`,
      [
        field(body?.name, 2, 120, "nome"),
        email.toLowerCase(),
        optional(body?.organization, 160),
        optional(body?.segment, 60),
        field(body?.message, 5, 4000, "mensagem"),
        optional(body?.source_page, 200),
        hash,
      ],
    );
    return { ok: true };
  }
}

@Controller("public")
class PublicController {
  constructor(private readonly leads: LeadService) {}

  @Post("leads")
  @HttpCode(201)
  create(@Body() body: LeadInput, @Req() request: { ip?: string }) {
    return this.leads.create(body, request.ip ?? "unknown");
  }
}

@Module({ controllers: [PublicController], providers: [LeadService] })
export class PublicModule {}
