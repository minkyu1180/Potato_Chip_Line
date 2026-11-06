"""Quotation quantities: mass reconciliation and independently known stock sizes."""
import csv
import math
import tempfile
import unittest
from pathlib import Path

import station1_design as design
from station1_materials import rectangle_blank


class MaterialTakeoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = design.analyze({}, include_comparison=False)
        cls.material = cls.report['material_takeoff']

    def row(self, specification):
        return next(q for q in self.material['rows'] if q['specification'] == specification)

    def test_every_component_counted_once_without_load_allowance(self):
        names = [q['name'] for q in self.material['details']]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), {q['name'] for q in self.report['bom']})
        self.assertAlmostEqual(self.material['accounted_mass_kg'], self.report['base_mass_kg'])
        self.assertLess(self.material['accounted_mass_kg'], self.report['dead_mass_kg'])

    def test_known_shaft_and_pipe_stock(self):
        shaft = self.row('Ø150 mm')
        self.assertEqual(shaft['model_count'], 2)
        self.assertAlmostEqual(shaft['length_m'], 2*1.35)
        self.assertAlmostEqual(shaft['mass_kg'], math.pi*.075**2*2.7*7930)
        pipe = self.row('Ø60×t5 mm')
        self.assertEqual(pipe['model_count'], 17)
        self.assertAlmostEqual(pipe['length_m'], 17*.670)
        self.assertAlmostEqual(pipe['mass_kg'], math.pi*(.030**2-.025**2)*17*.670*7930)
        self.assertEqual(self.row('160x160x8 mm')['model_count'], 3)
        self.assertAlmostEqual(self.row('160x160x8 mm')['length_m'], 6.3)

    def test_plate_cutouts_and_normal_thickness(self):
        parts = {q['name']: q for q in self.material['details']}
        foot = parts['01_Anchor_Foot_100_-1']
        self.assertAlmostEqual(foot['blank_area_m2'], .2*.2)
        self.assertAlmostEqual(foot['mass_kg'], (.2*.2-4*math.pi*.009**2)*.02*7930)
        slope = parts['01_Hopper_Slope_1']
        self.assertEqual(slope['thickness_mm'], 6)
        self.assertAlmostEqual(slope['blank_area_m2'], 2*math.hypot(.675, .890))
        for q in self.material['details']:
            if q['category'] == 'plate':
                self.assertGreaterEqual(q['blank_mass_kg']+1e-8, q['mass_kg'], q['name'])

    def test_rotated_blank_avoids_axis_aligned_waste(self):
        a = math.radians(37)
        points = [(x*math.cos(a)-y*math.sin(a), x*math.sin(a)+y*math.cos(a))
                  for x, y in [(0, 0), (100, 0), (100, 5), (0, 5)]]
        w, h = rectangle_blank(points)
        self.assertAlmostEqual(w, 5)
        self.assertAlmostEqual(h, 100)

    def test_purchased_units_and_unresolved_castings(self):
        belt = self.row('식품용 TPU 무단 벨트 670×6 mm')
        self.assertEqual(belt['model_count'], 4)
        self.assertEqual(belt['order_count'], 1)
        self.assertEqual(belt['quote_quantity'], 1)
        self.assertEqual(sum(q['order_count'] for q in self.material['rows'] if '베어링 유닛' in q['specification']), 62)
        self.assertEqual(self.row('게이트 핸드휠')['category'], 'pending')
        self.assertEqual(self.row('배출 경사 립')['category'], 'pending')
        self.assertEqual(self.row('주 감속기')['quote_unit'], '개/식')

    def test_configuration_propagates_to_quantities(self):
        changed = design.analyze({'side_sheet_mm': 10, 'steel_density_kg_m3': 8000, 'frame_type': 'solid'}, include_comparison=False)
        m = changed['material_takeoff']
        self.assertFalse(any(q['category'] == 'square_tube' for q in m['rows']))
        slope = next(q for q in m['details'] if q['name']=='01_Hopper_Slope_1')
        self.assertEqual(slope['thickness_mm'], 10)
        self.assertAlmostEqual(slope['mass_kg'], 2*math.hypot(.675, .890)*.010*8000)
        self.assertAlmostEqual(m['accounted_mass_kg'], changed['base_mass_kg'])

    def test_report_exports_actual_line_items(self):
        with tempfile.TemporaryDirectory() as temp:
            path, report = design.write_report(temp)
            page = path.read_text(encoding='utf-8')
            self.assertIn('material-estimate', page)
            for filename, key in [('01_Material_Summary.csv', 'rows'), ('01_Material_Detail.csv', 'details')]:
                self.assertIn(filename, page)
                with (Path(temp)/filename).open(encoding='utf-8-sig', newline='') as f:
                    rows = list(csv.DictReader(f))
                self.assertEqual(len(rows), len(report['material_takeoff'][key]))


if __name__ == '__main__':
    unittest.main()
