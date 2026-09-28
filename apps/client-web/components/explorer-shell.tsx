import { ExplorerMap } from "./explorer-map";

const rail = [
  "Dashboard",
  "Explorer",
  "Imóveis",
  "Empreendimentos",
  "Análises",
  "Relatórios",
  "CRM",
];

export function ExplorerShell() {
  return (
    <main className="app-shell">
      <aside className="app-rail" aria-label="Navegação principal">
        <div className="brand-mark">LD</div>
        <nav>
          {rail.map((item) => (
            <button
              className={item === "Explorer" ? "rail-item active" : "rail-item"}
              key={item}
              type="button"
            >
              {item}
            </button>
          ))}
        </nav>
        <button className="rail-item more" type="button">Mais</button>
      </aside>

      <section className="app-stage">
        <header className="app-head">
          <label className="global-search">
            <span>Buscar imóvel, endereço, CIB ou inscrição</span>
            <input
              aria-label="Busca global"
              placeholder="Rua, número, CEP ou identificação cadastral"
            />
          </label>
          <div className="head-actions">
            <button type="button">Data-base: hoje</button>
            <button type="button">Workspace</button>
            <button type="button">Perfil</button>
          </div>
        </header>

        <section className="explorer-layout">
          <aside className="explorer-panel">
            <div className="eyebrow">Explorer</div>
            <h1>Terreno e contexto</h1>
            <p className="muted">
              Resolva o lote, ative camadas e abra a ficha auditável.
            </p>

            <div className="panel-card">
              <h2>Camadas</h2>
              <button type="button">Território</button>
              <button type="button">Urbanismo</button>
              <button type="button">Risco e ambiente</button>
              <button type="button">Infraestrutura</button>
              <button type="button">Rural</button>
            </div>

            <div className="panel-card">
              <h2>Imóvel selecionado</h2>
              <p className="muted">
                Selecione um terreno no mapa ou use a busca global.
              </p>
            </div>
          </aside>

          <div className="map-stage">
            <ExplorerMap />
            <div className="map-context-bar">
              <span>Nenhum lote selecionado</span>
              <span>Mapa 2D · MapLibre</span>
            </div>
          </div>

          <aside className="detail-panel">
            <div className="eyebrow">Ficha</div>
            <h2>Análise territorial</h2>
            <div className="empty-state">
              A ficha aparecerá aqui com identificação, zoneamento, restrições,
              topografia, infraestrutura, evidências e pendências.
            </div>
          </aside>
        </section>
      </section>
    </main>
  );
}
