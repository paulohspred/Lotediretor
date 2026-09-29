import type { Metadata } from "next";
import Link from "next/link";
import { MODULES, STATUS_LABEL } from "@/lib/content";

export const metadata: Metadata = {
  title: "Soluções",
  description: "Módulos do LoteDiretor: dossiê territorial, A.I Cidades, Imóvel 360 e o que está em desenvolvimento.",
  alternates: { canonical: "/solucoes" },
};

export default function Solutions() {
  return (
    <section className="section">
      <div className="container narrow">
        <h1 className="page-title">Soluções</h1>
        <p className="section-lead">
          Uma plataforma, uma base de dados e um motor jurídico compartilhados. Cada módulo é
          indicado com sua situação real.
        </p>
        {MODULES.map((m) => (
          <article className="module-detail" id={m.slug} key={m.slug}>
            <header>
              <h2>{m.name}</h2>
              <span className={`status ${m.status}`}>{STATUS_LABEL[m.status]}</span>
            </header>
            <p>{m.summary}</p>
            <ul className="checklist">
              {m.bullets.map((b) => <li key={b}>{b}</li>)}
            </ul>
          </article>
        ))}
        <p className="center"><Link href="/contato" className="btn primary lg">Solicitar demonstração</Link></p>
      </div>
    </section>
  );
}
