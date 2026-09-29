"""Offline tests for point_context (federal queries are stubbed)."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import federal_context  # noqa: E402
import point_context  # noqa: E402
import restriction_context  # noqa: E402
import rural_context  # noqa: E402


class PointContextTest(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def fake_load(lat, lng, ibge, geometry):
            self.calls.append((lat, lng, ibge, geometry))
            return {
                "hydrology": {"macro": {"DMA_NM": "Paraná", "DMA_CD": "6"}},
                "query_errors": {"incra_sigef": "TimeoutError"},
                "queried_at": "2026-09-28T00:00:00Z",
                "interpretation": "contexto",
            }

        self._orig = federal_context.load
        self._orig_restrictions = restriction_context.query_geometry
        self._orig_rural = rural_context.load
        federal_context.load = fake_load
        restriction_context.query_geometry = lambda geometry: {"hits": [], "unavailable": []}
        rural_context.load = lambda lng, lat: {"sigef": None, "car": None, "restrictions": [], "warnings": []}

    def tearDown(self):
        federal_context.load = self._orig
        restriction_context.query_geometry = self._orig_restrictions
        rural_context.load = self._orig_rural

    def test_rejects_points_outside_brazil_and_bad_codes(self):
        for lat, lng, ibge in [(40.7, -74.0, "3550308"), (-10, -50, "123"),
                               (float("nan"), -50, "3550308")]:
            with self.assertRaises(ValueError):
                point_context.build(lat, lng, ibge)
        self.assertEqual(self.calls, [])

    def test_builds_sections_and_reports_unavailable_sources(self):
        out = point_context.build(-22.25, -45.70, "3159605")
        self.assertEqual(out["mode"], "POINT_CONTEXT")
        self.assertEqual(self.calls[0][2], "3159605")
        titles = [s["title"] for s in out["sections"]]
        self.assertIn("Contexto territorial e socioeconômico", titles)
        self.assertEqual(out["unavailable_sources"], ["INCRA · SIGEF"])
        self.assertIn("Não é o limite do lote", out["analysis_area"]["note"])

    def test_analysis_square_is_about_50m(self):
        ring = point_context.analysis_square(-22.25, -45.70)["coordinates"][0]
        width_deg = ring[1][0] - ring[0][0]
        height_deg = ring[2][1] - ring[1][1]
        width_m = width_deg * 111_320 * math.cos(math.radians(-22.25))
        self.assertAlmostEqual(width_m, 50, delta=0.5)
        self.assertAlmostEqual(height_deg * 111_320, 50, delta=0.5)


if __name__ == "__main__":
    unittest.main()
