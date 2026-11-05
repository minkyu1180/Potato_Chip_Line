"""Station 01: welded SUS304 hopper, shared CAD inputs and engineering review.

Standard library only. This module NEVER opens CATIA.
    py station1_design.py
    py station1_design.py --config station1_config.json --output-dir D:\\VBK
The generated HTML is self-contained and can be printed to PDF in a browser.
Dimensions: mm; stress: N/mm2 (MPa); mass: kg; power: kW.
This is an auditable preliminary sizing model, not a certified fabrication design.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import html
import json
import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

REVISION = 'VBK-R4.1-2026-11-01'
G = 9.80665
I = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))
AX = ((0., 1., 0.), (0., 0., 1.), (1., 0., 0.))
AY = ((1., 0., 0.), (0., 0., -1.), (0., 1., 0.))
STEEL, FRAME, BELT, DRIVE = (190, 198, 204), (85, 111, 125), (44, 132, 157), (51, 86, 142)

DEFAULTS = {
    'material': 'SUS304', 'steel_density_kg_m3': 7930.,
    'yield_mpa': 205., 'elastic_modulus_mpa': 193000., 'poisson_ratio': .30,
    'frame_type': 'tube',
    'potato_density_kg_m3': 1100., 'packing_fraction': .65,
    'headspace_mm': 150., 'working_mass_limit_kg': 2000.,
    'side_sheet_mm': 6., 'end_sheet_mm': 8.,
    'gate_opening_mm': 150., 'bed_profile_factor': .80,
    'target_kg_h': 1000., 'min_speed_m_min': .15, 'max_speed_m_min': .80,
    'vertical_dynamic_factor': 1.5, 'lateral_accel_g': .10,
    'yield_safety_factor': 2., 'leg_load_share': .25, 'crossbeam_load_share': .50,
    'eccentricity_mm': 20., 'weld_leg_mm': 5., 'bearing_weld_leg_mm': 6.,
    'mass_allowance_fraction': .10,
    'running_roll_coefficient': .04, 'starting_roll_coefficient': .06,
    'running_hopper_coefficient': .25, 'starting_hopper_coefficient': .45,
    'running_fixed_drag_n': 200., 'starting_fixed_drag_n': 300.,
    'start_seconds': 3., 'drive_service_factor': 1.5,
    'pulley_wet_friction': .25, 'pulley_wrap_deg': 180.,
    'belt_pretension_each_span_n': 32000.,
    'belt_allowable_working_tension_n_mm': 70.,
    'motor_kw': .75, 'motor_rpm_at_60hz': 1750., 'motor_pf': .75,
    'gear_ratio': 1000., 'gear_efficiency': .75,
    'motor_efficiency_estimate': .70, 'motor_rated_efficiency_estimate': .80,
    'vfd_efficiency': .96, 'motor_low_speed_torque_factor': .85,
    'motor_rotor_inertia_kg_m2': .003,
    'gear_continuous_torque_nm': 3000., 'gear_peak_torque_nm': 4000.,
    'torque_limiter_nm': 2200., 'motor_no_load_loss_kw': .080,
    'aux_power_kw': .060, 'supply_v': 380., 'supply_hz': 60.,
    'outfeed_motor_kw': .09, 'outfeed_speed_m_min': 1.2,
    'outfeed_gear_ratio': 300., 'outfeed_gear_efficiency': .65,
    'outfeed_no_load_loss_kw': .025,
    'hours_per_day': 8., 'days_per_month': 22., 'running_fraction': 1.,
    'assumed_all_in_energy_krw_kwh': 160.,
    'incremental_demand_charge_krw_month': 0.,
}

SOURCES = [
    ('S1', 'Nippon Steel: SUS304 판재 물성·강종표',
     'https://www.nipponsteel.com/product/catalog_download/pdf/S008.pdf',
     'SUS304: 0.2% 내력 205 MPa, 밀도 7.93 g/cm³, 탄성계수 193 GPa. 관재·봉재 구매 시 같은 하한을 성적서로 확인.'),
    ('S2', 'Rulmeca: Hopper feeder loading',
     'https://www.rulmeca.com/en/rulmeca-corporation/19/cc/hoppers/9',
     '호퍼에서 인출하는 추가 저항을 일반 이송 저항에 합산. 본 계산의 감자 마찰계수는 실측치가 아닌 명시적 가정.'),
    ('S3', 'Oriental Motor: Technical Reference',
     'https://www.orientalmotor.com/products/pdfs/F_TecRef/TecRefAll.pdf',
     '속도·드럼 회전수·기동 부하·감속비를 함께 검토하는 구동 선정 절차.'),
    ('S4', 'SEW-EURODRIVE: 60 Hz gearmotors',
     'https://download.sew-eurodrive.com/download/pdf/22742654_G01.pdf',
     '인버터 운전 시 모터 열적 허용토크와 감속기 사용 조건을 확인. 이 보고서는 특정 구매 모델을 선정한 것이 아님.'),
    ('S5', 'Worldstainless: Food and beverage industry',
     'https://worldstainless.org/applications/industrial-applications/food-and-beverage-industry/',
     '식품 설비는 강종뿐 아니라 표면·용접·세척 가능한 구조가 중요.'),
    ('S6', 'University of Florida IFAS: Sanitary design (UC Davis 보관)',
     'https://ucfoodsafety.ucdavis.edu/files/26502.pdf',
     '식품 접촉부 연속 용접과 세척 가능한 이음부 설계 참고.'),
    ('S7', 'KEPCO: 2026년 전기요금 개편 설명',
     'https://www.kepco.co.kr/KEPCO_FILE/html/2026_08/issue.html',
     '계약종별·계절·시간대에 따라 요금이 다름. 160원/kWh는 공식 한전 단가가 아닌 비교용 총 변동단가 가정.'),
]


def configuration(overrides=None):
    c = copy.deepcopy(DEFAULTS)
    if overrides:
        unknown = set(overrides) - set(c)
        if unknown:
            raise ValueError('Unknown station1 inputs: ' + ', '.join(sorted(unknown)))
        c.update(overrides)
    if c['material'] != 'SUS304':
        raise ValueError('This revision is sized for user-confirmed SUS304 only.')
    if c['frame_type'] not in ('tube', 'solid'):
        raise ValueError('frame_type must be tube or solid')
    for k, v in c.items():
        if isinstance(v, bool) or (k not in ('material', 'frame_type') and
                (not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0)):
            raise ValueError(f'Invalid nonnegative finite input: {k}={v!r}')
    for k in ('steel_density_kg_m3','yield_mpa','elastic_modulus_mpa','potato_density_kg_m3',
              'target_kg_h','gate_opening_mm','side_sheet_mm','end_sheet_mm','start_seconds',
              'gear_ratio','motor_rpm_at_60hz','supply_v','supply_hz','yield_safety_factor',
              'outfeed_speed_m_min','outfeed_gear_ratio','weld_leg_mm','working_mass_limit_kg',
              'bearing_weld_leg_mm','motor_kw','outfeed_motor_kw','gear_continuous_torque_nm',
              'gear_peak_torque_nm','torque_limiter_nm','pulley_wet_friction','pulley_wrap_deg',
              'belt_pretension_each_span_n','belt_allowable_working_tension_n_mm'):
        if c[k] <= 0: raise ValueError(f'{k} must be positive')
    for k in ('packing_fraction','bed_profile_factor','gear_efficiency','motor_efficiency_estimate',
              'motor_rated_efficiency_estimate','vfd_efficiency','motor_pf',
              'motor_low_speed_torque_factor','outfeed_gear_efficiency'):
        if not 0 < c[k] <= 1: raise ValueError(f'{k} must be in (0, 1]')
    if not 0 <= c['running_fraction'] <= 1: raise ValueError('running_fraction must be in [0, 1]')
    if not 0 <= c['headspace_mm'] < 1190: raise ValueError('headspace_mm must be 0..1190 (exclusive)')
    if not 80 <= c['gate_opening_mm'] <= 300: raise ValueError('Gate travel is 80..300 mm; revise geometry beyond this')
    if not .15 <= c['leg_load_share'] <= 1 or not 1/3 <= c['crossbeam_load_share'] <= 1:
        raise ValueError('Load shares cannot be less than equal distribution')
    if c['vertical_dynamic_factor'] < 1 or c['yield_safety_factor'] < 1:
        raise ValueError('Dynamic and safety factors must be >= 1')
    if not 0 < c['min_speed_m_min'] <= c['max_speed_m_min']:
        raise ValueError('Invalid speed range')
    if not 0 < c['poisson_ratio'] < .5: raise ValueError('Invalid Poisson ratio')
    if c['side_sheet_mm'] > 12 or c['end_sheet_mm'] > 20:
        raise ValueError('Revise hopper interfaces for larger sheet thickness')
    if c['pulley_wrap_deg'] != 180:
        raise ValueError('This geometry has 180-degree wrap; revise CAD before changing wrap angle')
    if c['supply_hz'] != 60:
        raise ValueError('Motor speed map in this revision is based on a 60-Hz nameplate')
    return c


def sections(c):
    # Main cross members carry a narrow live bottom across a 2100 mm span.
    # Solid alternative is independently enlarged; it is not a hollow-size alias.
    if c['frame_type'] == 'tube':
        return dict(leg=(80.,5.), cross=(160.,8.), rail=(100.,6.), brace=(50.,4.))
    return dict(leg=(70.,0.), cross=(130.,0.), rail=(100.,0.), brace=(40.,0.))


def section_properties(b, t):
    inner = b - 2*t if t else 0.
    area = b*b - inner*inner
    inertia = (b**4 - inner**4)/12
    return dict(area_mm2=area, inertia_mm4=inertia, modulus_mm3=2*inertia/b,
                mass_kg_m_at_reference_density=area*DEFAULTS['steel_density_kg_m3']/1e6)


def vadd(a,b): return tuple(x+y for x,y in zip(a,b))
def vmul(a,k): return tuple(x*k for x in a)
def vsub(a,b): return tuple(x-y for x,y in zip(a,b))
def vnorm(v): return math.sqrt(sum(x*x for x in v))
def vunit(v): return vmul(v,1/vnorm(v))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def rect(w,h): return ((-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2))


def polygon_area_centroid(points):
    pairs = list(zip(points, points[1:]+points[:1]))
    a2 = sum(x*v-u*y for (x,y),(u,v) in pairs)
    if abs(a2) < 1e-10: raise ValueError('Zero-area profile')
    return abs(a2)/2, (sum((x+u)*(x*v-u*y) for (x,y),(u,v) in pairs)/(3*a2),
                      sum((y+v)*(x*v-u*y) for (x,y),(u,v) in pairs)/(3*a2))


def part_mass(spec, c):
    if spec['kind'] == 'circle':
        area = math.pi*(spec['radius']**2-spec.get('inner',0)**2); uv=(0.,0.)
    else:
        area, uv = polygon_area_centroid(spec['points'])
        mx,my=area*uv[0],area*uv[1]
        for loop in spec.get('loops',()):
            a,(x,y)=polygon_area_centroid(loop);area-=a;mx-=a*x;my-=a*y
        for x,y,r in spec.get('holes',()):
            a=math.pi*r*r;area-=a;mx-=a*x;my-=a*y
        if area <= 0: raise ValueError('Non-positive net area: '+spec['name'])
        uv=mx/area,my/area
    centroid=spec['origin']
    for axis,d in zip(spec['axes'],(*uv,spec['depth']/2)): centroid=vadd(centroid,vmul(axis,d))
    mass=spec.get('mass_override_kg',area*spec['depth']*spec.get('density_kg_m3',c['steel_density_kg_m3'])/1e9)
    return mass,centroid,area*spec['depth']/1e9


def bounding_box(specs):
    lo=[float('inf')]*3;hi=[-float('inf')]*3
    for s in specs:
        if s['kind']=='circle':
            # Exact extrema of an oriented cylindrical primitive.
            center=vadd(s['origin'],vmul(s['axes'][2],s['depth']/2))
            radii=[s['radius']*math.hypot(s['axes'][0][j],s['axes'][1][j])+
                   abs(s['axes'][2][j])*s['depth']/2 for j in range(3)]
            verts=[tuple(center[j]+sign*radii[j] for j in range(3)) for sign in (-1,1)]
        else:
            verts=[vadd(s['origin'],vadd(vadd(vmul(s['axes'][0],x),vmul(s['axes'][1],y)),
                                      vmul(s['axes'][2],z))) for x,y in s['points'] for z in (0,s['depth'])]
        for p in verts:
            for j in range(3): lo[j]=min(lo[j],p[j]);hi[j]=max(hi[j],p[j])
    return dict(min_mm=lo,max_mm=hi,size_mm=[hi[j]-lo[j] for j in range(3)])


def stiffener_layout(c):
    """Nominal fit-up dimensions shared by CAD, mass and the design review."""
    sec=sections(c);thickness=8.;depth=50.;positions=[];bays=[]
    for left,right in ((100.,1100.),(1100.,2100.)):
        lo=left+sec['leg'][0]/2;hi=right-sec['leg'][0]/2
        first,last=lo+thickness/2,hi-thickness/2
        count=math.ceil((last-first)/400.)+1
        positions.extend(first+(last-first)*i/(count-1) for i in range(count))
        bays.append((lo,hi))
    ny,nz=890/math.hypot(675,890),-675/math.hypot(675,890)
    t=c['side_sheet_mm']
    # Intersect each offset slope face with the corresponding vertical collar face.
    def joint(d):return (1000+d,1910+890/675*d+d/nz)
    near,far=joint(t),joint(t+depth)
    top=2230-sec['rail'][0]
    slope=((325+ny*t,1020+nz*t),near,far,
           (325+ny*(t+depth),1020+nz*(t+depth)))
    collar=(near,far,(far[0],top),(near[0],top))
    span_positions=[100.,*positions,2100.]
    return dict(rib_thickness_mm=thickness,rib_depth_mm=depth,
                column_clear_bays_x_mm=bays,side_rib_centers_x_mm=positions,
                side_panel_max_span_mm=max(b-a for a,b in zip(span_positions,span_positions[1:])),
                top_z_mm=top,slope_profile_abs_yz_mm=slope,collar_profile_abs_yz_mm=collar,
                miter_near_abs_yz_mm=near,miter_far_abs_yz_mm=far,
                gate_max_top_z_mm=1020+300+350,gate_clearance_mm=10.,
                front_header_bottom_z_mm=1680.,front_header_top_z_mm=1680+sec['leg'][0],
                front_header_span_mm=1492.,front_free_edge_height_mm=1680-1320,
                end_regular_panel_span_mm=500.)


def clip_stiffener_profile(points, normal, limit):
    """Clip a convex YZ profile to normal dot point <= limit (nominal contact)."""
    if not points:return ()
    out=[]
    for a,b in zip(points,points[1:]+points[:1]):
        da=sum(u*v for u,v in zip(normal,a))-limit
        db=sum(u*v for u,v in zip(normal,b))-limit
        if da<=1e-8:out.append(a)
        if (da < -1e-8 and db > 1e-8) or (da > 1e-8 and db < -1e-8):
            f=da/(da-db);out.append(tuple(a[j]+f*(b[j]-a[j]) for j in range(2)))
    clean=[]
    for p in out:
        if not clean or math.dist(clean[-1],p)>1e-7:clean.append(p)
    if len(clean)>1 and math.dist(clean[0],clean[-1])<1e-7:clean.pop()
    if len(clean)<3:return ()
    if abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(clean,clean[1:]+clean[:1])))<1e-7:return ()
    return tuple(clean)


def cope_rear_stiffener(points, brace_size):
    """Split at both rear brace outer faces, including the hollow interior envelope."""
    pieces=[tuple(points)]
    for side in (-1,1):
        a=(-side*1050.,360.);dy=side*2100.;dz=1240.;length=math.hypot(dy,dz)
        n=(-dz/length,dy/length);k=sum(u*v for u,v in zip(n,a));out=[]
        for piece in pieces:
            for normal,limit in ((n,k-brace_size/2),(tuple(-x for x in n),-k-brace_size/2)):
                clipped=clip_stiffener_profile(piece,normal,limit)
                if clipped:out.append(clipped)
        pieces=out
    return pieces


def make_specs(c):
    s=[];group='Welded Support Frame';sec=sections(c)
    def add(spec, **attrs):
        spec.update(group=group,material='SUS304',density_kg_m3=c['steel_density_kg_m3'])
        spec.update(attrs);s.append(spec);return spec
    def poly(name,points,depth,origin,axes=I,color=STEEL,loops=(),**attrs):
        return add(dict(name='01_'+name,kind='poly',points=tuple(points),depth=depth,origin=origin,
                        axes=axes,color=color,loops=tuple(loops),holes=()),**attrs)
    def box(name,corner,size,color=STEEL,**attrs):
        x,y,z=corner;w,d,h=size
        return poly(name,rect(w,d),h,(x+w/2,y+d/2,z),color=color,**attrs)
    def member(name,a,b,w,h=None,t=0,color=FRAME,**attrs):
        h=w if h is None else h;axis=vunit(vsub(b,a));ref=(0.,0.,1.) if abs(axis[2])<.9 else (0.,1.,0.)
        u=vunit(cross(ref,axis));v=cross(axis,u)
        item=poly(name,rect(w,h),vnorm(vsub(b,a)),a,(u,v,axis),color,
                  loops=(tuple(reversed(rect(w-2*t,h-2*t))),) if t else (),**attrs)
        if t:
            # Recessed caps fill the cavity; continuous seal welds are specified, not faked as solids.
            for j,end in enumerate((0,item['depth']-t)):
                poly(name+f'_Seal_Cap_{j}',rect(w-2*t,h-2*t),t,vadd(a,vmul(axis,end)),(u,v,axis),color)
        return item
    def tube(name,a,b,key):
        w,t=sec[key];return member(name,a,b,w,t=t,stock_section=f'{w:g}x{w:g}'+(f'x{t:g}' if t else ' solid'))
    def cyl(name,a,b,r,inner=0,color=STEEL,**attrs):
        axis=vunit(vsub(b,a));ref=(0.,0.,1.) if abs(axis[2])<.9 else (0.,1.,0.)
        u=vunit(cross(ref,axis));v=cross(axis,u)
        return add(dict(name='01_'+name,kind='circle',radius=r,inner=inner,depth=vnorm(vsub(b,a)),
                        origin=a,axes=(u,v,axis),color=color,holes=()),**attrs)
    # Six main columns, three full-width deck beams, closed perimeter and side bracing.
    for x in (100,1100,2100):
        for side in (-1,1):
            y=side*1050
            tube(f'Column_{x}_{side}',(x,y,20),(x,y,2230),'leg')
            foot=box(f'Anchor_Foot_{x}_{side}',(x-100,y-100,0),(200,200,20),FRAME)
            foot['holes']=((-70,-70,9),(70,-70,9),(70,70,9),(-70,70,9))
            # Load-spreading gussets at beam-column nodes.
            for z in (770-sec['cross'][0],2100):
                poly(f'Gusset_{x}_{side}_{z:g}',((0,0),(-side*160,0),(0,120)),8,
                     (x-4,y-side*40,z),AX,FRAME)
        tube(f'Deck_Crossbeam_{x}',(x,-1050,770-sec['cross'][0]/2),
             (x,1050,770-sec['cross'][0]/2),'cross')
    for side in (-1,1):
        for z in (360,2230-sec['rail'][0]/2):
            tube(f'Side_Longitudinal_{side}_{z:g}',(100,side*1050,z),(2100,side*1050,z),'rail')
        for x in (100,1100):
            tube(f'Side_Diagonal_{side}_{x}',(x,side*1050,360),(x+1000,side*1050,1600),'brace')
        for x in (100,1100,2100):
            box(f'Conveyor_Pedestal_{side}_{x}',(x-40,side*400-40,770),(80,80,119-sec['rail'][0]),FRAME)
        tube(f'Conveyor_Stringer_{side}',(100,side*400,889-sec['rail'][0]/2),
             (2260,side*400,889-sec['rail'][0]/2),'rail')
    # Rear X braces resist transverse racking without blocking the product throat.
    for side in (-1,1):
        tube(f'Rear_Transverse_Diagonal_{side}',(60,-side*1050,360),(60,side*1050,1600),'brace')
    for x in (100,2100):
        tube(f'Top_End_Rim_{x}',(x,-1050,2230-sec['rail'][0]/2),(x,1050,2230-sec['rail'][0]/2),'rail')

    group='Hopper and Reinforcement';t=c['side_sheet_mm'];te=c['end_sheet_mm'];layout=stiffener_layout(c)
    section=((-1000,2210),(-1000,1910),(-325,1020),(325,1020),(1000,1910),(1000,2210))
    poly('Hopper_Rear',section,te,(100,0,0),AX)
    front=((-1000,2210),(-1000,1910),(-325,1020),(-325,1320),
           (325,1320),(325,1020),(1000,1910),(1000,2210))
    poly('Hopper_Front_With_Throat',front,te,(2100-te,0,0),AX)
    for side in (-1,1):
        # Slope thickness is measured normal to the plate, not horizontally.
        ny,nz=890/math.hypot(675,890),-675/math.hypot(675,890)
        p0=(side*325,1020);p1=(side*1000,1910)
        poly(f'Hopper_Slope_{side}',(p0,p1,(p1[0]+side*ny*t,p1[1]+nz*t),
             (p0[0]+side*ny*t,p0[1]+nz*t)),2000,(100,0,0),AX)
        box(f'Hopper_Collar_{side}',(100,-1000-t if side<0 else 1000,1908),(2000,t,302))
        for x in layout['side_rib_centers_x_mm']:
            # Both polygon profiles share the same full miter face; no buried ends.
            for label,key in (('Slope','slope_profile_abs_yz_mm'),('Collar','collar_profile_abs_yz_mm')):
                poly(f'{label}_Stiffener_{side}_{x:g}',tuple((side*y,z) for y,z in layout[key]),
                     layout['rib_thickness_mm'],(x-layout['rib_thickness_mm']/2,0,0),AX)
    # Header bridges the moving gate. Inner front ribs land on its top face,
    # while the header ends meet the inner faces of the outer front ribs.
    header_center=layout['front_header_bottom_z_mm']+sec['leg'][0]/2
    tube('Front_Gate_Header',(2100+sec['leg'][0]/2,-746,header_center),
         (2100+sec['leg'][0]/2,746,header_center),'leg')
    for x in (100-25,2100+25):
        for y in (-750,-250,250,750):
            def low(yedge):
                bottom=1020+max(0,abs(yedge)-325)*890/675
                if x>2000 and abs(y)<325:bottom=layout['front_header_top_z_mm']
                return bottom
            profile=((y-4,low(y-4)),(y+4,low(y+4)),
                     (y+4,layout['top_z_mm']),(y-4,layout['top_z_mm']))
            pieces=cope_rear_stiffener(profile,sec['brace'][0]) if x<100 else [profile]
            for i,piece in enumerate(pieces,1):
                suffix=f'_Segment_{i:02d}' if len(pieces)>1 else ''
                poly(f'End_Stiffener_{x}_{y}{suffix}',piece,50,(x-25,0,0),AX)

    group='Metering Gate'
    box('Gate_Plate',(2102,-325,1020+c['gate_opening_mm']),(8,650,350),STEEL)
    for side in (-1,1):
        box(f'Gate_Slide_Guide_{side}',(2110,side*340-15,1100),(15,30,620),FRAME)
    member('Gate_Handwheel_Screw',(2120,0,1370),(2120,0,1790),20,color=DRIVE)
    cyl('Gate_Handwheel',(2120,0,1780),(2120,0,1790),70,58,DRIVE)

    group='Live Bottom Conveyor'
    belt_density=1250.;belt_width=670.;r=100.;bt=6.;z=914.
    for name,z0 in (('Carry_Run',1014),('Return_Run',808)):
        box('Belt_'+name,(120,-335,z0),(2140,670,6),BELT,material='Food-contact reinforced TPU belt',density_kg_m3=belt_density)
    for x,angles in ((120,(90,270)),(2260,(-90,90))):
        theta=[math.radians(angles[0]+(angles[1]-angles[0])*i/24) for i in range(25)]
        pts=tuple(((r+bt)*math.cos(a),-(r+bt)*math.sin(a)) for a in theta)+tuple((r*math.cos(a),-r*math.sin(a)) for a in reversed(theta))
        poly(f'Belt_End_Wrap_{x}',pts,670,(x,-335,z),AY,BELT,material='Food-contact reinforced TPU belt',density_kg_m3=belt_density)
        cyl(f'Drum_{x}',(x,-335,z),(x,335,z),100,92)
        cyl(f'Drum_Shaft_{x}',(x,-650,z),(x,700,z),75)
        for side in (-1,1):
            cyl(f'Drum_End_Disc_{x}_{side}',(x,side*327-4,z),(x,side*327+4,z),100,75)
            box(f'Drum_Bearing_{x}_{side}',(x-110,side*550-80,816),(220,160,196),DRIVE,
                material='Purchased sealed bearing unit',mass_override_kg=15.)
            # Bearing bases sit outside the belt/stringers, supported by welded outriggers.
            tube(f'Drum_Bearing_Outrigger_{x}_{side}',(x,side*400,804-sec['rail'][0]/2),
                 (x,side*550,804-sec['rail'][0]/2),'rail')
            box(f'Drum_Bearing_Seat_{x}_{side}',(x-110,side*550-80,804),(220,160,12),FRAME)
            box(f'Drum_Bearing_Dropper_{x}_{side}',(x-40,side*400-40,764),(80,80,125-sec['rail'][0]),FRAME)
            if x==120:
                cyl(f'Tail_Takeup_Screw_{side}',(20,side*550,785),(220,side*550,785),12,color=DRIVE)
                box(f'Tail_Takeup_Anchor_{side}',(30,side*550-30,760),(30,60,55),FRAME)
    # 17 carrying rollers. Full hopper load is conservatively assigned to the belt.
    for i in range(17):
        x=220+115*i
        cyl(f'Carry_Roller_{i}',(x,-335,984),(x,335,984),30,25)
        cyl(f'Carry_Axle_{i}',(x,-420,984),(x,420,984),25)
        for side in (-1,1):
            box(f'Carry_Roller_Riser_{i}_{side}',(x-25,side*400-25,889),(50,50,70),FRAME)
            box(f'Carry_Bearing_{i}_{side}',(x-30,side*400-25,959),(60,50,50),DRIVE,
                material='Purchased sealed bearing unit',mass_override_kg=1.5)
    for side in (-1,1):
        box(f'Belt_Skirt_{side}',(105,side*326-3,1015),(2120,6,80),BELT,
            material='Food-contact elastomer skirt',density_kg_m3=1200.)

    group='Outfeed Roller Conveyor'
    for side in (-1,1):
        tube(f'Outfeed_Rail_{side}',(2350,side*355,940),(3310,side*355,940),'rail')
        tube(f'Outfeed_Leg_{side}',(3250,side*355,20),(3250,side*355,940),'leg')
        foot=box(f'Outfeed_Foot_{side}',(3150,side*355-100,0),(200,200,20),FRAME)
        foot['holes']=((-70,-70,9),(70,-70,9),(70,70,9),(-70,70,9))
        tube(f'Outfeed_Connection_{side}',(2100,side*400,889-sec['rail'][0]/2),
             (2420,side*355,940),'rail')
        box(f'Outfeed_Guide_{side}',(2345,side*309-3,1017),(1030,6,183),STEEL)
    for i in range(12):
        x=2387+80*i
        cyl(f'Outfeed_Roller_{i}',(x,-305,982),(x,305,982),38,33)
        cyl(f'Outfeed_Shaft_{i}',(x,-395,982),(x,425,982),15)
        for side in (-1,1):
            box(f'Outfeed_Bearing_{i}_{side}',(x-20,side*355-18,962),(40,36,40),DRIVE,
                material='Purchased sealed bearing unit',mass_override_kg=.7)
        cyl(f'Outfeed_Sprocket_Envelope_{i}',(x,398,982),(x,408,982),32,15,DRIVE,
            material='Purchased sprocket (tooth envelope)',mass_override_kg=.35)
    box('Outfeed_Chain_Envelope',(2387,390,1011),(880,26,6),DRIVE,
        material='Purchased chain, simplified envelope',mass_override_kg=4.)
    box('Outfeed_Chain_Guard',(2337,430,925),(1000,3,145),(218,158,62))
    poly('Exit_Lip',((3305,-1020),(3375,-1000),(3375,-1006),(3305,-1026)),610,(0,-305,0),AY)

    group='Drive Systems'
    # Purchased equipment: explicit mass overrides, never solid-steel bounding-box masses.
    box('Main_Gearmotor_Mount',(2110,650,794),(300,480,20),FRAME)
    box('Main_Gearbox_Envelope',(2135,680,814),(250,200,200),DRIVE,
        material='Purchased compound helical gear unit',mass_override_kg=75.)
    cyl('Main_Motor_Envelope',(2260,880,914),(2260,1120,914),85,color=DRIVE,
        material=f"Purchased {c['motor_kw']:g} kW motor, forced cooling",mass_override_kg=16.)
    cyl('Main_Torque_Limiter_Envelope',(2260,630,914),(2260,680,914),95,color=DRIVE,
        material='Purchased adjustable torque limiter',mass_override_kg=6.)
    box('Outfeed_Drive_Mount',(3140,445,850),(240,280,15),FRAME)
    box('Outfeed_Gearmotor_Envelope',(3187,455,902),(160,240,160),DRIVE,
        material=f"Purchased {c['outfeed_motor_kw']:g} kW gearmotor",mass_override_kg=12.)
    cyl('Outfeed_Coupling',(3267,408,982),(3267,455,982),25,color=DRIVE)

    group='Electrical Controls'
    box('Control_Enclosure',(200,-1130,1150),(400,80,500),FRAME,
        material='Purchased control panel including two VFDs',mass_override_kg=15.)
    box('High_Level_Sensor',(500,-1010,2040),(45,35,60),DRIVE,
        material='Purchased level sensor',mass_override_kg=.3)
    return s


def hopper(c, height_mm):
    """Exact clear prismatic volume + centroid: trapezoid up to 890, then rectangle."""
    h=height_mm/1000; hs=min(h,.89);hu=max(0,h-.89)
    k=(2.-.65)/.89;area=.65*hs+k*hs*hs/2+2*hu
    moment=.65*hs*hs/2+k*hs**3/3+2*(.89*hu+hu*hu/2)
    length=(2000-2*c['end_sheet_mm'])/1000
    return dict(volume_m3=length*area, centroid_z_mm=1020+1000*moment/area if area else 1020)


def analyze(c, specs=None, include_comparison=True):
    c=configuration(c);specs=make_specs(c) if specs is None else specs
    layout=stiffener_layout(c)
    massrows=[];groups=defaultdict(float);mom=[0.,0.,0.]
    for s in specs:
        mass,cg,volume=part_mass(s,c);groups[s['group']]+=mass
        for j in range(3):mom[j]+=mass*cg[j]
        massrows.append(dict(name=s['name'],group=s['group'],material=s['material'],
                             mass_kg=mass,volume_m3=volume,centroid_mm=cg,
                             basis='purchased estimate' if 'mass_override_kg' in s else 'geometry x density'))
    base_mass=sum(groups.values());allowance=base_mass*c['mass_allowance_fraction'];dead=base_mass+allowance
    cg=[v/base_mass for v in mom]
    rho=c['potato_density_kg_m3']*c['packing_fraction']
    gross=hopper(c,1190);usable=hopper(c,1190-c['headspace_mm'])
    full_mass=gross['volume_m3']*rho;working=min(usable['volume_m3']*rho,c['working_mass_limit_kg'])
    wd=(dead+full_mass)*G*c['vertical_dynamic_factor'];fy=c['yield_mpa'];ns=c['yield_safety_factor']
    allow=fy/ns;E=c['elastic_modulus_mpa'];sec=sections(c);checks=[]
    def check(name,demand,limit,unit,basis):
        checks.append(dict(name=name,demand=demand,limit=limit,unit=unit,
                           utilization=demand/limit,margin=limit/demand if demand else None,
                           result='계산조건 충족' if demand<=limit else '재선정 필요',basis=basis))
    crossp=section_properties(*sec['cross']);legp=section_properties(*sec['leg']);railp=section_properties(*sec['rail'])
    # Center point load deliberately overestimates the moment from two belt rails.
    beam_p=wd*c['crossbeam_load_share'];span=2100.;bm=beam_p*span/4
    beamstress=bm/crossp['modulus_mm3'];beamdef=beam_p*span**3/(48*E*crossp['inertia_mm4'])
    check('하부 횡보 굽힘',beamstress,allow,'MPa','P=전체 동하중×횡보분담률; M=P L/4; σ=M/Z, L=2100 mm')
    check('하부 횡보 처짐',beamdef,span/300,'mm','δ=P L³/(48 E I); 단순지지 중앙집중하중; 한계 L/300')
    lp=wd*c['leg_load_share'];legL=2210.
    euler=math.pi**2*E*legp['inertia_mm4']/legL**2
    rankine=1/(1/(legp['area_mm2']*fy)+1/euler)
    axial=lp/legp['area_mm2'];bend=lp*c['eccentricity_mm']/legp['modulus_mm3']
    interaction=lp/(rankine/ns)+bend/allow
    check('기둥 압축+편심 굽힘',axial+bend,allow,'MPa','기둥 6개 중 1개에 전체 동하중의 25%; 편심 20 mm 기본값')
    check('기둥 좌굴·편심 상호작용',interaction,1.,'비율','전장 2210 mm, K=1, Rankine 보수 선별식 + M/Z; 규격 좌굴곡선 검토 별도')
    railP=wd/2/2 # two rails and two 1000-mm bays, full assembly load conservatively retained
    railM=railP*1000/4
    check('벨트 세로 레일 굽힘',railM/railp['modulus_mm3'],allow,'MPa','전체 동하중/4를 1000 mm 경간 중앙집중하중으로 가정')
    check('벨트 세로 레일 처짐',railP*1000**3/(48*E*railp['inertia_mm4']),1000/300,'mm','단순지지 L/300')
    horizontal=(dead+full_mass)*G*c['lateral_accel_g']
    bp=section_properties(*sec['brace']);bl=math.hypot(1000,1240)
    braceF=horizontal/2/(1000/bl)
    braceEuler=math.pi**2*E*bp['inertia_mm4']/bl**2
    braceRankine=1/(1/(bp['area_mm2']*fy)+1/braceEuler)
    check('측면 가새 압축 좌굴',braceF,braceRankine/ns,'N','수평 관성하중, 두 측면 가새 분담; K=1, Rankine 선별')
    # One-way simply-supported plate strips. Full vertical pressure used for lateral pressure.
    pressure=rho*G*1.190*c['vertical_dynamic_factor']/1e6
    for label,t,spanp in (('경사판',c['side_sheet_mm'],layout['side_panel_max_span_mm']),
                          ('끝판 연속 보강 구간',c['end_sheet_mm'],layout['end_regular_panel_span_mm'])):
        check(label+' 굽힘',.75*pressure*spanp**2/t**2,allow,'MPa',f'p=ρbulk g H×동하중계수; σ=0.75 p a²/t²; a={spanp:g} mm, 수압형 등분포 상한 가정')
        check(label+' 처짐',5*pressure*spanp**4/(32*E*t**3),spanp/200,'mm',f'1 mm 폭 단순지지 스트립; δ=5 p a⁴/(32 E t³), a={spanp:g} mm, L/200')
    # The gate clearance interrupts the two central front ribs: do not apply the
    # regular 500-mm span to this unreinforced strip. Its top is seal-welded to
    # the new header; the opening edge below is free (ideal cantilever screen).
    free=layout['front_free_edge_height_mm'];end_t=c['end_sheet_mm']
    check('게이트 상부 끝판 자유단 굽힘',3*pressure*free**2/end_t**2,allow,'MPa',
          f'헤더 접합부 고정/개구부 자유단인 세로 판 스트립 가정; L={free:g} mm; σ=3 p L²/t²; 접합 회전강성 별도')
    check('게이트 상부 끝판 자유단 처짐',1.5*pressure*free**4/(E*end_t**3),free/100,'mm',
          'δ=1.5 p L⁴/(E t³); 자유단 서비스 한계 L/100은 본 설계의 가정, 규격 인증값 아님')
    hp=section_properties(*sec['leg']);header_span=layout['front_header_span_mm']
    tributary=free+(layout['top_z_mm']-layout['front_header_top_z_mm'])/2
    header_q=pressure*tributary
    check('게이트 헤더 굽힘',header_q*header_span**2/(8*hp['modulus_mm3']),allow,'MPa',
          f'정면 법선 방향 등분포하중 q=p×{tributary:g} mm; L={header_span:g} mm, M=q L²/8; 양끝 단순지지')
    check('게이트 헤더 처짐',5*header_q*header_span**4/(384*E*hp['inertia_mm4']),header_span/300,'mm',
          'δ=5 q L⁴/(384 E I); L/300, 헤더 끝 접합부 및 지지 보강재 국부 회전은 별도')
    weld_throat=.707*c['weld_leg_mm'];weldL=4*sec['leg'][0]
    weldtau=math.hypot(lp,horizontal/4)/(weld_throat*weldL)
    check('기둥 접합 용접부 직접전단',weldtau,allow/math.sqrt(3),'MPa','둘레 연속 필릿 a=0.707 s, τ=R/(a L); 모멘트·피로 및 관벽 국부파괴는 별도')
    footpressure=lp/(200*200-4*math.pi*9**2)
    check('베이스 플레이트 국부 굽힘',3*footpressure*((200-sec['leg'][0])/2)**2/20**2,allow,'MPa','균일 지압, 기둥 외측 돌출부 캔틸레버 스트립 근사')
    # Local flat wall elastic buckling screen (not a section class certification).
    for key in ('cross','leg','rail'):
        b,t=sec[key]
        if t:
            flat=b-2*t;elastic_plate=4*math.pi**2*E/(12*(1-c['poisson_ratio']**2))*(t/flat)**2
            check(key+' 관벽 탄성 국부좌굴 선별',fy,elastic_plate,'MPa','단순지지 k=4 판좌굴; 항복보다 먼저 탄성 국부좌굴하는지 선별')
    # Throughput is RAW potato throughput, not finished chips.
    line_kg_m=.650*(c['gate_opening_mm']/1000)*c['bed_profile_factor']*rho
    speed=c['target_kg_h']/60/line_kg_m;v=speed/60;R=.100;D=.200
    nr=speed/(math.pi*D);nm=nr*c['gear_ratio'];hz=nm/c['motor_rpm_at_60hz']*60
    belt_mass=sum(r['mass_kg'] for r in massrows if r['name'].startswith('01_Belt_') and 'Skirt' not in r['name'])
    # No arching benefit: entire full hopper weight in extraction resistance.
    def pull(m, start=False, mu=None):
        roll=c['starting_roll_coefficient' if start else 'running_roll_coefficient']
        hop=c['starting_hopper_coefficient' if start else 'running_hopper_coefficient'] if mu is None else mu
        fixed=c['starting_fixed_drag_n' if start else 'running_fixed_drag_n']
        return roll*(m+belt_mass)*G+hop*m*G+fixed
    runF=pull(full_mass);startF=pull(full_mass,True)+(full_mass+belt_mass)*v/c['start_seconds']
    # Rotating roller/shaft inertia reflected to the belt. J = m*(ro²+ri²)/2.
    J_equiv=0.
    for s in specs:
        if s['kind']=='circle' and any(k in s['name'] for k in ('Carry_Roller_','Carry_Axle_','Drum_')) and 'Bearing' not in s['name']:
            m,_,_=part_mass(s,c);J=m*((s['radius']/1000)**2+(s.get('inner',0)/1000)**2)/2
            surfaceR=.030 if 'Carry_' in s['name'] else R
            J_equiv+=J*(R/surfaceR)**2
    inertia_torque=J_equiv*(v/R)/c['start_seconds']
    runT=runF*R;startT=startF*R+inertia_torque;designT=startT*c['drive_service_factor']
    nominalMotorT=c['motor_kw']*1000/(c['motor_rpm_at_60hz']*2*math.pi/60)
    available=nominalMotorT*c['gear_ratio']*c['gear_efficiency']*c['motor_low_speed_torque_factor']
    motorAccel=c['motor_rotor_inertia_kg_m2']*(nm*2*math.pi/60)/c['start_seconds']
    requiredMotorT=designT/(c['gear_ratio']*c['gear_efficiency'])+motorAccel
    check('주 구동 모터 토크',requiredMotorT,nominalMotorT*c['motor_low_speed_torque_factor'],'N·m','출력축 기동토크×서비스계수/(iηg) + 모터 자체 가속토크; 강제냉각 가정')
    check('감속기 연속 토크 정격',runT*c['drive_service_factor'],c['gear_continuous_torque_nm'],'N·m','정상 최대 충전 인출토크×서비스계수')
    check('감속기 순간 토크 정격',designT,c['gear_peak_torque_nm'],'N·m','기동 설계 토크')
    check('토크리미터 설정 여유',designT,c['torque_limiter_nm'],'N·m','기동 설계토크보다 높고 전달계 허용값보다 낮게 설정')
    # Traction and shaft loads at limiter setting: include large pre-tension reactions.
    limitPull=c['torque_limiter_nm']/R;tractionRatio=math.exp(c['pulley_wet_friction']*math.radians(c['pulley_wrap_deg']))
    pretension=c['belt_pretension_each_span_n'];tight=pretension+limitPull/2;slack=pretension-limitPull/2
    tractionAvailable=2*pretension*(tractionRatio-1)/(tractionRatio+1)
    check('습윤 드럼 마찰 전달',limitPull,tractionAvailable,'N','Fmax=2 T0 (exp(μθ)-1)/(exp(μθ)+1); 총장력 보존 근사, 습윤 μ는 가정')
    check('벨트 최대 운전장력',tight/670,c['belt_allowable_working_tension_n_mm'],'N/mm','Ttight=T0+Flimit/2; 벨트 허용 작업장력(파단강도 아님) 최소 구매요구')
    # Shaft D150, 1100-mm bearing spacing, full radial tension resultant plus torque.
    shaftM=(2*pretension)*1100/4;shaftD=150.;Kt=1.6
    shaftSigma=Kt*32*shaftM/(math.pi*shaftD**3);shaftTau=Kt*16*c['torque_limiter_nm']*1000/(math.pi*shaftD**3)
    shaftVM=math.sqrt(shaftSigma**2+3*shaftTau**2)
    check('주 드럼 축 D150 복합응력',shaftVM,allow,'MPa','키홈 계수 1.6; M=(Ttight+Tslack) L/4; L=1100 mm, von Mises 굽힘+비틀림')
    bearingRadial=pretension+full_mass*G/17/2
    check('주 드럼 베어링 정격하중 요구',bearingRadial*2,80000.,'N','각 베어링 반력×2 ≤ 예비 정정격 C0 80 kN; 동수명·밀봉 구매검토 별도')
    check('벨트 레일 굽힘+장력 압축',railM/railp['modulus_mm3']+pretension/railp['area_mm2'],allow,'MPa','보수적 수직하중 굽힘과 각 레일의 드럼 장력 반력 압축을 합산')
    outrig_m=pretension*150
    check('드럼 베어링 받침 횡굽힘',outrig_m/railp['modulus_mm3'],allow,'MPa','각 베어링 장력 반력 × 횡방향 돌출 150 mm; 레일과 같은 단면')
    wb=sec['rail'][0];wa=.707*c['bearing_weld_leg_mm']
    weld_bend=outrig_m/(4*wa*wb*wb/3);weld_shear=pretension/(4*wa*wb)
    check('드럼 받침 접합 용접 복합응력',math.hypot(weld_bend,math.sqrt(3)*weld_shear),allow,'MPa','사각 둘레 용접군 Z=4 a b²/3, Aw=4ab; 횡굽힘+전단 선별, 국부 관벽 별도')
    rollerP=full_mass*G*c['vertical_dynamic_factor']*2/17
    check('받침 롤러 축 D50 굽힘',32*(rollerP*800/4)/(math.pi*50**3),allow,'MPa','17개 롤러, 불균등분담 2배, 중앙집중하중; 베어링 간격 800 mm')
    # Outfeed is independently driven so its rollers actually carry potatoes forward.
    out_m=line_kg_m*.96;outF=.08*(out_m+30)*G+30;outT=outF*.038
    outnr=c['outfeed_speed_m_min']/(math.pi*.076);outnm=outnr*c['outfeed_gear_ratio']
    outMotorT=c['outfeed_motor_kw']*1000/(c['motor_rpm_at_60hz']*2*math.pi/60)
    outAvail=outMotorT*c['outfeed_gear_ratio']*c['outfeed_gear_efficiency']*.8
    check('배출 롤러 구동 토크',outT*2,outAvail,'N·m','벨트 위 0.96 m분 감자+회전체 30 kg, 등가저항 0.08, 기동계수 2')
    # Energy: separate predicted load, fixed losses, and nameplate input envelope.
    opF=pull(working);shaftkw=opF*v/1000
    mainElec=shaftkw/(c['gear_efficiency']*c['motor_efficiency_estimate']*c['vfd_efficiency'])+c['motor_no_load_loss_kw']
    outElec=outF*(c['outfeed_speed_m_min']/60)/1000/(c['outfeed_gear_efficiency']*.55*c['vfd_efficiency'])+c['outfeed_no_load_loss_kw']
    runningkw=mainElec+outElec+c['aux_power_kw']
    fullinput=(c['motor_kw']+c['outfeed_motor_kw'])/(c['motor_rated_efficiency_estimate']*c['vfd_efficiency'])+c['aux_power_kw']
    avgkw=runningkw*c['running_fraction']+c['aux_power_kw']*(1-c['running_fraction'])
    hours=c['hours_per_day']*c['days_per_month'];energy=avgkw*hours
    current=c['motor_kw']*1000/(math.sqrt(3)*c['supply_v']*c['motor_rated_efficiency_estimate']*c['motor_pf'])
    avgflow=c['target_kg_h']*c['running_fraction'];batch=working/c['target_kg_h']*60
    # Lateral tipping screen, empty and full; no anchorage resistance credited.
    tip=[]
    for label,mass,zload in (('빈 호퍼',0,0),('만재 호퍼',full_mass,gross['centroid_z_mm'])):
        total=dead+mass;zc=(dead*cg[2]+mass*zload)/total
        yc=dead*cg[1]/total;lever=1150-abs(yc)
        factor=lever/(c['lateral_accel_g']*zc) if c['lateral_accel_g'] else None
        tip.append(dict(case=label,cg_z_mm=zc,side_tip_factor=factor))
        if factor is not None:check(label+' 횡방향 전도',1.5,factor,'안전율','받침 폭 2300 mm, H=m g ah, 외력 추가 없는 관성하중; 목표 1.5')
    # Mathematical load ceilings for two controlling submodels, not rated payloads.
    beam_payload_ceiling=allow*crossp['modulus_mm3']*4/(2100*c['crossbeam_load_share']*G*c['vertical_dynamic_factor'])-dead
    constant_start=c['starting_roll_coefficient']*belt_mass*G+c['starting_fixed_drag_n']+belt_mass*v/c['start_seconds']
    slope_start=(c['starting_roll_coefficient']+c['starting_hopper_coefficient'])*G+v/c['start_seconds']
    drive_payload_ceiling=(c['torque_limiter_nm']/c['drive_service_factor']-inertia_torque-R*constant_start)/(R*slope_start)
    speed_rows=[]
    for label,sp in (('최저',c['min_speed_m_min']),('기준',speed),('최고',c['max_speed_m_min'])):
        nout=sp/(math.pi*D);motor_n=nout*c['gear_ratio']
        fstart=pull(full_mass,True)+(full_mass+belt_mass)*(sp/60)/c['start_seconds']
        tstart=(fstart*R+J_equiv*(sp/60/R)/c['start_seconds'])*c['drive_service_factor']
        mt=tstart/(c['gear_ratio']*c['gear_efficiency'])+c['motor_rotor_inertia_kg_m2']*(motor_n*2*math.pi/60)/c['start_seconds']
        speed_rows.append(dict(case=label,speed_m_min=sp,raw_kg_h=line_kg_m*sp*60,
                               drum_rpm=nout,motor_rpm=motor_n,hz=motor_n/c['motor_rpm_at_60hz']*60,
                               required_motor_nm=mt))
    check('최고속 기동 모터 토크',speed_rows[-1]['required_motor_nm'],nominalMotorT*c['motor_low_speed_torque_factor'],'N·m','설정 최대 속도에서 3초 기동; 모터/롤러 자체 관성 포함')
    warnings=[]
    if not c['min_speed_m_min'] <= speed <= c['max_speed_m_min']:warnings.append('목표 처리량에 필요한 벨트 속도가 설정 운전범위를 벗어남.')
    if c['max_speed_m_min']/(math.pi*D)*c['gear_ratio'] > c['motor_rpm_at_60hz']:warnings.append('최대 속도에서 60 Hz 기저속도를 초과: 감속비 재선정 필요.')
    if outnm>c['motor_rpm_at_60hz']:warnings.append('배출 모터가 기저속도를 초과: 감속비 재선정 필요.')
    if c['working_mass_limit_kg'] > usable['volume_m3']*rho:warnings.append('작업 질량 한도를 여유높이 기준 용량으로 제한함.')
    warnings.extend(x['name']+': 재선정 필요' for x in checks if x['utilization']>1)
    result=dict(revision=REVISION,inputs=c,input_sha256=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest(),
        status='예비 설계 계산 — 제작 승인/피로수명 검증 아님',geometry_bbox=bounding_box(specs),
        sections=sec,stiffener_layout=layout,
        stiffener_mass_kg=sum(row['mass_kg'] for row in massrows if 'Stiffener_' in row['name']),
        front_header_mass_kg=sum(row['mass_kg'] for row in massrows if 'Front_Gate_Header' in row['name']),
        front_header_end_reaction_n=header_q*header_span/2,
        groups_mass_kg=dict(groups),base_mass_kg=base_mass,mass_allowance_kg=allowance,
        dead_mass_kg=dead,dead_cg_mm=cg,bom=massrows,bulk_density_kg_m3=rho,
        gross_volume_m3=gross['volume_m3'],headspace_volume_m3=usable['volume_m3'],
        brim_potato_mass_kg=full_mass,headspace_potato_mass_kg=usable['volume_m3']*rho,
        working_potato_mass_kg=working,loaded_working_mass_kg=dead+working,loaded_brim_mass_kg=dead+full_mass,
        design_vertical_load_n=wd,design_horizontal_load_n=horizontal,leg_design_load_n=lp,
        material_allowable_mpa=allow,beam_stress_mpa=beamstress,beam_yield_factor=fy/beamstress,
        beam_allowable_margin=allow/beamstress,leg_euler_n=euler,leg_rankine_n=rankine,
        foot_bearing_pressure_mpa=footpressure,checks=checks,tip_cases=tip,speed_cases=speed_rows,
        crossbeam_payload_ceiling_kg=beam_payload_ceiling,drive_payload_ceiling_kg=drive_payload_ceiling,
        line_load_kg_m=line_kg_m,speed_m_min=speed,drum_rpm=nr,motor_rpm=nm,vfd_hz=hz,
        raw_kg_min=c['target_kg_h']/60,batch_minutes=batch,belt_mass_kg=belt_mass,
        run_pull_n=runF,start_pull_n=startF,run_torque_nm=runT,start_torque_nm=startT,
        design_torque_nm=designT,required_motor_torque_nm=requiredMotorT,available_output_torque_nm=available,
        run_mechanical_kw=runF*v/1000,rotating_inertia_kg_m2=J_equiv,
        belt_tight_n=tight,belt_slack_n=slack,traction_capacity_n=tractionAvailable,
        outfeed_torque_nm=outT,outfeed_rpm=outnr,outfeed_motor_rpm=outnm,
        outfeed_vfd_hz=outnm/c['motor_rpm_at_60hz']*60,
        estimated_running_kw=runningkw,nameplate_input_envelope_kw=fullinput,
        estimated_main_motor_current_a=current,monthly_energy_kwh=energy,monthly_run_hours=hours*c['running_fraction'],
        monthly_cost_krw=energy*c['assumed_all_in_energy_krw_kwh']+c['incremental_demand_charge_krw_month'],
        nameplate_monthly_energy_kwh=fullinput*hours,average_raw_throughput_kg_h=avgflow,
        energy_kwh_per_raw_tonne=runningkw/c['target_kg_h']*1000,warnings=warnings)
    if include_comparison:
        alt=dict(c,frame_type='solid' if c['frame_type']=='tube' else 'tube')
        ar=analyze(alt,include_comparison=False)
        result['alternative']=dict(frame_type=alt['frame_type'],sections=ar['sections'],
            dead_mass_kg=ar['dead_mass_kg'],frame_mass_kg=ar['groups_mass_kg']['Welded Support Frame'],
            beam_stress_mpa=ar['beam_stress_mpa'],beam_yield_factor=ar['beam_yield_factor'],
            warnings=ar['warnings'])
    return result


def station_geometry(overrides=None):
    c=configuration(overrides);s=make_specs(c);r=analyze(c,s)
    meta=dict(name='01_VBK_Welded_R4_1_'+c['frame_type'].upper(),
              description='SUS304 welded hopper with live bottom and powered roller outfeed; preliminary sized design.',
              inlet=(1100,0,2210),outlet=(3375,0,1000),length=r['geometry_bbox']['max_mm'][0],
              engineering_revision=REVISION,engineering_inputs=c,input_sha256=r['input_sha256'],
              geometry_envelope_mm=r['geometry_bbox'],material='SUS304',
              mass_calculation='Analytic component volume x density plus purchased mass estimates and 10% allowance; not CATIA mass measurement.',
              report='01_VBK_Design_Review.html',engineering_status=r['status'],engineering_warnings=r['warnings'])
    return s,meta


def fmt(value, digits=1):
    return f'{value:,.{digits}f}' if isinstance(value,(int,float)) else str(value)


def report_html(r):
    from review_layout import compact_report
    return compact_report(1,r)


def write_report(output_dir, overrides=None):
    c=configuration(overrides);r=analyze(c);out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    target=out/'01_VBK_Design_Review.html'
    target.write_text(report_html(r),encoding='utf-8')
    (out/'01_VBK_Calculations.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return target,r


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path)
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parent/'Overall_Review'/'01_VBK_Design_Review')
    args=parser.parse_args()
    c=json.loads(args.config.read_text(encoding='utf-8-sig')) if args.config else None
    path,r=write_report(args.output_dir,c)
    print('SAVED '+str(path.resolve()),flush=True)
    print('STATUS '+('RESELECTION_REQUIRED' if r['warnings'] else 'PRELIMINARY_SCREEN_WITHIN_LIMITS'),flush=True)


if __name__=='__main__':main()
