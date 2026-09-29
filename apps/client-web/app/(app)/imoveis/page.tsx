import { PropertiesList } from "@/components/properties-list";
import { requireViewer } from "@/lib/server/viewer";

export const dynamic = "force-dynamic";

export default async function PropertiesPage() {
  await requireViewer("/imoveis");
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <div className="eyebrow">Carteira</div>
          <h1>Meus imóveis</h1>
        </div>
      </header>
      <PropertiesList />
    </div>
  );
}
