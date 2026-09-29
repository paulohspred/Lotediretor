"use client";

import { FormEvent, useState } from "react";

const SEGMENTS = [
  "Arquitetura",
  "Engenharia",
  "Incorporação",
  "Corretagem",
  "Avaliação/perícia",
  "Banco/investidor",
  "Prefeitura",
  "Profissional",
  "Empresa",
  "Outro",
];

export function ContactForm({ initialSegment }: { initialSegment?: string }) {
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setState("sending");
    setError(null);
    try {
      const response = await fetch("/api/lead", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: form.get("name"),
          email: form.get("email"),
          organization: form.get("organization"),
          segment: form.get("segment"),
          message: form.get("message"),
          consent_privacy: form.get("consent") === "on",
          website: form.get("website"),
          source_page: "/contato",
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        setError(body.message ?? "Não foi possível enviar. Tente novamente.");
        setState("error");
        return;
      }
      setState("sent");
    } catch {
      setError("Não foi possível enviar. Verifique sua conexão.");
      setState("error");
    }
  }

  if (state === "sent") {
    return (
      <div className="form-success" role="status">
        <h2>Mensagem recebida</h2>
        <p>Obrigado! Nossa equipe responde pelo e-mail informado.</p>
      </div>
    );
  }

  return (
    <form className="contact-form" onSubmit={submit} noValidate={false}>
      <label>
        <span>Nome</span>
        <input name="name" required minLength={2} maxLength={120} autoComplete="name" />
      </label>
      <label>
        <span>E-mail</span>
        <input name="email" type="email" required maxLength={200} autoComplete="email" />
      </label>
      <label>
        <span>Organização (opcional)</span>
        <input name="organization" maxLength={160} autoComplete="organization" />
      </label>
      <label>
        <span>Segmento</span>
        <select name="segment" defaultValue={initialSegment && SEGMENTS.includes(initialSegment) ? initialSegment : "Outro"}>
          {SEGMENTS.map((s) => <option key={s}>{s}</option>)}
        </select>
      </label>
      <label className="full">
        <span>Como podemos ajudar? Diga o município e o tipo de decisão.</span>
        <textarea name="message" required minLength={5} maxLength={4000} rows={5} />
      </label>
      {/* Honeypot: hidden from people, tempting to bots. */}
      <label className="hp" aria-hidden="true">
        <span>Não preencha</span>
        <input name="website" tabIndex={-1} autoComplete="off" />
      </label>
      <label className="consent full">
        <input type="checkbox" name="consent" required />
        <span>
          Li e concordo com a <a href="/privacidade" target="_blank">Política de Privacidade</a>.
          Usaremos seus dados apenas para responder a este contato.
        </span>
      </label>
      {error && <p className="form-error full" role="alert">{error}</p>}
      <button className="btn primary lg full" type="submit" disabled={state === "sending"}>
        {state === "sending" ? "Enviando…" : "Enviar"}
      </button>
    </form>
  );
}
