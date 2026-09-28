from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
import cadquery as cq
import trimesh
from legacy.src.fixture import assembly as bend_assembly, box, cylinder_y

COLORS={'printed':'#368ea1','metal':'#a9b4bf','specimen':'#e8aa47'}
def part(name,kind,shape):return dict(name=name,kind=kind,shape=shape,color=COLORS[kind])
def corner(x,y,z,dx,dy,dz):return box(dx,dy,dz,(x+dx/2,y+dy/2,z))

def build(result):
    if result['decision']=='REJECTED':return []
    d=result['input'];s=d['specimen'];c=d['design']['clearance'];t=d['type']
    if t=='bending':
        mapped={**s,'flexural_strength':s['strength']};mapped.pop('strength')
        base=result['metrics']['base_length_mm']
        return bend_assembly(mapped,base,base-60)
    if t=='tensile':
        length=s['length']+12;channel=s['width']+2*c;width=channel+12
        tray=box(length,width,2)
        for sign in [-1,1]:tray=tray.fuse(box(length,6,2,(0,sign*(channel/2+3),2)))
        # Thin transverse end stop, outside specimen. Open opposite end for removal.
        tray=tray.fuse(box(3,channel,2,(-s['length']/2-1.5,0,2)))
        return [part('alignment_tray','printed',tray),part('film_specimen','specimen',box(s['length'],s['width'],s['thickness'],(0,0,2)))]
    if t=='compression':
        w,l,h=s['width'],s['length'],s['height'];a=w/2+c+6;b=l/2+c+6
        loc=corner(-a,-b,10,6,b,6).fuse(corner(-a,-b,10,a,6,6)).clean()
        e=d['equipment'];pw=e['platen_width'] or w+20;pl=e['platen_length'] or l+20
        return [part('lower_platen','metal',box(pw,pl,10)),part('locator_A','printed',loc),part('locator_B','printed',loc.rotate((0,0,0),(0,0,1),180)),part('foam_specimen','specimen',box(w,l,h,(0,0,10))),part('upper_platen','metal',box(pw,pl,10,(0,0,10+h)))]
    r=s['inner_radius'];w=s['width'];h=s['thickness']
    half=cylinder_y(r,w+12,(0,0,5)).intersect(box(2*r,w+12,r,(0,0,5)))
    former=box(2*r+12,w+12,5).fuse(half).clean()
    outer=cylinder_y(r+h,w,(0,0,5));inner=cylinder_y(r,w+2,(0,0,5))
    strip=outer.cut(inner).intersect(box(2*(r+h),w,r+h,(0,0,5)))
    return [part('radius_former','printed',former),part('bent_strip_reference','specimen',strip)]

def mesh_of(shape):
    verts,faces=shape.tessellate(.08,.15)
    return trimesh.Trimesh(vertices=[v.toTuple() for v in verts],faces=faces,process=True)

def export_and_check(parts,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);checks=[];bom=[]
    def test(code,ok,detail):
        checks.append({'code':code,'status':'PASS' if bool(ok) else 'FAIL','detail':detail})
    assy=cq.Assembly(name=folder.name)
    for p in parts:
        shape=p['shape'];bb=shape.BoundingBox();bounds=[bb.xlen,bb.ylen,bb.zlen]
        test('BREP_'+p['name'],shape.isValid() and shape.Volume()>0,{'solids':len(shape.Solids()),'volume_mm3':shape.Volume(),'bounds_mm':bounds})
        assy.add(shape,name=p['name'],color=cq.Color(p['color']))
        bom.append({'part':p['name'],'role':p['kind'],'quantity':1,'bounds_mm':bounds,'volume_mm3':shape.Volume(),'print_file':p['name']+'.stl' if p['kind']=='printed' else None})
        if p['kind']!='printed':continue
        centered=shape.translate(cq.Vector(-(bb.xmin+bb.xmax)/2,-(bb.ymin+bb.ymax)/2,-bb.zmin))
        cq.exporters.export(centered,str(folder/(p['name']+'.stl')),tolerance=.05,angularTolerance=.1)
        cq.exporters.export(centered,str(folder/(p['name']+'.3mf')),exportType='3MF',tolerance=.05,angularTolerance=.1)
        loaded=trimesh.load_mesh(folder/(p['name']+'.stl'))
        test('STL_'+p['name'],loaded.is_watertight and loaded.is_winding_consistent and loaded.volume>0 and np.allclose(loaded.extents,bounds,atol=.02) and abs(loaded.volume/shape.Volume()-1)<.01,{'watertight':bool(loaded.is_watertight),'dimensions_mm':loaded.extents.tolist(),'relative_volume_error':abs(loaded.volume/shape.Volume()-1)})
        with zipfile.ZipFile(folder/(p['name']+'.3mf')) as archive:
            model=ET.fromstring(archive.read('3D/3dmodel.model'));ns={'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
            vertices=model.findall('.//m:vertex',ns);faces=model.findall('.//m:triangle',ns)
            vv=np.array([[float(v.attrib[k]) for k in ('x','y','z')] for v in vertices])
            ff=np.array([[int(f.attrib[k]) for k in ('v1','v2','v3')] for f in faces])
            mesh=trimesh.Trimesh(vertices=vv,faces=ff,process=True)
            test('3MF_'+p['name'],model.attrib.get('unit')=='millimeter' and mesh.is_watertight and mesh.is_winding_consistent and np.allclose(mesh.extents,bounds,atol=.02) and abs(mesh.volume/shape.Volume()-1)<.01,{'unit':model.attrib.get('unit'),'watertight':bool(mesh.is_watertight),'dimensions_mm':mesh.extents.tolist(),'relative_volume_error':abs(mesh.volume/shape.Volume()-1)})
    assy.export(str(folder/'assembly.step'))
    reloaded=cq.importers.importStep(str(folder/'assembly.step')).val();vol=sum(p['shape'].Volume() for p in parts)
    test('STEP_roundtrip',len(reloaded.Solids())==sum(len(p['shape'].Solids()) for p in parts) and abs(reloaded.Volume()/vol-1)<1e-6,{'solids':len(reloaded.Solids()),'relative_volume_error':abs(reloaded.Volume()/vol-1)})
    overlaps=[]
    for i,p in enumerate(parts):
        for q in parts[i+1:]:
            v=p['shape'].intersect(q['shape']).Volume()
            if v>1e-5:overlaps.append({'a':p['name'],'b':q['name'],'overlap_mm3':v})
    test('initial_position_interference',not overlaps,overlaps)
    return checks,bom
