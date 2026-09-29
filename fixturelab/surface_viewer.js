/* Interactive view of tessellated faces from the final FreeCAD BREP.
 * Color-buffer picking identifies a face; it does not invent a CAD dimension.
 */
window.createFaceViewer=function(canvas,onSelect){
  const gl=canvas.getContext('webgl',{antialias:true});
  if(!gl)throw Error('이 브라우저에서 WebGL을 사용할 수 없습니다');
  const vertex=`attribute vec3 position; attribute vec3 normal;
    uniform vec3 center; uniform float extent,aspect,yaw,pitch;
    varying vec3 lighting;
    void main(){vec3 p=position-center;
      vec3 r=vec3(cos(yaw)*p.x-sin(yaw)*p.y,sin(yaw)*p.x+cos(yaw)*p.y,p.z);
      vec3 q=vec3(r.x,cos(pitch)*r.y-sin(pitch)*r.z,sin(pitch)*r.y+cos(pitch)*r.z);
      vec3 n=normal;
      lighting=n;
      gl_Position=vec4(q.x/extent,q.y*aspect/extent,-q.z/extent,1.0);
    }`;
  const fragment=`precision mediump float; uniform vec3 color; uniform float picking;
    varying vec3 lighting;
    void main(){float shade=0.66+0.34*abs(dot(normalize(lighting),normalize(vec3(-0.4,-0.5,1.0))));
      gl_FragColor=vec4(color*(picking>0.5?1.0:shade),1.0);
    }`;
  function shader(kind,source){const s=gl.createShader(kind);gl.shaderSource(s,source);gl.compileShader(s);
    if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s}
  const program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,vertex));
  gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fragment));gl.linkProgram(program);
  if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
  gl.useProgram(program);
  const attrPosition=gl.getAttribLocation(program,'position'),attrNormal=gl.getAttribLocation(program,'normal');
  const uniforms=Object.fromEntries(['center','extent','aspect','yaw','pitch','color','picking'].map(k=>[k,gl.getUniformLocation(program,k)]));
  const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
  gl.vertexAttribPointer(attrPosition,3,gl.FLOAT,false,24,0);gl.enableVertexAttribArray(attrPosition);
  gl.vertexAttribPointer(attrNormal,3,gl.FLOAT,false,24,12);gl.enableVertexAttribArray(attrNormal);
  gl.enable(gl.DEPTH_TEST);gl.disable(gl.DITHER);
  let data=null,segments=[],yaw=-0.65,pitch=0.55,zoom=1,selected=0;
  let frame=null,texture=null,depth=null;
  function resize(){const width=Math.max(1,Math.round(canvas.clientWidth*devicePixelRatio));
    const height=Math.max(1,Math.round(canvas.clientHeight*devicePixelRatio));
    if(canvas.width===width&&canvas.height===height)return;
    canvas.width=width;canvas.height=height;
    if(frame){gl.deleteFramebuffer(frame);gl.deleteTexture(texture);gl.deleteRenderbuffer(depth)}
    frame=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,frame);
    texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,width,height,0,gl.RGBA,gl.UNSIGNED_BYTE,null);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);
    gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,texture,0);
    depth=gl.createRenderbuffer();gl.bindRenderbuffer(gl.RENDERBUFFER,depth);
    gl.renderbufferStorage(gl.RENDERBUFFER,gl.DEPTH_COMPONENT16,width,height);
    gl.framebufferRenderbuffer(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.RENDERBUFFER,depth);
    if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw Error('3D picking buffer unavailable');
    gl.bindFramebuffer(gl.FRAMEBUFFER,null);
  }
  function render(picking=false){if(!data)return;resize();gl.bindFramebuffer(gl.FRAMEBUFFER,picking?frame:null);
    gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(picking?0:0.95,picking?0:0.97,picking?0:0.98,1);
    gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(program);gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
    const lo=data.bounds[0],hi=data.bounds[1];
    gl.uniform3f(uniforms.center,(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,(lo[2]+hi[2])/2);
    gl.uniform1f(uniforms.aspect,canvas.width/canvas.height);
    gl.uniform1f(uniforms.extent,Math.max(...lo.map((x,i)=>hi[i]-x))*Math.max(0.85,canvas.width/canvas.height*0.85)/zoom);
    gl.uniform1f(uniforms.yaw,yaw);gl.uniform1f(uniforms.pitch,pitch);
    gl.uniform1f(uniforms.picking,picking?1:0);
    for(const face of segments){const id=face.id;
      if(picking)gl.uniform3f(uniforms.color,(id&255)/255,((id>>8)&255)/255,((id>>16)&255)/255);
      else if(id===selected)gl.uniform3f(uniforms.color,0.98,0.48,0.14);
      else gl.uniform3f(uniforms.color,0.40+(id%4)*0.025,0.72,0.82);
      gl.drawArrays(gl.TRIANGLES,face.start,face.count);
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER,null);
  }
  function setData(value){data=value;selected=0;segments=[];yaw=-0.65;pitch=0.55;zoom=1;
    const vertices=[];
    for(const face of value.faces){const start=vertices.length/6;
      for(const t of face.triangles){const a=t.slice(0,3),b=t.slice(3,6),c=t.slice(6,9);
        const ab=b.map((x,i)=>x-a[i]),ac=c.map((x,i)=>x-a[i]);
        const n=[ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]];
        for(const p of [a,b,c])vertices.push(...p,...n);
      }
      segments.push({id:face.id,start,count:vertices.length/6-start});
    }
    gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(vertices),gl.STATIC_DRAW);
    render();
  }
  let start=null;
  canvas.addEventListener('pointerdown',e=>{start={x:e.clientX,y:e.clientY,dragged:false};canvas.setPointerCapture(e.pointerId)});
  canvas.addEventListener('pointermove',e=>{if(!start)return;
    const dx=e.clientX-start.x,dy=e.clientY-start.y;
    if(Math.abs(dx)+Math.abs(dy)>3)start.dragged=true;
    if(start.dragged){yaw+=dx*.008;pitch=Math.max(-1.5,Math.min(1.5,pitch+dy*.008));render()}
    start.x=e.clientX;start.y=e.clientY;
  });
  canvas.addEventListener('pointerup',e=>{if(!start)return;const dragged=start.dragged;start=null;
    if(dragged||!data)return;render(true);
    const bounds=canvas.getBoundingClientRect(),pixel=new Uint8Array(4);
    const x=Math.min(canvas.width-1,Math.max(0,Math.floor((e.clientX-bounds.left)*canvas.width/bounds.width)));
    const y=Math.min(canvas.height-1,Math.max(0,canvas.height-1-Math.floor((e.clientY-bounds.top)*canvas.height/bounds.height)));
    gl.bindFramebuffer(gl.FRAMEBUFFER,frame);gl.readPixels(x,y,1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel);gl.bindFramebuffer(gl.FRAMEBUFFER,null);
    selected=pixel[0]+(pixel[1]<<8)+(pixel[2]<<16);render(false);
    onSelect(data.faces.find(face=>face.id===selected)||null);
  });
  canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.6,Math.min(3,zoom*(e.deltaY<0?1.1:.9)));render()},{passive:false});
  if(typeof ResizeObserver!=='undefined')new ResizeObserver(()=>render()).observe(canvas);
  return {setData,render};
};
