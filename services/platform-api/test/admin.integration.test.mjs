// Admin control plane: role + MFA enforcement, rule review with audit trail,
// organization status, leads (public intake + admin funnel), audit log.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { generateKeyPair, exportJWK, SignJWT } from "jose";

const DB = process.env.TEST_DATABASE_URL;
const skip = DB ? false : "TEST_DATABASE_URL not set";
let idp, issuer, key, app, base;
const run = Date.now().toString(36);

before(async () => {
  if (!DB) return;
  await import("reflect-metadata");
  const pair = await generateKeyPair("RS256", { extractable: true });
  key = pair.privateKey;
  const jwk = { ...(await exportJWK(pair.publicKey)), kid: "k1", alg: "RS256" };
  idp = http.createServer((req, res) => {
    res.setHeader("content-type", "application/json");
    if (req.url === "/.well-known/openid-configuration") {
      return res.end(JSON.stringify({ issuer, jwks_uri: `${issuer}/jwks` }));
    }
    res.end(JSON.stringify({ keys: [jwk] }));
  });
  await new Promise((r) => idp.listen(0, "127.0.0.1", r));
  issuer = `http://127.0.0.1:${idp.address().port}`;
  Object.assign(process.env, {
    DATABASE_URL: DB, OIDC_ISSUER: issuer, OIDC_AUDIENCE: "lotediretor-api",
    LEADS_PER_IP_PER_HOUR: "3",
  });
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

async function token(sub, { roles = [], amr = [], extra = {} } = {}) {
  return new SignJWT({ email: `${sub}@example.com`, name: `Admin ${sub}`, realm_access: { roles }, amr, ...extra })
    .setProtectedHeader({ alg: "RS256", kid: "k1" })
    .setIssuer(issuer).setAudience("lotediretor-api").setSubject(`${sub}-${run}`)
    .setIssuedAt().setExpirationTime("5m").sign(key);
}

async function call(path, tok, { method = "GET", body, headers = {} } = {}) {
  const r = await fetch(`${base}${path}`, {
    method,
    headers: {
      ...(tok ? { authorization: `Bearer ${tok}` } : {}),
      ...(body ? { "content-type": "application/json" } : {}),
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  return { status: r.status, body: text ? JSON.parse(text) : null };
}

test("admin requires the platform-admin role and MFA", { skip }, async () => {
  assert.equal((await call("/admin/overview", await token("u"))).body.code, "FORBIDDEN");
  const noMfa = await call("/admin/overview", await token("a", { roles: ["platform-admin"] }));
  assert.equal(noMfa.status, 403);
  assert.equal(noMfa.body.code, "MFA_REQUIRED");
  const stringClaim = await call("/admin/overview", await token("a", { roles: ["platform-admin"], extra: { ld_mfa: "true" } }));
  assert.equal(stringClaim.status, 403, "only a boolean true MFA claim counts");
  const viaClaim = await call("/admin/overview", await token("a", { roles: ["platform-admin"], extra: { ld_mfa: true } }));
  assert.equal(viaClaim.status, 200, "Keycloak admin-client hardcoded MFA claim");
  const ok = await call("/admin/overview", await token("a", { roles: ["platform-admin"], amr: ["pwd", "otp"] }));
  assert.equal(ok.status, 200);
  assert.ok(ok.body.municipalities >= 1);
  assert.ok(ok.body.rules_by_status.CANDIDATE > 0);
});

test("coverage exposes national layer freshness", { skip }, async () => {
  const tok = await token("coverage", { roles: ["platform-admin"], amr: ["otp"] });
  const result = await call("/admin/coverage", tok);
  assert.equal(result.status, 200);
  assert.ok(Array.isArray(result.body.national_layers));
  const fixture = result.body.national_layers.find((l) => l.layer_key === "fixture_restriction");
  assert.ok(fixture);
  assert.equal(fixture.status, "ACTIVE");
  assert.equal(fixture.feature_count, "2");
  assert.ok(fixture.loaded_at);
});

test("rule review: requires a note, records event and audit, changes effective rules", { skip }, async () => {
  const tok = await token("rev", { roles: ["platform-admin"], amr: ["otp"] });
  const queue = await call("/admin/rules?ibge=3505708", tok);
  assert.equal(queue.status, 200);
  // Any pending rule (keeps the test re-runnable on the same database).
  const rule = queue.body.items.find((r) => r.zone_code !== "SRE");
  assert.ok(rule.provision_text.length > 20);

  const short = await call(`/admin/rules/${rule.rule_id}/review`, tok, {
    method: "POST", body: { decision: "confirm", note: "ok" },
  });
  assert.equal(short.status, 400);

  const done = await call(`/admin/rules/${rule.rule_id}/review`, tok, {
    method: "POST", body: { decision: "confirm", note: "Conferido com o art. 35 do texto oficial" },
  });
  assert.equal(done.status, 201);
  assert.equal(done.body.status, "CONFIRMED");

  const effective = await call(`/legal/rules?ibge=3505708&zone=${rule.zone_code}`);
  assert.ok(effective.body.rules.some((r) => r.rule_id === rule.rule_id && r.status === "CONFIRMED"));

  const audit = await call("/admin/audit", tok);
  const entry = audit.body.items.find((a) => a.object_id === rule.rule_id);
  assert.equal(entry.action, "legal.rule.review");
  assert.equal(entry.after_state.status, "CONFIRMED");
  assert.match(entry.actor_label, /Admin rev/);
});

test("organization status change is audited and requires a reason", { skip }, async () => {
  const admin = await token("orgadm", { roles: ["platform-admin"], amr: ["otp"] });
  const customer = await token("cust");
  const me = await call("/me", customer);
  const orgId = me.body.active_org.org_id;
  assert.equal((await call(`/admin/organizations/${orgId}`, admin, {
    method: "PATCH", body: { status: "ACTIVE" },
  })).status, 400);
  const changed = await call(`/admin/organizations/${orgId}`, admin, {
    method: "PATCH", body: { status: "ACTIVE", reason: "Contrato assinado em 28/09/2026" },
  });
  assert.equal(changed.body.status, "ACTIVE");
  const list = await call("/admin/organizations?q=cust", admin);
  assert.ok(list.body.items.some((o) => o.org_id === orgId && o.status === "ACTIVE"));
});

test("public lead intake: validation, honeypot, consent, rate limit; admin funnel", { skip }, async () => {
  const lead = {
    name: "Maria Urbanista", email: `maria.${run}@example.com`, organization: "Escritório X",
    segment: "Arquitetura", message: "Quero uma demonstração para 3 municípios.",
    consent_privacy: true, source_page: "/contato",
  };
  const headers = { "x-forwarded-for": `203.0.113.${Math.floor(Math.random() * 200)}` };
  assert.equal((await call("/public/leads", null, { method: "POST", body: { ...lead, consent_privacy: false }, headers })).status, 400);
  assert.equal((await call("/public/leads", null, { method: "POST", body: lead, headers })).status, 201);
  const bot = await call("/public/leads", null, {
    method: "POST", body: { ...lead, email: `bot.${run}@example.com`, website: "http://spam" }, headers,
  });
  assert.equal(bot.status, 201);
  assert.equal((await call("/public/leads", null, { method: "POST", body: lead, headers })).status, 429);

  const admin = await token("leads", { roles: ["platform-admin"], amr: ["otp"] });
  const leads = await call("/admin/leads?status=NEW", admin);
  const mine = leads.body.items.filter((l) => l.email.includes(run));
  assert.equal(mine.length, 1, "honeypot submission was not stored");
  const upd = await call(`/admin/leads/${mine[0].lead_id}`, admin, { method: "PATCH", body: { status: "CONTACTED" } });
  assert.equal(upd.body.status, "CONTACTED");
});

test("audit log cannot be altered, even by the runtime role", { skip }, async () => {
  const pg = (await import("pg")).default;
  const client = new pg.Client({ connectionString: DB });
  await client.connect();
  await assert.rejects(client.query("UPDATE ld_app.audit_log SET reason = 'x'"));
  await assert.rejects(client.query("DELETE FROM ld_app.audit_log"));
  await client.end();
});
