"""Tests for the municipal factory (spec validation + harvest on PostGIS).

DB tests run when TEST_DATABASE_URL points at a migrated database that has the
sample IBGE mesh (database/fixtures/ibge_municipios_sample.sql) loaded.
"""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "factory"))

import spec as spec_mod  # noqa: E402

FIXTURE = ROOT / "database" / "fixtures" / "factory" / "3159605.json"
DSN = os.environ.get("TEST_DATABASE_URL")


def base_spec():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class SpecValidationTest(unittest.TestCase):
    def test_fixture_is_valid(self):
        self.assertEqual(spec_mod.validate(base_spec()), [])

    def test_personal_fields_are_rejected(self):
        s = base_spec()
        s["layers"][0]["attribute_allowlist"] = ["NOME_PROPRIETARIO"]
        self.assertTrue(any("personal data" in e for e in spec_mod.validate(s)))
        s = base_spec()
        s["layers"][0]["fields"]["street"] = "CPF_CONTRIBUINTE"
        self.assertTrue(any("personal data" in e for e in spec_mod.validate(s)))

    def test_remote_layers_must_use_https(self):
        s = base_spec()
        s["layers"][0].update(kind="arcgis_feature_layer", url="http://x/MapServer/1")
        self.assertTrue(any("https" in e for e in spec_mod.validate(s)))

    def test_approved_requires_review_and_known_source(self):
        s = base_spec()
        del s["reviewed_by"]
        self.assertTrue(any("reviewed_by" in e for e in spec_mod.validate(s)))
        errors = spec_mod.validate(base_spec(), known_sources={"other"})
        self.assertTrue(any("not in registry" in e for e in errors))

    def test_zoning_requires_zone_code(self):
        s = base_spec()
        del s["layers"][1]["fields"]["zone_code"]
        self.assertTrue(any("zone_code" in e for e in spec_mod.validate(s)))

    def test_injection_like_field_names_are_rejected(self):
        s = base_spec()
        s["layers"][0]["fields"]["street"] = 'x"; DROP TABLE y; --'
        self.assertTrue(any("invalid upstream field" in e for e in spec_mod.validate(s)))

    def test_repository_specs_are_valid(self):
        known = spec_mod.registry_ids()
        for path in sorted(spec_mod.SPEC_DIR.glob("*.json")):
            with self.subTest(spec=path.name):
                spec_mod.load(path, known)


@unittest.skipUnless(DSN, "TEST_DATABASE_URL not set")
class HarvestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg2
        import harvest

        cls.psycopg2 = psycopg2
        cls.harvest = harvest
        with psycopg2.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute((ROOT / "database/fixtures/factory/load_fixture.sql").read_text())

    def query(self, sql, params=()):
        with self.psycopg2.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def test_harvest_loads_parcels_and_zones_and_flips_current(self):
        self.harvest.harvest(DSN, FIXTURE, allow_draft=False, roles=None)
        self.harvest.harvest(DSN, FIXTURE, allow_draft=False, roles={"parcels"})
        current = self.query(
            "SELECT role, feature_count FROM ld_catalog.municipal_layer_load "
            "WHERE ibge_code='3159605' AND is_current ORDER BY role")
        self.assertEqual(current, [("parcels", 12), ("zoning", 2)])
        history = self.query(
            "SELECT count(*) FROM ld_catalog.municipal_layer_load "
            "WHERE ibge_code='3159605' AND role='parcels'")[0][0]
        self.assertGreaterEqual(history, 2)

        row = self.query(
            "SELECT fiscal_reference, cib, sector, block, lot, unit, postal_code, "
            "land_area_m2::text, built_area_m2::text, frontage_m::text, "
            "cadastral_use, cadastral_status, attributes::text, parcel_id "
            "FROM ld_api.municipal_parcel_at('3159605', -45.7095, -22.2595)")[0]
        self.assertEqual(row[0], "01.02.000")
        self.assertEqual(row[1], "CIB-0001")
        self.assertEqual(row[2:7], ("01", "12", "01", "001", "37540-000"))
        self.assertEqual(row[7:10], ("360.50", "120.25", "12.00"))
        self.assertEqual(row[10:12], ("RESIDENCIAL", "ATIVO"))
        self.assertNotIn("PROPRIET", row[12])
        prov = self.query(
            "SELECT field_name, upstream_field FROM ld_domain.municipal_parcel_field_provenance "
            "WHERE parcel_id=%s ORDER BY field_name", (row[13],))
        self.assertIn(("cib", "CIB"), prov)
        self.assertIn(("built_area_m2", "AREA_CONSTRUIDA"), prov)
        by_cib = self.query(
            "SELECT cib, matched_field FROM ld_api.municipal_parcel_search('3159605','CIB-0001',10)")
        self.assertEqual(by_cib[0], ("CIB-0001", "CIB"))
        by_inscricao = self.query(
            "SELECT fiscal_reference, matched_field FROM ld_api.municipal_parcel_search('3159605','01.02.000',10)")
        self.assertEqual(by_inscricao[0], ("01.02.000", "INSCRICAO"))
        zones = self.query(
            "SELECT zone_code FROM ld_api.municipal_zones_for('3159605', "
            "(SELECT geom FROM ld_api.municipal_parcel_at('3159605', -45.7095, -22.2595)))")
        self.assertEqual(zones[0][0], "ZR1")

    def test_wrong_crs_is_rejected_and_nothing_changes(self):
        self.harvest.harvest(DSN, FIXTURE, allow_draft=False, roles={"zoning"})
        before = self.query(
            "SELECT load_id FROM ld_catalog.municipal_layer_load "
            "WHERE ibge_code='3159605' AND role='zoning' AND is_current")
        bad = copy.deepcopy(base_spec())
        bad["layers"][1]["source_srid"] = 31983  # lat/lng read as UTM metres
        bad["layers"][1]["url"] = str(FIXTURE.parent / "zones.geojson")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "3159605.json"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(Exception):
                self.harvest.harvest(DSN, path, allow_draft=False, roles={"zoning"})
        after = self.query(
            "SELECT load_id FROM ld_catalog.municipal_layer_load "
            "WHERE ibge_code='3159605' AND role='zoning' AND is_current")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
