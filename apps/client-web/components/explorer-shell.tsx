"use client";

import { FormEvent, useMemo, useState } from "react";
import type { Geometry } from "geojson";
import { ExplorerMap } from "./explorer-map";
import { CITIES, cityByIbge } from "@/lib/cities";
import {
  CATEGORY_LABELS,
  defaultLayerIds,
  layersForCity,
  type MapLayerCategory,
} from "@/lib/map-layers";

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
  properties: Record<string, never>;
};

type DossierItem = {
  label: string;
  value: unknown;
  unit?: string;
};

type DossierSection = {
  id: string;
  title: string;
  order: number;
  type: string;
  items: DossierItem[];
};

type ParcelPayload = {
  found?: boolean;
  parcel?: {
    geometry?: Geometry | null;
    address?: {
      street?: string | null;
      number?: string | null;
      complement?: string | null;
    };
    identifiers?: {
      fiscal_registration?: string | null;
      real_estate_code?: string | null;
    };
    land_area_m2?: number | null;
    built_area_m2?: number | null;
    use?: string | null;
    cadastral_status?: string | null;
  };
  dossier?: {
    title?: string;
    sections?: DossierSection[];
  };
  analysis?: {
    run_id?: string | null;
    audit_available?: boolean;
    lineage_status?: string | null;
    municipality_ibge?: string;
    lat?: number;
    lng?: number;
    analysis_date?: string | null;
  };
};

type SearchResult = {
  kind: "address" | "parcel";
  display_name?: string;
  lat: number;
  lng: number;
  exact_house_number?: boolean;
};

function formatNumber(value: number, digits = 2): string {
  return new Intl.NumberFormat("pt-BR", {
    maximumFractionDigits: digits,
  }).format(value);
}

function formatItemValue(item: DossierItem): string {
  const value = item.value;
  if (typeof value === "boolean") return value ? "Sim" : "Não";

  if (typeof value === "number") {
    if (item.unit === "BRL") {
      return new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
        maximumFractionDigits: 2,
      }).format(value);
    }
    if (item.unit === "ratio_percent") {
      return `${formatNumber(value * 100)}%`;
    }
    return `${formatNumber(value)}${item.unit ? ` ${item.unit}` : ""}`;
  }

  const text = String(value ?? "—");
  if (item.unit === "BRL") {
    const numeric = Number(text);
    if (Number.isFinite(numeric)) {
      return new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
        maximumFractionDigits: 2,
      }).format(numeric);
    }
  }
  return `${text}${item.unit ? ` ${item.unit}` : ""}`;
}

export function ExplorerShell() {
  const [cityIbge, setCityIbge] = useState(CITIES[0].ibge);
  const city = useMemo(() => cityByIbge(cityIbge), [cityIbge]);
  const [query, setQuery] = useState("");
  const [activeLayerIds, setActiveLayerIds] = useState<string[]>(() =>
    defaultLayerIds(CITIES[0].ibge),
  );
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [payload, setPayload] = useState<ParcelPayload | null>(null);
  const [focusPoint, setFocusPoint] = useState<{ lat: number; lng: number } | null>(null);
  const [activeSectionId, setActiveSectionId] = useState<string | null>(null);
  const [status, setStatus] = useState(
    "Selecione um terreno no mapa ou busque um endereço.",
  );
  const [busy, setBusy] = useState(false);
  const [viewMode, setViewMode] = useState<"2d" | "3d">("2d");

  const parcel = payload?.parcel;
  const geometry = parcel?.geometry ?? null;
  const feature: ParcelFeature | null = geometry
    ? { type: "Feature", geometry, properties: {} }
    : null;

  const sections = payload?.dossier?.sections ?? [];
  const availableLayers = useMemo(
    () => layersForCity(cityIbge),
    [cityIbge],
  );
  const layerGroups = useMemo(() => {
    const groups = new Map<MapLayerCategory, typeof availableLayers>();
    for (const layer of availableLayers) {
      const group = groups.get(layer.category) ?? [];
      group.push(layer);
      groups.set(layer.category, group);
    }
    return Array.from(groups.entries());
  }, [availableLayers]);
  const activeSection =
    sections.find((section) => section.id === activeSectionId) ??
    sections[0] ??
    null;

  async function resolveParcel(lat: number, lng: number) {
    setBusy(true);
    setSearchResults([]);
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
      if (!body.found || !body.parcel?.geometry) {
        setPayload(null);
        setActiveSectionId(null);
        setStatus(
          "Nenhum lote cadastral foi encontrado neste ponto. Tente clicar dentro do terreno.",
        );
        return;
      }

      setPayload(body);
      const firstSection = body.dossier?.sections?.[0];
      setActiveSectionId(firstSection?.id ?? null);

      const street = body.parcel.address?.street;
      const number = body.parcel.address?.number;
      setStatus(
        street
          ? `${street}${number ? `, ${number}` : ""}`
          : "Lote encontrado.",
      );
    } catch (error) {
      setPayload(null);
      setActiveSectionId(null);
      setStatus(
        error instanceof Error
          ? error.message
          : "A análise territorial está temporariamente indisponível.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function searchProperty(event: FormEvent) {
    event.preventDefault();
    if (query.trim().length < 3) return;
    setBusy(true);
    setPayload(null);
    setActiveSectionId(null);
    setStatus("Buscando endereço e cadastro municipal…");
    try {
      const params = new URLSearchParams({
        q: query.trim(),
        ibge: city.ibge,
      });

      const [addressResponse, parcelResponse] = await Promise.all([
        fetch(`/api/search/address?${params}`),
        fetch(`/api/search/parcel?${params}`),
      ]);

      const addressBody = (await addressResponse.json()) as {
        results?: Array<Omit<SearchResult, "kind">>;
        warning?: string;
      };
      const parcelBody = (await parcelResponse.json()) as {
        results?: SearchResult[];
        warning?: string;
      };

      const parcelResults = (parcelBody.results ?? []).map((item) => ({
        ...item,
        kind: "parcel" as const,
      }));
      const addressResults = (addressBody.results ?? []).map((item) => ({
        ...item,
        kind: "address" as const,
      }));
      const results = [...parcelResults, ...addressResults];

      setSearchResults(results);
      setStatus(
        results.length
          ? "Escolha um resultado. Cadastros abrem o lote; ruas posicionam o mapa."
          : addressBody.warning ||
              parcelBody.warning ||
              "Nenhum imóvel ou endereço foi localizado.",
      );
    } catch {
      setSearchResults([]);
      setStatus("Busca temporariamente indisponível.");
    } finally {
      setBusy(false);
    }
  }

  function changeCity(nextIbge: string) {
    setCityIbge(nextIbge);
    setPayload(null);
    setSearchResults([]);
    setFocusPoint(null);
    setActiveSectionId(null);
    setQuery("");
    setActiveLayerIds(defaultLayerIds(nextIbge));
    setStatus("Selecione um terreno no mapa ou busque um endereço.");
  }

  const sql = parcel?.identifiers?.fiscal_registration ?? null;
  const cib = parcel?.identifiers?.real_estate_code ?? null;
  const street = parcel?.address?.street ?? null;
  const number = parcel?.address?.number ?? null;
  const complement = parcel?.address?.complement ?? null;

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
          <form className="global-search" onSubmit={searchProperty}>
            <span>Buscar imóvel</span>
            <input
              aria-label="Busca global"
              placeholder="Rua, número, inscrição ou código cadastral"
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

            {searchResults.length > 0 && (
              <div className="search-result-stack">
                {searchResults.map((result, index) => (
                  <button
                    type="button"
                    key={`${result.lat}-${result.lng}-${index}`}
                    onClick={() => {
                      setSearchResults([]);
                      setFocusPoint({ lat: result.lat, lng: result.lng });
                      if (
                        result.kind === "parcel" ||
                        result.exact_house_number
                      ) {
                        void resolveParcel(result.lat, result.lng);
                      } else {
                        setStatus(
                          "Rua localizada. Clique no terreno desejado para abrir a ficha.",
                        );
                      }
                    }}
                  >
                    <span className="search-result-kind">
                      {result.kind === "parcel" ? "Cadastro" : "Endereço"}
                    </span>
                    <span>{result.display_name || "Resultado localizado"}</span>
                  </button>
                ))}
              </div>
            )}

            <div className="panel-card layer-panel">
              <h2>Camadas</h2>
              {layerGroups.map(([category, group]) => (
                <div className="layer-group" key={category}>
                  <h3>{CATEGORY_LABELS[category]}</h3>
                  {group.map((layer) => {
                    const checked = activeLayerIds.includes(layer.id);
                    return (
                      <label className="layer-check" key={layer.id}>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() =>
                            setActiveLayerIds((current) =>
                              checked
                                ? current.filter((id) => id !== layer.id)
                                : [...current, layer.id],
                            )
                          }
                        />
                        <span>
                          <strong>{layer.label}</strong>
                          <small>{layer.description}</small>
                        </span>
                      </label>
                    );
                  })}
                </div>
              ))}
            </div>

            <div className="panel-card">
              <h2>Seleção</h2>
              <p className="muted">
                Clique dentro de um terreno. O contorno cadastral encontrado
                será destacado e a ficha auditável abrirá ao lado.
              </p>
            </div>
          </aside>

          <div className="map-stage">
            <ExplorerMap
              city={city}
              feature={feature}
              focusPoint={focusPoint}
              activeLayerIds={activeLayerIds}
              viewMode={viewMode}
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
              <div className="map-mode">
                <button
                  className={viewMode === "2d" ? "active" : ""}
                  type="button"
                  onClick={() => setViewMode("2d")}
                >
                  2D
                </button>
                <button
                  className={viewMode === "3d" ? "active" : ""}
                  type="button"
                  onClick={() => setViewMode("3d")}
                >
                  3D urbano
                </button>
              </div>
              <span>{city.name} · {city.uf} · MapLibre</span>
            </div>
          </div>

          <aside className="detail-panel">
            <div className="eyebrow">Ficha do imóvel</div>
            <h2>{street || "Análise territorial"}</h2>

            {!parcel ? (
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

                <div className="key-facts">
                  {sql && (
                    <div>
                      <span>Inscrição fiscal</span>
                      <strong>{sql}</strong>
                    </div>
                  )}
                  {cib && (
                    <div>
                      <span>Código imobiliário</span>
                      <strong>{cib}</strong>
                    </div>
                  )}
                  {parcel.land_area_m2 !== null &&
                    parcel.land_area_m2 !== undefined && (
                      <div>
                        <span>Terreno</span>
                        <strong>{formatNumber(parcel.land_area_m2)} m²</strong>
                      </div>
                    )}
                  {parcel.built_area_m2 !== null &&
                    parcel.built_area_m2 !== undefined && (
                      <div>
                        <span>Construído</span>
                        <strong>{formatNumber(parcel.built_area_m2)} m²</strong>
                      </div>
                    )}
                </div>

                {payload?.analysis?.audit_available && (
                  <div className="audit-card">
                    <div>
                      <span className="audit-dot" aria-hidden="true" />
                      <strong>Análise registrada e imutável</strong>
                    </div>
                    <p>
                      {payload.analysis.lineage_status ||
                        "Snapshot de análise registrado."}
                    </p>
                    <details>
                      <summary>Detalhes de auditoria</summary>
                      <dl>
                        <dt>Identificador da execução</dt>
                        <dd>{payload.analysis.run_id}</dd>
                        <dt>Município analisado</dt>
                        <dd>{city.name} · {city.uf}</dd>
                      </dl>
                    </details>
                  </div>
                )}

                {sections.length > 0 && (
                  <>
                    <label className="section-picker">
                      <span>Seção do dossiê</span>
                      <select
                        value={activeSection?.id ?? ""}
                        onChange={(event) =>
                          setActiveSectionId(event.target.value)
                        }
                      >
                        {sections.map((section) => (
                          <option key={section.id} value={section.id}>
                            {section.title}
                          </option>
                        ))}
                      </select>
                    </label>

                    {activeSection && (
                      <section className="dossier-section">
                        <h3>{activeSection.title}</h3>
                        <dl>
                          {activeSection.items.map((item, index) => (
                            <div
                              className="dossier-row"
                              key={`${item.label}-${index}`}
                            >
                              <dt>{item.label}</dt>
                              <dd>{formatItemValue(item)}</dd>
                            </div>
                          ))}
                        </dl>
                      </section>
                    )}
                  </>
                )}
              </div>
            )}
          </aside>
        </section>
      </section>
    </main>
  );
}
