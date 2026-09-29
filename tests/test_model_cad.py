import json

import cadquery as cq
import pytest

from fixturelab import model_cad
from fixturelab.model_cad import catalogue,definition,execute


def test_model_source_drives_discovered_parameters_and_model_variants(tmp_path):
    listed={x['id']:x for x in catalogue()}
    assert set(listed)=={'roller_support','film_tray'}
    assert set(x['name'] for x in listed['roller_support']['parameters'])!={'specimen_width_mm'}
    assert any(x['name']=='specimen_width_mm' for x in listed['film_tray']['parameters'])

    original=execute('roller_support',{},tmp_path/'original')
    modified=execute('roller_support',{'support_width_mm':38},tmp_path/'modified')
    tray=execute('film_tray',{'specimen_width_mm':20},tmp_path/'tray')
    assert all(x['cad_generated'] for x in (original,modified,tray))
    assert original['bom'][0]['bounds_mm']==pytest.approx([32,40,26])
    assert modified['bom'][0]['bounds_mm']==pytest.approx([38,40,26])
    assert tray['bom'][0]['bounds_mm']==pytest.approx([162,32.5,4])
    assert cq.importers.importStep(str(tmp_path/'modified'/'assembly.step')).val().BoundingBox().xlen==pytest.approx(38)
    assert {'cad_source.py','roller_support.stl','roller_support.3mf','assembly.step','report.html'}<={p.name for p in (tmp_path/'modified').iterdir()}
    assert all(c['status']=='PASS' for c in modified['cad_checks'])


def test_source_relation_blocks_cad_and_range_is_not_equipment_qualification(tmp_path):
    rejected=execute('roller_support',{'bolt_pitch_x_mm':30},tmp_path/'relation')
    assert rejected['decision']=='REJECTED'
    assert not rejected['cad_generated']
    assert any(c['code']=='cad_source_relation' and c['status']=='FAIL' for c in rejected['checks'])
    assert not list((tmp_path/'relation').glob('*.stl'))
    bounded=execute('film_tray',{'specimen_width_mm':100},tmp_path/'range')
    assert bounded['decision']=='REJECTED'
    assert not list((tmp_path/'range').glob('*.step'))


def test_registered_sources_only_and_no_parameter_invention():
    with pytest.raises(ValueError,match='name'):definition('../secrets')
    with pytest.raises(ValueError,match='not registered'):definition('missing')
    with pytest.raises(ValueError,match='Unknown CAD parameter'):
        execute('roller_support',{'invented_dimension':7},'/tmp/unused-cad-model-test')


def test_new_cad_source_is_discovered_without_adding_a_shape_template(tmp_path,monkeypatch):
    models=tmp_path/'models';models.mkdir()
    (models/'adapter_block.py').write_text('''import cadquery as cq
FIXTURE_META = {
    "title": "Adapter block",
    "description": "Independent source-added solid",
    "parameters": {"body_width_mm": {"label": "Body width", "unit": "mm", "min": 10, "max": 40}},
}
body_width_mm = 12.0
show_object(cq.Workplane("XY").box(body_width_mm, 9, 7))
''')
    monkeypatch.setattr(model_cad,'MODELS',models)
    assert [item['id'] for item in catalogue()]==['adapter_block']
    result=execute('adapter_block',{'body_width_mm':18},tmp_path/'result')
    assert result['cad_generated']
    assert result['bom'][0]['bounds_mm']==pytest.approx([18,9,7])
    assert cq.importers.importStep(str(tmp_path/'result'/'assembly.step')).val().BoundingBox().xlen==pytest.approx(18)
