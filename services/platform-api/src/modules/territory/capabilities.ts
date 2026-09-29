/**
 * Municipality capabilities that depend on code, not data.
 *
 * Parcel resolution still depends on per-city engines (see services/*.py).
 * This is the single place that lists them, so the API, the Explorer and the
 * coverage endpoint agree. Moving these to data-driven connectors
 * (service_registry) is Phase 3.
 */
export const PARCEL_ENGINE_SLUG: Readonly<Record<string, string>> = {
  "3550308": "sp",
  "2611606": "recife",
  "3304557": "rio",
  "3106200": "bh",
  "2507507": "jp",
};

export function parcelResolverAvailable(ibge: string): boolean {
  return Object.prototype.hasOwnProperty.call(PARCEL_ENGINE_SLUG, ibge);
}

export const IBGE_CODE = /^[0-9]{7}$/;
