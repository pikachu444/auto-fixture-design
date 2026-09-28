import copy,json,unittest
from pathlib import Path
from src.fixture import mechanics,choose_base,print_fit,assembly
CONFIG=json.loads((Path(__file__).resolve().parents[1]/'inputs/bending.json').read_text())
class EngineeringRules(unittest.TestCase):
    def test_independent_beam_equation(self):
        for k in ['initial','modified']:
            s=CONFIG[k]; m=mechanics(s); I=s['width']*s['thickness']**3/12
            delta=m['force_at_target_N']*m['span_mm']**3/(48*s['elastic_modulus']*I)
            self.assertAlmostEqual(delta,m['deflection_at_target_mm'])
    def test_reference_values(self):
        m=mechanics(CONFIG['modified']); self.assertAlmostEqual(m['span_mm'],128)
        self.assertAlmostEqual(m['design_load_N'],333.3333333333)
        self.assertAlmostEqual(m['deflection_at_target_mm'],1.7066666667)
    def test_thickness_scaling(self):
        a,b=[mechanics(CONFIG[k]) for k in ['initial','modified']]
        self.assertAlmostEqual(b['force_at_target_N']/a['force_at_target_N'],2)
    def test_preserve_input(self):
        original=copy.deepcopy(CONFIG['modified']); mechanics(CONFIG['modified']); self.assertEqual(original,CONFIG['modified'])
    def test_invalid_values(self):
        for value in [-1,0,float('nan'),float('inf')]:
            with self.subTest(value=value):
                s={**CONFIG['modified'],'thickness':value}
                with self.assertRaises(ValueError): mechanics(s)
    def test_short_specimen(self):
        with self.assertRaises(ValueError): mechanics({**CONFIG['modified'],'length':128})
    def test_template_selection(self):
        self.assertEqual(choose_base(128,CONFIG['design'],CONFIG['printer']),(220,160))
        self.assertEqual(choose_base(64,CONFIG['design'],CONFIG['printer']),(160,100))
    def test_capacity_boundary(self):
        self.assertEqual(choose_base(160,CONFIG['design'],CONFIG['printer']),(220,160))
        with self.assertRaises(ValueError): choose_base(160.001,CONFIG['design'],CONFIG['printer'])
    def test_printer_brim(self):
        p=CONFIG['printer']; self.assertTrue(print_fit([232,80,12],p)['fits'])
        self.assertFalse(print_fit([232.01,80,12],p)['fits'])
        self.assertFalse(print_fit([244,80,12],p)['fits'])
    def test_reject_wrong_fixture(self):
        with self.assertRaises(ValueError): assembly(CONFIG['modified'],160,100)
    def test_large_strain_rejected(self):
        with self.assertRaises(ValueError): mechanics({**CONFIG['modified'],'target_strain':.2})
if __name__=='__main__': unittest.main()
