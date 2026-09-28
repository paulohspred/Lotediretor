export type CityOption = {
  ibge: string;
  name: string;
  uf: string;
  center: [number, number];
  zoom: number;
  parcelSupported?: boolean;
  officialZoningUrl?: string;
  officialIptuUrl?: string;
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
    officialIptuUrl: "https://portal.barueri.sp.gov.br/cidadao/moradia/emissao-2-via-iptu",
  },
  { ibge: "2611606", name: "Recife", uf: "PE", center: [-34.8842, -8.0543], zoom: 12, parcelSupported: true },
  { ibge: "3304557", name: "Rio de Janeiro", uf: "RJ", center: [-43.1729, -22.9068], zoom: 11.5, parcelSupported: true },
  { ibge: "3106200", name: "Belo Horizonte", uf: "MG", center: [-43.9378, -19.9208], zoom: 12, parcelSupported: true },
  { ibge: "2507507", name: "João Pessoa", uf: "PB", center: [-34.8631, -7.1153], zoom: 12, parcelSupported: true },
];

export function cityByIbge(ibge: string): CityOption {
  return CITIES.find((city) => city.ibge === ibge) ?? CITIES[0];
}
