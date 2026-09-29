import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import rural_context

class RuralContextTest(unittest.TestCase):
    def test_report_explains_registry_limits(self):
        values=rural_context.report_values({
          "sigef":{"parcel_code":"SIG-1","status":"CERTIFICADA","area_ha":"10.5"},
          "car":{"car_code":"CAR-1","status":"ATIVO","area_ha":"11","property_type":"IRU"},
          "restrictions":[],
          "warnings":["CAR/SICAR é cadastro declaratório e não prova domínio."]
        })
        text=" ".join(str(x["value"]) for x in values)
        self.assertIn("SIG-1",text)
        self.assertIn("CAR-1",text)
        self.assertIn("não prova domínio",text)
if __name__=="__main__": unittest.main()
