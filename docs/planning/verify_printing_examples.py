"""Printing-plan arithmetic checks only. Does not run CAD, a slicer, or a printer."""
import json,math
from pathlib import Path
R=Path(__file__).resolve().parent
ss=json.loads((R/'printing_scenarios.json').read_text())['scenarios']
d={x['id']:{k:v['value'] for k,v in x['values'].items()} for x in ss}
checks=[]
def ck(n,a,e,u):
 checks.append({'name':n,'value':a,'expected':e,'unit':u,'status':'PASS' if math.isclose(a,e,rel_tol=1e-10,abs_tol=1e-10) else 'FAIL'})
s=d['P1'];pad=2*(s['brim_each']+s['margin_each'])
ck('P1_required_x',s['part_x']+pad,262,'mm')
ck('P1_candidate_required_x',s['candidate_x']+pad,238,'mm')
ck('P1_candidate_required_y',s['candidate_y']+pad,138,'mm')
s=d['P2'];ck('P2_xy_utilization',s['assumed_stress']/s['allowable_xy'],0.6,'1')
ck('P2_z_utilization',s['assumed_stress']/s['allowable_z'],1.5,'1')
s=d['P3'];pmin=s['pin']-s['pin_tol'];pmax=s['pin']+s['pin_tol']
ck('P3_min_before',s['bore']-s['bore_tol']-pmax,0.14,'mm')
ck('P3_max_before',s['bore']+s['bore_tol']-pmin,0.36,'mm')
ck('P3_min_after',s['bore_after']-s['bore_after_tol']-pmax,0.14,'mm')
ck('P3_max_after',s['bore_after']+s['bore_after_tol']-pmin,0.26,'mm')
s=d['P4'];mass=s['part_mass']+s['support_mass']+s['waste_mass'];material=mass/1000*s['filament_price']
energy=s['average_power']*s['print_hours']*s['energy_price'];labor=s['labor_hours']*s['labor_rate']
ck('P4_mass',mass,160,'g');ck('P4_material_cost',material,4800,'KRW');ck('P4_energy_cost',energy,120,'KRW')
ck('P4_total_direct_cost',material+energy+labor+s['metal_parts'],23420,'KRW')
report={'scope':'planning_arithmetic_only','not_verified':['cad_generation','slicing','mesh_quality','structural_strength','physical_printing','actual_cost'],
        'check_count':len(checks),'pass_count':sum(x['status']=='PASS' for x in checks),'checks':checks}
(R/'printing_calculation_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['scope','check_count','pass_count']}))
if report['pass_count']!=report['check_count']:raise SystemExit(1)
