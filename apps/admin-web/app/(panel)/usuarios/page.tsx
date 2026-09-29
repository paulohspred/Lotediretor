import { adminJson } from "@/lib/admin";

export const dynamic = "force-dynamic";

type User = {
  user_id: string; email: string | null; display_name: string | null; status: string;
  created_at: string; last_login_at: string | null; memberships: { org: string; role: string }[];
};

const d = (v: string | null) => (v ? new Date(v).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" }) : "—");

export default async function UsersPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await searchParams;
  const data = await adminJson<{ items: User[] }>(`/users${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  return (
    <>
      <h1>Usuários</h1>
      <p className="muted">Senhas e fatores de autenticação são gerenciados no provedor de identidade (Keycloak).</p>
      <form className="filters"><input name="q" defaultValue={q} placeholder="Nome ou e-mail" aria-label="Buscar" /><button className="btn">Buscar</button></form>
      {!data ? <p className="error">Falha ao carregar.</p> : (
        <table className="table">
          <thead><tr><th>Nome</th><th>E-mail</th><th>Organizações</th><th>Último acesso</th><th>Situação</th></tr></thead>
          <tbody>
            {data.items.map((u) => (
              <tr key={u.user_id}>
                <td>{u.display_name ?? "—"}</td><td>{u.email ?? "—"}</td>
                <td>{u.memberships.map((m) => `${m.org} (${m.role})`).join(", ") || "—"}</td>
                <td>{d(u.last_login_at)}</td><td>{u.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
