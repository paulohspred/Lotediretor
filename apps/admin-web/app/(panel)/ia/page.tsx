import { adminJson } from "@/lib/admin";

export const dynamic = "force-dynamic";

type Trace = {
  trace_id: string; created_at: string; organization: string | null; municipality: string | null;
  mode: string; status: string; model: string | null; latency_ms: number;
  input_tokens: number | null; output_tokens: number | null; retrieved: number; cited: number;
  validator_flags: string[]; feedback: number | null; question_chars: number;
};

export default async function AiPage() {
  const data = await adminJson<{ items: Trace[] }>("/ai/traces?limit=100");
  return (
    <>
      <h1>A.I Cidades · rastreabilidade</h1>
      <p className="muted">
        Cada resposta registra fontes recuperadas e citadas, modelo, custo e o resultado do
        validador. O texto das perguntas não é armazenado (apenas hash e tamanho).
      </p>
      {!data ? <p className="error">Falha ao carregar.</p> : (
        <table className="table">
          <thead><tr><th>Quando</th><th>Organização</th><th>Município</th><th>Modo</th><th>Status</th><th>Fontes</th><th>Tokens</th><th>Latência</th><th>Validador</th><th>Aval.</th></tr></thead>
          <tbody>
            {data.items.map((t) => (
              <tr key={t.trace_id}>
                <td>{new Date(t.created_at).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" })}</td>
                <td>{t.organization ?? "—"}</td><td>{t.municipality ?? "—"}</td>
                <td>{t.mode}</td><td>{t.status}</td>
                <td>{t.cited}/{t.retrieved}</td>
                <td>{t.input_tokens !== null ? `${t.input_tokens}+${t.output_tokens}` : "—"}</td>
                <td>{t.latency_ms} ms</td>
                <td>{t.validator_flags.length ? t.validator_flags.join(", ") : "ok"}</td>
                <td>{t.feedback === 1 ? "👍" : t.feedback === -1 ? "👎" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
