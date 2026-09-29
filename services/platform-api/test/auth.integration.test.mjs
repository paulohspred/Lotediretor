// Auth, account provisioning, tenant isolation (RLS) and saved properties.
// Uses a fake OIDC issuer (discovery + JWKS) and a real PostGIS database.
// TEST_DATABASE_URL must use the least-privilege runtime role, not a
// superuser, otherwise row-level security would be bypassed.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { generateKeyPair, exportJWK, SignJWT } from "jose";

const DB = process.env.TEST_DATABASE_URL;
const skip = DB ? false : "TEST_DATABASE_URL not set";
let app, base, idp, issuer, privateKey, otherKey;
const AUD = "lotediretor-api";

before(async () => {
  if (!DB) return;
  ({ privateKey } = await generateKeyPair("RS256"));
  const pair = await generateKeyPair("RS256", { extractable: true });
  ({ privateKey: otherKey } = await generateKeyPair("RS256"));
  const jwk = { ...(await exportJWK(pair.publicKey)), kid: "k1", alg: "RS256", use: "sig" };
  privateKey = pair.privateKey;
  idp = http.createServer((req, res) => {
    res.setHeader("content-type", "application/json");
    if (req.url === "/.well-known/openid-configuration") {
      res.end(JSON.stringify({ issuer, jwks_uri: `${issuer}/jwks` }));
    } else if (req.url === "/jwks") {
      res.end(JSON.stringify({ keys: [jwk] }));
    } else {
      res.statusCode = 404;
      res.end("{}");
    }
  });
  await new Promise((r) => idp.listen(0, "127.0.0.1", r));
  issuer = `http://127.0.0.1:${idp.address().port}`;
  Object.assign(process.env, { OIDC_ISSUER: issuer, OIDC_AUDIENCE: AUD, DATABASE_URL: DB });

  await import("reflect-metadata");
  const { NestFactory } = await import("@nestjs/core");
  const { FastifyAdapter } = await import("@nestjs/platform-fastify");
  const { AppModule } = await import("../dist/app.module.js");
  app = await NestFactory.create(AppModule, new FastifyAdapter(), { logger: false });
  await app.listen(0, "127.0.0.1");
  base = await app.getUrl();
});

after(async () => {
  await app?.close();
  idp?.close();
});

const run = Date.now().toString(36);

async function token(sub, extra = {}, { key = privateKey, aud = AUD, exp = "5m" } = {}) {
  return new SignJWT({ email: `${sub}@example.com`, name: `User ${sub}`, ...extra })
    .setProtectedHeader({ alg: "RS256", kid: "k1" })
    .setIssuer(issuer)
    .setAudience(aud)
    .setSubject(`${sub}-${run}`)
    .setIssuedAt()
    .setExpirationTime(exp)
    .sign(key);
}

async function call(path, { method = "GET", tok, body, headers = {} } = {}) {
  const response = await fetch(`${base}${path}`, {
    method,
    headers: {
      ...(tok ? { authorization: `Bearer ${tok}` } : {}),
      ...(body ? { "content-type": "application/json" } : {}),
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  return { status: response.status, body: text ? JSON.parse(text) : null };
}

test("protected routes reject missing, forged, expired and wrong-audience tokens", { skip }, async () => {
  assert.equal((await call("/me")).body.code, "AUTH_REQUIRED");
  assert.equal((await call("/me", { tok: await token("x", {}, { key: otherKey }) })).status, 401);
  assert.equal((await call("/me", { tok: await token("x", {}, { exp: "-1m" }) })).status, 401);
  assert.equal((await call("/me", { tok: await token("x", {}, { aud: "other" }) })).status, 401);
  // Public endpoints stay public.
  assert.equal((await call("/municipalities/3550308")).status, 200);
});

test("first login provisions exactly one personal workspace, even concurrently", { skip }, async () => {
  const tok = await token("alice");
  const results = await Promise.all([1, 2, 3, 4].map(() => call("/me", { tok })));
  for (const r of results) assert.equal(r.status, 200);
  const orgs = new Set(results.map((r) => r.body.active_org.org_id));
  assert.equal(orgs.size, 1);
  assert.equal(results[0].body.memberships.length, 1);
  assert.equal(results[0].body.active_org.role, "OWNER");
  assert.equal(results[0].body.active_org.kind, "PERSONAL");
});

test("saved properties are isolated between organizations", { skip }, async () => {
  const alice = await token("alice");
  const bob = await token("bob");
  const created = await call("/properties", {
    method: "POST", tok: alice,
    body: { ibge_code: "3550308", label: "Terreno Av. Paulista", lat: -23.56, lng: -46.65 },
  });
  assert.equal(created.status, 201);
  const id = created.body.saved_property_id;

  const mine = await call("/properties", { tok: alice });
  assert.ok(mine.body.properties.some((p) => p.saved_property_id === id));
  assert.equal(mine.body.properties[0].municipality, "São Paulo");

  const theirs = await call("/properties", { tok: bob });
  assert.ok(!theirs.body.properties.some((p) => p.saved_property_id === id));
  assert.equal((await call(`/properties/${id}`, { method: "DELETE", tok: bob })).status, 404);
  assert.equal(
    (await call(`/properties/${id}`, { method: "PATCH", tok: bob, body: { label: "hack" } })).status,
    404,
  );

  const aliceOrg = mine.body && (await call("/me", { tok: alice })).body.active_org.org_id;
  const forged = await call("/properties", { tok: bob, headers: { "x-org-id": aliceOrg } });
  assert.equal(forged.status, 403);
  assert.equal(forged.body.code, "ORG_FORBIDDEN");

  const activity = await call("/activity", { tok: alice });
  assert.ok(activity.body.events.some((e) => e.kind === "property.saved"));

  assert.equal((await call(`/properties/${id}`, { method: "DELETE", tok: alice })).status, 204);
});

test("property input is validated", { skip }, async () => {
  const tok = await token("carol");
  for (const body of [
    { ibge_code: "35", label: "x", lat: 0, lng: 0 },
    { ibge_code: "3550308", label: "", lat: 0, lng: 0 },
    { ibge_code: "3550308", label: "x", lat: "a", lng: 0 },
    { ibge_code: "9999999", label: "x", lat: 0, lng: 0 },
  ]) {
    const r = await call("/properties", { method: "POST", tok, body });
    assert.equal(r.status, 400, JSON.stringify(body));
  }
  assert.equal((await call("/properties", { tok, headers: { "x-org-id": "nope" } })).status, 400);
});
