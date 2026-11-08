"""Build stations 1-4 and 6-11 without keeping a growing parent Product open.

Save/close all masters, then each functional group, then create the final root.
Checkpoints permit saved, signature-matched geometry to survive a CATIA crash.
"""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import uuid
from packaging_machine import Occurrence
from transfer_assembly import TransferBuilder

BUILDER_REVISION='ENGINEERING-STAGED-R23-2026-11-08'


def geometry_key(spec):
    # Exactly the key used by the old engineering builder. In particular, keep
    # its treatment of profile_ends/materials and do not change the native shape.
    data={k:v for k,v in spec.items() if k not in ('name','origin','axes','group')}
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()


def signature(specs,meta):
    import build_line as line
    return hashlib.sha256((line.model_signature(specs)+'|rib-v1|'+meta.get('input_sha256','')).encode()).hexdigest()


def grouped_specs(specs):
    import build_line as line
    groups={}
    for q in specs:groups.setdefault(line.product_group(q),[]).append(q)
    return groups


def local_part(folder,relative):
    folder=folder.resolve();path=(folder/relative).resolve()
    if path.is_relative_to(folder) and path.suffix.lower()=='.catpart' and path.is_file() and path.stat().st_size:
        return path
    return None


def file_digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def recoverable_parts(base,specs,meta):
    """Read-only discovery. Never infer geometry compatibility from a name alone."""
    import build_line as line
    from line_assembly import read_json
    from review_layout import data_name
    expected=signature(specs,meta)
    raw_digest=hashlib.sha256(json.dumps(specs,sort_keys=True).encode()).hexdigest()
    groups=grouped_specs(specs);legacy={}
    for group,members in groups.items():
        for q in members:
            legacy.setdefault(geometry_key(q),Path('Parts')/group.replace(' ','_')/(q['name']+'.CATPart'))
    result={}
    for folder in sorted(Path(base).glob(meta['name']+'*')):
        if not folder.is_dir():continue
        record=read_json(folder/'MODEL_INFO.json') or {}
        if record.get('engineering_builder_revision')==BUILDER_REVISION and record.get('model_signature')==expected:
            entries=record.get('parts_by_geometry',{});checksums=record.get('part_sha256',{})
        else:
            # Legacy partial builds have no MODEL_INFO. The calculation snapshot
            # stored before modeling records the exact ordered input geometry.
            report=read_json(folder/data_name(int(meta['name'][:2]))) or {}
            if report.get('geometry_sha256')!=raw_digest:continue
            entries=legacy;checksums=None
        for key,relative in entries.items():
            if key not in legacy:continue
            path=local_part(folder,relative)
            if path is None:continue
            if checksums is not None and checksums.get(key)!=file_digest(path):continue
            if key not in result or path.stat().st_mtime_ns>result[key].stat().st_mtime_ns:result[key]=path
    return result


def checkpoint(folder,record):
    from line_assembly import save_assembly_info
    save_assembly_info(folder,record)


def rpc_failure(exc):
    seen=set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        value=getattr(exc,'hresult',None)
        if value is None and getattr(exc,'args',()) and isinstance(exc.args[0],int):value=exc.args[0]
        if value is not None and (value & 0xffffffff) in (0x800706BE,0x800706BA,0x80010108):return True
        exc=exc.__cause__ or exc.__context__
    return False


class EngineeringBuilder(TransferBuilder):
    def product_path(self,key):
        if not key:return self.folder/(self.root_name+'.CATProduct')
        return super().product_path(key)

    def create_part(self,item):
        self.record.update(phase='masters',current_master=item.name,current_source_name=item.geometry['name'])
        checkpoint(self.folder,self.record)
        path=super().create_part(item)  # Save and close before returning, even on failure.
        self.record['parts_by_geometry'][item.geometry_key]=str(path.relative_to(self.folder))
        self.record['part_sha256'][item.geometry_key]=file_digest(path)
        self.record['completed_masters']=len(self.record['parts_by_geometry'])
        counter='copied_native_masters' if item.source is not None else 'newly_modeled_masters'
        self.record[counter]+=1
        checkpoint(self.folder,self.record)
        return path

    def create_product(self,key,plan,counts,total,keep_open=False):
        self.record.update(phase='root' if not key else 'groups',current_group=list(key))
        checkpoint(self.folder,self.record)
        path,doc=super().create_product(key,plan,counts,total,keep_open)
        if key:self.record['saved_groups'].append(dict(name=key[-1],product=str(path),components=len(plan['occurrences'])))
        checkpoint(self.folder,self.record)
        return path,doc


def write_station_report(index,folder,specs,meta):
    import build_line as line
    if index==1:
        from station1_design import write_report
        return write_report(folder,line.VBK_CONFIG)
    if index==2:
        from station2_design import write_report
        return write_report(folder,line.SO_CONFIG)
    if index in (3,4):
        from peeler_design import write_report
        return write_report(index,folder,line.CRP_CONFIG if index==3 else line.MS_CONFIG)
    from finishing_design import write_report
    return write_report(index,folder,meta['engineering_inputs'],specs,meta)


def build(catia,specs,meta,base,rebuild=False):
    import build_line as line
    base=Path(base);index=int(meta['name'][:2]);model_signature=signature(specs,meta)
    if not rebuild:
        found=line.existing_station(base,meta,model_signature)
        if found:
            print('REUSE '+found['product'],flush=True)
            return line.open_document(catia,Path(found['product'])),found
    sources={} if rebuild else recoverable_parts(base,specs,meta)
    folder=line.new_folder(base,meta['name']);path=folder/(meta['name']+'.CATProduct')
    report,_=write_station_report(index,folder,specs,meta)
    print('SAVED DESIGN REPORT '+str(report),flush=True)
    masters={};occurrences=[];instances=[]
    for group,members in grouped_specs(specs).items():
        for q in members:
            key=geometry_key(q)
            if key not in masters:
                # Short file/PartNumbers and a per-build namespace prevent names
                # in another open assembly from reserving this new document.
                masters[key]=SimpleNamespace(name=f'P{len(masters)+1:04d}_{q["name"][:40]}',geometry=q,
                                              geometry_key=key,source=sources.get(key))
            name=masters[key].name;matrix=tuple(v for a in q['axes'] for v in a)+tuple(q['origin'])
            occurrences.append(Occurrence(name,(group,),matrix))
            instances.append(dict(source_name=q['name'],master=name,group=group,reference_key=key,
                                  origin_mm=q['origin'],axes=q['axes']))
    model=SimpleNamespace(parts={p.name:p for p in masters.values()},occ=occurrences)
    record=dict(meta,generator_revision=line.REVISION,engineering_builder_revision=BUILDER_REVISION,
        build_status='building',phase='masters',product=str(path.resolve()),model_signature=model_signature,
        components=len(specs),unique_catparts=len(masters),completed_masters=0,parts_by_geometry={},part_sha256={},
        saved_groups=[],copied_native_masters=0,newly_modeled_masters=0,
        recovery_sources=sorted({str(p.parent.parent) for p in sources.values()}),instances=instances,
        model_bounds=line.model_bounds(specs),helix_builder='Native Rib / analytical helix',
        sketch_constraints='Driving XY coordinates and circle radii; no fake sketch colours',planes_and_sketches='Hidden',
        build_strategy='Save/close every master; save/close every functional group; create final root last',
        product_structure='Equipment / saved functional CATProduct / editable CATPart')
    checkpoint(folder,record)
    copied=sum(p.source is not None for p in masters.values())
    print(f'{meta["name"]}: {len(masters)} unique masters; {copied} saved masters recoverable; '
          f'{len(masters)-copied} new masters. Root Product will be created last.',flush=True)
    builder=None
    try:
        builder=EngineeringBuilder(folder,app=catia,namespace=f'E{index:02d}_'+uuid.uuid4().hex[:8]+'_',root_name=meta['name'])
        builder.record=record;builder.progress_label=meta['name']
        path=builder.build(model)
        record.update(build_status='complete',phase='complete',subassemblies=record['saved_groups'],
                      native_identity_namespace=builder.namespace)
        checkpoint(folder,record);line.update_status(base,meta['name'],record)
    except Exception as exc:
        record.update(build_status='failed',error=str(exc),rpc_connection_lost=rpc_failure(exc))
        if builder is not None:record['cleanup_warnings']=builder.warnings
        checkpoint(folder,record)
        reason='CATIA RPC connection lost; restart CATIA before retrying. ' if record['rpc_connection_lost'] else ''
        raise RuntimeError(f'{meta["name"]}: {reason}Stopped in {record["phase"]}; '
                           f'{record["completed_masters"]}/{len(masters)} masters saved. Files preserved in {folder}. '
                           f'Retry --stage {index} with the same input options, without --rebuild, to recover saved geometry.') from exc
    print('SAVED '+str(path),flush=True)
    print('ZIP '+str(line.pack(folder)),flush=True)
    return builder.root_doc,record
