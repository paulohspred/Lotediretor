import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
  SetMetadata,
  UnauthorizedException,
  createParamDecorator,
} from "@nestjs/common";
import { Reflector } from "@nestjs/core";
import { createRemoteJWKSet, jwtVerify, type JWTPayload } from "jose";

export type Principal = {
  issuer: string;
  subject: string;
  email: string | null;
  name: string | null;
  roles: string[];
  mfa: boolean;
  claims: JWTPayload;
};

export type AuthConfig = {
  issuer: string;
  audience: string;
  jwksUrl?: string;
  mfaAmr: string[];
  mfaAcr: string[];
};

export function authConfigFromEnv(): AuthConfig | null {
  const issuer = process.env.OIDC_ISSUER;
  const audience = process.env.OIDC_AUDIENCE;
  if (!issuer || !audience) return null;
  const list = (v: string | undefined, d: string) =>
    (v ?? d).split(",").map((s) => s.trim()).filter(Boolean);
  return {
    issuer,
    audience,
    jwksUrl: process.env.OIDC_JWKS_URL,
    mfaAmr: list(process.env.OIDC_MFA_AMR, "otp,totp,webauthn,hwk,mfa"),
    mfaAcr: list(process.env.OIDC_MFA_ACR, "mfa,2,urn:lotediretor:mfa"),
  };
}

type Jwks = ReturnType<typeof createRemoteJWKSet>;

@Injectable()
export class TokenVerifier {
  private readonly config = authConfigFromEnv();
  private jwks: Jwks | null = null;

  get configured(): boolean {
    return this.config !== null;
  }

  private async keySet(): Promise<Jwks> {
    if (this.jwks) return this.jwks;
    const config = this.config!;
    let url = config.jwksUrl;
    if (!url) {
      const response = await fetch(
        `${config.issuer.replace(/\/$/, "")}/.well-known/openid-configuration`,
        { signal: AbortSignal.timeout(5_000) },
      );
      if (!response.ok) throw new Error("OIDC discovery failed");
      url = ((await response.json()) as { jwks_uri: string }).jwks_uri;
    }
    this.jwks = createRemoteJWKSet(new URL(url), {
      cooldownDuration: 30_000,
      cacheMaxAge: 10 * 60_000,
    });
    return this.jwks;
  }

  async verify(token: string): Promise<Principal> {
    if (!this.config) {
      throw new UnauthorizedException({
        code: "AUTH_NOT_CONFIGURED",
        message: "Autenticação não configurada.",
      });
    }
    let payload: JWTPayload;
    try {
      ({ payload } = await jwtVerify(token, await this.keySet(), {
        issuer: this.config.issuer,
        audience: this.config.audience,
        algorithms: ["RS256", "PS256", "ES256"],
        clockTolerance: 30,
        requiredClaims: ["sub", "exp", "iat"],
      }));
    } catch {
      throw new UnauthorizedException({
        code: "INVALID_TOKEN",
        message: "Sessão inválida ou expirada.",
      });
    }
    const realmRoles = ((payload.realm_access as { roles?: string[] } | undefined)?.roles ?? []);
    const clientRoles =
      ((payload.resource_access as Record<string, { roles?: string[] }> | undefined)?.[
        this.config.audience
      ]?.roles ?? []);
    const amr = Array.isArray(payload.amr) ? (payload.amr as string[]) : [];
    const acr = typeof payload.acr === "string" ? payload.acr : "";
    return {
      issuer: String(payload.iss),
      subject: String(payload.sub),
      email: typeof payload.email === "string" ? payload.email : null,
      name:
        typeof payload.name === "string"
          ? payload.name
          : typeof payload.preferred_username === "string"
            ? payload.preferred_username
            : null,
      roles: [...new Set([...realmRoles, ...clientRoles])],
      mfa:
        amr.some((m) => this.config!.mfaAmr.includes(m)) ||
        this.config.mfaAcr.includes(acr),
      claims: payload,
    };
  }
}

export const ROLES_KEY = "ld:roles";
export const MFA_KEY = "ld:mfa";
/** Require one of the IdP roles (realm or API client roles). */
export const RequireRole = (...roles: string[]) => SetMetadata(ROLES_KEY, roles);
/** Require a token issued after multi-factor authentication. */
export const RequireMfa = () => SetMetadata(MFA_KEY, true);

type RequestWithPrincipal = {
  headers: Record<string, string | string[] | undefined>;
  principal?: Principal;
};

@Injectable()
export class AuthGuard implements CanActivate {
  constructor(
    private readonly verifier: TokenVerifier,
    private readonly reflector: Reflector,
  ) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest<RequestWithPrincipal>();
    const header = request.headers.authorization;
    const value = Array.isArray(header) ? header[0] : header;
    const match = value?.match(/^Bearer\s+([A-Za-z0-9._~+/=-]+)$/);
    if (!match) {
      throw new UnauthorizedException({
        code: "AUTH_REQUIRED",
        message: "Faça login para continuar.",
      });
    }
    const principal = await this.verifier.verify(match[1]);
    const targets = [context.getHandler(), context.getClass()];
    const roles = this.reflector.getAllAndOverride<string[]>(ROLES_KEY, targets);
    if (roles?.length && !roles.some((role) => principal.roles.includes(role))) {
      throw new ForbiddenException({
        code: "FORBIDDEN",
        message: "Seu perfil não tem acesso a esta área.",
      });
    }
    if (this.reflector.getAllAndOverride<boolean>(MFA_KEY, targets) && !principal.mfa) {
      throw new ForbiddenException({
        code: "MFA_REQUIRED",
        message: "Esta área exige autenticação em dois fatores.",
      });
    }
    request.principal = principal;
    return true;
  }
}

export const CurrentPrincipal = createParamDecorator(
  (_data: unknown, context: ExecutionContext): Principal => {
    const request = context.switchToHttp().getRequest<RequestWithPrincipal>();
    return request.principal!;
  },
);
