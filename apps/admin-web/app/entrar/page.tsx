import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

const ERRORS: Record<string, string> = {
  "sessao-expirada": "O tempo para concluir o login expirou.",
  "login-cancelado": "O login foi cancelado.",
  "falha-na-autenticacao": "Não foi possível confirmar sua identidade.",
};

export default async function AdminLogin({ searchParams }: { searchParams: Promise<{ erro?: string }> }) {
  if (await getSession()) redirect("/");
  const { erro } = await searchParams;
  return (
    <main className="gate">
      <section className="gate-card">
        <h1>LoteDiretor · Admin</h1>
        <p>Área interna. Acesso com autenticação em dois fatores.</p>
        {erro && <p className="error" role="alert">{ERRORS[erro] ?? "Não foi possível entrar."}</p>}
        <a className="btn primary" href="/auth/login?returnTo=%2F">Entrar</a>
      </section>
    </main>
  );
}
