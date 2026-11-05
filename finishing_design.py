"""Stations 05-11: shared CAD inputs and preliminary engineering reviews.

Standard library only. No CATIA/COM activation on import or report generation.
Units: mm, kg, N, MPa, rpm, kW. All process coefficients are editable assumptions.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import math
from collections import defaultdict
from pathlib import Path
import station1_design as core
import station2_design as so

REVISION='FINISHING-R13-2026-11-03'
G=9.80665
NAMES={5:('CC','Centrifugal Slicer'),6:('BL','Continuous Blancher'),7:('VDW','Vibratory Dewaterer'),
       8:('AD','Air Dryer'),9:('FR','Continuous Fryer'),10:('VDO','Vibratory Deoiler'),11:('SD','Seasoning Drum')}
COMMON=dict(material='SUS304',steel_density_kg_m3=7930.,yield_mpa=205.,elastic_modulus_mpa=193000.,
    safety_factor=2.,dynamic_factor=1.5,lateral_accel_g=.15,mass_allowance_fraction=.15,
    raw_density_kg_m3=1100.,raw_packing_fraction=.65,wet_flow_kg_h=560.,wet_slice_bulk_density_kg_m3=550.,
    chip_bulk_density_kg_m3=100.,feed_water_fraction=.80,final_water_fraction=.02,final_oil_fraction=.35,
    operating_hours_day=8.,days_month=22.,energy_rate_krw_kwh=160.,extra_demand_krw_month=0.,
    supply_v=380.,supply_hz=60.,motor_base_rpm=1750.,motor_efficiency=.84,vfd_efficiency=.96,
    motor_pf=.78,gear_efficiency=.75,low_speed_torque_factor=.80,start_seconds=5.,
    service_factor=1.5,running_resistance=.12,breakaway_factor=1.5,
    control_kw=.06,weld_leg_mm=4.,leg_eccentricity_mm=10.)
DEFAULTS={
 5:{},
 6:dict(residence_min=2.,bed_height_mm=40.,max_bed_height_mm=50.,conveyor_motor_kw=.37,conveyor_ratio=150.,
        bath_temperature_c=85.,feed_temperature_c=20.,makeup_water_kg_h=100.,heater_kw=120.,heater_efficiency=.95,
        heat_loss_kw=12.,food_cp_kj_kgk=3.6,water_density_kg_m3=970.,warmup_minutes=90.),
 7:dict(conveying_speed_m_min=6.,max_bed_height_mm=50.,vibration_hz=25.,amplitude_mm=1.5,
        damping_ratio=.08,motor_kw_each=.55,motor_count=2.,exciter_force_n_each=5000.,spring_E_mpa=200000.,spring_allowable_mpa=150.,
        spring_density_kg_m3=7850.,spring_thickness_mm=3.,motor_input_load_fraction=.70,drain_hold_kg=20.),
 8:dict(conveying_speed_m_min=4.,max_bed_height_mm=50.,conveyor_motor_kw=.18,conveyor_ratio=80.,
        fan_count=6.,fan_flow_m3_h_each=1000.,fan_pressure_pa=1200.,fan_efficiency=.55,fan_motor_kw=1.1),
 9:dict(residence_min=3.,bed_height_mm=40.,max_bed_height_mm=65.,conveyor_motor_kw=.75,conveyor_ratio=350.,
        fryer_model='PC4',oil_density_kg_m3=820.,oil_cp_kj_kgk=2.,oil_temperature_c=180.,feed_temperature_c=65.,
        initial_temperature_c=25.,heater_kw=450.,heater_efficiency=.90,heat_loss_kw=25.,thermal_reserve=1.15,
        evaporation_kj_kg=2257.,food_cp_kj_kgk=3.6,solids_cp_kj_kgk=1.7,warmup_minutes=60.,
        pump_head_m=12.,pump_efficiency=.60,pump_motor_kw=7.5,oil_turnover_min=1.,exhaust_motor_kw=1.5,
        lift_motor_kw=.75,lift_speed_mm_s=5.,jack_lead_mm=6.,jack_efficiency=.30,jack_rated_load_n=20000.),
 10:dict(conveying_speed_m_min=4.,max_bed_height_mm=60.,vibration_hz=25.,amplitude_mm=1.,
        damping_ratio=.08,motor_kw_each=.55,motor_count=2.,exciter_force_n_each=5000.,spring_E_mpa=200000.,spring_allowable_mpa=150.,
        spring_density_kg_m3=7850.,spring_thickness_mm=3.,motor_input_load_fraction=.70,drain_hold_kg=15.),
 11:dict(drum_rpm=8.,residence_min=2.,max_fill_fraction=.12,drum_motor_kw=.75,drum_gear_ratio=18.,
         drum_ring_pitch_radius_mm=398.6,pinion_radius_mm=35.,rolling_resistance=.03,
         infeed_motor_kw=.18,infeed_gear_ratio=100.,infeed_bed_height_mm=40.,
         seasoning_fraction=.03,powder_bulk_density_kg_m3=600.,powder_fill_fraction=.30,powder_axial_efficiency=.50,
         feeder_motor_kw=.09,feeder_gear_ratio=100.,feeder_empty_nm=5.,seasoning_angle_deg=40.)}
SOURCES=[
 ('MAT','Nippon Steel SUS304 properties','https://www.nipponsteel.com/product/catalog_download/__icsFiles/afieldfile/2025/10/06/S008.pdf',
  'SUS304 기준 밀도 7930 kg/m³, 상온 내력 205 MPa, E 193 GPa. 구매 관재·용접·고온 물성은 별도 확인.'),
 ('CC','Urschel CC-DL reference','https://www.urschel.com/wp-content/uploads/2024/03/fact-sheet-model-cc-dl-english.pdf',
  'CC-DL 원제품 외형 1578×947×871 mm, 318 kg, 모터 7.5 kW. 별도 800 mm 투입 컨베이어와 받침대는 자체 설계.'),
 ('BX','Baixin processing line','https://www.bxmachinery.com/products/full-automatic-potato-chips-production-line/',
  '블랜처 4500×1200×1300, 탈수기 1800×1000×1300, 건조기 3500×1000×1600 mm 참고. 공급사 번호와 본 프로젝트 번호는 다름. 본 내부 구조·성능은 추정 설계.'),
 ('FR','Heat and Control PC fryer drawing','https://www.heatandcontrol.com/sites/default/files/content/resource/pdf/2026-06/Potato%20Chip%20Fryer_HeatandControl.pdf',
  'A/B/C/D/E 외형과 PC4 완제품 400 lb/h 기준 참고. 오일 순환·필터·히터는 외부 계통; 이번 모델에 외부 스키드 형상은 포함하지 않음.'),
 ('VIB','Italvibras selection method','https://www.italvibras.it/user/upload_inc_inglese_new/scelta.pdf',
  '진동기 선정은 이동 질량, 주파수, 진폭 및 원심력으로 수행. kW만으로 진동 이송량을 보장하지 않음.'),
]


def configuration(index,overrides=None):
    if index==5:
        from slicer_design import configuration as slicer_configuration
        return slicer_configuration(overrides)
    if index not in DEFAULTS:raise ValueError('Station must be 5..11')
    c=dict(COMMON,**DEFAULTS[index])
    if overrides is not None:
        if not isinstance(overrides,dict):raise ValueError('Configuration must be a JSON object')
        unknown=set(overrides)-set(c)
        if unknown:raise ValueError('Unknown inputs: '+', '.join(sorted(unknown)))
        c.update(overrides)
    for k,v in c.items():
        if k in ('material','fryer_model'):continue
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0:
            raise ValueError(f'Invalid finite nonnegative input {k}: {v!r}')
    zero_allowed={'lateral_accel_g','mass_allowance_fraction','energy_rate_krw_kwh','extra_demand_krw_month','control_kw',
                  'initial_temperature_c','feed_temperature_c','makeup_water_kg_h','heat_loss_kw','drain_hold_kg'}
    for k,v in c.items():
        if isinstance(v,(float,int)) and not v and k not in zero_allowed:raise ValueError(k+' must be positive')
    if c['material']!='SUS304' or c['supply_v']!=380 or c['supply_hz']!=60:raise ValueError('Design basis: SUS304 / 380 V 3-phase / 60 Hz')
    for k in ('raw_packing_fraction','feed_water_fraction','final_water_fraction','final_oil_fraction','motor_efficiency',
              'vfd_efficiency','gear_efficiency','motor_pf','low_speed_torque_factor','feed_utilization','max_fill_fraction',
              'powder_fill_fraction','powder_axial_efficiency','fan_efficiency','heater_efficiency','pump_efficiency','jack_efficiency'):
        if k in c and not 0<c[k]<=1:raise ValueError(k+' must be in (0,1]')
    if c['final_oil_fraction']+c['final_water_fraction']>=1:raise ValueError('No positive finished solids fraction')
    if c['feed_water_fraction']>=1:raise ValueError('Potato solids fraction must be positive')
    if min(c['safety_factor'],c['dynamic_factor'],c['service_factor'])<1:raise ValueError('Safety/dynamic/service factors must be >=1')
    if index in (7,10) and c['motor_count']!=2:raise ValueError('Geometry has two exciters')
    if index==8 and c['fan_count']!=6:raise ValueError('Geometry has six blowers')
    if index in (7,10) and not 2<=c['spring_thickness_mm']<=6:raise ValueError('Supported spring strip thickness: 2..6 mm')
    if index==6 and not c['feed_temperature_c']<=c['bath_temperature_c']<=95:raise ValueError('Blancher feed <= bath <=95 C')
    if index==9 and c['fryer_model'] not in ('PC4','PC10','PC14','PC21','PC32','PC42','PC50'):raise ValueError('Unknown PC fryer model')
    if index==9 and not c['initial_temperature_c']<100<c['oil_temperature_c']<=200:raise ValueError('Supported cold start <100 C; oil >100 and <=200 C')
    if index==9 and c['feed_temperature_c']>=100:raise ValueError('Fryer wet feed must be below boiling in this thermal model')
    if index==11 and not 38<=c['seasoning_angle_deg']<=50:raise ValueError('Seasoning inlet angle must be 38..50')
    return c


def flow_balance(c):
    feed=c['wet_flow_kg_h'];solids=feed*(1-c['feed_water_fraction'])
    chips=solids/(1-c['final_water_fraction']-c['final_oil_fraction'])
    if feed*c['feed_water_fraction']<chips*c['final_water_fraction']:raise ValueError('Moisture assumptions imply negative evaporation')
    return dict(wet_kg_h=feed,dry_solids_kg_h=solids,finished_kg_h=chips,
                oil_uptake_kg_h=chips*c['final_oil_fraction'],
                evaporated_water_kg_h=feed*c['feed_water_fraction']-chips*c['final_water_fraction'])


class Geometry(so.Geometry):
    def __init__(self,index,c):super().__init__(c);self.index=index;self.group='Welded Support Frame'
    def add(self,s,**kw):
        s.update(name=f'{self.index:02d}_'+s['name'],group=self.group,material='SUS304',density_kg_m3=self.c['steel_density_kg_m3'])
        s.update(kw);self.specs.append(s);return s
    def member(self,name,a,b,w,h=None,t=4.,**kw):
        return super().member(name,a,b,w,h,t,part_type='Welded Member',section_wall_mm=t,
                              stock_section_mm=(w,w if h is None else h,t),**kw)


def move(q,delta):
    q['origin']=core.vadd(q['origin'],delta)
    if 'profile_ends' in q:q['profile_ends']=tuple(core.vadd(p,delta) for p in q['profile_ends'])


def mirror_y(q):
    """Reflection plus local U reversal keeps the CATIA placement right-handed."""
    reflect=lambda p:(p[0],-p[1],p[2])
    q['origin']=reflect(q['origin']);u,v,n=q['axes']
    q['axes']=(core.vmul(reflect(u),-1),reflect(v),reflect(n))
    if q['kind']=='poly':
        q['points']=tuple((-x,y) for x,y in q['points'])
        q['loops']=tuple(tuple((-x,y) for x,y in loop) for loop in q.get('loops',()))
    q['holes']=tuple((-x,y,r) for x,y,r in q.get('holes',()))
    if 'profile_ends' in q:q['profile_ends']=tuple(reflect(p) for p in q['profile_ends'])


def welded_base(g,xs,half,top,leg=(80.,5.),beam=(100.,6.),inner_rails=()):
    """Butt-fitted frame: columns stop under beams, rails fit between beam faces."""
    b,t=beam;lb,lt=leg
    for x in xs:
        for side in (-1,1):
            y=side*half
            g.member(f'Base_Column_{x:g}_{side}',(x,y,20),(x,y,top-b),lb,t=lt)
            g.box(f'Base_Foot_{x:g}_{side}',(x-80,y-80,0),(160,160,20),
                  holes=((-55,-55,9),(55,-55,9),(55,55,9),(-55,55,9)))
        g.member(f'Base_Crossbeam_{x:g}',(x,-half-lb/2,top-b/2),(x,half+lb/2,top-b/2),b,t=t)
    for y in (-half,half,*inner_rails):
        for a,z in zip(xs,xs[1:]):
            g.member(f'Base_Rail_{y:g}_{a:g}',(a+b/2,y,top-b/2),(z-b/2,y,top-b/2),b,t=t)


def weld_and_assign(index,specs,c):
    """Replace old structural clamp joints with real hollow, capped weld members."""
    import build_line as b
    out=[]
    for original in specs:
        s=dict(original);name=s['name']
        if '_End_Bracket_' in name or ('_Bolt_' in name and s.get('family')=='Support_Bolts'):continue
        s.setdefault('material','SUS304');s.setdefault('density_kg_m3',c['steel_density_kg_m3'])
        group=s.get('group')
        if not group or group in ('Main Assembly','Main Structure'):
            group=b.product_group({k:v for k,v in s.items() if k!='group'})
        s['group']='Welded Support Frame' if group in ('Support Frame','Main Structure') else group
        if index==11:
            n=name.lower()
            if 'seasoning' in n or 'metering' in n or 'feeder' in n:s['group']='Seasoning Feeder'
            elif 'drum' in n or 'lifter' in n:s['group']='Seasoning Drum'
            elif 'roller' in n or 'pinion' in n:s['group']='Drum Supports and Drive'
        if s.get('part_type')=='Profile':
            w,h=s['profile_section_mm'];wall=min(4.,min(w,h)/6.)
            s['loops']=(tuple(reversed(core.rect(w-2*wall,h-2*wall))),)
            s['part_type']='Welded Member';s['section_wall_mm']=wall;s['stock_section_mm']=(w,h,wall)
            s['name']=name.removesuffix('_Profile')+'_Weldment'
            out.append(s)
            if '_Slide_Sleeve_' in name:
                s['part_type']='Adjustable Sleeve'
                continue
            for j,z in enumerate((0,s['depth']-wall)):
                cap=b.poly(s['name']+f'_Seal_Cap_{j}',core.rect(w-2*wall,h-2*wall),wall,
                           core.vadd(s['origin'],core.vmul(s['axes'][2],z)),s['axes'],s['color'])
                cap.update(group=s['group'],material='SUS304',density_kg_m3=c['steel_density_kg_m3'],
                           moving_with_hood=s.get('moving_with_hood',False));out.append(cap)
            continue
        # Spring stock is a purchased elastic element, not SUS304 structural tubing.
        if '_Spring_Pack_' in name and '_Leaf_' in name:
            s['material']='Purchased spring strip; grade and fatigue rating to be selected'
            s['density_kg_m3']=c.get('spring_density_kg_m3',7850.)
        if 'Support_Roller_' in name and s['kind']=='circle':s.update(material='Food-compatible roller polymer',density_kg_m3=1200.)
        if s['kind']=='circle' and name.endswith('_Drum') and not s.get('inner'):s['inner']=max(0,s['radius']-3.)
        out.append(s)
    names=[s['name'] for s in out]
    if len(names)!=len(set(names)):raise ValueError('Duplicate finishing part name')
    return out


def fix6(s,m,c):
    import build_line as b
    g=Geometry(6,c)
    remove=('Frame_','Foot_','Level_Screw_','06_Central_','06_Pan_Seat_',
            '06_Immersion_Dry_Drive','06_Hold_Down_Dry_Drive','06_Immersion_Motor_Pedestal',
            '06_Hold_Down_Motor_Pedestal','06_Discharge_Motor_Seat','06_Lid_Fixed_Support')
    s=[q for q in s if not q['name'].startswith(remove)]
    # Cladding reaches Z615: primary beams stop at610, floor stringers at640
    # stay entirely inside its Y envelope. Neither legs nor beams pierce the skin.
    xs=(100.,1100.,2100.,3100.,4370.)
    welded_base(g,xs,640.,610.,inner_rails=(-450.,450.))
    for x in (100.,500.,900.,1300.,1700.,2100.,2500.,2900.,3300.,3700.,4100.):
        g.member(f'Floor_Stiffener_{x:g}',(x,-500,625),(x,500,625),40,30,3.)
    # Dry drives are separated to opposite sides. Shafts and transmission move together.
    for label,x,z,bw,side in (('Immersion',3040.,806.,700.,1),('Hold_Down',2840.,946.,680.,-1)):
        prefix='06_'+label;top=1210.;chain_y=440.
        s=[q for q in s if not q['name'].startswith((prefix+'_Transmission_Shaft',prefix+'_Dry_Transmission'))]
        assembly=[]
        assembly.append(b.cylinder(prefix+'_Transmission_Shaft',(x,bw/2,z),(x,chain_y+12,z),14,b.FRAME))
        b.enclosed_chain(assembly,prefix+'_Dry_Transmission',(x,z),(x,top),chain_y)
        b.dry_side_drive(assembly,prefix+'_Dry_Drive',x,top,chain_y,505.,side_clearance=135.)
        if side<0:
            for q in assembly:mirror_y(q)
        s.extend(assembly)
        g.member(label+'_Motor_Pedestal',(x,side*640,610),(x,side*640,top-70),50,t=4.)
    # Discharge stand is outside the tank end; a welded rail carries its motor.
    mount=next(q for q in s if q['name']=='06_Discharge_Dry_Drive_Mount_Bracket')
    bb=core.bounding_box([mount]);zmount=bb['min_mm'][2]
    g.member('Discharge_Motor_Pedestal',(4383,640,610),(4383,640,zmount-20),50,t=4.)
    g.member('Discharge_Motor_Shelf',(4383,590,zmount-10),(4383,665,zmount-10),20,t=3.)
    for side in (-1,1):g.box(f'Discharge_Stand_Landing_{side}',(4330,side*385-40,610),(80,80,30))
    # Lid supports lie inside the skirts. Landing tabs bear on the rim from above.
    for x in (320.,1220.,2120.):
        for side in (-1,1):
            g.member(f'Lid_Landing_{x:g}_{side}',(x,side*490,1130),(x,side*520,1130),20,t=3.)
            g.member(f'Lid_Post_{x:g}_{side}',(x,side*490,1140),(x,side*490,1257),20,t=3.)
    # Actual round clearance for the left hold-down shaft through the lid skirt.
    for i,q in enumerate(s):
        if q['name']=='06_Fill_Pipe_Clip':
            q['depth']=45.;q['profile_ends']=(q['profile_ends'][0],(650.,500.,1070.))
        if q['name']=='06_Lid_Skirt_3_-1':
            replacement=b.poly(q['name']+'_Shaft_Clearance',core.rect(896.,115.),3.,(2548.,-505.,1202.5),core.AY,
                               holes=((2840-2548,-(1210-1202.5),22.),))
            replacement['group']='Covers';s[i]=replacement
    s.extend(g.specs)
    m.update(frame_design=dict(leg=(80.,5.),beam=(100.,6.),beam_span_mm=1360.,leg_length_mm=490.,leg_count=10,
                              max_rail_span_mm=1270.,beam_load_share=.25),
             fixes=['Welded SUS304 frame below the tank and cladding; separate internal floor stiffeners at maximum 400 mm pitch.',
                    'Opposed dry drives; lid posts offset from skirts; hold-down shaft has an actual skirt clearance hole.'],
             primary_cladding_clearance_mm=5.,floor_stiffener_pitch_mm=400.)
    return s,m


def station_geometry(index,overrides=None,analyze_meta=True,**options):
    import build_line as b
    c=configuration(index,overrides)
    fn=getattr(b,f'draft_station{index}')
    if index==9:s,m=fn(c['fryer_model'],0.,False)
    elif index==11:s,m=fn(c['seasoning_angle_deg'])
    else:s,m=fn()
    s,m=globals()[f'fix{index}'](list(s),dict(m),c)
    if index==9:
        lift=options.get('hood_lift',0.)
        if not 0<=lift<=650:raise ValueError('hood_lift must be 0..650 mm')
        for q in s:
            if q.get('moving_with_hood'):move(q,(0,0,lift))
            if options.get('hood_transparent') and q['name'].startswith(('09_Hood_Side','09_Hood_Roof','09_Hood_End')):q['transparency']=65
        m.update(hood_lift_mm=lift,hood_transparent=options.get('hood_transparent',False),
                 inlet=core.vadd(m['inlet'],(0,0,lift)),outlet=core.vadd(m['outlet'],(0,0,lift)))
    s=weld_and_assign(index,s,c)
    m.update(name=m['name'].removesuffix('_R13')+'_Welded_R13',engineering_revision=REVISION,
             engineering_inputs=c,input_sha256=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest(),
             geometry_envelope_mm=geometry_bounds(s),material='SUS304',
             joint_design='Sealed hollow SUS304 weldments; removable drives, bearings, covers and spring clamps.',
             product_structure='Equipment / functional assembly / editable native CATPart')
    return s,m


def geometry_bounds(specs):
    if any(s['kind']=='helix' for s in specs):
        import build_line
        result=build_line.model_bounds(specs)
        return dict(min_mm=result['minimum_mm'],max_mm=result['maximum_mm'],size_mm=result['size_mm'])
    return core.bounding_box(specs)


def fix_vibration(index,s,m,c):
    offset=0. if index==7 else -200.;prefix=f'{index:02d}'
    s=[q for q in s if not q['name'].startswith(('Frame_','Foot_','Level_Screw_',prefix+'_Drain_Pan_Support_'))]
    g=Geometry(index,c);top=875.+offset;pan=900.+offset
    welded_base(g,(100.,900.,1700.),380.,top)
    for x in (300.,1500.):
        g.member(f'Drain_Tray_Cross_{x:g}',(x,-380,pan-10),(x,380,pan-10),40,20,3.)
        for side in (-1,1):g.box(f'Drain_Tray_Seat_{x:g}_{side}',(x-20,side*380-20,top),(40,40,5))
    for q in s:
        name=q['name']
        if '_Spring_Pack_' in name and '_Leaf_' in name:
            move(q,core.vmul(q['axes'][2],q['depth']-c['spring_thickness_mm']))
            q['depth']=c['spring_thickness_mm']
        if name.startswith(prefix+'_Moving_Crossbeam_'):
            q['origin']=core.vadd(q['origin'],core.vmul(q['axes'][2],20.));q['depth']-=40.
            q['profile_ends']=(q['origin'],core.vadd(q['origin'],core.vmul(q['axes'][2],q['depth'])))
        if '_Mount_Stay_' in name and name.startswith(prefix+'_Vibration_Motor_'):
            q['depth']-=25.;q['profile_ends']=(q['origin'],core.vadd(q['origin'],core.vmul(q['axes'][2],q['depth'])))
    g.group='Vibrating Deck'
    for x in (760.,1090.):
        z=1220.+offset-20*x/1800
        g.member(f'Exciter_Load_Crossbeam_{x:g}',(x,-360,z-25),(x,360,z-25),40,t=4.)
    s.extend(g.specs)
    m.update(frame_design=dict(leg=(80.,5.),beam=(100.,6.),beam_span_mm=840.,leg_length_mm=top-120.,leg_count=6,
                              max_rail_span_mm=800.,beam_load_share=.40),
             fixes=['Welded sealed SUS304 fixed frame; moving deck and fixed spring mounts remain separate.',
                    'Added exciter load crossbeams; bearing stays terminate at the supporting faces; drain supports bear on the fixed rails.'],
             suspension_design='12 independent spring leaves; fixed-guided stiffness screen; actual mode shape/fatigue require supplier validation.')
    return s,m


def fix7(s,m,c):return fix_vibration(7,s,m,c)
def fix10(s,m,c):return fix_vibration(10,s,m,c)


def fix8(s,m,c):
    import build_line as b
    remove=('Frame_','Foot_','Level_Screw_','08_Central_','08_Fixed_Foot_','08_Fixed_Ground_',
            '08_Deck_Guide_','08_Cascade_Guide_','08_Lift_Guide','08_Infeed_Left','08_Infeed_Right',
            '08_Fryer_Infeed_Transition_Left','08_Fryer_Infeed_Transition_Right',
            '08_Roller_Pedestal_','08_Tray_Seat_','08_Panel_Tie_','08_Chute_Attachment_',
            '08_Full_Length_Drain_Guard','08_Full_Length_Side_Panel','08_Drip_Tray_End_Seal')
    s=[q for q in s if not q['name'].startswith(remove)]
    g=Geometry(8,c);welded_base(g,(100.,1750.,3400.),550.,780.)
    # One closed side profile follows every cascade and the previously open 70-mm gap.
    path=((0.,1200.),(940.,1200.),(1120.,1140.),(1940.,1140.),(2120.,1080.),
          (2780.,1080.),(2850.,1080.),(3180.,1200.))
    profile=tuple((x,-z+3) for x,z in path)+tuple((x,-z-120) for x,z in reversed(path))
    g.group='Continuous Product Guides'
    for side in (-1,1):
        g.poly(f'Continuous_Deck_to_Lift_Guide_{side}',profile,3.,(0,-353. if side<0 else 350.,0),core.AY)
        corners=((3180.,side*350.,1200.),(3500.,side*255.,1190.),
                 (3500.,side*255.,1310.),(3180.,side*350.,1320.))
        q=b.quad_sheet(f'08_Outlet_Taper_Guide_{side}',corners if side>0 else tuple(reversed(corners)),3.)
        q['group']=g.group;s.append(q)
    # Side drainage walls end below the bearing shelves, with ample water freeboard.
    g.group='Drainage and Guards'
    for side in (-1,1):
        profile=((0,-871),(3500,-806),(3500,-930),(0,-930))
        g.poly(f'Drain_Guard_{side}',profile,4,(0,-479 if side<0 else 475,0),core.AY)
        g.poly(f'Attached_Side_Panel_{side}',profile,3,(0,-485 if side<0 else 482,0),core.AY)
        for x in (100.,900.,1750.,2600.,3400.):
            floor=875.-65*x/3500.-4.
            # A cross-seat below the tray; all vertical risers remain outside it.
            if floor-800<12:
                g.box(f'Tray_Solid_Seat_{x:g}_{side}',(x-15,side*520-15,780),(30,30,floor-800))
            else:g.member(f'Tray_Outside_Post_{x:g}_{side}',(x,side*520,780),(x,side*520,floor-20),30,t=4.)
        for x,z in ((0,875),(3496,810)):g.box(f'Drain_End_Seal_{x}_{side}',(x,-475,z-4),(4,950,930-z+4)) if side==1 else None
    for x in (100.,900.,1750.,2600.,3400.):
        floor=875.-65*x/3500.-4.
        g.member(f'Tray_Cross_Seat_{x:g}',(x,-520,floor-10),(x,520,floor-10),30,20,3.)
    g.group='Conveyor Supports'
    drums=[q for q in s if q['name'].endswith('_Drum') and q['name'].startswith(('08_Drying_Deck','08_Discharge_Lift'))]
    for i,q in enumerate(drums):
        x,_,z=q['origin'];seat=z-48
        for side in (-1,1):
            g.member(f'Bearing_Outside_Post_{i}_{side}',(x,side*520,780),(x,side*520,seat-40),50,t=4.)
            g.member(f'Bearing_Shelf_{i}_{side}',(x,side*374,seat-20),(x,side*545,seat-20),50,40,4.)
    # Fan stands sit outside the wet tray, while sliding sleeves remain removable.
    for q in s:
        n=q['name']
        if n.startswith('08_Blower_') and ('_Adjustable_Stand_' in n or '_Slide_Sleeve_' in n):
            side=1 if q['origin'][1]>0 else -1;move(q,(0,side*120,0))
            if '_Adjustable_Stand_' in n:
                move(q,(0,0,-180));q['depth']+=180
                q['profile_ends']=(q['origin'],core.vadd(q['origin'],core.vmul(q['axes'][2],q['depth'])))
        if n.startswith('08_Blower_') and '_Plenum_Bracket_' in n:
            q['depth']+=120.;q['profile_ends']=(q['origin'],core.vadd(q['origin'],core.vmul(q['axes'][2],q['depth'])))
    for x,z in ((80.,1200.),(3300.,1196.25)):
        for side in (-1,1):
            g.member(f'Chute_Post_{x:g}_{side}',(x,side*520,780),(x,side*520,z-34),40,t=4.)
            g.member(f'Chute_Landing_{x:g}_{side}',(x,side*340,z-19),(x,side*540,z-19),40,30,4.)
    s.extend(g.specs)
    m.update(frame_design=dict(leg=(80.,5.),beam=(100.,6.),beam_span_mm=1180.,leg_length_mm=660.,leg_count=6,
                              max_rail_span_mm=1650.,beam_load_share=.40),
             fixes=['Deck and lift guides are a single continuous side profile, including X2780–2850; outlet taper joins the same edges.',
                    'Welded frame and posts are outside/below the wet tray; drainage walls stop below bearing shelves; sliding blower sleeves remain service parts.'],
             continuous_guide_path_xz_mm=path,product_guard_height_mm=120.,minimum_bearing_shelf_above_drain_mm=18.)
    return s,m


def fix9(s,m,c):
    import build_line as b
    dims=b.FRYER_MODELS[c['fryer_model']];A,B,C,D,E=(dims[k] for k in ('A','B','C','D','E'))
    half=(B-180)/2;wet=half-45;floor=min(D-570,min(D-370,E-230)-200);rim=D-90;hb=rim+30
    drive_z=rim+135;gy=half+80;rail_y=wet-45;rail_z=floor+40
    motor_x={'Lower':min(A*.70,A*.72-180),'Submerger':min(A*.69,min(A*.70,A*.72-180)-75)}
    remove=('09_Frame_','09_Foot_','09_Leveling_','09_Lower_Dry_Drive','09_Submerger_Dry_Drive',
            '09_Lower_Motor_Shelf','09_Submerger_Motor_Shelf','09_Lower_Motor_Tower','09_Submerger_Motor_Tower')
    s=[q for q in s if not q['name'].startswith(remove) and not ('09_Hood_Jack_' in q['name'] and '_Frame_Bracket' in q['name'])]
    g=Geometry(9,c);beam=140. if B<1800 else (180. if B<2300 else 220.);leg=100. if B<2300 else 120.
    wall=8. if beam<200 else 10.;frame_y=half-35;top=floor-35
    forbidden=(A*.18,A*.64,A*.20,A*.72)
    first=A*.02+100;last=A-80;count=math.ceil((last-first)/1250)
    xs=[first+(last-first)*i/count for i in range(count+1)]
    for i in range(1,len(xs)-1):
        while any(abs(xs[i]-p)<beam/2+100 for p in forbidden):xs[i]+=beam/2+100
    xs=sorted(set(xs));welded_base(g,xs,frame_y,top,leg=(leg,6.),beam=(beam,wall),inner_rails=(-wet+65,wet-65))
    # Lower the two outside ties so they do not pass through screw-jack bases.
    g.specs[:]=[q for q in g.specs if not q['name'].startswith((f'09_Base_Rail_{frame_y:g}_',f'09_Base_Rail_{-frame_y:g}_'))]
    for side in (-1,1):
        for x0,x1 in zip(xs,xs[1:]):
            g.member(f'Lower_Frame_Tie_{x0:g}_{side}',(x0+leg/2,side*frame_y,top-185-beam/2),
                     (x1-leg/2,side*frame_y,top-185-beam/2),beam,t=wall)
    stiff=[];x=A*.02+50
    while x<A*.975-20:
        if any(abs(x-p)<85 for p in (A*.18,A*.64)):x+=170;continue
        stiff.append(x)
        g.member(f'Pan_Floor_Stiffener_{x:g}',(x,-wet+10,floor-17.5),(x,wet-10,floor-17.5),40,35,4.)
        x+=400.
    # Source jack nuts were too near the hood; shift the whole jack axis out 20 mm.
    for q in s:
        n=q['name']
        if n.startswith('09_Hood_Jack_') or '09_Jack_Nut_Riser_' in n:
            side=1 if q['origin'][1]>0 else -1
            if 'Hood_Bracket' in n:
                q['depth']+=20.;q['profile_ends']=(q['origin'],core.vadd(q['origin'],core.vmul(q['axes'][2],q['depth'])))
            else:move(q,(0,side*20,0))
        if n.startswith('09_Lift_Crosshead_') and q.get('part_type')=='Profile':
            move(q,(0,-20,0));q['depth']+=40
            q['profile_ends']=(q['origin'],core.vadd(q['origin'],core.vmul(q['axes'][2],q['depth'])))
    # Rebuild the crosshead end plates are discarded during weld conversion.
    for x in (A*.20,A*.72):
        for side in (-1,1):
            # Fixed jack seat bears on the lowered outer rail, below the pan wall.
            tie_top=top-185;zseat=floor-160
            g.member(f'Jack_Base_Riser_{x:g}_{side}',(x,side*(half+5),tie_top),(x,side*(half+5),zseat-10),80,t=5.)
            g.box(f'Jack_Base_Seat_{x:g}_{side}',(x-75,side*(half+55)-90,zseat-10),(150,180,10))
    # Motor bodies/gearboxes are outside both hood side plates by at least25 mm.
    # Only a round shaft passes the wall; its hole is an actual Pocket.
    first_moving=len(g.specs)
    for label,side in (('Lower',1),('Submerger',-1)):
        x=motor_x[label]
        if side<0:
            for q in s:
                if q['name'].startswith(('09_Submerger_Inner_Extended_Shaft','09_Submerger_Lift_Transmission')):mirror_y(q)
        parts=[];chain_y=C/2+(wet-C/2)*.52
        b.dry_side_drive(parts,'09_'+label+'_Dry_Drive',x,drive_z,chain_y,wet,side_clearance=gy-wet)
        parts=[q for q in parts if not q['name'].endswith('_Mount_Bracket')]
        # Outboard mount doesn't cross the wall. Two feet support gearbox and motor.
        parts.append(b.box('09_'+label+'_Outside_Motor_Mount',(x-65,gy-55,drive_z-70),(310,110,15),b.FRAME))
        if side<0:
            for q in parts:mirror_y(q)
        for q in parts:q['moving_with_hood']=True;q['group']='Conveyor Drives'
        s.extend(parts)
        bridge_z=rim+8 # ten-mm-deep arms fit below the hood base rail, above pan rim
        for xx in (x-35,x+190):
            g.member(f'{label}_Inside_Motor_Tower_{xx:g}',(xx,side*rail_y,rail_z+20),(xx,side*rail_y,bridge_z-5),40,t=4.)
            g.member(f'{label}_Over_Rim_Motor_Arm_{xx:g}',(xx,side*rail_y,bridge_z),(xx,side*(gy+20),bridge_z),120,10,2.)
            g.member(f'{label}_Outside_Motor_Post_{xx:g}',(xx,side*gy,bridge_z+5),(xx,side*gy,drive_z-70),40,t=4.)
    for q in g.specs[first_moving:]:q['moving_with_hood']=True;q['group']='Conveyor Drives'
    for i,q in enumerate(s):
        if q['name'] in ('09_Hood_Side_1','09_Hood_Side_-1'):
            side=1 if q['name'].endswith('_1') else -1
            x0=A*.055;x1=A*.85;z0=hb+12.5;z1=D+260;xc=(x0+x1)/2;zc=(z0+z1)/2
            x=motor_x['Lower' if side>0 else 'Submerger']
            bottom=[(x0,z0)]
            for jx in (A*.20,A*.72):bottom.extend(((jx-25,z0),(jx-25,hb+145),(jx+25,hb+145),(jx+25,z0)))
            outline=tuple((px-xc,-(pz-zc)) for px,pz in (*bottom,(x1,z0),(x1,z1),(x0,z1)))
            new=b.poly(q['name']+'_Shaft_Clearance',outline,3.,
                       (xc,half+7 if side>0 else -half-10,zc),core.AY,holes=((x-xc,-(drive_z-zc),22.),))
            new.update(moving_with_hood=True,group='Hood and Exhaust');s[i]=new
    s.extend(g.specs)
    m.update(frame_design=dict(leg=(leg,6.),beam=(beam,wall),beam_span_mm=2*frame_y+leg,
               leg_length_mm=top-beam-20,leg_count=2*len(xs),max_rail_span_mm=max(z-a for a,z in zip(xs,xs[1:])),beam_load_share=2/len(xs)),
             fixes=['Lower and submerger drives moved to opposite sides; motor/fan envelopes clear hood by25 mm; separate Ø44 shaft openings.',
                    'Motor mounts are outboard, with over-rim welded arms clear of both pan and hood. Fixed frame and lifting cassette remain separate.',
                    'Welded pan support frame and jack seats added; legs/rails do not pierce the pan cladding.'],
             motor_side_clearance_mm=25.,drive_axes_y_mm=(gy,-gy),floor_stiffener_pitch_mm=max(z-a for a,z in zip(stiff,stiff[1:])),
             frame_support_x_mm=xs)
    return s,m


def floor_height(specs,x,y):
    """Vertical intersection with actual triangulated chute pad faces, lower Z."""
    hits=[]
    for q in specs:
        if q['kind']!='poly':continue
        u,v,n=q['axes']
        if abs(n[2])<1e-8:continue
        for depth in (0.,q['depth']):
            o=core.vadd(q['origin'],core.vmul(n,depth))
            pts=[core.vadd(o,core.vadd(core.vmul(u,a),core.vmul(v,b))) for a,b in q['points']]
            for i in range(1,len(pts)-1):
                tri=(pts[0],pts[i],pts[i+1]);signs=[]
                for a,b in zip(tri,tri[1:]+tri[:1]):signs.append((b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]))
                if min(signs)>=-1e-6 or max(signs)<=1e-6:
                    hits.append(o[2]-(n[0]*(x-o[0])+n[1]*(y-o[1]))/n[2]);break
    if not hits:raise ValueError(f'No chute support surface at {x:g}, {y:g}')
    return min(hits)


def fix11(s,m,c):
    import build_line as b
    remove=('Frame_','Foot_','Level_Screw_','S11_Roller_Frame_Cross_', 'S11_Main_Gearbox_Shelf',
            'S11_Infeed_Leg_','S11_Infeed_Foot_','S11_Discharge_Support_','S11_Discharge_Foot_',
            'S11_Seasoning_Hopper_Stand_','S11_Hopper_Foot_','S11_Seasoning_Flight_')
    s=[q for q in s if not q['name'].startswith(remove)]
    g=Geometry(11,c);g.group='Drum Support Frame'
    # Roller base bottom defines each crossbeam TOP. Direct columns reach the floor.
    portal_tops=[]
    for x in (510.,1970.):
        rr=340+100*(x-340)/1800+75;z=1240-rr*math.sqrt(3)/2;top=z-96;xx=x+1350
        portal_tops.append(top)
        g.member(f'Roller_Load_Crossbeam_{x:g}',(xx,-565,top-50),(xx,565,top-50),250,100,6.)
        for side in (-1,1):
            g.member(f'Roller_Ground_Column_{x:g}_{side}',(xx,side*525,20),(xx,side*525,top-100),80,t=5.)
            g.box(f'Roller_Ground_Foot_{x:g}_{side}',(xx-80,side*525-80,0),(160,160,20))
    for side in (-1,1):
        g.member(f'Drum_Lower_Tie_{side}',(1900,side*525,300),(3280,side*525,300),80,t=5.)
    # Independent grounded drive platform; it does not rely on an elevated free stay.
    g.group='Drum Drive Platform'
    for x in (1930.,2150.):
        for y in (-950.,-500.):
            g.member(f'Drive_Platform_Column_{x:g}_{y:g}',(x,y,20),(x,y,1035),60,t=4.)
            g.box(f'Drive_Platform_Foot_{x:g}_{y:g}',(x-60,y-60,0),(120,120,20))
    g.box('Drive_Platform_Deck',(1880,-1040,1035),(330,625,15))
    g.box('Drive_Motor_Saddle',(1955,-925,1050),(160,250,25))
    g.member('Control_Ground_Post',(1565,-575,20),(1565,-575,1070),60,t=4.)
    g.box('Control_Ground_Foot',(1500,-640,0),(130,130,20))
    # Infeed legs end below sloping rail seats. Fitted wedges close the slope gap.
    g.group='Chip Infeed Support'
    slope=-60/1770;normal=core.vunit((60/1770,0,1));nz=normal[2]
    for x in (200.,950.,1550.):
        for side in (-1,1):
            y=side*130;zunder=lambda xx:1100+slope*xx-60.5/nz
            za=lambda xx:zunder(xx)-6/nz
            low=min(za(x-22.5),za(x+22.5))
            g.member(f'Infeed_Column_{x:g}_{side}',(x,y,20),(x,y,low),45,t=4.)
            g.box(f'Infeed_Ground_Foot_{x:g}_{side}',(x-65,y-65,0),(130,130,20))
            g.quad(f'Infeed_Sloped_Seat_{x:g}_{side}',((x-40,y-40,zunder(x-40)),(x+40,y-40,zunder(x+40)),
                   (x+40,y+40,zunder(x+40)),(x-40,y+40,zunder(x-40))),6.)
            g.poly(f'Infeed_Fitted_Wedge_{x:g}_{side}',((x-22.5,-low),(x-22.5,-za(x-22.5)),(x+22.5,-low)),45,
                   (0,y-22.5,0),core.AY)
    # Powder hopper, screw and motor share a grounded welded platform.
    g.group='Seasoning Feeder Support'
    welded_base(g,(630.,1370.),240.,1630.,leg=(80.,5.),beam=(100.,6.))
    g.box('Feeder_Platform',(580,-280,1630),(840,560,10))
    for x in (1015.,1345.):
        for side in (-1,1):g.member(f'Hopper_Riser_{x:g}_{side}',(x,side*185,1640),(x,side*185,1740),40,t=4.)
    g.box('Metering_Motor_Saddle',(600,-45,1640),(190,90,18))
    flights=[];b.auger(flights,'S11_Powder_Metering',(1006.,0.,1715.),(1414.,0.,1715.),28.,32.,12.,2.)
    for q in flights:
        if q['kind']=='helix':q.update(group='Seasoning Feeder',normal_thickness=True);s.append(q)
    # No beam crosses the open discharge. Two low portals carry fitted side webs.
    g.group='Discharge Support'
    lip=b.plate_between('S11_Extended_Discharge_Landing',(3790.,0.,740.),(3870.,0.,740.),500.,4.)
    lip['group']='Outfeed';s.append(lip)
    for side in (-1,1):
        corners=((3790.,side*250,740),(3870.,side*250,740),(3870.,side*250,890),(3790.,side*250,890))
        q=b.quad_sheet(f'S11_Discharge_Landing_Guide_{side}',corners if side>0 else tuple(reversed(corners)),4.);q['group']='Outfeed';s.append(q)
    welded_base(g,(3550.,3830.),350.,650.,leg=(80.,5.),beam=(80.,5.))
    floors=[q for q in s if 'S11_Continuous_Discharge_' in q['name'] or q['name']=='S11_Extended_Discharge_Landing']
    for side in (-1,1):
        y=side*200;xx=[3550+i*10 for i in range(29)]
        # A small fabrication seam clearance is explicit; no web passes through the tray.
        top=[(x,min(floor_height(floors,px,py) for px in (x-2,x+2) for py in (y-4,y+4))-.5) for x in xx]
        profile=((xx[0],-650),(xx[-1],-650))+tuple((x,-z) for x,z in reversed(top))
        g.poly(f'Discharge_Fitted_Support_Web_{side}',profile,8.,(0,y-4,0),core.AY)
    s.extend(g.specs)
    m.update(outlet=(3870.,0.,740.),length=3870.,
             frame_design=dict(leg=(80.,5.),beam=(250.,100.,6.),beam_span_mm=1130.,leg_length_mm=max(portal_tops)-120,
                               leg_count=4,max_rail_span_mm=1460.,beam_load_share=.5),
             fixes=['Roller crossbeams now bear directly on ground columns; beam tops meet the roller base plates.',
                    'Removed the high discharge cross-member. Low portals and fitted webs support the chute from below; exit extended80 mm.',
                    'Grounded infeed seats, motor platform and powder-feeder platform replace unsupported stays. Structural connections are welded.',
                    'Powder metering paddles replaced with editable native Rib quarter-helices to match the screw capacity calculation.'],
             discharge_support_top_z_mm=650.,discharge_floor_min_z_mm=736.,support_web_weld_gap_min_mm=.5,
             roller_portal_top_z_mm=portal_tops)
    return s,m


def analyze(index,overrides=None,specs=None,meta=None):
    if index==5:
        from slicer_review import calculations
        return calculations(overrides)
    c=configuration(index,overrides)
    if specs is None or meta is None:specs,meta=station_geometry(index,c,analyze_meta=False)
    return analyze_process(index,c,specs,meta)


def finalize(r):
    c=r['inputs'];hours=c['operating_hours_day']*c['days_month']
    r['monthly_energy_kwh']=r['estimated_running_kw']*hours+r.get('daily_startup_kwh',0)*c['days_month']
    r['monthly_cost_krw']=r['monthly_energy_kwh']*c['energy_rate_krw_kwh']+c['extra_demand_krw_month']
    r['warnings']=[x['name']+': 재선정 필요' for x in r['checks'] if x['utilization']>1]
    r['input_sha256']=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()
    r['status']='가정에 따른 예비 설계 — 제작 승인 또는 실제 CATIA 간섭 검증 아님'
    return r


def analyze_process(index,c,specs,meta):
    import peeler_design
    f=flow_balance(c);details=[];checks=[];drives=[];thermal=[];pending=[]
    def row(label,value,unit='',basis='설계 가정 또는 코드 형상에서 계산'):
        details.append(dict(label=label,value=value,unit=unit,basis=basis))
    def check(name,value,limit,unit,basis):
        checks.append(dict(name=name,demand=value,limit=limit,unit=unit,basis=basis,
                           utilization=value/limit,result='계산조건 충족' if value<=limit else '재선정 필요'))
    def motor(label,rpm,torque,kw,ratio):
        nr=rpm*ratio;hz=nr/c['motor_base_rpm']*60
        available=kw*9550/c['motor_base_rpm']*ratio*c['gear_efficiency']*c['low_speed_torque_factor']
        required=torque*c['service_factor']
        check(label+' 출력축 토크',required,available,'N·m','기동 요구토크×서비스계수 ≤ 모터 정격토크×총 감속비×효율×저속 보정')
        check(label+' 모터 회전수',nr,c['motor_base_rpm'],'rpm','60 Hz 기저 속도 이하; 실제 VFD 열적 한계는 구매 검토')
        drives.append(dict(name=label,output_rpm=rpm,motor_rpm=nr,hz=hz,required_torque_nm=required,
                           available_torque_nm=available,motor_kw=kw,ratio=ratio))
    bom=[];mom=[0.,0.,0.];groups=defaultdict(float)
    for s in specs:
        mass,cg,volume,_=peeler_design.mass_info(s,c)
        basis='explicit purchased estimate' if 'mass_override_kg' in s else 'model net volume × specified density'
        bom.append(dict(name=s['name'],group=s['group'],mass_kg=mass,basis=basis,volume_m3=volume))
        groups[s['group']]+=mass
        for j in range(3):mom[j]+=mass*cg[j]
    base=sum(x['mass_kg'] for x in bom);dead=base*(1+c['mass_allowance_fraction']);cg=[x/base for x in mom]
    flow=f['wet_kg_h'] if index<=9 else f['finished_kg_h']
    rho=c['wet_slice_bulk_density_kg_m3'] if index<=9 else c['chip_bulk_density_kg_m3']
    liquid=0.;startup=0.;extra_nameplate=0.;thermal=[]
    allmass={x['name']:x['mass_kg'] for x in bom}
    if index==6:
        internal=(4200.,1000.,475.);water_vol=4.2*1.*.345;limit_vol=4.2*.435
        liquid=limit_vol*1000.;normal_water=water_vol*c['water_density_kg_m3']
        speed=2.540/c['residence_min'];length=2.54+.14+math.hypot(1.190,.375)
        hold=flow/60*length/speed;blocked=length*.7*c['max_bed_height_mm']/1000*rho
        bed=flow/(60*speed*.7*rho)*1000
        check('벨트 제품 층높이',bed,c['max_bed_height_mm'],'mm','Q/(60 v b ρbulk); 상부 벨트 하부 간극을 고려한 운전 제한')
        row('탱크 내부 L × W × H',' × '.join(f'{x:g}' for x in internal),'mm')
        row('기준 수위 / 내측 바닥', '990 / 645','mm')
        row('물 공간 총용적 상한',water_vol,'m³','내부 기구 체적 미차감; 실제 충전량은 레벨 보정')
        row('기준 운전 물 질량',normal_water,'kg');row('월류 전 수위',1080.,'mm','출구 벨트 노치 하단')
        row('잠김 구간 체류시간',c['residence_min'],'min');row('컨베이어 동기 속도',speed,'m/min')
        row('계산 제품 층높이',bed,'mm');row('외장-주 프레임 수직 여유',5.,'mm')
        belt_mass=sum(x['mass_kg'] for x in bom if '_MeshTile_' in x['name'])
        pull=c['running_resistance']*(hold+belt_mass)*G+150.
        for label,D in (('Immersion belt',.070),('Hold-down belt',.060),('Discharge belt',.070)):
            # Conservatively apply total moving belt/product load to each drive.
            force=pull*c['breakaway_factor']+(hold+belt_mass)*speed/60/c['start_seconds']
            if label=='Discharge belt':force+=hold*G*math.sin(math.atan2(.375,1.19))
            motor(label,speed/(math.pi*D),force*D/2,c['conveyor_motor_kw'],c['conveyor_ratio'])
        heat=(flow*c['food_cp_kj_kgk']+c['makeup_water_kg_h']*4.18)*(c['bath_temperature_c']-c['feed_temperature_c'])/3600+c['heat_loss_kw']
        heat_input=heat/c['heater_efficiency']
        warm_energy=(normal_water*4.18+dead*.50)*(c['bath_temperature_c']-c['feed_temperature_c'])/3600
        warm_kw=(warm_energy/(c['warmup_minutes']/60)+c['heat_loss_kw'])/c['heater_efficiency']
        check('히터 정상 열부하',heat_input,c['heater_kw'],'kW','감자+보충수 현열+입력 열손실 / 히터 효율')
        check('히터 냉간 기동 열부하',warm_kw,c['heater_kw'],'kW','물+전체 기계 자중의 현열을 목표 예열시간으로 나눔; 전체 자중 가열은 보수적')
        installed=3*c['conveyor_motor_kw'];running=heat_input+3*(pull*speed/60/1000/(c['gear_efficiency']*c['motor_efficiency']*c['vfd_efficiency'])+.06)+c['control_kw']
        extra_nameplate=c['heater_kw'];startup=(warm_kw+.3)*c['warmup_minutes']/60
        row('정상 히터 전기입력',heat_input,'kW');row('냉간 예열 시간',c['warmup_minutes'],'min')
        row('예열 전기입력',warm_kw,'kW');row('예열 1회 전력량',startup,'kWh')
        pressure=1000*G*.435*c['dynamic_factor']/1e6
        check('탱크 바닥판 굽힘',.75*pressure*400**2/5**2,c['yield_mpa']/c['safety_factor'],'MPa','t5, 하부 실제 보강 간격 최대400; 등분포 수압 상한')
        thermal=['히터는 총 120 kW 잠정 전기 가열 사양이다. 3개 히터 외형은 개념도이며 실제 표면 열유속·단자·배관·온도 제한은 구매 설계가 필요하다.',
                 '정상 생산 8시간/일과 별도로 매일 냉간 예열 1회를 가정해 월 전력량에 가산했다. 전날 온수를 유지하면 실제 예열 전력량은 낮아진다.']
        pending=['블랜칭 온도·체류시간에 따른 색상·조직·효소 불활성 시험','히터 표면 열유속·수위 인터록·과열차단','수밀 용접·배수·팽창 변위 및 열교']
    elif index in (7,10):
        width=.7 if index==7 else .510;length=1.620;speed=c['conveying_speed_m_min']
        hold=flow/60*length/speed;blocked=length*width*c['max_bed_height_mm']/1000*rho;liquid=c['drain_hold_kg']
        bed=flow/(60*speed*width*rho)*1000
        check('제품 층높이',bed,c['max_bed_height_mm'],'mm','Q/(60 v b ρbulk), v는 경험적 이송속도 입력')
        moving_names=('Perforated_Screen','Moving_','Raised_Product_Guard','Product_Guard','Vibration_Motor_','Exciter_Load_Crossbeam','Infeed','Outfeed')
        moving=sum(x['mass_kg'] for x in bom if any(k in x['name'] for k in moving_names))+hold
        leaves=[q for q in specs if '_Spring_Pack_' in q['name'] and '_Leaf_' in q['name']]
        lengths=[max(x for x,y in q['points'])-min(x for x,y in q['points']) for q in leaves]
        L=sum(lengths)/len(lengths);b=60.;t=c['spring_thickness_mm'];Es=c['spring_E_mpa']
        stiffness=len(leaves)*Es*b*t**3/L**3 # N/mm, fixed-guided leaves, independent layers
        fn=math.sqrt(stiffness*1000/moving)/(2*math.pi);frequency=c['vibration_hz'];omega=2*math.pi*frequency
        a=c['amplitude_mm']/1000;ratio=frequency/fn;zeta=c['damping_ratio']
        force=moving*omega**2*a*math.sqrt((1-1/ratio**2)**2+(2*zeta/ratio)**2)
        trans=math.sqrt(1+(2*zeta*ratio)**2)/math.sqrt((1-ratio**2)**2+(2*zeta*ratio)**2)
        transmitted=force*trans
        # Resolve gravity into the compliant leaf-normal direction conservatively.
        normal_vertical=70./L;static_def=moving*G*normal_vertical/stiffness
        leafstress=3*Es*t*(static_def+c['amplitude_mm'])/L**2
        check('진동기 원심력 합',force*c['service_factor'],c['motor_count']*c['exciter_force_n_each'],'N',
              'F=M ω² A × 동적 임피던스 보정; 서비스계수 포함, 구매 시 원심력/주파수 확인')
        check('스프링 굽힘 예비 선별',leafstress,c['spring_allowable_mpa'],'MPa',
              '고정-가이드 판스프링 σ=3 E t δ/L²; 정적 법선 처짐+진폭. 150 MPa는 잠정 선별치, 피로인증값 아님')
        check('운전/고유진동수 분리',3.,ratio,'비율','운전 주파수/고유진동수 ≥3을 예비 목표로 채택; 다자유도/기동 공진 별도')
        check('베이스 진동 전달력 여유',transmitted,(c['dynamic_factor']-1)*(dead+blocked+liquid)*G,'N',
              '전달력 상한을 기존 수직 동하중 할증분과 비교; 실제 기초 반력 측정으로 보정')
        installed=c['motor_count']*c['motor_kw_each'];running=installed*c['motor_input_load_fraction']/(c['motor_efficiency']*c['vfd_efficiency'])+c['control_kw']
        rpm=frequency*60;nominal=c['motor_kw_each']*9550/rpm
        drives.append(dict(name='Twin counter-rotating exciters',output_rpm=rpm,motor_rpm=rpm,hz=frequency*2,
                           required_torque_nm='원심력 기준 선정',available_torque_nm=nominal,motor_kw=installed,ratio=1.))
        row('유효 트레이 L × W',f'{length*1000:g} × {width*1000:g}','mm');row('이송속도 가정',speed,'m/min')
        row('정상 체류시간',length/speed*60,'s');row('계산 제품 층높이',bed,'mm');row('이동 질량 (제품 포함)',moving,'kg')
        row('편진폭 / 주파수',f'{c["amplitude_mm"]:g} / {frequency:g}','mm / Hz');row('가속도 진폭',omega**2*a/G,'g')
        row('스프링 유효 길이',L,'mm');row('스프링 수 / 폭 / 두께',f'{len(leaves)} / {b:g} / {t:g}','개 / mm / mm')
        row('스프링 합성 강성',stiffness,'N/mm');row('단자유도 고유진동수',fn,'Hz')
        row('원심력 요구 (서비스계수 포함)',force*c['service_factor'],'N');row('베이스 전달력 근사',transmitted,'N')
        row('모터별 최소 원심력 구매요구',c['exciter_force_n_each'],'N/대');row('예상 누적 진동 횟수 / 월',frequency*3600*c['operating_hours_day']*c['days_month'],'회')
        pending=['진동속도→kg/min는 제품 마찰·낙하·점착 실험으로 보정; 진동수만으로 처리량 확정 불가',
                 '구매 스프링 강종·열처리·피로곡선·클램프 프리로드·공진 및 실제 진동 방향 확인',
                 '진동기 2대의 대칭 설치·동기화·정격 원심력 확인; 외형으로 전기 정격을 확정하지 않음']
    elif index==8:
        width=.7;speed=c['conveying_speed_m_min'];length=3.18
        hold=flow/60*length/speed;blocked=length*width*c['max_bed_height_mm']/1000*rho
        bed=flow/(60*speed*width*rho)*1000
        check('제품 층높이',bed,c['max_bed_height_mm'],'mm','Q/(60 v b ρbulk); 공기 건조 성능은 별도 실측')
        belt_mass=sum(x['mass_kg'] for x in bom if '_MeshTile_' in x['name'])
        pull=c['running_resistance']*(hold+belt_mass)*G+50.
        for i in range(4):
            force=pull*c['breakaway_factor']+(hold+belt_mass)*speed/60/c['start_seconds']
            if i==3:force+=hold*G*math.sin(math.atan2(.12,.33))
            motor('Dryer conveyor '+str(i+1),speed/(math.pi*.07),force*.035,c['conveyor_motor_kw'],c['conveyor_ratio'])
        q=c['fan_flow_m3_h_each']/3600.;fan_shaft=q*c['fan_pressure_pa']/1000/c['fan_efficiency']
        check('블로어 1대 축동력',fan_shaft,c['fan_motor_kw'],'kW','P=Q Δp/ηfan; 동일 유량·압력에서의 실제 팬 곡선 확인 필요')
        installed=4*c['conveyor_motor_kw']+c['fan_count']*c['fan_motor_kw']
        running=c['fan_count']*fan_shaft/(c['motor_efficiency']*c['vfd_efficiency'])+4*(pull*speed/60/1000/(c['gear_efficiency']*c['motor_efficiency']*c['vfd_efficiency'])+.05)+c['control_kw']
        row('주 이송 폭 / 유효 길이','700 / 3180','mm');row('최종 배출 폭',510.,'mm')
        row('이송 속도',speed,'m/min');row('전체 체류시간 근사',length/speed*60,'s');row('계산 제품 층높이',bed,'mm')
        row('가이드 높이 / 연결 구간','120 / X2780–2850','mm');row('블로어 수',c['fan_count'],'대')
        row('블로어 1대 요구 유량',c['fan_flow_m3_h_each'],'m³/h');row('블로어 요구 정압',c['fan_pressure_pa'],'Pa')
        row('노즐 속도 근사',q/(.680*.024),'m/s','공칭 680×24 mm 슬릿, 압축성·누설 무시')
        pending=['6개 팬의 유량-정압 곡선과 230 mm 외형 호환 확인; 동력만으로 풍량 보장 불가',
                 '진입 수분·표면 잔류수·공기 습도/온도 실측 후 건조율과 체류시간 확정',
                 '강한 바람에서 칩 비산 여부 확인 및 가이드 상부 망/커버 필요성 판단']
    elif index==9:
        import build_line as b
        d=b.FRYER_MODELS[c['fryer_model']];A,B,C,D,E=(d[k] for k in ('A','B','C','D','E'))
        wet=(B-180)/2-45;floor=min(D-570,min(D-370,E-230)-200);oil=min(D-280,E-140)
        inner_length=A*.955-12;inner_width=2*wet-12;depth=oil-floor-6
        oil_volume=inner_length*inner_width*depth/1e9
        normal_oil=oil_volume*c['oil_density_kg_m3']
        overflow=E-90;liquid=inner_length*inner_width*(overflow-floor-6)/1e9*1000
        # Water/CIP-filled abnormal case bounds the lower-density cooking-oil mass.
        carrier=min(A*.70,A*.72-180)-A*.15;speed=carrier/1000/c['residence_min']
        out_length=math.hypot(A*.28-80,E+15-(min(D-370,E-230)+8))/1000
        out_speed=speed*35/55 # lower and discharge sprockets are equal in this CAD
        hold=flow*c['residence_min']/60+f['finished_kg_h']/60*out_length/out_speed
        blocked=carrier/1000*C/1000*c['max_bed_height_mm']/1000*rho+out_length*C/1000*.08*c['chip_bulk_density_kg_m3']
        bed=flow/(60*speed*C/1000*rho)*1000
        check('잠김 벨트 제품 층높이',bed,c['max_bed_height_mm'],'mm','젖은 슬라이스 체적 유량 / 벨트 속도·폭')
        rated_lb={'PC4':400.,'PC10':1000.,'PC14':1400.,'PC21':2100.,'PC32':3200.,'PC42':4200.,'PC50':5000.}
        check('완제품 목표 / 해당 PC 참고 정격',f['finished_kg_h'],rated_lb[c['fryer_model']]*.45359237,'kg/h',
              '제조사 모델별 lb/h 완제품 표기 환산; 본 추정 내부 구조의 성능 인증 아님')
        moving_belt=sum(x['mass_kg'] for x in bom if '_MeshTile_' in x['name'])
        pull=c['running_resistance']*(hold+moving_belt)*G+250.
        for label,diameter in (('Lower and coupled outfeed',.110),('Submerger',.100)):
            start=pull*c['breakaway_factor']+(hold+moving_belt)*speed/60/c['start_seconds']+hold*G*.25
            motor(label,speed/(math.pi*diameter),start*diameter/2,c['conveyor_motor_kw'],c['conveyor_ratio'])
        sensible=flow*c['food_cp_kj_kgk']*(100-c['feed_temperature_c'])/3600
        evaporation=f['evaporated_water_kg_h']*c['evaporation_kj_kg']/3600
        solids_heat=f['dry_solids_kg_h']*c['solids_cp_kj_kgk']*(c['oil_temperature_c']-100)/3600
        oil_heat=f['oil_uptake_kg_h']*c['oil_cp_kj_kgk']*(c['oil_temperature_c']-c['initial_temperature_c'])/3600
        duty=(sensible+evaporation+solids_heat+oil_heat+c['heat_loss_kw'])*c['thermal_reserve']
        heater_input=duty/c['heater_efficiency']
        warm_energy=(normal_oil*c['oil_cp_kj_kgk']+dead*.50)*(c['oil_temperature_c']-c['initial_temperature_c'])/3600
        warm_input=(warm_energy/(c['warmup_minutes']/60)+c['heat_loss_kw'])/c['heater_efficiency']
        check('외부 히터 정상 전기입력',heater_input,c['heater_kw'],'kW','감자 현열+증발 잠열+고형분/보충유 현열+손실, 열 여유계수 및 효율 적용')
        check('외부 히터 예열 입력',warm_input,c['heater_kw'],'kW','오일과 전체 기계 자중 현열 / 예열시간; 전체 자중 가열 가정은 보수적')
        pump_q=oil_volume/c['oil_turnover_min']/60
        pump_shaft=c['oil_density_kg_m3']*G*pump_q*c['pump_head_m']/1000/c['pump_efficiency']
        check('외부 순환 펌프 축동력',pump_shaft,c['pump_motor_kw'],'kW','ρ g Q H/η; 헤드에 필터·열교환기 손실을 포함한다고 가정, 실제 회로 곡선 필요')
        lifting=sum(allmass[q['name']] for q in specs if q.get('moving_with_hood'))*1.15+hold
        jack_load=lifting*G*.40*c['service_factor']
        check('단일 리프트 잭 하중',jack_load,c['jack_rated_load_n'],'N','4개 중1개에40% 분담, 기동 서비스계수; 동기화 및 유지 잠금 별도')
        lift_t=jack_load*(c['jack_lead_mm']/1000)/(2*math.pi*c['jack_efficiency'])
        lift_power=lifting*G*c['lift_speed_mm_s']/1000/1000/c['jack_efficiency']
        check('리프트 모터 축동력',lift_power*c['service_factor'],c['lift_motor_kw'],'kW','M g v/ηjack, 서비스계수 적용; 감속기·잭 입력축 토크 별도 확인')
        # Motor mounting arm is rectangular 120x10x2; two arms carry one drive.
        armI=(120*10**3-116*6**3)/12;armZ=armI/5
        drive_weight=max(sum(allmass[q['name']] for q in specs if q['name'].startswith('09_'+label+'_Dry_Drive')) for label in ('Lower','Submerger'))
        armF=drive_weight*G*c['dynamic_factor']/2;armL=190.
        check('모터 외측 받침 굽힘',armF*armL/armZ,c['yield_mpa']/c['safety_factor'],'MPa','120×10×2 받침팔 두 개, 모터/감속기 형상 질량 분담; 190 mm 외팔 상한')
        installed=2*c['conveyor_motor_kw']+c['pump_motor_kw']+c['exhaust_motor_kw']+c['lift_motor_kw']
        running=heater_input+pump_shaft/(c['motor_efficiency']*c['vfd_efficiency'])+c['exhaust_motor_kw']*.7/(c['motor_efficiency']*c['vfd_efficiency'])+2*(pull*speed/60/1000/(c['gear_efficiency']*c['motor_efficiency']*c['vfd_efficiency'])+.08)+c['control_kw']
        extra_nameplate=c['heater_kw'];startup=(warm_input+pump_shaft/(c['motor_efficiency']*c['vfd_efficiency']))*c['warmup_minutes']/60
        row('탱크 내부 L × W × 운전 오일 깊이',f'{inner_length:g} × {inner_width:g} × {depth:g}','mm')
        row('오일 공간 총용적 상한',oil_volume,'m³','내부 기구 미차감, 실제 충전량은 레벨 시운전으로 보정')
        row('운전 오일 질량 상한',normal_oil,'kg');row('튀김 체류시간',c['residence_min'],'min');row('동기 벨트 속도',speed,'m/min')
        row('연동 배출 벨트 속도',out_speed,'m/min','동일 스프로킷 비에서 드럼 반지름35/55 적용; 하부/상부 잠김 벨트는 독립 VFD 동기')
        check('배출 칩 층높이',f['finished_kg_h']/(60*out_speed*C/1000*c['chip_bulk_density_kg_m3'])*1000,80.,'mm','연동 배출 속도와 튀김 후 칩 밀도 적용')
        row('투입 제품 층높이',bed,'mm');row('완제품 유량',f['finished_kg_h'],'kg/h')
        row('증발수',f['evaporated_water_kg_h'],'kg/h');row('증발 잠열 부하',evaporation,'kW')
        row('외부 히터 정상 요구 입력',heater_input,'kW');row('외부 히터 설치 입력',c['heater_kw'],'kW')
        row('순환 오일 유량',pump_q*3600,'m³/h');row('DN80 포트 평균 유속 근사',pump_q/(math.pi*.036**2),'m/s','모델 내경72 mm; 실제 배관 압력손실/흡입 NPSH 검토 필요')
        row('들어 올리는 질량',lifting,'kg');row('잭1개 요구 입력 토크',lift_t,'N·m')
        row('모터-후드 측면 최소 공칭 여유',25.,'mm');row('냉간 예열 1회 전력량',startup,'kWh')
        thermal=['9번은 PC4 외형을 기본으로 한 예비 설계이며, Baixin의 다른 120 kW 튀김기 정격을 그대로 가져오지 않았다. 수분 증발을 포함해 외부 히터를 다시 산정했다.',
                 '히터·순환펌프·필터·배기팬 및 잭 구동 모터는 외부/구매 시스템 사양이다. CAD에 외부 스키드의 확정 형상과 배선까지 그렸다는 뜻이 아니다.',
                 '정상 생산 시간 외에 매일 냉간 예열 1회분을 월 전력량에 추가했다. 실제 단열·배기·오일 여과 조건에 따라 열손실을 다시 입력해야 한다.']
        pending=['고온 SUS304 및 용접부 허용응력·열팽창, 오일 누유·화재·수분 유입 방지와 온도/레벨 인터록 상세 설계',
                 '오일 점도·필터 막힘·NPSH·배관 손실·펌프 곡선 확인; 내경72 mm 포트의 실제 유속/손실 재검토',
                 '리프트 동기화·기계식 유지 잠금·잭 좌굴·추락 방지·정비 중 인터록',
                 '모터/감속기 실제 구매 외형·베어링 반력·축 씰 및 후드 관통부의 위생/증기 차폐 상세']
    elif index==11:
        r0=.334;r1=.434;length=1.8;volume=math.pi*length*(r0*r0+r0*r1+r1*r1)/3
        hold=flow*c['residence_min']/60;blocked=volume*c['max_fill_fraction']*rho
        fill=hold/(volume*rho)
        check('드럼 제품 충전율',fill,c['max_fill_fraction'],'체적비','체류시간×완제품 유량 / 드럼 내부 용적 / 칩 벌크 밀도')
        drum=sum(x['mass_kg'] for x in bom if any(k in x['name'] for k in ('Expanding_Open_Drum','Tapered_Lifter','Open_Rim','S11_Drive_Ring')))
        rolling=(drum+hold)*G*c['rolling_resistance']*.4
        lift=hold*G*.30;J=drum*.4**2;accel=J*(c['drum_rpm']*2*math.pi/60)/c['start_seconds']
        drum_start=(rolling+lift+15)*c['breakaway_factor']+accel
        ratio=c['drum_gear_ratio']*c['drum_ring_pitch_radius_mm']/c['pinion_radius_mm']
        motor('Seasoning drum',c['drum_rpm'],drum_start,c['drum_motor_kw'],ratio)
        line=.190*c['infeed_bed_height_mm']/1000*rho;speed=flow/(60*line)
        in_mass=line*1.77;pull=c['running_resistance']*(in_mass+20)*G+40.
        motor('Chip infeed',speed/(math.pi*.076),pull*.038*c['breakaway_factor'],c['infeed_motor_kw'],c['infeed_gear_ratio'])
        powder=flow*c['seasoning_fraction'];area=math.pi*(.028**2-.012**2)
        per_rev=area*.032*c['powder_fill_fraction']*c['powder_axial_efficiency']*c['powder_bulk_density_kg_m3']
        rpm=powder/(per_rev*60)
        powder_hold=area*.408*c['powder_fill_fraction']*c['powder_bulk_density_kg_m3']
        feeder_t=c['feeder_empty_nm']+.35*powder_hold*G*.028
        motor('Powder metering screw',rpm,feeder_t*c['breakaway_factor'],c['feeder_motor_kw'],c['feeder_gear_ratio'])
        hopper_volume=.374*.424*.430;powder_store=hopper_volume*.85*c['powder_bulk_density_kg_m3']
        blocked+=powder_store+1.77*.190*.100*rho
        installed=c['drum_motor_kw']+c['infeed_motor_kw']+c['feeder_motor_kw']
        shaft_kw=(rolling+lift+15)*2*math.pi*c['drum_rpm']/60/1000+pull*speed/60/1000+feeder_t*2*math.pi*rpm/60/1000
        running=shaft_kw/(c['gear_efficiency']*c['motor_efficiency']*c['vfd_efficiency'])+.18+c['control_kw']
        roller_load=(drum+hold)*G*c['dynamic_factor']*.40/math.cos(math.pi/6)
        check('드럼 롤러 베어링 요구 정격',roller_load*2,15000.,'N','드럼 하중 40%/cos30°, 정정격 여유2; 실제 수명·접촉압력은 공급사 확인')
        row('드럼 내부 입구 / 출구 지름',f'{r0*2000:g} / {r1*2000:g}','mm')
        row('드럼 유효 길이',1800.,'mm');row('드럼 내부 용적',volume,'m³')
        row('정상 충전율',fill*100,'%');row('최대 운전 충전율 가정',c['max_fill_fraction']*100,'%')
        row('정상 체류시간',c['residence_min'],'min','회전수만으로 체류시간이 결정되지 않음; 실제 배출 유량으로 보정')
        row('드럼 회전수',c['drum_rpm'],'rpm');row('기어박스 / 링-피니언 / 총 감속비',f'{c["drum_gear_ratio"]:g} / {c["drum_ring_pitch_radius_mm"]/c["pinion_radius_mm"]:.3f} / {ratio:.3f}')
        row('칩 투입 벨트 속도',speed,'m/min');row('양념 유량',powder,'kg/h');row('양념 혼합 후 유량',flow+powder,'kg/h')
        row('양념 호퍼 내부 L × W × H','374 × 424 × 430','mm');row('양념 호퍼 유효 저장량',powder_store,'kg','체적의85%, 분말 밀도 입력')
        row('양념 보충 간격',powder_store/powder,'h');row('계량 스크루 외경 / 축경 / 피치','56 / 24 / 32','mm')
        row('계량 스크루 속도',rpm,'rpm');row('드럼 롤러1개 반력 선별',roller_load,'N')
        row('배출 프레임 상단 / 최저 바닥판 하단','650 / 736','mm','가로보는 제품 경로 아래, 성형 웹으로 슈트 지지')
        pending=['수평 확장 드럼의 실제 체류·혼합 균일도·파손률을 시험해 경사 또는 내부 이송 날개 필요성 결정',
                 '분말 점착·브리징·벌크 밀도 변화에 따른 kg/rev 계량 보정; 토크리미터·레벨센서 연동',
                 '드럼 링과 롤러 접촉압력·추력 방지·베어링 수명, 모터 플랫폼 및 배출 웹의 국부 용접 상세',
                 '성형 배출판과 지지 웹은 최소0.5 mm 제작 용접 간극을 둔 명목 형상; 절단·맞춤 공차 반영']
    else:
        raise ValueError(f'Station {index} engineering calculation is not implemented yet')
    frame=meta['frame_design'];leg=frame['leg'];beam=frame['beam'];span=frame['beam_span_mm']
    if len(beam)==3:
        bw,bh,bt=beam;inertia=(bw*bh**3-(bw-2*bt)*(bh-2*bt)**3)/12
        bp=dict(area_mm2=bw*bh-(bw-2*bt)*(bh-2*bt),inertia_mm4=inertia,modulus_mm3=2*inertia/bh)
    else:bp=core.section_properties(*beam)
    lp=core.section_properties(*leg);allow=c['yield_mpa']/c['safety_factor'];E=c['elastic_modulus_mpa']
    load=(dead+blocked+liquid)*G*c['dynamic_factor'];beamP=load*frame['beam_load_share']
    per_leg=load*max(2/frame['leg_count'],.25)
    stress=beamP*span/4/bp['modulus_mm3'];deflect=beamP*span**3/(48*E*bp['inertia_mm4'])
    check('주 횡보 굽힘',stress,allow,'MPa',f'전체 설계하중×{frame["beam_load_share"]:g}; 중앙집중하중 L={span:g}; M=PL/4')
    check('주 횡보 처짐',deflect,span/300,'mm','δ=PL³/(48EI), L/300')
    check('기둥 압축+편심',per_leg/lp['area_mm2']+per_leg*c['leg_eccentricity_mm']/lp['modulus_mm3'],allow,'MPa','불균등 분담 max(2/N,0.25); 편심 입력값')
    euler=math.pi**2*E*lp['inertia_mm4']/frame['leg_length_mm']**2
    rankine=1/(1/(lp['area_mm2']*c['yield_mpa'])+1/euler)
    check('기둥 좌굴 선별',per_leg,rankine/c['safety_factor'],'N','전장 K=1, Rankine 예비 선별; 관벽/용접 및 규격 좌굴곡선 별도')
    check('기둥 필릿 용접 직접전단',per_leg/(.707*c['weld_leg_mm']*4*leg[0]),allow/math.sqrt(3),'MPa','둘레 필릿 직접전단, 모멘트·피로·국부 관벽 별도')
    horizontal=(dead+blocked+liquid)*G*c['lateral_accel_g']
    row('기둥 1개 계산 반력',per_leg/1000,'kN');row('수평 관성 설계하중',horizontal/1000,'kN')
    row('전체 질량 중심 Z (기계 자중)',cg[2],'mm','모델 형상 및 추정 질량 기준; 액체/제품 제외')
    notes=meta.get('fixes',[])+['외형은 구매품을 포함한 코드 외접치수이며 카탈로그 외형과 다를 수 있다. 내부 판·메시·구매품 외형은 예비 설계치다.',
        '자중은 동일 모델의 순단면 체적에서 계산하며 용접·배선 등 여유를 별도로 가산한다. 모터/기어박스 봉투 형상과 거친 메시의 질량은 실제 구매품·제작 질량으로 교체해야 한다.']
    result=dict(index=index,revision=REVISION,inputs=c,flow_balance=f,geometry_bbox=geometry_bounds(specs),bom=bom,
        base_mass_kg=base,dead_mass_kg=dead,normal_product_kg=hold,blocked_product_kg=blocked,liquid_design_mass_kg=liquid,
        design_vertical_load_n=load,checks=checks,drives=drives,details=details,normal_flow_kg_h=flow,
        installed_motor_kw=installed,estimated_running_kw=running,daily_startup_kwh=startup,
        nameplate_input_kw=installed/(c['motor_efficiency']*c['vfd_efficiency'])+extra_nameplate+c['control_kw'],
        notes=notes,thermal_notes=thermal,pending=pending,frame_sections=dict(leg_mm=leg,crossbeam_mm=beam),
        geometry_sha256=hashlib.sha256(json.dumps(specs,sort_keys=True).encode()).hexdigest(),geometry_metadata=meta)
    return finalize(result)


def report_html(r):
    from review_layout import compact_report
    return compact_report(r['index'],r)


def write_index(base):
    from review_layout import write_index as write_all
    return write_all(base)


def write_report(index,output_dir,overrides=None,specs=None,meta=None):
    if index==5:
        from slicer_review import write_report as write_slicer_review
        return write_slicer_review(output_dir,overrides)
    r=analyze(index,overrides,specs,meta);out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    prefix=f'{index:02d}_{NAMES[index][0]}'
    path=out/(prefix+'_Design_Review.html')
    path.write_text(report_html(r),encoding='utf-8')
    (out/(prefix+'_Calculations.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return path,r


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',type=int,choices=range(5,12),required=True)
    p.add_argument('--config',type=Path);p.add_argument('--output-dir',type=Path)
    a=p.parse_args();c=json.loads(a.config.read_text(encoding='utf-8-sig')) if a.config else None
    folder=a.output_dir or Path(__file__).resolve().parent/'Overall_Review'/f'{a.stage:02d}_{NAMES[a.stage][0]}_Design_Review'
    report,r=write_report(a.stage,folder,c)
    print('SAVED DESIGN REPORT '+str(report.resolve()))
    for warning in r['warnings']:print('DESIGN REVIEW: '+warning)
