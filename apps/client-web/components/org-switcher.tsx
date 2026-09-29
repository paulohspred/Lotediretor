"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Membership = { org_id: string; name: string; role: string };

export function OrgSwitcher({
  memberships,
  activeOrgId,
}: {
  memberships: Membership[];
  activeOrgId: string;
}) {
  const router = useRouter();
  const [value, setValue] = useState(activeOrgId);
  return (
    <label className="org-switcher">
      <span>Organização</span>
      <select
        value={value}
        onChange={async (event) => {
          setValue(event.target.value);
          await fetch("/api/org", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ org_id: event.target.value }),
          });
          router.refresh();
        }}
      >
        {memberships.map((m) => (
          <option key={m.org_id} value={m.org_id}>
            {m.name}
          </option>
        ))}
      </select>
    </label>
  );
}
