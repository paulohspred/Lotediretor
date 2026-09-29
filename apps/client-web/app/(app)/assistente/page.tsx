import { CidadesChat } from "@/components/cidades-chat";
import { requireViewer } from "@/lib/server/viewer";

export const dynamic = "force-dynamic";

export default async function AssistantPage() {
  await requireViewer("/assistente");
  return (
    <div className="page page-chat">
      <header className="page-head">
        <div>
          <div className="eyebrow">Assistente</div>
          <h1>A.I Cidades</h1>
          <p className="muted">
            Legislação urbanística com citação obrigatória da fonte. Parâmetros ainda não
            revisados por profissional aparecem sinalizados.
          </p>
        </div>
      </header>
      <CidadesChat />
    </div>
  );
}
