"use client";

import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import type { CityOption } from "@/lib/cities";

type GeoFeature = {
  type: "Feature";
  geometry: Geometry;
  properties?: Record<string, unknown> | null;
};

type Props = {
  city: CityOption;
  feature: GeoFeature | null;
  onPick: (point: { lat: number; lng: number }) => void;
};

const SELECTED_SOURCE = "selected-parcel";
const SELECTED_FILL = "selected-parcel-fill";
const SELECTED_LINE = "selected-parcel-line";

export function ExplorerMap({ city, feature, onPick }: Props) {
  const container = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const onPickRef = useRef(onPick);

  useEffect(() => {
    onPickRef.current = onPick;
  }, [onPick]);

  useEffect(() => {
    if (!container.current || mapRef.current) return;

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
