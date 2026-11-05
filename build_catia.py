"""Native editable CATIA V5 parts; nested reusable CATProduct instances.

Run: py build_catia.py --output-dir CAD
No old station 5 geometry is imported. Failure stops and preserves completed parts.
"""
from __future__ import annotations
import argparse,json,math,traceback,uuid
from pathlib import Path
import slicer_design as d

BUILDER_REVISION='CC-SHAFT-AND-SESSION-NAME-FIX-2026-11-05'

def bind(part,sk,point,x,y,label):
    ref=part.CreateReferenceFromObject(point)
    for a,n,v in [('X','VDirection',x),('Y','HDirection',y)]:
        axis=part.CreateReferenceFromObject(sk.AbsoluteAxis.GetItem(n))
        c=sk.Constraints.AddBiEltCst(2 if abs(v)<1e-8 else 1,ref,axis)
        if abs(v)>=1e-8:c.Mode=0;c.Dimension.Value=abs(float(v))
        c.Name=label+'_'+a

def polygon_sketch(part,body,outer,loops=(),name='Profile',axis=None,support=None):
    part.InWorkObject=body
    sk=body.Sketches.Add(support if support is not None else part.OriginElements.PlaneXY);sk.Name=name
    if axis is not None:sk.SetAbsoluteAxisData(tuple(float(v) for v in axis))
    f=sk.OpenEdition()
    for j,coords in enumerate([outer,*loops]):
        ps=[f.CreatePoint(float(x),float(y)) for x,y in coords]
        for i,(a,b) in enumerate(zip(coords,coords[1:]+coords[:1])):
            ln=f.CreateLine(float(a[0]),float(a[1]),float(b[0]),float(b[1]));ln.StartPoint=ps[i];ln.EndPoint=ps[(i+1)%len(ps)]
        for i,(p,(x,y)) in enumerate(zip(ps,coords)):bind(part,sk,p,x,y,f'P{j}_{i}')
    sk.CloseEdition();part.Update();return sk

def circles_sketch(part,body,circles,name,axis=None):
    part.InWorkObject=body;support=part.OriginElements.PlaneXY
    if axis is not None:
        normal=d.cross(axis[3:6],axis[6:9])
        if abs(normal[0])>1-1e-8:support=part.OriginElements.PlaneYZ
        elif abs(normal[1])>1-1e-8:support=part.OriginElements.PlaneZX
        elif abs(normal[2])<1-1e-8:raise ValueError('Circular sketch requires an orthogonal support plane')
    sk=body.Sketches.Add(support);sk.Name=name
    if axis is not None:sk.SetAbsoluteAxisData(tuple(float(v) for v in axis))
    f=sk.OpenEdition()
    for i,(x,y,r) in enumerate(circles):
        pt=f.CreatePoint(float(x),float(y));c=f.CreateClosedCircle(float(x),float(y),float(r));c.CenterPoint=pt
        bind(part,sk,pt,x,y,f'C{i}')
        con=sk.Constraints.AddMonoEltCst(14,part.CreateReferenceFromObject(c));con.Mode=0;con.Dimension.Value=float(r)
    sk.CloseEdition();part.Update();return sk

def belt_sketch(part,body,p):
    # Native circular arcs and tangent lines; not separate flat belt strips.
    sk=body.Sketches.Add(part.OriginElements.PlaneXY);sk.Name='Continuous_Endless_Belt_Path'
    f=sk.OpenEdition()
    for off in (0,p['belt_thickness']):
        cs=[(x,y,r+off) for x,y,r in p['centers']];tang=[]
        for (x,y,r),(xx,yy,rr) in zip(cs,cs[1:]+cs[:1]):
            a=math.atan2(yy-y,xx-x)-math.acos((r-rr)/math.hypot(xx-x,yy-y))
            tang.append(((x+r*math.cos(a),y+r*math.sin(a)),(xx+rr*math.cos(a),yy+rr*math.sin(a))))
        pout=[f.CreatePoint(*a) for a,b in tang];pin=[f.CreatePoint(*b) for a,b in tang]
        for i,(a,b) in enumerate(tang):
            ln=f.CreateLine(*a,*b);ln.StartPoint=pout[i];ln.EndPoint=pin[i]
        for i,(x,y,r) in enumerate(cs):
            a=tang[(i-1)%len(cs)][1];b=tang[i][0]
            aa=math.atan2(a[1]-y,a[0]-x);bb=math.atan2(b[1]-y,b[0]-x)
            while bb<=aa:bb+=2*math.pi
            arc=f.CreateCircle(x,y,r,aa,bb);arc.StartPoint=pin[(i-1)%len(cs)];arc.EndPoint=pout[i]
    sk.CloseEdition();part.Update();return sk


def revolved_shell(part,body,p):
    """Closed meridian + an explicitly registered, constrained sketch axis.

    Sketch.CenterLine is the axis used by AddNewShaft. Marking an ordinary
    Line2D as Construction and assigning its object reference to RevoluteAxis
    does not register the sketch axis. Keep the four profile edges closed;
    their radial separation already describes the physical wall thickness.
    CAA reference: SketcherInterfaces/interface_Sketch_21197.htm (CenterLine).
    """
    sk=polygon_sketch(part,body,p['section'],name='Conical_Meridian',
                      axis=(0,0,0,1,0,0,0,0,1),support=part.OriginElements.PlaneZX)
    f=sk.OpenEdition()
    z0=min(z for r,z in p['section']);z1=max(z for r,z in p['section'])
    a=f.CreatePoint(0.,float(z0));b=f.CreatePoint(0.,float(z1))
    a.Construction=True;b.Construction=True
    axis=f.CreateLine(0.,float(z0),0.,float(z1))
    axis.StartPoint=a;axis.EndPoint=b;axis.Construction=True
    sk.CenterLine=axis  # Set while editing, BEFORE AddNewShaft.
    bind(part,sk,a,0.,z0,'Revolution_Axis_Start')
    bind(part,sk,b,0.,z1,'Revolution_Axis_End')
    sk.CloseEdition();part.Update();part.InWorkObject=body
    shaft=part.ShapeFactory.AddNewShaft(sk);shaft.Name='Open_Conical_Shell'
    shaft.IsThin=False
    shaft.SecondAngle.Value=0.;shaft.FirstAngle.Value=360.
    try:part.Update()
    except Exception as exc:
        raise RuntimeError(f'{p["master"]} / {p["family"]}: closed-meridian Shaft update failed '
                           '(Sketch.CenterLine; first angle 360, second angle 0)') from exc
    return sk

def close_failed_document(catia,doc):
    """Close only the document this call created, never pre-existing user docs."""
    previous=None
    try:
        previous=catia.DisplayFileAlerts;catia.DisplayFileAlerts=False
        doc.Close()
    except Exception as exc:print(f'NOTE: failed generated document could not be closed: {exc}',flush=True)
    finally:
        if previous is not None:
            try:catia.DisplayFileAlerts=previous
            except Exception:pass


def part_document(catia,p,path,part_number=None):
    doc=catia.Documents.Add('Part')
    try:
        doc.Activate()
        number=part_number or p['master']+'_'+uuid.uuid4().hex[:12].upper()
        return populate_part_document(doc,p,path,number)
    except Exception:
        close_failed_document(catia,doc)
        raise


def populate_part_document(doc,p,path,part_number):
    part=doc.Part;body=part.MainBody
    part.Update()  # Finish new-document initialization before editing its reference identity.
    doc.Product.PartNumber=part_number
    doc.Product.Nomenclature=p['family'];part.InWorkObject=body;hidden=[]
    part.Parameters.CreateString('Generator_Master_ID',p['master'])
    part.Parameters.CreateString('Material_Specification',p['material'])
    part.Parameters.CreateString('Revision',d.REVISION)
    part.Parameters.CreateString('Builder_Revision',BUILDER_REVISION)
    part.Parameters.CreateString('Manufacturing_Status','Custom design; drawing and prototype validation required')
    if p['kind']=='revolve':
        sk=revolved_shell(part,body,p)
    elif p['kind']=='tube':
        sk=polygon_sketch(part,body,p['points'],name='Single_Closed_Outer_Square')
    elif p['kind']=='circle':
        cs=[(0,0,p['radius'])]+([(0,0,p['inner'])] if p.get('inner') else [])
        sk=circles_sketch(part,body,cs,'Radial_Section')
    elif p['kind']=='belt':sk=belt_sketch(part,body,p)
    elif p['kind']=='bolt':sk=circles_sketch(part,body,[(0,0,p['diameter']/2)],'Bolt_Shank')
    else:sk=polygon_sketch(part,body,p['points'],p.get('loops',[]),'Single_Closed_Profile' if p.get('single_closed_profile') else 'Plate_Profile')
    hidden.append(sk);length=p.get('depth',p.get('length'))
    if p['kind']!='revolve':
        parameter=part.Parameters.CreateDimension('Pad_Length','LENGTH',0)
        parameter.ValuateFromString(f'{length}mm')
        pad=part.ShapeFactory.AddNewPad(sk,float(length));pad.Name='Profile_Pad'
        part.Relations.CreateFormula('Length_Control','',pad.FirstLimit.Dimension,'Pad_Length');part.Update()
    if p['kind']=='tube':
        ski=polygon_sketch(part,body,p['loops'][0],name='Square_Tube_Bore',
                           axis=(0,0,length,1,0,0,0,1,0))
        pocket=part.ShapeFactory.AddNewPocket(ski,float(length));pocket.Name='Hollow_Section_Through_Pocket'
        part.Parameters.CreateDimension('Tube_Wall','LENGTH',0).ValuateFromString(str(p['wall_mm'])+'mm')
        part.Update();hidden.append(ski)
    if p['kind']=='bolt':
        # Head projects backward; bolt placement datum is the bearing face.
        skh=circles_sketch(part,body,[(0,0,p['head_diameter']/2)],'Bolt_Head',axis=(0,0,-p['head_height'],1,0,0,0,1,0))
        part.ShapeFactory.AddNewPad(skh,float(p['head_height']));part.Update();hidden.append(skh)
    if p.get('holes'):
        skh=circles_sketch(part,body,p['holes'],'Through_Bolt_Holes',axis=(0,0,length,1,0,0,0,1,0))
        part.ShapeFactory.AddNewPocket(skh,float(length));part.Update();hidden.append(skh)
    for i,hole in enumerate(p.get('drills',[])):
        n=d.unit(hole['normal']);seed=(0,1,0) if abs(n[0])>.9 else (1,0,0)
        v=d.unit(d.cross(n,seed));u=d.cross(v,n)
        skh=circles_sketch(part,body,[(0,0,hole['radius'])],f'Joint_Hole_{i+1}',axis=(*hole['center'],*u,*v))
        part.ShapeFactory.AddNewPocket(skh,float(hole['depth']));part.Update();hidden.append(skh)
    sel=doc.Selection;sel.Clear()
    for obj in hidden+[part.OriginElements.PlaneXY,part.OriginElements.PlaneYZ,part.OriginElements.PlaneZX]:sel.Add(obj)
    sel.VisProperties.SetShow(1);sel.Clear();sel.Add(body);sel.VisProperties.SetRealColor(*p['color'],1);sel.Clear()
    path.parent.mkdir(parents=True,exist_ok=True);doc.SaveAs(str(path.resolve()));return doc

def build(catia,folder,config=None):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    from clean_outputs import mark_model_folder
    mark_model_folder(folder,d.PRODUCT_NAME)
    m,payload=d.write_geometry(folder,config)
    master_dir=folder/'CATParts';cache={};count=0
    build_id=uuid.uuid4().hex[:12].upper();product_doc=None
    status=dict(revision=d.REVISION,builder_revision=BUILDER_REVISION,build_id=build_id,
                status='building',completed_masters=[],components=len(m.parts),part_numbers={})
    def save_status(): (folder/'BUILD_STATUS.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
    try:
        for p in m.parts:
            if p['master'] in cache:continue
            # CATIA also requires session-unique document names. A new output
            # folder alone does not distinguish equal basenames in open sessions.
            part_number=p['master']+'_'+build_id
            path=master_dir/(p['master']+'_'+p['family']+'_'+build_id+'.CATPart')
            status['current_master']=dict(number=count+1,master=p['master'],family=p['family'],kind=p['kind'],path=str(path))
            save_status()
            print(f'BUILD MASTER {count+1}/{payload["master_count"]}: {p["family"]} [{p["kind"]}]',flush=True)
            try:doc=part_document(catia,p,path,part_number)
            except Exception as exc:
                raise RuntimeError(f'MASTER {count+1}/{payload["master_count"]}: {p["master"]} / {p["family"]}; '
                                   f'previous {count} masters saved in {master_dir}') from exc
            doc.Close();cache[p['master']]=path;status['part_numbers'][p['master']]=part_number
            count+=1;status['completed_masters'].append(str(path));save_status()
            print(f'SAVED MASTER {count}/{payload["master_count"]}: {p["family"]}',flush=True)
        status.pop('current_master',None)
        doc=catia.Documents.Add('Product');product_doc=doc;doc.Activate()
        root=doc.Product;root.PartNumber=d.PRODUCT_NAME+'_'+build_id
        root.Nomenclature='CC-DL centrifugal potato slicer / fixed knives 1.5 mm / 800 mm feeder / welded SUS304 square tube'
        categories={};types={};families={}
        type_order={'Square_Tube':1,'Profile':1,'Plate':2,'Bracket':3,'Fastener':4,'Foot':5,'Belt':1,'Mechanism':2,'Bearing':3,'Knife':4,'Adjustment':5,'Chute':6,'Hopper':7,'Drive':1,'Control':2}
        for p in m.parts:
            cat=p['category'];typ=p['part_type'];family=p['family']
            if cat not in categories:
                categories[cat]=root.Products.AddNewProduct(cat);categories[cat].Name=cat
            tk=(cat,typ)
            if tk not in types:
                title=f'{cat[0]}-{type_order.get(typ,9)}_{typ}'
                types[tk]=categories[cat].Products.AddNewProduct(title);types[tk].Name=title
            fk=(cat,typ,family)
            if fk not in families:
                families[fk]=types[tk].Products.AddNewProduct(family);families[fk].Name=family
            # Every occurrence references the same saved CATPart, equivalent to
            # CATIA multi-instantiation; no duplicated feature bodies per occurrence.
            parent=families[fk];before=parent.Products.Count
            parent.Products.AddComponentsFromFiles((str(cache[p['master']]),),'All')
            comp=parent.Products.Item(before+1);comp.Name=p['name']
            comp.Position.SetComponents(tuple(v for a in p['axes'] for v in a)+tuple(p['origin']))
        root.Update();product=folder/(d.PRODUCT_NAME+'_'+build_id+'.CATProduct');doc.SaveAs(str(product))
        status.update(status='complete',product=str(product),unique_catparts=len(cache),instances=len(m.parts),
                      assembly_validation='Built and updated in CATIA; operational validation remains separate')
        save_status();print('SAVED PRODUCT '+str(product),flush=True);return doc
    except Exception as exc:
        if product_doc is not None:close_failed_document(catia,product_doc)
        status.update(status='failed',error=repr(exc));save_status();raise

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output-dir',type=Path,default=d.ROOT/'CAD');ap.add_argument('--config',type=Path)
    args=ap.parse_args()
    import pythoncom,win32com.client
    pythoncom.CoInitialize()
    try:
        try:catia=win32com.client.GetActiveObject('CATIA.Application')
        except Exception:catia=win32com.client.Dispatch('CATIA.Application')
        config=json.loads(args.config.read_text()) if args.config else None
        build(catia,args.output_dir,config)
    finally:pythoncom.CoUninitialize()
