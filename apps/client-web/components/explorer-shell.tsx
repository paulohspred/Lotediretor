"use client";

import { FormEvent, useMemo, useState } from "react";
import type { Geometry } from "geojson";
import { ExplorerMap } from "./explorer-map";
import { CITIES, cityByIbge } from "@/lib/cities";

const rail = [
  "Dashboard",
  "Explorer",
  "Imóveis",
  "Empreendimentos",
  "Análises",
  "Relatórios",
  "CRM",
];

type ParcelFeature = {
  type: "Feature";
  geometry: Geometry;
  properties?: Record<string, unknown> | null;
};

type ParcelPayload = {
  found?: boolean;
  feature?: ParcelFeature | null;
  context?: Record<string, unknown>;
  report?: { title?: string };
};

type AddressResult = {
  display_name?: string;
  lat: number;
  lng: number;
  exact_house_number?: boolean;
};

function textValue(
  properties: Record<string, unknown>,
  key: string,
): string | null {
  const value = properties[key];
  if (value === null || value === undefined || value === "") return null;
  return String(value);
}

function numberValue(
  properties: Record<string, unknown>,
  key: string,
): string | null {
  const value = properties[key];
  if (typeof value !== "number") return value ? String(value) : null;
  return new Intl.NumberFormat("pt-BR", {
    maximumFractionDigits: 2,
  }).format(value);
}

export function ExplorerShell() {
  const [cityIbge, setCityIbge] = useState(CITIES[0].ibge);
  const city = useMemo(() => cityByIbge(cityIbge), [cityIbge]);
  const [query, setQuery] = useState("");
  const [addresses, setAddresses] = useState<AddressResult[]>([]);
  const [payload, setPayload] = useState<ParcelPayload | null>(null);
  const [focusPoint, setFocusPoint] = useState<{ lat: number; lng: number } | null>(null);
  const [status, setStatus] = useState(
    "Selecione um terreno no mapa ou busque um endereço.",
  );
  const [busy, setBusy] = useState(false);

  const feature = payload?.feature ?? null;
  const properties = (feature?.properties ?? {}) as Record<string, unknown>;

  async function resolveParcel(lat: number, lng: number) {
    setBusy(true);
    setAddresses([]);
    setFocusPoint({ lat, lng });
    setStatus("Consultando cadastro, regras e contexto territorial…");
    try {
      const response = await fetch("/api/parcel/resolve", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          municipality_ibge: city.ibge,
          lat,
          lng,
        }),
      });
      const body = (await response.json()) as ParcelPayload & {
        message?: string;
      };
      if (!response.ok) {
        throw new Error(body.message || "Falha ao analisar o terreno.");
      }
      if (!body.found || !body.feature) {
        setPayload(null);
        setStatus(
          "Nenhum lote cadastral foi encontrado neste ponto. Tente clicar dentro do terreno.",
        );
        return;
      }
      setPayload(body);
      const street = textValue(
        (body.feature.properties ?? {}) as Record<string, unknown>,
        "street",
      );
      const number = textValue(
        (body.feature.properties ?? {}) as Record<string, unknown>,
        "number",
      );
      setStatus(
        street
          ? `${street}${number ? `, ${number}` : ""}`
          : "Lote encontrado.",
      );
    } catch (error) {
      setPayload(null);
      setStatus(
        error instanceof Error
          ? error.message
          : "A análise territorial está temporariamente indisponível.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function searchAddress(event: FormEvent) {
    event.preventDefault();
    if (query.trim().length < 3) return;
    setBusy(true);
    setPayload(null);
    setStatus("Buscando endereço…");
    try {
      const params = new URLSearchParams({
        q: query.trim(),
        ibge: city.ibge,
      });
      const response = await fetch(`/api/search/address?${params}`);
      const body = (await response.json()) as {
        results?: AddressResult[];
        warning?: string;
      };
      const results = body.results ?? [];
      setAddresses(results);
      setStatus(
        results.length
          ? "Escolha um resultado para localizar e analisar o terreno."
          : body.warning || "Endereço não localizado.",
      );
    } catch {
      setAddresses([]);
      setStatus("Busca de endereço temporariamente indisponível.");
    } finally {
      setBusy(false);
    }
  }

  function changeCity(nextIbge: string) {
    setCityIbge(nextIbge);
    setPayload(null);
    setAddresses([]);
    setFocusPoint(null);
    setQuery("");
    setStatus("Selecione um terreno no mapa ou busque um endereço.");
  }

  const sql = textValue(properties, "sql_reference");
  const cib = textValue(properties, "cib");
  const street = textValue(properties, "street");
  const number = textValue(properties, "number");
  const complement = textValue(properties, "complement");
  const landArea = numberValue(properties, "land_area_m2");
  const builtArea = numberValue(properties, "built_area_m2");
  const use = textValue(properties, "use_description");

  return (
    <main className="app-shell">
      <aside className="app-rail" aria-label="Navegação principal">
        <div className="brand-mark">LD</div>
        <nav>
          {rail.map((item) => (
            <button
              className={item === "Explorer" ? "rail-item active" : "rail-item"}
              key={item}
              type="button"
            >
              {item}
            </button>
          ))}
        </nav>
        <button className="rail-item more" type="button">
          Mais
        </button>
      </aside>

      <section className="app-stage">
        <header className="app-head">
          <form className="global-search" onSubmit={searchAddress}>
            <span>Buscar imóvel</span>
            <input
              aria-label="Busca global"
              placeholder="Rua, número ou endereço"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <button type="submit" disabled={busy}>
              Buscar
            </button>
          </form>
          <div className="head-actions">
            <select
              aria-label="Município"
              value={cityIbge}
              onChange={(event) => changeCity(event.target.value)}
            >
              {CITIES.map((item) => (
                <option key={item.ibge} value={item.ibge}>
                  {item.name} · {item.uf}
                </option>
              ))}
            </select>
            <button type="button">Data-base: hoje</button>
            <button type="button">Workspace</button>
          </div>
        </header>

        <section className="explorer-layout">
          <aside className="explorer-panel">
            <div className="eyebrow">Explorer</div>
            <h1>Terreno e contexto</h1>
            <p className="muted">{status}</p>

            {addresses.length > 0 && (
              <div className="search-result-stack">
                {addresses.map((result, index) => (
                  <button
                    type="button"
                    key={`${result.lat}-${result.lng}-${index}`}
                    onClick={() => {
                      setAddresses([]);
                      setFocusPoint({ lat: result.lat, lng: result.lng });
                      if (result.exact_house_number) {
                        void resolveParcel(result.lat, result.lng);
                      } else {
                        setStatus(
                          "Rua localizada. Clique no terreno desejado para abrir a ficha.",
                        );
                      }
                    }}
                  >
                    {result.display_name || "Endereço localizado"}
                  </button>
                ))}
              </div>
            )}

            <div className="panel-card">
              <h2>Camadas</h2>
              <button type="button">Território</button>
              <button type="button">Urbanismo</button>
              <button type="button">Risco e ambiente</button>
              <button type="button">Infraestrutura</button>
              <button type="button">Rural</button>
            </div>

            <div className="panel-card">
              <h2>Seleção</h2>
              <p className="muted">
                Clique dentro de um terreno. O contorno oficial encontrado será
                destacado no mapa e a ficha abrirá ao lado.
              </p>
            </div>
          </aside>

          <div className="map-stage">
            <ExplorerMap
              city={city}
              feature={feature}
              focusPoint={focusPoint}
              onPick={({ lat, lng }) => resolveParcel(lat, lng)}
            />
            <div className="map-context-bar">
              <span>
                {busy
                  ? "Analisando…"
                  : sql
                    ? `Lote ${sql}`
                    : "Nenhum lote selecionado"}
              </span>
              <span>{city.name} · {city.uf} · MapLibre</span>
            </div>
          </div>

          <aside className="detail-panel">
            <div className="eyebrow">Ficha do imóvel</div>
            <h2>{street || "Análise territorial"}</h2>

            {!feature ? (
              <div className="empty-state">
                A ficha aparecerá aqui após selecionar um terreno.
              </div>
            ) : (
              <div className="property-sheet">
                <div className="sheet-address">
                  <strong>
                    {street}
                    {number ? `, ${number}` : ""}
                  </strong>
                  {complement && <span>{complement}</span>}
                </div>

                <dl>
                  {sql && (
                    <>
                      <dt>Inscrição fiscal</dt>
                      <dd>{sql}</dd>
                    </>
                  )}
                  {cib && (
                    <>
                      <dt>Código imobiliário</dt>
                      <dd>{cib}</dd>
                    </>
                  )}
                  {landArea && (
                    <>
                      <dt>Área do terreno</dt>
                      <dd>{landArea} m²</dd>
                    </>
                  )}
                  {builtArea && (
                    <>
                      <dt>Área construída cadastrada</dt>
                      <dd>{builtArea} m²</dd>
                    </>
                  )}
                  {use && (
                    <>
                      <dt>Uso cadastrado</dt>
                      <dd>{use}</dd>
                    </>
                  )}
                </dl>

                <button className="primary-action" type="button">
                  Abrir dossiê completo
                </button>
              </div>
            )}
          </aside>
        </section>
      </section>
    </main>
  );
}
