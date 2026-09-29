import type { Metadata } from "next";
import { COMPANY } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Política de Privacidade",
  alternates: { canonical: "/privacidade" },
};

export default function Privacy() {
  return (
    <section className="section">
      <article className="container narrow legal">
        <h1 className="page-title">Política de Privacidade</h1>
        {!COMPANY.reviewed && (
          <p className="callout">Versão preliminar, em revisão jurídica.</p>
        )}
        <p className="muted">Atualizada em {COMPANY.updatedAt}.</p>

        <h2>1. Quem somos</h2>
        <p>
          {COMPANY.name}, CNPJ {COMPANY.cnpj}, {COMPANY.address}, é a controladora dos dados
          pessoais tratados no site e na plataforma LoteDiretor Brasil, nos termos da Lei nº
          13.709/2018 (LGPD). Encarregado (DPO): {COMPANY.dpoEmail}.
        </p>

        <h2>2. Dados que tratamos</h2>
        <ul>
          <li><strong>Contato pelo site:</strong> nome, e-mail, organização, segmento e mensagem.</li>
          <li><strong>Conta na plataforma:</strong> identificador do provedor de login, nome e e-mail. Senhas e fatores de autenticação ficam no provedor de identidade e não são acessados por nós.</li>
          <li><strong>Uso da plataforma:</strong> imóveis salvos, anotações e registros de atividade da sua organização.</li>
          <li><strong>Perguntas à A.I Cidades:</strong> guardamos apenas um resumo criptográfico (hash) e o tamanho da pergunta, a resposta classificada e as fontes citadas — não o texto da pergunta.</li>
          <li><strong>Segurança:</strong> para limitar abusos no formulário usamos um identificador derivado do endereço IP que muda diariamente; o IP em si não é armazenado.</li>
        </ul>

        <h2>3. Finalidades e bases legais</h2>
        <ul>
          <li>Responder contatos e demonstrações — procedimentos preliminares a contrato, a seu pedido (art. 7º, V).</li>
          <li>Prestar o serviço contratado — execução de contrato (art. 7º, V).</li>
          <li>Segurança, prevenção a fraude e auditoria — legítimo interesse (art. 7º, IX) e cumprimento de obrigação legal (art. 7º, II).</li>
        </ul>

        <h2>4. Dados de terceiros nos relatórios</h2>
        <p>
          Os dossiês usam bases públicas oficiais. Não exibimos titularidade de imóveis,
          CPF/CNPJ de proprietários ou dados pessoais de cadastros públicos; os conectores são
          configurados para não solicitar esses campos.
        </p>

        <h2>5. Compartilhamento</h2>
        <p>
          Com operadores necessários ao serviço (hospedagem, provedor de identidade e, quando
          você usa a A.I Cidades, o provedor do modelo de linguagem, que recebe a pergunta e os
          trechos de lei selecionados). Não vendemos dados pessoais.
        </p>

        <h2>6. Retenção</h2>
        <p>
          Mantemos os dados pelo tempo necessário às finalidades acima e às obrigações legais.
          Registros de auditoria são mantidos de forma imutável para fins de segurança.
        </p>

        <h2>7. Seus direitos</h2>
        <p>
          Você pode solicitar confirmação, acesso, correção, anonimização, portabilidade,
          eliminação e informações sobre compartilhamento pelo e-mail {COMPANY.dpoEmail}. Você
          também pode peticionar à ANPD.
        </p>

        <h2>8. Segurança</h2>
        <p>
          Login com provedor de identidade e suporte a dois fatores, sessões com cookies
          protegidos, tokens criptografados, isolamento de dados entre organizações no banco
          de dados e registro de auditoria das ações administrativas.
        </p>
      </article>
    </section>
  );
}
