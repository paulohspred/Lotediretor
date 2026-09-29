"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type Property = {
  saved_property_id: string;
  ibge_code: string;
  municipality: string;
  uf: string;
  label: string;
  lat: number;
  lng: number;
  parcel_reference: string | null;
  notes: string | null;
  created_at: string;
};

export function PropertiesList() {
  const [items, setItems] = useState<Property[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const load = useCallback(async () => {
    const response = await fetch("/api/properties");
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      setError(body.message ?? "Não foi possível carregar os imóveis.");
      setItems([]);
      return;
    }
    setError(null);
    setItems(body.properties ?? []);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/properties")
      .then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (cancelled) return;
        if (!response.ok) {
          setError(body.message ?? "Não foi possível carregar os imóveis.");
          setItems([]);
        } else {
          setItems(body.properties ?? []);
        }
      })
      .catch(() => !cancelled && setError("Serviço indisponível."));
    return () => {
      cancelled = true;
    };
  }, []);

  async function remove(id: string) {
    if (!window.confirm("Remover este imóvel da lista? A análise registrada não é apagada.")) return;
    const response = await fetch(`/api/properties/${id}`, { method: "DELETE" });
    if (!response.ok) setError("Não foi possível remover.");
    await load();
  }

  async function saveNotes(id: string) {
    const response = await fetch(`/api/properties/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ notes: draft }),
    });
    if (!response.ok) setError("Não foi possível salvar a anotação.");
    setEditing(null);
    await load();
  }

  if (items === null) return <p className="muted">Carregando…</p>;
  return (
    <>
      {error && <p className="login-error" role="alert">{error}</p>}
      {items.length === 0 ? (
        <div className="empty-state">
          Nenhum imóvel salvo ainda. Selecione um terreno no{" "}
          <Link href="/explorer">Explorer</Link> e clique em “Salvar em Meus imóveis”.
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Imóvel</th>
              <th>Município</th>
              <th>Referência</th>
              <th>Anotações</th>
              <th aria-label="Ações" />
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.saved_property_id}>
                <td>
                  <strong>{p.label}</strong>
                  <small>
                    {new Date(p.created_at).toLocaleDateString("pt-BR", {
                      timeZone: "America/Sao_Paulo",
                    })}
                  </small>
                </td>
                <td>
                  {p.municipality} · {p.uf}
                </td>
                <td>{p.parcel_reference ?? "—"}</td>
                <td>
                  {editing === p.saved_property_id ? (
                    <div className="inline-edit">
                      <textarea
                        value={draft}
                        maxLength={4000}
                        onChange={(e) => setDraft(e.target.value)}
                        aria-label="Anotações"
                      />
                      <button type="button" onClick={() => void saveNotes(p.saved_property_id)}>
                        Salvar
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => {
                        setEditing(p.saved_property_id);
                        setDraft(p.notes ?? "");
                      }}
                    >
                      {p.notes ? p.notes.slice(0, 80) : "Adicionar"}
                    </button>
                  )}
                </td>
                <td className="row-actions">
                  <Link href={`/explorer?lat=${p.lat}&lng=${p.lng}`}>Abrir</Link>
                  <button
                    type="button"
                    className="link-button danger"
                    onClick={() => void remove(p.saved_property_id)}
                  >
                    Remover
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
