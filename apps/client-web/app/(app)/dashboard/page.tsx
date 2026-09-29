import Link from "next/link";
import { apiJson, requireViewer } from "@/lib/server/viewer";

export const dynamic = "force-dynamic";

type Property = {
  saved_property_id: string;
  label: string;
  municipality: string;
  uf: string;
  created_at: string;
};

type Activity = { kind: string; summary: string; created_at: string };

function when(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  });
}

export default async function DashboardPage() {
  const viewer = await requireViewer("/dashboard");
  const [properties, activity] = await Promise.all([
    apiJson<{ properties: Property[] }>("/properties"),
    apiJson<{ events: Activity[] }>("/activity"),
  ]);
  const name = viewer.me?.display_name?.split(" ")[0];
  const org = viewer.me?.active_org;

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <div className="eyebrow">{org ? org.name : "Workspace"}</div>
          <h1>{name ? `Olá, ${name}` : "Início"}</h1>
        </div>
        <Link className="primary-button" href="/explorer">
          Analisar um terreno
        </Link>
      </header>

      {org?.status === "TRIAL" && (
        <div className="notice">
          Seu workspace está em período de avaliação. Os planos pagos chegam com o
          módulo de assinatura.
        </div>
      )}

      <section className="card-grid">
        <article className="stat-card">
          <span>Imóveis salvos</span>
          <strong>{properties?.properties.length ?? "—"}</strong>
          <Link href="/imoveis">Ver imóveis</Link>
        </article>
        <article className="stat-card">
          <span>Cobertura territorial</span>
          <strong>Brasil</strong>
          <small>contexto federal em qualquer município</small>
        </article>
        <article className="stat-card">
          <span>A.I Cidades</span>
          <strong>Legislação</strong>
          <Link href="/assistente">Perguntar com citação da lei</Link>
        </article>
      </section>

      <section className="two-col">
        <article className="panel-card">
          <h2>Imóveis recentes</h2>
          {properties === null ? (
            <p className="muted">Não foi possível carregar seus imóveis.</p>
          ) : properties.properties.length === 0 ? (
            <p className="muted">
              Nenhum imóvel salvo. Abra o <Link href="/explorer">Explorer</Link>, selecione um
              terreno e use “Salvar em Meus imóveis”.
            </p>
          ) : (
            <ul className="list">
              {properties.properties.slice(0, 6).map((p) => (
                <li key={p.saved_property_id}>
                  <strong>{p.label}</strong>
                  <small>
                    {p.municipality} · {p.uf} · {when(p.created_at)}
                  </small>
                </li>
              ))}
            </ul>
          )}
        </article>
        <article className="panel-card">
          <h2>Atividade</h2>
          {activity?.events.length ? (
            <ul className="list">
              {activity.events.slice(0, 8).map((e, i) => (
                <li key={`${e.created_at}-${i}`}>
                  <span>{e.summary}</span>
                  <small>{when(e.created_at)}</small>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Sem atividade registrada ainda.</p>
          )}
        </article>
      </section>
    </div>
  );
}
