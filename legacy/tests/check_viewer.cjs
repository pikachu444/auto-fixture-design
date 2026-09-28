// Dependency-free smoke check; does not substitute for browser rendering QA.
const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'outputs/cad_viewer.html'),'utf8');
const js=html.match(/<script>([\s\S]*?)<\/script>/)[1];
let fills=0;
const ctx={scale(){},clearRect(){},beginPath(){},moveTo(){},lineTo(){},closePath(){},fill(){fills++},stroke(){}};
const nodes={};for(const id of ['cad','stage','hide','metrics','iso','front','top'])nodes[id]={value:'1',checked:false};
Object.assign(nodes.cad,{getContext:()=>ctx,getBoundingClientRect:()=>({width:1000,height:600}),addEventListener(){},setPointerCapture(){}});
const context=vm.createContext({document:{getElementById:id=>nodes[id]},devicePixelRatio:1,addEventListener(){},Math});
vm.runInContext(js,context);assert(fills>0);assert(nodes.metrics.textContent.includes('128'));
nodes.stage.value='0';nodes.stage.onchange();assert(nodes.metrics.textContent.includes('64'));
nodes.front.onclick();nodes.top.onclick();nodes.iso.onclick();
nodes.hide.checked=true;nodes.hide.onchange();
nodes.cad.onpointerdown({clientX:0,clientY:0,pointerId:1});nodes.cad.onpointermove({clientX:15,clientY:10});nodes.cad.onpointerup();
const report={status:'PASS',scope:'Node VM with mocked Canvas; no actual browser rendering',checks:['embedded JavaScript executes','mesh draws triangles','stage switch updates measured span','camera controls execute','visibility toggle executes','drag rotation executes'],triangle_draw_calls:fills};
fs.writeFileSync(path.join(root,'outputs/viewer_smoke.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
