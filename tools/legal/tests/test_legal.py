"""Legal engine tests: segmentation, rule extraction, temporal validity, review."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "legal"))

import rules  # noqa: E402
from segment import segment  # noqa: E402

DSN = os.environ.get("TEST_DATABASE_URL")

LAW = """LEI COMPLEMENTAR Nº 1, DE 1º DE JANEIRO DE 2024
Dispõe sobre o uso do solo.
CAPÍTULO I
DAS ZONAS
Art. 1º Esta lei institui as zonas.
Art. 2º Na Zona Residencial 1 (ZR1):
I - coeficiente de aproveitamento: a) residência unifamiliar: 1. mínimo = 0,1; 2. básico = 1,0; 3. máximo = 1,5;
II - taxa de ocupação: 60% (sessenta por cento);
III - recuos: a) de frente = 4,00m; b) laterais = sem restrições;
§ 1º Os recuos contam da alvenaria.
Parágrafo único. Vide anexo.
12
Art. 10. Revogam-se as disposições em contrário.
ANEXO I - QUADRO DE PARÂMETROS
Zona ZR1 lote mínimo 1.000 m2
"""


class SegmentTest(unittest.TestCase):
    def test_structure_and_paths(self):
        pages = LAW.split("12\n")  # page break where the page number was
        provisions = segment(pages)
        paths = [p.path for p in provisions]
        self.assertIn("art. 1º", paths)
        self.assertIn("art. 2º inc. I", paths)
        self.assertIn("art. 2º inc. III", paths)
        self.assertIn("art. 2º § 1º", paths)
        self.assertIn("art. 2º parágrafo único", paths)
        self.assertIn("art. 10", paths)
        self.assertIn("Anexo I", paths)
        art10 = next(p for p in provisions if p.path == "art. 10")
        self.assertEqual(art10.page_start, 2)
        self.assertNotIn("12", art10.text.split())
        inc = next(p for p in provisions if p.path == "art. 2º inc. I")
        art2 = next(i for i, p in enumerate(provisions) if p.path == "art. 2º")
        self.assertEqual(inc.parent_index, art2)


class RuleExtractionTest(unittest.TestCase):
    def test_extracts_parameters_with_uses_and_excerpts(self):
        text = " ".join(p.text for p in segment([LAW]) if p.path.startswith("art. 2"))
        got = {(c.parameter, c.use_condition): c for c in rules.extract(text)}
        self.assertEqual(got[("CA_BASICO", "residência unifamiliar")].value, 1.0)
        self.assertEqual(got[("CA_MAXIMO", "residência unifamiliar")].value, 1.5)
        self.assertEqual(got[("TO_MAXIMA", "GERAL")].value, 60.0)
        self.assertEqual(got[("RECUO_FRONTAL_M", "GERAL")].value, 4.0)
        self.assertTrue(got[("RECUO_LATERAL_M", "GERAL")].no_restriction)
        for c in got.values():
            self.assertTrue(c.excerpt)

    def test_brazilian_numbers(self):
        self.assertEqual(rules.to_number("1.000"), 1000.0)
        self.assertEqual(rules.to_number("1.000,50"), 1000.5)
        self.assertEqual(rules.to_number("0,25"), 0.25)
        self.assertEqual(rules.to_number("26.7"), 26.7)

    def test_barueri_transcription_regressions(self):
        data = json.loads((ROOT / "data/legal/barueri-lc565-sector-rules.json").read_text("utf-8"))
        supi = {(c.parameter, c.use_condition): c.value
                for c in rules.extract(data["groups"]["SUPI-1"]["rule_text"])}
        self.assertEqual(supi[("LOTE_MINIMO_M2", "GERAL")], 1000.0)
        sem = {c.parameter: c.value for c in rules.extract(data["groups"]["SEM"]["rule_text"])}
        self.assertEqual(sem["RECUO_FRONTAL_M"], 15.0)


@unittest.skipUnless(DSN, "TEST_DATABASE_URL not set")
class LegalDatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg2
        cls.pg = psycopg2
        subprocess.run([sys.executable, str(ROOT / "tools/legal/seed_catalog.py"),
                        "--dsn", DSN], check=True)

    def q(self, sql, params=()):
        with self.pg.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else None

    def test_candidates_never_look_confirmed(self):
        confirmed = self.q("SELECT count(*) FROM ld_api.effective_urban_rules('3505708','SER')")
        self.assertEqual(confirmed[0][0], 0)
        cands = self.q("SELECT count(*) FROM ld_api.effective_urban_rules('3505708','A-04', current_date, true)")
        self.assertGreater(cands[0][0], 5)

    def test_confirmed_requires_reviewer(self):
        with self.assertRaises(self.pg.errors.CheckViolation):
            self.q("UPDATE ld_legal.urban_rule SET status='CONFIRMED' "
                   "WHERE rule_id=(SELECT rule_id FROM ld_legal.urban_rule LIMIT 1)")

    def test_review_flow_and_temporal_validity(self):
        rule_id = self.q(
            "SELECT rule_id FROM ld_legal.urban_rule WHERE ibge_code='3505708' "
            "AND zone_code='SER' AND parameter='CA_MAXIMO' "
            "AND use_condition='residência unifamiliar'")[0][0]
        subprocess.run([sys.executable, str(ROOT / "tools/legal/review_rules.py"),
                        "--dsn", DSN, "confirm", str(rule_id), "--reviewer", "teste",
                        "--note", "Conferido no texto transcrito do art. 35"], check=True)
        # Alias A-04 → SER, in force today, not before the law existed.
        now = self.q("SELECT parameter, value FROM ld_api.effective_urban_rules('3505708','A-04')")
        self.assertIn(("CA_MAXIMO", 1.1), [(p, float(v)) for p, v in now])
        before = self.q("SELECT count(*) FROM ld_api.effective_urban_rules('3505708','A-04','2020-01-01')")
        self.assertEqual(before[0][0], 0)
        events = self.q("SELECT to_status FROM ld_legal.rule_review_event WHERE rule_id=%s", (rule_id,))
        self.assertEqual(events, [("CONFIRMED",)])

    def test_search_is_scoped_to_jurisdiction(self):
        hits = self.q("SELECT path FROM ld_api.search_provisions('recuos alvenaria','3505708')")
        self.assertTrue(hits)
        other = self.q("SELECT count(*) FROM ld_api.search_provisions('recuos alvenaria','3550308')")
        self.assertEqual(other[0][0], 0)

    def test_ingest_cli_versions_text(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write(LAW)
        cmd = [sys.executable, str(ROOT / "tools/legal/ingest.py"), fh.name, "--dsn", DSN,
               "--jurisdiction", "MUNICIPAL", "--ibge", "3159605", "--kind", "LEI_COMPLEMENTAR",
               "--number", "1/2024", "--title", "LC 1/2024 (teste)", "--valid-from", "2024-01-01",
               "--zone-article", "ZR1=2"]
        first = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
        second = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
        self.assertIn("nova versão", first)
        self.assertIn("idêntico", second)
        n = self.q("SELECT count(*) FROM ld_legal.urban_rule WHERE ibge_code='3159605' AND zone_code='ZR1'")
        self.assertGreaterEqual(n[0][0], 4)


if __name__ == "__main__":
    unittest.main()
