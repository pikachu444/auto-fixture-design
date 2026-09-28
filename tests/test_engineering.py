import copy,json,math
from pathlib import Path
import pytest
from fixturelab.core import evaluate,validate
ROOT=Path(__file__).resolve().parents[1]
def data(name='bend_8mm'):return json.loads((ROOT/'examples'/f'{name}.json').read_text())
def codes(result,status='FAIL'):return {c['code'] for c in result['checks'] if c['status']==status}

@pytest.mark.parametrize('case',json.loads((ROOT/'examples/suite.json').read_text()))
def test_suite_decisions(case):
    r=evaluate(json.loads((ROOT/'examples'/case['file']).read_text()))
    assert r['decision']==case['expected']
    assert r['production_release']=='UNKNOWN'

@pytest.mark.parametrize('name',['bend_4mm','bend_8mm'])
def test_independent_beam_equation(name):
    d=data(name);s=d['specimen'];r=evaluate(d);m=r['metrics']
    inertia=s['width']*s['thickness']**3/12
    delta=m['force_target_N']*m['span_mm']**3/(48*s['elastic_modulus']*inertia)
    assert m['deflection_mm']==pytest.approx(delta)
    stress=3*m['nominal_strength_load_N']*m['span_mm']/(2*s['width']*s['thickness']**2)
    assert stress==pytest.approx(s['strength'])

def test_known_results():
    assert evaluate(data())['metrics']['design_load_N']==pytest.approx(333.3333333333)
    assert evaluate(data('film_alignment'))['metrics']['design_load_N']==pytest.approx(187.5)
    assert evaluate(data('foam_locator'))['metrics']['design_load_N']==pytest.approx(1562.5)
    assert evaluate(data('fold_radius_former'))['metrics']['outer_fiber_strain']==pytest.approx(.3/40.3)

def test_original_input_unchanged():
    d=data();before=copy.deepcopy(d);evaluate(d);assert d==before

@pytest.mark.parametrize('value',[0,-1,float('nan'),float('inf'),True,'8',None])
def test_invalid_dimensions(value):
    d=data();d['specimen']['thickness']=value
    with pytest.raises(ValueError):validate(d)

def test_wrong_units():
    d=data();d['units']='m_N_Pa'
    with pytest.raises(ValueError):validate(d)

def test_typo_field_rejected():
    d=data();d['specimen']['widht']=10
    with pytest.raises(ValueError):validate(d)

def test_no_frame_only_approval():
    r=evaluate(data('bend_load_reject'))
    assert 'frame_capacity' not in codes(r)
    assert {'load_cell_capacity','tool_capacity'}<=codes(r)

def test_unknown_capacity_stays_unknown():
    d=data();d['equipment']['load_cell_capacity']=None
    r=evaluate(d);assert 'load_cell_capacity' in codes(r,'UNKNOWN')
    assert r['production_release']=='UNKNOWN'

def test_printer_boundary_and_reason():
    d=data();d['printer']['build'][0]=238
    assert evaluate(d)['decision']=='REVIEW_REQUIRED'
    d['printer']['build'][0]=237.99
    assert 'base_printer_fit' in codes(evaluate(d))

def test_travel_boundary():
    d=data('film_alignment');d['specimen']['target_strain']=.4
    assert 'usable_travel' not in codes(evaluate(d))
    d['specimen']['target_strain']=.4001
    assert 'usable_travel' in codes(evaluate(d))

def test_engagement_guard():
    d=data('film_alignment');d['specimen']['length']=149
    assert 'grip_engagement' in codes(evaluate(d))

def test_fold_radius_monotonic():
    d=data('fold_radius_former');a=evaluate(d)['metrics']['outer_fiber_strain']
    d['specimen']['inner_radius']*=2
    assert evaluate(d)['metrics']['outer_fiber_strain']<a

def test_no_low_safety_factor():
    d=data();d['design']['load_factor']=.8
    with pytest.raises(ValueError):validate(d)

def test_id_path_injection():
    d=data();d['id']='../../outside'
    with pytest.raises(ValueError):validate(d)
