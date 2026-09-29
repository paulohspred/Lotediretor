import Link from "next/link";
import { requireViewer } from "@/lib/server/viewer";
import { NavLink } from "@/components/nav-link";
import { OrgSwitcher } from "@/components/org-switcher";

export const dynamic = "force-dynamic";

const NAV = [
  { href: "/dashboard", label: "Início", icon: "◧" },
  { href: "/explorer", label: "Explorer", icon: "⌖" },
  { href: "/imoveis", label: "Imóveis", icon: "▦" },
  { href: "/assistente", label: "A.I Cidades", icon: "✦" },
];

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const viewer = await requireViewer("/dashboard");
  const me = viewer.me;
  const initials = (me?.display_name ?? me?.email ?? "LD")
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <main className="app-shell">
      <aside className="app-rail" aria-label="Navegação principal">
        <Link href="/dashboard" className="brand-mark" aria-label="LoteDiretor — início">
          LD
        </Link>
        <nav>
          {NAV.map((item) => (
            <NavLink key={item.href} href={item.href} icon={item.icon} label={item.label} />
          ))}
        </nav>
        <div className="rail-account">
          {me ? (
            <>
              <span className="avatar" title={me.email ?? undefined}>{initials}</span>
              <form action="/auth/logout" method="post">
                <button className="rail-item" type="submit">Sair</button>
              </form>
            </>
          ) : (
            <span className="rail-dev" title="AUTH_MODE=disabled">Modo local</span>
          )}
        </div>
      </aside>
      <div className="app-content">
        {me && me.memberships.length > 1 && (
          <div className="org-bar">
            <OrgSwitcher memberships={me.memberships} activeOrgId={me.active_org.org_id} />
          </div>
        )}
        {viewer.mode === "disabled" && (
          <div className="dev-banner" role="status">
            Autenticação desativada (AUTH_MODE=disabled). Use somente em desenvolvimento local.
          </div>
        )}
        {children}
      </div>
    </main>
  );
}
