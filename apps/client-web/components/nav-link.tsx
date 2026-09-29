"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function NavLink({ href, icon, label }: { href: string; icon: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href || pathname.startsWith(`${href}/`);
  return (
    <Link
      href={href}
      className={active ? "rail-item active" : "rail-item"}
      aria-current={active ? "page" : undefined}
    >
      <span aria-hidden="true" className="rail-icon">{icon}</span>
      <span>{label}</span>
    </Link>
  );
}
