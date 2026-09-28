import argparse,json,sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description='Generate actual fixture CAD and evidence reports')
    sub=p.add_subparsers(dest='command',required=True)
    gen=sub.add_parser('generate');gen.add_argument('--input',type=Path,required=True);gen.add_argument('--output',type=Path,default=Path('artifacts/custom'))
    suite=sub.add_parser('suite');suite.add_argument('--output',type=Path,default=Path('artifacts/suite'))
    serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=8765)
    args=p.parse_args()
    if args.command=='serve':
        from .server import serve
        serve(args.port);return
    from .pipeline import execute,run_suite
    if args.command=='suite':return run_suite(args.output)
    result=execute(json.loads(args.input.read_text()),args.output)
    print(json.dumps({'decision':result['decision'],'report':str(args.output/'report.html')},ensure_ascii=False))
    return 2 if result['decision']=='REJECTED' else 0
if __name__=='__main__':sys.exit(main())
