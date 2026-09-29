import { adminJson } from "@/lib/admin";
import { StatusAction } from "@/components/status-action";

export const dynamic = "force-dynamic";

type Lead = { lead_id: string; name: string; email: string; organization: string | null;
  segment: string | null; message: string; status: string; source_page: string | null; created_at: string };

export default async function LeadsPage() {
  const data = await adminJson<{ items: Lead[] }>("/leads?limit=200");
  return (
    <>
      <h1>Leads do site</h1>
      {!data ? <p className="error">Falha ao carregar.</p> : (
        <table className="table">
          <thead><tr><th>Recebido</th><th>Contato</th><th>Organização</th><th>Mensagem</th><th>Situação</th></tr></thead>
          <tbody>
            {data.items.map((l) => (
              <tr key={l.lead_id}>
                <td>{new Date(l.created_at).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" })}</td>
                <td>{l.name}<br /><a href={`mailto:${l.email}`}>{l.email}</a></td>
                <td>{l.organization ?? "—"}{l.segment ? ` · ${l.segment}` : ""}</td>
                <td className="wrap">{l.message}</td>
                <td><StatusAction endpoint={`/api/admin/leads/${l.lead_id}`} current={l.status}
                  options={["NEW", "CONTACTED", "QUALIFIED", "DISCARDED"]} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
