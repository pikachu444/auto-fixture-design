import numpy as np
import matplotlib
matplotlib.use("Agg")
from PIL import Image
from .cad import mesh_of

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


def preview(parts,path):
    Image.fromarray(rasterize(parts)).save(path)
