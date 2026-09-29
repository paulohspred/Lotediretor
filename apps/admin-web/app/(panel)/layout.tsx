import Link from "next/link";
import { requireAdmin } from "@/lib/admin";
import { AdminNav } from "@/components/admin-nav";

export const dynamic = "force-dynamic";

export default async function PanelLayout({ children }: { children: React.ReactNode }) {
  const gate = await requireAdmin();
  if (!gate.ok) {
    return (
      <main className="gate">
        <section className="gate-card">
          <h1>Acesso restrito</h1>
          {gate.reason === "role" ? (
            <p>
              Sua conta ({gate.me.email}) não tem o perfil de administrador da plataforma.
              Solicite acesso a um responsável.
            </p>
          ) : (
            <p>
              O painel administrativo exige autenticação em dois fatores. Configure um
              segundo fator na sua conta e entre novamente.
            </p>
          )}
          <div className="gate-actions">
            {gate.reason === "mfa" && (
              <a className="btn primary" href="/auth/login?reauth=1">Entrar novamente com 2FA</a>
            )}
            <form action="/auth/logout" method="post">
              <button className="btn" type="submit">Sair</button>
            </form>
          </div>
        </section>
      </main>
    );
  }
  return (
    <div className="admin">
      <aside className="admin-side">
        <Link href="/" className="admin-brand">LoteDiretor <span>admin</span></Link>
        <AdminNav />
        <div className="admin-user">
          <span>{gate.me.display_name ?? gate.me.email}</span>
          <form action="/auth/logout" method="post">
            <button type="submit" className="link">Sair</button>
          </form>
        </div>
      </aside>
      <main className="admin-main">{children}</main>
    </div>
  );
}
