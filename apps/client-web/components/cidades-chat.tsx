"use client";

import { FormEvent, useState } from "react";
import { MunicipalityPicker } from "./municipality-picker";
import type { ApiMunicipality } from "@/lib/cities";

type Citation = {
  id: string;
  kind: "provision" | "rule";
  document_title: string;
  path: string;
  page: number | null;
  excerpt: string;
  url: string | null;
  review_status: string;
};

type Answer = {
  trace_id: string;
  mode: "LLM" | "RETRIEVAL_ONLY" | "NO_SOURCES";
  status: string;
  answer: string;
  conditions: string[];
  citations: Citation[];
  missing_information: string[];
  uncertainty: string;
  professional_review: string;
  zones: string[];
  disclaimer: string;
  municipality: { name: string; uf: string };
};

type Turn = { question: string; answer?: Answer; error?: string };

const STATUS_LABEL: Record<string, { text: string; tone: string }> = {
  PERMITIDO: { text: "Permitido", tone: "ok" },
  PROIBIDO: { text: "Proibido", tone: "danger" },
  CONDICIONADO: { text: "Condicionado", tone: "warn" },
  NAO_DETERMINADO: { text: "Não determinado", tone: "neutral" },
  CONFLITO: { text: "Conflito entre fontes", tone: "danger" },
  INFORMATIVO: { text: "Informativo", tone: "info" },
};

const REVIEW_LABEL: Record<string, string> = {
  NENHUMA: "Revisão profissional: não necessária",
  RECOMENDADA: "Revisão profissional: recomendada",
  OBRIGATORIA: "Revisão profissional: obrigatória",
};

const EXAMPLES = [
  "Qual o coeficiente de aproveitamento máximo para residência unifamiliar no setor A-04?",
  "Quais são os recuos exigidos para comércio local?",
  "Qual o lote mínimo nesta zona?",
];

export function CidadesChat() {
  const [municipality, setMunicipality] = useState<ApiMunicipality | null>(null);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Record<string, number>>({});

  async function submit(event: FormEvent) {
    event.preventDefault();
    const q = question.trim();
    if (!municipality || q.length < 8 || busy) return;
    setBusy(true);
    setQuestion("");
    setTurns((t) => [...t, { question: q }]);
    try {
      const response = await fetch("/api/ai/cidades", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ibge_code: municipality.ibge_code, question: q }),
      });
      const body = await response.json();
      setTurns((t) =>
        t.map((turn, i) =>
          i === t.length - 1
            ? response.ok
              ? { ...turn, answer: body as Answer }
              : { ...turn, error: body.message ?? "Não foi possível responder." }
            : turn,
        ),
      );
    } catch {
      setTurns((t) =>
        t.map((turn, i) => (i === t.length - 1 ? { ...turn, error: "Serviço indisponível." } : turn)),
      );
    } finally {
      setBusy(false);
    }
  }

  async function rate(traceId: string, value: 1 | -1) {
    setFeedback((f) => ({ ...f, [traceId]: value }));
    await fetch(`/api/ai/feedback/${traceId}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ value }),
    }).catch(() => undefined);
  }

  return (
    <div className="chat">
      <div className="chat-context">
        <span>Município</span>
        <MunicipalityPicker
          currentLabel={municipality ? `${municipality.name} · ${municipality.uf}` : "Escolher município"}
          onSelect={(m) => {
            setMunicipality(m);
            setTurns([]);
          }}
        />
      </div>

      <div className="chat-log" aria-live="polite">
        {turns.length === 0 && (
          <div className="chat-empty">
            <p>
              Pergunte sobre a legislação urbanística do município. As respostas citam o
              artigo de lei que as sustenta — e dizem “não determinado” quando a legislação
              cadastrada não permite concluir.
            </p>
            <div className="chat-examples">
              {EXAMPLES.map((ex) => (
                <button key={ex} type="button" className="chip" onClick={() => setQuestion(ex)}>
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn, index) => (
          <div key={index} className="chat-turn">
            <div className="chat-question">{turn.question}</div>
            {!turn.answer && !turn.error && <div className="chat-answer muted">Consultando a legislação…</div>}
            {turn.error && <div className="chat-answer login-error" role="alert">{turn.error}</div>}
            {turn.answer && (
              <article className="chat-answer">
                <header>
                  <span className={`status-pill ${STATUS_LABEL[turn.answer.status]?.tone ?? "neutral"}`}>
                    {STATUS_LABEL[turn.answer.status]?.text ?? turn.answer.status}
                  </span>
                  {turn.answer.mode === "RETRIEVAL_ONLY" && <span className="chip">Somente busca</span>}
                  {turn.answer.zones.length > 0 && <span className="chip">Zona {turn.answer.zones.join(", ")}</span>}
                </header>
                <p className="answer-text">{turn.answer.answer}</p>
                {turn.answer.conditions.length > 0 && (
                  <>
                    <h4>Condições</h4>
                    <ul>{turn.answer.conditions.map((c, i) => <li key={i}>{c}</li>)}</ul>
                  </>
                )}
                {turn.answer.missing_information.length > 0 && (
                  <>
                    <h4>O que falta para concluir</h4>
                    <ul>{turn.answer.missing_information.map((c, i) => <li key={i}>{c}</li>)}</ul>
                  </>
                )}
                {turn.answer.citations.length > 0 && (
                  <>
                    <h4>Fundamentação</h4>
                    <ol className="citations">
                      {turn.answer.citations.map((c) => (
                        <li key={c.id}>
                          <div>
                            <strong>{c.document_title}</strong>, {c.path}
                            {c.page ? `, p. ${c.page}` : ""}
                            {(c.review_status === "CANDIDATE" || c.review_status === "PENDING_REVIEW") && (
                              <span className="chip warn">aguardando revisão</span>
                            )}
                          </div>
                          <blockquote>{c.excerpt}</blockquote>
                          {c.url && (
                            <a href={c.url} target="_blank" rel="noreferrer">Documento oficial</a>
                          )}
                        </li>
                      ))}
                    </ol>
                  </>
                )}
                <footer>
                  <span>{REVIEW_LABEL[turn.answer.professional_review] ?? ""}</span>
                  <span>Incerteza: {turn.answer.uncertainty.toLowerCase()}</span>
                  <span className="feedback">
                    <button
                      type="button"
                      aria-pressed={feedback[turn.answer.trace_id] === 1}
                      onClick={() => void rate(turn.answer!.trace_id, 1)}
                      aria-label="Resposta útil"
                    >👍</button>
                    <button
                      type="button"
                      aria-pressed={feedback[turn.answer.trace_id] === -1}
                      onClick={() => void rate(turn.answer!.trace_id, -1)}
                      aria-label="Resposta com problema"
                    >👎</button>
                  </span>
                </footer>
                <p className="disclaimer">{turn.answer.disclaimer}</p>
              </article>
            )}
          </div>
        ))}
      </div>

      <form className="chat-input" onSubmit={submit}>
        <textarea
          aria-label="Sua pergunta"
          placeholder={municipality ? "Pergunte sobre zoneamento, recuos, coeficientes…" : "Escolha um município primeiro"}
          value={question}
          maxLength={1000}
          disabled={!municipality}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <button className="primary-button" type="submit" disabled={!municipality || busy || question.trim().length < 8}>
          {busy ? "Consultando…" : "Perguntar"}
        </button>
      </form>
    </div>
  );
}
