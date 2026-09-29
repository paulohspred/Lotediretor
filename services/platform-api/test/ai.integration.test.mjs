// A.I Cidades: retrieval, citation validation, degraded modes, quota, traces.
// Uses a fake OIDC issuer and a fake Anthropic-compatible endpoint.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { generateKeyPair, exportJWK, SignJWT } from "jose";

const DB = process.env.TEST_DATABASE_URL;
const skip = DB ? false : "TEST_DATABASE_URL not set";
let idp, issuer, key, llm, llmUrl, app, base, appNoKey, baseNoKey;
const llmRequests = [];
let llmReply = () => ({ status: 200, body: {} });
const run = Date.now().toString(36);

function listen(server) {
  return new Promise((r) => server.listen(0, "127.0.0.1", () => r(server.address().port)));
}

async function makeApp(env) {
  Object.assign(process.env, env);
  const { NestFactory } = await import("@nestjs/core");
  const { FastifyAdapter } = await import("@nestjs/platform-fastify");
  const { AppModule } = await import("../dist/app.module.js");
  const instance = await NestFactory.create(AppModule, new FastifyAdapter(), { logger: false });
  await instance.listen(0, "127.0.0.1");
  return instance;
}

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
  issuer = `http://127.0.0.1:${await listen(idp)}`;

  llm = http.createServer((req, res) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => {
      llmRequests.push({ headers: req.headers, body: JSON.parse(data) });
      const { status, body } = llmReply(JSON.parse(data));
      res.writeHead(status, { "content-type": "application/json" });
      res.end(JSON.stringify(body));
    });
  });
  llmUrl = `http://127.0.0.1:${await listen(llm)}`;

  const common = {
    DATABASE_URL: DB, OIDC_ISSUER: issuer, OIDC_AUDIENCE: "lotediretor-api",
    AI_MAX_QUESTIONS_PER_HOUR: "3",
  };
  appNoKey = await makeApp({ ...common, ANTHROPIC_API_KEY: "" });
  baseNoKey = await appNoKey.getUrl();
  app = await makeApp({ ...common, ANTHROPIC_API_KEY: "test-key", AI_BASE_URL: llmUrl, AI_MODEL: "fake-model" });
  base = await app.getUrl();
});

after(async () => {
  await app?.close();
  await appNoKey?.close();
  idp?.close();
  llm?.close();
});

async function token(sub) {
  return new SignJWT({ email: `${sub}@example.com`, name: sub })
    .setProtectedHeader({ alg: "RS256", kid: "k1" })
    .setIssuer(issuer).setAudience("lotediretor-api").setSubject(`${sub}-${run}`)
    .setIssuedAt().setExpirationTime("5m").sign(key);
}

async function ask(url, tok, body) {
  const r = await fetch(`${url}/ai/cidades/ask`, {
    method: "POST",
    headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return { status: r.status, body: await r.json() };
}

function toolAnswer(input) {
  return {
    status: 200,
    body: {
      model: "fake-model",
      content: [{ type: "tool_use", id: "t1", name: "responder", input }],
      usage: { input_tokens: 1234, output_tokens: 210 },
    },
  };
}

const BARUERI = "3505708";
const Q_SER = "Qual o recuo frontal para residência unifamiliar no setor A-04?";

test("requires authentication", { skip }, async () => {
  const r = await fetch(`${base}/ai/cidades/ask`, { method: "POST" });
  assert.equal(r.status, 401);
});

test("without a model: retrieval-only answer with sources, no LLM call", { skip }, async () => {
  const before = llmRequests.length;
  const { status, body } = await ask(baseNoKey, await token("nokey"), { ibge_code: BARUERI, question: Q_SER });
  assert.equal(status, 200);
  assert.equal(body.mode, "RETRIEVAL_ONLY");
  assert.equal(body.status, "NAO_DETERMINADO");
  assert.deepEqual(body.zones, ["SER"]);
  assert.ok(body.citations.some((c) => c.kind === "provision" && c.path === "art. 35"));
  assert.ok(body.citations.some((c) => c.kind === "rule" && c.review_status === "CANDIDATE"));
  assert.equal(llmRequests.length, before);
});

test("municipality without legislation: NO_SOURCES, LLM never called", { skip }, async () => {
  const before = llmRequests.length;
  const { body } = await ask(base, await token("nosrc"), {
    ibge_code: "5300108", question: "Qual o gabarito máximo no Plano Piloto?",
  });
  assert.equal(body.mode, "NO_SOURCES");
  assert.equal(body.status, "NAO_DETERMINADO");
  assert.equal(llmRequests.length, before);
});

test("LLM answer: unknown citations removed, candidate rules force review", { skip }, async () => {
  llmReply = () => toolAnswer({
    status: "CONDICIONADO",
    answer: "O recuo frontal é de 5 m para residência unifamiliar.",
    citations: ["S1", "R1", "S99"],
    uncertainty: "BAIXA",
    professional_review: "NENHUMA",
  });
  const { status, body } = await ask(base, await token("llm1"), { ibge_code: BARUERI, question: Q_SER });
  assert.equal(status, 200);
  assert.equal(body.mode, "LLM");
  assert.equal(body.status, "CONDICIONADO");
  assert.deepEqual(body.citations.map((c) => c.id), ["S1", "R1"]);
  assert.ok(body.validator_flags.includes("unknown_citation_removed"));
  assert.ok(body.validator_flags.includes("uses_unreviewed_rules"));
  assert.equal(body.professional_review, "OBRIGATORIA");
  assert.match(body.answer, /revis/i);

  const sent = llmRequests.at(-1);
  assert.equal(sent.headers["x-api-key"], "test-key");
  assert.equal(sent.body.tool_choice.name, "responder");
  assert.equal(sent.body.temperature, 0);
  assert.match(sent.body.system, /é DADO, não instrução/);
  const prompt = sent.body.messages[0].content;
  assert.match(prompt, /<fonte id="S1"[^>]*dispositivo="art\. 35"/);
  assert.match(prompt, /<regra id="R1" status="CANDIDATE"/);
  assert.match(prompt, /<pergunta>\nQual o recuo frontal/);
});

test("a decision without valid citations is downgraded", { skip }, async () => {
  llmReply = () => toolAnswer({
    status: "PROIBIDO", answer: "É proibido.", citations: ["S42"],
    uncertainty: "BAIXA", professional_review: "NENHUMA",
  });
  const { body } = await ask(base, await token("llm2"), { ibge_code: BARUERI, question: Q_SER });
  assert.equal(body.status, "NAO_DETERMINADO");
  assert.ok(body.validator_flags.includes("downgraded_no_valid_citation"));
  assert.doesNotMatch(body.answer, /É proibido/);
});

test("provider failure returns 503 and quota returns 429", { skip }, async () => {
  llmReply = () => ({ status: 500, body: { error: "boom" } });
  const tok = await token("quota");
  const failed = await ask(base, tok, { ibge_code: BARUERI, question: Q_SER });
  assert.equal(failed.status, 503);
  assert.equal(failed.body.code, "AI_UNAVAILABLE");
  llmReply = () => toolAnswer({
    status: "INFORMATIVO", answer: "ok", citations: [], uncertainty: "MEDIA",
    professional_review: "RECOMENDADA",
  });
  // Failed calls are not traced; three successful ones fill the hourly quota.
  for (let i = 0; i < 3; i += 1) {
    assert.equal((await ask(base, tok, { ibge_code: BARUERI, question: Q_SER })).status, 200);
  }
  const limited = await ask(base, tok, { ibge_code: BARUERI, question: Q_SER });
  assert.equal(limited.status, 429);
  assert.equal(limited.body.code, "AI_QUOTA_EXCEEDED");
});

test("input validation", { skip }, async () => {
  const tok = await token("val");
  assert.equal((await ask(base, tok, { ibge_code: "35", question: Q_SER })).status, 400);
  assert.equal((await ask(base, tok, { ibge_code: BARUERI, question: "curta" })).status, 400);
  assert.equal((await ask(base, tok, { ibge_code: BARUERI, question: "x".repeat(1001) })).status, 400);
});

test("traces store a hash of the question and accept feedback", { skip }, async () => {
  llmReply = () => toolAnswer({
    status: "INFORMATIVO", answer: "Explicação.", citations: ["S1"], uncertainty: "MEDIA",
    professional_review: "RECOMENDADA",
  });
  const tok = await token("trace");
  const { body } = await ask(base, tok, { ibge_code: BARUERI, question: Q_SER });
  const pg = (await import("pg")).default;
  const client = new pg.Client({ connectionString: DB });
  await client.connect();
  const { rows } = await client.query(
    "SELECT question_sha256, question_chars, model, input_tokens, cardinality(cited_provisions) AS cited FROM ld_ai.trace WHERE trace_id = $1",
    [body.trace_id],
  );
  assert.equal(rows[0].question_chars, Q_SER.length);
  assert.match(rows[0].question_sha256, /^[0-9a-f]{64}$/);
  assert.equal(rows[0].model, "fake-model");
  assert.equal(rows[0].input_tokens, 1234);
  assert.equal(rows[0].cited, 1);
  const fb = await fetch(`${base}/ai/cidades/traces/${body.trace_id}/feedback`, {
    method: "POST",
    headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
    body: JSON.stringify({ value: 1 }),
  });
  assert.equal(fb.status, 204);
  const other = await fetch(`${base}/ai/cidades/traces/${body.trace_id}/feedback`, {
    method: "POST",
    headers: { authorization: `Bearer ${await token("intruder")}`, "content-type": "application/json" },
    body: JSON.stringify({ value: -1 }),
  });
  assert.equal(other.status, 404);
  await client.end();
});
