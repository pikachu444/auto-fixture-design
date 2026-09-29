"""Gmsh/CalculiX preliminary 3D FE of the actual printed bending support CAD.

Run in CI, where the open-source gmsh and calculix-ccx packages are installed.
This does not model the base, bolts, nonlinear roller contact, or printed infill.
"""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

import cadquery as cq
import numpy as np

from fixturelab.cad import build
from fixturelab.core import evaluate
from fixturelab.handcheck import bending_and_support


def parse_gmsh_inp(path):
    """Read Gmsh's Abaqus output; Gmsh handles C3D10 node ordering."""
    nodes={};elements={};section=None;etype=None
    for raw in path.read_text().splitlines():
        line=raw.strip()
        if not line or line.startswith('**'):continue
        if line.startswith('*'):
            header=line.upper();section=None
            if header.startswith('*NODE'):section='node'
            elif header.startswith('*ELEMENT'):
                match=re.search(r'TYPE\s*=\s*([A-Z0-9]+)',header)
                etype=match.group(1) if match else None
                if etype=='C3D10':section='element'
            continue
        if section=='node':
            data=[x.strip() for x in line.split(',') if x.strip()]
            if len(data)>=4:nodes[int(data[0])]=tuple(float(x) for x in data[1:4])
        elif section=='element':
            data=[x.strip() for x in line.split(',') if x.strip()]
            if len(data)==11:elements[int(data[0])]=tuple(map(int,data[1:]))
    if not nodes or not elements:raise RuntimeError('Gmsh must output 10-node tetrahedra (C3D10)')
    return nodes,elements


def quadratic_tet_jacobian_quality(nodes,elements):
    """Check all C3D10 Jacobians at the four standard Gauss points."""
    tags=np.fromiter(elements,dtype=int)
    coords=np.array([[nodes[n] for n in ids] for ids in elements.values()])
    dL=np.array([[-1,-1,-1],[1,0,0],[0,1,0],[0,0,1]],dtype=float)
    minimum=np.full(len(tags),np.inf)
    for corner in range(4):
        L=np.full(4,.1381966011250105);L[corner]=.5854101966249685
        deriv=np.empty((10,3))
        for a in range(4):deriv[a]=(4*L[a]-1)*dL[a]
        for k,(a,b) in enumerate(((0,1),(1,2),(2,0),(0,3),(1,3),(2,3)),4):
            deriv[k]=4*(L[a]*dL[b]+L[b]*dL[a])
        jac=np.einsum('nic,ir->ncr',coords,deriv)
        minimum=np.minimum(minimum,np.linalg.det(jac))
    bad=tags[minimum<=1e-10]
    if len(bad):raise RuntimeError(f'Nonpositive curved C3D10 Jacobians: {len(bad)}; first element IDs {bad[:10].tolist()}')
    return float(minimum.min())


def elastic_material_lines(material):
    if not material.get('provenance') or not material.get('qualification'):
        raise ValueError('Material provenance and qualification status are required')
    if material.get('model')=='orthotropic':
        keys=('E_1_MPa','E_2_MPa','E_3_MPa','nu_12','nu_13','nu_23',
              'G_12_MPa','G_13_MPa','G_23_MPa')
        values=[material[k] for k in keys]
        if not material.get('axes'):raise ValueError('Orthotropic CAD/print axes must be identified')
        if not all(isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x) for x in values):
            raise ValueError('Finite material constants required')
        E1,E2,E3,n12,n13,n23,G12,G13,G23=values
        if min(E1,E2,E3,G12,G13,G23)<=0:raise ValueError('All orthotropic moduli must be positive')
        compliance=np.array([[1/E1,-n12/E1,-n13/E1],
                             [-n12/E1,1/E2,-n23/E2],
                             [-n13/E1,-n23/E2,1/E3]])
        if np.linalg.eigvalsh(compliance)[0]<=0:raise ValueError('Orthotropic compliance is not positive definite')
        return ['*ELASTIC, TYPE=ENGINEERING CONSTANTS',
                ', '.join(map(str,values[:8])),str(G23)]
    if material.get('model')=='isotropic':
        E=material['elastic_modulus_MPa'];nu=material['poisson_ratio']
        if not (isinstance(E,(float,int)) and isinstance(nu,(float,int)) and
                not isinstance(E,bool) and not isinstance(nu,bool) and
                math.isfinite(E) and math.isfinite(nu) and 0<E<1e7 and 0<=nu<.49):
            raise ValueError('Invalid finite isotropic material')
        return ['*ELASTIC',f'{E}, {nu}']
    raise ValueError('Material model must be isotropic or orthotropic')


def write_deck(path,nodes,elements,support,material,force_N):
    material_deck=elastic_material_lines(material)
    bb=support.BoundingBox();cx=(bb.xmin+bb.xmax)/2
    fixed=sorted(n for n,(x,y,z) in nodes.items() if abs(z-bb.zmin)<1e-4)
    # Nodes on the concave, cylindrical roller saddle, over central 24 mm.
    # Nodal equal-force distribution approximates bearing pressure; the
    # explicit set is retained for audit of the boundary condition.
    loaded=sorted(n for n,(x,y,z) in nodes.items()
                  if abs(y)<=12.001 and z>bb.zmax-4.5
                  and abs(math.hypot(x-cx,z-bb.zmax)-4.15)<.15)
    if len(fixed)<15 or len(loaded)<10:raise RuntimeError(f'Boundary node selection failed: fixed={len(fixed)}, contact={len(loaded)}')
    if set(fixed)&set(loaded):raise RuntimeError('Load and fixed sets overlap')
    # Check first four C3D10 corner nodes form nondegenerate tetrahedra.
    vols=[]
    for elem in elements.values():
        p=np.array([nodes[n] for n in elem[:4]])
        vols.append(abs(np.linalg.det((p[1:]-p[0]).T))/6)
    approximate=sum(vols)
    cad=support.Volume()
    if min(vols)<1e-9 or abs(approximate/cad-1)>.08:
        raise RuntimeError(f'Mesh volume differs from CAD: {approximate} vs {cad} mm3')
    lines=['*HEADING','Bending support: preliminary fixed-base linear elastic screen',
           '*NODE']
    lines += [f'{i}, {x:.10g}, {y:.10g}, {z:.10g}' for i,(x,y,z) in nodes.items()]
    lines += ['*ELEMENT, TYPE=C3D10, ELSET=SUPPORT']
    lines += [f'{i}, '+', '.join(map(str,ns)) for i,ns in elements.items()]
    lines += ['*NSET, NSET=BASE_FIXED']
    lines += [', '.join(map(str,fixed[i:i+12])) for i in range(0,len(fixed),12)]
    lines += ['*NSET, NSET=ROLLER_NODES']
    lines += [', '.join(map(str,loaded[i:i+12])) for i in range(0,len(loaded),12)]
    lines += ['*MATERIAL, NAME=PRINT_INPUT',*material_deck,
              '*SOLID SECTION, ELSET=SUPPORT, MATERIAL=PRINT_INPUT',
              '*STEP','*STATIC','*BOUNDARY','BASE_FIXED, 1, 3',
              '*CLOAD']
    lines += [f'{n}, 3, {-force_N/len(loaded):.12g}' for n in loaded]
    lines += ['*NODE PRINT, NSET=ROLLER_NODES','U',
              '*NODE FILE, NSET=ROLLER_NODES','U',
              '*EL FILE','S','*END STEP']
    path.write_text('\n'.join(lines)+'\n')
    return {'fixed_node_count':len(fixed),'loaded_node_count':len(loaded),
            'loaded_node_ids':loaded,
            'mesh_corner_volume_mm3':approximate,'cad_volume_mm3':cad,
            'mesh_volume_relative_error':abs(approximate/cad-1),
            'total_applied_force_N':force_N,'per_node_force_N':-force_N/len(loaded)}


def extract_vertical_displacements(dat,loaded):
    """Read the NODE PRINT displacement table and require every load node."""
    text=dat.read_text(errors='replace')
    if 'displacements (vx,vy,vz)' not in text.lower():
        raise RuntimeError('CalculiX displacement table not found')
    block=text.lower().split('displacements (vx,vy,vz)')[-1]
    records={}
    for line in block.splitlines():
        fields=line.strip().split()
        if len(fields)!=4:continue
        try:
            i=int(fields[0]);u=[float(x.replace('D','E')) for x in fields[1:]]
        except ValueError:continue
        if i in loaded:records[i]=u
    if set(records)!=set(loaded):raise RuntimeError(f'Displacement result incomplete: {len(records)}/{len(loaded)}')
    return {'max_abs_vertical_displacement_mm':max(abs(u[2]) for u in records.values()),
            'min_vertical_displacement_mm':min(u[2] for u in records.values())}


def extract_stress_diagnostic(frd,nodes):
    """Read averaged nodal stress in ASCII FRD; diagnostic, not failure stress."""
    text=frd.read_text(errors='replace')
    if ' -4  STRESS' not in text:raise RuntimeError('CalculiX stress field not found')
    block=text.rsplit(' -4  STRESS',1)[1].split('\n -3',1)[0]
    records={}
    for line in block.splitlines():
        if not line.startswith(' -1'):continue
        try:label=int(line[3:13])
        except ValueError:continue
        values=re.findall(r'[-+]?\d+\.\d+E[-+]\d+',line[13:])
        if len(values)!=6:raise RuntimeError(f'Malformed six-component stress at node {label}')
        sxx,syy,szz,sxy,syz,szx=map(float,values)
        vm=math.sqrt(((sxx-syy)**2+(syy-szz)**2+(szz-sxx)**2)/2+
                     3*(sxy*sxy+syz*syz+szx*szx))
        records[label]=vm
    if set(records)!=set(nodes):raise RuntimeError(f'Stress field incomplete: {len(records)}/{len(nodes)}')
    peak=max(records,key=records.get)
    return {'max_averaged_nodal_von_mises_MPa':records[peak],
            'p95_averaged_nodal_von_mises_MPa':float(np.percentile(list(records.values()),95)),
            'maximum_node_id':peak,'maximum_node_xyz_mm':nodes[peak],
            'node_count':len(records)}


def run(data,material,out,sizes):
    if data['type']!='bending':raise ValueError('Only printed bending supports are modeled')
    result=evaluate(data)
    if result['decision']=='REJECTED':raise ValueError('Rejected design cannot be simulated')
    for program in ('gmsh','ccx'):
        if not shutil.which(program):raise RuntimeError(f'Missing open-source executable: {program}')
    support=next(p['shape'] for p in build(result) if p['name']=='printed_support_left')
    hand=bending_and_support(data,material,support)
    if abs(hand['design_total_load_N']/result['metrics']['design_load_N']-1)>1e-10:
        raise RuntimeError('Independent bending-load hand check disagrees with design calculation')
    out.mkdir(parents=True,exist_ok=True)
    step=out/'printed_support_left.step'
    cq.exporters.export(support,str(step))
    studies=[]
    F=result['metrics']['design_load_N']/2
    for idx,size in enumerate(sizes):
        job=f'support_{idx}'
        folder=out/job;folder.mkdir()
        mesh=folder/'gmsh.inp'
        # Linear interpolation of second-order midside nodes keeps all tetrahedra
        # valid near the small bore/counterbore intersection. The triangulated
        # boundary approximates STEP curvature; refinement assesses that error.
        gmsh=subprocess.run(['gmsh',str(step.resolve()),'-3','-order','2','-format','inp','-o',str(mesh.resolve()),
                             '-clmin',str(size/2),'-clmax',str(size),'-setnumber','Mesh.SecondOrderLinear','1',
                             '-nopopup','-v','2'],
                            cwd=folder,text=True,capture_output=True,timeout=180)
        (folder/'gmsh.log').write_text(gmsh.stdout+'\n'+gmsh.stderr)
        if gmsh.returncode or not mesh.is_file():raise RuntimeError(f'Gmsh failed: {folder/"gmsh.log"}')
        nodes,elements=parse_gmsh_inp(mesh)
        min_jacobian=quadratic_tet_jacobian_quality(nodes,elements)
        deck=folder/(job+'.inp')
        bc=write_deck(deck,nodes,elements,support,material,F)
        ccx=subprocess.run(['ccx',job],cwd=folder,text=True,capture_output=True,timeout=300)
        (folder/'ccx.log').write_text(ccx.stdout+'\n'+ccx.stderr)
        if ccx.returncode or not (folder/(job+'.frd')).is_file():
            raise RuntimeError(f'CalculiX failed: {folder/"ccx.log"}; tail: {ccx.stdout[-900:]} {ccx.stderr[-300:]}')
        disp=extract_vertical_displacements(folder/(job+'.dat'),set(bc['loaded_node_ids']))
        stress=extract_stress_diagnostic(folder/(job+'.frd'),nodes)
        studies.append({'mesh_size_max_mm':size,'nodes':len(nodes),'elements_C3D10':len(elements),
                        'minimum_quadratic_jacobian_mm3':min_jacobian,
                        'boundary':bc,'displacement':disp,'stress_diagnostic':stress,
                        'files':{'mesh':str(mesh.relative_to(out)),
                                 'deck':str(deck.relative_to(out)),
                                 'field_results':f'{job}/{job}.frd'}})
    coarse,fine=studies[-2:]
    delta=abs(coarse['displacement']['max_abs_vertical_displacement_mm']-
              fine['displacement']['max_abs_vertical_displacement_mm'])
    rel=delta/fine['displacement']['max_abs_vertical_displacement_mm']
    output={'case_id':data['id'],'status':'PRELIMINARY_ONLY_NOT_QUALIFIED',
            'model':'STEP -> Gmsh C3D10 -> CalculiX; single printed support',
            'material':material,'total_design_load_N':2*F,'force_per_support_N':F,
            'analytical_scale_check':hand,
            'mesh_studies':studies,'displacement_mesh_change_ratio_last_two':rel,
            'fea_to_idealized_axial_displacement_ratio':
                fine['displacement']['max_abs_vertical_displacement_mm']/hand['ideal_uniform_axial_shortening_mm'],
            'limitations':['Fixed support bottom replaces actual bolts and base.',
                           'Roller contact replaced by distributed nodal force on cradle.',
                           'Example directional print properties are hypothetical, not measured coupon data.',
                           'No strength allowables, stress convergence or physical print verification.',
                           'No production approval from this simulation.']}
    (out/'result.json').write_text(json.dumps(output,ensure_ascii=False,indent=2))
    return output


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True);p.add_argument('--material',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    r=run(json.loads(args.input.read_text()),json.loads(args.material.read_text()),args.output,[4.0,3.0,2.0])
    print(json.dumps({'status':r['status'],'case_id':r['case_id'],
                      'meshes':[(v['elements_C3D10'],v['displacement']) for v in r['mesh_studies']],
                      'displacement_mesh_change_ratio_last_two':r['displacement_mesh_change_ratio_last_two']}))


if __name__=='__main__':main()
