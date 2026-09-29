import Link from "next/link";
import { APP_URL, MODULES, STATUS_LABEL } from "@/lib/content";

export default function Home() {
  return (
    <>
      <section className="hero">
        <div className="container hero-inner">
          <p className="kicker">Inteligência urbanística e territorial</p>
          <h1>
            O que pode ser feito em um terreno — <span>com a fonte de cada resposta.</span>
          </h1>
          <p className="lead">
            O LoteDiretor reúne legislação urbanística, dados municipais e bases federais em um
            dossiê auditável. Cada conclusão mostra de onde veio, quando foi consultada e o que
            ainda precisa de confirmação.
          </p>
          <div className="hero-cta">
            <Link href="/contato" className="btn primary lg">Solicitar demonstração</Link>
            <a href={`${APP_URL}/entrar`} className="btn ghost lg">Entrar na plataforma</a>
          </div>
          <ul className="hero-proof">
            <li><strong>Brasil inteiro</strong><span>todo ponto resolvido para o município oficial do IBGE</span></li>
            <li><strong>Lei citada</strong><span>parâmetros com artigo, versão e vigência</span></li>
            <li><strong>Sem chute</strong><span>“não determinado” quando falta base legal</span></li>
          </ul>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <h2 className="section-title">Para quem decide sobre terrenos</h2>
          <div className="grid-3">
            <article className="card">
              <h3>Arquitetos e engenheiros</h3>
              <p>Zona, parâmetros urbanísticos e restrições ambientais antes de começar o estudo, com a lei aberta ao lado.</p>
            </article>
            <article className="card">
              <h3>Incorporadores e investidores</h3>
              <p>Triagem de terrenos com evidência: o que é confirmado, o que é inferido e o que exige diligência.</p>
            </article>
            <article className="card">
              <h3>Corretores e avaliadores</h3>
              <p>Qualificação do imóvel com linguagem clara e referências oficiais que você pode compartilhar.</p>
            </article>
          </div>
        </div>
      </section>

      <section className="section alt">
        <div className="container two">
          <div>
            <h2 className="section-title">Evidência em primeiro lugar</h2>
            <p>
              Relatórios imobiliários costumam misturar dado oficial, estimativa e opinião. No
              LoteDiretor, cada informação carrega sua natureza:
            </p>
            <ul className="checklist">
              <li><strong>Confirmado</strong> — fonte oficial vigente, sem conflito.</li>
              <li><strong>Aguardando revisão</strong> — extraído do texto legal, ainda não conferido por um profissional.</li>
              <li><strong>Não disponível</strong> — a fonte não existe, não é pública ou não foi integrada.</li>
              <li><strong>Conflitante</strong> — fontes divergem; mostramos as duas.</li>
            </ul>
          </div>
          <div className="evidence-card" aria-label="Exemplo de parâmetro com evidência">
            <span className="pill">Parâmetro urbanístico</span>
            <p className="evidence-value">Recuo frontal · 5,00 m</p>
            <p className="evidence-source">Lei Complementar nº 565/2023, art. 35, inc. IV</p>
            <p className="evidence-status">Situação: aguardando revisão profissional</p>
            <p className="evidence-note">Exemplo ilustrativo do formato exibido no dossiê.</p>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <h2 className="section-title">Módulos</h2>
          <p className="section-lead">Mostramos o que já funciona e o que está em construção — sem promessa vaga.</p>
          <div className="grid-3">
            {MODULES.map((m) => (
              <article className="card module" key={m.slug}>
                <span className={`status ${m.status}`}>{STATUS_LABEL[m.status]}</span>
                <h3>{m.name}</h3>
                <p>{m.summary}</p>
              </article>
            ))}
          </div>
          <p className="center"><Link href="/solucoes" className="btn ghost-dark">Ver detalhes dos módulos</Link></p>
        </div>
      </section>

      <section className="cta-band">
        <div className="container cta-inner">
          <div>
            <h2>Veja um dossiê do seu município</h2>
            <p>Conte qual cidade e que tipo de decisão você precisa tomar. Respondemos com uma demonstração.</p>
          </div>
          <Link href="/contato" className="btn primary lg">Falar com a equipe</Link>
        </div>
      </section>
    </>
  );
}
