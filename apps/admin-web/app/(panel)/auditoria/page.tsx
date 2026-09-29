import { adminJson } from "@/lib/admin";

export const dynamic = "force-dynamic";

type Entry = { audit_id: number; created_at: string; actor_label: string; action: string;
  object_type: string; object_id: string | null; reason: string | null;
  before_state: unknown; after_state: unknown };

export default async function AuditPage() {
  const data = await adminJson<{ items: Entry[] }>("/audit?limit=200");
  return (
    <>
      <h1>Auditoria</h1>
      <p className="muted">Registro imutável das ações administrativas (não pode ser alterado nem apagado pela aplicação).</p>
      {!data ? <p className="error">Falha ao carregar.</p> : (
        <table className="table">
          <thead><tr><th>#</th><th>Quando</th><th>Quem</th><th>Ação</th><th>Objeto</th><th>Motivo</th><th>Antes → depois</th></tr></thead>
          <tbody>
            {data.items.map((e) => (
              <tr key={e.audit_id}>
                <td>{e.audit_id}</td>
                <td>{new Date(e.created_at).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" })}</td>
                <td>{e.actor_label}</td><td>{e.action}</td>
                <td>{e.object_type}<br /><small>{e.object_id}</small></td>
                <td className="wrap">{e.reason}</td>
                <td><code>{JSON.stringify(e.before_state)} → {JSON.stringify(e.after_state)}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
