import { adminJson } from "@/lib/admin";

export const dynamic = "force-dynamic";

type Overview = {
  organizations: number;
  organizations_by_status: Record<string, number> | null;
  users: number;
  users_active_30d: number;
  municipalities: number;
  municipalities_with_parcels: number;
  sources: number;
  legal_documents: number;
  rules_by_status: Record<string, number> | null;
  ai_answers_24h: number;
  ai_by_mode_7d: Record<string, number> | null;
  ai_avg_latency_ms_7d: number | null;
  ai_tokens_30d: number;
  ai_feedback_up: number;
  ai_feedback_down: number;
  ai_downgrades_7d: number;
  leads_new: number;
};

const n = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : new Intl.NumberFormat("pt-BR").format(v);

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="kpi">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  );
}

export default async function OverviewPage() {
  const o = await adminJson<Overview>("/overview");
  if (!o) return <p className="error">Não foi possível carregar os indicadores.</p>;
  const rules = o.rules_by_status ?? {};
  const mode = o.ai_by_mode_7d ?? {};
  const orgs = o.organizations_by_status ?? {};
  return (
    <>
      <h1>Visão geral</h1>
      <section>
        <h2>Clientes</h2>
        <div className="kpis">
          <Kpi label="Organizações" value={n(o.organizations)}
               hint={Object.entries(orgs).map(([k, v]) => `${k}: ${v}`).join(" · ") || undefined} />
          <Kpi label="Usuários" value={n(o.users)} hint={`${n(o.users_active_30d)} ativos em 30 dias`} />
          <Kpi label="Leads novos" value={n(o.leads_new)} />
        </div>
      </section>
      <section>
        <h2>Dados e cobertura</h2>
        <div className="kpis">
          <Kpi label="Municípios na malha" value={n(o.municipalities)} />
          <Kpi label="Municípios com lotes" value={n(o.municipalities_with_parcels)} />
          <Kpi label="Fontes catalogadas" value={n(o.sources)} />
          <Kpi label="Documentos legais" value={n(o.legal_documents)} />
        </div>
      </section>
      <section>
        <h2>Regras urbanísticas</h2>
        <div className="kpis">
          <Kpi label="Aguardando revisão" value={n(rules.CANDIDATE ?? 0)} />
          <Kpi label="Confirmadas" value={n(rules.CONFIRMED ?? 0)} />
          <Kpi label="Em conflito" value={n(rules.CONFLICTING ?? 0)} />
          <Kpi label="Rejeitadas" value={n(rules.REJECTED ?? 0)} />
        </div>
      </section>
      <section>
        <h2>A.I Cidades</h2>
        <div className="kpis">
          <Kpi label="Respostas em 24 h" value={n(o.ai_answers_24h)} />
          <Kpi label="Por modo (7 dias)" value={n((mode.LLM ?? 0) + (mode.RETRIEVAL_ONLY ?? 0) + (mode.NO_SOURCES ?? 0))}
               hint={`LLM ${n(mode.LLM ?? 0)} · só busca ${n(mode.RETRIEVAL_ONLY ?? 0)} · sem fonte ${n(mode.NO_SOURCES ?? 0)}`} />
          <Kpi label="Latência média (7 dias)" value={o.ai_avg_latency_ms_7d ? `${n(o.ai_avg_latency_ms_7d)} ms` : "—"} />
          <Kpi label="Tokens (30 dias)" value={n(o.ai_tokens_30d)} />
          <Kpi label="Avaliações" value={`${n(o.ai_feedback_up)} 👍 · ${n(o.ai_feedback_down)} 👎`} />
          <Kpi label="Respostas rebaixadas (7 dias)" value={n(o.ai_downgrades_7d)}
               hint="Sem citação válida → não determinado" />
        </div>
      </section>
    </>
  );
}
