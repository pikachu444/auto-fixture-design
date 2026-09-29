"""Runs under FreeCADCmd, not the application's ordinary Python interpreter.

The editable source is an FCStd feature tree. Parameter definitions are stored
inside that document, next to the selected feature properties/Sketcher datums.
"""
import json
import math
import os
from pathlib import Path
import re
import sys
import traceback

import FreeCAD as App
import Part


def _signature(shape):
    b=shape.BoundBox
    # Boolean results can be Part.Compound even when they hold exactly one
    # valid solid. FreeCAD exposes CenterOfMass on the enclosed Part.Solid.
    c=shape.Solids[0].CenterOfMass
    return (shape.Volume,shape.Area,b.XMin,b.XMax,b.YMin,b.YMax,b.ZMin,b.ZMax,
            c.x,c.y,c.z)


def _changes_shape(before,after):
    return any(abs(a-b)>max(1e-6,1e-7*max(abs(a),abs(b))) for a,b in zip(before,after))


def _config(doc):
    obj=doc.getObject('FixtureConfiguration')
    if obj is None:
        obj=doc.addObject('App::DocumentObjectGroup','FixtureConfiguration')
        obj.Label='Fixture parameter definitions'
        obj.addProperty('App::PropertyString','Definition','Fixture')
        obj.Definition=json.dumps({'parameters':[],'final':None})
    return obj


def _registry(doc):
    return json.loads(_config(doc).Definition)


def _save_registry(doc,registry):
    _config(doc).Definition=json.dumps(registry,ensure_ascii=False,sort_keys=True)


def _targets(doc):
    items=[]
    for obj in doc.Objects:
        for prop in obj.PropertiesList:
            kind=obj.getTypeIdOfProperty(prop)
            if kind not in ('App::PropertyLength','App::PropertyDistance'):
                continue
            value=getattr(obj,prop)
            items.append({'key':obj.Name+'|property|'+prop,'object':obj.Name,
                          'object_label':obj.Label,'dimension':prop,'kind':'property',
                          'value':float(value.Value),'unit':'mm'})
        if obj.TypeId=='Sketcher::SketchObject':
            for i,c in enumerate(obj.Constraints):
                if c.Type not in ('Distance','DistanceX','DistanceY','Radius','Diameter') or not obj.getDriving(i):
                    continue
                items.append({'key':obj.Name+'|constraint|'+str(i),'object':obj.Name,
                              'object_label':obj.Label,'dimension':c.Name or f'{c.Type} #{i+1}',
                              'kind':'constraint','value':float(c.Value),'unit':'mm'})
    return items


def _resolve(doc,target):
    matches=[x for x in _targets(doc) if x['key']==target]
    if len(matches)!=1:raise ValueError('Selected CAD feature dimension is missing or is not driving')
    return matches[0]


def _datum(doc,entry):
    obj=doc.getObject(entry['object'])
    if obj is None:raise ValueError('A registered CAD feature was deleted')
    if entry['kind']=='property':
        if obj.getTypeIdOfProperty(entry['property']) not in ('App::PropertyLength','App::PropertyDistance'):
            raise ValueError('The CAD property no longer has a length unit')
        return obj,entry['property']
    if 'constraint_index' in entry:
        index=entry['constraint_index']
        if obj.TypeId=='Sketcher::SketchObject' and 0<=index<len(obj.Constraints) and obj.getDriving(index):
            return obj,index
        raise ValueError('Selected sketch dimension is not driving')
    for i,c in enumerate(obj.Constraints):
        if c.Name==entry['constraint'] and obj.getDriving(i):return obj,i
    raise ValueError('The named driving sketch constraint was deleted')


def _assign(doc,entry,value):
    obj,key=_datum(doc,entry)
    if entry['kind']=='property':setattr(obj,key,App.Units.Quantity(f'{value} mm'))
    else:obj.setDatum(key,App.Units.Quantity(f'{value} mm'))


def _read(doc,entry):
    obj,key=_datum(doc,entry)
    return float(getattr(obj,key).Value) if entry['kind']=='property' else float(obj.Constraints[key].Value)


def _final(doc,registry):
    name=registry['final']
    obj=doc.getObject(name) if name else None
    if obj is None or not hasattr(obj,'Shape'):raise ValueError('Choose a final CAD solid in the document')
    return obj


def inspect(doc):
    registry=_registry(doc)
    used={p['key'] for p in registry['parameters']}
    candidates=[x for x in _targets(doc) if x['key'] not in used]
    solids=[{'name':o.Name,'label':o.Label,'volume_mm3':o.Shape.Volume}
            for o in doc.Objects if hasattr(o,'Shape') and len(o.Shape.Solids)==1 and o.Shape.Volume>0]
    params=[{**p,'value':_read(doc,p)} for p in registry['parameters']]
    return {'parameters':params,'candidates':candidates,'final':registry['final'],
            'final_candidates':solids,'document':doc.Label}


def _face_metric(face):
    b=face.BoundBox;c=face.CenterOfMass
    return (type(face.Surface).__name__,face.Area,c.x,c.y,c.z,
            b.XMin,b.XMax,b.YMin,b.YMax,b.ZMin,b.ZMax)


def _face_changed(before,after):
    if before[0]!=after[0]:return True
    return _changes_shape(before[1:],after[1:])


def surface_selection(doc):
    """Exact final BREP face tessellation; face-to-dimension links are suggestions.

    A small perturbation tests which existing driving dimensions alter each face.
    Face numbers can change after a topology change, so such probes do not create
    a mapping. This is deliberately not reverse engineering of a STEP file.
    """
    registry=_registry(doc);final=_final(doc,registry);shape=final.Shape
    if shape.isNull() or not shape.isValid() or len(shape.Solids)!=1:
        raise ValueError('Final CAD shape must contain one valid solid')
    if len(shape.Faces)>256:raise ValueError('Interactive face selection supports up to 256 faces')
    candidates=_targets(doc)
    if len(candidates)>64:raise ValueError('Interactive dimension probing supports up to 64 candidates')
    base=[_face_metric(f) for f in shape.Faces]
    faces=[];triangle_count=0
    for index,face in enumerate(shape.Faces):
        vertices,triangles=face.tessellate(.35)
        triangle_count+=len(triangles)
        if triangle_count>50000:raise ValueError('Interactive viewer supports up to 50,000 triangles')
        faces.append({'id':index+1,'surface':base[index][0],
                      'triangles':[[round(value,5) for vertex in (vertices[i] for i in tri)
                                    for value in (vertex.x,vertex.y,vertex.z)] for tri in triangles],
                      'candidate_keys':[]})
    for candidate in candidates:
        value=candidate['value'];step=max(.05,abs(value)*.02)
        entry={'object':candidate['object'],'kind':candidate['kind']}
        if candidate['kind']=='property':entry['property']=candidate['dimension']
        else:
            # Unnamed sketch constraints are addressed by index until registered.
            entry['constraint_index']=int(candidate['key'].rsplit('|',1)[1])
        assigned=False
        try:
            _assign(doc,entry,value+step)
            assigned=True
            doc.recompute();changed=final.Shape
            if changed.isNull() or not changed.isValid() or len(changed.Faces)!=len(faces):continue
            after=[_face_metric(f) for f in changed.Faces]
            for face,old,new in zip(faces,base,after):
                if _face_changed(old,new):face['candidate_keys'].append(candidate['key'])
        except Exception:
            # A constrained/imported feature may reject perturbation.
            continue
        finally:
            if assigned:_assign(doc,entry,value);doc.recompute()
    b=shape.BoundBox
    return {'final':final.Name,'bounds':[[b.XMin,b.YMin,b.ZMin],[b.XMax,b.YMax,b.ZMax]],
            'faces':faces,'triangle_count':triangle_count,
            'mapping_basis':'A small independent CAD recomputation; suggestions require user confirmation.'}


def bootstrap(path):
    doc=App.newDocument('RollerSupport')
    doc.Label='Editable roller support'
    block=doc.addObject('Part::Box','SupportBlock');block.Label='Printed support block'
    block.Length=32;block.Width=40;block.Height=26
    block.Placement.Base=App.Vector(-16,-20,0)
    groove=doc.addObject('Part::Cylinder','RollerCradle');groove.Label='Metal roller cradle'
    groove.Radius=4.15;groove.Height=42
    groove.Placement=App.Placement(App.Vector(0,-21,26),App.Rotation(App.Vector(0,0,1),App.Vector(0,1,0)))
    previous=block
    for name,cutter in [('CradleCut',groove)]:
        cut=doc.addObject('Part::Cut',name);cut.Base=previous;cut.Tool=cutter;previous=cut
    for j,(x,y) in enumerate(((-10,-12),(-10,12),(10,-12),(10,12)),1):
        hole=doc.addObject('Part::Cylinder',f'BoltBore{j}');hole.Label=f'Bolt bore {j}'
        hole.Radius=2.25;hole.Height=28;hole.Placement.Base=App.Vector(x,y,-1)
        cut=doc.addObject('Part::Cut',f'BoreCut{j}');cut.Base=previous;cut.Tool=hole;previous=cut
    previous.Label='Final printed roller support'
    registry={'parameters':[],'final':previous.Name}
    _save_registry(doc,registry);doc.recompute()
    if not previous.Shape.isValid() or len(previous.Shape.Solids)!=1:raise RuntimeError('Bootstrap CAD is not a solid')
    doc.saveAs(str(path));App.closeDocument(doc.Name)
    return {'path':str(path)}


def bootstrap_sketch(path):
    import Sketcher
    doc=App.newDocument('SketchFixture')
    doc.Label='Editable sketch-driven cylindrical locator'
    sketch=doc.addObject('Sketcher::SketchObject','LocatorProfile')
    sketch.Label='Selectable locator circle'
    sketch.addGeometry(Part.Circle(App.Vector(0,0,0),App.Vector(0,0,1),4),False)
    sketch.addConstraint(Sketcher.Constraint('Radius',0,4.0))
    solid=doc.addObject('Part::Extrusion','LocatorSolid')
    solid.Label='Final printed cylindrical locator'
    solid.Base=sketch;solid.Dir=App.Vector(0,0,8);solid.Solid=True
    _save_registry(doc,{'parameters':[],'final':solid.Name})
    doc.recompute()
    if len(solid.Shape.Solids)!=1 or not solid.Shape.isValid():
        raise RuntimeError('Sketch-driven CAD did not create one solid')
    doc.saveAs(str(path));App.closeDocument(doc.Name)
    return {'path':str(path)}


def dispatch(request):
    action=request['action']
    if action=='bootstrap':return bootstrap(Path(request['document']))
    if action=='bootstrap_sketch':return bootstrap_sketch(Path(request['document']))
    doc=App.openDocument(str(request['document']))
    try:
        if action=='inspect':return inspect(doc)
        if action=='surface':return surface_selection(doc)
        if action=='register':
            name=request['name']
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,47}',name):raise ValueError('Use a unique lower-case parameter name')
            minimum,maximum=float(request['min']),float(request['max'])
            if not all(map(math.isfinite,(minimum,maximum))) or minimum>=maximum:
                raise ValueError('Invalid parameter range')
            selected=_resolve(doc,request['target']);value=selected['value']
            if not minimum<=value<=maximum:raise ValueError('The current CAD dimension is outside the proposed range')
            registry=_registry(doc)
            if any(p['name']==name for p in registry['parameters']):raise ValueError('Parameter name already exists')
            entry={'name':name,'label':request.get('label',name),'min':minimum,'max':maximum,
                   'unit':'mm','object':selected['object'],'kind':selected['kind'],'key':selected['key']}
            if selected['kind']=='property':entry['property']=selected['dimension']
            else:
                obj=doc.getObject(selected['object']);index=int(selected['key'].rsplit('|',1)[1])
                obj.renameConstraint(index,name)
                entry['constraint']=name
            before=_signature(_final(doc,registry).Shape)
            step=max(.05,abs(value)*.02)
            probe=value+step if value+step<=maximum else value-step
            if probe<minimum or probe==value:raise ValueError('No room to test this CAD dimension')
            _assign(doc,entry,probe);doc.recompute()
            after=_signature(_final(doc,registry).Shape)
            _assign(doc,entry,value);doc.recompute()
            if not _changes_shape(before,after):
                raise ValueError('This dimension has no measurable effect on the final solid')
            registry['parameters'].append(entry);_save_registry(doc,registry)
            doc.recompute();doc.save()
            return inspect(doc)
        if action=='select_final':
            name=request['final'];registry=_registry(doc)
            if name not in [p['name'] for p in inspect(doc)['final_candidates']]:raise ValueError('Invalid final solid')
            registry['final']=name;_save_registry(doc,registry);doc.save()
            return inspect(doc)
        if action=='generate':
            registry=_registry(doc)
            changes=request['values']
            if not isinstance(changes,dict) or set(changes)-{p['name'] for p in registry['parameters']}:
                raise ValueError('Unknown native CAD parameter')
            checks=[];previous=_signature(_final(doc,registry).Shape)
            any_changed=False
            for entry in registry['parameters']:
                value=changes.get(entry['name'],_read(doc,entry))
                if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
                    raise ValueError('CAD parameter must be a finite number')
                passed=entry['min']<=value<=entry['max']
                checks.append({'code':'range_'+entry['name'],'status':'PASS' if passed else 'FAIL',
                               'observed':value,'limit':[entry['min'],entry['max']]})
                if passed:
                    any_changed|=abs(value-_read(doc,entry))>1e-9
                    _assign(doc,entry,value)
            if any(c['status']=='FAIL' for c in checks):
                return {'decision':'REJECTED','checks':checks,'parameters':{p['name']:changes.get(p['name'],_read(doc,p)) for p in registry['parameters']}}
            doc.recompute()
            final=_final(doc,registry);shape=final.Shape
            if shape.isNull() or not shape.isValid() or len(shape.Solids)!=1 or shape.Volume<=0:
                checks.append({'code':'native_brep','status':'FAIL','observed':'Invalid or multiple solids'})
                return {'decision':'REJECTED','checks':checks}
            if any_changed and not _changes_shape(previous,_signature(shape)):
                checks.append({'code':'parameter_affects_final_shape','status':'FAIL',
                               'observed':'Changed inputs left the final solid unchanged'})
                return {'decision':'REJECTED','checks':checks}
            # This named example additionally checks actual cutter positions against
            # the changed block. Other documents need their own engineering rules.
            if doc.getObject('RollerCradle') and doc.getObject('SupportBlock') and all(doc.getObject(f'BoltBore{i}') for i in range(1,5)):
                block=doc.getObject('SupportBlock').Shape.BoundBox
                for i in range(1,5):
                    hole=doc.getObject(f'BoltBore{i}');x=hole.Placement.Base.x;y=hole.Placement.Base.y;r=float(hole.Radius)
                    land=min(x-block.XMin,block.XMax-x,y-block.YMin,block.YMax-y)-r
                    ok=land>=2
                    checks.append({'code':f'bore_{i}_edge_land','status':'PASS' if ok else 'FAIL','observed':land,'limit':2})
                if any(c['status']=='FAIL' for c in checks):return {'decision':'REJECTED','checks':checks}
            destination=Path(request['output']);destination.mkdir(parents=True,exist_ok=True)
            doc.saveAs(str(destination/'editable.FCStd'))
            Part.export([final],str(destination/'native.step'))
            bounds=shape.BoundBox
            return {'decision':'REVIEW_REQUIRED','checks':checks,
                    'parameters':{p['name']:_read(doc,p) for p in registry['parameters']},
                    'bounds_mm':[bounds.XLength,bounds.YLength,bounds.ZLength],
                    'volume_mm3':shape.Volume,'final':final.Name}
        raise ValueError('Unknown FreeCAD action')
    finally:App.closeDocument(doc.Name)


if __name__=='__main__':
    request_path=os.environ['FIXTURE_FREECAD_REQUEST']
    result_path=os.environ['FIXTURE_FREECAD_RESULT']
    try:
        result=dispatch(json.loads(Path(request_path).read_text()))
        Path(result_path).write_text(json.dumps({'ok':True,'result':result},ensure_ascii=False))
    except Exception as error:
        Path(result_path).write_text(json.dumps({'ok':False,'error':str(error),'traceback':traceback.format_exc()}))
        sys.exit(1)
