"""Repair/build transfer Products with unique part identities and saved groups.

Legacy transfer CATParts are copied and renumbered; their geometry is not rebuilt.
Original files and pre-existing CATIA documents are never renamed or overwritten.
"""
from pathlib import Path
from types import SimpleNamespace
import json
import shutil
import uuid
from packaging_machine import CatiaBuilder,Occurrence

BUILDER_REVISION='TRANSFER-FILE-GROUPS-R21-2026-11-07'
GROUPS={'Frame':'Frame','Internal':'Conveyor and Guides','External':'Drive and Controls'}


def saved_parts(specs,meta,record):
    """Reproduce the legacy master's filename allocation from the same geometry."""
    import build_line as line
    if not record:return {}
    folder=Path(record['product']).parent.resolve();serials={};result={}
    for q in specs:
        key=line.geometry_key(q)
        if key in result:continue
        family=(q['category'],q['part_type'],q['family'])
        serials[family]=serials.get(family,0)+1
        filename=f'{meta["name"][:2]}_{family[0][0]}_{family[1]}_{family[2]}_P{serials[family]:03d}.CATPart'
        relative=record.get('parts_by_geometry',{}).get(key,str(Path('Parts')/filename))
        path=(folder/relative).resolve()
        result[key]=path if path.is_relative_to(folder) and path.is_file() and path.stat().st_size else None
    return result


def ready(record):
    if not record or record.get('transfer_builder_revision')!=BUILDER_REVISION:return False
    folder=Path(record['product']).parent
    files=list(record.get('parts_by_geometry',{}).values())+record.get('saved_groups',[])
    return bool(files) and all((folder/p).is_file() and (folder/p).stat().st_size for p in files)


class TransferBuilder(CatiaBuilder):
    def create_part(self,item):
        import build_line as line
        key=('Part',item.name);path=self.part_path(item.name)
        failure=None
        try:
            if item.source is not None:
                # Copy first: changing PartNumber on an opened original would
                # also affect any existing assemblies that currently reference it.
                shutil.copy2(item.source,path)
                doc=self.app.Documents.Open(str(path))
                if Path(str(doc.FullName)).resolve()!=path.resolve():
                    raise RuntimeError('CATIA returned another open document for '+str(path)+
                                       '. Preserve your edits, restart CATIA, and retry; original was not renamed.')
                self.docs[key]=doc
                doc.Activate();doc.Product.PartNumber=self.identifier(item.name)
                doc.SaveAs(str(path))
            else:
                line.create_part(self.app,item.geometry,path,self.identifier(item.name),
                                 on_created=lambda doc:self.docs.__setitem__(key,doc))
            if not path.is_file() or not path.stat().st_size:raise RuntimeError('Missing saved transfer part: '+str(path))
            return path
        except BaseException as exc:
            failure=exc
            raise
        finally:
            if failure is None:self.close_owned_document(key)
            else:
                try:self.close_owned_document(key)
                except Exception as exc:self.warnings.append('Part cleanup after original failure: '+str(exc))


def ensure_product(catia,specs,meta,base,rebuild=False):
    import build_line as line
    base=Path(base);specs=line.prepare_specs(specs,meta);signature=line.model_signature(specs)
    found=None if rebuild else line.existing_station(base,meta,signature)
    if ready(found):
        print('REUSE SAVED TRANSFER '+found['product'],flush=True)
        return found
    originals=saved_parts(specs,meta,found)
    folder=line.new_folder(base,meta['name'])
    token=uuid.uuid4().hex[:8]
    number=meta['name'].replace('Transfer_','T').replace('_','')
    builder=TransferBuilder(folder,app=catia,namespace=number+'_'+token+'_',root_name=meta['name'])
    builder.progress_label=meta['name']
    masters={};by_geometry={};occurrences=[];instances=[]
    for q in specs:
        key=line.geometry_key(q)
        if key not in by_geometry:
            name=q['family'][:30]+'_'+key[:12]
            masters[name]=SimpleNamespace(name=name,geometry=q,source=originals.get(key))
            by_geometry[key]=name
        name=by_geometry[key];group=GROUPS[q['category']]
        matrix=tuple(v for axis in q['axes'] for v in axis)+tuple(q['origin'])
        occurrences.append(Occurrence(name,(group,),matrix))
        instances.append(dict(source_name=q['name'],reference_key=key,group=group,
                              origin_mm=q['origin'],axes=q['axes']))
    model=SimpleNamespace(parts=masters,occ=occurrences)
    copied=sum(item.source is not None for item in masters.values())
    print(f'{meta["name"]}: reuse geometry from {copied}/{len(masters)} saved CATParts; '
          f'{len(masters)-copied} new masters; save unique identities in {folder}',flush=True)
    completed=False
    try:
        path=builder.build(model);completed=True
        groups=[str(builder.product_path(key).relative_to(folder)) for key,_ in builder.product_plan(model) if key]
        result=dict(meta,generator_revision=line.REVISION,transfer_builder_revision=BUILDER_REVISION,build_status='complete',
                    product=str(path.resolve()),model_signature=signature,components=len(specs),unique_catparts=len(masters),
                    model_bounds=line.model_bounds(specs),native_identity_namespace=builder.namespace,
                    parts_by_geometry={k:str(builder.part_path(n).relative_to(folder)) for k,n in by_geometry.items()},
                    saved_groups=groups,instances=instances,copied_native_masters=copied,
                    newly_modeled_masters=len(masters)-copied,
                    repaired_from=None if found is None else found['product'],
                    product_structure='Saved functional CATProducts / shared uniquely numbered CATParts')
        (folder/'MODEL_INFO.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        line.update_status(base,meta['name'],result)
        print('SAVED TRANSFER '+str(path),flush=True)
        return result
    finally:
        # Only this new root remains open after the staged builder finishes.
        if completed:builder.root_doc.Close()
