// Contract tests for ParcelEngineService against a fake Python engine.
// Run after `npm run build`: `npm test`.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";

let server;
let lastUrl = "";
const routes = new Map();

before(async () => {
  server = http.createServer((req, res) => {
    lastUrl = req.url;
    const path = req.url.split("?")[0];
    const handler = routes.get(path) ?? (() => [404, { error: "not_found" }]);
    const [status, body] = handler(req);
    res.writeHead(status, { "content-type": "application/json" });
    res.end(JSON.stringify(body));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  process.env.PARCEL_ENGINE_BASE_URL = `http://127.0.0.1:${server.address().port}`;
});

after(() => server.close());

async function service() {
  const mod = await import("../dist/modules/geo/parcel-engine.service.js");
  return new mod.ParcelEngineService();
}

const SP = "3550308";

test("rejects unsupported municipality without calling the engine", async () => {
  const svc = await service();
  await assert.rejects(
    svc.resolve({ municipality_ibge: "9999999", lat: -23.5, lng: -46.6 }),
    (err) => err.getResponse().code === "UNSUPPORTED_MUNICIPALITY",
  );
});

test("rejects non-numeric or out-of-range coordinates", async () => {
  const svc = await service();
  for (const bad of [{ lat: "x", lng: 1 }, { lat: 91, lng: 0 }, { lat: 0, lng: 181 }]) {
    await assert.rejects(
      svc.resolve({ municipality_ibge: SP, ...bad }),
      (err) => err.getResponse().code === "INVALID_COORDINATE",
    );
  }
});

test("engine 404 parcel_not_found becomes found:false, not a 502", async () => {
  routes.set("/v1/sp/parcel", () => [404, { error: "parcel_not_found" }]);
  const svc = await service();
  const out = await svc.resolve({ municipality_ibge: SP, lat: -23.5, lng: -46.6 });
  assert.equal(out.found, false);
  assert.equal(out.parcel, null);
});

test("engine 400 (outside bounds) becomes POINT_OUTSIDE_MUNICIPALITY", async () => {
  routes.set("/v1/sp/parcel", () => [400, { error: "outside_sao_paulo_demo_bounds" }]);
  const svc = await service();
  await assert.rejects(
    svc.resolve({ municipality_ibge: SP, lat: -23.5, lng: -46.6 }),
    (err) => err.getResponse().code === "POINT_OUTSIDE_MUNICIPALITY",
  );
});

test("historical analysis_date is refused instead of silently ignored", async () => {
  const svc = await service();
  await assert.rejects(
    svc.resolve({ municipality_ibge: SP, lat: -23.5, lng: -46.6, analysis_date: "2021-03-01" }),
    (err) => err.getResponse().code === "HISTORICAL_ANALYSIS_NOT_SUPPORTED",
  );
  await assert.rejects(
    svc.resolve({ municipality_ibge: SP, lat: -23.5, lng: -46.6, analysis_date: "01/03/2021" }),
    (err) => err.getResponse().code === "INVALID_ANALYSIS_DATE",
  );
});

test("failed persistence surfaces an audit warning", async () => {
  routes.set("/v1/sp/parcel", () => [
    200,
    {
      found: true,
      feature: { geometry: { type: "Point", coordinates: [0, 0] }, properties: { sql_reference: "001.002.0003-4" } },
      report: { sections: [] },
      persistence: { status: "failed" },
    },
  ]);
  const svc = await service();
  const out = await svc.resolve({ municipality_ibge: SP, lat: -23.5, lng: -46.6 });
  assert.equal(out.found, true);
  assert.equal(out.analysis.audit_available, false);
  assert.equal(out.analysis.persistence_status, "failed");
  assert.match(out.analysis.audit_warning, /auditoria/);
  assert.equal(out.parcel.identifiers.primary.value, "001.002.0003-4");
  assert.match(lastUrl, /lat=-23.5&lng=-46.6/);
});

test("prototype keys are not treated as supported municipalities", async () => {
  const svc = await service();
  for (const key of ["constructor", "__proto__", "toString"]) {
    await assert.rejects(
      svc.resolve({ municipality_ibge: key, lat: -23.5, lng: -46.6 }),
      (err) => err.getResponse().code === "UNSUPPORTED_MUNICIPALITY",
    );
    await assert.rejects(
      svc.search({ municipality_ibge: key, q: "rua teste" }),
      (err) => err.getResponse().code === "UNSUPPORTED_MUNICIPALITY",
    );
  }
});
