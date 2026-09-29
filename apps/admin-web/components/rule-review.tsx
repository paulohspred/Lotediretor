"use client";

import { useCallback, useEffect, useState } from "react";

type Rule = {
  rule_id: string;
  municipality: string;
  ibge_code: string;
  zone_code: string;
  parameter: string;
  use_condition: string;
  value: string | null;
  unit: string;
  no_restriction: boolean;
  status: string;
  evidence_excerpt: string;
  provision_path: string;
  page_start: number | null;
  document_title: string;
  canonical_url: string | null;
  provision_text: string;
  reviewed_by: string | null;
  review_note: string | null;
};

const LABEL: Record<string, string> = {
  CA_MINIMO: "CA mínimo", CA_BASICO: "CA básico", CA_MAXIMO: "CA máximo",
  TO_MAXIMA: "Taxa de ocupação", TP_MINIMA: "Permeabilidade", GABARITO_M: "Altura máxima",
  PAVIMENTOS_MAX: "Pavimentos", RECUO_FRONTAL_M: "Recuo frontal", RECUO_LATERAL_M: "Recuo lateral",
  RECUO_FUNDOS_M: "Recuo de fundos", LOTE_MINIMO_M2: "Lote mínimo", TESTADA_MINIMA_M: "Testada mínima",
};
const UNIT: Record<string, string> = { ratio: "", percent: "%", m: " m", m2: " m²", count: "" };

function value(r: Rule) {
  if (r.no_restriction) return "sem restrição";
  return `${Number(r.value).toLocaleString("pt-BR")}${UNIT[r.unit] ?? ""}`;
}

function highlight(text: string, excerpt: string) {
  const core = excerpt.replace(/\s+/g, " ").trim().slice(0, 60);
  const i = text.replace(/\s+/g, " ").indexOf(core);
  if (!core || i < 0) return <>{text}</>;
  const flat = text.replace(/\s+/g, " ");
  return (
    <>
      {flat.slice(Math.max(0, i - 400), i)}
      <mark>{flat.slice(i, i + excerpt.length)}</mark>
      {flat.slice(i + excerpt.length, i + excerpt.length + 400)}
    </>
  );
}

export function RuleReview() {
  const [status, setStatus] = useState("CANDIDATE");
  const [ibge, setIbge] = useState("");
  const [zone, setZone] = useState("");
  const [items, setItems] = useState<Rule[] | null>(null);
  const [selected, setSelected] = useState<Rule | null>(null);
  const [note, setNote] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ status, limit: "500" });
    if (/^\d{7}$/.test(ibge)) params.set("ibge", ibge);
    if (zone.trim()) params.set("zone", zone.trim());
    const response = await fetch(`/api/admin/rules?${params}`);
    const body = await response.json().catch(() => ({}));
    setItems(response.ok ? body.items : []);
    if (!response.ok) setMessage(body.message ?? "Falha ao carregar a fila.");
  }, [status, ibge, zone]);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ status, limit: "500" });
    fetch(`/api/admin/rules?${params}`, { signal: controller.signal })
      .then((r) => r.json())
      .then((body) => setItems(body.items ?? []))
      .catch(() => undefined);
    return () => controller.abort();
  }, [status]);

  async function decide(decision: "confirm" | "reject" | "conflict") {
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    const response = await fetch(`/api/admin/rules/${selected.rule_id}/review`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ decision, note }),
    });
    const body = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage(body.message ?? "Não foi possível registrar a decisão.");
      return;
    }
    setMessage(`Regra ${LABEL[selected.parameter] ?? selected.parameter} (${selected.zone_code}) → ${body.status}`);
    setNote("");
    setSelected(null);
    await load();
  }

  return (
    <div className="review">
      <div className="filters">
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Situação">
          <option value="CANDIDATE">Aguardando revisão</option>
          <option value="CONFIRMED">Confirmadas</option>
          <option value="CONFLICTING">Em conflito</option>
          <option value="REJECTED">Rejeitadas</option>
        </select>
        <input placeholder="IBGE (7 dígitos)" value={ibge} onChange={(e) => setIbge(e.target.value)} aria-label="Código IBGE" />
        <input placeholder="Zona" value={zone} onChange={(e) => setZone(e.target.value)} aria-label="Zona" />
        <button className="btn" type="button" onClick={() => void load()}>Filtrar</button>
        <span className="muted">{items ? `${items.length} regra(s)` : "Carregando…"}</span>
      </div>
      {message && <p className="notice" role="status">{message}</p>}
      <div className="review-grid">
        <table className="table">
          <thead>
            <tr><th>Município</th><th>Zona</th><th>Parâmetro</th><th>Uso</th><th>Valor</th><th>Fonte</th></tr>
          </thead>
          <tbody>
            {(items ?? []).map((r) => (
              <tr key={r.rule_id}
                  className={selected?.rule_id === r.rule_id ? "selected" : undefined}
                  onClick={() => { setSelected(r); setNote(""); }}
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && setSelected(r)}>
                <td>{r.municipality}</td>
                <td>{r.zone_code}</td>
                <td>{LABEL[r.parameter] ?? r.parameter}</td>
                <td>{r.use_condition === "GERAL" ? "—" : r.use_condition}</td>
                <td><strong>{value(r)}</strong></td>
                <td>{r.provision_path}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <aside className="review-detail">
          {!selected ? (
            <p className="muted">Selecione uma regra para ver o texto legal e decidir.</p>
          ) : (
            <>
              <h3>{LABEL[selected.parameter] ?? selected.parameter} · {selected.zone_code}</h3>
              <p><strong>{value(selected)}</strong>{selected.use_condition !== "GERAL" && ` — ${selected.use_condition}`}</p>
              <p className="muted">
                {selected.document_title}, {selected.provision_path}
                {selected.page_start ? `, p. ${selected.page_start}` : ""}
                {selected.canonical_url && (
                  <> · <a href={selected.canonical_url} target="_blank" rel="noreferrer">documento oficial</a></>
                )}
              </p>
              <blockquote className="legal-text">{highlight(selected.provision_text, selected.evidence_excerpt)}</blockquote>
              {selected.reviewed_by && (
                <p className="muted">Última revisão: {selected.reviewed_by} — {selected.review_note}</p>
              )}
              <label className="field">
                <span>O que você conferiu (obrigatório)</span>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000}
                          placeholder="Ex.: Conferido com o art. 35, inciso IV, do PDF oficial, p. 16" />
              </label>
              <div className="actions">
                <button className="btn primary" disabled={busy || note.trim().length < 10} onClick={() => void decide("confirm")}>Confirmar</button>
                <button className="btn" disabled={busy || note.trim().length < 10} onClick={() => void decide("conflict")}>Marcar conflito</button>
                <button className="btn danger" disabled={busy || note.trim().length < 10} onClick={() => void decide("reject")}>Rejeitar</button>
              </div>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
