"""Concise station reviews and the portable 01-12 Overall_Review index."""
from __future__ import annotations
from collections import Counter,defaultdict
from pathlib import Path
import html
import json

REVISION='REVIEW-R19-2026-11-06'
STATIONS={1:('VBK','감자 투입 호퍼'),2:('SO','습식 나선 제석기'),3:('CRP','롤러 탈피기'),
 4:('MS','나이프 탈피기'),5:('CC','CC 감자 슬라이서'),6:('BL','연속 블랜처'),
 7:('VDW','진동 탈수기'),8:('AD','공기 건조기'),9:('FR','연속 튀김기'),
 10:('VDO','진동 탈유기'),11:('SD','양념 드럼'),12:('PKG','감자칩 포장기')}
CSS='''body{font:15px/1.6 "Malgun Gothic",sans-serif;color:#22343e;background:#eef2f3;margin:0}main{max-width:1120px;background:#fff;margin:24px auto;padding:32px}h1{font-size:27px}h2{font-size:20px;border-bottom:2px solid #dce7eb;padding-bottom:6px;margin-top:30px}table{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}th,td{border:1px solid #ccd9df;padding:8px;text-align:left;vertical-align:top}th{background:#edf3f5}a{color:#146184}.scroll{overflow:auto}.note{padding:12px;background:#fff2d7}details{margin:12px 0}summary{cursor:pointer;color:#146184}small{color:#526773}@media print{main{margin:0;padding:0}body{background:white}tr{break-inside:avoid}button{display:none}}'''

def root(base):
    p=Path(base);return p if p.name=='Overall_Review' else p/'Overall_Review'

def station_folder(base,index):return root(base)/f'{index:02d}_{STATIONS[index][0]}_Design_Review'
def status_path(base):return root(base)/'BUILD_STATUS.json'
def page_name(index):return '05_Slicer_Review.html' if index==5 else f'{index:02d}_{STATIONS[index][0]}_Design_Review.html'
def data_name(index):return f'{index:02d}_{STATIONS[index][0]}_Calculations.json'

def migrate_legacy(base):
    """Move only known loose generator outputs; leave model folders untouched."""
    import clean_outputs as clean
    base=clean.output_root(base);out=root(base)
    if out.exists() and not clean.safe_path(base,out):raise ValueError('Unsafe Overall_Review path')
    out.mkdir(exist_ok=True);moved=[]
    def checked_target(target):
        if not target.resolve().is_relative_to(out.resolve()):raise ValueError('Review target escapes Overall_Review')
        for node in (target,*target.parents):
            if node==base:break
            if node.exists() and clean.is_link(node):raise ValueError('Review destination contains a link')
        return target
    def move_file(source,target):
        if not clean.safe_path(base,source):return
        checked_target(target)
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if source.read_bytes()==target.read_bytes():source.unlink();return
            original=out/'Legacy_Reports'/source.parent.name/source.name;target=original;n=1
            while target.exists():target=original.with_name(original.stem+f'_{n}'+original.suffix);n+=1
            checked_target(target)
            target.parent.mkdir(parents=True,exist_ok=True)
        source.replace(target);moved.append(str(target))
    for folder in list(base.iterdir()):
        if folder.name not in clean.REPORT_DIRS or not folder.is_dir() or not clean.safe_path(base,folder):continue
        for p in list(folder.iterdir()):
            if p.is_file() and p.name in clean.REPORTS:move_file(p,out/folder.name/p.name)
        try:folder.rmdir()
        except OSError:pass
    for p in list(base.iterdir()):
        if not p.is_file() or not clean.safe_path(base,p):continue
        if p.name in ('05_11_Design_Review_Index.html','05_11_Review_Summary.json','01_11_Design_Review_Index.html','01_11_Review_Summary.json'):
            move_file(p,out/'Legacy_Reports'/p.name)
        elif p.name in clean.REPORTS or p.name in ('05_Geometry.json','05_Config.json'):
            i=next((i for i in STATIONS if p.name.startswith(f'{i:02d}_')),None)
            if i:move_file(p,station_folder(base,i)/p.name)
    old=base/'BUILD_STATUS.json';new=status_path(base)
    if old.is_file() and clean.safe_path(base,old):
        checked_target(new)
        if new.exists():
            a=json.loads(old.read_text(encoding='utf-8'));b=json.loads(new.read_text(encoding='utf-8'))
            new.write_text(json.dumps(dict(a,**b),ensure_ascii=False,indent=2),encoding='utf-8');old.unlink()
        else:move_file(old,new)
    for name in ('01_11_Design_Review_Index.html','01_11_Review_Summary.json'):
        p=out/name
        if p.is_file():move_file(p,out/'Legacy_Reports'/name)
    return moved
def fmt(value,dec=2):
    if value is None:return '미확정'
    if isinstance(value,bool):return '충족' if value else '재검토'
    if isinstance(value,(int,float)):return f'{value:,.{dec}f}'.rstrip('0').rstrip('.') if dec else f'{value:,.0f}'
    if isinstance(value,(list,tuple)):return ' × '.join(fmt(x) for x in value)
    return str(value)
def table(headers,rows):
    e=lambda x:html.escape(fmt(x))
    return '<div class="scroll"><table><tr>'+''.join('<th>'+e(x)+'</th>' for x in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+e(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</table></div>'
def document(title,body):
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+CSS+'</style><main><h1>'+html.escape(title)+'</h1>'+body+'</main></html>'
def pick(r,*keys):return next((r[k] for k in keys if k in r and r[k] is not None),None)

def summary(index,r):
    c=r['inputs'];size=pick(r,'geometry_bbox','bbox','bounds') or {}
    installed=r.get('installed_motor_kw')
    if index==1 and not r.get('review_unavailable'):installed=c['motor_kw']+c['outfeed_motor_kw']
    if index==2 and not r.get('review_unavailable'):installed=c['motor_kw']
    rate=pick(c,'energy_rate_krw_kwh','assumed_all_in_energy_krw_kwh','electric_rate_krw_kwh')
    running=pick(r,'estimated_running_kw','input_power_kw')
    if index==5:running=c.get('measured_input_kw')
    return dict(index=index,name=STATIONS[index][1],revision=r['revision'],size_mm=size.get('size_mm'),
        flow_kg_h=pick(r,'normal_flow_kg_h','target_kg_h') or c.get('target_kg_h'),
        flow_basis='포장기 자체 목표' if index==12 else ('튀김 후 칩' if index>=10 else '투입 감자'),
        dead_mass_kg=pick(r,'dead_mass_kg','total_machine_mass_kg'),
        installed_motor_kw=installed,running_kw=running,
        rated_input_kw=pick(r,'rated_load_input_kw','nameplate_input_kw','nameplate_input_envelope_kw'),
        hourly_cost_krw=None if running is None or rate is None else running*rate,
        monthly_cost_krw=pick(r,'monthly_cost_krw','month_cost_krw'),
        warnings=r.get('warnings',[]),input_sha256=r.get('input_sha256'),
        status=('선택 모델의 계산 자료 없음' if r.get('review_unavailable') else
                '원본 개념 모델 / 강도·전력 미확정' if index==12 else
                '조건부 계산 통과 / 구매·실측 미확정' if index==5 and r.get('structural_calculation_pass') else
                '재검토 항목 있음' if r.get('warnings') else '예비 계산 / 구매·실측 미확정 항목 있음'))

def _drives(index,r):
    c=r['inputs']
    if index==1:return [dict(name='투입 벨트',motor_kw=c['motor_kw'],output_rpm=r['drum_rpm'],required_torque_nm=r['design_torque_nm'],ratio=c['gear_ratio']),
        dict(name='배출 롤러',motor_kw=c['outfeed_motor_kw'],output_rpm=r['outfeed_rpm'],required_torque_nm=r['outfeed_torque_nm'],ratio=c['outfeed_gear_ratio'])]
    if index==2:
        q=r['nominal_drive'];return [dict(name='승강 나선',motor_kw=c['motor_kw'],output_rpm=q['rpm'],required_torque_nm=q['design_nm'],ratio=c['gear_ratio'])]
    if index in (3,4):
        result=[]
        for label,prefix in (('이송 나선','screw'),('탈피 구동','peeling')):
            q=min(r[prefix+'_cases'],key=lambda x:abs(x['rpm']-c[prefix+'_rpm']))
            result.append(dict(name=label,motor_kw=c[prefix+'_motor_kw'],output_rpm=q['rpm'],required_torque_nm=q['design_nm'],ratio=c[prefix+'_ratio']))
        return result
    return r.get('drives',[])

def compact_report(index,r):
    c=r['inputs'];s=summary(index,r);parts=[];dim=r.get('dimensions',{})
    frame=r.get('sections',r.get('frame_sections',{}))
    if not frame and index==2:frame={'기둥 B×t':(dim['leg_b'],dim['leg_t']),'가로보 B×t':(dim['beam_b'],dim['beam_t'])}
    if not frame and index in (3,4):frame={'기둥 B×t':dim['leg'],'가로보 B×t':dim['beam']}
    labels={'leg':'기둥','leg_mm':'기둥','cross':'횡보','crossbeam_mm':'횡보','rail':'레일','brace':'가새'}
    solid=index==1 and c.get('frame_type')=='solid'
    frame_text=' / '.join(labels.get(k,k.replace(' B×t',''))+': '+fmt((v[0],v[0]) if solid else (v[0],v[0],v[1]) if len(v)==2 else v)+' mm' for k,v in frame.items())
    dimensions=[]
    if index==1:dimensions=[('호퍼 총 용적',fmt(r['gross_volume_m3'])+' m³'),('통감자 벌크 밀도',fmt(r['bulk_density_kg_m3'])+' kg/m³')]
    elif index==2:dimensions=[('수조 내부 L×W×H',fmt(r['internal_tank_mm'])+' mm'),('수조 총 용적',fmt(r['gross_tank_m3'])+' m³')]
    elif index in (3,4):dimensions=[('공정 유효 체적',fmt(r['free_process_m3'])+' m³'),('정상/막힘 감자량',fmt(r['working_potato_kg'])+' / '+fmt(r['blocked_potato_kg'])+' kg')]
    else:
        dimensions=[(x['label'],fmt(x['value'])+' '+x['unit']) for x in r.get('details',[]) if any(t in x['label'] for t in ('내부','치수','용적','두께','폭','수위'))]
    parts.append('<h2>1. 크기와 구조</h2>'+table(['항목','설계 내용'],[
        ('전체 L×W×H',fmt(s['size_mm'])+' mm'),('주 구조물','SUS304 용접 '+('중실 사각봉' if solid else '사각관')),('부재 단면 '+('B×H' if solid else 'B×H×t'),frame_text),*dimensions]))
    inventory=pick(r,'working_potato_mass_kg','working_potato_kg','normal_product_kg')
    blocked=pick(r,'brim_potato_mass_kg','blocked_potato_kg','blocked_product_kg','dry_geometric_potato_capacity_kg')
    load=pick(r,'design_vertical_load_n','vertical_design_n','total_vertical_design_n')
    checks=r.get('checks',[]);ranked=sorted(checks,key=lambda q:q.get('utilization',0),reverse=True)
    def check_rows(items):return [(q['name'],fmt(q['demand'])+' '+q['unit'],fmt(q['limit'])+' '+q['unit'],fmt(q['utilization']*100,1)+'%',q['result']) for q in items]
    parts.append('<h2>2. 두께·하중·응력·안전한계</h2>'+table(['항목','값'],[
        ('여유 포함 기계 자중',fmt(s['dead_mass_kg'])+' kg'),('정상 / 막힘·최대 적재량',fmt(inventory)+' / '+fmt(blocked)+' kg'),
        ('수직 설계하중',fmt(None if load is None else load/1000)+' kN'),
        ('허용응력',fmt(pick(r,'material_allowable_mpa','allowable_mpa') or c.get('yield_mpa',205)/c.get('safety_factor',2))+' MPa')])+
        table(['주요 검토','계산값','한계','이용률','판정'],check_rows(ranked[:5]))+
        '<details><summary>전체 계산 조건과 검토 항목</summary>'+table(['검토','계산값','한계','이용률','판정'],check_rows(checks))+
        table(['항목','계산식·가정'],[(q['name'],q.get('basis','')) for q in checks])+'</details>')
    speeds=[]
    for key,label,unit in [('speed_m_min','벨트 속도','m/min'),('axial_speed_m_min','축 방향 이송 속도','m/min'),
        ('tank_inventory_minutes','수조 재고 기준 시간','min'),('residence_seconds','공정 체류시간','s'),('batch_minutes','작업 적재량 소진 시간','min')]:
        if key in r:speeds.append((label,fmt(r[key])+' '+unit))
    if index==2:speeds.append(('나선 회전수',fmt(c['screw_rpm'])+' rpm'))
    if index>=6:speeds.extend((q['label'],fmt(q['value'])+' '+q['unit']) for q in r.get('details',[]) if any(t in q['label'] for t in ('속도','회전','시간','충전','체류','재고')))
    parts.append('<h2>3. 한 시간 처리량과 속도</h2>'+table(['항목','값'],[
        ('운전 목표 / 물량 기준',fmt(s['flow_kg_h'])+' kg/h · '+s['flow_basis']),
        ('분당 처리량',fmt(None if s['flow_kg_h'] is None else s['flow_kg_h']/60)+' kg/min'),*speeds])+
        '<p>운전 목표와 기계의 이론상 최대 용량은 구분합니다. 공정별 탈피 손실·증발·흡유에 따라 질량이 바뀝니다.</p>')
    drives=_drives(index,r)
    parts.append('<h2>4. 모터 용량과 전기요금</h2>'+table(['구동','모터 kW','출력 rpm','요구 토크 N·m','감속비'],[
        (q['name'],q['motor_kw'],q['output_rpm'],q['required_torque_nm'],q['ratio']) for q in drives])+
        table(['항목','값'],[('전원','380 V 3상 / 60 Hz'),('모터 출력 합',fmt(s['installed_motor_kw'])+' kW'),
        ('예상 정상 전기입력',fmt(s['running_kw'])+' kW'),('정격 동시부하 입력 참고',fmt(s['rated_input_kw'])+' kW'),
        ('가정 단가 기준 시간당 에너지비',fmt(s['hourly_cost_krw'],0)+' 원/h'),('월 전기비용',fmt(s['monthly_cost_krw'],0)+' 원')])+
        ''.join('<p>'+html.escape(x)+'</p>' for x in r.get('thermal_notes',[]))+
        '<p>전력·요금은 입력 가정에 따른 예비값입니다. 히터·팬·펌프 전력은 모터 출력 합과 구분하며 월 비용에는 기동·기본요금 가정이 포함될 수 있습니다.</p>')
    groups=defaultdict(lambda:[0,0.])
    for q in r.get('bom',[]):
        group=q.get('group','기타');groups[group][0]+=1;groups[group][1]+=q.get('mass_kg',0)
    parts.append('<h2>5. 부품 종류·수량·가격</h2>'+table(['기능 그룹','모델 구성 개수','형상 질량 kg'],[(g,n,round(w,2)) for g,(n,w) in groups.items()])+
        '<p>완제품 구매 단위와 모델 인스턴스 수는 다릅니다. 동일 규격 부품 단가가 입력되지 않아 전체 부품비는 <b>미확정</b>입니다.</p>'+
        '<details><summary>전체 모델 질량 명세</summary>'+table(['부품','그룹','kg'],[(q['name'],q.get('group',''),q.get('mass_kg')) for q in r.get('bom',[])])+'</details>')
    parts.append('<h2>6. 전체 제작 공임·보완 사항</h2><p>전체 제작 공임: <b>견적 필요</b>. 사각관 절단·용접·마감·산세/부동태화·구매품 조립을 견적 범위에 포함합니다.</p>'+
        ''.join('<p>'+html.escape(x)+'</p>' for x in r.get('pending',[])[:4])+
        '<p>상온 예비 강도 계산이며 용접 피로·위생 마감·구매품 치수·실제 처리 성능은 별도 확인 항목입니다.</p>')
    warning='<div class="note">'+ '<br>'.join(html.escape(str(x)) for x in r.get('warnings',[]))+'</div>' if r.get('warnings') else ''
    import importlib
    module='station1_design' if index==1 else 'station2_design' if index==2 else 'peeler_design' if index in (3,4) else 'finishing_design'
    sources=getattr(importlib.import_module(module),'SOURCES',[])
    source_html='<details><summary>자료 출처와 적용 범위</summary>'+''.join('<p><a href="'+html.escape(url,quote=True)+'">'+html.escape(title)+'</a> · '+html.escape(note)+'</p>' for _,title,url,note in sources)+'</details>'
    return document(f'{index:02d} {STATIONS[index][1]} · 디자인 리뷰','<p>'+html.escape(r['revision'])+' · '+REVISION+'</p>'+warning+''.join(parts)+source_html+
        '<p><a href="'+data_name(index)+'">전체 계산값 JSON</a> · 실행·폴더 안내는 별도 README를 참조하세요.</p>')

def write_index(base):
    out=root(base);out.mkdir(parents=True,exist_ok=True);records=[];rows=[]
    for i,(code,label) in STATIONS.items():
        folder=station_folder(out,i);data=folder/data_name(i);page=folder/page_name(i)
        if not data.is_file() or not page.is_file():
            rows.append(f'<tr><td>{i:02d} {html.escape(label)}</td><td colspan="6">아직 생성되지 않음</td></tr>');continue
        r=json.loads(data.read_text(encoding='utf-8'));s=summary(i,r);records.append(s)
        href=page.relative_to(out).as_posix()
        vals=[fmt(s['size_mm']),fmt(s['flow_kg_h'])+' / '+s['flow_basis'],fmt(s['dead_mass_kg']),fmt(s['installed_motor_kw']),fmt(s['running_kw']),s['status']]
        rows.append(f'<tr><td><a href="{href}">{i:02d} {html.escape(label)}</a></td>'+''.join('<td>'+html.escape(v)+'</td>' for v in vals)+'</tr>')
    data=dict(revision=REVISION,complete=len(records)==12,stations=records,
        note='개별 설계 운전점의 비교표. 공정별 목표 유량과 포장기 자체 목표는 다르며, 5·12번 실제 전기입력 미확정으로 전체 소비전력/비용을 확정하지 않음.')
    (out/'01_12_Review_Summary.json').write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    headers=('기계 / 개별 리뷰','L×W×H mm','유량 kg/h / 기준','자중 kg','모터 kW','정상 입력 kW','검토 상태')
    body='<p>1~12번 전체 공정 · '+REVISION+'</p><div class="scroll"><table><tr>'+''.join('<th>'+x+'</th>' for x in headers)+'</tr>'+''.join(rows)+'</table></div>'
    body+='<p class="note">'+html.escape(data['note'])+'</p><p><a href="05_to_06_Connection_Concept.html">5→6번 연결 설계</a> · <a href="01_12_Review_Summary.json">전체 요약 JSON</a> · <a href="README.md">사용 안내</a></p>'
    body+='<p>4번 제외 조립: <code>py build_line.py --assemble-existing --exclude-stage 4</code>. 조립 순서는 1→2→3→5→6→7→8→9→10→11→12입니다. 아래 목록은 보관 중인 개별 기계 리뷰이며, 4번 리뷰가 있어도 제외 조립에 포함된다는 뜻은 아닙니다.</p>'
    if (out/'01_12_Assembly_Layout.html').is_file():body+='<p><a href="01_12_Assembly_Layout.html">마지막 전체 조립의 배치와 참조 파일</a></p>'
    target=out/'01_12_Design_Review_Index.html';target.write_text(document('감자칩 생산 라인 · 전체 디자인 리뷰',body),encoding='utf-8')
    code=Path(__file__).resolve().parent
    source=code/'README'/'README_RUN_01_12.md'
    if not source.is_file():source=code/'README_RUN_01_12.md'
    if source.is_file():(out/'README.md').write_text(source.read_text(encoding='utf-8'),encoding='utf-8')
    write_connection_concept(out)
    return target

def write_connection_concept(out,design=None):
    from transfer_05_06 import design_data
    data=dict(design or design_data(),geometry_implemented=True,catia_validation_performed=False,
              report_basis='Selected assembly ports' if design else 'Source defaults; not proof of an existing CAD build')
    body='<p>R22 코드가 Transfer_05_06.CATProduct를 생성합니다. 받이 슈트 → 낮은 수평 벨트 → 연결 슈트 → 경사 벨트 → 6번 투입 슈트 순서입니다. 5번은 높이지 않고, 6번 이후 기계는 5번 기준 −Y 방향으로 90° 돌립니다.</p>'
    body+=table(['항목','설계 치수 / 동작'],[
        ('하향 배출 높이',fmt(data['outlet_z_mm'])+' mm; 개방된 사각 받이 입구 500×500 mm'),
        ('받이 벨트',fmt(data['receiver_width_mm'])+' mm 폭 × 1,300 mm 축간 거리 / 상면 Z150 mm'),
        ('하부 보 통과','가이드 상단 Z220 mm / 기존 보 하단 Z250 mm / 명목 여유 30 mm'),
        ('기둥 통과','CC X119 기둥의 내측면 X159 / 받이 레일 외측 X171 / 명목 여유 12 mm'),
        ('기존 발판 통과','레일 상단 Z70 / CC 발판 하단 Z88 / 명목 여유 18 mm'),
        ('상승 구간',f"Z140 → Z{fmt(data['incline_end_mm'][2])} mm / 수평 {fmt(data['incline_horizontal_run_mm'])} mm / 경사 {fmt(data['incline_angle_deg'])}°"),
        ('경사 벨트 폭',fmt(data['incline_width_mm'])+' mm; 15 mm 이송 리브, 연속 측면 가이드'),
        ('설치 길이','배출 중심에서 6번 투입점까지 '+fmt(data['outlet_mm'][0])+' mm, 5번 −Y 방향'),
        ('프레임 / 받이','SUS304 용접 사각관, 물받이·배수 구멍, 개별 모터 받침과 지면 지지'),
        ('벨트','슬라이스가 빠지지 않는 연속 벨트 표현. 실제 식품 접촉 재질·구매 규격은 선정 필요')])
    body+='<p>위 여유는 현재 CC 프레임의 코드 치수를 기준으로 한 배치값입니다. 다른 형상의 5번 모델에는 그대로 적용할 수 없습니다. 저상 받이의 세척 접근성, 낙하에 따른 슬라이스 손상, 처리량·구동부 사양은 후속 상세 설계 항목입니다. CATIA 실행 및 간섭 검증은 수행하지 않았습니다.</p>'
    body+='<h2>4번 제외 조립</h2><p><code>py build_line.py --assemble-existing --exclude-stage 4</code>는 기존 1·2·3·5~12번을 재사용하고 Transfer_03_05와 Transfer_05_06을 생성합니다. 결과는 <code>Potato_Line_01_12_No04</code> 폴더에 저장되며 기존 4번 파일은 보존합니다. 새로 만들 때는 <code>py build_line.py --exclude-stage 4</code>를 사용합니다.</p>'
    body+='<p>파일명의 Concept는 기존 링크 호환을 위해 유지합니다. 이 문서는 생성 코드의 설계 설명이며 저장된 CATIA 모델의 검증 완료 보고서가 아닙니다.</p>'
    (out/'05_to_06_Connection_Concept.html').write_text(document('5번 슬라이서 → 6번 블랜처 · 연결 설계 R22',body),encoding='utf-8')
    (out/'05_to_06_Connection_Concept.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
