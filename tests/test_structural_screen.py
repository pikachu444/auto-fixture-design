import json
from pathlib import Path

import pytest

from fixturelab.cad import build
from fixturelab.core import evaluate
from scripts.run_structural_screen import elastic_material_lines,extract_vertical_displacements,parse_gmsh_inp,quadratic_tet_jacobian_quality,write_deck

ROOT=Path(__file__).resolve().parents[1]


def test_mesh_import_and_actual_support_boundary_deck(tmp_path):
    # Two C3D10 elements exercise Abaqus node/element parsing independently of gmsh.
    mesh=tmp_path/'gmsh.inp'
    mesh.write_text('''*Heading
*Node
1, 0, 0, 0
2, 1, 0, 0
3, 0, 1, 0
4, 0, 0, 1
5, .5, 0, 0
6, .5, .5, 0
7, 0, .5, 0
8, 0, 0, .5
9, .5, 0, .5
10, 0, .5, .5
*Element, type=C3D10, elset=solid
1, 1,2,3,4,5,6,7,8,9,10
''')
    nodes,elements=parse_gmsh_inp(mesh)
    assert len(nodes)==10 and elements[1]==tuple(range(1,11))
    assert quadratic_tet_jacobian_quality(nodes,elements)>0
    nodes[10]=(0,.5,-100)
    with pytest.raises(RuntimeError,match='Jacobian'):
        quadratic_tet_jacobian_quality(nodes,elements)
    data=json.loads((ROOT/'examples/bend_8mm.json').read_text())
    material=json.loads((ROOT/'examples/printed_material_ASSUMED.json').read_text())
    support=next(p['shape'] for p in build(evaluate(data)) if p['name']=='printed_support_left')
    # Real CAD is required to select both sets; synthetic elements cannot pass
    # the CAD volume check, so this must fail rather than claiming a simulation.
    with pytest.raises(RuntimeError,match='Boundary node selection failed'):
        write_deck(tmp_path/'run.inp',nodes,elements,support,material,166.67)


def test_mesh_import_rejects_surface_only(tmp_path):
    mesh=tmp_path/'bad.inp';mesh.write_text('*Node\n1,0,0,0\n*Element, type=S6\n1,1,1,1,1,1,1\n')
    with pytest.raises(RuntimeError,match='C3D10'):parse_gmsh_inp(mesh)


def test_read_actual_solver_style_displacement_table(tmp_path):
    dat=tmp_path/'job.dat'
    dat.write_text('''displacements (vx,vy,vz) for set ROLLER_NODES and time 1.0000000E+00

 10  0.0000E+00  0.0000E+00 -2.2000E-02
 11  0.0000E+00  0.0000E+00 -3.1000E-02
''')
    out=extract_vertical_displacements(dat,{10,11})
    assert out['max_abs_vertical_displacement_mm']==pytest.approx(.031)
    with pytest.raises(RuntimeError,match='incomplete'):
        extract_vertical_displacements(dat,{10,11,12})


def test_directional_material_requires_positive_definite_compliance():
    material=json.loads((ROOT/'examples/printed_material_ASSUMED.json').read_text())
    lines=elastic_material_lines(material)
    assert lines[0]=='*ELASTIC, TYPE=ENGINEERING CONSTANTS'
    assert len(lines[1].split(','))==8 and float(lines[2])==320
    material['nu_12']=8
    with pytest.raises(ValueError,match='positive definite'):
        elastic_material_lines(material)
