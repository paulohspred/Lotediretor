/** Public URLs of the other apps, configured per environment. */
export const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "https://app.lotediretor.com.br";
export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://www.lotediretor.com.br";

export type ModuleStatus = "disponivel" | "piloto" | "em-desenvolvimento";

export const MODULES: {
  slug: string;
  name: string;
  status: ModuleStatus;
  summary: string;
  bullets: string[];
}[] = [
  {
    slug: "lote-diretor",
    name: "LoteDiretor",
    status: "disponivel",
    summary:
      "Dossiê territorial auditável: o que incide sobre um terreno, de onde veio cada informação e o que ainda precisa ser confirmado.",
    bullets: [
      "Qualquer ponto do Brasil resolvido para o município oficial (malha IBGE)",
      "Contexto federal: hidrografia, unidades de conservação, terras indígenas, SIGEF, CAR, risco geológico, rodovias, uso do solo",
      "Lote, cadastro e zoneamento nas cidades com dados municipais integrados",
      "Parâmetros urbanísticos com o artigo de lei que os sustenta",
    ],
  },
  {
    slug: "ai-cidades",
    name: "A.I Cidades",
    status: "disponivel",
    summary:
      "Pergunte sobre a legislação urbanística e receba respostas com citação obrigatória do artigo — ou “não determinado” quando a lei cadastrada não permite concluir.",
    bullets: [
      "Respostas sempre fundamentadas em trechos de lei e parâmetros cadastrados",
      "Citações verificadas automaticamente: fonte inexistente é descartada",
      "Parâmetros ainda não revisados por profissional aparecem sinalizados",
      "Rastreabilidade de cada resposta para auditoria",
    ],
  },
  {
    slug: "imovel-360",
    name: "Imóvel 360",
    status: "piloto",
    summary:
      "Carteira de imóveis da sua equipe: salve terrenos analisados, anote diligências e volte ao dossiê a qualquer momento.",
    bullets: [
      "Meus imóveis por organização, com isolamento entre clientes",
      "Anotações e histórico de atividade",
      "Mercado, AVM e CRM completos em desenvolvimento",
    ],
  },
  {
    slug: "re-rural",
    name: "RE Rural",
    status: "em-desenvolvimento",
    summary:
      "Relacionar CAR, SIGEF, SNCR, CIB, embargos e monitoramento para imóveis rurais sem confundir identidades jurídicas.",
    bullets: ["Hoje: CAR, SIGEF e terras indígenas no contexto do ponto", "Grafo de identidades e sobreposições: em desenvolvimento"],
  },
  {
    slug: "condominio",
    name: "Condomínio",
    status: "em-desenvolvimento",
    summary: "Convenção, regimento e atas transformados em regras consultáveis com citação.",
    bullets: ["Planejado sobre o mesmo motor jurídico e de IA"],
  },
  {
    slug: "energia-solar",
    name: "Energia Solar",
    status: "em-desenvolvimento",
    summary: "Potencial fotovoltaico, geração, conta de energia e retorno financeiro por imóvel.",
    bullets: ["Planejado"],
  },
  {
    slug: "ai-tec",
    name: "A.I TEC",
    status: "em-desenvolvimento",
    summary: "Estudos de massa e implantação gerados a partir das restrições legais verificadas.",
    bullets: ["Planejado"],
  },
];

export const STATUS_LABEL: Record<ModuleStatus, string> = {
  disponivel: "Disponível",
  piloto: "Em piloto",
  "em-desenvolvimento": "Em desenvolvimento",
};
