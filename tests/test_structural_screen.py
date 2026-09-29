import json
from pathlib import Path

import pytest

from fixturelab.cad import build
from fixturelab.core import evaluate
from scripts.run_structural_screen import parse_gmsh_inp,write_deck

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
