// End-to-end OIDC login flow through the real BFF (Next.js) and platform API,
// against a fake OpenID provider. Requires:
//   - apps/client-web built (`npm run build`)
//   - services/platform-api built
//   - TEST_DATABASE_URL (least-privilege runtime role) on a migrated database
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { spawn } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { generateKeyPair, exportJWK, SignJWT } from "jose";

const DB = process.env.TEST_DATABASE_URL;
const skip = DB ? false : "TEST_DATABASE_URL not set";
const here = path.dirname(fileURLToPath(import.meta.url));
const WEB_DIR = path.resolve(here, "../..");
const API_DIR = path.resolve(here, "../../../../services/platform-api");

const CLIENT_ID = "lotediretor-client";
const API_AUD = "lotediretor-api";
let idp, issuer, key, jwk, web, api, webUrl;
const codes = new Map();
const stats = { refresh: 0, token: 0 };

function freePort() {
  return new Promise((resolve) => {
    const s = http.createServer().listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });
}

async function sign(claims, aud, exp = "5m") {
  return new SignJWT(claims)
    .setProtectedHeader({ alg: "RS256", kid: "k1" })
    .setIssuer(issuer).setAudience(aud).setSubject("e2e-user")
    .setIssuedAt().setExpirationTime(exp).sign(key);
}

async function tokenSet(nonce) {
  return {
    access_token: await sign({ email: "e2e@example.com", name: "Pessoa Teste" }, API_AUD),
    id_token: await sign({ nonce, email: "e2e@example.com", name: "Pessoa Teste" }, CLIENT_ID),
    refresh_token: randomBytes(16).toString("hex"),
    token_type: "Bearer",
    // Below the BFF refresh margin (60 s) so every request exercises refresh.
    expires_in: 30,
  };
}

function readBody(req) {
  return new Promise((resolve) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => resolve(new URLSearchParams(data)));
  });
}

async function waitFor(url, ms = 60_000) {
  const start = Date.now();
  while (Date.now() - start < ms) {
    try {
      const r = await fetch(url, { redirect: "manual" });
      if (r.status < 500) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`timeout waiting for ${url}`);
}

before(async () => {
  if (!DB) return;
  const pair = await generateKeyPair("RS256", { extractable: true });
  key = pair.privateKey;
  jwk = { ...(await exportJWK(pair.publicKey)), kid: "k1", alg: "RS256", use: "sig" };
  idp = http.createServer(async (req, res) => {
    const url = new URL(req.url, issuer);
    res.setHeader("content-type", "application/json");
    if (url.pathname === "/.well-known/openid-configuration") {
      return res.end(JSON.stringify({
        issuer,
        authorization_endpoint: `${issuer}/authorize`,
        token_endpoint: `${issuer}/token`,
        jwks_uri: `${issuer}/jwks`,
        end_session_endpoint: `${issuer}/logout`,
        response_types_supported: ["code"],
        subject_types_supported: ["public"],
        id_token_signing_alg_values_supported: ["RS256"],
        code_challenge_methods_supported: ["S256"],
        token_endpoint_auth_methods_supported: ["client_secret_basic", "client_secret_post"],
      }));
    }
    if (url.pathname === "/jwks") return res.end(JSON.stringify({ keys: [jwk] }));
    if (url.pathname === "/authorize") {
      assert.equal(url.searchParams.get("code_challenge_method"), "S256");
      assert.equal(url.searchParams.get("client_id"), CLIENT_ID);
      const code = randomBytes(12).toString("hex");
      codes.set(code, {
        challenge: url.searchParams.get("code_challenge"),
        nonce: url.searchParams.get("nonce"),
        redirect: url.searchParams.get("redirect_uri"),
      });
      const back = new URL(url.searchParams.get("redirect_uri"));
      back.searchParams.set("code", code);
      back.searchParams.set("state", url.searchParams.get("state"));
      back.searchParams.set("iss", issuer);
      res.statusCode = 302;
      res.setHeader("location", back.toString());
      return res.end();
    }
    if (url.pathname === "/token") {
      const form = await readBody(req);
      if (form.get("grant_type") === "refresh_token") {
        stats.refresh += 1;
        return res.end(JSON.stringify(await tokenSet(undefined)));
      }
      stats.token += 1;
      const entry = codes.get(form.get("code"));
      codes.delete(form.get("code")); // single use
      const verifier = form.get("code_verifier") ?? "";
      const challenge = createHash("sha256").update(verifier).digest("base64url");
      if (!entry || entry.challenge !== challenge || entry.redirect !== form.get("redirect_uri")) {
        res.statusCode = 400;
        return res.end(JSON.stringify({ error: "invalid_grant" }));
      }
      return res.end(JSON.stringify(await tokenSet(entry.nonce)));
    }
    res.statusCode = 404;
    res.end("{}");
  });
  const idpPort = await freePort();
  await new Promise((r) => idp.listen(idpPort, "127.0.0.1", r));
  issuer = `http://127.0.0.1:${idpPort}`;

  const apiPort = await freePort();
  const webPort = await freePort();
  webUrl = `http://127.0.0.1:${webPort}`;
  const common = { ...process.env, NODE_ENV: "production" };
  api = spawn("node", ["dist/main.js"], {
    cwd: API_DIR,
    env: { ...common, PORT: String(apiPort), HOST: "127.0.0.1", DATABASE_URL: DB,
           OIDC_ISSUER: issuer, OIDC_AUDIENCE: API_AUD },
    stdio: "inherit",
  });
  web = spawn("node", ["node_modules/next/dist/bin/next", "start", "-H", "127.0.0.1", "-p", String(webPort)], {
    cwd: WEB_DIR,
    env: {
      ...common, AUTH_MODE: "oidc", OIDC_ISSUER: issuer, OIDC_CLIENT_ID: CLIENT_ID,
      OIDC_CLIENT_SECRET: "test-secret", APP_BASE_URL: webUrl,
      SESSION_SECRET: randomBytes(32).toString("base64"), DATABASE_URL: DB,
      PLATFORM_API_URL: `http://127.0.0.1:${apiPort}`, OIDC_ALLOW_INSECURE_FOR_TESTS: "true",
      NEXT_TELEMETRY_DISABLED: "1",
    },
    stdio: "inherit",
  });
  await waitFor(`http://127.0.0.1:${apiPort}/healthz`);
  await waitFor(`${webUrl}/entrar`);
});

after(() => {
  web?.kill();
  api?.kill();
  idp?.close();
});

// Minimal cookie jar with manual redirects, to observe every hop.
class Browser {
  constructor() { this.cookies = new Map(); }
  header() { return [...this.cookies].map(([k, v]) => `${k}=${v}`).join("; "); }
  store(res) {
    for (const raw of res.headers.getSetCookie()) {
      const [pair, ...attrs] = raw.split(";");
      const [name, ...rest] = pair.split("=");
      const value = rest.join("=");
      const expired = attrs.some((a) => /max-age=0|expires=thu, 01 jan 1970/i.test(a.trim()));
      if (!value || expired) this.cookies.delete(name.trim());
      else this.cookies.set(name.trim(), value);
    }
  }
  async go(url, init = {}) {
    const res = await fetch(url, {
      ...init, redirect: "manual",
      headers: { ...(init.headers ?? {}), cookie: this.header() },
    });
    this.store(res);
    return res;
  }
  async login(returnTo = "/imoveis") {
    const start = await this.go(`${webUrl}/auth/login?returnTo=${encodeURIComponent(returnTo)}`);
    const authorize = await fetch(start.headers.get("location"), { redirect: "manual" });
    const callback = authorize.headers.get("location");
    return { start, callback, done: await this.go(callback) };
  }
}

test("unauthenticated pages redirect to the login page", { skip }, async () => {
  const b = new Browser();
  const res = await b.go(`${webUrl}/dashboard`);
  assert.equal(res.status, 307);
  assert.match(res.headers.get("location"), /\/entrar\?returnTo=/);
  const api = await b.go(`${webUrl}/api/properties`);
  assert.equal(api.status, 401);
  const resolve = await b.go(`${webUrl}/api/parcel/resolve`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ municipality_ibge: "3550308", lat: -23.5, lng: -46.6 }),
  });
  assert.equal(resolve.status, 401);
});

test("full login: PKCE + state + nonce, HttpOnly session, API access, logout", { skip }, async () => {
  const b = new Browser();
  const { start, done } = await b.login("/imoveis");
  const authUrl = new URL(start.headers.get("location"));
  assert.equal(authUrl.origin, issuer);
  assert.ok(authUrl.searchParams.get("code_challenge"));
  const setCookie = done.headers.getSetCookie().join("\n");
  assert.match(setCookie, /ld_session=.*HttpOnly/i);
  assert.match(setCookie, /SameSite=lax/i);
  assert.equal(done.status, 307);
  assert.equal(new URL(done.headers.get("location"), webUrl).pathname, "/imoveis");

  const me = await b.go(`${webUrl}/api/me`);
  assert.equal(me.status, 200);
  const account = await me.json();
  assert.equal(account.email, "e2e@example.com");
  assert.ok(stats.refresh > 0, "short-lived access token was refreshed by the BFF");

  const created = await b.go(`${webUrl}/api/properties`, {
    method: "POST", headers: { "content-type": "application/json", origin: webUrl },
    body: JSON.stringify({ ibge_code: "3550308", label: "Terreno E2E", lat: -23.55, lng: -46.63 }),
  });
  assert.equal(created.status, 201);
  const list = await (await b.go(`${webUrl}/api/properties`)).json();
  assert.ok(list.properties.some((p) => p.label === "Terreno E2E"));

  const csrf = await b.go(`${webUrl}/api/properties`, {
    method: "POST", headers: { "content-type": "application/json", origin: "https://evil.example" },
    body: JSON.stringify({ ibge_code: "3550308", label: "x", lat: 0, lng: 0 }),
  });
  assert.equal(csrf.status, 403);

  const page = await b.go(`${webUrl}/dashboard`);
  assert.equal(page.status, 200);
  assert.match(await page.text(), /Pessoa/);

  const logout = await b.go(`${webUrl}/auth/logout`, { method: "POST", headers: { origin: webUrl } });
  assert.equal(logout.status, 303);
  assert.match(logout.headers.get("location"), new RegExp(`^${issuer}/logout`));
  assert.equal((await b.go(`${webUrl}/api/me`)).status, 401);
});

test("callback rejects replayed codes, forged state and missing login state", { skip }, async () => {
  const b = new Browser();
  const { callback, done } = await b.login();
  assert.equal(done.status, 307);
  // Replay: the login-state cookie was consumed and the code is single-use.
  const replay = await b.go(callback);
  assert.match(replay.headers.get("location"), /\/entrar\?erro=/);

  const c = new Browser();
  const start = await c.go(`${webUrl}/auth/login`);
  const authorize = await fetch(start.headers.get("location"), { redirect: "manual" });
  const forged = new URL(authorize.headers.get("location"));
  forged.searchParams.set("state", "forged");
  const res = await c.go(forged.toString());
  assert.match(res.headers.get("location"), /erro=falha-na-autenticacao/);

  const fresh = new Browser();
  const noState = await fresh.go(`${webUrl}/auth/callback?code=x&state=y`);
  assert.match(noState.headers.get("location"), /erro=sessao-expirada/);
});

test("returnTo cannot redirect off-site", { skip }, async () => {
  for (const evil of ["//evil.example/x", "https://evil.example", "/\\evil.example", "/auth/logout"]) {
    const b = new Browser();
    const { done } = await b.login(evil);
    const target = new URL(done.headers.get("location"), webUrl);
    assert.equal(target.origin, webUrl, evil);
    assert.equal(target.pathname, "/dashboard", evil);
  }
});
