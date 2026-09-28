"""Run from any cwd: python run_demo.py. Outputs are overwritten reproducibly."""
from pathlib import Path
import argparse, json, sys, zipfile, xml.etree.ElementTree as ET
import numpy as np
import cadquery as cq
import trimesh
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from src.fixture import mechanics, choose_base, print_fit, assembly

ROOT=Path(__file__).resolve().parent

def mesh_of(shape):
    vertices,faces=shape.tessellate(0.08,0.15)
    return trimesh.Trimesh(vertices=[v.toTuple() for v in vertices],faces=faces,process=True)

def rasterize(parts, width=1100, height=560):
    # Orthographic depth-buffer rendering of actual CAD triangles.
    # Per-pixel depth avoids painter-order artifacts where components overlap.
    yaw,pitch=-.65,.55
    R=np.array([[np.cos(yaw),-np.sin(yaw),0],
                [np.sin(yaw)*np.sin(pitch),np.cos(yaw)*np.sin(pitch),-np.cos(pitch)],
                [np.sin(yaw)*np.cos(pitch),np.cos(yaw)*np.cos(pitch),np.sin(pitch)]])
    rgb=np.full((height,width,3),[245,247,250],dtype=np.uint8)
    depth=np.full((height,width),-np.inf)
    scale=width/290
    light=np.array([-.4,-.5,1]); light=light/np.linalg.norm(light)
    for part in parts:
        mesh=mesh_of(part['shape']); v=(mesh.vertices-[0,0,22])@R.T
        v[:,0]=v[:,0]*scale+width/2; v[:,1]=v[:,1]*scale+height/2
        color=np.array(matplotlib.colors.to_rgb(part['color']))*255
        for f,normal in zip(mesh.faces,mesh.face_normals):
            t=v[f]; xmin=max(0,int(np.floor(t[:,0].min()))); xmax=min(width-1,int(np.ceil(t[:,0].max())))
            ymin=max(0,int(np.floor(t[:,1].min()))); ymax=min(height-1,int(np.ceil(t[:,1].max())))
            if xmin>xmax or ymin>ymax: continue
            (x0,y0,z0),(x1,y1,z1),(x2,y2,z2)=t
            den=(y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
            if abs(den)<1e-9: continue
            yy,xx=np.mgrid[ymin:ymax+1,xmin:xmax+1];xx=xx+.5;yy=yy+.5
            a=((y1-y2)*(xx-x2)+(x2-x1)*(yy-y2))/den
            b=((y2-y0)*(xx-x2)+(x0-x2)*(yy-y2))/den
            c=1-a-b;z=a*z0+b*z1+c*z2
            buf=depth[ymin:ymax+1,xmin:xmax+1]
            mask=(a>=-1e-8)&(b>=-1e-8)&(c>=-1e-8)&(z>buf)
            buf[mask]=z[mask]
            shade=.60+.40*max(0,float(normal@light))
            rgb[ymin:ymax+1,xmin:xmax+1][mask]=np.clip(color*shade,0,255).astype(np.uint8)
    return rgb

def render(stages,path):
    fig,axes=plt.subplots(1,2,figsize=(15,5.6),facecolor='#f5f7fa')
    for ax,(label,parts,span) in zip(axes,stages):
        ax.imshow(rasterize(parts));ax.set_axis_off()
        ax.set_title(label,fontsize=14,fontweight='bold',pad=14)
        ax.text(.02,-.10,f'Support span: {span:.0f} mm | units: mm',transform=ax.transAxes,fontsize=11)
    fig.suptitle('PARAMETRIC FIXTURE / EXECUTED CAD DEMO',fontsize=19,fontweight='bold',y=.96)
    fig.text(.5,.115,'Blue/teal: printed concepts | silver: metal | gold: specimen',ha='center',fontsize=11)
    fig.text(.5,.055,'Geometry and envelope checks only. Strength, mounting and slicing remain unverified.',ha='center',fontsize=11,color='#9b5226')
    fig.subplots_adjust(top=.79,bottom=.21,left=.02,right=.98,wspace=.03)
    fig.savefig(path,dpi=160);plt.close(fig)

def viewer(stages,path):
    data=[]
    for title,parts,span in stages:
        data.append(dict(title=title,span=span,parts=[dict(name=p['name'],kind=p['kind'],color=p['color'],v=mesh_of(p['shape']).vertices.round(4).tolist(),f=mesh_of(p['shape']).faces.tolist()) for p in parts]))
    template=(ROOT/'viewer_template.html').read_text()
    path.write_text(template.replace('__CAD_DATA__',json.dumps(data,separators=(',',':'))))

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--input',type=Path,default=ROOT/'inputs/bending.json'); args=parser.parse_args()
    config=json.loads(args.input.read_text()); out=ROOT/'outputs'; out.mkdir(exist_ok=True)
    report={'scope':'Executed three-point bending CAD prototype only','production_release':'UNKNOWN',
      'not_verified':['printed material strength/anisotropy/creep','assembly stiffness/contact/fastener and roller retention','load cell calibration and usable range','machine interface and mounting adapter','slicer/G-code/physical print and load test','standards compliance'],
      'checks':[], 'scenarios':{},'artifacts':[]}
    checks=report['checks']
    def check(name,passed,detail): checks.append(dict(name=name,status='PASS' if passed else 'FAIL',detail=detail))
    stages=[]
    for key in ['initial','modified']:
        s=config[key]; m=mechanics(s,config['design']['design_load_factor']); length,maxspan=choose_base(m['span_mm'],config['design'],config['printer'])
        parts=assembly(s,length,maxspan); stage=out/key; stage.mkdir(exist_ok=True)
        report['scenarios'][key]={**m,'base_length_mm':length,'max_span_mm':maxspan,'specimen_input':s,'printer_fit':print_fit([length,80,12],config['printer'])}
        check(f'{key}: reference frame capacity only',m['design_load_N']<=config['equipment']['frame_capacity_N'],{'design_load_N':m['design_load_N'],'frame_capacity_N':config['equipment']['frame_capacity_N'],'system_approval':'UNKNOWN: load cell, tooling and mounting not verified'})
        assy=cq.Assembly(name=key)
        for p in parts:
            assy.add(p['shape'],name=p['name'],color=cq.Color(p['color']))
        assy.export(str(stage/'assembly.step'))
        imported=cq.importers.importStep(str(stage/'assembly.step')).val()
        check(f'{key}: STEP roundtrip solid count',len(imported.Solids())==len(parts),f'{len(imported.Solids())} solids')
        vol=sum(p['shape'].Volume() for p in parts)
        check(f'{key}: STEP volume preserved',abs(imported.Volume()-vol)/vol<1e-6,{'relative_error':abs(imported.Volume()-vol)/vol})
        for p in parts:
            check(f'{key}/{p["name"]}: valid BREP',p['shape'].isValid() and p['shape'].Volume()>0,'OpenCascade validity and positive volume')
            if p['kind']!='printed': continue
            shape=p['shape']; bb=shape.BoundingBox()
            # Export printable parts in local coordinates with bottom at Z=0.
            centered=shape.translate(cq.Vector(-(bb.xmin+bb.xmax)/2,-(bb.ymin+bb.ymax)/2,-bb.zmin))
            stl=stage/(p['name']+'.stl'); mf=stage/(p['name']+'.3mf')
            cq.exporters.export(centered,str(stl),tolerance=.05,angularTolerance=.1)
            cq.exporters.export(centered,str(mf),exportType='3MF',tolerance=.05,angularTolerance=.1)
            loaded=trimesh.load_mesh(stl)
            check(f'{key}/{p["name"]}: STL watertight',loaded.is_watertight and loaded.is_winding_consistent and loaded.volume>0,{'triangles':len(loaded.faces),'watertight':bool(loaded.is_watertight)})
            check(f'{key}/{p["name"]}: STL dimensions',np.allclose(loaded.extents,[bb.xlen,bb.ylen,bb.zlen],atol=.02),'Tolerance 0.02 mm')
            check(f'{key}/{p["name"]}: STL volume',abs(loaded.volume-shape.Volume())/shape.Volume()<.01,'Mesh volume within 1% of BREP')
            with zipfile.ZipFile(mf) as z:
                model=ET.fromstring(z.read('3D/3dmodel.model'))
                ns={'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
                verts=model.findall('.//m:vertex',ns); faces=model.findall('.//m:triangle',ns)
                check(f'{key}/{p["name"]}: 3MF mm and mesh',model.attrib.get('unit')=='millimeter' and len(verts)>0 and len(faces)>0,{'vertices':len(verts),'triangles':len(faces),'note':'geometry 3MF, no printer profile'})
            fit=print_fit([bb.xlen,bb.ylen,bb.zlen],config['printer'])
            check(f'{key}/{p["name"]}: single-part print envelope',fit['fits'],fit)
        # Measured roller centers from generated CAD, not only requested parameters.
        roller=[p['shape'].Center().x for p in parts if 'metal_roller' in p['name']]
        check(f'{key}: measured roller spacing',abs(abs(roller[1]-roller[0])-m['span_mm'])<1e-6,abs(roller[1]-roller[0]))
        # Solids should only touch; no unintended overlapping volume.
        collisions=[]
        for i,p in enumerate(parts):
            for q in parts[i+1:]:
                v=p['shape'].intersect(q['shape']).Volume()
                if v>1e-5: collisions.append([p['name'],q['name'],v])
        check(f'{key}: initial-position interference',not collisions,collisions)
        stages.append((f'{key.upper()} | h = {s["thickness"]} | base = {length}',parts,m['span_mm']))
    required=report['scenarios']['modified']['span_mm']; old=config['design']['original_max_span']
    check('Reject unchanged fixture for modified specimen',required>old,{'required_span_mm':required,'existing_max_mm':old,'decision':'REJECT'})
    too_large=print_fit([244,80,12],config['printer'])
    check('Reject oversize 244 mm base with brim',not too_large['fits'],too_large)
    report['check_summary']={s:sum(c['status']==s for c in checks) for s in ['PASS','FAIL']}
    render(stages,out/'cad_comparison.png'); viewer(stages,out/'cad_viewer.html')
    (out/'results.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    print(json.dumps({'checks':report['check_summary'],'production_release':report['production_release'],'outputs':str(out)},indent=2))
    return int(report['check_summary']['FAIL']>0)

if __name__=='__main__': sys.exit(main())
