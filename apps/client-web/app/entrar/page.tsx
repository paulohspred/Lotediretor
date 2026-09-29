import Link from "next/link";
import { redirect } from "next/navigation";
import { authConfig } from "@/lib/auth/config";
import { safeReturnTo } from "@/lib/auth/crypto";
import { getSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

const ERRORS: Record<string, string> = {
  "sessao-expirada": "O tempo para concluir o login expirou. Tente novamente.",
  "login-cancelado": "O login foi cancelado.",
  "falha-na-autenticacao": "Não foi possível confirmar sua identidade. Tente novamente.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ returnTo?: string; erro?: string }>;
}) {
  const params = await searchParams;
  const returnTo = safeReturnTo(params.returnTo);
  const config = authConfig();
  if (config.mode !== "oidc" || (await getSession())) {
    redirect(returnTo);
  }
  const error = params.erro ? ERRORS[params.erro] ?? "Não foi possível entrar." : null;
  const loginHref = `/auth/login?returnTo=${encodeURIComponent(returnTo)}`;

  return (
    <main className="login-page">
      <div className="login-brand">
        <span className="brand-mark">LD</span>
        <strong>LoteDiretor Brasil</strong>
      </div>
      <section className="login-card" aria-labelledby="login-title">
        <h1 id="login-title">Entrar na plataforma</h1>
        <p className="muted">
          Inteligência urbanística e territorial auditável para qualquer município do Brasil.
        </p>
        {error && (
          <p className="login-error" role="alert">
            {error}
          </p>
        )}
        <a className="primary-button login-button" href={loginHref}>
          Entrar
        </a>
        <a className="secondary-button login-button" href={`${loginHref}&signup=1`}>
          Criar conta
        </a>
        <p className="login-note">
          O login é feito no provedor de identidade da LoteDiretor, com suporte a
          autenticação em dois fatores. Não armazenamos sua senha.
        </p>
      </section>
      <footer className="login-footer">
        <Link href={process.env.NEXT_PUBLIC_SITE_URL ?? "/"}>Voltar ao site</Link>
      </footer>
    </main>
  );
}
