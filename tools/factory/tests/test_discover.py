"""discover.py against a fake ArcGIS REST server (no network)."""
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discover  # noqa: E402
import spec as spec_mod  # noqa: E402

DOCS = {
    "/rest/services": {"folders": ["Cadastro"], "services": []},
    "/rest/services/Cadastro": {"services": [
        {"name": "Cadastro/Mapa", "type": "MapServer"},
        {"name": "Cadastro/Imagem", "type": "ImageServer"}]},
    "/rest/services/Cadastro/Mapa/MapServer": {"layers": [
        {"id": 0, "name": "Lotes"}, {"id": 1, "name": "Zoneamento"},
        {"id": 2, "name": "Pontos de ônibus"}]},
    "/rest/services/Cadastro/Mapa/MapServer/0": {
        "name": "Lotes", "geometryType": "esriGeometryPolygon",
        "fields": [{"name": n} for n in ["OBJECTID", "INSCRICAO_IMOBILIARIA",
                                        "LOGRADOURO", "NUMERO", "BAIRRO",
                                        "NOME_PROPRIETARIO", "AREA_TERRENO"]]},
    "/rest/services/Cadastro/Mapa/MapServer/1": {
        "name": "Zoneamento", "geometryType": "esriGeometryPolygon",
        "fields": [{"name": n} for n in ["OBJECTID", "SIGLA", "NOME_ZONA"]]},
    "/rest/services/Cadastro/Mapa/MapServer/2": {
        "name": "Pontos de ônibus", "geometryType": "esriGeometryPoint",
        "fields": [{"name": "OBJECTID"}]},
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = DOCS.get(self.path.split("?")[0])
        self.send_response(200 if body else 404)
        self.end_headers()
        self.wfile.write(json.dumps(body or {"error": 404}).encode())

    def log_message(self, *args):
        pass


class DiscoverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}/rest/services"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_draft_picks_layers_maps_fields_and_excludes_personal_data(self):
        layers = discover.arcgis_layers(self.base)
        self.assertEqual(len(layers), 3)
        draft = discover.draft("4209102", "sc-x", "arcgis_feature_layer", layers)
        parcels, zoning = draft["layers"]
        self.assertTrue(parcels["url"].endswith("/MapServer/0"))
        self.assertEqual(parcels["fields"]["fiscal_reference"], "INSCRICAO_IMOBILIARIA")
        self.assertEqual(parcels["fields"]["street"], "LOGRADOURO")
        self.assertEqual(parcels["personal_fields_excluded"], ["NOME_PROPRIETARIO"])
        self.assertNotIn("NOME_PROPRIETARIO", parcels["fields"].values())
        self.assertEqual(zoning["fields"]["zone_code"], "SIGLA")
        self.assertEqual(draft["status"], "DRAFT")
        # A draft cannot be approved as-is: license must be filled in by a human.
        self.assertTrue(any("license" in e for e in spec_mod.validate(draft)))


if __name__ == "__main__":
    unittest.main()
