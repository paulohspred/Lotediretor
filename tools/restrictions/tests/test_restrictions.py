from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import psycopg2

import tools.loaders.load_national_restrictions as loader
from tools.loaders.load_national_restrictions import load_one, pg_ogr_dsn


class RestrictionLoaderUnitTest(unittest.TestCase):
    def test_arcgis_download_pages_without_holding_whole_dataset(self):
        class Response:
            def __init__(self, body: bytes):
                self.body = body
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return self.body

        def fake_urlopen(request, timeout=0):
            offset = 1000 if "resultOffset=1000" in request.full_url else 0
            count = 1 if offset else 1000
            features = [
                {
                    "type": "Feature",
                    "properties": {"OBJECTID": offset + i},
                    "geometry": {"type": "Point", "coordinates": [-45.7, -22.2]},
                }
                for i in range(count)
            ]
            return Response(json.dumps({"type": "FeatureCollection", "features": features}).encode())

        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "raw.jsonl"
            normalized = Path(td) / "normalized.geojson"
            with mock.patch.object(loader.urllib.request, "urlopen", side_effect=fake_urlopen):
                _, _, _, manifest = loader.download_arcgis(
                    "https://example.invalid/FeatureServer/0",
                    raw,
                    normalized,
                    ["OBJECTID"],
                )
            data = json.loads(normalized.read_text())
            self.assertEqual(len(data["features"]), 1001)
            self.assertEqual(manifest["page_count"], 2)
            self.assertEqual(manifest["feature_count_raw"], 1001)
            self.assertEqual(len(raw.read_bytes().splitlines()), 2)

    def test_pg_ogr_dsn_accepts_database_url(self):
        value = pg_ogr_dsn("postgresql://u@db.example:5433/lotediretor?sslmode=require")
        self.assertIn("dbname='lotediretor'", value)
        self.assertIn("host='db.example'", value)
        self.assertIn("port='5433'", value)
        self.assertIn("user='u'", value)
        self.assertIn("sslmode='require'", value)



class RestrictionLoaderDatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get("TEST_DATABASE_URL") or os.environ.get("LOTEDIRETOR_DB_DSN")
        if not cls.dsn:
            raise unittest.SkipTest("database not configured")

    def test_snapshot_promotion_pii_filter_and_multiple_intersections(self):
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO ld_catalog.source
                   (source_id,authority,scope,source_type,access_class,verification_status,canonical_url)
                   VALUES ('fixture-restriction','Fixture','BR','fixture','OPEN_REUSABLE','VERIFIED','https://example.invalid/fixture')
                   ON CONFLICT (source_id) DO NOTHING"""
            )

        feature_collection = {
            "type": "FeatureCollection",
            "features": [
                {
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
                            [-45.7102, -22.2602], [-45.7088, -22.2602],
                            [-45.7088, -22.2588], [-45.7102, -22.2588],
                            [-45.7102, -22.2602],
                        ]],
                    },
                },
                {
                    "type": "Feature",
                    "properties": {"id": "fx-2", "name": "Área teste 2", "category": "teste"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [-45.7098, -22.2598], [-45.7092, -22.2598],
                            [-45.7092, -22.2592], [-45.7098, -22.2592],
                            [-45.7098, -22.2598],
                        ]],
                    },
                },
            ],
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
            "retain_raw": False,
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.geojson"
            path.write_text(json.dumps(feature_collection), encoding="utf-8")
            result = load_one(self.dsn, cfg, path)

        self.assertEqual(result["status"], "ACTIVE")
        self.assertEqual(result["features"], 2)
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT l.status, l.feature_count, f.label,
                          f.attributes ? 'cpf_titular'
                   FROM ld_core.restriction_layer l
                   JOIN ld_api.current_restriction_feature f USING (layer_key)
                   WHERE l.layer_key='fixture_restriction'
                   ORDER BY f.label"""
            )
            rows = cur.fetchall()
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row[0] == "ACTIVE" for row in rows))
            self.assertTrue(all(row[1] == 2 for row in rows))
            self.assertTrue(all(not row[3] for row in rows))

            cur.execute(
                """SELECT intersects, distance_m
                   FROM ld_api.restrictions_for_point(%s,%s,5000)
                   WHERE layer_key='fixture_restriction'""",
                (-45.7095, -22.2595),
            )
            hits = cur.fetchall()
            self.assertEqual(len(hits), 2)
            self.assertTrue(all(row[0] for row in hits))
            self.assertTrue(all(float(row[1]) == 0.0 for row in hits))

            cur.execute(
                "SELECT object_key FROM ld_catalog.snapshot WHERE snapshot_id=%s",
                (result["snapshot_id"],),
            )
            self.assertIsNone(cur.fetchone()[0])


if __name__ == "__main__":
    unittest.main()
