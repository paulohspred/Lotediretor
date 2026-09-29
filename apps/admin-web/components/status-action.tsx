"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/** Change a status through the admin BFF; asks for a reason when required. */
export function StatusAction({
  endpoint,
  current,
  options,
  requireReason = false,
}: {
  endpoint: string;
  current: string;
  options: string[];
  requireReason?: boolean;
}) {
  const router = useRouter();
  const [value, setValue] = useState(current);
  const [error, setError] = useState<string | null>(null);
  return (
    <span className="status-action">
      <select
        value={value}
        aria-label="Alterar situação"
        onChange={async (event) => {
          const next = event.target.value;
          let reason: string | null = null;
          if (requireReason) {
            reason = window.prompt(`Motivo para mudar de ${current} para ${next} (mín. 10 caracteres):`);
            if (!reason) return;
          }
          const response = await fetch(endpoint, {
            method: "PATCH",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ status: next, reason }),
          });
          if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            setError(body.message ?? "Falhou");
            return;
          }
          setValue(next);
          setError(null);
          router.refresh();
        }}
      >
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
      {error && <small className="error">{error}</small>}
    </span>
  );
}
