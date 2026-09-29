import type { Metadata } from "next";
import { ContactForm } from "@/components/contact-form";

export const metadata: Metadata = {
  title: "Contato",
  description: "Solicite uma demonstração do LoteDiretor para o seu município.",
  alternates: { canonical: "/contato" },
};

export default async function Contact({ searchParams }: { searchParams: Promise<{ segmento?: string }> }) {
  const { segmento } = await searchParams;
  return (
    <section className="section">
      <div className="container narrow">
        <h1 className="page-title">Fale com a equipe</h1>
        <p className="section-lead">
          Conte o município e a decisão que você precisa tomar. Respondemos com uma
          demonstração usando dados reais da cidade, quando disponíveis.
        </p>
        <ContactForm initialSegment={segmento} />
      </div>
    </section>
  );
}
