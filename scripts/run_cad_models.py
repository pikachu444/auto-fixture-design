"""Execute two distinct CAD sources and parameter changes in CI."""
import argparse
import json
from pathlib import Path

from fixturelab.model_cad import execute


def run(output):
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    variants=[('roller_default','roller_support',{}),
              ('roller_wider','roller_support',{'support_width_mm':38}),
              ('film_wider','film_tray',{'specimen_width_mm':20}),
              ('roller_invalid','roller_support',{'bolt_pitch_x_mm':30})]
    results={name:execute(model,values,root/name) for name,model,values in variants}
    a,b=results['roller_default'],results['roller_wider']
    if not (a['cad_generated'] and b['cad_generated'] and
            a['bom'][0]['bounds_mm'][0]==32 and b['bom'][0]['bounds_mm'][0]==38 and
            results['film_wider']['bom'][0]['bounds_mm'][1]==32.5 and
            results['roller_invalid']['decision']=='REJECTED' and not results['roller_invalid']['cad_generated']):
        raise RuntimeError('Model-defined parameterization regression failed')
    summary={'status':'PASS','variants':{k:{'model':v['model'],'decision':v['decision'],
               'parameters':v['parameters'],'bounds_mm':v['bom'][0]['bounds_mm'] if v['bom'] else None,
               'cad_checks_passed':sum(c['status']=='PASS' for c in v['cad_checks'])}
               for k,v in results.items()},
             'meaning':'CAD source owns numeric parameters and relations; separate STEP exports contain no editable parameter history.'}
    (root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('artifacts/models'))
    run(parser.parse_args().output)
