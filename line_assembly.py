"""Saved-machine discovery and floor-based 01-12 assembly; no COM on import."""
from __future__ import annotations
from pathlib import Path
import html
import json
import math
import uuid


def read_json(path):
    try:return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return None


def local_product(record,info_path):
    raw=record.get('product')
    if not raw:return None
    # Prefer the file next to its own metadata after a directory was moved.
    basename=str(raw).replace('\\','/').rsplit('/',1)[-1]
    paths=[info_path.parent/basename,Path(raw)]
    return next((p.resolve() for p in paths if p.suffix.lower()=='.catproduct' and p.is_file() and p.stat().st_size>0),None)


def validate_ports(index,record):
    for key in ('inlet',) if index==12 else ('inlet','outlet'):
        p=record.get(key)
        if not isinstance(p,(list,tuple)) or len(p)!=3 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in p):
            raise ValueError(f'Station {index:02d}: missing/invalid {key} in MODEL_INFO or --existing-map')


def station_sequence(through=12,exclude_stage=None):
    if not 1<=through<=12:raise ValueError('through must be 1..12')
    if exclude_stage not in (None,4):raise ValueError('Only station 4 can currently be omitted')
    if exclude_stage==4 and through<5:raise ValueError('Omitting station 4 requires through >=5')
    return [i for i in range(1,through+1) if i!=exclude_stage]


def discover_existing(base,through=12,mapping=None,exclude_stage=None):
    """Find complete root products only; never guess a subassembly or create CAD."""
    base=Path(base).resolve();candidates={i:[] for i in station_sequence(through,exclude_stage)}
    for folder in base.iterdir():
        if not folder.is_dir():continue
        info=folder/'MODEL_INFO.json';record=read_json(info)
        if not isinstance(record,dict):continue
        name=record.get('name','')
        try:index=int(name[:2])
        except (ValueError,TypeError):continue
        if index not in candidates or record.get('build_status') in ('partial','failed','building'):continue
        product=local_product(record,info)
        if product is None:continue
        try:validate_ports(index,record)
        except ValueError:continue
        candidates[index].append((product.stat().st_mtime_ns,dict(record,product=str(product))))
    chosen={i:max(rows,key=lambda r:r[0])[1] for i,rows in candidates.items() if rows}
    if mapping:
        mapping_path=Path(mapping).resolve();raw=read_json(mapping_path)
        if not isinstance(raw,dict):raise ValueError('--existing-map must be a JSON object keyed "1".."12"')
        for key,value in raw.items():
            if exclude_stage is not None and key==str(exclude_stage):continue
            if key not in {str(i) for i in candidates}:raise ValueError('Unexpected station in --existing-map: '+key)
            override={'product':value} if isinstance(value,str) else value
            if not isinstance(override,dict) or not isinstance(override.get('product'),str):
                raise ValueError('Each mapping entry requires a CATProduct path')
            path=Path(override['product']).expanduser()
            if not path.is_absolute():path=mapping_path.parent/path
            path=path.resolve()
            if path.suffix.lower()!='.catproduct' or not path.is_file() or not path.stat().st_size:
                raise ValueError('Missing CATProduct: '+str(path))
            record=read_json(path.parent/'MODEL_INFO.json') or {}
            record.update(override);record['product']=str(path);record.setdefault('name',f'{int(key):02d}_Existing')
            validate_ports(int(key),record);chosen[int(key)]=record
    missing=sorted(set(candidates)-set(chosen))
    if missing:
        raise ValueError('Existing-only assembly: missing complete stations '+', '.join(f'{i:02d}' for i in missing)+
                         '. Build them with --stages '+ ' '.join(map(str,missing))+
                         ', or supply --existing-map with product paths and inlet/outlet coordinates. No machines were built.')
    return chosen


def refresh_existing_reviews(base,records):
    """Render each saved model's calculation snapshot, never today's defaults."""
    from review_layout import station_folder,data_name,page_name,write_index,compact_report
    for i,record in records.items():
        model_dir=Path(record['product']).parent;source=model_dir/data_name(i)
        r=read_json(source)
        if not isinstance(r,dict):
            folder=station_folder(base,i);folder.mkdir(parents=True,exist_ok=True)
            from review_layout import document
            # An explicit missing-data record prevents a stale unrelated review
            # being presented as the selected existing CAD model.
            r=dict(index=i,revision='EXISTING-CAD-REVIEW-UNAVAILABLE',inputs={},warnings=['선택한 기존 모델의 계산 스냅샷 없음'],
                   review_unavailable=True,selected_product=record['product'])
            page=document(f'{i:02d} 기존 모델 리뷰','<p>선택한 CATProduct의 계산 스냅샷이 없습니다. 현재 코드의 기본값으로 기존 모델을 검증한 것처럼 표시하지 않습니다.</p><p>'+html.escape(record['product'])+'</p>')
        else:
            folder=station_folder(base,i);folder.mkdir(parents=True,exist_ok=True)
            if i==5:
                # Preserve its as-built report: an older saved model may predate
                # the external gearbox modification.
                saved=model_dir/page_name(i)
                if saved.is_file():page=saved.read_text(encoding='utf-8')
                else:
                    from slicer_review import report_html
                    page=report_html(r)
            elif i==12:
                from station12_design import report_html
                page=report_html(r)
            else:page=compact_report(i,r)
            r['selected_product']=record['product']
        (folder/data_name(i)).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/page_name(i)).write_text(page,encoding='utf-8')
        print('SAVED EXISTING MODEL REVIEW '+str(folder/page_name(i)),flush=True)
    write_index(base)


def transfer_plan(index,upstream,downstream,downstream_index=None):
    import build_line as line
    next_index=index+1 if downstream_index is None else downstream_index
    if index==5 and next_index==6:
        from transfer_05_06 import geometry
        return geometry(upstream,downstream)
    if upstream.get('outlet_direction') and upstream['outlet_direction'][2]<-.5:
        raise ValueError(f'No downward-outlet connection is defined for {index:02d} -> {next_index:02d}')
    return line.transfer_between(index,upstream,downstream,next_index)


def layout_report(base,info,metas):
    from review_layout import root,document,table,fmt
    out=root(base);out.mkdir(parents=True,exist_ok=True)
    (out/'01_12_Assembly_Layout.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[]
    for i,m in metas.items():
        position=info['placements_mm']['stations'][i][0]
        rows.append((f'{i:02d} '+m['name'],fmt(position),m['product']))
    body=table(['기계','배치 원점 X×Y×Z mm','참조 CATProduct'],rows)
    body+='<p>'+html.escape(info['layout_note'])+'</p>'
    body+='<p>12번 자체 승강 컨베이어는 포장기 모델에 포함됩니다. 11→12번 연결은 그 컨베이어의 낮은 투입 끝으로 이어집니다.</p>'
    body+='<p>조립 순서: '+html.escape(' → '.join(str(i) for i in info['station_sequence']))+'</p>'
    if info['excluded_stations']:body+='<p>4번과 3→4·4→5 연결부는 제외하고 3→5 연결부를 사용했습니다. 기존 4번 파일과 개별 리뷰는 보존됩니다.</p>'
    body+='<p>5→6번은 하부 받이·측면 인출 벨트·경사 컨베이어를 포함합니다. 5번은 바닥 높이를 유지하고 6번 이후는 5번 기준 −Y 방향으로 배치합니다.</p>' if 5 in metas and 6 in metas else ''
    if 5 in info.get('connection_designs',{}):
        from review_layout import write_connection_concept
        write_connection_concept(out,info['connection_designs'][5]['design'])
    body+='<p>CATProduct는 외부 CATPart 및 하위 CATProduct를 참조합니다. 관련 기계 폴더를 함께 보관하세요. --zip은 전체 참조 기계 폴더를 포함합니다.</p>'
    (out/'01_12_Assembly_Layout.html').write_text(document('전체 라인 조립 · 배치 및 참조 파일',body),encoding='utf-8')


def open_paths(catia):
    """Snapshot user-owned windows; None means we cannot safely distinguish them."""
    paths=set()
    try:
        for i in range(1,catia.Documents.Count+1):
            name=str(catia.Documents.Item(i).FullName)
            if name:paths.add(Path(name).resolve())
    except Exception:return None
    return paths


def release_created_document(doc,product_path,user_paths):
    if user_paths is None or Path(product_path).resolve() in user_paths:return
    actual=Path(str(doc.FullName)).resolve()
    if actual!=Path(product_path).resolve():
        raise RuntimeError('Returned document does not match saved model; it was not closed: '+str(actual))
    doc.Close()


def insert_saved_product(doc,source,name,placement):
    """Load a saved root by path, rather than passing a long-lived COM handle."""
    import build_line as line
    source=Path(source).resolve()
    if not source.is_file() or not source.stat().st_size:raise FileNotFoundError(str(source))
    doc.Activate()
    products=doc.Product.Products;before=products.Count
    products.AddComponentsFromFiles((str(source),),'All')
    if products.Count!=before+1:
        raise RuntimeError('CATIA did not insert exactly one root Product for '+str(source))
    component=products.Item(before+1)
    component.Name=name;line.place(component,*placement)


def save_assembly_info(folder,info):
    path=folder/'MODEL_INFO.json';temporary=folder/'MODEL_INFO.json.tmp'
    temporary.write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def build(catia,base,rebuild=False,through=12,step=False,existing=None,exclude_stage=None,**options):
    import build_line as line
    from transfer_assembly import ensure_product
    if options.get('hood_lift',0):raise ValueError('Full line requires the fryer hood closed')
    sequence=station_sequence(through,exclude_stage)
    metas={};tmetas={};deps=[];user_paths=open_paths(catia)
    # Existing-only is preflighted for ALL stations before any new document.
    if existing is not None:
        missing=set(sequence)-set(existing)
        if missing:raise ValueError('Missing existing stations: '+str(sorted(missing)))
    for i in sequence:
        station_doc=None
        if existing is None:station_doc,meta=line.build_station(catia,i,base,rebuild,**options)
        else:
            meta=existing[i];print('REUSE SAVED STATION '+meta['product'],flush=True)
        metas[i]=meta;deps.append(Path(meta['product']).parent)
        try:
            if step:
                if station_doc is None:station_doc=line.open_document(catia,Path(meta['product']))
                line.export_step(station_doc,meta['product'])
        finally:
            if station_doc is not None:release_created_document(station_doc,meta['product'],user_paths)
            station_doc=None
    for i,next_index in zip(sequence,sequence[1:]):
        specs,meta=transfer_plan(i,metas[i],metas[next_index],next_index)
        tmetas[i]=ensure_product(catia,specs,meta,base,rebuild)
        deps.append(Path(tmetas[i]['product']).parent)
    locations=line.line_placements(metas,tmetas);name=f'Potato_Line_01_{through:02d}'
    if exclude_stage is not None:name+=f'_No{exclude_stage:02d}'
    folder=line.new_folder(Path(base),name);path=folder/(name+'.CATProduct')
    entries=[]
    for i in sequence:
        entries.append(dict(name=metas[i]['name'],source=metas[i]['product'],placement=locations['stations'][i]))
        if i in tmetas and tmetas[i].get('product'):
            entries.append(dict(name=tmetas[i]['name'],source=tmetas[i]['product'],placement=locations['transfers'][i]))
    for entry in entries:
        source=Path(entry['source'])
        if not source.is_file() or not source.stat().st_size:raise FileNotFoundError(str(source))
    info=dict(name=name,generator_revision=line.REVISION,assembly_builder='Saved-file insertion / unique transfer identities',
              build_status='building',product=str(path.resolve()),
              station_sequence=sequence,excluded_stations=[] if exclude_stage is None else [exclude_stage],
              connections=[dict(upstream=i,downstream=j,name=tmetas[i]['name']) for i,j in zip(sequence,sequence[1:])],
              connection_designs={i:m for i,m in tmetas.items() if m.get('design')},
              stations=[metas[i]['product'] for i in metas],transfers=[m['product'] for m in tmetas.values() if m.get('product')],
              pending_connections=[dict(index=i,**m) for i,m in tmetas.items() if not m.get('product')],placements_mm=locations,
              expected_components=len(entries),completed_components=0,inserted_components=[],
              existing_station_files_only=existing is not None,
              layout_note='Floor-mounted line with a low 05-06 receiver and a -90 degree turn after station 5. Dimensions are design estimates; no CATIA clash or production validation claimed.')
    retry='--assemble-existing'+(f' --through {through}' if through!=12 else '')+(f' --exclude-stage {exclude_stage}' if exclude_stage is not None else '')
    info['retry_arguments']=retry
    save_assembly_info(folder,info)
    doc=catia.Documents.Add('Product');root=doc.Product
    entry=None;number=0
    try:
        root.PartNumber=name+'_'+uuid.uuid4().hex[:8]
        root.Nomenclature='Integrated potato chip line with separately saved machine assemblies'
        for number,entry in enumerate(entries,1):
            print(f'ASSEMBLY {number}/{len(entries)}: {entry["name"]} <- {entry["source"]}',flush=True)
            insert_saved_product(doc,entry['source'],entry['name'],entry['placement'])
            doc.SaveAs(str(path))
            info['completed_components']=number
            info['inserted_components'].append(dict(name=entry['name'],source=entry['source']))
            save_assembly_info(folder,info)
            print(f'SAVED ASSEMBLY {number}/{len(entries)}: {path}',flush=True)
        root.Update();doc.SaveAs(str(path))
        info['build_status']='complete';save_assembly_info(folder,info)
    except Exception as exc:
        info.update(build_status='failed',failed_component=entry,failed_component_number=number,error=str(exc))
        try:doc.SaveAs(str(path))
        except Exception as save_exc:info['partial_save_error']=str(save_exc)
        save_assembly_info(folder,info)
        label=entry['name'] if entry else 'root initialization'
        source=entry['source'] if entry else str(path)
        raise RuntimeError(f'Assembly failed at {number}/{len(entries)}: {label}; source={source}; '
                           f'last saved count={info["completed_components"]}; partial assembly={path}. '
                           f'Saved machine and transfer files are preserved. Retry with {retry}.') from exc
    line.update_status(Path(base),name,info);layout_report(base,info,metas)
    print('SAVED FULL ASSEMBLY '+str(path),flush=True)
    return doc,info,deps
