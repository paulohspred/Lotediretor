"use client";

import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";

export function ExplorerMap() {
  const container = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!container.current) return;

    const map = new maplibregl.Map({
      container: container.current,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: [-46.6333, -23.5505],
      zoom: 11.5,
      maxZoom: 22,
      attributionControl: { compact: true },
    });

    map.addControl(
      new maplibregl.NavigationControl({ visualizePitch: true }),
      "top-right",
    );

    return () => map.remove();
  }, []);

  return <div className="explorer-map" ref={container} aria-label="Mapa do Explorer" />;
}
