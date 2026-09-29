import { adminJson } from "@/lib/admin";
import { StatusAction } from "@/components/status-action";

export const dynamic = "force-dynamic";

type Org = { org_id: string; name: string; kind: string; status: string; created_at: string; members: number; ai_30d: number };

export default async function OrganizationsPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await searchParams;
  const data = await adminJson<{ items: Org[] }>(`/organizations${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  return (
    <>
      <h1>Organizações</h1>
      <form className="filters"><input name="q" defaultValue={q} placeholder="Buscar por nome" aria-label="Buscar" /><button className="btn">Buscar</button></form>
      {!data ? <p className="error">Falha ao carregar.</p> : (
        <table className="table">
          <thead><tr><th>Nome</th><th>Tipo</th><th>Membros</th><th>IA (30 dias)</th><th>Criada em</th><th>Situação</th></tr></thead>
          <tbody>
            {data.items.map((o) => (
              <tr key={o.org_id}>
                <td>{o.name}</td><td>{o.kind}</td><td>{o.members}</td><td>{o.ai_30d}</td>
                <td>{new Date(o.created_at).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" })}</td>
                <td><StatusAction endpoint={`/api/admin/organizations/${o.org_id}`} current={o.status} requireReason
                  options={["TRIAL", "ACTIVE", "PAST_DUE", "RESTRICTED", "SUSPENDED", "CANCELLED"]} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
