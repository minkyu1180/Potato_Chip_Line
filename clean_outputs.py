"""Remove recognized generator outputs, never recursively delete a directory.

No CATIA imports. Existing output folders are recognized by MODEL_INFO.json;
new/partial builds have an ownership marker. Unknown files and links survive.
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path, PurePosixPath
import json
import os
import re
import stat
import zipfile

MARKER='.potato_line_generated.json'
GENERATOR='potato-line-native'
MODEL_NAME=re.compile(r'(?:(?:0[1-9]|1[01])_[A-Za-z0-9_]+|Transfer_\d{2}_\d{2}(?:_\w+)?|Potato_Line_01_\d{2}(?:_\w+)?)\Z')
CODES={1:('VBK',),2:('SO',),3:('CRP',),4:('MS',),5:('BSM','CC'),6:('BL',),
       7:('VDW',),8:('AD',),9:('FR',),10:('VDO',),11:('SD',)}
REPORTS={f'{i:02d}_{code}_{suffix}' for i,codes in CODES.items() for code in codes
         for suffix in ('Design_Review.html','Calculations.json')}
REPORTS.update(('05_Slicer_Review.html','05_BOM.csv','05_Labor_Cost.csv',
                '05_Tube_Cut_List.csv','05_Weld_Schedule.csv',
                '01_Material_Summary.csv','01_Material_Detail.csv'))
REPORT_DIRS={f'{i:02d}_{code}_Design_Review' for i,codes in CODES.items() for code in codes}
SUMMARY={'05_11_Design_Review_Index.html','05_11_Review_Summary.json',
         '01_11_Design_Review_Index.html','01_11_Review_Summary.json',
         '05_to_06_Connection_Concept.html','05_to_06_Connection_Concept.json'}
MODEL_DATA={'MODEL_INFO.json','BUILD_STATUS.json','05_Geometry.json','05_Config.json',MARKER}
CAD_EXTENSIONS={'.catpart','.catproduct','.stp','.step'}
EVIDENCE={'MODEL_INFO.json','BUILD_STATUS.json',MARKER}


def is_link(path):
    """Also exclude Windows junctions and other reparse points."""
    info=path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info,'st_file_attributes',0)&0x400)


def safe_path(base,path):
    """Check lexical AND resolved containment, and every component for links."""
    try:
        relative=path.relative_to(base)
        if not relative.parts:return False
        if '..' in relative.parts:return False
        current=base
        for item in relative.parts:
            current=current/item
            if is_link(current):return False
        return path.resolve().is_relative_to(base)
    except (OSError,ValueError):return False


def output_root(path):
    raw=Path(os.path.abspath(Path(path).expanduser()))
    if raw==Path(raw.anchor):raise ValueError('Refusing a drive/filesystem root')
    for component in (raw,*raw.parents):
        if component.exists() and is_link(component):raise ValueError('Output directory must not pass through a link/junction')
    if not raw.is_dir():raise ValueError('Output directory does not exist: '+str(raw))
    return raw.resolve()


def read_json(path):
    try:
        if path.stat().st_size>8*1024*1024:return None
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return None


def record_name(record):
    if not isinstance(record,dict):return None
    name=record.get('name');product=record.get('product')
    if not isinstance(name,str) or not MODEL_NAME.fullmatch(name):return None
    if not isinstance(product,str) or not product.lower().endswith('.catproduct'):return None
    if not any(k in record for k in ('generator_revision','components','model_signature','stations','build_status')):return None
    return name


def mark_model_folder(folder,name):
    """Called when a model output folder is created, before its first CATPart."""
    folder=Path(folder)
    if not MODEL_NAME.fullmatch(name):raise ValueError('Unrecognized generated model name: '+name)
    (folder/MARKER).write_text(json.dumps(dict(generator=GENERATOR,name=name,version=1)),encoding='utf-8')


def owned_model(base,folder):
    for name in (MARKER,'MODEL_INFO.json'):
        p=folder/name
        if not safe_path(base,p) or not p.is_file():continue
        data=read_json(p)
        if name==MARKER:
            if isinstance(data,dict) and data.get('generator')==GENERATOR and MODEL_NAME.fullmatch(str(data.get('name',''))):return True
        elif record_name(data):return True
    return False


def category(name):
    # An allowlist: no .py, .py.bak, Markdown, arbitrary JSON/CSV or source ZIP.
    if name in REPORTS or name in SUMMARY:return 'reports'
    if name in MODEL_DATA or Path(name).suffix.lower() in CAD_EXTENSIONS:return 'models'
    return None


def generated_zip(path):
    """Recognize model-only packs even if their original folder was removed."""
    try:
        with zipfile.ZipFile(path) as archive:
            entries=[x for x in archive.infolist() if not x.is_dir()]
            if not entries or len(entries)>100000:return False
            evidence=False;cad=False
            for entry in entries:
                p=PurePosixPath(entry.filename)
                if p.is_absolute() or '..' in p.parts:return False
                if len(p.parts)==1:
                    if p.name in REPORTS|SUMMARY:continue
                    return False
                if not MODEL_NAME.fullmatch(p.parts[0]) or not category(p.name):return False
                if p.suffix.lower() in CAD_EXTENSIONS:cad=True
                if p.name=='MODEL_INFO.json' and len(p.parts)==2:
                    if entry.file_size>2*1024*1024:return False
                    if record_name(json.loads(archive.read(entry).decode('utf-8-sig'))):evidence=True
                elif p.name==MARKER and len(p.parts)==2:
                    if entry.file_size>4096:return False
                    data=json.loads(archive.read(entry).decode('utf-8'))
                    if isinstance(data,dict) and data.get('generator')==GENERATOR:evidence=True
            return evidence and cad
    except (OSError,ValueError,RuntimeError,zipfile.BadZipFile,NotImplementedError):return False


def walk_files(base,folder):
    pending=[folder]
    while pending:
        parent=pending.pop()
        for p in sorted(parent.iterdir()):
            if not safe_path(base,p):continue
            if p.is_dir():pending.append(p)
            elif p.is_file():yield p


def fingerprint(path):
    s=path.stat();return (s.st_size,s.st_mtime_ns,s.st_ino)


def plan_cleanup(folder,kind='all'):
    if kind not in ('all','models','reports'):raise ValueError('Clean kind must be all/models/reports')
    base=output_root(folder);files=[];owners=set()
    def add(p,owner):
        files.append(dict(path=p,owner=owner,stamp=fingerprint(p)))
    for p in sorted(base.iterdir()):
        if not safe_path(base,p):continue
        if p.is_dir():
            model=owned_model(base,p);overall=p.name=='Overall_Review';report=p.name in REPORT_DIRS or overall
            if not model and not report:continue
            owners.add(p)
            candidates=list(walk_files(base,p))
            keep_evidence=kind=='models' and any(category(f.name)=='reports' for f in candidates)
            for f in candidates:
                cat=category(f.name)
                if cat is None:continue
                if cat=='models' and not model and not (overall and f.name in ('05_Geometry.json','05_Config.json')):continue
                if keep_evidence and f.name in EVIDENCE:continue
                # Do not treat an arbitrary nested directory as a CAD output store.
                rel=f.relative_to(p)
                allowed=REPORT_DIRS|{'Legacy_Reports'} if overall else {'Parts','CATParts','Subassemblies'}
                if len(rel.parts)>1 and rel.parts[0] not in allowed:continue
                if kind=='all' or cat==kind:add(f,p)
        elif p.is_file():
            if kind in ('all','reports') and p.name in REPORTS|SUMMARY:add(p,base)
            elif kind in ('all','models') and p.suffix.lower()=='.zip' and generated_zip(p):add(p,base)
    statuses=[]
    for status in (base/'BUILD_STATUS.json',base/'Overall_Review'/'BUILD_STATUS.json'):
        if kind in ('all','models') and safe_path(base,status) and status.is_file():
            data=read_json(status)
            if isinstance(data,dict):statuses.append(dict(path=status,data=data,stamp=fingerprint(status)))
    return dict(base=base,kind=kind,files=files,owners=owners,statuses=statuses)


def _local_record_product(base,record):
    if not record_name(record):return None
    p=Path(record['product'])
    if not p.is_absolute():return None
    try:
        rel=p.relative_to(base)
        if len(rel.parts)!=2 or not MODEL_NAME.fullmatch(rel.parts[0]):return None
        # A missing product is allowed here, but never a redirected parent.
        parent=p.parent
        if parent.exists() and not safe_path(base,parent):return None
        if p.exists() and not safe_path(base,p):return None
        if not p.resolve().is_relative_to(base):return None
        return p
    except (OSError,ValueError):return None


def execute_cleanup(plan,dry_run=False):
    base=plan['base'];groups=defaultdict(lambda:[0,0]);errors=[];deleted=[];failed_owners=set()
    for entry in plan['files']:
        label=entry['path'].relative_to(base).parts[0]
        groups[label][0]+=1;groups[label][1]+=entry['stamp'][0]
    print(('PREVIEW' if dry_run else 'CLEAN')+' '+str(base),flush=True)
    for label,(count,size) in sorted(groups.items()):print(f'  {label}: {count} files, {size/1024/1024:.2f} MiB',flush=True)
    if dry_run:
        for status in plan['statuses']:print('  '+str(status['path'].relative_to(base))+': prune deleted/missing local generated model records')
        print(f'PREVIEW ONLY: {len(plan["files"])} files; no files changed.',flush=True)
        return dict(deleted=[],errors=[],planned=len(plan['files']))
    # Verify the root again. There is deliberately no shutil.rmtree / recursive delete.
    if output_root(base)!=base:raise ValueError('Output root changed')
    for entry in sorted(plan['files'],key=lambda x:x['path'].name in EVIDENCE):
        p=entry['path'];owner=entry['owner']
        if owner in failed_owners and p.name in EVIDENCE:continue
        try:
            if not safe_path(base,p) or not p.is_file() or fingerprint(p)!=entry['stamp']:
                raise OSError('File changed or became a link after planning')
            p.unlink();deleted.append(p)
        except OSError as exc:
            failed_owners.add(owner);errors.append(f'{p}: {exc}')
    # Prune only empty parent directories of deleted files. Unknown files keep their folders alive.
    parents=set()
    for p in deleted:
        current=p.parent
        while current!=base and current.is_relative_to(base):parents.add(current);current=current.parent
    for p in sorted(parents,key=lambda x:len(x.parts),reverse=True):
        if safe_path(base,p) and p.is_dir():
            try:p.rmdir()
            except OSError:pass
    for item in plan['statuses']:
        status=item['path']
        try:
            if not safe_path(base,status) or fingerprint(status)!=item['stamp']:raise OSError('Status changed during cleanup')
            data=item['data'];kept={}
            for key,value in data.items():
                product=_local_record_product(base,value)
                if product is None or product.exists() or product.parent in failed_owners:kept[key]=value
            if kept!=data:
                if kept:status.write_text(json.dumps(kept,ensure_ascii=False,indent=2),encoding='utf-8')
                else:status.unlink();deleted.append(status)
        except OSError as exc:errors.append(f'{status}: {exc}')
    for error in errors:print('KEPT / ERROR '+error,flush=True)
    print(f'CLEAN COMPLETE: {len(deleted)} files removed; {len(errors)} errors. Source/config/unknown files preserved.',flush=True)
    return dict(deleted=deleted,errors=errors,planned=len(plan['files']))


def clean(folder,kind='all',dry_run=False):
    return execute_cleanup(plan_cleanup(folder,kind),dry_run)
