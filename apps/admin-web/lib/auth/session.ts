import "server-only";
import pg from "pg";
import { cookies } from "next/headers";
import { authConfig, sessionCookieName, secureCookies, type AuthConfig } from "./config";
import { keyFromSecret, newSessionId, open, seal, sessionHash } from "./crypto";
import { refresh } from "./oidc";

type StoredTokens = {
  access_token: string;
  refresh_token?: string;
  id_token?: string;
  subject: string;
  name: string | null;
  email: string | null;
};

export type Session = {
  hash: string;
  accessToken: string;
  idToken?: string;
  subject: string;
  name: string | null;
  email: string | null;
};

const globalPool = globalThis as unknown as { __ldPool?: pg.Pool };

function pool(config: AuthConfig): pg.Pool {
  if (!globalPool.__ldPool) {
    globalPool.__ldPool = new pg.Pool({
      connectionString: config.databaseUrl,
      max: 5,
      statement_timeout: 5_000,
      application_name: `lotediretor-${config.app}-bff`,
    });
  }
  return globalPool.__ldPool;
}

const REFRESH_MARGIN_MS = 60_000;

export async function createSession(tokens: {
  access_token: string;
  refresh_token?: string;
  id_token?: string;
  expiresIn: () => number | undefined;
  claims: () => Record<string, unknown> | undefined;
}): Promise<{ id: string; maxAgeSeconds: number }> {
  const config = authConfig();
  const claims = tokens.claims() ?? {};
  const stored: StoredTokens = {
    access_token: tokens.access_token,
    refresh_token: tokens.refresh_token,
    id_token: tokens.id_token,
    subject: String(claims.sub ?? ""),
    name: typeof claims.name === "string" ? claims.name : null,
    email: typeof claims.email === "string" ? claims.email : null,
  };
  const id = newSessionId();
  const hash = sessionHash(id);
  const maxAgeSeconds = Math.round(config.absoluteLifetimeHours * 3600);
  const key = keyFromSecret(config.sessionSecret);
  await pool(config).query(
    `INSERT INTO ld_app.web_session
       (session_hash, app, token_ciphertext, access_expires_at, absolute_expires_at)
     VALUES ($1, $2, $3, now() + make_interval(secs => $4), now() + make_interval(secs => $5))`,
    [hash, config.app, seal(key, stored, hash), tokens.expiresIn() ?? 300, maxAgeSeconds],
  );
  return { id, maxAgeSeconds };
}

/** Current session from the cookie; refreshes the access token if needed. */
export async function getSession(): Promise<Session | null> {
  const config = authConfig();
  if (config.mode !== "oidc") return null;
  const id = (await cookies()).get(sessionCookieName(config))?.value;
  if (!id || id.length > 100) return null;
  const hash = sessionHash(id);
  const db = pool(config);
  const { rows } = await db.query<{
    token_ciphertext: Buffer;
    access_expires_at: Date;
  }>(
    `UPDATE ld_app.web_session SET last_seen_at = now()
     WHERE session_hash = $1 AND app = $2 AND revoked_at IS NULL
       AND absolute_expires_at > now()
     RETURNING token_ciphertext, access_expires_at`,
    [hash, config.app],
  );
  if (!rows.length) return null;
  const key = keyFromSecret(config.sessionSecret);
  let stored = open<StoredTokens>(key, rows[0].token_ciphertext, hash);
  if (!stored) return null;

  if (rows[0].access_expires_at.getTime() - Date.now() < REFRESH_MARGIN_MS) {
    if (!stored.refresh_token) return null;
    try {
      const next = await refresh(stored.refresh_token);
      stored = {
        ...stored,
        access_token: next.access_token,
        refresh_token: next.refresh_token ?? stored.refresh_token,
        id_token: next.id_token ?? stored.id_token,
      };
      await db.query(
        `UPDATE ld_app.web_session
         SET token_ciphertext = $2, access_expires_at = now() + make_interval(secs => $3)
         WHERE session_hash = $1`,
        [hash, seal(key, stored, hash), next.expiresIn() ?? 300],
      );
    } catch {
      // Refresh token revoked/expired at the IdP: end the session.
      await revokeSession(hash);
      return null;
    }
  }
  return {
    hash,
    accessToken: stored.access_token,
    idToken: stored.id_token,
    subject: stored.subject,
    name: stored.name,
    email: stored.email,
  };
}

export async function revokeSession(hash: string): Promise<void> {
  const config = authConfig();
  await pool(config).query(
    `UPDATE ld_app.web_session SET revoked_at = now(), token_ciphertext = '\\x00'
     WHERE session_hash = $1 AND revoked_at IS NULL`,
    [hash],
  );
}

export function sessionCookieOptions(maxAgeSeconds: number) {
  const config = authConfig();
  return {
    name: sessionCookieName(config),
    httpOnly: true,
    secure: secureCookies(config),
    sameSite: "lax" as const,
    path: "/",
    maxAge: maxAgeSeconds,
  };
}
