// HTTP integration tests for /municipalities against a real PostGIS database
// migrated and loaded with database/fixtures/ibge_municipios_sample.sql and
// the source registry. Skipped unless TEST_DATABASE_URL is set.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";

const DB = process.env.TEST_DATABASE_URL;
const skip = DB ? false : "TEST_DATABASE_URL not set";
let app;
let base;
let engine;
const engineCalls = [];

before(async () => {
  if (!DB) return;
  engine = http.createServer((req, res) => {
    const url = new URL(req.url, "http://x");
    engineCalls.push(Object.fromEntries(url.searchParams));
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({
      found: true,
      sections: [{ id: "territorial", title: "Contexto territorial",
        items: [{ label: "Macrorregião hidrográfica (ANA/IBGE)", value: "Paraná" }] }],
      unavailable_sources: ["INCRA · SIGEF"],
      analysis_area: { kind: "POINT_BUFFER", half_side_m: 25 },
    }));
  });
  await new Promise((r) => engine.listen(0, "127.0.0.1", r));
  process.env.PARCEL_ENGINE_BASE_URL = `http://127.0.0.1:${engine.address().port}`;
  process.env.DATABASE_URL = DB;
  await import("reflect-metadata");
  const { NestFactory } = await import("@nestjs/core");
  const { FastifyAdapter } = await import("@nestjs/platform-fastify");
  const { AppModule } = await import("../dist/app.module.js");
  app = await NestFactory.create(AppModule, new FastifyAdapter(), {
    logger: false,
  });
  await app.listen(0, "127.0.0.1");
  base = await app.getUrl();
});

after(async () => {
  await app?.close();
  engine?.close();
});

async function get(path) {
  const response = await fetch(`${base}${path}`);
  return { status: response.status, body: await response.json() };
}

test("resolves a point to its municipality", { skip }, async () => {
  const { status, body } = await get("/municipalities/resolve?lat=-23.55&lng=-46.63");
  assert.equal(status, 200);
  assert.equal(body.ibge_code, "3550308");
  assert.equal(body.uf, "SP");
  assert.equal(body.capabilities.parcel_resolver, true);
  assert.equal(body.bbox.length, 4);
});

test("a municipality without a parcel engine still resolves", { skip }, async () => {
  const { status, body } = await get("/municipalities/resolve?lat=-15.8&lng=-47.9");
  assert.equal(status, 200);
  assert.equal(body.name, "Brasília");
  assert.equal(body.capabilities.parcel_resolver, false);
  assert.equal(body.capabilities.federal_context, true);
});

test("ocean point returns MUNICIPALITY_NOT_FOUND", { skip }, async () => {
  const { status, body } = await get("/municipalities/resolve?lat=-20&lng=-30");
  assert.equal(status, 404);
  assert.equal(body.code, "MUNICIPALITY_NOT_FOUND");
});

test("invalid coordinates are rejected", { skip }, async () => {
  for (const q of ["lat=abc&lng=1", "lat=95&lng=1", "lng=1"]) {
    const { status, body } = await get(`/municipalities/resolve?${q}`);
    assert.equal(status, 400, q);
    assert.equal(body.code, "INVALID_COORDINATE");
  }
});

test("search is accent-insensitive and escapes LIKE wildcards", { skip }, async () => {
  let r = await get("/municipalities?q=sao%20paulo");
  assert.equal(r.status, 200);
  assert.equal(r.body.results[0].ibge_code, "3550308");
  r = await get("/municipalities?q=SAPUCAI&uf=mg");
  assert.equal(r.body.results[0].ibge_code, "3159605");
  r = await get("/municipalities?q=%25%25");
  assert.equal(r.body.results.length, 0);
  r = await get("/municipalities?q=a");
  assert.equal(r.status, 400);
});

test("detail validates the IBGE code", { skip }, async () => {
  assert.equal((await get("/municipalities/12345")).status, 400);
  assert.equal((await get("/municipalities/9999999")).status, 404);
  const { body } = await get("/municipalities/5300108");
  assert.equal(body.uf, "DF");
});

test("coverage lists national, state and municipal sources", { skip }, async () => {
  const { status, body } = await get("/municipalities/3505708/coverage");
  assert.equal(status, 200);
  assert.ok(body.summary.by_level.NATIONAL > 0);
  assert.ok(body.summary.by_level.STATE > 0);
  assert.ok(body.summary.by_level.MUNICIPAL > 0);
  assert.equal(body.summary.municipal_sources_catalogued, true);
  assert.equal(body.sources[0].coverage_level, "MUNICIPAL");
  // No municipal source of another city leaks into Barueri.
  assert.ok(
    body.sources
      .filter((s) => s.coverage_level === "MUNICIPAL")
      .every((s) => s.source_id.includes("barueri")),
  );
});

test("a municipality with no catalogued local source says so", { skip }, async () => {
  const { body } = await get("/municipalities/5300108/coverage");
  assert.equal(body.summary.by_level.MUNICIPAL, 0);
  assert.equal(body.summary.municipal_sources_catalogued, false);
  assert.ok(body.summary.total_sources > 0);
});

async function post(path, body) {
  const response = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return { status: response.status, body: await response.json() };
}

test("point context resolves the municipality server-side", { skip }, async () => {
  const { status, body } = await post("/context/point", { lat: -22.25, lng: -45.7 });
  assert.equal(status, 200);
  assert.equal(body.municipality.ibge_code, "3159605");
  assert.equal(engineCalls.at(-1).municipality_ibge, "3159605");
  assert.equal(body.dossier.sections[0].items[0].value, "Paraná");
  assert.deepEqual(body.unavailable_sources, ["INCRA · SIGEF"]);
  assert.match(body.disclaimer, /Não identifica o lote/);
});

test("point context outside Brazil never reaches the engine", { skip }, async () => {
  const before = engineCalls.length;
  const { status, body } = await post("/context/point", { lat: -20, lng: -30 });
  assert.equal(status, 404);
  assert.equal(body.code, "MUNICIPALITY_NOT_FOUND");
  assert.equal(engineCalls.length, before);
  assert.equal((await post("/context/point", { lat: "x", lng: 1 })).status, 400);
});

test("factory municipality resolves parcels from PostGIS", { skip }, async () => {
  const detail = await get("/municipalities/3159605");
  assert.equal(detail.body.capabilities.parcel_resolver, true);
  assert.equal(detail.body.capabilities.parcel_source, "municipal_factory");

  const { status, body } = await post("/parcel/resolve", {
    municipality_ibge: "3159605", lat: -22.2595, lng: -45.7095,
  });
  assert.equal(status, 200);
  assert.equal(body.found, true);
  assert.equal(body.parcel.identifiers.primary.value, "01.02.000");
  assert.equal(body.parcel.address.street, "Rua Teste");
  const zoning = body.dossier.sections.find((s) => s.id === "zoning");
  assert.match(zoning.items[0].label, /ZR1/);
  const provenance = body.dossier.sections.find((s) => s.id === "provenance");
  assert.ok(provenance.items.some((i) => /Parâmetros urbanísticos/.test(i.label)));
  const restrictions = body.dossier.sections.find((s) => s.id === "restrictions");
  assert.ok(restrictions);
  assert.ok(restrictions.items.some((i) => /Unidade de conservação/.test(i.label)));
  assert.ok(restrictions.items.some((i) => /Fonte: Fixture/.test(i.value)));
  // Personal fields present in the upstream files never reach the API.
  assert.doesNotMatch(JSON.stringify(body), /PROPRIET/);
});

test("factory municipality: empty point and parcel search", { skip }, async () => {
  const miss = await post("/parcel/resolve", {
    municipality_ibge: "3159605", lat: -22.20, lng: -45.65,
  });
  assert.equal(miss.status, 200);
  assert.equal(miss.body.found, false);
  const search = await get("/parcel/search?municipality_ibge=3159605&q=01.02.00");
  assert.equal(search.status, 200);
  assert.ok(search.body.results.length > 0);
  assert.equal(search.body.results[0].kind, "parcel");
});

test("legal search, documents and rules respect review status", { skip }, async () => {
  const search = await get("/legal/search?q=recuos%20alvenaria&ibge=3505708");
  assert.equal(search.status, 200);
  assert.ok(search.body.results.length > 0);
  assert.match(search.body.results[0].document_title, /565/);

  const docs = await get("/legal/documents?ibge=3505708");
  assert.ok(docs.body.documents.some((d) => d.text_versions > 0));

  const strict = await get("/legal/rules?ibge=3505708&zone=A-11");
  for (const rule of strict.body.rules) assert.notEqual(rule.status, "CANDIDATE");
  const loose = await get("/legal/rules?ibge=3505708&zone=A-11&include_candidates=true");
  assert.ok(loose.body.rules.length > strict.body.rules.length);
  assert.ok(loose.body.rules.every((r) => r.provision_path && r.evidence_excerpt));

  assert.equal((await get("/legal/rules?ibge=3505708&zone=A-11&date=31/12/2020")).status, 400);
  assert.equal((await get("/legal/search?q=ab&ibge=3505708")).status, 400);
});

test("factory dossier shows zone parameters flagged by review status", { skip }, async () => {
  const { body } = await post("/parcel/resolve", {
    municipality_ibge: "3159605", lat: -22.2595, lng: -45.7095,
  });
  const params = body.dossier.sections.find((s) => s.id === "urban_parameters");
  assert.ok(params, "urban_parameters section present");
  assert.match(params.title, /ZR1/);
  assert.ok(params.items.some((i) => /Aguardando revisão/.test(i.label)));
  assert.ok(params.items.some((i) => /Não use para decisão/.test(i.value)));
});
