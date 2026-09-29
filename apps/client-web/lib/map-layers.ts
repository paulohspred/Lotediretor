export type MapLayerCategory =
  | "territory"
  | "planning"
  | "risk"
  | "environment"
  | "buildings"
  | "terrain"
  | "infrastructure"
  | "rural"
  | "imagery";

export type MapLayerSpec = {
  id: string;
  cityIbge?: string;
  label: string;
  description: string;
  category: MapLayerCategory;
  tiles: string[];
  opacity: number;
  sourceType?: "raster" | "vector";
  sourceLayer?: string;
  lineColor?: string;
  lineWidth?: number;
  renderType?: "line" | "circle";
  circleRadius?: number;
  minZoom?: number;
  maxZoom?: number;
  defaultActive?: boolean;
  attribution: string;
};

function wms(
  base: string,
  layers: string,
  {
    format = "image/png",
    transparent = true,
  }: { format?: string; transparent?: boolean } = {},
): string {
  const params = new URLSearchParams({
    service: "WMS",
    request: "GetMap",
    version: "1.1.1",
    layers,
    styles: "",
    format,
    transparent: transparent ? "true" : "false",
    width: "256",
    height: "256",
    srs: "EPSG:3857",
    bbox: "{bbox-epsg-3857}",
  });
  return `${base}?${params.toString()}`
    .replace("%7Bbbox-epsg-3857%7D", "{bbox-epsg-3857}");
}

function arcgisExport(
  endpoint: string,
  layer: number,
  format = "png32",
): string {
  const params = new URLSearchParams({
    f: "image",
    format,
    transparent: format !== "jpg" ? "true" : "false",
    layers: `show:${layer}`,
    size: "256,256",
    bboxSR: "3857",
    imageSR: "3857",
    bbox: "{bbox-epsg-3857}",
  });
  return `${endpoint}?${params.toString()}`
    .replace("%7Bbbox-epsg-3857%7D", "{bbox-epsg-3857}");
}

function arcgisImage(endpoint: string): string {
  const params = new URLSearchParams({
    f: "image",
    format: "jpgpng",
    bboxSR: "3857",
    imageSR: "3857",
    size: "256,256",
    bbox: "{bbox-epsg-3857}",
  });
  return `${endpoint}/exportImage?${params.toString()}`
    .replace("%7Bbbox-epsg-3857%7D", "{bbox-epsg-3857}");
}

const SP_WMS =
  "https://wms.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wms";
const SP_RASTER =
  "https://raster.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wms";
const BH_WMS = "https://bhmap.pbh.gov.br/v2/api/idebhgeo/wms";
const JP_WMS = "https://filipeia.joaopessoa.pb.gov.br/geoserver/wms";
const BARUERI_WMS_PROXY = "/api/barueri/wms";
function barueriWms(layer: string): string {
  return BARUERI_WMS_PROXY + "?layer=" + encodeURIComponent(layer) + "&bbox={bbox-epsg-3857}";
}

const layers: MapLayerSpec[] = [
  {
    id: "barueri-street-network",
    cityIbge: "3505708",
    label: "Eixos de logradouros · GeoPixel",
    description: "Malha viária municipal publicada no WMS oficial de gestão territorial.",
    category: "infrastructure",
    sourceType: "raster",
    tiles: [barueriWms("eixo_logradouro")],
    opacity: 0.72,
    minZoom: 12,
    attribution: "Prefeitura de Barueri · GeoPixel",
  },
  {
    id: "barueri-transpetro-pipeline",
    cityIbge: "3505708",
    label: "Faixa de dutos Transpetro · GeoPixel",
    description: "Camada municipal de referência da faixa de dutos. A presença da camada não substitui levantamento, faixa de domínio ou anuência do operador.",
    category: "infrastructure",
    sourceType: "raster",
    tiles: [barueriWms("faixa_de_dutos_transpetro_edif")],
    opacity: 0.72,
    minZoom: 12,
    attribution: "Prefeitura de Barueri · GeoPixel",
  },
  {
    id: "barueri-public-works",
    cityIbge: "3505708",
    label: "Obras municipais · GeoPixel",
    description: "Camada de obras publicada no WMS municipal. É contexto territorial e não é associada automaticamente ao lote por proximidade.",
    category: "infrastructure",
    sourceType: "raster",
    tiles: [barueriWms("obras_edif")],
    opacity: 0.7,
    minZoom: 12,
    attribution: "Prefeitura de Barueri · GeoPixel",
  },
  {
    id: "barueri-tic-oeste",
    cityIbge: "3505708",
    label: "TIC Oeste · anteprojeto",
    description: "Anteprojeto territorial publicado no WMS municipal; não representa obra concluída.",
    category: "infrastructure",
    sourceType: "raster",
    tiles: [barueriWms("tic_oeste_anteprojeto_edif")],
    opacity: 0.72,
    minZoom: 11,
    attribution: "Prefeitura de Barueri · GeoPixel",
  },
  {
    id: "barueri-environmental-licensing",
    cityIbge: "3505708",
    label: "Licenciamento ambiental · GeoPixel",
    description: "Camada municipal de registros de licenciamento. Não inferimos licença vigente do lote por mera sobreposição visual ou proximidade.",
    category: "environment",
    sourceType: "raster",
    tiles: [barueriWms("licenciamento")],
    opacity: 0.7,
    minZoom: 12,
    attribution: "Prefeitura de Barueri · GeoPixel",
  },

  {
    id: "barueri-risk-reference-points",
    cityIbge: "3505708",
    label: "Setores de risco · pontos de referência",
    description: "248 coordenadas UTM publicadas no Plano Municipal de Adaptação e Resiliência Climática 2025. São pontos de referência dos setores, não polígonos de risco.",
    category: "risk",
    sourceType: "vector",
    sourceLayer: "barueri_risk_reference_points",
    tiles: ["/api/tiles/barueri_risk_reference_points/{z}/{x}/{y}"],
    opacity: 0.78,
    renderType: "circle",
    circleRadius: 4,
    minZoom: 12,
    attribution: "Prefeitura de Barueri · SEMA / Instituto Geológico",
  },

  {
    id: "ibge-sectors-2022",
    label: "Setores censitários 2022",
    description: "Limites oficiais do Censo 2022 materializados no PostGIS.",
    category: "territory",
    sourceType: "vector",
    sourceLayer: "ibge_censo2022_setores",
    tiles: ["/api/tiles/ibge_censo2022_setores/{z}/{x}/{y}"],
    opacity: 0.62,
    lineColor: "#74695C",
    lineWidth: 1,
    minZoom: 12,
    attribution: "IBGE",
  },

  {
    id: "sp-parcels",
    cityIbge: "3550308",
    label: "Lotes cadastrais",
    description: "Limites oficiais de lotes publicados pela Prefeitura.",
    category: "territory",
    tiles: [wms(SP_WMS, "lote_cidadao")],
    opacity: 0.72,
    defaultActive: true,
    attribution: "Prefeitura de São Paulo",
  },
  {
    id: "sp-zoning",
    cityIbge: "3550308",
    label: "Zoneamento",
    description: "Zoneamento vigente publicado pela Prefeitura.",
    category: "planning",
    tiles: [wms(SP_WMS, "perimetro_zona_lei_18177_24")],
    opacity: 0.34,
    attribution: "Prefeitura de São Paulo",
  },
  {
    id: "sp-risk-geological",
    cityIbge: "3550308",
    label: "Risco geológico",
    description: "Áreas de risco geológico publicadas pelo município.",
    category: "risk",
    tiles: [wms(SP_WMS, "area_risco_geologico")],
    opacity: 0.5,
    attribution: "Prefeitura de São Paulo",
  },
  {
    id: "sp-risk-hydrological",
    cityIbge: "3550308",
    label: "Risco hidrológico",
    description: "Áreas de risco hidrológico publicadas pelo município.",
    category: "risk",
    tiles: [wms(SP_WMS, "risco_hidrologico")],
    opacity: 0.5,
    attribution: "Prefeitura de São Paulo",
  },
  {
    id: "sp-heritage",
    cityIbge: "3550308",
    label: "Patrimônio cultural",
    description: "Bens tombados e áreas envoltórias municipais.",
    category: "environment",
    tiles: [
      wms(
        SP_WMS,
        "patrimonio_cultural_bem_tombado,patrimonio_cultural_area_envoltoria_CONPRESP",
      ),
    ],
    opacity: 0.46,
    attribution: "Prefeitura de São Paulo",
  },
  {
    id: "sp-slope",
    cityIbge: "3550308",
    label: "Declividade",
    description: "Camada municipal de declividade.",
    category: "terrain",
    tiles: [wms(SP_WMS, "declividade")],
    opacity: 0.5,
    attribution: "Prefeitura de São Paulo",
  },
  {
    id: "sp-roads",
    cityIbge: "3550308",
    label: "Classificação viária",
    description: "Classificação urbanística do sistema viário.",
    category: "infrastructure",
    tiles: [wms(SP_WMS, "zoneamento_classificacao_viaria")],
    opacity: 0.62,
    attribution: "Prefeitura de São Paulo",
  },
  {
    id: "sp-ortho-2020",
    cityIbge: "3550308",
    label: "Ortofoto 2020",
    description: "Imagem aérea municipal de 2020.",
    category: "imagery",
    tiles: [
      wms(SP_RASTER, "ORTO_RGB_2020", {
        format: "image/jpeg",
        transparent: false,
      }),
    ],
    opacity: 0.92,
    attribution: "Prefeitura de São Paulo",
  },

  {
    id: "recife-parcels",
    cityIbge: "2611606",
    label: "Lotes cadastrais",
    description: "Base municipal de lotes.",
    category: "territory",
    tiles: [
      arcgisExport(
        "https://esigportal2.recife.pe.gov.br/arcgis/rest/services/Planejamento/BASES_LOTES_EDIFICACAO_BAIRRO/MapServer/export",
        1,
      ),
    ],
    opacity: 0.7,
    defaultActive: true,
    attribution: "Prefeitura do Recife",
  },
  {
    id: "recife-zoning",
    cityIbge: "2611606",
    label: "Zoneamento",
    description: "Zoneamento do Plano Diretor publicado pelo município.",
    category: "planning",
    tiles: [
      arcgisExport(
        "https://esigportal2.recife.pe.gov.br/arcgis/rest/services/Planejamento/BASES_ZONEAMENTO_G_PD2020/MapServer/export",
        6,
      ),
    ],
    opacity: 0.32,
    attribution: "Prefeitura do Recife",
  },
  {
    id: "recife-buildings",
    cityIbge: "2611606",
    label: "Edificações",
    description: "Cartografia municipal de edificações.",
    category: "buildings",
    tiles: [
      arcgisExport(
        "https://esigportal2.recife.pe.gov.br/arcgis/rest/services/Planejamento/BASES_BAIRRO_FACEQUADRA_LOGRADOURO_LOTE/MapServer/export",
        7,
      ),
    ],
    opacity: 0.48,
    attribution: "Prefeitura do Recife",
  },
  {
    id: "recife-slope",
    cityIbge: "2611606",
    label: "Declividade",
    description: "Modelo municipal de declividade.",
    category: "terrain",
    tiles: [
      "https://esigportal2.recife.pe.gov.br/arcgis/rest/services/Hosted/RGB_MDT_2_5MTS_DECLIVIDADE_tif/MapServer/tile/{z}/{y}/{x}",
    ],
    opacity: 0.48,
    minZoom: 12,
    attribution: "Prefeitura do Recife",
  },
  {
    id: "recife-roads",
    cityIbge: "2611606",
    label: "Classificação viária",
    description: "Rede e classificação viária publicada pela CTTU.",
    category: "infrastructure",
    tiles: [
      arcgisExport(
        "https://esigportal2.recife.pe.gov.br/arcgis/rest/services/Cttu_An%C3%A1lise_Vias_Recife/MapServer/export",
        16,
      ),
    ],
    opacity: 0.68,
    attribution: "CTTU / Prefeitura do Recife",
  },
  {
    id: "recife-risk",
    cityIbge: "2611606",
    label: "Setores de risco",
    description: "Setores de risco publicados pela Defesa Civil.",
    category: "risk",
    tiles: [
      arcgisExport(
        "https://esigportal2.recife.pe.gov.br/arcgis/rest/services/Hosted/Setores_Risco_SEDEC/MapServer/export",
        0,
      ),
    ],
    opacity: 0.44,
    attribution: "Defesa Civil do Recife",
  },
  {
    id: "recife-flood-2026",
    cityIbge: "2611606",
    label: "Alagamento 2026",
    description: "Polígonos municipais de alagamento publicados em 2026.",
    category: "risk",
    tiles: [
      arcgisExport(
        "https://esigportal2.recife.pe.gov.br/arcgis/rest/services/Hosted/Poligonos_Alagamentos_2026_5/MapServer/export",
        0,
      ),
    ],
    opacity: 0.42,
    attribution: "Prefeitura do Recife",
  },

  {
    id: "rio-parcels",
    cityIbge: "3304557",
    label: "Imóveis territoriais",
    description: "Limites territoriais publicados pela Prefeitura.",
    category: "territory",
    tiles: [
      arcgisExport(
        "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/CadParcel/IMOVEIS_TERRITORIAIS/MapServer/export",
        0,
      ),
    ],
    opacity: 0.68,
    defaultActive: true,
    attribution: "Prefeitura do Rio de Janeiro",
  },
  {
    id: "rio-zoning",
    cityIbge: "3304557",
    label: "Zoneamento",
    description: "Zoneamento urbano vigente.",
    category: "planning",
    tiles: [
      arcgisExport(
        "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Urbanismo/LBB_Zoneamento_urbano_vigente/MapServer/export",
        0,
      ),
    ],
    opacity: 0.32,
    attribution: "Prefeitura do Rio de Janeiro",
  },
  {
    id: "rio-buildings",
    cityIbge: "3304557",
    label: "Edificações",
    description: "Cartografia municipal de edificações 2019.",
    category: "buildings",
    tiles: [
      arcgisExport(
        "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/CadLog/Edificacoes_2019/MapServer/export",
        0,
      ),
    ],
    opacity: 0.5,
    attribution: "Prefeitura do Rio de Janeiro",
  },
  {
    id: "rio-flood",
    cityIbge: "3304557",
    label: "Suscetibilidade a inundação",
    description: "Índice municipal de suscetibilidade física a inundação.",
    category: "risk",
    tiles: [
      arcgisExport(
        "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Estudos/ISMFI_Indice_de_Suscetibilidade_do_Meio_Fisico_a_Inundacoes/MapServer/export",
        0,
      ),
    ],
    opacity: 0.44,
    attribution: "Prefeitura do Rio de Janeiro",
  },
  {
    id: "rio-heritage",
    cityIbge: "3304557",
    label: "Proteção cultural",
    description: "Áreas de proteção do ambiente cultural.",
    category: "environment",
    tiles: [
      arcgisExport(
        "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Urbanismo/LBB_APAC/MapServer/export",
        0,
      ),
    ],
    opacity: 0.42,
    attribution: "Prefeitura do Rio de Janeiro",
  },
  {
    id: "rio-app",
    cityIbge: "3304557",
    label: "Áreas de preservação",
    description: "Áreas de preservação permanente publicadas pelo município.",
    category: "environment",
    tiles: [
      arcgisExport(
        "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Urbanismo/LBB_APP/MapServer/export",
        0,
      ),
    ],
    opacity: 0.36,
    attribution: "Prefeitura do Rio de Janeiro",
  },
  {
    id: "rio-terrain",
    cityIbge: "3304557",
    label: "Modelo de terreno 2019",
    description: "Modelo digital de terreno derivado de LiDAR.",
    category: "terrain",
    tiles: [
      arcgisExport(
        "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Cartografia/Modelo_Digital_de_Terreno__Lidar_2019__escala_1_10_000_/MapServer/export",
        0,
      ),
    ],
    opacity: 0.52,
    attribution: "Prefeitura do Rio de Janeiro",
  },
  {
    id: "rio-roads",
    cityIbge: "3304557",
    label: "Logradouros",
    description: "Trechos oficiais de logradouros.",
    category: "infrastructure",
    tiles: [
      arcgisExport(
        "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/CadLog/Trechos_Logradouros/MapServer/export",
        0,
      ),
    ],
    opacity: 0.62,
    attribution: "Prefeitura do Rio de Janeiro",
  },
  {
    id: "rio-ortho-2025",
    cityIbge: "3304557",
    label: "Mosaico aéreo 2025",
    description: "Mosaico oficial de imagens de 2025.",
    category: "imagery",
    tiles: [
      arcgisImage(
        "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Imagens/Mosaico_2025/ImageServer",
      ),
    ],
    opacity: 0.92,
    attribution: "Prefeitura do Rio de Janeiro",
  },

  {
    id: "bh-parcels",
    cityIbge: "3106200",
    label: "Lotes cadastrais",
    description: "Lotes do cadastro territorial municipal.",
    category: "territory",
    tiles: [wms(BH_WMS, "ide_bhgeo:LOTE_CTM")],
    opacity: 0.7,
    defaultActive: true,
    attribution: "Prefeitura de Belo Horizonte",
  },
  {
    id: "bh-zoning",
    cityIbge: "3106200",
    label: "Zoneamento",
    description: "Zoneamento municipal vigente.",
    category: "planning",
    tiles: [wms(BH_WMS, "ide_bhgeo:ZONEAMENTO_11181")],
    opacity: 0.32,
    attribution: "Prefeitura de Belo Horizonte",
  },
  {
    id: "bh-buildings",
    cityIbge: "3106200",
    label: "Edificações",
    description: "Cartografia municipal de edificações.",
    category: "buildings",
    tiles: [wms(BH_WMS, "ide_bhgeo:EDIFICACAO")],
    opacity: 0.5,
    attribution: "Prefeitura de Belo Horizonte",
  },
  {
    id: "bh-contours",
    cityIbge: "3106200",
    label: "Curvas de nível de 1 m",
    description: "Curvas oficiais de nível com equidistância de 1 m.",
    category: "terrain",
    tiles: [wms(BH_WMS, "ide_bhgeo:CURVA_NIVEL_SEGMENTADA_1M")],
    opacity: 0.64,
    attribution: "Prefeitura de Belo Horizonte",
  },
  {
    id: "bh-environment",
    cityIbge: "3106200",
    label: "Áreas ambientais",
    description: "Áreas ambientais e unidades de conservação municipais.",
    category: "environment",
    tiles: [
      wms(
        BH_WMS,
        "ide_bhgeo:ADE_INTERESSE_AMBIENTAL_11181,ide_bhgeo:AEIS_INTERESSE_AMBIENTAL_11181,ide_bhgeo:UNID_CONSERV_AMBIENTAL,ide_bhgeo:PARQUES_MUNICIPAIS,ide_bhgeo:CORREDOR_ECOLOGICO_SERRA_CURRAL",
      ),
    ],
    opacity: 0.38,
    attribution: "Prefeitura de Belo Horizonte",
  },
  {
    id: "bh-roads",
    cityIbge: "3106200",
    label: "Classificação viária",
    description: "Classificação oficial das vias.",
    category: "infrastructure",
    tiles: [wms(BH_WMS, "ide_bhgeo:CLASSIFICACAO_VIARIA_11181")],
    opacity: 0.6,
    attribution: "Prefeitura de Belo Horizonte",
  },
  {
    id: "bh-drainage",
    cityIbge: "3106200",
    label: "Microdrenagem",
    description: "Rede municipal publicada de microdrenagem.",
    category: "infrastructure",
    tiles: [wms(BH_WMS, "ide_bhgeo:REDE_MICRODRENAGEM")],
    opacity: 0.64,
    attribution: "Prefeitura de Belo Horizonte",
  },
  {
    id: "bh-ortho-2015",
    cityIbge: "3106200",
    label: "Ortofoto 2015",
    description: "Ortofoto municipal de 2015.",
    category: "imagery",
    tiles: [
      wms(BH_WMS, "ide_bhgeo:ORTOFOTO_2015", {
        format: "image/jpeg",
        transparent: false,
      }),
    ],
    opacity: 0.92,
    attribution: "Prefeitura de Belo Horizonte",
  },

  {
    id: "jp-parcels",
    cityIbge: "2507507",
    label: "Lotes cadastrais",
    description: "Lotes oficiais materializados localmente e servidos como vetor MVT.",
    category: "territory",
    sourceType: "vector",
    sourceLayer: "jp_lotes",
    tiles: ["/api/tiles/jp_lotes/{z}/{x}/{y}"],
    opacity: 0.9,
    lineColor: "#356854",
    lineWidth: 1.35,
    minZoom: 14,
    defaultActive: true,
    attribution: "Prefeitura de João Pessoa / LoteDiretor",
  },
  {
    id: "jp-zoning",
    cityIbge: "2507507",
    label: "Zoneamento 2024",
    description: "Zoneamento oficial publicado pelo município.",
    category: "planning",
    tiles: [wms(JP_WMS, "digeoc:zoneamento2024")],
    opacity: 0.32,
    attribution: "Prefeitura de João Pessoa",
  },
  {
    id: "jp-coastal",
    cityIbge: "2507507",
    label: "Restrições da orla",
    description: "Faixas e restrições costeiras municipais.",
    category: "environment",
    tiles: [wms(JP_WMS, "digeoc:faixas")],
    opacity: 0.46,
    attribution: "Prefeitura de João Pessoa",
  },
  {
    id: "jp-roads",
    cityIbge: "2507507",
    label: "Hierarquia viária",
    description: "Hierarquia oficial do sistema viário.",
    category: "infrastructure",
    tiles: [wms(JP_WMS, "digeoc:Hierarquia")],
    opacity: 0.5,
    attribution: "Prefeitura de João Pessoa",
  },
  {
    id: "jp-environment",
    cityIbge: "2507507",
    label: "Áreas ambientais e especiais",
    description: "Unidades de conservação e áreas especiais.",
    category: "environment",
    tiles: [wms(JP_WMS, "digeoc:UC,digeoc:ZEIS")],
    opacity: 0.38,
    attribution: "Prefeitura de João Pessoa",
  },
  {
    id: "jp-risk",
    cityIbge: "2507507",
    label: "Suscetibilidade",
    description: "Cartografia oficial de suscetibilidade.",
    category: "risk",
    tiles: [wms(JP_WMS, "digeoc:Suscetibilidade")],
    opacity: 0.44,
    attribution: "Prefeitura de João Pessoa",
  },
  {
    id: "jp-heritage",
    cityIbge: "2507507",
    label: "Patrimônio cultural",
    description: "Tombamentos federal/estadual e centro histórico.",
    category: "environment",
    tiles: [
      wms(
        JP_WMS,
        "digeoc:Tombamento_IPHAN,digeoc:TOMBAMENTO_IPHAEP,digeoc:centrohistorico",
      ),
    ],
    opacity: 0.46,
    attribution: "Prefeitura de João Pessoa",
  },
  {
    id: "jp-buildings",
    cityIbge: "2507507",
    label: "Edificações",
    description: "Cartografia municipal de edificações.",
    category: "buildings",
    tiles: [wms(JP_WMS, "digeoc:EDIFICACOES")],
    opacity: 0.52,
    attribution: "Prefeitura de João Pessoa",
  },
  {
    id: "jp-contours",
    cityIbge: "2507507",
    label: "Curvas de nível 2022",
    description: "Curvas oficiais materializadas localmente e servidas como vetor MVT.",
    category: "terrain",
    sourceType: "vector",
    sourceLayer: "jp_curvas_nivel_2022",
    tiles: ["/api/tiles/jp_curvas_nivel_2022/{z}/{x}/{y}"],
    opacity: 0.8,
    lineColor: "#7D6E57",
    lineWidth: 1,
    minZoom: 13,
    attribution: "Prefeitura de João Pessoa / LoteDiretor",
  },
  {
    id: "jp-gas",
    cityIbge: "2507507",
    label: "Rede de gás",
    description: "Rede de gás publicada no portal municipal.",
    category: "infrastructure",
    tiles: [wms(JP_WMS, "digeoc:PBGAS")],
    opacity: 0.7,
    attribution: "Prefeitura de João Pessoa",
  },
  {
    id: "jp-ortho-2021",
    cityIbge: "2507507",
    label: "Aerofotogrametria 2021",
    description: "Imagem aérea municipal de 20 cm.",
    category: "imagery",
    tiles: [
      wms(JP_WMS, "digeoc:2021_20cm", {
        format: "image/png",
        transparent: false,
      }),
    ],
    opacity: 0.92,
    attribution: "Prefeitura de João Pessoa",
  },

  {
    id: "federal-uc",
    label: "Unidades de conservação federais",
    description: "Limites oficiais publicados pelo ICMBio.",
    category: "environment",
    tiles: [
      wms(
        "https://geoservicos.inde.gov.br/geoserver/ICMBio/wms",
        "ICMBio:limiteucsfederais_a",
      ),
    ],
    opacity: 0.4,
    attribution: "ICMBio",
  },
  {
    id: "federal-roads",
    label: "Rodovias federais",
    description: "Sistema Nacional de Viação publicado pelo DNIT.",
    category: "infrastructure",
    tiles: [
      wms(
        "https://geoservicos.inde.gov.br/geoserver/DNIT/wms",
        "DNIT:snv_202507a",
      ),
    ],
    opacity: 0.64,
    attribution: "DNIT",
  },
  {
    id: "federal-indigenous",
    label: "Terras indígenas",
    description: "Poligonais oficiais publicadas pela FUNAI.",
    category: "environment",
    tiles: [
      wms(
        "https://geoserver.funai.gov.br/geoserver/wms",
        "Funai:tis_poligonais",
      ),
    ],
    opacity: 0.4,
    attribution: "FUNAI",
  },
  {
    id: "federal-sigef",
    label: "Parcelas rurais certificadas",
    description: "Referência fundiária pública do Geoportal INCRA/SIGEF.",
    category: "rural",
    tiles: [
      wms(
        "https://geoportal.incra.gov.br/geoserver/wms",
        "geonode:sigef_geo",
      ),
    ],
    opacity: 0.38,
    attribution: "INCRA / SIGEF",
  },
];

const sicarByCity: Record<string, string> = {
  "3550308": "sicar:sicar_imoveis_sp",
  "3505708": "sicar:sicar_imoveis_sp",
  "2611606": "sicar:sicar_imoveis_pe",
  "3304557": "sicar:sicar_imoveis_rj",
  "3106200": "sicar:sicar_imoveis_mg",
  "2507507": "sicar:sicar_imoveis_pb",
};

export const CATEGORY_LABELS: Record<MapLayerCategory, string> = {
  territory: "Território",
  planning: "Urbanismo",
  risk: "Risco",
  environment: "Ambiente e patrimônio",
  buildings: "Edificações",
  terrain: "Topografia",
  infrastructure: "Infraestrutura",
  rural: "Rural",
  imagery: "Imagens",
};

export function layersForCity(cityIbge: string): MapLayerSpec[] {
  const cityLayers = layers.filter(
    (layer) => !layer.cityIbge || layer.cityIbge === cityIbge,
  );

  const sicar = sicarByCity[cityIbge];
  if (!sicar) return cityLayers;

  return [
    ...cityLayers,
    {
      id: `sicar-${cityIbge}`,
      label: "Cadastro Ambiental Rural",
      description:
        "Imóveis declarados no SICAR. Cadastro declaratório; não representa domínio.",
      category: "rural",
      tiles: [
        wms(
          "https://geoserver.car.gov.br/geoserver/sicar/wms",
          sicar,
        ),
      ],
      opacity: 0.32,
      attribution: "SICAR",
    },
  ];
}

export function defaultLayerIds(cityIbge: string): string[] {
  return layersForCity(cityIbge)
    .filter((layer) => layer.defaultActive)
    .map((layer) => layer.id);
}
