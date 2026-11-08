"""CC R16 welded square-tube Korean review; execute separately AFTER saving/building the model.

This module never opens CATIA. No verification is run on import.
Public rates are evidence; unpublished shop hours/quotations are NOT invented.
Run: py slicer_review.py --output-dir Review
Optional --cost-input FILE supplies evidenced procurement and labor entries.
"""
from __future__ import annotations
import argparse,collections,csv,html,json,math
from pathlib import Path
import slicer_design as d

SOURCES={
 'ccdl':('Urschel CC-DL 외형도·사양, 2026-02',
    'https://www.urschel.com/wp-content/uploads/2024/03/fact-sheet-model-cc-dl-english.pdf'),
 'potato':('Urschel 감자용 Model CC, 2020-11',
    'https://www.urschel.com/wp-content/uploads/2024/03/brochure-model-cc-potato-english.pdf'),
 'manual':('Urschel L2355/L2533 매뉴얼 §6.9–6.10, 제조사 문서의 공개 사본',
    'https://www.scribd.com/document/745038859/Urschel-CC-manual-English-2355-adndm-2533-ches'),
 'kbiz':('중소기업중앙회 2026년 상반기 제조노임 원문, 7월 적용',
    'https://www.kbiz.or.kr/ko/contents/bbs/view.do?mnSeq=325&seq=163372&topFixYn=Y'),
 'wage_copy':('동일 제조노임 보고서 PDF 첨부본','https://psm0801.tistory.com/913'),
 'mill':('강원메이커스페이스 NSM-A 범용밀링 이용료',
    'https://www.stbc.or.kr/bbs/board.php?bo_table=2_1&wr_id=114'),
 'lathe':('강원메이커스페이스 HL-380 범용선반 이용료',
    'https://www.stbc.or.kr/bbs/board.php?bo_table=2_1&wr_id=112'),
 'cnc':('강원메이커스페이스 C22U 이용료·가공 범위',
    'https://www.stbc.or.kr/bbs/board.php?bo_table=2_1&wr_id=122'),
 'angle':('SUS304 50×50×5 앵글 1 m, 2026-11-04 확인',
    'https://item.gmarket.co.kr/Item?goodsCode=3043845546'),
 'nut':('SUS304 M8 너트 100개, 2026-11-04 확인',
    'https://www.coupang.com/vp/products/7121137562'),
 'motor_comparison':('신용모터 STM 0.2 kW 삼상 기어드모터 일반형 가격',
    'https://sym.or.kr/product/detail.html?cate_no=42&display_group=1&product_no=3082'),
 'steel':('Outokumpu Core 304 재료 자료',
    'https://www.outokumpu.com/-/media/files/products/core/outokumpu-core-range-datasheet.pdf'),
}
# KBIZ original report, printed pp.20–21. KRW / eight-hour working day.
LABOR={
 '레이저광선원':119138,'벤딩머쉰조작원':104512,'선반기조작원':123489,
 '드릴링기조작원':101336,'머쉬닝센터조작원':119851,
 '기타공작기계조작원':124222,'연삭기및연마기조작원':116506,
 '경기계조립원':129158,'전기기계조립원':116674,
 '부품조립원':110036,'제품검사및조정원':109491,'용접원':124879,
}
# Each operation needs actual/quoted person-hours and its evidence.
# The official daily wage is a direct-wage basis, NOT a contractor's billing rate.
OPERATIONS=[
 ('cut','소재 절단·네스팅','레이저광선원'),
 ('bend','판재 절곡·호퍼 성형','벤딩머쉰조작원'),
 ('weld','사각관·거싯·슈트 TIG 용접, 끝막음','용접원'),
 ('turn','축·풀리·베어링 하우징 선삭','선반기조작원'),
 ('drill','탈착 장착판·기계부 체결 구멍','드릴링기조작원'),
 ('mill','칼날 시트·헤드·장착면 가공','머쉬닝센터조작원'),
 ('finish','디버링·용접부 연마·세척','연삭기및연마기조작원'),
 ('assemble','프레임·절단부·컨베이어 조립','경기계조립원'),
 ('electrical','제어반·모터 배선','전기기계조립원'),
 ('adjust','제작 후 간극·회전·절단 조정','제품검사및조정원'),
]
# Fill with supplier evidence, not arbitrary example numbers.
# parts: {master: {unit_price_krw: ..., source: ..., scope: "complete_part"}}
# labor: {operation_id: {person_hours: ..., source: ...}}
# fabrication_quote: {amount_krw: ..., source: ..., scope: "all_fabrication"}
# A full fabrication quote is NEVER added again to its included hourly operations.
COST_INPUTS=dict(parts={},labor={},fabrication_quote=None)

def section_properties(points):
    """Area/centroid and least principal inertia, not bounding-box inertia."""
    cross=[a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])]
    area=sum(cross)/2
    cx=sum((a[0]+b[0])*q for a,b,q in zip(points,points[1:]+points[:1],cross))/(6*area)
    cy=sum((a[1]+b[1])*q for a,b,q in zip(points,points[1:]+points[:1],cross))/(6*area)
    ix=sum((a[1]**2+a[1]*b[1]+b[1]**2)*q for a,b,q in zip(points,points[1:]+points[:1],cross))/12-area*cy**2
    iy=sum((a[0]**2+a[0]*b[0]+b[0]**2)*q for a,b,q in zip(points,points[1:]+points[:1],cross))/12-area*cx**2
    ixy=sum((2*a[0]*a[1]+a[0]*b[1]+b[0]*a[1]+2*b[0]*b[1])*q for a,b,q in zip(points,points[1:]+points[:1],cross))/24-area*cx*cy
    imin=(ix+iy)/2-math.sqrt(((ix-iy)/2)**2+ixy**2)
    radius=max(math.hypot(x-cx,y-cy) for x,y in points)
    return dict(area_mm2=area,centroid_mm=(cx,cy),I_min_mm4=imin,Z_conservative_mm3=imin/radius)


def purchased_reference(p):
    return any(t in p['material'].lower() for t in ('purchased','pending','envelope','supplier','oem'))
def mass(p):return d.part_volume(p)*p['density_kg_m3']/1e9
def perimeter(points):return sum(math.dist(a,b) for a,b in zip(points,points[1:]+points[:1]))
def frac_cone(r0,r1,h):return math.pi*h*(r0*r0+r0*r1+r1*r1)/3

def labor_cost(inputs):
    rows=[];subtotal=0.;missing=[]
    for ident,title,trade in OPERATIONS:
        entry=inputs.get('labor',{}).get(ident,{})
        hours=entry.get('person_hours');evidence=entry.get('source','')
        if hours is not None:
            if isinstance(hours,bool) or not isinstance(hours,(int,float)) or not math.isfinite(hours) or hours<0 or not evidence:
                raise ValueError(ident+': nonnegative person_hours and source required')
        cost=None if hours is None else hours*LABOR[trade]/8
        if cost is None:missing.append(title)
        else:subtotal+=cost
        rows.append(dict(id=ident,operation=title,trade=trade,hourly_wage_krw=LABOR[trade]/8,
                         person_hours=hours,source=evidence,direct_wage_krw=cost))
    quote=inputs.get('fabrication_quote')
    total=None
    if quote is not None:
        value=quote.get('amount_krw')
        if not quote.get('source') or quote.get('scope')!='all_fabrication' or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
            raise ValueError('Fabrication quotation needs amount, source and all_fabrication scope')
        total=value
    return dict(rows=rows,known_direct_wage_krw=subtotal,
        complete_direct_wage_krw=None if missing else subtotal,missing=missing,
        all_fabrication_quote_krw=total,quote=quote,
        reference_machine_rates_krw_h={'범용밀링 장비만':5000,'범용선반 장비만':5000,'C22U 장비만':40000})

def tube_section(c,b,h,t):
    """Nominal sharp-corner RHS, reduced 10% for unspecified corner/tolerance data."""
    f=c['section_property_factor']
    area=(b*h-(b-2*t)*(h-2*t))*f
    ix=(b*h**3-(b-2*t)*(h-2*t)**3)/12*f
    iy=(h*b**3-(h-2*t)*(b-2*t)**3)/12*f
    return dict(area_mm2=area,I_min_mm4=min(ix,iy),
        Z_conservative_mm3=min(ix/(h/2),iy/(b/2)),
        shear_area_mm2=2*t*(min(b,h)-2*t)*f,
        width_mm=b,height_mm=h,wall_mm=t,property_factor=f)

def weld_case(c,N,V,M,b=80.,h=80.):
    # Full rectangular continuous fillet group. No credit for the knee gusset.
    a=.707*c['weld_leg_mm'];Aw=a*2*(b+h)
    Zw=a*(b*h+h*h/3)
    normal=abs(N)/Aw+abs(M)/Zw;shear=abs(V)/Aw
    vm=math.sqrt(normal**2+3*shear**2)
    # Deliberately limited to 80% of base-metal design stress, not a qualified WPS.
    allowable=.8*c['yield_mpa']/c['safety_factor']
    return dict(leg_mm=c['weld_leg_mm'],throat_mm=a,effective_area_mm2=Aw,
        normal_mpa=normal,shear_mpa=shear,von_mises_mpa=vm,allowable_mpa=allowable,
        load_multiplier_limit=allowable/vm if vm else None,
        passes_screen=vm<=allowable)

def leg_case(c,mass_kg,length,wall,extra_front_reaction_kg=0.):
    p=tube_section(c,80,80,wall)
    # Extra chute reaction is per FRONT leg; back-leg uplift is treated separately.
    N=(mass_kg*c['leg_load_share']+extra_front_reaction_kg)*9.80665*c['dynamic_factor']
    V=mass_kg*9.80665*c['lateral_accel_g']*c['leg_load_share']
    axial=N/p['area_mm2'];bending=V*length/p['Z_conservative_mm3']
    tau=V/p['shear_area_mm2']
    euler=math.pi**2*c['E_mpa']*p['I_min_mm4']/(2*length)**2
    # Rankine screening combines yielding and elastic buckling; avoids using
    # an unrealistically large Euler capacity for these short stocky columns.
    rankine=1/(1/(c['yield_mpa']*p['area_mm2'])+1/euler)
    flat=80-2*wall
    local=4*math.pi**2*c['E_mpa']/(12*(1-.3**2))*(wall/flat)**2
    allowable=min(c['yield_mpa'],local)/c['safety_factor']
    vm=math.sqrt((axial+bending)**2+3*tau*tau)
    weld=weld_case(c,N,V,V*length)
    multiplier=min(allowable/vm,rankine/c['safety_factor']/N,weld['load_multiplier_limit'])
    return dict(wall_mm=wall,N_n=N,V_n=V,axial_mpa=axial,bending_mpa=bending,
        compression_mpa=axial+bending,tension_mpa=max(0,bending-axial),shear_mpa=tau,
        von_mises_mpa=vm,allowable_mpa=allowable,euler_n=euler,
        rankine_n=rankine,allowable_buckling_n=rankine/c['safety_factor'],
        local_plate_buckling_mpa=local,yield_safety_factor=c['yield_mpa']/vm,
        load_multiplier_limit=multiplier,remaining_margin_percent=(multiplier-1)*100,
        passes_screen=multiplier>=1,section=p,weld=weld)

def beam_case(c,name,mass_kg,span,b=80.,h=80.,t=4.,cantilever=False,share=1.):
    p=tube_section(c,b,h,t);P=mass_kg*9.80665*c['dynamic_factor']*share
    # All allocated mass concentrated at the worst point; includes self-weight
    # through the assembly mass, rather than adding it a second time.
    M=P*span if cantilever else P*span/4
    V=P if cantilever else P/2
    delta=P*span**3/((3 if cantilever else 48)*c['E_mpa']*p['I_min_mm4'])
    sigma=M/p['Z_conservative_mm3'];tau=V/p['shear_area_mm2']
    vm=math.sqrt(sigma*sigma+3*tau*tau);allowable=c['yield_mpa']/c['safety_factor']
    delta_allow=span/(180 if cantilever else 300)
    w=weld_case(c,0,V,M if cantilever else 0,b,h)
    mult=min(allowable/vm,delta_allow/delta,w['load_multiplier_limit'])
    return dict(name=name,section_mm=[b,h,t],span_mm=span,mass_basis_kg=mass_kg,
        allocated_share=share,load_n=P,moment_nmm=M,von_mises_mpa=vm,
        allowable_mpa=allowable,deflection_mm=delta,allowable_deflection_mm=delta_allow,
        load_multiplier_limit=mult,passes_screen=mult>=1,weld=w,
        support_condition='cantilever, end point load' if cantilever else 'simply supported, central point load')

def floor_case(c,rho):
    # One-mm-wide strip, deliberately 200 mm cantilever; actual outlet lip is 119 mm.
    L=200.;t=3.;q=rho*9.80665*(c['transition_bed_height_mm']/1000)*c['dynamic_factor']/1e6
    stress=(q*L*L/2)/(t*t/6)
    delta=q*L**4/(8*c['E_mpa']*(t**3/12))
    return dict(thickness_mm=t,screened_overhang_mm=L,actual_outlet_overhang_mm=119.,
        pressure_n_mm2=q,stress_mpa=stress,allowable_mpa=c['yield_mpa']/c['safety_factor'],
        deflection_mm=delta,allowable_deflection_mm=L/250,
        passes_screen=stress<=c['yield_mpa']/c['safety_factor'] and delta<=L/250)

def calculations(config=None,cost_inputs=None):
    m=d.geometry(config);c=m.c;costs=COST_INPUTS if cost_inputs is None else cost_inputs
    groups=collections.OrderedDict();known=0.;feed_mass=0.;core_stand_mass=0.
    group_mass=collections.defaultdict(float)
    for p in m.parts:
        kg=mass(p);ref=purchased_reference(p)
        if not ref:known+=kg
        if not ref:group_mass[p['support_group']]+=kg
        if p['support_group']=='feeder' and not ref:feed_mass+=kg
        if p['family'].startswith(('CC_Stand','Chamber_Post','Chamber_Support')) and not ref:core_stand_mass+=kg
        key=(p['category'],p['part_type'],p['family'],p['master'])
        row=groups.setdefault(key,dict(category=key[0],type=key[1],family=key[2],master=key[3],
             quantity=0,material=p['material'],model_mass_kg_each=None if ref else kg,
             unit_price_krw=None,extended_krw=None,source='',status='동일 규격 견적 필요'))
        row['quantity']+=1
    bom=list(groups.values());priced=0.;missing_parts=[]
    for row in bom:
        q=costs.get('parts',{}).get(row['master'])
        if q:
            value=q.get('unit_price_krw')
            if not q.get('source') or q.get('scope')!='complete_part' or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                raise ValueError(row['master']+': complete_part unit price and source required')
            row.update(unit_price_krw=value,extended_krw=value*row['quantity'],source=q['source'],status='근거 입력 단가')
            priced+=row['extended_krw']
        else:missing_parts.append(row['master'])
    rho=c['potato_density_kg_m3']*c['packing_fraction']
    kg_per_m=rho*.8*(c['product_height_mm']/1000)*c['width_loading_fraction']
    speed=c['target_kg_h']/60/kg_per_m
    belt_full=rho*.8*.098*1.2
    belt_normal=kg_per_m*1.2
    hopper_full=frac_cone(.115,.2325,.218)*rho
    head_full=math.pi*(.245**2-.06**2)*.160*rho
    core_food=hopper_full+head_full
    transition_food=rho*((.8+.3)/2*.666)*(c['transition_bed_height_mm']/1000)
    # Unknown buying weights are never silently omitted. These are design
    # allowances, NOT measured masses or supplier specifications.
    # If only a combined buying weight is given, put the WHOLE amount on EACH
    # stand for conservative sizing until its actual distribution is known.
    core_purchase=c['purchased_mass_kg'] if c['purchased_mass_kg'] is not None else c['core_purchase_allowance_kg']
    feed_purchase=c['purchased_mass_kg'] if c['purchased_mass_kg'] is not None else c['feed_purchase_allowance_kg']
    core_machine=max(c['core_machine_design_min_kg'],group_mass['core']+core_purchase,
                     d.CORE_REFERENCE_MASS_KG+core_stand_mass)
    feed_machine=max(c['feed_machine_design_min_kg'],group_mass['feeder']+feed_purchase)
    transition_machine=max(c['transition_machine_design_min_kg'],group_mass['transition'])
    core_load=core_machine+core_food;feed_base_load=feed_machine+belt_full
    transition_load=transition_machine+transition_food
    feed_load=feed_base_load+transition_load
    actual=None if c['purchased_mass_kg'] is None else known+c['purchased_mass_kg']
    # Worst chute resultant at X=300: 700 mm beyond the front legs at X=-400.
    # Extra FRONT reaction = W*(1+700/1050)/2 per leg. Full chute mass is
    # additionally included in lateral loading, but is not added twice vertically.
    front_extra=transition_load*(1+700/1050)/2
    supports=[]
    for label,load,length,extra in [
        ('본체 다리 4개',core_load,390.,0.),
        ('투입 컨베이어 앞다리 2개: 돌출 슈트 포함',feed_load,1350.,
         front_extra-transition_load*c['leg_load_share'])]:
        cases=[leg_case(c,load,length,t,extra) for t in (3.,4.,5.,6.)]
        passing=[x['wall_mm'] for x in cases if x['passes_screen']]
        supports.append(dict(name=label,mass_basis_kg=load,leg_length_mm=length,
            extra_front_reaction_kg=extra,selected=leg_case(c,load,length,c['leg_wall_mm'],extra),
            cases=cases,screened_minimum_wall_mm=min(passing) if passing else None))
    beams=[
        beam_case(c,'본체 세로 보',core_load,1279.,t=c['leg_wall_mm'],share=.60),
        beam_case(c,'본체 절단실 가로 보',core_load,840.,share=.75),
        beam_case(c,'컨베이어 세로 보',feed_load,970.,t=c['leg_wall_mm'],share=.60),
        beam_case(c,'슈트 돌출 팔 1개 (거싯 효과 미반영)',transition_load,500.,cantilever=True,share=.75),
        beam_case(c,'슈트 가로 보',transition_load,880.),
        beam_case(c,'슈트 경사 레일 1개',transition_load,350.,50.,50.,3.,True,.75),
        beam_case(c,'슈트 받침 가로 부재',transition_load,310.,50.,50.,3.,False,.50),
    ]
    # Back-leg contact depends on actual mass distribution. Required stabilising
    # moment is reported; a guessed centre of gravity is not used to certify tipping.
    overturning=transition_load*9.80665*.700*c['dynamic_factor']
    floor=floor_case(c,rho)
    tube_groups=collections.OrderedDict()
    for p in m.parts:
        if p['kind']!='tube':continue
        key=(p['family'],p['master'])
        row=tube_groups.setdefault(key,dict(family=p['family'],master=p['master'],
            section_mm=f"{p['width_mm']:g} x {p['height_mm']:g} x {p['wall_mm']:g}",
            cut_length_mm=p['depth'],quantity=0,total_length_m=0.))
        row['quantity']+=1;row['total_length_m']+=p['depth']/1000
    weld_groups=collections.OrderedDict()
    for w in m.welds:
        key=(w['family'],w['leg_mm'],w['process'])
        row=weld_groups.setdefault(key,dict(family=key[0],leg_mm=key[1],process=key[2],
            joints=0,total_length_m=0.,filler=w['filler']))
        row['joints']+=1;row['total_length_m']+=w['length_mm']/1000
    pulley_rpm=speed/(math.pi*.100);omega=math.tau*c['impeller_rpm']/60
    available_torque=c['knife_motor_kw']*1000*c['drive_efficiency']/omega
    cutforce=c['cutting_force_total_n']
    cutradius=(c['head_guide_radius_mm']-c['slice_mm'])/1000
    required_cut_kw=None if cutforce is None else cutforce*cutradius*omega*c['service_factor']/1000/c['drive_efficiency']
    feed_moving=belt_full+sum(mass(p) for p in m.parts if p['family']=='Feed_Endless_Belt_800')
    v=speed/60
    pull=c['conveyor_friction']*feed_moving*9.80665+c['conveyor_extra_pull_n']+feed_moving*v/c['start_seconds']
    feed_torque=pull*.05*c['service_factor']
    feed_power=pull*v*c['service_factor']/1000/c['conveyor_efficiency']
    # Low-speed induction-motor torque derating is explicit, pending actual motor curve.
    output_torque=c['conveyor_motor_kw']*9550/c['motor_base_rpm']*c['conveyor_ratio']*c['conveyor_efficiency']*.50
    rated_input=c['knife_motor_kw']/c['motor_efficiency']+c['conveyor_motor_kw']/c['conveyor_motor_efficiency']+c['control_kw']
    actual_input=c['measured_input_kw'];rate=c['electric_rate_krw_kwh']
    actual_cost=None if actual_input is None or rate is None else actual_input*rate
    rated_cost=None if rate is None else rated_input*rate
    # Geometric quantities for a quote; no invented minutes per hole or days per machine.
    fabricated=[p for p in m.parts if not purchased_reference(p) and p['part_type'] not in ('Fastener','Foot')]
    poly=[p for p in fabricated if p['kind']=='poly' and not p.get('single_closed_profile')]
    q=dict(profile_pieces=sum(p['kind']=='tube' for p in m.parts),
        profile_length_m=sum(p['depth']/1000 for p in m.parts if p['kind']=='tube'),
        welded_joints=len(m.welds),weld_length_m=sum(w['length_mm'] for w in m.welds)/1000,
        end_caps=sum(p['family'].endswith('_End_Cap') for p in m.parts),
        gussets=sum('Gusset' in p['family'] for p in m.parts),
        plate_pieces=len(poly),contour_length_m=sum(perimeter(p['points'])+sum(perimeter(x) for x in p.get('loops',[])) for p in poly)/1000,
        drill_holes=sum(len(p.get('holes',[]))+len(p.get('drills',[])) for p in fabricated),
        turned_parts=sum(p['kind']=='circle' for p in fabricated),
        formed_cones=sum(p['kind']=='revolve' for p in m.parts),
        bolted_joints=sum(p['kind']=='bolt' for p in m.parts),knife_stations=8,motors=2)
    # Exact angle stock application only. Each 1m bar yields floor(1000/53)=18 blanks.
    angle_parts=[p for p in m.parts if p['kind']=='poly' and p.get('points')==d.angle(50,50,5) and p.get('depth')==50]
    angle_bars=math.ceil(len(angle_parts)/18)
    nut_count=sum(p['family']=='M8_Nut' for p in m.parts);nut_packs=math.ceil(nut_count/100)
    stock=[dict(item='SUS304 50×50×5 앵글 1 m',quantity=angle_bars,unit_price_krw=35800,
                subtotal_krw=angle_bars*35800,source='angle',scope='브라켓 원소재만, 가공·배송 제외'),
           dict(item='SUS304 M8 너트 100개 봉지',quantity=nut_packs,unit_price_krw=8000,
                subtotal_krw=nut_packs*8000,source='nut',scope='너트만, 배송 제외')]
    stock=[x for x in stock if x['quantity']>0]
    labor=labor_cost(costs)
    total_parts=None if missing_parts else priced
    total=None if total_parts is None or labor['all_fabrication_quote_krw'] is None else total_parts+labor['all_fabrication_quote_krw']
    return dict(revision=d.REVISION,inputs=c,bounds=d.bounds(m),component_count=len(m.parts),
        unique_parts=len({p['master'] for p in m.parts}),bom=bom,
        fabricated_geometry_mass_kg=known,purchased_mass_kg=c['purchased_mass_kg'],total_machine_mass_kg=actual,
        core_reference_mass_kg=d.CORE_REFERENCE_MASS_KG,core_stand_mass_kg=core_stand_mass,
        feeder_fabricated_mass_kg=feed_mass,normal_potato_kg=belt_normal,
        blocked_feeder_potato_kg=belt_full,blocked_core_potato_kg=core_food,supports=supports,
        blocked_transition_potato_kg=transition_food,transition_mass_kg=group_mass['transition'],
        core_machine_design_kg=core_machine,feed_machine_design_kg=feed_machine,
        transition_machine_design_kg=transition_machine,
        core_purchase_design_kg=core_purchase,feed_purchase_design_kg=feed_purchase,
        design_mass_by_group_kg=dict(group_mass),beams=beams,floor=floor,
        transition_overturning_moment_nm=overturning,
        tube_cut_list=list(tube_groups.values()),weld_schedule=list(weld_groups.values()),
        structural_calculation_pass=all(x['selected']['passes_screen'] for x in supports)
            and all(x['passes_screen'] for x in beams) and floor['passes_screen'],
        target_kg_h=c['target_kg_h'],belt_speed_m_min=speed,drive_pulley_rpm=pulley_rpm,
        roller_rpm=speed/(math.pi*.05),knife_rpm=0.,impeller_rpm=c['impeller_rpm'],
        blade_passes_per_potato_min=c['blade_count']*c['impeller_rpm'],
        main_drive_ratio=c['motor_base_rpm']/c['impeller_rpm'],impeller_tip_speed_m_s=omega*.24,
        available_impeller_torque_nm=available_torque,
        service_factored_tangential_force_n=available_torque/c['service_factor']/cutradius,
        required_knife_motor_kw=required_cut_kw,feed_pull_n=pull,feed_required_torque_nm=feed_torque,
        feed_required_motor_kw=feed_power,feed_available_torque_nm=output_torque,
        feed_motor_speed_rpm=pulley_rpm*c['conveyor_ratio'],
        feed_motor_frequency_hz=60*pulley_rpm*c['conveyor_ratio']/c['motor_base_rpm'],
        installed_motor_kw=c['knife_motor_kw']+c['conveyor_motor_kw'],rated_load_input_kw=rated_input,
        energy_cost_per_hour_krw=actual_cost,rated_load_cost_per_hour_krw=rated_cost,
        electricity_sensitivity=[(price,rated_input*price) for price in (100,150,200)],
        manufacturing_quantities=q,reference_stock=stock,known_stock_subtotal_krw=sum(x['subtotal_krw'] for x in stock),
        quoted_part_subtotal_krw=priced,complete_part_cost_krw=total_parts,
        unpriced_part_masters=missing_parts,labor=labor,complete_machine_price_krw=total,
        warnings=['Python 코드만 수정. CATIA 생성·회전·간섭·절단 성능 검증은 사용자가 수행.',
            '318 kg는 CC-DL 원제품의 지지하중 참고값이며 이 자체 제작 모델의 실중량이 아님.',
            '본체 500 kg, 컨베이어 200 kg, 슈트 구조 80 kg는 최소 설계 질량이며 실중량이 아님. 계산 형상+구매품 여유가 크면 큰 값을 사용.',
            '부재·용접 응력의 조건부 계산이며 완성 기계의 전도·진동·용접 절차 적합성을 인증하지 않음.',
            '560 kg/h는 기존 라인의 투입 목표. 원제품의 보증 처리량 또는 확인된 자체 제작 성능이 아님.',
            '업체의 제작 공임 총액과 실공수 미입력: 총액은 미확정으로 남김.'])

def fmt(v,digits=2):return '미확정' if v is None else f'{v:,.{digits}f}'
def esc(v):return html.escape(str(v))
def link(key):
    title,url=SOURCES[key];return f'<a href="{html.escape(url,quote=True)}">{esc(title)}</a>'
def table(headers,rows):
    return '<table><tr>'+''.join('<th>'+str(x)+'</th>' for x in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+str(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</table>'

def report_html(r):
    c=r['inputs'];size=' × '.join(fmt(x,0) for x in r['bounds']['size_mm']);s=[]
    s.append('<h2>1. 크기와 구조</h2>'+table(['항목','설계 내용'],[
        ('받침대·투입 컨베이어 포함 전체 L × W × H',size+' mm'),
        ('참고 CC-DL 본체 L × W × H','1,578 × 947 × 871 mm · 원제품 318 kg'),
        ('자체 설치 높이','본체 배출구 바닥 500 mm · 투입 벨트 상면 1,600 mm'),
        ('절단 방식','고정 칼날 8개 + 수직축 임펠러 5패들 · 목표 두께 1.5 mm'),
        ('컨베이어','별도 투입용 1개, 폭 800 mm · 구동 풀리 Ø100 · 나머지 Ø50'),
        ('프레임','SUS304 사각관 용접: 주 다리·보 80×80×'+fmt(c['leg_wall_mm'],0)+' mm, 보조 50×50×3 mm'),
        ('원추형 부품','Swing Away cover / Lower Discharge Cone / Hopper: XZ 단면을 수직 Z축 주위로 360° 회전'),
        ('감속기 간섭 수정','외부 케이스 X885 시작: 지지 링 끝 X864와 21 mm 여유. Z700 수평축은 원추 Ø70 구멍과 밀폐 보호관으로 연결' if 'R17' in r['revision'] else '이 계산 스냅샷은 R17 외부 감속기 변경 전 모델입니다.'),
        ('모터 색상','본체 모터·팬 커버·직각 감속기·투입 기어드모터: 공통 파란색 RGB 47, 92, 158'),
        ('슈트 하부 지지','경사 레일 → 틈을 채운 받침 → 기둥 → 가로 보 → 돌출 팔·거싯 → 컨베이어 다리'),
        ('개정 부품','기존 C형 프레임·볼트식 프레임 스플라이스·떠 있던 연결판 삭제; 사각관·끝막음·용접 거싯 추가'),
        ('Product 구성','1_Frame / 2_Internal / 3_External → 종류 → 기능별 그룹 → 공통 CATPart 반복 인스턴스')])+
        '<p>외형은 CC-DL 자료, 고정 칼날과 회전 임펠러는 감자용 CC 자료를 참고했습니다. 원제품의 단면 제작도는 공개되어 있지 않아 헤드·축·체결부는 자체 설계 치수입니다. CC-DL과 일반 CC의 외형·무게를 섞지 않았습니다. '+link('ccdl')+' · '+link('potato')+'</p>'+
        '<p>본체 바닥 배출은 아래 방향입니다. 다음 공정과는 높이와 낙하 연결을 맞춰야 합니다. 칼날은 경화 가능한 식품용 스테인리스 구매품, 베어링은 스테인리스 구매품, 벨트는 식품용 PU입니다. 구조물과 식품 접촉 금속판은 SUS304로 지정했습니다.</p>')
    rows=[]
    for x in r['supports']:
        a=x['selected'];rows.append((x['name'],fmt(x['mass_basis_kg'])+' kg',
            fmt(a['N_n'],0)+' N',fmt(a['compression_mpa'])+' / '+fmt(a['tension_mpa'])+' / '+fmt(a['shear_mpa'])))
    s.append('<h2>2. 사각관 두께·하중·응력·안전한계</h2>'+
        '<p><b>채택: 주 다리와 보는 80×80×'+fmt(c['leg_wall_mm'],0)+' mm, 보조 받침은 50×50×3 mm, 거싯은 6 mm, 슈트 바닥은 3 mm입니다.</b> 사각봉은 속이 빈 사각관으로 설계했습니다. 세척수가 관 안으로 들어가지 않도록 끝막음 판과 연속 용접을 포함합니다.</p>'+
        table(['지지 구역','제작 형상 질량','계산에 적용한 기계 질량','적체 감자 질량'],[
            ('본체',fmt(r['design_mass_by_group_kg']['core'])+' kg',fmt(r['core_machine_design_kg'])+' kg',fmt(r['blocked_core_potato_kg'])+' kg'),
            ('투입 컨베이어',fmt(r['feeder_fabricated_mass_kg'])+' kg',fmt(r['feed_machine_design_kg'])+' kg',fmt(r['blocked_feeder_potato_kg'])+' kg'),
            ('돌출 슈트와 받침',fmt(r['transition_mass_kg'])+' kg',fmt(r['transition_machine_design_kg'])+' kg',fmt(r['blocked_transition_potato_kg'])+' kg')])+
        '<details><summary>기계·감자 하중의 산정 근거</summary><p>본체는 max('+fmt(c['core_machine_design_min_kg'],0)+' kg, 본체 제작 형상+'+fmt(r['core_purchase_design_kg'],0)+' kg 구매품 여유, 원제품 318 kg+추가 받침대), 컨베이어는 max('+fmt(c['feed_machine_design_min_kg'],0)+' kg, 제작 형상+'+fmt(r['feed_purchase_design_kg'],0)+' kg 구매품 여유), 슈트는 max('+fmt(c['transition_machine_design_min_kg'],0)+' kg, 제작 형상)을 사용합니다. 이 값은 <b>설계용 하중</b>이고 실제 기계 중량이 아닙니다. 구매품 질량을 0으로 두어 다리를 계산하지 않습니다.</p>'+
        '<p>제작 형상 총질량 '+fmt(r['fabricated_geometry_mass_kg'])+' kg, 구매품 포함 실제 총중량 '+fmt(r['total_machine_mass_kg'])+' kg. 구매품 총중량만 입력하면 구역 배분이 불명확하므로 각 프레임에 전량을 각각 적용합니다. 총중량 계산에는 한 번만 더합니다.</p>'+
        '<p>감자는 벨트 높이 98 mm, 슈트 적체 높이 '+fmt(c['transition_bed_height_mm'],0)+' mm, 호퍼·절단부의 채움 체적과 벌크밀도 '+fmt(c['potato_density_kg_m3']*c['packing_fraction'],0)+' kg/m³로 계산합니다. 슈트 하중은 본체 호퍼에 얹지 않고 컨베이어 프레임으로 전달합니다.</p></details>'+
        table(['다리 그룹','분담하는 기계+감자 하중','최대 한 다리 압축력','압축 / 인장 / 전단 [MPa]'],rows)+
        '<p><b>압축</b>은 기계와 감자가 다리를 아래로 누르는 작용입니다. <b>전단</b>은 흔들림이 다리를 옆으로 미는 작용입니다. 이때 다리가 휘면서 한쪽 면은 눌리고 반대쪽 면은 <b>인장</b>을 받습니다. σ=N/A±M/Z, τ=V/Av, 등가응력=√(σ²+3τ²)로 합쳤습니다.</p>'+
        '<p>수직 동하중 '+fmt(c['dynamic_factor'],1)+'배, 한 다리 기본 분담 '+fmt(c['leg_load_share']*100,0)+'%, 횡하중 '+fmt(c['lateral_accel_g'],2)+'g입니다. 슈트는 앞다리에서 700 mm 돌출한 곳에 전 하중이 걸린다고 보고, 앞다리 반력에 W×(1+700/1050)/2를 별도로 반영합니다. 동일 슈트 무게를 수직 하중에 두 번 더하지 않습니다.</p>'+
        table(['다리','등가응력 / 허용응력','계산 항복 안전율','허용 좌굴력 / 작용 압축력','동일 비율 하중 한계'],[
            (x['name'],fmt(x['selected']['von_mises_mpa'])+' / '+fmt(x['selected']['allowable_mpa'])+' MPa',
             fmt(x['selected']['yield_safety_factor']),
             fmt(x['selected']['allowable_buckling_n'],0)+' / '+fmt(x['selected']['N_n'],0)+' N',
             fmt(x['selected']['load_multiplier_limit'])+'배 · '+('식의 조건 통과' if x['selected']['passes_screen'] else '단면 증대 필요'))
            for x in r['supports']])+
        '<details><summary>허용응력·단면 산식과 3~6 mm 두께 비교</summary><p>허용응력은 설계 내력 '+fmt(c['yield_mpa'],0)+' MPa ÷ 안전율 '+fmt(c['safety_factor'],1)+' = '+fmt(c['yield_mpa']/c['safety_factor'])+' MPa입니다. 사각관 단면은 A=BH−(B−2t)(H−2t), I=[BH³−(B−2t)(H−2t)³]/12, Z=I/(H/2)를 사용합니다. 공급사 모서리·두께 공차 자료 전에는 A·I·Z에 '+fmt(c['section_property_factor']*100,0)+'%를 적용합니다. 이 감소율은 설계 입력이지 규격 보증치가 아닙니다.</p>'+
        table(['다리 두께 비교','3 mm','4 mm','5 mm','6 mm','계산에서 처음 만족한 두께'],[
            (x['name'],*[fmt(y['von_mises_mpa'])+' MPa / '+('조건 통과' if y['passes_screen'] else '초과') for y in x['cases']],
             fmt(x['screened_minimum_wall_mm'],0)+' mm') for x in r['supports']])+
        '<p>두께는 압축만으로 정하지 않습니다. 흔들림의 굽힘, 전단, 좌굴, 용접부 여유와 아래 보의 처짐까지 함께 봅니다. 기본 4 mm는 보와 다리 단면을 통일하고 3 mm 필릿 용접 및 제작 여유를 확보하는 선정값입니다. 후보가 통과해도 그 값이 인증된 제작 최소 두께라는 뜻은 아닙니다.</p></details>'+
        '<details><summary>받침 보와 Feed_transition_floor</summary>'+
        table(['부재 / 단면','계산 길이','등가 / 허용응력','처짐 / 허용처짐','하중 한계'],[
            (x['name']+' / '+'×'.join(fmt(v,0) for v in x['section_mm'])+' mm',fmt(x['span_mm'],0)+' mm',
             fmt(x['von_mises_mpa'])+' / '+fmt(x['allowable_mpa'])+' MPa',
             fmt(x['deflection_mm'],3)+' / '+fmt(x['allowable_deflection_mm'],3)+' mm',
             fmt(x['load_multiplier_limit'])+'배 / '+('조건 통과' if x['passes_screen'] else '단면 증대 필요')) for x in r['beams']])+
        '<p>보는 최악 위치에 집중하중을 놓고 M=PL/4 또는 돌출 팔의 M=PL로 계산합니다. 돌출 팔 2개 중 하나에 슈트 하중의 75%를 적용하고, 거싯의 보강 효과는 계산에 넣지 않았습니다. 경사 레일은 실제 지지점 이후 길이보다 긴 350 mm 외팔보로 계산합니다.</p>'+
        '<p>슈트 바닥은 '+fmt(r['floor']['actual_outlet_overhang_mm'],0)+' mm의 끝단 돌출을 남기고 레일로 받칩니다. 3 mm 판을 200 mm 외팔 띠판으로 보수적으로 계산한 응력 '+fmt(r['floor']['stress_mpa'])+' / 허용 '+fmt(r['floor']['allowable_mpa'])+' MPa, 처짐 '+fmt(r['floor']['deflection_mm'],3)+' / 허용 '+fmt(r['floor']['allowable_deflection_mm'],3)+' mm입니다. 사람의 발판 하중은 적용하지 않았습니다.</p></details>'+
        table(['용접부','등가응력','허용응력','하중 한계'],[
            (x['name']+' 하부 전둘레',fmt(x['selected']['weld']['von_mises_mpa'])+' MPa',
             fmt(x['selected']['weld']['allowable_mpa'])+' MPa',
             fmt(x['selected']['weld']['load_multiplier_limit'])+'배') for x in r['supports']]+[
            (x['name']+' 접합부',fmt(x['weld']['von_mises_mpa'])+' MPa',
             fmt(x['weld']['allowable_mpa'])+' MPa',fmt(x['weld']['load_multiplier_limit'])+'배')
            for x in r['beams'] if '돌출' in x['name']])+
        '<p>전둘레 필릿 다리 길이 '+fmt(c['weld_leg_mm'],0)+' mm, 유효 목두께 0.707a를 적용했습니다. 용접 허용응력은 모재 허용의 80%로 제한한 설계 입력입니다. 용접 절차·필러·실제 목두께가 확보되어야 이 계산을 적용할 수 있습니다. 모터·칼날·베어링·커버의 정비 접합은 분리 가능한 구조로 유지합니다.</p>'+
        '<p>전체 조건부 부재 계산: <b>'+('설정 하중에서 식의 조건 통과' if r['structural_calculation_pass'] else '초과 부재가 있어 단면·지지 구조 변경 필요')+'</b>. 이 표는 코드의 계산 결과이며 실물 검증 결과가 아닙니다. 하중 한계 배수는 해당 부재에 적용한 하중을 같은 비율로 키운 한계이며, 기계 전체의 적재 허용량으로 바꿔 읽지 않습니다.</p>'+
        '<p>좌굴은 K=2 Euler와 항복을 결합한 Rankine 예비식 및 관 벽의 탄성 국부좌굴을 사용합니다. 실제 무게중심·바닥 고정조건이 없어 전도 안전율은 확정하지 않습니다. 슈트만의 전도 모멘트 '+fmt(r['transition_overturning_moment_nm'])+' N·m에 본체·컨베이어의 복원 모멘트와 운전 횡하중을 함께 확인해야 합니다. 진동 피로·운전 공진·관 접합부 국부 변형은 별도 대상입니다. 재료 내력 205 MPa는 성적서 확인 전 보수적 입력입니다. '+link('steel')+'</p>')
    s.append('<h2>3. 한 시간 처리량과 회전수</h2>'+table(['항목','값'],[
        ('기존 라인 투입 목표',fmt(r['target_kg_h'],0)+' kg/h'),
        ('고정 칼날 회전수','0 RPM'),
        ('임펠러 초기 설정',fmt(r['impeller_rpm'],0)+' RPM'),
        ('벨트 속도 / Ø100 구동 풀리',fmt(r['belt_speed_m_min'],3)+' m/min / '+fmt(r['drive_pulley_rpm'],3)+' RPM'),
        ('Ø50 롤러',fmt(r['roller_rpm'],3)+' RPM'),
        ('슬라이스 두께','가이드 반경 245.0 − 칼끝 반경 243.5 = 1.5 mm')])+
        '<p>임펠러가 감자를 원주 쪽으로 밀어 고정된 칼날을 지나게 합니다. 두께는 칼날과 가이드의 설정 간격으로 정합니다. 벨트속도 ÷ 칼날RPM 식은 이 방식에 적용하지 않습니다.</p>'+
        '<p>257 RPM은 제조사 구형 매뉴얼의 감자 절단 적용 사례에서 가져온 초기값이며, CC-DL의 확정 운전속도라는 뜻은 아닙니다. '+link('manual')+'</p>'+
        '<p>벨트속도는 560 ÷ [60 × 0.8 × 0.06 × 1,100 × 0.65 × 0.5]로 산출했습니다. 높이 60 mm, 폭 사용률 50%, 충전율 65%는 설계 입력입니다. 공개된 두 PDF에는 kg/h 보증 수치가 없어 560 kg/h를 달성 성능으로 표시하지 않습니다.</p>')
    s.append('<h2>4. 모터 용량과 한 시간 전기요금</h2>'+table(['구동 위치','채택 용량','회전수·토크 근거'],[
        ('본체 절단 구동: 모터 → 직각 감속기 → 임펠러','7.5 kW × 1',
         '모터 '+fmt(c['motor_base_rpm'],0)+' RPM → 임펠러 '+fmt(r['impeller_rpm'],0)+' RPM, 총 감속비 '+fmt(r['main_drive_ratio'],3)),
        ('투입 컨베이어: 기어드모터 → 끝 Ø100 풀리','0.20 kW × 1',
         '감속비 '+fmt(c['conveyor_ratio'],0)+', 모터 '+fmt(r['feed_motor_speed_rpm'],1)+' RPM ('+fmt(r['feed_motor_frequency_hz'],1)+' Hz 초기값)'),
        ('임펠러에 공급 가능한 정격 토크',fmt(r['available_impeller_torque_nm'])+' N·m','7,500 × 전달효율 0.9 ÷ 각속도'),
        ('컨베이어 계산 필요 동력 / 필요 토크',fmt(r['feed_required_motor_kw'],4)+' kW / '+fmt(r['feed_required_torque_nm'])+' N·m',
         '견인력 '+fmt(r['feed_pull_n'])+' N, 기동 여유 1.5, 전달효율 0.65'),
        ('컨베이어 공급 토크 참고',fmt(r['feed_available_torque_nm'])+' N·m','저속 토크 50% 저감 입력, 감속기 허용 토크 별도 확인')])+
        '<p>7.5 kW는 CC-DL 공개 사양을 채택한 용량입니다. 절단력으로 역산한 최소 필요 용량은 절단력 입력이 없어 '+fmt(r['required_knife_motor_kw'])+' kW입니다. 서비스계수 1.5 적용 후 환산 접선력은 '+fmt(r['service_factored_tangential_force_n'],0)+' N까지입니다. '+link('ccdl')+'</p>'+
        '<p>컨베이어는 벨트·감자 무게, 마찰계수 0.12, 추가 저항 100 N, 3초 기동을 반영했습니다. 0.20 kW는 이 예비 하중에 대한 선정값입니다. 두 모터는 서로 다른 곳을 구동하며, 고정 칼날 자체를 회전시키는 모터는 없습니다.</p>'+
        '<p>두 모터 정격 출력 합은 '+fmt(r['installed_motor_kw'])+' kW입니다. 효율을 반영한 정격부하 전기입력 참고값은 '+fmt(r['rated_load_input_kw'])+' kW입니다. 실제 입력은 부하에 따라 달라집니다.</p>'+
        table(['요금 항목','한 시간 금액'],[
            ('실측 입력 × 실제 계약단가',fmt(r['energy_cost_per_hour_krw'],0)+' 원'),
            ('정격부하 입력 × 입력한 계약단가',fmt(r['rated_load_cost_per_hour_krw'],0)+' 원'),
            *[('단가 '+fmt(price,0)+' 원/kWh를 넣어 본 비교값',fmt(cost,0)+' 원') for price,cost in r['electricity_sensitivity']]])+
        '<p>100/150/200원은 요금 민감도 비교값이며 한전의 확정 계약단가가 아닙니다. 실제 청구액에는 계약별 기본요금·조정요금·세금 등이 더해집니다.</p>')
    q=r['manufacturing_quantities'];labor=r['labor']
    s.append('<h2>5. 부품 종류·수량·가격</h2>'+
        '<p>모델 부품 형상 '+str(r['unique_parts'])+'종, 조립 인스턴스 '+str(r['component_count'])+'개입니다. 구매 모터는 2대, 칼날은 8개, 임펠러는 1세트(패들 5개), 벨트는 1개, 끝 풀리는 2개, 지지 롤러는 4개입니다. 베어링은 임펠러 2개+컨베이어 12개이며, 하우징·내륜·외륜 표시 형상을 완제품 베어링 수량에 중복 합산하지 않습니다.</p>'+
        table(['가격을 확인한 품목','구매 수량','단가','소계','범위'],[
            (x['item'],x['quantity'],fmt(x['unit_price_krw'],0)+' 원',fmt(x['subtotal_krw'],0)+' 원',x['scope']+' · '+link(x['source'])) for x in r['reference_stock']])+
        '<p>C형 프레임과 조립 앵글은 용접 사각관으로 교체했습니다. 남아 있는 동일 규격 구매품만 공개 단가 소계에 포함합니다. 공개 단가 소계는 '+fmt(r['known_stock_subtotal_krw'],0)+' 원입니다. 이것은 기계 전체 부품비가 아닙니다.</p>'+
        '<p>비교용 일반형 0.2 kW 기어드모터 공개가는 194,700원(VAT 포함)입니다. 기어비 1/5~1/100 일반형으로, 이번 1/300·스테인리스 사양과 달라 BOM 가격으로 대입하지 않았습니다. '+link('motor_comparison')+'</p>'+
        '<p>전체 동일 규격 부품비: '+fmt(r['complete_part_cost_krw'],0)+' 원. 견적이 없는 '+str(len(r['unpriced_part_masters']))+'개 형상은 0원으로 처리하지 않았습니다. 표준 부품 표시 형상과 실물 구매 단위도 구분해야 합니다.</p>'+
        '<details><summary>추가·변경 사각관 절단 목록</summary>'+table(['기능','단면 B×H×t [mm]','한 개 절단 길이','수량','총 길이'],[
            (esc(x['family']),esc(x['section_mm']),fmt(x['cut_length_mm'])+' mm',x['quantity'],fmt(x['total_length_m'],3)+' m')
            for x in r['tube_cut_list']])+'</details>'+
        '<p>관 끝막음 '+str(q['end_caps'])+'개, 용접 거싯 '+str(q['gussets'])+'개도 BOM에 포함합니다. 사각관 원소재·절단·끝막음·용접·연마·산세/부동태화는 새 견적 항목이며, 기존 앵글 가격을 사각관 가격으로 바꾸어 넣지 않았습니다.</p>'+
        '<details><summary>전체 모델 BOM: 종류·수량·재질·단가</summary>'+table(['그룹','부품 / Master','수량','재질','단가 / 소계'],[
            (esc(x['category'])+'/'+esc(x['type']),esc(x['family'])+' / '+esc(x['master']),x['quantity'],esc(x['material']),
             fmt(x['unit_price_krw'],0)+' / '+fmt(x['extended_krw'],0)+' 원') for x in r['bom']])+'</details>')
    s.append('<h2>6. 전체 제작 공임</h2>'+
        '<p><b>전체 제작 공임: '+fmt(labor['all_fabrication_quote_krw'],0)+' 원.</b> 이 신규 기계의 동일 규격 제작 견적이나 실제 공수는 확보되지 않았습니다. 임의 작업일수를 곱해 실제 공임처럼 표시하지 않았습니다.</p>'+
        table(['제작 작업','공개 시간당 노임','확인된 인시','직접 노무비'],[
            (x['operation'],fmt(x['hourly_wage_krw'])+' 원/h',fmt(x['person_hours']),fmt(x['direct_wage_krw'],0)+' 원') for x in labor['rows']])+
        '<p>노임은 중소기업중앙회 2026년 하반기 적용 보고서의 8시간 일급을 나눈 값입니다. 이는 원가계산 기초 임금으로, 업체의 판매 공임·장비비·간접비·이윤·VAT를 포함한 견적이 아닙니다. '+link('kbiz')+'</p>'+
        table(['직접 찾아 확인한 장비료','공개 금액','적용 범위'],[
            ('범용밀링 NSM-A','5,000원/h','장비 사용료 · '+link('mill')),
            ('범용선반 HL-380','5,000원/h','장비 사용료 · '+link('lathe')),
            ('5축 C22U','40,000원/h','장비 사용료, XYZ 450×600×330 · '+link('cnc'))])+
        '<p>큰 절단실이나 Ø560 헤드 전체를 C22U 한 대에서 가공한다고 계산하지 않았습니다. 장비 범위가 맞는 작은 브라켓·시트 가공의 비교 단가로만 기록했습니다.</p>'+
        table(['공임 견적에 필요한 모델 물량','수량'],[
            ('사각관 절단',str(q['profile_pieces'])+'개 / '+fmt(q['profile_length_m'])+' m'),
            ('전둘레·끝막음·거싯·슈트 용접',str(q['welded_joints'])+'개소 / 지정 이음 길이 '+fmt(q['weld_length_m'])+' m'),
            ('관 끝막음 / 용접 거싯',str(q['end_caps'])+'개 / '+str(q['gussets'])+'개'),
            ('평판·브라켓',''+str(q['plate_pieces'])+'개 / 평면 윤곽 '+fmt(q['contour_length_m'])+' m'),
            ('모델의 드릴 가공 구멍',str(q['drill_holes'])+'개'),
            ('선삭 형상 / 원추 성형',str(q['turned_parts'])+'개 / '+str(q['formed_cones'])+'개'),
            ('볼트 조립 / 칼날 설정',str(q['bolted_joints'])+'개 / 8개소')])+
        '<p>용접원 공개 노임은 124,879원/8시간 = '+fmt(LABOR['용접원']/8)+'원/h입니다. 용접 길이만으로 작업시간을 임의 환산하지 않습니다. 준비·지그·뒤틀림 교정·관 끝막음·산세/부동태화·용접 검사 범위를 업체 견적에 명시해야 합니다. 기록된 길이는 지정된 구조 접합부의 이음 길이로, 호퍼 제조사의 성형 이음 등 상세도 미정 공정은 별도입니다.</p>'+
        '<details><summary>용접 내역과 견적 물량</summary>'+table(['접합부','다리 길이','개소','이음 길이'],[
            (esc(x['family']),fmt(x['leg_mm'],0)+' mm',x['joints'],fmt(x['total_length_m'],3)+' m')
            for x in r['weld_schedule']])+'</details>'+
        '<p>산식은 공정별 확인 인시 × 해당 노임 + 확인된 장비·외주 가공비입니다. 실제 업체 전체 공임 견적이 입력되면 이를 우선 사용하고 포함된 직접 노무비를 다시 더하지 않습니다. 확인되지 않은 열처리·연마·성형·전기 조립을 누락한 소계를 전체 제작 공임이라고 부르지 않습니다.</p>'+
        '<p>부품비+전체 공임 총액: '+fmt(r['complete_machine_price_krw'],0)+' 원. 실제 단가는 Python의 COST_INPUTS 또는 --cost-input으로 출처와 함께 입력할 수 있습니다.</p>')
    css='body{font:15px/1.65 "Malgun Gothic",sans-serif;color:#203441;max-width:1050px;margin:35px auto;padding:0 22px}h1{font-size:28px}h2{font-size:20px;margin-top:30px;border-bottom:2px solid #dce5eb}table{border-collapse:collapse;width:100%;font-size:13px;margin:14px 0}th,td{border:1px solid #dce5eb;padding:8px;text-align:left}th{background:#eef4f7}a{color:#176b94}details{margin:18px 0}@media print{body{font-size:11px;margin:0}tr{break-inside:avoid}details{display:none}}'
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>5번 CC 슬라이서 리뷰</title><style>'+css+'</style><h1>5번 CC 방식 감자 슬라이서 · 1.5 mm</h1><p>'+esc(r['revision'])+' · 모델링 Python 저장 후 작성한 리뷰 생성 코드 · 실행·검증은 사용자 수행</p>'+''.join(s)+'</html>'

def write_report(folder=None,config=None,cost_inputs=None):
    folder=Path(folder or d.ROOT/'Overall_Review'/'05_CC_Design_Review');folder.mkdir(parents=True,exist_ok=True)
    r=calculations(config,cost_inputs);page=folder/'05_Slicer_Review.html'
    page.write_text(report_html(r),encoding='utf-8')
    (folder/'05_CC_Calculations.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    for filename,rows in [('05_BOM.csv',r['bom']),('05_Labor_Cost.csv',r['labor']['rows']),
                           ('05_Tube_Cut_List.csv',r['tube_cut_list']),('05_Weld_Schedule.csv',r['weld_schedule'])]:
        with (folder/filename).open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return page,r

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--config',type=Path);ap.add_argument('--cost-input',type=Path)
    ap.add_argument('--output-dir',type=Path,default=d.ROOT/'Overall_Review'/'05_CC_Design_Review');args=ap.parse_args()
    read=lambda p:json.loads(p.read_text(encoding='utf-8-sig')) if p else None
    page,result=write_report(args.output_dir,read(args.config),read(args.cost_input));print(page)
