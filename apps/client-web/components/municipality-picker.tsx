"use client";

import { useEffect, useRef, useState } from "react";
import type { ApiMunicipality } from "@/lib/cities";

type Props = {
  currentLabel: string;
  onSelect: (municipality: ApiMunicipality) => void;
};

/**
 * Search any of Brazil's municipalities (IBGE mesh) by name. Debounced, with
 * request cancellation so a slow earlier query never overwrites a newer one.
 */
export function MunicipalityPicker({ currentLabel, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ApiMunicipality[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const q = query.trim();
    if (q.length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(
          `/api/municipalities?${new URLSearchParams({ q })}`,
          { signal: controller.signal },
        );
        const body = (await response.json()) as {
          results?: ApiMunicipality[];
          message?: string;
        };
        if (!response.ok) {
          setResults([]);
          setMessage(body.message ?? "Busca de municípios indisponível.");
          return;
        }
        setResults(body.results ?? []);
        setActive(0);
        setMessage(
          body.results?.length ? null : "Nenhum município encontrado.",
        );
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          setMessage("Busca de municípios indisponível.");
        }
      }
    }, 200);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query, open]);

  function choose(municipality: ApiMunicipality) {
    onSelect(municipality);
    setOpen(false);
    setQuery("");
    setResults([]);
  }

  const tooShort = query.trim().length < 2;
  const visibleResults = tooShort ? [] : results;
  const visibleMessage = tooShort
    ? "Digite ao menos 2 letras do município."
    : message;

  if (!open) {
    return (
      <button
        type="button"
        className="municipality-trigger"
        aria-label={`Município: ${currentLabel}. Trocar município`}
        onClick={() => {
          setOpen(true);
          window.setTimeout(() => inputRef.current?.focus(), 0);
        }}
      >
        {currentLabel}
      </button>
    );
  }

  return (
    <div className="municipality-picker">
      <input
        ref={inputRef}
        role="combobox"
        aria-expanded={visibleResults.length > 0}
        aria-controls="municipality-options"
        aria-activedescendant={
          visibleResults[active] ? `municipality-${visibleResults[active].ibge_code}` : undefined
        }
        aria-label="Buscar município"
        placeholder="Buscar município do Brasil"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setActive((i) => Math.min(i + 1, visibleResults.length - 1));
          }
          if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((i) => Math.max(i - 1, 0));
          }
          if (event.key === "Enter" && visibleResults[active]) {
            event.preventDefault();
            choose(visibleResults[active]);
          }
        }}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
      />
      <ul id="municipality-options" role="listbox" className="municipality-options">
        {visibleResults.map((item, index) => (
          <li
            key={item.ibge_code}
            id={`municipality-${item.ibge_code}`}
            role="option"
            aria-selected={index === active}
            className={index === active ? "active" : undefined}
            onMouseDown={(event) => {
              event.preventDefault();
              choose(item);
            }}
          >
            <span>
              {item.name} · {item.uf}
            </span>
            {item.capabilities.parcel_resolver && <small>lotes</small>}
          </li>
        ))}
        {visibleMessage && (
          <li className="municipality-message">{visibleMessage}</li>
        )}
      </ul>
    </div>
  );
}
