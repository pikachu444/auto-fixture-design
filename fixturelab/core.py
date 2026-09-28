from copy import deepcopy
import math
import re

SPEC_FIELDS={
 'bending': {'width','thickness','length','elastic_modulus','strength','target_strain','span_ratio'},
 'tensile': {'width','thickness','length','strength','grip_gap','target_strain','engagement'},
 'compression': {'width','length','height','stress_at_target','target_strain'},
 'folding': {'width','thickness','inner_radius','allowable_strain'},
}
EQUIPMENT={'frame_capacity','load_cell_capacity','tool_capacity','usable_travel','jaw_width','platen_width','platen_length'}
DESIGN={'load_factor','clearance','brim','edge_margin'}
def positive(value,name,zero=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or (value<0 if zero else value<=0):
        raise ValueError(f'{name}: finite {"nonnegative" if zero else "positive"} number required')

def validate(data):
    d=deepcopy(data)
    required={'id','title','type','units','specimen','equipment','printer','design'}
    if set(d)!=required: raise ValueError('Input keys must be exactly '+', '.join(sorted(required)))
    if not isinstance(d['id'],str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,59}',d['id']): raise ValueError('Invalid case id')
    if not isinstance(d['title'],str) or not 1<=len(d['title'])<=160: raise ValueError('Invalid title')
    if d['type'] not in SPEC_FIELDS: raise ValueError('Unsupported fixture type')
    if d['units']!='mm_N_MPa': raise ValueError('Only explicit mm_N_MPa units accepted')
    if set(d['specimen'])!=SPEC_FIELDS[d['type']]: raise ValueError('Unexpected or missing specimen fields')
    if set(d['equipment'])!=EQUIPMENT: raise ValueError('Unexpected or missing equipment fields')
    if set(d['printer'])!={'build'} or len(d['printer']['build'])!=3: raise ValueError('Printer needs 3 build dimensions')
    if set(d['design'])!=DESIGN: raise ValueError('Unexpected or missing design fields')
    for k,v in d['specimen'].items(): positive(v,k)
    for k,v in d['equipment'].items():
        if v is not None: positive(v,k)
    for v in d['printer']['build']: positive(v,'printer.build')
    for k,v in d['design'].items(): positive(v,k,zero=k in {'brim','edge_margin'})
    if d['design']['load_factor']<1: raise ValueError('Load factor must be >= 1')
    if d['design']['clearance']>2: raise ValueError('Clearance exceeds supported 2 mm template limit')
    if any(v>2000 for k,v in d['specimen'].items() if k in {'width','thickness','length','height','inner_radius','grip_gap','engagement'}): raise ValueError('Dimension exceeds CAD resource limit 2000 mm')
    if d['specimen'].get('target_strain',.1)>=1: raise ValueError('Target strain must be < 1 for these templates')
    return d

def evaluate(data):
    d=validate(data);s=d['specimen'];e=d['equipment'];q=d['design'];t=d['type']
    r={'input':d,'metrics':{},'checks':[],'production_release':'UNKNOWN','decision':'REVIEW_REQUIRED',
       'limitations':['Example equipment configuration is not a verified installed system.','No material/print qualification, FEA, fatigue or physical testing.','No standard-compliance certification.'], 'cad_generated':False}
    def check(code,ok,observed,limit,reason):
        r['checks'].append({'code':code,'status':'UNKNOWN' if ok is None else ('PASS' if ok else 'FAIL'),'observed':observed,'limit':limit,'reason':reason})
    m=r['metrics']; F=None; travel=None; prints=[]
    if t=='bending':
        b,h,L=s['width'],s['thickness'],s['thickness']*s['span_ratio']
        m.update(span_mm=L,force_target_N=2*b*h*h*s['elastic_modulus']*s['target_strain']/(3*L),nominal_strength_load_N=2*b*h*h*s['strength']/(3*L),deflection_mm=s['target_strain']*L*L/(6*h))
        F=m['nominal_strength_load_N']*q['load_factor'];travel=m['deflection_mm']
        # Fixed section templates; do not expose unimplemented section parameters.
        candidates=[n for n in (160,220) if L<=n-60]
        base=next((n for n in candidates if n+2*(q['brim']+q['edge_margin'])<=d['printer']['build'][0]),None)
        check('span_template',bool(candidates) and L>=40,L,[40,160],'32 mm support footprint, 14 mm outer land; choose 160/220 mm base')
        if candidates:
            check('base_printer_fit',base is not None,[n+2*(q['brim']+q['edge_margin']) for n in candidates],d['printer']['build'][0],'Candidate base lengths with brim and margin must fit printer X')
        check('specimen_overhang',s['length']>=L+16,s['length'],L+16,'At least 8 mm overhang at each support; template rule')
        check('roller_contact_width',b<=16,b,16,'24 mm roller with 4 mm edge margin each side')
        check('small_strain_model',s['target_strain']<=.01,s['target_strain'],.01,'Linear beam approximation scope')
        m['base_length_mm']=base
        if base: prints=[('base',[base,80,12]),('support_left',[32,40,26]),('support_right',[32,40,26])]
        r['limitations']+=['Printed supports/base are load-bearing concepts with no verified load rating.','Machine adapter, nuts/washers and roller axial retention remain to be designed.']
        r['use']='Load-bearing hybrid fixture concept; do not load until mechanically qualified.'
    elif t=='tensile':
        F=s['strength']*s['width']*s['thickness']*q['load_factor'];travel=s['grip_gap']*s['target_strain']
        m.update(area_mm2=s['width']*s['thickness'],elongation_estimate_mm=travel,tray_length_mm=s['length']+12,channel_width_mm=s['width']+2*q['clearance'])
        check('grip_engagement',s['length']>=s['grip_gap']+2*s['engagement'],s['length'],s['grip_gap']+2*s['engagement'],'Specimen must engage both jaws')
        check('jaw_width',None if e['jaw_width'] is None else s['width']<=e['jaw_width'],s['width'],e['jaw_width'],'Installed jaw width must be measured')
        check('film_template',s['thickness']<=1,s['thickness'],1,'Tray is for thin flexible strips')
        prints=[('alignment_tray',[s['length']+12,s['width']+2*q['clearance']+12,4])]
        r['use']='Bench alignment/insertion aid; transfer specimen to metal grips and remove aid before testing.'
        r['limitations']+=['No OEM grip interface; tray is a bench preparation aid.','Grip slip/crushing and transfer alignment require physical checks.','Travel estimate assumes uniform engineering strain over free grip gap; use measured elongation for nonuniform tests.']
    elif t=='compression':
        F=s['width']*s['length']*s['stress_at_target']*q['load_factor'];travel=s['height']*s['target_strain']
        m.update(area_mm2=s['width']*s['length'],compression_mm=travel,final_height_mm=s['height']-travel)
        for dimension in ['width','length']:
            cap=e['platen_'+dimension]
            check('platen_'+dimension,None if cap is None else s[dimension]+10<=cap,s[dimension]+10,cap,'5 mm positioning allowance each side')
        check('locator_height',s['height']>6,s['height'],6,'Removable 6 mm high corner locators')
        # Two diagonal L blocks; slide outwards before loading. No under-specimen base.
        prints=[('locator_A',[s['width']/2+6+q['clearance'],s['length']/2+6+q['clearance'],6]),('locator_B',[s['width']/2+6+q['clearance'],s['length']/2+6+q['clearance'],6])]
        r['use']='Two removable corner locators on a metal platen; slide out both locators before compression.'
        r['limitations']+=['The user-supplied stress must correspond to target strain; no foam constitutive prediction.','Platens are envelope models, not OEM attachment models.','Leaving locators during loading can constrain lateral expansion and invalidate the test.']
    else:
        radius=s['inner_radius'];h=s['thickness'];strain=h/(2*radius+h)
        m.update(outer_fiber_strain=strain,minimum_inner_radius_mm=h*(1/s['allowable_strain']-1)/2,neutral_axis_radius_mm=radius+h/2)
        check('strain_limit',strain<=s['allowable_strain'],strain,s['allowable_strain'],'Homogeneous centered neutral axis, pure bending estimate; not laminate or fatigue model')
        check('thin_strip',h/radius<=.1,h/radius,.1,'Thin-strip geometric approximation scope')
        prints=[('radius_former',[2*radius+12,s['width']+12,radius+5])]
        r['use']='Static bend-radius former for screening and fit checks; not a cyclic folding machine.'
        r['limitations']+=['Laminates with slip or asymmetric layers require laminate/contact analysis.','Cycle count, actuator kinematics, force and fatigue life are not calculated.']
    if F is not None:
        m['design_load_N']=F
        for key in ['frame_capacity','load_cell_capacity','tool_capacity']:
            check(key,None if e[key] is None else F<=e[key],F,e[key],'Check each load-path component, not frame rating alone')
        check('usable_travel',None if e['usable_travel'] is None else travel<=e['usable_travel'],travel,e['usable_travel'],'Usable travel after tooling installation, not catalog crosshead travel')
    for name,bounds in prints:
        pad=2*(q['brim']+q['edge_margin']);occ=[bounds[0]+pad,bounds[1]+pad,bounds[2]]
        check('print_envelope_'+name,all(a<=b for a,b in zip(occ,d['printer']['build'])),occ,d['printer']['build'],'Single part, fixed orientation, brim and edge margin included')
    check('physical_qualification',None,None,None,'Equipment interfaces, printed material and actual setup require physical qualification')
    if any(c['status']=='FAIL' for c in r['checks']):r['decision']='REJECTED'
    return r
