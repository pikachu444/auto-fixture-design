"""Independent, deliberately simple scale checks beside the FE solver."""
import math


def specimen_scale_check(data):
    """Separate arithmetic for each specimen idealization (N, mm, MPa)."""
    s=data['specimen'];q=data['design'];kind=data['type']
    if kind=='bending':
        span=s['thickness']*s['span_ratio']
        section_modulus=s['width']*s['thickness']**2/6
        # M=F L/4 and sigma=M/Z for a centered three-point bending load.
        strength_load=4*s['strength']*section_modulus/span
        target_load=4*s['elastic_modulus']*s['target_strain']*section_modulus/span
        travel=s['target_strain']*span**2/(6*s['thickness'])
        values={'span_mm':span,'nominal_strength_load_N':strength_load,
                'force_target_N':target_load,'design_load_N':strength_load*q['load_factor'],
                'deflection_mm':travel}
        premise='Simply supported linear beam, centered point load, rectangular section.'
    elif kind=='tensile':
        area=s['width']*s['thickness']
        values={'area_mm2':area,'design_load_N':s['strength']*area*q['load_factor'],
                'elongation_estimate_mm':s['target_strain']*s['grip_gap']}
        premise='Uniform engineering stress and strain over the free grip gap.'
    elif kind=='compression':
        area=s['width']*s['length'];shortening=s['target_strain']*s['height']
        values={'area_mm2':area,'design_load_N':s['stress_at_target']*area*q['load_factor'],
                'compression_mm':shortening,'final_height_mm':s['height']-shortening}
        premise='User-supplied stress at target strain, uniform nominal platen area.'
    elif kind=='folding':
        radius=s['inner_radius'];t=s['thickness'];allow=s['allowable_strain']
        values={'outer_fiber_strain':(t/2)/(radius+t/2),
                'minimum_inner_radius_mm':(t/2)*(1/allow-1),
                'neutral_axis_radius_mm':radius+t/2}
        premise='Centered neutral axis and pure static bending; no cyclic life prediction.'
    else:raise ValueError(f'Unsupported specimen type {kind}')
    if not all(math.isfinite(v) for v in values.values()):
        raise ValueError('Non-finite specimen hand check')
    return {'values':values,'premise':premise,
            'interpretation':'Separate arithmetic cross-check of the same idealized equations, not independent physical validation.'}


def compare_specimen_scale_check(data,metrics):
    check=specimen_scale_check(data)
    for name,hand in check['values'].items():
        computed=metrics[name]
        if not math.isclose(hand,computed,rel_tol=1e-10,abs_tol=1e-10):
            raise RuntimeError(f'Specimen hand check mismatch: {name}: {hand} vs {computed}')
    return {'status':'MATCH','checked_metrics':list(check['values']),**check}


def bending_and_support(data,material,support):
    specimen=data['specimen'];design=data['design']
    b=specimen['width'];h=specimen['thickness'];L=h*specimen['span_ratio']
    strength=specimen['strength'];E_specimen=specimen['elastic_modulus']
    eps=specimen['target_strain']
    nominal_strength_load=2*b*h*h*strength/(3*L)
    design_load=nominal_strength_load*design['load_factor']
    target_load=2*b*h*h*E_specimen*eps/(3*L)
    bb=support.BoundingBox()
    gross_area=bb.xlen*bb.ylen
    P=design_load/2
    E_z=material['E_3_MPa'] if material['model']=='orthotropic' else material['elastic_modulus_MPa']
    if not all(math.isfinite(x) and x>0 for x in (gross_area,P,E_z,bb.zlen)):
        raise ValueError('Invalid analytical support dimensions or stiffness')
    return {'span_mm':L,'target_specimen_load_N':target_load,
            'nominal_strength_specimen_load_N':nominal_strength_load,
            'design_total_load_N':design_load,'load_per_support_N':P,
            'gross_support_area_mm2':gross_area,
            'nominal_gross_compressive_stress_MPa':P/gross_area,
            'ideal_uniform_axial_shortening_mm':P*bb.zlen/(E_z*gross_area),
            'formulae':['F_strength = 2 b h² sigma_strength / (3 L)',
                        'P_support = load_factor F_strength / 2',
                        'sigma_gross = P_support / (support_width support_depth)',
                        'delta_ideal = P_support support_height / (E_z gross_area)'],
            'interpretation':'Scale check only. Gross axial bar neglects cradle, holes, nonuniform bearing and base/bolt flexibility; not a safety bound or fixture strength.'}
