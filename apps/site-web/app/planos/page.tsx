import type { Metadata } from "next";
import Link from "next/link";
import { APP_URL } from "@/lib/content";

export const metadata: Metadata = {
  title: "Planos",
  description: "Planos do LoteDiretor para profissionais, empresas e instituições.",
  alternates: { canonical: "/planos" },
};

const PLANS = [
  {
    name: "Avaliação",
    who: "Para conhecer a plataforma",
    items: ["Workspace individual", "Explorer e dossiê territorial", "A.I Cidades com cota de perguntas", "Meus imóveis"],
    cta: { label: "Criar conta", href: `${APP_URL}/auth/login?signup=1` },
  },
  {
    name: "Profissional",
    who: "Arquitetos, engenheiros, corretores",
    items: ["Tudo da avaliação", "Cota ampliada de IA", "Relatórios para clientes", "Suporte por e-mail"],
    cta: { label: "Falar com vendas", href: "/contato?segmento=Profissional" },
  },
  {
    name: "Empresa",
    who: "Incorporadoras, bancos, escritórios",
    items: ["Equipes e organizações", "Integração por API", "Municípios prioritários integrados", "Acordo de nível de serviço"],
    cta: { label: "Falar com vendas", href: "/contato?segmento=Empresa" },
  },
];

export default function Plans() {
  return (
    <section className="section">
      <div className="container">
        <h1 className="page-title center">Planos</h1>
        <p className="section-lead center">
          Os valores estão em definição durante o lançamento. Fale com a equipe para uma proposta.
        </p>
        <div className="grid-3">
          {PLANS.map((p) => (
            <article className="card plan" key={p.name}>
              <h2>{p.name}</h2>
              <p className="muted">{p.who}</p>
              <ul className="checklist">
                {p.items.map((i) => <li key={i}>{i}</li>)}
              </ul>
              {p.cta.href.startsWith("http") ? (
                <a className="btn primary" href={p.cta.href}>{p.cta.label}</a>
              ) : (
                <Link className="btn primary" href={p.cta.href}>{p.cta.label}</Link>
              )}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
