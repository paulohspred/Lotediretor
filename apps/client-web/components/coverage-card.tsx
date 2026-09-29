"use client";

export type CoverageSource = {
  source_id: string;
  coverage_level: "MUNICIPAL" | "SUBMUNICIPAL" | "STATE" | "NATIONAL";
  authority: string;
  access_class: string;
  verification_status: string;
  canonical_url: string | null;
  domains: string[];
};

export type Coverage = {
  municipality: { name: string; uf: string; capabilities: { parcel_resolver: boolean } };
  summary: {
    total_sources: number;
    by_level: Record<string, number>;
    municipal_sources_catalogued: boolean;
  };
  sources: CoverageSource[];
  disclaimer: string;
};

const LEVEL_LABEL: Record<string, string> = {
  MUNICIPAL: "Municipais",
  STATE: "Estaduais",
  NATIONAL: "Federais",
};

const ACCESS_LABEL: Record<string, string> = {
  OPEN_REUSABLE: "Aberta",
  PUBLIC_QUERY_ONLY: "Consulta pública",
  AUTHENTICATED_PUBLIC: "Requer login",
  AUTHENTICATED_INSTITUTIONAL: "Institucional",
  RESTRICTED_PERSONAL: "Restrita",
  PAID_ON_DEMAND: "Paga sob demanda",
  USER_PRIVATE: "Do usuário",
  DERIVED: "Derivada",
};

type Props = {
  state: "idle" | "loading" | "ready" | "error";
  coverage: Coverage | null;
};

/** What we know exists for this municipality — shown before any analysis. */
export function CoverageCard({ state, coverage }: Props) {
  if (state === "idle") return null;
  if (state === "loading") {
    return (
      <div className="panel-card coverage-card">
        <h2>Cobertura de dados</h2>
        <p className="muted">Consultando catálogo de fontes…</p>
      </div>
    );
  }
  if (state === "error" || !coverage) {
    return (
      <div className="panel-card coverage-card">
        <h2>Cobertura de dados</h2>
        <p className="muted">Catálogo de fontes indisponível no momento.</p>
      </div>
    );
  }

  const { summary, municipality } = coverage;
  const municipal = coverage.sources.filter(
    (s) => s.coverage_level === "MUNICIPAL",
  );

  return (
    <div className="panel-card coverage-card">
      <h2>Cobertura de dados</h2>
      <ul className="coverage-levels">
        {["MUNICIPAL", "STATE", "NATIONAL"].map((level) => (
          <li key={level}>
            <strong>{summary.by_level[level] ?? 0}</strong>
            <span>{LEVEL_LABEL[level]}</span>
          </li>
        ))}
      </ul>
      <p className={municipality.capabilities.parcel_resolver ? "coverage-ok" : "coverage-gap"}>
        {municipality.capabilities.parcel_resolver
          ? "Lotes cadastrais disponíveis: clique em um terreno."
          : "Lotes cadastrais ainda não disponíveis neste município. O contexto federal e estadual pode ser analisado por ponto."}
      </p>
      {!summary.municipal_sources_catalogued && (
        <p className="muted">
          Nenhuma fonte municipal catalogada ainda para {municipality.name}.
        </p>
      )}
      {municipal.length > 0 && (
        <details>
          <summary>Fontes municipais ({municipal.length})</summary>
          <ul className="coverage-sources">
            {municipal.map((source) => (
              <li key={source.source_id}>
                {source.canonical_url ? (
                  <a href={source.canonical_url} target="_blank" rel="noreferrer">
                    {source.authority}
                  </a>
                ) : (
                  <span>{source.authority}</span>
                )}
                <small>
                  {ACCESS_LABEL[source.access_class] ?? source.access_class}
                  {source.domains.length ? ` · ${source.domains.join(", ")}` : ""}
                </small>
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="muted coverage-disclaimer">{coverage.disclaimer}</p>
    </div>
  );
}
