import json
from pathlib import Path

import pytest

from fixturelab.cad import build
from fixturelab.core import evaluate
from fixturelab.handcheck import bending_and_support,compare_specimen_scale_check

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('entry',json.loads((ROOT/'examples/suite.json').read_text()),ids=lambda x:x['file'])
def test_all_example_handchecks_match_and_detect_bad_metric(entry):
    data=json.loads((ROOT/'examples'/entry['file']).read_text())
    metrics=evaluate(data)['metrics']
    check=compare_specimen_scale_check(data,metrics)
    assert check['status']=='MATCH'
    key=next(iter(check['values']))
    with pytest.raises(RuntimeError,match='mismatch'):
        compare_specimen_scale_check(data,{**metrics,key:metrics[key]+1})


def test_independent_handcheck_8mm_geometry_and_units():
    data=json.loads((ROOT/'examples/bend_8mm.json').read_text())
    material=json.loads((ROOT/'examples/printed_material_ASSUMED.json').read_text())
    shape=next(p['shape'] for p in build(evaluate(data)) if p['name']=='printed_support_left')
    h=bending_and_support(data,material,shape)
    assert h['nominal_strength_specimen_load_N']==pytest.approx(266.6666666667)
    assert h['design_total_load_N']==pytest.approx(333.3333333333)
    assert h['gross_support_area_mm2']==pytest.approx(1280)
    assert h['nominal_gross_compressive_stress_MPa']==pytest.approx(166.6666666667/1280)
    assert h['ideal_uniform_axial_shortening_mm']==pytest.approx(166.6666666667*26/(900*1280))
