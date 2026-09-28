"""Small-strain rectangular three-point bending; demonstration, not certification."""
import math
import cadquery as cq

def mechanics(s, factor=1.25):
    keys = ('width','thickness','length','elastic_modulus','flexural_strength','target_strain','span_ratio')
    if any(not isinstance(s[k], (int,float)) or isinstance(s[k],bool) or not math.isfinite(s[k]) or s[k] <= 0 for k in keys):
        raise ValueError('All specimen inputs must be positive finite numbers')
    if factor < 1 or not math.isfinite(factor):
        raise ValueError('Design load factor must be finite and >= 1')
    b,h,E = s['width'],s['thickness'],s['elastic_modulus']
    L = h*s['span_ratio']
    if s['length'] < L+16:
        raise ValueError('Specimen must overhang each support by at least 8 mm in this template')
    if s['target_strain'] > 0.01:
        raise ValueError('Target strain exceeds this demo small-strain envelope')
    force = 2*b*h*h*E*s['target_strain']/(3*L)
    strength_load = 2*b*h*h*s['flexural_strength']/(3*L)
    return dict(span_mm=L, force_at_target_N=force, deflection_at_target_mm=s['target_strain']*L*L/(6*h), nominal_strength_load_N=strength_load, design_load_N=factor*strength_load)

def print_fit(bounds, printer):
    # Single-part, fixed flat orientation. Not a full plate-packing or slicing check.
    pad=2*(printer['brim']+printer['edge_margin'])
    occupied=[bounds[0]+pad,bounds[1]+pad,bounds[2]]
    return {'occupied_mm':occupied,'fits':all(a<=b for a,b in zip(occupied,printer['build']))}

def choose_base(span, design, printer):
    # Preserve 32 mm support footprint + 14 mm outer material at maximum setting.
    lengths=[design['original_base_length'],design['new_base_length']]
    for length in lengths:
        max_span=length-design['support_length']-2*design['end_land']
        if span<=max_span and print_fit([length,design['base_width'],design['base_thickness']],printer)['fits']:
            return length,max_span
    raise ValueError('No fixture template meets both span and printer envelope')

def box(x,y,z,at=(0,0,0)):
    return cq.Workplane('XY').box(x,y,z,centered=(True,True,False)).translate(at).val()

def cylinder_y(radius,length,center):
    return cq.Solid.makeCylinder(radius,length,cq.Vector(center[0],center[1]-length/2,center[2]),cq.Vector(0,1,0))

def assembly(s, base_length, max_span):
    span=mechanics(s)['span_mm']
    if span<40: raise ValueError('Span below 40 mm template minimum')
    if span>max_span: raise ValueError('Span exceeds fixture travel')
    if s['width']>16: raise ValueError('Specimen exceeds roller contact-width envelope')
    # Original fixture has center adjustment 20..50 mm; extended one 20..80 mm.
    lo,hi=20,max_span/2
    base=cq.Workplane('XY').box(base_length,80,12,centered=(True,True,False))
    for sign in [-1,1]:
        for y in [-12,12]:
            # Allow mounting hole offset +/-10 from each support center.
            length=hi-lo+20+5.5
            cutter=cq.Workplane('XY').center(sign*(hi+lo)/2,y).slot2D(length,5.5).extrude(12)
            base=base.cut(cutter)
    parts=[dict(name='printed_base',kind='printed',shape=base.val(),color='#386f9e')]
    for sign,label in [(-1,'left'),(1,'right')]:
        x=sign*span/2
        support=box(32,40,26,(x,0,12)).cut(cylinder_y(4.15,42,(x,0,38)))
        for dx in [-10,10]:
            for y in [-12,12]:
                support=support.cut(cq.Solid.makeCylinder(2.75,26,cq.Vector(x+dx,y,12)))
                support=support.cut(cq.Solid.makeCylinder(4.25,10,cq.Vector(x+dx,y,28)))
                bolt=cq.Solid.makeCylinder(2.5,26,cq.Vector(x+dx,y,2)).fuse(cq.Solid.makeCylinder(4,4,cq.Vector(x+dx,y,28)))
                parts.append(dict(name=f'metal_bolt_{label}_{dx}_{y}',kind='metal',shape=bolt,color='#9aa6af'))
        parts.append(dict(name=f'printed_support_{label}',kind='printed',shape=support,color='#39a99e'))
        # Gravity-seated in the 4.15 mm radius cradle: center drops by 0.15 mm.
        parts.append(dict(name=f'metal_roller_{label}',kind='metal',shape=cylinder_y(4,24,(x,0,37.85)),color='#acb7c2'))
    parts.append(dict(name='specimen',kind='specimen',shape=box(s['length'],s['width'],s['thickness'],(0,0,41.85)),color='#eaaa47'))
    parts.append(dict(name='metal_loading_nose',kind='metal',shape=cylinder_y(4,24,(0,0,45.85+s['thickness'])),color='#c9d0d7'))
    return parts
