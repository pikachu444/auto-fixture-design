"""Loopback-only local application. CAD runs in a bounded subprocess."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import io,json,mimetypes,re,subprocess,sys,threading,uuid,zipfile
from urllib.parse import unquote,urlparse
from .core import validate
ROOT=Path(__file__).resolve().parents[1]
BUSY=threading.Lock()

class Handler(BaseHTTPRequestHandler):
    def send(self,status,body,kind='application/json; charset=utf-8'):
        if isinstance(body,str):body=body.encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def do_GET(self):
        path=unquote(urlparse(self.path).path)
        if path=='/':return self.send(200,(ROOT/'fixturelab/ui.html').read_bytes(),'text/html; charset=utf-8')
        if path=='/api/examples':
            manifest=json.loads((ROOT/'examples/suite.json').read_text())
            examples=[json.loads((ROOT/'examples'/item['file']).read_text()) for item in manifest]
            return self.send(200,json.dumps(examples,ensure_ascii=False))
        if path=='/api/models':
            from .model_cad import catalogue
            return self.send(200,json.dumps(catalogue(),ensure_ascii=False))
        match=re.fullmatch(r'/jobs/([a-f0-9]{32})/([A-Za-z0-9_.-]+)',path)
        if not match:return self.send(404,'{"error":"not found"}')
        folder=ROOT/'artifacts/web'/match[1];file=folder/match[2]
        if match[2]=='bundle.zip' and (folder/'result.json').exists():
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
                for p in sorted(folder.iterdir()):
                    if p.is_file():z.write(p,p.name)
            return self.send(200,stream.getvalue(),'application/zip')
        if not file.is_file():return self.send(404,'{"error":"not found"}')
        return self.send(200,file.read_bytes(),mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
    def do_POST(self):
        if self.path not in ('/api/generate','/api/model/generate'):
            return self.send(404,'{"error":"not found"}')
        # No CORS; reject cross-origin browser requests to local compute endpoint.
        origin=self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:return self.send(403,'{"error":"origin denied"}')
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n<=0 or n>65536:raise ValueError('Request size must be 1..65536 bytes')
            payload=json.loads(self.rfile.read(n))
            if self.path=='/api/generate':data=validate(payload)
            else:
                from .model_cad import definition
                if set(payload)!={'model','parameters'} or not isinstance(payload['parameters'],dict):
                    raise ValueError('CAD request needs model and parameter mapping')
                definition(payload['model'])
                data=payload
        except (ValueError,TypeError,KeyError,OverflowError) as exc:return self.send(400,json.dumps({'error':str(exc)}))
        if not BUSY.acquire(blocking=False):return self.send(429,'{"error":"CAD generation already running"}')
        try:
            job=uuid.uuid4().hex;request_dir=ROOT/'artifacts/requests';request_dir.mkdir(parents=True,exist_ok=True)
            inp=request_dir/(job+'.json');inp.write_text(json.dumps(data),encoding='utf-8');output=ROOT/'artifacts/web'/job
            command=([sys.executable,'-m','fixturelab','generate','--input',str(inp),'--output',str(output)]
                     if self.path=='/api/generate' else
                     [sys.executable,'-m','fixturelab','model','--model',data['model'],
                      '--parameters',str(inp),'--output',str(output)])
            if self.path=='/api/model/generate':
                inp.write_text(json.dumps(data['parameters']),encoding='utf-8')
            completed=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=180)
            if completed.returncode not in (0,2):return self.send(500,json.dumps({'error':'CAD computation failed','detail':completed.stderr[-4000:]}))
            result=json.loads((output/'result.json').read_text())
            return self.send(200,json.dumps({'job':job,'decision':result['decision'],'report':f'/jobs/{job}/report.html','download':f'/jobs/{job}/bundle.zip','metrics':result.get('metrics',{})}))
        except subprocess.TimeoutExpired:return self.send(504,'{"error":"CAD generation exceeded 180 seconds"}')
        finally:BUSY.release()

def serve(port=8765):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'Open http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
