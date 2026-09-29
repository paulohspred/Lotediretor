import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Prefeituras",
  description: "Adesão institucional: a prefeitura publica legislação, mapas e cadastro como fonte municipal verificada.",
  alternates: { canonical: "/prefeituras" },
};

export default function CityHalls() {
  return (
    <section className="section">
      <div className="container narrow">
        <h1 className="page-title">Para prefeituras</h1>
        <p className="section-lead">
          Quando a prefeitura adere, seus dados passam a ser a fonte municipal verificada da
          plataforma — sem trocar os sistemas que já usa.
        </p>
        <div className="grid-2">
          <article className="card">
            <h2>O que a prefeitura publica</h2>
            <ul className="checklist">
              <li>Plano Diretor, zoneamento e código de obras, com vigência</li>
              <li>Camadas oficiais: lotes, zonas, áreas especiais</li>
              <li>Parâmetros urbanísticos homologados por técnicos municipais</li>
            </ul>
          </article>
          <article className="card">
            <h2>O que a prefeitura ganha</h2>
            <ul className="checklist">
              <li>Menos atendimento repetitivo sobre “o que posso construir”</li>
              <li>Respostas públicas sempre citando a norma municipal vigente</li>
              <li>Visão de qualidade: conflitos entre mapa, lei e cadastro</li>
            </ul>
          </article>
        </div>
        <div className="callout">
          <p>
            O ambiente institucional da prefeitura está em desenvolvimento. Municípios
            interessados em participar do piloto podem falar com a equipe.
          </p>
        </div>
        <p className="center"><Link href="/contato?segmento=Prefeitura" className="btn primary lg">Participar do piloto</Link></p>
      </div>
    </section>
  );
}
