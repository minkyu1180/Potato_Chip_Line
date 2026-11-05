"""Station 02 wet screw destoner: welded frame, four-arm upper support, review.

Pure Python; never opens CATIA. Keep station1_design.py beside this module.
    py station2_design.py --config station2_config.json
All geometry is in mm. Calculation results are preliminary, not certified ratings.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import html
import json
import math
from pathlib import Path
import station1_design as core

REVISION='SO-R5.1-2026-11-01'
G=9.80665
I,AX,AY=core.I,core.AX,core.AY
STEEL,FRAME,BLUE,DRIVE=core.STEEL,core.FRAME,core.BELT,core.DRIVE
add,sub,mul,norm,unit,cross=core.vadd,core.vsub,core.vmul,core.vnorm,core.vunit,core.cross
rect=core.rect
# One source for both geometry and equations. These are redesign dimensions,
# NOT a claim of reproducing the manufacturer's internal fabrication drawings.
DIM={
    'tank_x0':80.,'tank_x1':1420.,'tank_half_width':600.,'tank_floor_z':180.,
    'tank_top_z':1550.,'floor_t':8.,'wall_t':6.,'end_t':6.,
    'screw_x':850.,'shaft_d':80.,'shaft_bottom':300.,'shaft_top':2595.,
    'flight_bottom':350.,'flight_top':2275.,'screw_d':500.,'pitch':350.,'flight_t':8.,
    'casing_inner_d':530.,'casing_wall':6.,'intake_z':650.,'discharge_z':2020.,
    'casing_top_z':2283.,'casing_tube_bottom':650.,
    'top_beam_top':2435.,'top_plate_t':20.,'top_bolt_radius':160.,
    'inlet_z':1000.,'outlet_z':1790.,'outlet_x':1800.,
    'chute_width':440.,'chute_height':230.,'chute_t':6.,
    'leg_b':80.,'leg_t':5.,'beam_b':100.,'beam_t':6.,'base_b':140.,'base_t':8.,
    'brace_b':50.,'brace_t':4.,'outfeed_b':60.,'outfeed_t':4.,
}
DEFAULTS={
    'material':'SUS304','steel_density_kg_m3':7930.,'yield_mpa':205.,'E_mpa':193000.,
    'potato_density_kg_m3':1100.,'packing_fraction':.65,'water_density_kg_m3':1000.,
    'water_level_z_mm':900.,'working_potato_kg':200.,'target_kg_h':1000.,
    'screw_rpm':30.,'min_rpm':15.,'max_rpm':35.,
    'flight_loading_fraction':.10,'axial_transport_efficiency':.20,
    'jam_loading_fraction':.35,'capacity_reserve_factor':1.20,
    'screw_lead_efficiency':.50,'potato_wall_friction':.35,
    'water_lift_m3_h_at_nominal':10.,'hydraulic_efficiency':.25,
    'empty_drag_torque_nm':25.,'breakaway_factor':1.5,'start_seconds':3.,
    'drive_service_factor':1.5,'motor_kw':2.2,'motor_base_rpm':1750.,
    'gear_ratio':50.,'gear_efficiency':.90,'low_speed_torque_factor':.85,
    'gear_continuous_nm':500.,'gear_peak_nm':750.,'torque_limiter_nm':350.,
    'motor_rotor_inertia_kg_m2':.006,'motor_efficiency_estimate':.75,
    'motor_rated_efficiency_estimate':.86,'vfd_efficiency':.96,'motor_pf':.78,
    'motor_fixed_loss_kw':.08,'control_and_fan_kw':.06,
    'vertical_dynamic_factor':2.,'lateral_accel_g':.30,'yield_safety_factor':2.,
    'mass_allowance_fraction':.10,'leg_load_share':.25,'beam_load_share':.50,
    'top_arm_load_share':.50,'leg_eccentricity_mm':20.,'weld_leg_mm':5.,
    'top_joint_weld_leg_mm':6.,'shaft_bending_factor':1.6,'shaft_torsion_factor':1.3,
    'bolt_proof_mpa':450.,'bolt_tensile_area_mm2':157.,'bolt_preload_fraction':.60,
    'joint_friction':.15,'retained_preload_fraction':.50,
    'upper_bearing_axial_allowable_n':30000.,'lower_guide_radial_allowable_n':10000.,
    'supply_v':380.,'supply_hz':60.,'hours_per_day':8.,'days_per_month':22.,
    'running_fraction':1.,'design_years':5.,'energy_rate_krw_kwh':160.,
    'extra_demand_charge_krw_month':0.,
}
SOURCES=[
    ('S1','Sormac SO 작동 원리·제조사 참고 사양',
     'https://static.sormac.com/91/21/912194081f6b5f402785d901d4bc6aa2b92d8f68.pdf',
     '물과 수직 스크루로 감자를 올리고 돌을 바닥에 남기는 장비. 제조사 설치출력 1.5 kW와 최대 5 t/h는 참고값이며 본 재설계의 보증 성능이 아님. 치수표와 측면 도면의 높이 표기가 달라 내부 치수는 별도로 정의했다.'),
    ('S2','KWS: Vertical Screw Conveyor Capacity & Horsepower',
     'https://www.kwsmfg.com/engineering-guides/vertical-conveyor/capacity-table-horsepower-calculation/',
     '수직 이송은 회전수·마찰·중력·투입 조건을 함께 고려. 건식 벌크의 권장 고속 RPM을 이 습식 감자 제석기에 그대로 적용하지 않았다.'),
    ('S3','Nippon Steel: SUS304 물성',
     'https://www.nipponsteel.com/product/catalog_download/pdf/S008.pdf',
     '기본값: 밀도 7.93 g/cm³, 0.2% 내력 205 MPa, 탄성계수 193 GPa. 실제 관재/봉재 성적서 확인 필요.'),
    ('S4','Nord-Lock: Safe Bolted Joint Design',
     'https://www.nord-lock.com/contentassets/e6bddf99fa6c470680a3f81b9df0a9a7/nlg-bolted-joint-white-paper-.pdf',
     '진동 풀림에는 접합면의 횡방향 미끄럼과 축력 유지가 중요. 십자 배치만으로 풀림 방지가 보장되지는 않음.'),
    ('S5','Kotadia Fasteners: Stainless Steel Data',
     'https://www.kotadiafasteners.com/technical-data/stainless-steel-data/',
     'A2-70 체결품 강도 참고. M16, 인장응력 면적 157 mm² 및 proof 450 MPa를 구매 요구값으로 사용; 성적서와 조임 절차는 별도.'),
    ('S6','SKF: Spectrum analysis',
     'https://cdn.skfmediahub.skf.com/api/public/0901d196802186cb/pdf_preview_medium/0901d196802186cb_pdf_preview_medium.pdf',
     '회전체 불균형·축 정렬 불량 등 진동 원인을 별도로 진단해야 함.'),
    ('S7','Worldstainless: Food and beverage industry',
     'https://worldstainless.org/applications/industrial-applications/food-and-beverage-industry/',
     '식품 위생은 재료뿐 아니라 표면 마감·용접·세척 가능한 구조를 함께 고려.'),
    ('S8','KEPCO: 2026년 요금제 개편 안내',
     'https://www.kepco.co.kr/KEPCO_FILE/html/2026_08/issue.html',
     '계약종별·시간대에 따른 요금 차이. 160원/kWh는 총 변동단가 가정이며 실제 공식 단가를 뜻하지 않음.'),
]


def configuration(overrides=None):
    c=dict(DEFAULTS)
    if overrides is not None:
        if not isinstance(overrides,dict):raise ValueError('Configuration must be a JSON object')
        extra=set(overrides)-set(c)
        if extra:raise ValueError('Unknown station2 inputs: '+', '.join(sorted(extra)))
        c.update(overrides)
    if c['material']!='SUS304':raise ValueError('This design is for user-confirmed SUS304')
    zero_ok={'lateral_accel_g','mass_allowance_fraction','working_potato_kg','empty_drag_torque_nm',
             'water_lift_m3_h_at_nominal','motor_fixed_loss_kw','control_and_fan_kw',
             'running_fraction','extra_demand_charge_krw_month','energy_rate_krw_kwh'}
    for k,v in c.items():
        if k=='material':continue
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 or (v==0 and k not in zero_ok):
            raise ValueError(f'Invalid input {k}={v!r}')
    for k in ('packing_fraction','flight_loading_fraction','axial_transport_efficiency',
              'jam_loading_fraction','screw_lead_efficiency','hydraulic_efficiency',
              'gear_efficiency','low_speed_torque_factor','motor_efficiency_estimate',
              'motor_rated_efficiency_estimate','vfd_efficiency','motor_pf','bolt_preload_fraction',
              'joint_friction','retained_preload_fraction'):
        if not 0<c[k]<=1:raise ValueError(f'{k} must be in (0,1]')
    if not 0<=c['running_fraction']<=1:raise ValueError('running_fraction must be 0..1')
    if not 15<=c['min_rpm']<=c['screw_rpm']<=c['max_rpm']<=35:
        raise ValueError('This conceptual design supports 15 <= min <= nominal <= max <= 35 rpm')
    if not 700<=c['water_level_z_mm']<=950:
        raise ValueError('Working water surface must be Z700..950, below the Z1000 inlet')
    for k in ('vertical_dynamic_factor','yield_safety_factor','drive_service_factor','capacity_reserve_factor','breakaway_factor'):
        if c[k]<1:raise ValueError(k+' must be >= 1')
    if c['supply_hz']!=60:raise ValueError('The motor speed map is for 60 Hz')
    if not 1/6<=c['leg_load_share']<=1:raise ValueError('Invalid leg load share')
    if not 1/3<=c['beam_load_share']<=1 or not .25<=c['top_arm_load_share']<=1:
        raise ValueError('Invalid support load share')
    if c['jam_loading_fraction']<c['flight_loading_fraction']:raise ValueError('Jam filling cannot be lower than normal filling')
    return c


class Geometry:
    def __init__(self,c):self.c=c;self.specs=[];self.group='Welded Base Frame'
    def add(self,s,**kw):
        s.update(name='02_'+s['name'],group=self.group,material='SUS304',density_kg_m3=self.c['steel_density_kg_m3'])
        s.update(kw);self.specs.append(s);return s
    def poly(self,name,points,depth,origin,axes=I,color=STEEL,loops=(),holes=(),**kw):
        return self.add(dict(name=name,kind='poly',points=tuple(points),loops=tuple(loops),
                            depth=depth,origin=origin,axes=axes,color=color,holes=holes),**kw)
    def box(self,name,corner,size,color=STEEL,holes=(),**kw):
        x,y,z=corner;w,d,h=size
        return self.poly(name,rect(w,d),h,(x+w/2,y+d/2,z),color=color,holes=holes,**kw)
    def member(self,name,a,b,w,h=None,t=0,color=FRAME,**kw):
        h=w if h is None else h;axis=unit(sub(b,a));ref=(0.,0.,1.) if abs(axis[2])<.9 else (0.,1.,0.)
        u=unit(cross(ref,axis));v=cross(axis,u);depth=norm(sub(b,a))
        result=self.poly(name,rect(w,h),depth,a,(u,v,axis),color,
                         loops=(tuple(reversed(rect(w-2*t,h-2*t))),) if t else (),**kw)
        if t:
            for j,z in enumerate((0,depth-t)):
                self.poly(name+f'_Sealed_End_{j}',rect(w-2*t,h-2*t),t,add(a,mul(axis,z)),(u,v,axis),color)
        return result
    def tube(self,name,a,b,role='beam'):
        return self.member(name,a,b,DIM[role+'_b'],t=DIM[role+'_t'])
    def cyl(self,name,a,b,r,inner=0,color=STEEL,holes=(),**kw):
        axis=unit(sub(b,a));ref=(0.,0.,1.) if abs(axis[2])<.9 else (0.,1.,0.)
        u=unit(cross(ref,axis));v=cross(axis,u)
        return self.add(dict(name=name,kind='circle',radius=r,inner=inner,depth=norm(sub(b,a)),
                             origin=a,axes=(u,v,axis),color=color,holes=holes),**kw)
    def sector(self,name,z0,z1,start_deg,end_deg,r,inner):
        angles=[math.radians(start_deg+(end_deg-start_deg)*i/36) for i in range(37)]
        pts=tuple((r*math.cos(a),r*math.sin(a)) for a in angles)+tuple((inner*math.cos(a),inner*math.sin(a)) for a in reversed(angles))
        return self.poly(name,pts,z1-z0,(DIM['screw_x'],0,z0))
    def sheet(self,name,a,b,width,t,color=STEEL):
        u=unit(sub(b,a));v=(0.,1.,0.);n=unit(cross(u,v));center=mul(add(a,b),.5)
        return self.poly(name,rect(norm(sub(b,a)),width),t,add(center,mul(n,-t)),(u,v,n),color)
    def chute(self,name,a,b,width,height,t):
        self.sheet(name+'_Floor',a,b,width,t)
        for side in (-1,1):
            x0,_,z0=a;x1,_,z1=b
            pts=((x0,-z0),(x1,-z1),(x1,-z1-height),(x0,-z0-height))
            self.poly(name+f'_Side_{side}',pts,t,(0,side*width/2,0),AY)
    def quad(self,name,vertices,t,**kw):
        a=vertices[0];u=unit(sub(vertices[1],a));normal=unit(cross(u,sub(vertices[-1],a)));v=cross(normal,u)
        points=tuple((sum(x*y for x,y in zip(sub(p,a),u)),sum(x*y for x,y in zip(sub(p,a),v))) for p in vertices)
        return self.poly(name,points,t,add(a,mul(normal,-t)),(u,v,normal),**kw)


def make_specs(c):
    d=DIM;g=Geometry(c);X=d['screw_x'];top=d['top_beam_top'];bb=d['beam_b']
    for x in (100,750,1400):
        for side in (-1,1):
            y=side*680;leg_top=top if x!=750 else 1570
            g.tube(f'Welded_Column_{x}_{side}',(x,y,20),(x,y,leg_top),'leg')
            g.box(f'Foundation_Foot_{x}_{side}',(x-100,y-100,0),(200,200,20),FRAME,
                  holes=((-70,-70,9),(70,-70,9),(70,70,9),(-70,70,9)))
        g.tube(f'Tank_Base_Crossbeam_{x}',(x,-680,180-d['base_b']/2),(x,680,180-d['base_b']/2),'base')
    for side in (-1,1):
        for z in (130,1570,top-bb/2):
            g.tube(f'Longitudinal_Rail_{side}_{z:g}',(100,side*680,z),(1400,side*680,z))
        for x in (100,750):
            g.tube(f'Lower_Side_Brace_{x}_{side}',(x,side*680,300),(x+650,side*680,1450),'brace')
        g.tube(f'Upper_Side_Brace_{side}',(100,side*680,1570),(1400,side*680,top-100),'brace')
    for x in (100,1400):
        g.tube(f'Upper_Perimeter_End_{x}',(x,-680,top-bb/2),(x,680,top-bb/2))
        # Transverse braces are outside the tank/end sheet, not inside the product path.
        offset=-55 if x==100 else 55
        brace_top=850 if x==100 else 1450
        g.tube(f'Transverse_X_A_{x}',(x+offset,-680,250),(x+offset,680,brace_top),'brace')
        g.tube(f'Transverse_X_B_{x}',(x+offset,680,250),(x+offset,-680,brace_top),'brace')
    for x in (100,450,800,1150,1400):
        g.member(f'Floor_Stiffener_{x}',(x,-600,155),(x,600,155),8,50)

    g.group='Wet Separation Tank'
    # Actual inlet window and access opening. No solid wall across either aperture.
    g.box('Tank_Floor',(80,-600,180),(1340,1200,d['floor_t']),holes=((300,-500,29),))
    rear=((-600,188),(600,188),(600,1550),(-600,1550))
    opening=tuple(reversed(((-325,990),(325,990),(325,1320),(-325,1320))))
    g.poly('Tank_Infeed_End_With_Window',rear,d['end_t'],(80,0,0),AX,loops=(opening,))
    g.poly('Tank_Outfeed_End',rear,d['end_t'],(1420-d['end_t'],0,0),AX)
    for side in (-1,1):
        g.poly(f'Tank_Side_{side}',((80,-188),(1420,-188),(1420,-1550),(80,-1550)),d['wall_t'],
               (0,-600 if side<0 else 600-d['wall_t'],0),AY,holes=((750,-500,180),) if side==-1 else ((250,-1000,20),))
        for x in (100,400,700,1000,1300,1400):
            intervals=((188,320),(680,1550)) if side<0 and x==700 else ((188,1550),)
            for j,(lo,hi) in enumerate(intervals):
                g.member(f'Wall_Stiffener_{side}_{x}_{j}',(x,side*625,lo),(x,side*625,hi),8,50)
        g.tube(f'Tank_Rim_{side}',(80,side*620,1530),(1420,side*620,1530),'brace')
    for x in (55,1445):
        for y in (-525,-175,175,525):
            intervals=((188,990),(1320,1550)) if x<100 and abs(y)<325 else ((188,1550),)
            for j,(low,high) in enumerate(intervals):
                g.member(f'End_Stiffener_{x}_{y}_{j}',(x,y,low),(x,y,high),50,8)
    g.tube('Infeed_Window_Lower_Reinforcement',(55,-600,965),(55,600,965),'brace')
    g.tube('Infeed_Window_Upper_Reinforcement',(55,-600,1345),(55,600,1345),'brace')
    # Access flange is hollow and aligned with a real Pocket in the side sheet.
    access_holes=tuple((198*math.cos(2*math.pi*j/8),198*math.sin(2*math.pi*j/8),8.5) for j in range(8))
    g.cyl('Access_Hollow_Flange',(750,-620,500),(750,-600,500),215,180,holes=access_holes)
    g.cyl('Access_Removable_Cover',(750,-635,500),(750,-620,500),215,holes=access_holes)
    for j in range(8):
        a=2*math.pi*j/8
        g.cyl(f'Access_Bolt_{j}',(750+198*math.cos(a),-648,500+198*math.sin(a)),
              (750+198*math.cos(a),-620,500+198*math.sin(a)),8,color=DRIVE,
              material='Purchased stainless fastener',mass_override_kg=.10)
    g.cyl('Bottom_Drain',(1050,-500,80),(1050,-500,188),35,29)
    g.cyl('Water_Inlet',(250,595,1000),(250,800,1000),25,20)
    g.box('High_Level_Sensor',(200,-640,930),(50,40,50),DRIVE,material='Purchased level sensor',mass_override_kg=.5)

    g.group='Infeed'
    g.chute('Infeed_1000mm_Interface',(0,0,1000),(450,0,975),620,180,5)
    # Wet tapered guide ends upstream of the rotor swept radius (min X = 600).
    # This directs product toward the intake; the structural crossmembers do not feed it.
    guide0=((450,-310,975),(590,-150,800),(590,150,800),(450,310,975))
    g.quad('Wet_Infeed_Guide_Floor',guide0,5,displaces_tank_water=True)
    for name,a,b in (('Left',guide0[0],guide0[1]),('Right',guide0[3],guide0[2])):
        g.quad('Wet_Infeed_Guide_'+name,(a,b,add(b,(0,0,140)),add(a,(0,0,140))),5,displaces_tank_water=True)
    for side in (-1,1):
        g.tube(f'Infeed_Bracket_{side}',(100,side*680,850),(100,side*310,950),'outfeed')

    g.group='Screw Rotor'
    g.cyl('Rotor_Shaft',(X,0,d['shaft_bottom']),(X,0,d['shaft_top']),d['shaft_d']/2)
    n=int(round((d['flight_top']-d['flight_bottom'])/(d['pitch']/4)))
    for j in range(n):
        a=j*math.pi/2;u=(math.cos(a),math.sin(a),0.);v=(-math.sin(a),math.cos(a),0.)
        g.add(dict(name=f'Flight_Quarter_{j+1:02d}',kind='helix',radius=d['screw_d']/2,
                   inner=d['shaft_d']/2-1,thickness=d['flight_t'],pitch=d['pitch'],normal_thickness=True,
                   depth=d['pitch']/4,origin=(X,0,d['flight_bottom']+j*d['pitch']/4),
                   axes=(u,v,(0.,0.,1.)),color=(202,177,97),holes=()))

    g.group='Screw Casing'
    ri=d['casing_inner_d']/2;ro=ri+d['casing_wall']
    # Lower intake faces upstream (-X); upper discharge faces downstream (+X).
    g.sector('Lower_Intake_Open_Sector',650,1000,225,495,ro,ri)
    g.cyl('Closed_Lift_Casing',(X,0,1000),(X,0,2020),ro,ri)
    g.sector('Upper_Discharge_Open_Sector',2020,2275,45,315,ro,ri)
    g.cyl('Casing_Top_Cover_With_Shaft_Clearance',(X,0,2275),(X,0,2283),ro+10,55)
    # External collar gives the casing a lateral support without intruding into the screw sweep.
    g.cyl('External_Casing_Collar',(X,0,1750),(X,0,1780),ro+15,ro)
    for side in (-1,1):
        g.tube(f'Casing_Lateral_Bracket_{side}',(X,side*(ro+10),1765),(X,side*680,1765),'outfeed')
        g.tube(f'Casing_Bracket_Rail_{side}',(100,side*680,1765),(1400,side*680,1765),'outfeed')

    g.group='Screw Support and Bearings'
    # P006 replacement: four separate arms at 90 degrees; clear space around the shaft.
    arm_ends=[('West',(100,0,top-bb/2),(X-90,0,top-bb/2)),
              ('East',(X+90,0,top-bb/2),(1400,0,top-bb/2)),
              ('South',(X,-680,top-bb/2),(X,-90,top-bb/2)),
              ('North',(X,90,top-bb/2),(X,680,top-bb/2))]
    for name,a,b in arm_ends:
        g.tube('P006_Cross_Arm_'+name,a,b)
    holes=((0,0,55),(160,0,9),(0,160,9),(-160,0,9),(0,-160,9))
    g.box('P006_Central_Bearing_Plate',(X-220,-220,top),(440,440,20),holes=holes)
    bolt_xy=((160,0),(0,160),(-160,0),(0,-160))
    g.cyl('Upper_Thrust_Bearing_Flange',(X,0,top+20),(X,0,top+35),190,55,
          holes=tuple((x,y,9) for x,y in bolt_xy))
    g.cyl('Upper_Thrust_Radial_Bearing',(X,0,top+35),(X,0,2555),115,40,DRIVE,
          material='Purchased combined thrust/radial bearing unit',mass_override_kg=22.)
    for j,(x,y) in enumerate(bolt_xy,1):
        g.cyl(f'P006_Cross_Bolt_M16_{j}',(X+x,y,top-15),(X+x,y,top+48),8,color=DRIVE,
              material='A2-70 stainless bolt M16',mass_override_kg=.16)
        g.cyl(f'P006_Locking_Washer_{j}',(X+x,y,top+35),(X+x,y,top+39),15,8.5,DRIVE,
              material='Purchased stainless wedge-lock washer pair',mass_override_kg=.025)
    # Upper thrust bearing carries axial load. Lower water-lubricated guide is radial only.
    g.cyl('Lower_Radial_Guide_Housing',(X,0,280),(X,0,340),85,55)
    g.cyl('Lower_Food_Contact_Guide_Bush',(X,0,285),(X,0,335),55,40.5,BLUE,
          material='Food-contact water-lubricated polymer guide',density_kg_m3=950.)
    for j in range(4):
        a=j*math.pi/2
        g.member(f'Lower_Guide_Rib_{j}',(X+80*math.cos(a),80*math.sin(a),290),
                 (X+220*math.cos(a),220*math.sin(a),210),12,50)
    g.box('Lower_Guide_Floor_Doubler',(X-250,-250,188),(500,500,12))

    g.group='Drive System'
    g.cyl('Flexible_Coupling',(X,0,2555),(X,0,2595),65,40,DRIVE,
          material='Purchased flexible coupling and torque limiter',mass_override_kg=6.)
    g.box('Gearbox_Envelope',(X-100,-100,2595),(200,200,160),DRIVE,
          material='Purchased right-angle gear unit',mass_override_kg=35.)
    g.cyl('Motor_Envelope',(X-100,0,2695),(X-400,0,2695),90,color=DRIVE,
          material=f"Purchased {c['motor_kw']:g} kW three-phase inverter-duty motor",mass_override_kg=28.)
    # Gearbox stand attaches to the dry cross support, never to a thin casing lid.
    for side in (-1,1):
        g.tube(f'Gearbox_Stand_{side}',(X,side*195,top+20),(X,side*195,2590),'outfeed')
    g.box('Gearbox_Stand_Base',(X-140,-235,2590),(280,470,5),FRAME,holes=((0,0,70),))
    g.cyl('Coupling_Guard',(X,0,2550),(X,0,2595),85,82,(218,158,62))

    g.group='Supported Outfeed'
    a=(1030.,0.,2020.);b=(d['outlet_x'],0.,d['outlet_z']);u=unit(sub(b,a));normal=unit(cross(u,(0,1,0)))
    g.chute('Discharge_Chute',a,b,d['chute_width'],d['chute_height'],d['chute_t'])
    for side in (-1,1):
        g.tube(f'Discharge_Longitudinal_{side}',add(add(a,(0,side*180,0)),mul(normal,-36)),
               add(add(b,(0,side*180,0)),mul(normal,-36)),'outfeed')
        g.tube(f'Outfeed_Column_{side}',(1750,side*280,20),(1750,side*280,1750),'outfeed')
        g.box(f'Outfeed_Foot_{side}',(1660,side*280-90,0),(180,180,20),FRAME,
              holes=((-60,-60,9),(60,-60,9),(60,60,9),(-60,60,9)))
        g.tube(f'Outfeed_Base_Tie_{side}',(1400,side*680,130),(1750,side*280,130),'outfeed')
        g.tube(f'Outfeed_Diagonal_{side}',(1400,side*680,1200),(1750,side*280,1750),'brace')
        g.tube(f'Outfeed_Upper_Side_Rail_{side}',(100,side*680,1910),(1400,side*680,1910),'outfeed')
    g.tube('Discharge_Rear_Cradle',(1200,-680,1910),(1200,680,1910),'outfeed')
    g.tube('Discharge_Front_Cradle',(1750,-280,1750),(1750,280,1750),'outfeed')
    # Short risers bridge from cradle beams to the longitudinal chute members.
    for x,base in ((1200,1940),(1750,1780)):
        floor=2020+(d['outlet_z']-2020)*(x-1030)/(d['outlet_x']-1030)
        lower=floor-66
        if lower>base:
            for side in (-1,1):g.box(f'Chute_Riser_{x}_{side}',(x-30,side*180-30,base),(60,60,lower-base),FRAME)

    g.group='Electrical Controls'
    g.box('Control_Enclosure',(120,-760,1100),(360,80,440),FRAME,
          material='Purchased VFD/control enclosure',mass_override_kg=18.)
    return g.specs


def flight_section_data(s):
    """The Rib profile uses linear axial thickness; min normal thickness is t."""
    r,R,p,t=s['inner'],s['radius'],s['pitch'],s['thickness'];a=p/(2*math.pi)
    h0=t*math.hypot(r,a)/r;h1=t*math.hypot(R,a)/R;k=(h1-h0)/(R-r)
    # Integral r*h(r) dr, and r^3*h(r) dr for polar inertia.
    A=h0*(R*R-r*r)/2+k*((R**3-r**3)/3-r*(R*R-r*r)/2)
    J=h0*(R**4-r**4)/4+k*((R**5-r**5)/5-r*(R**4-r**4)/4)
    return A*math.pi/2/1e9,J/A/1e6,h0,h1


def mass_info(s,c):
    if s['kind']=='helix':
        volume,r2,_,_=flight_section_data(s);mass=volume*c['steel_density_kg_m3']
        # Use on-axis CG for the partial turn; mass approximation is explicitly identified.
        cg=(s['origin'][0],s['origin'][1],s['origin'][2]+s['pitch']/8)
        return mass,cg,volume,mass*r2
    if s['kind']=='circle' and s.get('holes') and 'mass_override_kg' not in s:
        area=math.pi*(s['radius']**2-s.get('inner',0)**2)-sum(math.pi*r*r for _,_,r in s['holes'])
        volume=area*s['depth']/1e9;mass=volume*s['density_kg_m3']
        cg=add(s['origin'],mul(s['axes'][2],s['depth']/2))
    else:mass,cg,volume=core.part_mass(s,c)
    inertia=mass*((s.get('radius',0)/1000)**2+(s.get('inner',0)/1000)**2)/2 if s['kind']=='circle' else 0.
    return mass,cg,volume,inertia


def wet_internal_volume(specs,c,zlevel):
    """Inside-tank steel/polymer displacement; clip only wholly internal primitives in Z.
    Casing is open/flooded, so only its wall (not its envelope) displaces water.
    Tank walls, external frames and attached stiffeners are excluded.
    """
    total=0.
    allowed=('Screw Rotor','Screw Casing','Screw Support and Bearings')
    floor=DIM['tank_floor_z']+DIM['floor_t']
    for s in specs:
        if s['group'] not in allowed and not s.get('displaces_tank_water'):continue
        if s['kind']=='helix':
            z0=s['origin'][2];z1=z0+s['pitch']/4
        else:
            bb=core.bounding_box([s]);z0,z1=bb['min_mm'][2],bb['max_mm'][2]
        overlap=max(0,min(zlevel,z1)-max(floor,z0))
        if overlap:
            # Parts crossing the waterline are prismatic or use a linear fraction approximation.
            _,_,vol,_=mass_info(s,c);total+=vol*overlap/(z1-z0)
    return total


def analyze(overrides=None,specs=None):
    c=configuration(overrides);d=DIM;specs=make_specs(c) if specs is None else specs
    groups=defaultdict(float);bom=[];mom=[0.,0.,0.];rotorJ=0.
    for s in specs:
        m,cg,vol,J=mass_info(s,c);groups[s['group']]+=m
        for j in range(3):mom[j]+=m*cg[j]
        if s['group']=='Screw Rotor':rotorJ+=J
        bom.append(dict(name=s['name'],group=s['group'],material=s['material'],mass_kg=m,volume_m3=vol,
                        basis='구매품 추정' if 'mass_override_kg' in s else ('나선 Rib 근사 체적' if s['kind']=='helix' else '체적×밀도')))
    bare=sum(groups.values());dead=bare*(1+c['mass_allowance_fraction']);cg=[x/bare for x in mom]
    floor=d['tank_floor_z']+d['floor_t'];L=(d['tank_x1']-d['tank_x0']-2*d['end_t'])/1000
    W=(1200-2*d['wall_t'])/1000;H=(d['tank_top_z']-floor)/1000
    gross=L*W*H;wetgross=L*W*(c['water_level_z_mm']-floor)/1000
    internal=wet_internal_volume(specs,c,c['water_level_z_mm']);free=max(0,wetgross-internal)
    fullfree=gross-wet_internal_volume(specs,c,d['tank_top_z'])
    rho=c['potato_density_kg_m3']*c['packing_fraction'];working=c['working_potato_kg']
    wetcap=free*rho;drycap=fullfree*rho
    if working>wetcap:raise ValueError(f'working_potato_kg exceeds submerged geometric capacity {wetcap:.1f} kg')
    watermass=(free-working/c['potato_density_kg_m3'])*c['water_density_kg_m3']
    packedwater=free*(1-c['packing_fraction'])*c['water_density_kg_m3']
    # Full static fill is an abnormal overfill case, with inlet temporarily blocked.
    fault_contents=fullfree*(rho+(1-c['packing_fraction'])*c['water_density_kg_m3'])
    operating_contents=working+watermass
    total=dead+fault_contents;kd=c['vertical_dynamic_factor'];wd=total*G*kd;horizontal=total*G*c['lateral_accel_g']
    fy=c['yield_mpa'];allow=fy/c['yield_safety_factor'];E=c['E_mpa'];checks=[]
    def check(name,demand,limit,unit_,basis):
        checks.append(dict(name=name,demand=demand,limit=limit,unit=unit_,utilization=demand/limit,
                           result='조건 충족' if demand<=limit else '재선정 필요',basis=basis))
    def sec(role):return core.section_properties(d[role+'_b'],d[role+'_t'])
    beam,leg,brace,out=sec('beam'),sec('leg'),sec('brace'),sec('outfeed')
    basebeam=sec('base');beamP=wd*c['beam_load_share'];beamM=beamP*1360/4
    beamstress=beamM/basebeam['modulus_mm3']
    check('수조 하부 횡보 굽힘',beamstress,allow,'MPa','전체 이상충전 동하중×0.5, 단순지지 중앙집중하중, L=1360 mm')
    check('수조 하부 횡보 처짐',beamP*1360**3/(48*E*basebeam['inertia_mm4']),1360/300,'mm','단순지지 L/300')
    legP=wd*c['leg_load_share'];legL=topL=d['top_beam_top']-20
    euler=math.pi**2*E*leg['inertia_mm4']/legL**2
    rankine=1/(1/(leg['area_mm2']*fy)+1/euler)
    legb=legP*c['leg_eccentricity_mm']/leg['modulus_mm3']
    check('기둥 압축+편심',legP/leg['area_mm2']+legb,allow,'MPa','6개 중 한 기둥 25% 분담, 기본 편심 20 mm')
    check('기둥 좌굴·편심 선별',legP/(rankine/c['yield_safety_factor'])+legb/allow,1.,'비율','K=1, 전장 좌굴, Rankine 근사; 규격 비선형 좌굴 검토는 별도')
    bL=math.hypot(650,1150);bF=horizontal/2/(650/bL)
    bpcr=math.pi**2*E*brace['inertia_mm4']/bL**2
    brank=1/(1/(brace['area_mm2']*fy)+1/bpcr)
    check('측면 가새 좌굴',bF,brank/c['yield_safety_factor'],'N','수평 0.3g 등가하중을 2개 가새에 보수적으로 분담')
    # Pressure is maximum mixture density, full depth; the dynamic factor is not a measured slosh spectrum.
    mixture_rho=rho+(1-c['packing_fraction'])*c['water_density_kg_m3'];pressure=mixture_rho*G*H*kd/1e6
    for label,t,span in (('측판',d['wall_t'],300.),('끝판',d['end_t'],350.),('바닥판',d['floor_t'],350.)):
        check(label+' 굽힘',.75*pressure*span**2/t**2,allow,'MPa','최하부 수압형 압력 상한의 1 mm 폭 단순지지 스트립')
        check(label+' 처짐',5*pressure*span**4/(32*E*t**3),span/200,'mm','균일 압력 상한, L/200')
    throat=.707*c['weld_leg_mm'];weldA=throat*4*d['leg_b']
    check('주 기둥 용접부 직접전단',math.hypot(legP,horizontal/4)/weldA,allow/math.sqrt(3),'MPa','둘레 연속 필릿; 토우 피로·접합부 국부파괴 미평가')

    # Flow model: geometric swept annulus x occupied fraction x axial efficiency.
    # Neither the wet lifting coefficient nor the loading fraction is a measured Sormac value.
    ann=math.pi/4*((d['screw_d']/1000)**2-(d['shaft_d']/1000)**2)
    pitch=d['pitch']/1000;lift=(d['discharge_z']-d['intake_z'])/1000
    n=c['screw_rpm'];omega=n*2*math.pi/60
    per_rpm=rho*ann*pitch*60*c['flight_loading_fraction']*c['axial_transport_efficiency']
    modelcap=per_rpm*n;needed_rpm=c['target_kg_h']/per_rpm
    vz=pitch*n/60*c['axial_transport_efficiency'];transit=lift/vz
    moving=c['target_kg_h']/3600*transit;jam=rho*ann*lift*c['jam_loading_fraction']
    mean_radius=(d['screw_d']+d['shaft_d'])/4000
    def loads(rpm):
        om=rpm*2*math.pi/60;vz_=pitch*rpm/60*c['axial_transport_efficiency']
        mass_=c['target_kg_h']/3600*lift/vz_
        # Same assumed water flow per revolution throughout the speed sweep.
        flow=c['water_lift_m3_h_at_nominal']*(rpm/n)/3600
        waterP=c['water_density_kg_m3']*G*flow*lift/c['hydraulic_efficiency']
        waterT=waterP/om
        liftT=mass_*G*pitch/(2*math.pi*c['screw_lead_efficiency'])
        wallT=c['potato_wall_friction']*mass_*G*mean_radius
        run=c['empty_drag_torque_nm']+waterT+liftT+wallT
        J=rotorJ+(jam+20)*mean_radius**2
        accel=J*om/c['start_seconds']
        start=((c['empty_drag_torque_nm']+waterT)*c['breakaway_factor']+
               jam*G*pitch/(2*math.pi*c['screw_lead_efficiency'])+
               c['potato_wall_friction']*jam*G*mean_radius+accel)
        design=start*c['drive_service_factor']
        motoracc=c['motor_rotor_inertia_kg_m2']*(rpm*c['gear_ratio']*2*math.pi/60)/c['start_seconds']
        motorT=design/(c['gear_ratio']*c['gear_efficiency'])+motoracc
        return dict(rpm=rpm,model_capacity_kg_h=per_rpm*rpm,
                    recommended_feed_kg_h=min(c['target_kg_h'],per_rpm*rpm/c['capacity_reserve_factor']),
                    run_nm=run,start_nm=start,
                    design_nm=design,motor_required_nm=motorT,water_power_w=waterP,
                    hydraulic_nm=waterT,gravity_nm=liftT,wall_nm=wallT,accel_nm=accel,
                    motor_rpm=rpm*c['gear_ratio'],vfd_hz=rpm*c['gear_ratio']/c['motor_base_rpm']*60,
                    shaft_kw=run*om/1000)
    nominal=loads(n);speedcases=[loads(x) for x in (c['min_rpm'],n,c['max_rpm'])]
    max_start=max(x['design_nm'] for x in speedcases);max_motor=max(x['motor_required_nm'] for x in speedcases)
    baseMotorT=c['motor_kw']*1000/(c['motor_base_rpm']*2*math.pi/60);usableMotorT=baseMotorT*c['low_speed_torque_factor']
    check('가정된 전달능력/목표유량',c['target_kg_h']*c['capacity_reserve_factor'],modelcap,'kg/h','목표×여유계수; 운반계수는 미실측이므로 실제 CAPA 인증 아님')
    check('전 속도범위 기동 모터토크',max_motor,usableMotorT,'N·m','기동 저항+회전체/모터 관성+서비스계수; 저속 가용토크 감액')
    check('감속기 연속 출력토크',max(x['run_nm'] for x in speedcases)*c['drive_service_factor'],c['gear_continuous_nm'],'N·m','정상 운전 토크×서비스계수')
    check('감속기 순간 토크',max_start,c['gear_peak_nm'],'N·m','운전속도 범위 중 최대 기동 설계토크')
    check('토크리미터 기동 여유',max_start,c['torque_limiter_nm'],'N·m','설계 기동토크 이하에서 먼저 끊기지 않도록 설정')
    check('리미터/감속기 보호',c['torque_limiter_nm'],c['gear_peak_nm'],'N·m','장애물 끼임 시 리미터가 감속기 순간 허용보다 먼저 제한')

    # Drive support load path: rotor -> separate thrust bearing -> cross arms -> tower.
    rotor_mass=groups['Screw Rotor'];drive_mass=groups['Drive System'];bearing_mass=groups['Screw Support and Bearings']
    jam_thrust=2*math.pi*c['torque_limiter_nm']/pitch
    axial=(rotor_mass+jam)*G*kd+jam_thrust
    top_vertical=axial+(drive_mass+bearing_mass)*G*kd
    armP=top_vertical*c['top_arm_load_share'];armL=d['screw_x']-90-100
    armM=armP*armL;armSigma=armM/beam['modulus_mm3']
    check('P006 십자 팔 굽힘',armSigma,allow,'MPa','네 팔 중 한 팔 50% 집중, 최장 팔 660 mm 외팔보로 보수 계산')
    check('P006 십자 팔 처짐',armP*armL**3/(3*E*beam['inertia_mm4']),armL/300,'mm','최장 외팔보 L/300; 중앙 플레이트 강성 이득 미인정')
    check('상부 스러스트 베어링',axial,c['upper_bearing_axial_allowable_n'],'N','자중·정체 감자·토크리미터의 이상 축추력 포함; 공급사 정격 확인')
    # Conservative strip through central plate: 440 mm wide, 180 mm center clear span.
    plateStress=6*(top_vertical*180/4)/(440*d['top_plate_t']**2)
    check('중앙 베어링 받침판',plateStress,allow,'MPa','단순지지 중앙집중하중, 구멍을 감안해 추가 감소 검토 필요')
    topH=(rotor_mass+jam+drive_mass)*G*c['lateral_accel_g']
    topM=drive_mass*G*300+topH*500
    bolt_external=top_vertical/4+topM/(2*d['top_bolt_radius'])
    bolt_pretension=c['bolt_preload_fraction']*c['bolt_proof_mpa']*c['bolt_tensile_area_mm2']
    # External increment assigned fully to bolt, conservative without stiffness ratio.
    bolt_sigma=(bolt_pretension+bolt_external)/c['bolt_tensile_area_mm2']
    check('십자 M16 최대 인장응력',bolt_sigma,c['bolt_proof_mpa']/1.25,'MPa','가정 축력+외력 전량; proof/1.25 선별, 프라잉 별도')
    clamp=c['retained_preload_fraction']*bolt_pretension*4-top_vertical
    tangential=topH+c['torque_limiter_nm']/(d['top_bolt_radius']/1000)
    check('십자 체결부 횡미끄럼',tangential,max(clamp,1)*c['joint_friction'],'N','잔존 축력 50%, 외부 분리력 차감, 수평력+토크의 등가 접선력 합산')
    check('체결면 분리',top_vertical,4*bolt_pretension*c['retained_preload_fraction'],'N','프리로드 손실 후 남은 압축력')
    wa=.707*c['top_joint_weld_leg_mm'];wb=d['beam_b']
    ws=armM/(4*wa*wb**2/3);wt=armP/(4*wa*wb)
    check('십자 팔 접합 용접군',math.hypot(ws,math.sqrt(3)*wt),allow,'MPa','사각 둘레 필릿의 굽힘+전단 선별; 용접토우 피로는 별도')
    # Shaft, flight and lower guide loads. No buoyancy credit in strength calculations.
    shaftL=(2455-310);lateral=(rotor_mass+jam)*G*c['lateral_accel_g']
    bending=lateral*shaftL/4
    sig=c['shaft_bending_factor']*32*bending/(math.pi*d['shaft_d']**3)+axial/(math.pi*d['shaft_d']**2/4)
    tau=c['shaft_torsion_factor']*16*c['torque_limiter_nm']*1000/(math.pi*d['shaft_d']**3)
    shaftvm=math.sqrt(sig*sig+3*tau*tau)
    check('스크루 축 복합응력',shaftvm,allow,'MPa','상·하 지지, 횡하중 중앙집중+축추력+리미터 비틀림; 응력집중계수 포함')
    check('하부 가이드 반력',lateral/2,c['lower_guide_radial_allowable_n'],'N','하부는 방사방향만 안내; 축하중은 상부 스러스트 베어링')
    radial=(d['screw_d']-d['shaft_d'])/2;flightpressure=jam_thrust/(ann*1e6)
    check('나선 날개 국부 굽힘',3*flightpressure*radial**2/d['flight_t']**2,allow,'MPa','리미터 축추력이 한 바퀴 면적에 균일 분포하는 외팔 판 근사; 국부 돌 끼임 별도')
    check('나선 루트 용접 전단',jam_thrust/(2*.707*4*math.pi*d['shaft_d']),allow/math.sqrt(3),'MPa','양면 연속 4 mm 필릿, 한 바퀴 유효 길이 가정')

    # Outfeed is supported by its own cradle/feet; do not load the thin casing as a cantilever.
    chute_length=math.hypot(d['outlet_x']-1030,d['outlet_z']-2020)/1000
    chute_volume=chute_length*(d['chute_width']/1000)*(d['chute_height']/1000)
    blocked=chute_volume*rho;chute_dead=groups['Supported Outfeed']
    chute_load=(blocked+chute_dead)*G*kd
    check('배출 슈트 세로 보',chute_load/2*550/4/out['modulus_mm3'],allow,'MPa','전체 배출부 자중+측벽까지 정체된 감자, 2개 보, 지지 간격 550 mm')
    check('배출 후방 가로 받침',chute_load*.6*1360/4/out['modulus_mm3'],allow,'MPa','후방 받침 60% 하중, 단순지지 경간 1360 mm')
    check('배출 전방 기둥 압축',chute_load*.3/out['area_mm2'],allow,'MPa','전방 기둥 각각 30% 분담; 횡가새 별도 존재')
    floorpressure=legP/(200*200-4*math.pi*9**2)
    check('바닥 발판 굽힘',3*floorpressure*((200-d['leg_b'])/2)**2/20**2,allow,'MPa','균일 지압의 캔틸레버 스트립; 콘크리트/앵커 허용치는 미확정')
    # Tip screen for empty, working, abnormal-full. Anchor capacity is not assumed.
    tip=[]
    for label,m,z in (('빈 수조',0,0),('정상 습식',operating_contents,(floor+c['water_level_z_mm'])/2),
                      ('이상 만재',fault_contents,(floor+d['tank_top_z'])/2)):
        tot=dead+m;zbar=(dead*cg[2]+m*z)/tot;ybar=dead*cg[1]/tot
        factor=(780-abs(ybar))/(c['lateral_accel_g']*zbar) if c['lateral_accel_g'] else None
        tip.append(dict(case=label,cg_z_mm=zbar,factor=factor))
        if factor is not None:check(label+' 횡전도',1.5,factor,'안전율','수평 관성하중만 고려, 횡 발판 반폭 780 mm; 앵커 저항 제외')
    # First bending mode is only a shaft screening model, not a complete machine modal analysis.
    shaftI=math.pi*(d['shaft_d']/1000)**4/64;rot_line=(rotor_mass+jam+20)/(shaftL/1000)
    critical_rpm=60*math.pi/(2*(shaftL/1000)**2)*math.sqrt(E*1e6*shaftI/rot_line)
    cycles=n*60*c['hours_per_day']*c['days_per_month']*12*c['design_years']
    inputkw=nominal['shaft_kw']/(c['gear_efficiency']*c['motor_efficiency_estimate']*c['vfd_efficiency'])+c['motor_fixed_loss_kw']+c['control_and_fan_kw']
    nameplatekw=c['motor_kw']/(c['motor_rated_efficiency_estimate']*c['vfd_efficiency'])+c['control_and_fan_kw']
    hours=c['hours_per_day']*c['days_per_month'];kwh=(inputkw*c['running_fraction']+c['control_and_fan_kw']*(1-c['running_fraction']))*hours
    current=c['motor_kw']*1000/(math.sqrt(3)*c['supply_v']*c['motor_rated_efficiency_estimate']*c['motor_pf'])
    warnings=[x['name']+': 재선정 필요' for x in checks if x['utilization']>1]
    if max(x['vfd_hz'] for x in speedcases)>60+1e-8:warnings.append('최고속에서 60 Hz 기저속도 초과')
    if free<=0:warnings.append('유효 수조 체적이 0 이하')
    boxspecs=[dict(s,kind='circle',radius=s['radius'],inner=0,depth=s['pitch']/4) if s['kind']=='helix' else s for s in specs]
    return dict(revision=REVISION,inputs=c,dimensions=d,input_sha256=hashlib.sha256(json.dumps(dict(inputs=c,dimensions=d),sort_keys=True).encode()).hexdigest(),
        status='예비 계산 / 실제 습식 이송 성능·피로수명·CATIA 실행 검증 전',bbox=core.bounding_box(boxspecs),
        groups_mass_kg=dict(groups),bom=bom,bare_mass_kg=bare,dead_mass_kg=dead,dead_cg_mm=cg,
        internal_tank_mm=[1000*L,1000*W,1000*H],gross_tank_m3=gross,internal_displacement_m3=internal,
        wet_available_volume_m3=free,dry_available_volume_m3=fullfree,wet_geometric_potato_capacity_kg=wetcap,
        dry_geometric_potato_capacity_kg=drycap,working_potato_kg=working,operating_water_kg=watermass,
        operating_contents_kg=operating_contents,packed_wet_water_kg=packedwater,
        fault_contents_kg=fault_contents,operating_total_kg=dead+operating_contents,fault_total_kg=total,
        bulk_density_kg_m3=rho,vertical_design_n=wd,horizontal_design_n=horizontal,leg_design_n=legP,
        allowable_mpa=allow,base_beam_stress_mpa=beamstress,base_beam_yield_factor=fy/beamstress,
        capacity_model_kg_h=modelcap,capacity_required_rpm=needed_rpm,
        capacity_rpm_with_reserve=needed_rpm*c['capacity_reserve_factor'],raw_kg_min=c['target_kg_h']/60,
        screw_axial_speed_m_s=vz,lift_height_m=lift,transit_seconds=transit,normal_screw_inventory_kg=moving,
        jam_screw_inventory_kg=jam,screw_tip_speed_m_s=omega*d['screw_d']/2000,
        tank_inventory_minutes=working/c['target_kg_h']*60,nominal_drive=nominal,speed_cases=speedcases,
        rotor_mass_kg=rotor_mass,rotor_inertia_kg_m2=rotorJ,upper_axial_n=axial,
        upper_total_vertical_n=top_vertical,upper_arm_load_n=armP,upper_arm_stress_mpa=armSigma,
        limiter_ideal_axial_n=jam_thrust,lower_radial_n=lateral/2,shaft_vm_mpa=shaftvm,
        bolt_preload_n=bolt_pretension,bolt_external_n=bolt_external,bolt_positions_mm=[[160,0],[0,160],[-160,0],[0,-160]],
        chute_blocked_potato_kg=blocked,chute_design_n=chute_load,foot_pressure_mpa=floorpressure,
        critical_shaft_rpm_screen=critical_rpm,vibration_cycle_estimate=cycles,tip_cases=tip,
        input_power_kw=inputkw,nameplate_input_kw=nameplatekw,estimated_motor_current_a=current,
        month_kwh=kwh,month_cost_krw=kwh*c['energy_rate_krw_kwh']+c['extra_demand_charge_krw_month'],
        nameplate_month_kwh=nameplatekw*hours,kwh_per_raw_tonne=inputkw/c['target_kg_h']*1000,
        checks=checks,warnings=warnings)


def station_geometry(overrides=None):
    c=configuration(overrides);s=make_specs(c);r=analyze(c,s)
    return s,dict(name='02_SO_Welded_CrossSupport_R5',description='SUS304 welded wet destoner with four-arm cross support and independently supported outfeed.',
        inlet=(0,0,DIM['inlet_z']),outlet=(DIM['outlet_x'],0,DIM['outlet_z']),length=r['bbox']['max_mm'][0],
        engineering_revision=REVISION,engineering_inputs=c,input_sha256=r['input_sha256'],
        geometry_envelope_mm=r['bbox'],dimensions=DIM,material='SUS304',report='02_SO_Design_Review.html',
        source_urls={s[0]:s[2] for s in SOURCES},engineering_warnings=r['warnings'],
        assumptions='Redesign dimensions, wet transport coefficients, vibration loads and bought-in component masses are estimates.',
        material_assignment='Specification parameters only; no CATIA catalog material assignment claimed.')


def report_html(r):
    from review_layout import compact_report
    return compact_report(2,r)


def write_report(output_dir,overrides=None):
    r=analyze(overrides);folder=Path(output_dir);folder.mkdir(parents=True,exist_ok=True)
    path=folder/'02_SO_Design_Review.html'
    path.write_text(report_html(r),encoding='utf-8')
    (folder/'02_SO_Calculations.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return path,r


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config',type=Path)
    ap.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parent/'Overall_Review'/'02_SO_Design_Review')
    args=ap.parse_args()
    try:
        overrides=json.loads(args.config.read_text(encoding='utf-8-sig')) if args.config else None
        path,r=write_report(args.output_dir,overrides)
    except (ValueError,OSError) as exc:ap.error(str(exc))
    print('SAVED '+str(path.resolve()),flush=True)
    print('STATUS '+('RESELECTION_REQUIRED' if r['warnings'] else 'PRELIMINARY_SCREEN_WITHIN_LIMITS'),flush=True)


if __name__=='__main__':main()
