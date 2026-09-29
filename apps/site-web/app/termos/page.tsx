import type { Metadata } from "next";
import { COMPANY } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Termos de Uso",
  alternates: { canonical: "/termos" },
};

export default function Terms() {
  return (
    <section className="section">
      <article className="container narrow legal">
        <h1 className="page-title">Termos de Uso</h1>
        {!COMPANY.reviewed && <p className="callout">Versão preliminar, em revisão jurídica.</p>}
        <p className="muted">Atualizados em {COMPANY.updatedAt}.</p>

        <h2>1. O serviço</h2>
        <p>
          O LoteDiretor Brasil, oferecido por {COMPANY.name} (CNPJ {COMPANY.cnpj}), organiza
          informações públicas e legislação urbanística para apoiar análises de imóveis.
        </p>

        <h2>2. Natureza das informações</h2>
        <p>
          Os relatórios e as respostas da A.I Cidades são inteligência técnica. Não substituem
          certidões, consultas formais aos órgãos competentes, projeto aprovado ou
          responsabilidade técnica (ART/RRT). Cada informação indica sua fonte e situação;
          parâmetros marcados como “aguardando revisão” não devem fundamentar decisões sem
          conferência profissional.
        </p>

        <h2>3. Conta e acesso</h2>
        <p>
          Você é responsável pelo uso da sua conta e deve proteger suas credenciais. Podemos
          suspender acessos em caso de uso indevido, risco de segurança ou inadimplência.
        </p>

        <h2>4. Uso permitido</h2>
        <p>
          É vedado usar a plataforma para identificar ou perseguir pessoas, contornar controles
          de acesso de fontes públicas, extrair dados em massa sem autorização contratual ou
          violar a legislação.
        </p>

        <h2>5. Fontes de terceiros</h2>
        <p>
          Dados de órgãos públicos e de terceiros permanecem sujeitos às licenças das
          respectivas fontes, indicadas no produto.
        </p>

        <h2>6. Responsabilidade</h2>
        <p>
          Empregamos cuidado técnico na coleta e apresentação das informações, mas fontes
          oficiais podem conter erros, atrasos ou divergências, que sinalizamos quando
          detectadas.
        </p>

        <h2>7. Contato</h2>
        <p>Dúvidas: {COMPANY.dpoEmail}.</p>
      </article>
    </section>
  );
}
