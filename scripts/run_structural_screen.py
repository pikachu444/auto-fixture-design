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


def write_deck(path,nodes,elements,support,material,force_N):
    E=material['elastic_modulus_MPa'];nu=material['poisson_ratio']
    if not (0<E<1e7 and 0<=nu<.49 and math.isfinite(E) and math.isfinite(nu)):
        raise ValueError('Invalid finite isotropic demonstration material')
    if not material.get('provenance') or not material.get('qualification'):
        raise ValueError('Material provenance and qualification status are required')
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
    lines += ['*MATERIAL, NAME=PRINT_ASSUMED','*ELASTIC',f'{E}, {nu}',
              '*SOLID SECTION, ELSET=SUPPORT, MATERIAL=PRINT_ASSUMED',
              '*STEP','*STATIC','*BOUNDARY','BASE_FIXED, 1, 3',
              '*CLOAD']
    lines += [f'{n}, 3, {-force_N/len(loaded):.12g}' for n in loaded]
    lines += ['*NODE PRINT, NSET=ROLLER_NODES','U',
              '*NODE FILE, NSET=ROLLER_NODES','U',
              '*EL FILE','S','*END STEP']
    path.write_text('\n'.join(lines)+'\n')
    return {'fixed_node_count':len(fixed),'loaded_node_count':len(loaded),
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


def run(data,material,out,sizes):
    if data['type']!='bending':raise ValueError('Only printed bending supports are modeled')
    result=evaluate(data)
    if result['decision']=='REJECTED':raise ValueError('Rejected design cannot be simulated')
    for program in ('gmsh','ccx'):
        if not shutil.which(program):raise RuntimeError(f'Missing open-source executable: {program}')
    support=next(p['shape'] for p in build(result) if p['name']=='printed_support_left')
    out.mkdir(parents=True,exist_ok=True)
    step=out/'printed_support_left.step'
    cq.exporters.export(support,str(step))
    studies=[]
    F=result['metrics']['design_load_N']/2
    for idx,size in enumerate(sizes):
        job=f'support_{idx}'
        folder=out/job;folder.mkdir()
        mesh=folder/'gmsh.inp'
        gmsh=subprocess.run(['gmsh',str(step.resolve()),'-3','-order','2','-format','inp','-o',str(mesh.resolve()),
                             '-clmin',str(size/2),'-clmax',str(size),'-optimize','-optimize_ho','-nopopup','-v','2'],
                            cwd=folder,text=True,capture_output=True,timeout=180)
        (folder/'gmsh.log').write_text(gmsh.stdout+'\n'+gmsh.stderr)
        if gmsh.returncode or not mesh.is_file():raise RuntimeError(f'Gmsh failed: {folder/"gmsh.log"}')
        nodes,elements=parse_gmsh_inp(mesh)
        deck=folder/(job+'.inp')
        bc=write_deck(deck,nodes,elements,support,material,F)
        ccx=subprocess.run(['ccx',job],cwd=folder,text=True,capture_output=True,timeout=300)
        (folder/'ccx.log').write_text(ccx.stdout+'\n'+ccx.stderr)
        if ccx.returncode or not (folder/(job+'.frd')).is_file():
            raise RuntimeError(f'CalculiX failed: {folder/"ccx.log"}; tail: {ccx.stdout[-900:]} {ccx.stderr[-300:]}')
        disp=extract_vertical_displacements(folder/(job+'.dat'),
                                            {int(n) for n in re.findall(r'^([0-9]+), 3,',deck.read_text(),re.M)})
        studies.append({'mesh_size_max_mm':size,'nodes':len(nodes),'elements_C3D10':len(elements),
                        'boundary':bc,'displacement':disp,
                        'files':{'mesh':str(mesh.relative_to(out)),
                                 'deck':str(deck.relative_to(out)),
                                 'field_results':f'{job}/{job}.frd'}})
    coarse,fine=studies
    delta=abs(coarse['displacement']['max_abs_vertical_displacement_mm']-
              fine['displacement']['max_abs_vertical_displacement_mm'])
    rel=delta/fine['displacement']['max_abs_vertical_displacement_mm']
    output={'case_id':data['id'],'status':'PRELIMINARY_ONLY_NOT_QUALIFIED',
            'model':'STEP -> Gmsh C3D10 -> CalculiX; single printed support',
            'material':material,'total_design_load_N':2*F,'force_per_support_N':F,
            'mesh_studies':studies,'displacement_mesh_change_ratio':rel,
            'limitations':['Fixed support bottom replaces actual bolts and base.',
                           'Roller contact replaced by distributed nodal force on cradle.',
                           'Linear isotropic material is a hypothetical example, not measured printed orthotropy.',
                           'No strength allowables, stress convergence or physical print verification.',
                           'No production approval from this simulation.']}
    (out/'result.json').write_text(json.dumps(output,ensure_ascii=False,indent=2))
    return output


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True);p.add_argument('--material',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    r=run(json.loads(args.input.read_text()),json.loads(args.material.read_text()),args.output,[4.0,3.0])
    print(json.dumps({'status':r['status'],'case_id':r['case_id'],
                      'meshes':[(v['elements_C3D10'],v['displacement']) for v in r['mesh_studies']],
                      'displacement_mesh_change_ratio':r['displacement_mesh_change_ratio']}))


if __name__=='__main__':main()
