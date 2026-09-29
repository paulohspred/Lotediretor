import unittest

import restriction_context


class RestrictionReportTest(unittest.TestCase):
    def test_unavailable_layers_do_not_claim_absence(self):
        values = restriction_context.report_values({
            "hits": [],
            "unavailable": [{"layer_key": "inpe_prodes", "status": "NOT_LOADED"}],
        })
        self.assertIn("Sem conclusão completa", values[0]["value"])

    def test_report_includes_source_and_dates(self):
        values = restriction_context.report_values({
            "hits": [{
                "theme": "MINING_PROCESS",
                "label": "Processo 123",
                "upstream_key": "123",
                "category": "Pesquisa",
                "intersects": False,
                "distance_m": 120.4,
                "authority": "ANM",
                "loaded_at": "2026-09-28",
                "source_updated_at": "2026-09-27",
            }]
        })
        self.assertIn("Fonte: ANM", values[0]["value"])
        self.assertIn("Carga: 2026-09-28", values[0]["value"])
        self.assertIn("120.4 m", values[0]["value"])


if __name__ == "__main__":
    unittest.main()
