from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import psycopg2

from tools.loaders.load_national_restrictions import load_one


class RestrictionLoaderDatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get("TEST_DATABASE_URL") or os.environ.get("LOTEDIRETOR_DB_DSN")
        if not cls.dsn:
            raise unittest.SkipTest("database not configured")

    def test_snapshot_promotion_and_pii_filter(self):
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO ld_catalog.source
                   (source_id,authority,scope,source_type,access_class,verification_status,canonical_url)
                   VALUES ('fixture-restriction','Fixture','BR','fixture','OPEN_REUSABLE','VERIFIED','https://example.invalid/fixture')
                   ON CONFLICT (source_id) DO NOTHING"""
            )

        feature_collection = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {
                    "id": "fx-1",
                    "name": "Área teste",
                    "category": "teste",
                    "cpf_titular": "00000000000",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-46.88, -23.52], [-46.87, -23.52],
                        [-46.87, -23.51], [-46.88, -23.51],
                        [-46.88, -23.52],
                    ]],
                },
            }],
        }
        cfg = {
            "layer_key": "fixture_restriction",
            "source_id": "fixture-restriction",
            "theme": "CONSERVATION_UNIT",
            "authority": "Fixture",
            "source_url": "https://example.invalid/fixture.geojson",
            "source_format": "GeoJSON",
            "license": "fixture",
            "mode": "manual_official_file",
            "label_fields": ["name"],
            "category_fields": ["category"],
            "min_features": 1,
            "attribute_allowlist": ["id", "name", "category"],
            "key_fields": ["id"],
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.geojson"
            path.write_text(json.dumps(feature_collection), encoding="utf-8")
            result = load_one(self.dsn, cfg, path)

        self.assertEqual(result["status"], "ACTIVE")
        self.assertEqual(result["features"], 1)
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT l.status, l.feature_count, f.label,
                          f.attributes ? 'cpf_titular'
                   FROM ld_core.restriction_layer l
                   JOIN ld_api.current_restriction_feature f USING (layer_key)
                   WHERE l.layer_key='fixture_restriction'"""
            )
            status, count, label, has_pii = cur.fetchone()
            self.assertEqual(status, "ACTIVE")
            self.assertEqual(count, 1)
            self.assertEqual(label, "Área teste")
            self.assertFalse(has_pii)
            cur.execute(
                "SELECT intersects, distance_m FROM ld_api.restrictions_for_point(%s,%s,5000) WHERE layer_key='fixture_restriction'",
                (-46.875, -23.515),
            )
            intersects, distance = cur.fetchone()
            self.assertTrue(intersects)
            self.assertEqual(float(distance), 0.0)


if __name__ == "__main__":
    unittest.main()
