"""Independent arithmetic checks for the planning document, not a product test suite."""
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'scenario_inputs.json').read_text(encoding='utf-8'))
cases={s['id']:{k:q['value'] for k,q in s['values'].items()} for s in data['scenarios']}
margin=data['load_margin_factor']['value']
checks=[]

def check(name, actual, expected, unit):
    ok=math.isclose(actual,expected,rel_tol=1e-8,abs_tol=1e-8)
    checks.append(dict(name=name,value=actual,expected=expected,unit=unit,status='PASS' if ok else 'FAIL'))

s=cases['T1'];area=s['width']*s['thickness']
check('T1_force_lower',area*s['strength_lower'],1200,'N')
check('T1_force_upper',area*s['strength_upper'],2000,'N')
check('T1_design_force',area*s['strength_upper']*margin,2500,'N')
s=cases['T2']
check('T2_extension',s['free_length']*s['target_engineering_strain'],500,'mm')
check('T2_available_before',1450-s['accessory_stack_before']-s['free_length']-s['clearance'],450,'mm')
check('T2_available_after',1450-s['accessory_stack_after']-s['free_length']-s['clearance'],600,'mm')
check('T2_force_upper',s['width']*s['thickness']*s['strength_upper'],120,'N')
s=cases['T3'];check('T3_force',s['width']*s['thickness']*s['strength_upper'],40,'N')
s=cases['C1'];check('C1_force',s['width']*s['depth']*s['nominal_stress_upper'],500,'N')
check('C1_displacement',s['height']*s['target_strain'],12.5,'mm')
s=cases['C2'];area=s['width']*s['depth'];force=area*s['E']*s['target_strain']
disp=s['height']*s['target_strain'];df=force/s['fixture_stiffness']
check('C2_force',force,6000,'N');check('C2_specimen_displacement',disp,0.2,'mm')
check('C2_fixture_displacement',df,0.3,'mm')
check('C2_apparent_E',(force/area)/((disp+df)/s['height']),1200,'MPa')
check('C2_required_fixture_K',force/(s['allowed_displacement_ratio']*disp),600000,'N/mm')
s=cases['C3'];check('C3_force',s['width']*s['depth']*s['target_nominal_stress'],16000,'N')
for sid,ef,ed,es in [('B1',16.666666666666668,0.8533333333333334,133.33333333333334),('B2',33.333333333333336,1.7066666666666668,266.6666666666667)]:
    s=cases[sid];b=s['width'];h=s['thickness'];L=s.get('span',s.get('span_ratio',0)*h)
    delta=s['elastic_surface_strain']*L**2/(6*h)
    f=4*s['E']*b*h**3*delta/L**3
    fs=2*b*h**2*s['nominal_flexural_strength']/(3*L)
    check(sid+'_elastic_force',f,ef,'N');check(sid+'_displacement',delta,ed,'mm');check(sid+'_strength_force',fs,es,'N')
s=cases['F1'];rn=s['inner_radius']+s['thickness']/2
check('F1_surface_strain',s['thickness']/(2*rn),0.047619047619047616,'1')
check('F1_alternative_strain',s['thickness']/(2*(s['alternative_inner_radius']+s['thickness']/2)),0.019607843137254905,'1')
s=cases['F2'];stroke=s['pinion_pitch_radius']*math.radians(s['relative_fold_angle_max'])/2;amplitude=stroke/2
vmax=2*math.pi*s['frequency']*amplitude;amax=(2*math.pi*s['frequency'])**2*amplitude/1000
check('F2_stroke',stroke,18.84955592153876,'mm')
check('F2_vmax',vmax,118.4352528130723,'mm/s')
check('F2_amax',amax,1.4883012806543912,'m/s2')
check('F2_linear_inertia',s['linear_moving_mass']*amax,0.7441506403271956,'N')
check('F2_hours',s['cycles']/s['frequency']/3600,20.833333333333332,'h')
s=cases['F3'];error=max(s['signal_force']*s['reading_fraction'],s['sensor_capacity_magnitude']*s['capacity_fraction'])
check('F3_absolute_error',error,0.1,'N');check('F3_relative_error',error/s['signal_force'],0.05,'1')
s=cases['H1'];check('H1_width_excess',s['fixture_width']-s['chamber_width'],10,'mm')

report={'scope':'planning_arithmetic_only','not_verified':['product_software','FreeCAD_regeneration','collision_detection','structural_analysis','real_machine_suitability'],
        'check_count':len(checks),'pass_count':sum(c['status']=='PASS' for c in checks),'checks':checks}
(ROOT/'planning_calculation_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ['scope','check_count','pass_count']},ensure_ascii=False))
if report['pass_count']!=report['check_count']:
    raise SystemExit(1)
