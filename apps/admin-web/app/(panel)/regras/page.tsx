import { RuleReview } from "@/components/rule-review";

export const dynamic = "force-dynamic";

export default function RulesPage() {
  return (
    <>
      <h1>Revisão de regras urbanísticas</h1>
      <p className="muted">
        Parâmetros extraídos automaticamente só aparecem como confirmados para clientes
        depois desta revisão. Toda decisão exige uma nota e fica na auditoria.
      </p>
      <RuleReview />
    </>
  );
}
