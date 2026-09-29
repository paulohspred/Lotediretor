import type { Metadata } from "next";
import { SiteFooter, SiteHeader } from "@/components/chrome";
import { SITE_URL } from "@/lib/content";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "LoteDiretor Brasil — inteligência urbanística auditável",
    template: "%s · LoteDiretor Brasil",
  },
  description:
    "Descubra o que incide sobre qualquer terreno do Brasil, com a fonte de cada informação: legislação urbanística com citação, contexto federal, lote e zoneamento.",
  openGraph: {
    type: "website",
    locale: "pt_BR",
    siteName: "LoteDiretor Brasil",
  },
  alternates: { canonical: "/" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>
        <a className="skip" href="#conteudo">Pular para o conteúdo</a>
        <SiteHeader />
        <main id="conteudo">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
