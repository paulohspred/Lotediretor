import { adminJson } from "@/lib/admin";

export const dynamic = "force-dynamic";

type Row = {
  ibge_code: string;
  name: string;
  uf: string;
  parcels: boolean;
  zoning: boolean;
  last_load: string | null;
  legal_documents: number;
  confirmed_rules: number;
};

type NationalLayer = {
  layer_key: string;
  theme: string;
  authority: string;
  source_url: string;
  source_format: string;
  license: string | null;
  status: string;
  feature_count: string;
  source_updated_at: string | null;
  loaded_at: string | null;
  notes: string | null;
};

function date(value: string | null): string {
  return value ? new Date(value).toLocaleString("pt-BR") : "—";
}

export default async function CoveragePage() {
  const data = await adminJson<{ items: Row[]; national_layers: NationalLayer[] }>("/coverage");
  return (
    <>
      <h1>Cobertura de dados</h1>
      <p className="muted">
        Camadas nacionais e cobertura municipal. Datas de carga são exibidas separadamente da data da fonte.
      </p>

      {!data ? (
        <p className="error">Falha ao carregar.</p>
      ) : (
        <>
          <h2>Camadas nacionais de restrição</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Camada</th>
                <th>Órgão</th>
                <th>Status</th>
                <th>Feições</th>
                <th>Última carga</th>
                <th>Atualização da fonte</th>
              </tr>
            </thead>
            <tbody>
              {data.national_layers.map((r) => (
                <tr key={r.layer_key}>
                  <td>
                    <strong>{r.theme}</strong>
                    <br />
                    <small>{r.layer_key} · {r.source_format}</small>
                  </td>
                  <td>{r.authority}</td>
                  <td>{r.status}</td>
                  <td>{r.feature_count}</td>
                  <td>{date(r.loaded_at)}</td>
                  <td>{date(r.source_updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h2>Cobertura municipal</h2>
          <p className="muted">
            Municípios com camadas carregadas pela fábrica ou legislação cadastrada.
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>Município</th><th>IBGE</th><th>Lotes</th><th>Zoneamento</th>
                <th>Última carga</th><th>Leis</th><th>Regras confirmadas</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.ibge_code}>
                  <td>{r.name} · {r.uf}</td><td>{r.ibge_code}</td>
                  <td>{r.parcels ? "sim" : "—"}</td><td>{r.zoning ? "sim" : "—"}</td>
                  <td>{r.last_load ? new Date(r.last_load).toLocaleDateString("pt-BR") : "—"}</td>
                  <td>{r.legal_documents}</td><td>{r.confirmed_rules}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  );
}
