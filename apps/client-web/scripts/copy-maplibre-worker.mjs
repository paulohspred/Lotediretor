// MapLibre GL 6 loads its web worker from a separate module file resolved next
// to the library bundle (import.meta.url). Next.js does not emit that file, so
// the worker 404s and the map never renders tiles. Publish the worker (and the
// shared chunk it imports) under /vendor/maplibre/<version>/ and point
// maplibregl.setWorkerUrl() at it (see components/explorer-map.tsx).
import { copyFileSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const pkgDir = dirname(require.resolve("maplibre-gl/package.json"));
const { version } = JSON.parse(readFileSync(join(pkgDir, "package.json"), "utf8"));
const root = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "vendor", "maplibre");
const target = join(root, version);

rmSync(root, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(join(pkgDir, "dist", file), join(target, file));
}
console.log(`maplibre worker ${version} → public/vendor/maplibre/${version}/`);
