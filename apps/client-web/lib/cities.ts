export type CityOption = {
  ibge: string;
  name: string;
  uf: string;
  center: [number, number];
  zoom: number;
  parcelSupported?: boolean;
  /** [minLng, minLat, maxLng, maxLat] from the IBGE mesh, when known. */
  bbox?: [number, number, number, number];
  officialZoningUrl?: string;
  officialIptuUrl?: string;
  officialCadastreUrl?: string;
  officialValueUrl?: string;
  officialPermitsUrl?: string;
};

export const CITIES: CityOption[] = [
  { ibge: "3550308", name: "São Paulo", uf: "SP", center: [-46.6333, -23.5505], zoom: 11.5, parcelSupported: true },
  {
    ibge: "3505708",
    name: "Barueri",
    uf: "SP",
    center: [-46.8765, -23.5114],
    zoom: 13,
    parcelSupported: false,
    officialZoningUrl: "https://portal.barueri.sp.gov.br/cidadao/moradia/mapa-zoneamento",
    officialIptuUrl: "https://www.barueri.sp.gov.br/sistemas/2via/?tipo=1",
    officialCadastreUrl: "https://servicos.barueri.sp.gov.br/emissaocertidao/certidaocadastral.aspx",
    officialValueUrl: "https://servicos.barueri.sp.gov.br/emissaocertidao/CertidaoVenal.aspx",
    officialPermitsUrl: "https://barueri.aprova.com.br/",
  },
  { ibge: "2611606", name: "Recife", uf: "PE", center: [-34.8842, -8.0543], zoom: 12, parcelSupported: true },
  { ibge: "3304557", name: "Rio de Janeiro", uf: "RJ", center: [-43.1729, -22.9068], zoom: 11.5, parcelSupported: true },
  { ibge: "3106200", name: "Belo Horizonte", uf: "MG", center: [-43.9378, -19.9208], zoom: 12, parcelSupported: true },
  { ibge: "2507507", name: "João Pessoa", uf: "PB", center: [-34.8631, -7.1153], zoom: 12, parcelSupported: true },
];

export function findCity(ibge: string): CityOption | undefined {
  return CITIES.find((city) => city.ibge === ibge);
}

/**
 * Only for UI state that was already initialised from CITIES. Never use it to
 * interpret untrusted input: an unknown IBGE code must not silently become
 * São Paulo. Use findCity() and reject unknown codes instead.
 */
export function cityByIbge(ibge: string): CityOption {
  return findCity(ibge) ?? CITIES[0];
}

/** Municipality as returned by the platform API (/municipalities). */
export type ApiMunicipality = {
  ibge_code: string;
  name: string;
  uf: string;
  bbox: [number, number, number, number] | null;
  capabilities: { parcel_resolver: boolean; federal_context: boolean };
};

function zoomForBbox(bbox: [number, number, number, number]): number {
  const span = Math.max(bbox[2] - bbox[0], bbox[3] - bbox[1], 0.01);
  // ~360° at zoom 0; leave margin so the whole municipality is visible.
  return Math.max(4, Math.min(14, Math.log2(360 / span) - 0.6));
}

/**
 * Any of the ~5,570 IBGE municipalities as a map/city option. Curated cities
 * keep their hand-tuned view and official links; the parcel capability always
 * comes from the API so UI and backend cannot disagree.
 */
export function cityFromMunicipality(m: ApiMunicipality): CityOption {
  const curated = findCity(m.ibge_code);
  const bbox = m.bbox ?? undefined;
  const center: [number, number] = bbox
    ? [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
    : curated?.center ?? [-51.9, -14.2];
  return {
    ...curated,
    ibge: m.ibge_code,
    name: m.name,
    uf: m.uf,
    center: curated?.center ?? center,
    zoom: curated?.zoom ?? (bbox ? zoomForBbox(bbox) : 4),
    bbox,
    parcelSupported: m.capabilities.parcel_resolver,
  };
}
