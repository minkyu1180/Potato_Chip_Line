"""Station 12 adapter for the supplied ten-line packaging machine.

Geometry is retained from 13_packaging_machine_10line.py; numbering, functional
groups, save locations and the line interface are integrated here. No COM on import.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import replace
from pathlib import Path
import hashlib
import html
import json
import math
import uuid
import packaging_machine as source

REVISION='S12-PACKAGING-STAGED-R20-2026-11-07'
NAME='12_Packaging_10Line'
ROOT=Path(__file__).resolve().parent


def configuration(overrides=None):
    if overrides is not None and not isinstance(overrides,dict):
        raise ValueError('Packaging config must be a JSON object')
    unknown=set(overrides or {})-set(source.DEFAULTS)
    if unknown:raise ValueError('Unknown packaging inputs: '+', '.join(sorted(unknown)))
    c={**source.DEFAULTS,**(overrides or {})}
    for key,value in c.items():
        values=value if isinstance(value,(list,tuple)) else [value]
        if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in values):
            raise ValueError('Packaging inputs must contain finite numbers: '+key)
    for key in ('conveyor_tail','conveyor_head'):
        if len(c[key])!=3:raise ValueError(key+' must contain X, Y, Z')
    for key in ('belt_width','roller_diameter','drive_pulley_diameter','belt_thickness',
                'platform_inner_radius','platform_outer_radius','platform_deck_z'):
        if c[key]<=0:raise ValueError(key+' must be positive')
    if c['platform_outer_radius']<=c['platform_inner_radius']:
        raise ValueError('Platform outer radius must exceed its inner radius')
    if c['conveyor_head'][0]<=c['conveyor_tail'][0] or c['conveyor_tail'][2]<=0:
        raise ValueError('Packaging infeed must run toward +X above the floor')
    if c['line_count']!=10:raise ValueError('This layout requires exactly 10 packaging lines')
    c['line_count']=10
    source.Model(c)  # Retain the source's ten-lane layout restrictions.
    return c


def geometry(config=None):
    model=source.Model(configuration(config)).build()
    # Keep geometry and shared masters; use large functional groups in the tree.
    labels={'01_InclinedConveyor':'Infeed Conveyor','02_CommonDistribution':'Distribution and Weighing',
            '02_IndependentNetWeigher':'Distribution and Weighing',
            '03_AnnularPlatform':'Access Platform','04_VFFSBagger':'Packaging Lines'}
    grouped=[]
    for o in model.occ:
        system=next((s for s in o.path if s in labels),None)
        if system is None:
            system=next((s for s in o.path if s.startswith(('01_','02_','03_','04_')) and s not in
                         ('01_Frame','01_Profile','02_Plate','03_Bracket','04_Fastener','02_Internal','03_ExternalControl')),o.path[0])
        top=labels.get(system,system)
        lane=next((s for s in o.path if s.startswith('Line_')),None)
        if lane:top='Packaging Lines' if system=='04_VFFSBagger' else 'Distribution and Weighing'
        kind={'01_Frame':'Structure','02_Internal':'Mechanisms','03_ExternalControl':'Controls'}[o.path[0]]
        path=(top,)+((lane,) if lane else ())+(kind,)
        grouped.append(replace(o,path=path))
    model.occ=grouped
    return model


def bounds(model):
    # Conservative per-master boxes, transformed analytically. Pockets only
    # remove material; no expensive tessellation of thousands of occurrences.
    boxes={}
    for name,spec in model.parts.items():
        pts=[]
        for f in spec.features:
            if f['op']=='pocket':continue
            if f['op']=='revolve':
                radius=max(p[0] for p in f['profile']);lo=min(p[1] for p in f['profile']);hi=max(p[1] for p in f['profile'])
                pts.extend((x,y,z) for x in (-radius,radius) for y in (-radius,radius) for z in (lo,hi))
            else:
                for loop in f['loops']:
                    if loop['type']=='circle':
                        cx,cy=loop['center'];r=loop['radius'];xy=[(cx+x*r,cy+y*r) for x in (-1,1) for y in (-1,1)]
                    elif loop['type']=='segments':
                        xy=[]
                        for seg in loop['segments']:
                            if seg['type']=='line':xy.extend((seg['p0'],seg['p1']))
                            else:
                                cx,cy=seg['center'];r=seg['radius'];xy.extend((cx+x*r,cy+y*r) for x in (-1,1) for y in (-1,1))
                    else:xy=loop['points']
                    m=source.pose(f['origin'],f['u'],f['v'],source.cross(f['u'],f['v']))
                    pts.extend(source.apply(m,(x,y,z)) for x,y in xy for z in (0,f['length']))
        lo=[min(p[i] for p in pts) for i in range(3)];hi=[max(p[i] for p in pts) for i in range(3)]
        boxes[name]=[(x,y,z) for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])]
    lo=[float('inf')]*3;hi=[-float('inf')]*3
    for o in model.occ:
        for p in boxes[o.part]:
            v=source.apply(o.matrix,p)
            lo=[min(lo[i],v[i]) for i in range(3)];hi=[max(hi[i],v[i]) for i in range(3)]
    return dict(min_mm=lo,max_mm=hi,size_mm=[hi[i]-lo[i] for i in range(3)],
                note='Conservative bounds of transformed part envelopes, not a CATIA clash check')


def metadata(model):
    c=model.cfg
    # Tail/head are roller centres in the supplied file. The transfer meets the
    # top of the tail pulley, not the roller axis.
    inlet=list(c['conveyor_tail']);inlet[2]+=c['roller_diameter']/2+c['belt_thickness']
    return dict(index=12,name=NAME,description='Independent ten-channel weighing and ten VFFS baggers',
                inlet=inlet,inlet_direction=[1,0,0],inlet_width_mm=c['belt_width'],
                outlet=None,outlets=[dict(line=f'Line_{i+1:02d}',point_mm=source.apply(model.line_pose(i),(0,-620,350))) for i in range(10)],
                engineering_inputs=c,geometry_bbox=bounds(model),generator_revision=20,
                build_strategy='Save and close each master; build saved Product groups bottom-up; open final root last',
                model_signature=hashlib.sha256((REVISION+json.dumps(c,sort_keys=True)).encode()).hexdigest(),
                product_structure='Infeed Conveyor / Distribution and Weighing / Access Platform / Packaging Lines',
                source_file='13_packaging_machine_10line.py',source_geometry_preserved=True)


def calculations(config=None,model=None,upstream_kg_h=None):
    model=model or geometry(config);c=model.cfg;meta=metadata(model);cap=model.capacity()
    counts=Counter(o.part for o in model.occ);target=cap['finished_product_kg_per_hour_at_target']
    actual=None if upstream_kg_h is None else min(upstream_kg_h,cap['scenario_finished_product_kg_per_hour'])
    return dict(index=12,revision=REVISION,inputs=c,geometry_metadata=meta,geometry_bbox=meta['geometry_bbox'],
                capacity=cap,normal_flow_kg_h=target,upstream_available_kg_h=upstream_kg_h,
                supply_limited_scenario_kg_h=actual,
                supply_limited_bags_min=None if actual is None else actual*1000/(60*c['nominal_fill_g']),
                installed_motor_kw=None,estimated_running_kw=None,dead_mass_kg=None,monthly_cost_krw=None,
                structural_calculation_pass=None,master_count=len(model.parts),component_count=len(model.occ),
                bom=[dict(name=p.name,quantity=counts[p.name],kind=p.kind,note=p.note) for p in model.parts.values()],
                warnings=['12번은 전달받은 개념 형상을 통합한 상태이며 자중·응력·구동 토크·전력은 미확정입니다.',
                          '원본의 프로파일·브라켓 구조를 유지했습니다. SUS304 용접 구조로 재설계한 기계로 표시하지 않습니다.'],
                input_sha256=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest())


def report_html(r):
    from review_layout import document,table,fmt
    c=r['inputs'];cap=r['capacity'];rows=[]
    rows.append('<h2>1. 크기와 구조</h2>'+table(['항목','내용'],[
        ('전체 외접치수 L×W×H',fmt(r['geometry_bbox']['size_mm'])+' mm'),
        ('작업대 외경 / 바닥 높이',fmt(c['platform_outer_radius']*2)+' / '+fmt(c['platform_deck_z'])+' mm'),
        ('투입 벨트 폭 / 투입점',fmt(c['belt_width'])+' mm / '+fmt(r['geometry_metadata']['inlet'])+' mm'),
        ('구성','공통 승강 벨트 → 분배기 → 독립 계량 10채널 → 전용 중공관 → 포장기 10대'),
        ('주 구조물','원본 프로파일·브라켓 구조 유지; 용접 사각관 전환은 이번 통합에 포함하지 않음')]))
    rows.append('<h2>2. 두께·하중·응력·안전한계</h2><p>기계 자중, 작업대 사람·적재 하중, 허용응력과 안전율은 <b>미확정</b>입니다. 원본의 형상 배치 검사를 구조 강도 검증으로 표시하지 않습니다. 재질별 질량·작업대 지지·접합부 계산은 후속 설계 항목입니다.</p>')
    rows.append('<h2>3. 한 시간 처리량과 속도</h2>'+table(['항목','값'],[
        ('한 봉 중량',fmt(c['nominal_fill_g'])+' g'),('목표',fmt(c['target_bags_per_min_per_line'])+' 봉/min/대 × 10대'),
        ('포장기 자체 목표',fmt(cap['theoretical_bags_per_min'])+' 봉/min · '+fmt(r['normal_flow_kg_h'])+' kg/h'),
        ('유효계수 가정 '+fmt(c['assumed_effective_factor']),fmt(cap['scenario_finished_product_kg_per_hour'])+' kg/h'),
        ('11번 공급량 가정(양념 포함)',fmt(r.get('upstream_available_kg_h'))+' kg/h'),
        ('공급량 제한 시나리오',fmt(r.get('supply_limited_scenario_kg_h'))+' kg/h · '+fmt(r.get('supply_limited_bags_min'))+' 봉/min')])+
        '<p>실측 생산능력이 아닙니다. 전 공정 중 최저 공급량, 계량 안정화, 실링·낙하 시간과 가동률이 전체 생산량을 제한합니다. 벨트 속도와 필요 토크는 원본에 확정값이 없습니다.</p>')
    rows.append('<h2>4. 모터 용량과 전기요금</h2><p>설비 전원 요구는 380 V 3상입니다. 구동모터·실링 히터·제어반·압축공기·질소 설비의 구매 사양이 없어 소비전력과 전기요금을 <b>미확정</b>으로 표시합니다.</p>')
    rows.append('<h2>5. 부품 종류·수량·가격</h2>'+table(['공유 CATPart 종류','반복 배치 수','구매 부품비'],[(r['master_count'],r['component_count'],'견적 필요')])+
        '<details><summary>부품 명세</summary>'+table(['부품','수량','분류'],[(p['name'],p['quantity'],p['kind']) for p in r['bom']])+'</details>')
    rows.append('<h2>6. 전체 제작 공임·보완 사항</h2><p>공임 견적 필요. 식품 접촉 재질, 프로파일의 세척성, 긴 낙하 경로의 칩 파손, 10개 계량 경로의 균등 공급과 인터록을 후속 검토합니다.</p><p>출처: 사용자가 전달한 13_packaging_machine_10line.py. 프로젝트 번호는 12번으로 변경했으며 원본 형상 치수는 유지했습니다.</p>')
    return document('12 감자칩 포장기 · 디자인 리뷰',''.join(rows)+'<p><a href="12_PKG_Calculations.json">전체 계산값 JSON</a></p>')


def write_report(folder=None,config=None,model=None,upstream_kg_h=None):
    folder=Path(folder or ROOT/'Overall_Review'/'12_PKG_Design_Review');folder.mkdir(parents=True,exist_ok=True)
    r=calculations(config,model,upstream_kg_h);page=folder/'12_PKG_Design_Review.html'
    (folder/'12_PKG_Calculations.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    page.write_text(report_html(r),encoding='utf-8')
    return page,r


def build(catia,base,rebuild=False,config=None,upstream_kg_h=None):
    import build_line as line
    model=geometry(config);meta=metadata(model)
    if not rebuild:
        found=line.existing_station(Path(base),meta,meta['model_signature'])
        if found:
            print('REUSE '+found['product'],flush=True)
            return line.open_document(catia,Path(found['product'])),found
    folder=line.new_folder(Path(base),NAME)
    write_report(folder,model=model,upstream_kg_h=upstream_kg_h)
    source.write_reports(model,folder)
    builder=source.CatiaBuilder(folder,app=catia,namespace='P12_'+uuid.uuid4().hex[:8]+'_')
    path=builder.build(model)
    meta.update(product=str(path.resolve()),build_status='complete',components=len(model.occ),unique_catparts=len(model.parts))
    (folder/'MODEL_INFO.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    line.update_status(Path(base),NAME,meta)
    print('SAVED '+str(path),flush=True)
    # The builder has already closed every temporary Part/Product document.
    # Only the completed root Product stays open for the line runner or user.
    return builder.root_doc,meta
