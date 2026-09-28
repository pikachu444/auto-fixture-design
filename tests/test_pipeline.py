import json
import pytest
from fixturelab.pipeline import execute
from test_engineering import data

def test_rejected_case_emits_report_without_cad(tmp_path):
    r=execute(data('film_travel_reject'),tmp_path)
    assert r['decision']=='REJECTED'
    assert (tmp_path/'report.html').is_file()
    assert not list(tmp_path.glob('*.stl'))
    assert not list(tmp_path.glob('*.step'))

def test_existing_output_rejected_not_mixed(tmp_path):
    (tmp_path/'old.stl').write_text('prior run')
    with pytest.raises(ValueError,match='empty'):execute(data(),tmp_path)

def test_html_injection_escaped(tmp_path):
    d=data('film_travel_reject');d['title']='<script>alert(1)</script>'
    execute(d,tmp_path)
    assert '<script>alert(1)</script>' not in (tmp_path/'report.html').read_text()

def test_real_cad_roundtrip(tmp_path):
    r=execute(data('film_alignment'),tmp_path)
    assert r['cad_generated']
    assert all(c['status']=='PASS' for c in r['cad_checks'])
    assert {'alignment_tray.stl','alignment_tray.3mf','assembly.step'}<={p.name for p in tmp_path.iterdir()}
    assert r['bom'][0]['bounds_mm']==pytest.approx([162,27.5,4])
