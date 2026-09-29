export type AuthMode = "oidc" | "disabled";

export type AuthConfig = {
  mode: AuthMode;
  app: "client" | "admin";
  issuer: string;
  clientId: string;
  clientSecret: string | undefined;
  baseUrl: URL;
  scopes: string;
  sessionSecret: string;
  databaseUrl: string | undefined;
  /** Hard cap on a browser session regardless of token refresh. */
  absoluteLifetimeHours: number;
  /** Only for tests against a local fake IdP; never in production. */
  allowInsecureIssuer: boolean;
};

export function authMode(): AuthMode {
  return process.env.AUTH_MODE === "disabled" ? "disabled" : "oidc";
}

export function authConfig(): AuthConfig {
  const mode = authMode();
  const baseUrl = new URL(process.env.APP_BASE_URL ?? "http://localhost:3001");
  const config: AuthConfig = {
    mode,
    app: process.env.AUTH_APP === "admin" ? "admin" : "client",
    issuer: process.env.OIDC_ISSUER ?? "",
    clientId: process.env.OIDC_CLIENT_ID ?? "",
    clientSecret: process.env.OIDC_CLIENT_SECRET,
    baseUrl,
    scopes: process.env.OIDC_SCOPES ?? "openid profile email",
    sessionSecret: process.env.SESSION_SECRET ?? "",
    databaseUrl: process.env.DATABASE_URL,
    absoluteLifetimeHours: Number(process.env.SESSION_MAX_HOURS ?? 12),
    allowInsecureIssuer: process.env.OIDC_ALLOW_INSECURE_FOR_TESTS === "true",
  };
  if (mode === "oidc") {
    const missing = [
      ["OIDC_ISSUER", config.issuer],
      ["OIDC_CLIENT_ID", config.clientId],
      ["SESSION_SECRET", config.sessionSecret],
      ["DATABASE_URL", config.databaseUrl],
    ].filter(([, v]) => !v).map(([k]) => k);
    if (missing.length) {
      throw new Error(`Autenticação OIDC sem configuração: ${missing.join(", ")}`);
    }
    if (process.env.NODE_ENV === "production" && baseUrl.protocol !== "https:"
        && !config.allowInsecureIssuer) {
      throw new Error("APP_BASE_URL deve usar https em produção");
    }
  }
  return config;
}

export function secureCookies(config: AuthConfig): boolean {
  return config.baseUrl.protocol === "https:";
}

export function sessionCookieName(config: AuthConfig): string {
  // __Host- binds the cookie to this exact origin (no Domain, Path=/, Secure).
  const base = config.app === "admin" ? "ld_admin_session" : "ld_session";
  return secureCookies(config) ? `__Host-${base}` : base;
}

export function loginStateCookieName(config: AuthConfig): string {
  const base = config.app === "admin" ? "ld_admin_oidc" : "ld_oidc";
  return secureCookies(config) ? `__Host-${base}` : base;
}
