"use client";

import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import type { CityOption } from "@/lib/cities";
import { layersForCity } from "@/lib/map-layers";

type GeoFeature = {
  type: "Feature";
  geometry: Geometry;
  properties?: Record<string, unknown> | null;
};

type Props = {
  city: CityOption;
  feature: GeoFeature | null;
  onPick: (point: { lat: number; lng: number }) => void;
  focusPoint?: { lat: number; lng: number } | null;
  activeLayerIds: string[];
  viewMode: "2d" | "3d";
};

const SELECTED_SOURCE = "selected-parcel";
const SELECTED_FILL = "selected-parcel-fill";
const SELECTED_LINE = "selected-parcel-line";
const CATALOG_SOURCE_PREFIX = "catalog-source:";
const CATALOG_LAYER_PREFIX = "catalog-layer:";
const BUILDINGS_3D = "ld-buildings-3d";

function sourceId(layerId: string): string {
  return `${CATALOG_SOURCE_PREFIX}${layerId}`;
}

function mapLayerId(layerId: string): string {
  return `${CATALOG_LAYER_PREFIX}${layerId}`;
}

export function ExplorerMap({
  city,
  feature,
  onPick,
  focusPoint,
  activeLayerIds,
  viewMode,
}: Props) {
  const container = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const onPickRef = useRef(onPick);

  useEffect(() => {
    onPickRef.current = onPick;
  }, [onPick]);

  useEffect(() => {
    if (!container.current || mapRef.current) return;

    // Worker published by scripts/copy-maplibre-worker.mjs (prebuild/predev).
    maplibregl.setWorkerUrl(
      `/vendor/maplibre/${maplibregl.getVersion()}/maplibre-gl-worker.mjs`,
    );
    const map = new maplibregl.Map({
      container: container.current,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: city.center,
      zoom: city.zoom,
      maxZoom: 22,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    map.addControl(
      new maplibregl.NavigationControl({ visualizePitch: true }),
      "top-right",
    );

    map.on("click", (event) => {
      onPickRef.current({
        lat: event.lngLat.lat,
        lng: event.lngLat.lng,
      });
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.flyTo({
      center: city.center,
      zoom: city.zoom,
      duration: 700,
    });
  }, [city]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focusPoint) return;
    map.flyTo({
      center: [focusPoint.lng, focusPoint.lat],
      zoom: 19,
      duration: 700,
    });
  }, [focusPoint]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const applyViewMode = () => {
      map.easeTo({
        pitch: viewMode === "3d" ? 58 : 0,
        bearing: viewMode === "3d" ? -18 : 0,
        duration: 650,
      });

      if (viewMode !== "3d") {
        if (map.getLayer(BUILDINGS_3D)) {
          map.removeLayer(BUILDINGS_3D);
        }
        return;
      }

      if (map.getLayer(BUILDINGS_3D)) return;
      const styleLayers = map.getStyle().layers ?? [];
      const buildingLayer = styleLayers.find((layer) => {
        const candidate = layer as maplibregl.LayerSpecification & {
          source?: string;
          "source-layer"?: string;
        };
        return (
          typeof candidate.source === "string" &&
          candidate["source-layer"] === "building"
        );
      }) as
        | (maplibregl.LayerSpecification & {
            source: string;
            "source-layer": string;
          })
        | undefined;

      if (!buildingLayer) return;

      map.addLayer(
        {
          id: BUILDINGS_3D,
          type: "fill-extrusion",
          source: buildingLayer.source,
          "source-layer": buildingLayer["source-layer"],
          minzoom: 15,
          paint: {
            "fill-extrusion-color": "#C7CFCC",
            "fill-extrusion-height": [
              "coalesce",
              ["get", "render_height"],
              ["get", "height"],
              6,
            ],
            "fill-extrusion-base": [
              "coalesce",
              ["get", "render_min_height"],
              ["get", "min_height"],
              0,
            ],
            "fill-extrusion-opacity": 0.78,
          },
        } as maplibregl.FillExtrusionLayerSpecification,
        map.getLayer(SELECTED_FILL) ? SELECTED_FILL : undefined,
      );

      if (map.getLayer(SELECTED_FILL)) map.moveLayer(SELECTED_FILL);
      if (map.getLayer(SELECTED_LINE)) map.moveLayer(SELECTED_LINE);
    };

    if (map.loaded()) applyViewMode();
    else map.once("load", applyViewMode);
  }, [viewMode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const sync = () => {
      const available = layersForCity(city.ibge);
      const availableIds = new Set(available.map((layer) => layer.id));
      const wanted = new Set(
        activeLayerIds.filter((id) => availableIds.has(id)),
      );

      for (const styleLayer of map.getStyle().layers ?? []) {
        if (!styleLayer.id.startsWith(CATALOG_LAYER_PREFIX)) continue;
        const id = styleLayer.id.slice(CATALOG_LAYER_PREFIX.length);
        if (wanted.has(id)) continue;

        if (map.getLayer(styleLayer.id)) {
          map.removeLayer(styleLayer.id);
        }
        const sid = sourceId(id);
        if (map.getSource(sid)) {
          map.removeSource(sid);
        }
      }

      const categoryOrder: Record<string, number> = {
        imagery: 0,
        terrain: 1,
        territory: 2,
        planning: 3,
        environment: 4,
        risk: 5,
        infrastructure: 6,
        buildings: 7,
        rural: 8,
      };

      const activeSpecs = available
        .filter((layer) => wanted.has(layer.id))
        .sort(
          (a, b) =>
            (categoryOrder[a.category] ?? 10) -
            (categoryOrder[b.category] ?? 10),
        );

      for (const spec of activeSpecs) {
        const sid = sourceId(spec.id);
        const lid = mapLayerId(spec.id);

        if (!map.getSource(sid)) {
          if (spec.sourceType === "vector") {
            map.addSource(sid, {
              type: "vector",
              tiles: spec.tiles,
              minzoom: spec.minZoom ?? 0,
              maxzoom: spec.maxZoom ?? 22,
              attribution: spec.attribution,
            });
          } else {
            map.addSource(sid, {
              type: "raster",
              tiles: spec.tiles,
              tileSize: 256,
              minzoom: spec.minZoom ?? 0,
              maxzoom: spec.maxZoom ?? 22,
              attribution: spec.attribution,
            });
          }
        }

        if (!map.getLayer(lid)) {
          if (spec.sourceType === "vector") {
            const vectorLayer =
              spec.renderType === "circle"
                ? ({
                    id: lid,
                    type: "circle",
                    source: sid,
                    "source-layer": spec.sourceLayer,
                    paint: {
                      "circle-color": spec.lineColor ?? "#356854",
                      "circle-radius": spec.circleRadius ?? 4,
                      "circle-opacity": spec.opacity,
                      "circle-stroke-width": 1,
                      "circle-stroke-color": "#ffffff",
                    },
                  } as maplibregl.CircleLayerSpecification)
                : ({
                    id: lid,
                    type: "line",
                    source: sid,
                    "source-layer": spec.sourceLayer,
                    paint: {
                      "line-color": spec.lineColor ?? "#356854",
                      "line-width": spec.lineWidth ?? 1,
                      "line-opacity": spec.opacity,
                    },
                  } as maplibregl.LineLayerSpecification);
            map.addLayer(
              vectorLayer,
              map.getLayer(SELECTED_FILL) ? SELECTED_FILL : undefined,
            );
          } else {
            map.addLayer(
              {
                id: lid,
                type: "raster",
                source: sid,
                paint: {
                  "raster-opacity": spec.opacity,
                  "raster-fade-duration": 0,
                },
              },
              map.getLayer(SELECTED_FILL) ? SELECTED_FILL : undefined,
            );
          }
        }
      }

      if (map.getLayer(SELECTED_FILL)) map.moveLayer(SELECTED_FILL);
      if (map.getLayer(SELECTED_LINE)) map.moveLayer(SELECTED_LINE);
    };

    if (map.loaded()) sync();
    else map.once("load", sync);
  }, [city.ibge, activeLayerIds]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const apply = () => {
      const data: FeatureCollection = {
        type: "FeatureCollection",
        features: feature ? [feature as Feature] : [],
      };

      const existing = map.getSource(SELECTED_SOURCE) as
        | maplibregl.GeoJSONSource
        | undefined;
      if (existing) {
        existing.setData(data);
      } else {
        map.addSource(SELECTED_SOURCE, {
          type: "geojson",
          data,
        });
        map.addLayer({
          id: SELECTED_FILL,
          type: "fill",
          source: SELECTED_SOURCE,
          paint: {
            "fill-color": "#20A475",
            "fill-opacity": 0.18,
          },
        });
        map.addLayer({
          id: SELECTED_LINE,
          type: "line",
          source: SELECTED_SOURCE,
          paint: {
            "line-color": "#1F4035",
            "line-width": 4,
          },
        });
      }

      if (feature?.geometry) {
        const bounds = new maplibregl.LngLatBounds();
        const walk = (coordinates: unknown): void => {
          if (
            Array.isArray(coordinates) &&
            coordinates.length >= 2 &&
            typeof coordinates[0] === "number" &&
            typeof coordinates[1] === "number"
          ) {
            bounds.extend([coordinates[0], coordinates[1]]);
            return;
          }
          if (Array.isArray(coordinates)) {
            coordinates.forEach(walk);
          }
        };
        const geometry = feature.geometry as Geometry & {
          coordinates?: unknown;
        };
        if ("coordinates" in geometry) walk(geometry.coordinates);
        if (!bounds.isEmpty()) {
          map.fitBounds(bounds, {
            padding: 72,
            maxZoom: 20,
            duration: 700,
          });
        }
      }

      if (map.getLayer(SELECTED_FILL)) map.moveLayer(SELECTED_FILL);
      if (map.getLayer(SELECTED_LINE)) map.moveLayer(SELECTED_LINE);
    };

    if (map.loaded()) apply();
    else map.once("load", apply);
  }, [feature]);

  return (
    <div
      className="explorer-map"
      ref={container}
      aria-label="Mapa do Explorer"
    />
  );
}
