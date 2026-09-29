// HTTP integration tests for /municipalities against a real PostGIS database
// migrated and loaded with database/fixtures/ibge_municipios_sample.sql and
// the source registry. Skipped unless TEST_DATABASE_URL is set.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";

const DB = process.env.TEST_DATABASE_URL;
const skip = DB ? false : "TEST_DATABASE_URL not set";
let app;
let base;

before(async () => {
  if (!DB) return;
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
  const { status, body } = await get("/municipalities/resolve?lat=-22.25&lng=-45.7");
  assert.equal(status, 200);
  assert.equal(body.name, "Santa Rita do Sapucaí");
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
  const { body } = await get("/municipalities/3159605/coverage");
  assert.equal(body.summary.by_level.MUNICIPAL, 0);
  assert.equal(body.summary.municipal_sources_catalogued, false);
  assert.ok(body.summary.total_sources > 0);
});
