"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Visão geral" },
  { href: "/regras", label: "Revisão de regras" },
  { href: "/organizacoes", label: "Organizações" },
  { href: "/usuarios", label: "Usuários" },
  { href: "/ia", label: "IA · rastreabilidade" },
  { href: "/cobertura", label: "Cobertura" },
  { href: "/leads", label: "Leads" },
  { href: "/auditoria", label: "Auditoria" },
];

export function AdminNav() {
  const pathname = usePathname();
  return (
    <nav className="admin-nav">
      {ITEMS.map((item) => {
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        return (
          <Link key={item.href} href={item.href} className={active ? "active" : undefined}
                aria-current={active ? "page" : undefined}>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
