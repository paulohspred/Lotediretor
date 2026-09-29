import Link from "next/link";
import { APP_URL } from "@/lib/content";

const NAV = [
  { href: "/solucoes", label: "Soluções" },
  { href: "/prefeituras", label: "Prefeituras" },
  { href: "/como-funciona", label: "Como funciona" },
  { href: "/planos", label: "Planos" },
  { href: "/contato", label: "Contato" },
];

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="container header-inner">
        <Link href="/" className="logo" aria-label="LoteDiretor Brasil — início">
          <span className="logo-mark">LD</span>
          <span>LoteDiretor <em>Brasil</em></span>
        </Link>
        <nav className="main-nav" aria-label="Principal">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href}>{item.label}</Link>
          ))}
        </nav>
        <div className="header-cta">
          <a href={`${APP_URL}/entrar`} className="btn ghost">Entrar</a>
          <Link href="/contato" className="btn primary">Solicitar demonstração</Link>
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="container footer-grid">
        <div>
          <Link href="/" className="logo"><span className="logo-mark">LD</span><span>LoteDiretor <em>Brasil</em></span></Link>
          <p>Inteligência urbanística, territorial e imobiliária auditável.</p>
        </div>
        <div>
          <h3>Produto</h3>
          <Link href="/solucoes">Soluções</Link>
          <Link href="/como-funciona">Como funciona</Link>
          <Link href="/planos">Planos</Link>
        </div>
        <div>
          <h3>Institucional</h3>
          <Link href="/prefeituras">Prefeituras</Link>
          <Link href="/contato">Contato</Link>
        </div>
        <div>
          <h3>Legal</h3>
          <Link href="/privacidade">Política de Privacidade</Link>
          <Link href="/termos">Termos de Uso</Link>
        </div>
      </div>
      <div className="container footer-note">
        <p>
          Os relatórios do LoteDiretor são inteligência técnica e não substituem certidões,
          consultas formais aos órgãos competentes ou responsabilidade técnica profissional.
        </p>
        <p>© {new Date().getFullYear()} LoteDiretor Brasil</p>
      </div>
    </footer>
  );
}
