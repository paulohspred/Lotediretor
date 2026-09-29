import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Como funciona",
  description: "Como o LoteDiretor monta um dossiê auditável: território, legislação, evidência e revisão humana.",
  alternates: { canonical: "/como-funciona" },
};

const STEPS = [
  {
    title: "1. Localização oficial",
    text: "Endereço, cadastro ou clique no mapa viram um ponto dentro do município correto, segundo a malha municipal do IBGE.",
  },
  {
    title: "2. Dados que se aplicam ao ponto",
    text: "Cruzamos bases federais (ANA, ICMBio, FUNAI, INCRA/SIGEF, CAR, SGB, DNIT, MapBiomas, IBGE) e, quando o município publica, lote e zoneamento oficiais.",
  },
  {
    title: "3. Legislação versionada",
    text: "Leis são guardadas por versão e vigência, divididas em artigos. Parâmetros como coeficiente de aproveitamento e recuos apontam para o artigo que os define.",
  },
  {
    title: "4. Revisão humana",
    text: "Parâmetros extraídos automaticamente só aparecem como confirmados depois de conferidos por um profissional. Toda revisão fica registrada.",
  },
  {
    title: "5. Resposta com evidência",
    text: "O dossiê e a A.I Cidades mostram a fonte, a data e a situação de cada informação — incluindo o que não foi possível determinar.",
  },
];

export default function HowItWorks() {
  return (
    <section className="section">
      <div className="container narrow">
        <h1 className="page-title">Como funciona</h1>
        <ol className="steps">
          {STEPS.map((s) => (
            <li key={s.title}>
              <h2>{s.title}</h2>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
        <div className="callout">
          <h2>Limites que assumimos</h2>
          <p>
            Nenhuma plataforma tem lote e zoneamento de todos os 5.570 municípios: muitos não
            publicam esses dados em formato aberto. Nesses casos mostramos o contexto federal e
            deixamos claro o que falta. O relatório é inteligência técnica e não substitui
            certidão, consulta formal à prefeitura ou responsabilidade técnica.
          </p>
        </div>
        <p className="center"><Link href="/contato" className="btn primary lg">Solicitar demonstração</Link></p>
      </div>
    </section>
  );
}
