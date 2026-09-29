import { adminJson } from "@/lib/admin";

export const dynamic = "force-dynamic";

type Row = { ibge_code: string; name: string; uf: string; parcels: boolean; zoning: boolean;
  last_load: string | null; legal_documents: number; confirmed_rules: number };

export default async function CoveragePage() {
  const data = await adminJson<{ items: Row[] }>("/coverage");
  return (
    <>
      <h1>Cobertura municipal</h1>
      <p className="muted">Municípios com camadas carregadas pela fábrica ou legislação cadastrada. Todos os demais têm contexto federal.</p>
      {!data ? <p className="error">Falha ao carregar.</p> : (
        <table className="table">
          <thead><tr><th>Município</th><th>IBGE</th><th>Lotes</th><th>Zoneamento</th><th>Última carga</th><th>Leis</th><th>Regras confirmadas</th></tr></thead>
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
      )}
    </>
  );
}
