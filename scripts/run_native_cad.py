"""End-to-end FreeCAD feature selection, definition and CAD regeneration."""
import json
from pathlib import Path

import cadquery as cq

from fixturelab import native_cad


def run():
    root=Path('artifacts/native_acceptance');root.mkdir(parents=True,exist_ok=True)
    info=native_cad.create_sample();design=info['design']
    assert info['parameters']==[]
    candidates={x['key'] for x in info['candidates']}
    assert {'SupportBlock|property|Length','RollerCradle|property|Radius',
            'BoltBore1|property|Radius'}<=candidates
    info=native_cad.register(design,'SupportBlock|property|Length','my_support_width',28,60)
    assert [p['name'] for p in info['parameters']]==['my_support_width']
    info=native_cad.register(design,'RollerCradle|property|Radius','selected_cradle_radius',3,8)
    info=native_cad.register(design,'BoltBore1|property|Radius','selected_bore_radius',2,20)
    assert [p['name'] for p in native_cad.inspect(design)['parameters']]==[
        'my_support_width','selected_cradle_radius','selected_bore_radius']
    original=native_cad.execute(design,{},root/'original')
    changed=native_cad.execute(design,{'my_support_width':38,'selected_cradle_radius':5},root/'changed')
    blocked=native_cad.execute(design,{'selected_bore_radius':5},root/'blocked')
    assert original['cad_generated'] and changed['cad_generated']
    assert original['bounds_mm'][0]==32 and changed['bounds_mm'][0]==38
    assert changed['parameters']['selected_cradle_radius']==5
    assert cq.importers.importStep(str(root/'changed'/'native.step')).val().BoundingBox().xlen==38
    assert all(c['status']=='PASS' for c in changed['cad_checks'])
    assert {'editable.FCStd','native.step','native_printed_part.stl','native_printed_part.3mf'}<=set(changed['files'])
    assert blocked['decision']=='REJECTED' and not blocked['cad_generated']
    assert any(c['code']=='bore_1_edge_land' and c['status']=='FAIL' for c in blocked['checks'])
    assert not list((root/'blocked').glob('*.step'))
    imported=native_cad.import_document((root/'changed'/'editable.FCStd').read_bytes())
    assert set(x['name'] for x in imported['parameters'])=={
        'my_support_width','selected_cradle_radius','selected_bore_radius'}
    # A separate sketch-driven document exercises a user-picked constraint,
    # rather than any of the Part::Box/Cylinder properties used above.
    sketch=native_cad.create_sample('sketch_locator')
    assert sketch['parameters']==[]
    assert 'LocatorProfile|constraint|0' in {x['key'] for x in sketch['candidates']}
    defined=native_cad.register(sketch['design'],'LocatorProfile|constraint|0',
                                'my_locator_radius',2,10)
    assert defined['parameters'][0]['name']=='my_locator_radius'
    sketch_change=native_cad.execute(sketch['design'],{'my_locator_radius':6},root/'sketch_changed')
    assert sketch_change['cad_generated'] and sketch_change['bounds_mm'][0]==12
    assert cq.importers.importStep(str(root/'sketch_changed'/'native.step')).val().BoundingBox().xlen==12
    try:native_cad.register(design,'BoltBore1|property|Height','ineffective_cutter_height',20,40)
    except ValueError as error:
        assert 'no measurable effect' in str(error)
    else:raise AssertionError('An ineffective CAD dimension was accepted')
    summary={'status':'PASS','design':design,'discovered_candidate_count':len(candidates),
             'user_defined_parameters':[p['name'] for p in info['parameters']],
             'original_bounds_mm':original['bounds_mm'],'changed_bounds_mm':changed['bounds_mm'],
             'change_cad_checks_passed':sum(c['status']=='PASS' for c in changed['cad_checks']),
             'blocked_decision':blocked['decision'],'reopened_definition_count':len(imported['parameters']),
             'sketch_user_defined_parameter':defined['parameters'][0]['name'],
             'sketch_changed_bounds_mm':sketch_change['bounds_mm'],
             'ineffective_dimension_blocked':True}
    (root/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':run()
