"""Stations 3/4: native welded supports and reproducible engineering reviews.

Pure Python, no CATIA activation. Dimensions and empirical process inputs are
provisional redesign values, not certified ratings of the Sormac machines.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import station1_design as core
import station2_design as so

G=9.80665
REVISION='PEELERS-R12-2026-11-01'
add,sub,mul,unit,cross,norm=core.vadd,core.vsub,core.vmul,core.vunit,core.cross,core.vnorm
I,AX,AY=core.I,core.AX,core.AY
DIM={
    3:dict(code='CRP',label='Roller Peeler',name='03_CRP_12_Welded_R12',
           length=2700.,process_radius=443.,shaft_radius=50.,screw_radius=425.,pitch=600.,axis_z=2250.,
           x0=600.,x1=3450.,half=800.,beam_z=1340.,cross_z=1130.,column_top=3065.,
           leg=(100.,6.),beam=(140.,8.),brace=(60.,4.),aux=(80.,5.),
           ports=[dict(key='Infeed',a=(0.,0.,2200.),b=(640.,0.,2080.),w0=915.,w1=915.,h=200.,xs=(80.,500.)),
                  dict(key='Outfeed',a=(3490.,0.,1700.),b=(3815.,0.,1550.),w0=600.,w1=600.,h=250.,xs=(3530.,3730.))]),
    4:dict(code='MS',label='Knife Peeler',name='04_MS_20_Supported_R12',
           length=2000.,process_radius=407.,shaft_radius=45.,screw_radius=385.,pitch=500.,axis_z=1770.,
           x0=550.,x1=2700.,half=650.,beam_z=820.,cross_z=820.,column_top=2330.,
           leg=(80.,5.),beam=(120.,6.),brace=(50.,4.),aux=(80.,5.),
           ports=[dict(key='Infeed',a=(0.,0.,1535.),b=(550.,0.,1420.),w0=660.,w1=460.,h=280.,xs=(80.,480.)),
                  dict(key='Outfeed',a=(2695.,0.,1340.),b=(3070.,0.,1140.),w0=600.,w1=500.,h=200.,xs=(2740.,2980.))]),
}
COMMON={
    'material':'SUS304','steel_density_kg_m3':7930.,'yield_mpa':205.,'E_mpa':193000.,
    'potato_density_kg_m3':1100.,'packing_fraction':.65,'mass_allowance_fraction':.10,
    'vertical_dynamic_factor':2.,'lateral_accel_g':.30,'yield_safety_factor':2.,
    'leg_load_share':.25,'crossbeam_load_share':.40,'leg_eccentricity_mm':20.,
    'chute_sheet_mm':6.,'chute_section_mm':80.,'chute_wall_mm':5.,
    'chute_extra_vertical_n':1000.,'weld_leg_mm':5.,
    'screw_rpm':6.,'screw_min_rpm':3.,'screw_max_rpm':8.,'axial_efficiency':.35,
    'normal_fill_limit':.15,'blocked_fill_fraction':.50,'transport_reserve_factor':1.20,
    'potato_friction':.35,'lead_efficiency':.40,'screw_empty_nm':25.,
    'start_seconds':5.,'breakaway_factor':1.5,'drive_service_factor':1.30,
    'screw_motor_kw':1.1,'screw_ratio':200.,'screw_gear_efficiency':.75,
    'screw_limiter_nm':600.,'screw_gear_continuous_nm':800.,'screw_gear_peak_nm':1200.,
    'motor_base_rpm':1750.,'low_speed_torque_factor':.80,'motor_efficiency':.85,
    'vfd_efficiency':.96,'motor_pf':.78,'peeling_gear_efficiency':.90,
    'control_power_kw':.06,'motor_fixed_loss_kw':.08,'supply_v':380.,'supply_hz':60.,
    'hours_per_day':8.,'days_per_month':22.,'running_fraction':1.,'design_years':5.,
    'energy_rate_krw_kwh':160.,'extra_demand_charge_krw_month':0.,
    'main_foot_mm':200.,'bearing_radial_allowable_n':30000.,'bearing_axial_allowable_n':15000.,
    'water_hold_up_kg':30.,'waste_hold_up_kg':30.,'control_cabinet_mass_kg':35.,
    'roller_shaft_d_mm':40.,'roller_limiter_nm':450.,'screw_motor_inertia_kg_m2':.004,
}
STAGE_DEFAULTS={
    3:dict(target_kg_h=1000.,peeling_loss_fraction=.10,peeling_rpm=300.,peeling_min_rpm=225.,peeling_max_rpm=350.,
           peeling_motor_kw=15.,peeling_drive_count=1.,peeling_ratio=5.,peeling_motor_inertia_kg_m2=.06,
           peeling_specific_kwh_t=2.5,peeling_empty_nm=25.,peeling_motor_mass_kg=90.,
           peeling_gear_mass_kg=45.,roller_core_wall_mm=4.,abrasive_density_kg_m3=2400.,
           suspension_belt_allowable_n=15000.,water_m3_h=.5),
    4:dict(target_kg_h=900.,peeling_loss_fraction=.04,peeling_rpm=15.,peeling_min_rpm=10.,peeling_max_rpm=17.5,
           peeling_motor_kw=1.1,peeling_drive_count=2.,peeling_ratio=10*445/45,peeling_motor_inertia_kg_m2=.004,
           peeling_specific_kwh_t=.25,peeling_empty_nm=30.,peeling_motor_mass_kg=16.,
           peeling_gear_mass_kg=18.,roller_core_wall_mm=4.,abrasive_density_kg_m3=2400.,
           suspension_belt_allowable_n=15000.,water_m3_h=.5),
}
SOURCES=[
    ('CRP','Sormac CRP-12 catalogue','https://static.sormac.com/f7/ca/f7ca880213395d291cf1ab670d102a92ce80231d.pdf',
     '12 rollers; published 3815 × 1515 × 3095 mm, 11.37 kW, 400 V / 50 Hz. Catalogue capacity is conditional, not this redesign performance.'),
    ('MS','Sormac MS catalogue','https://static.sormac.com/46/2a/462ab5d52d815c741828fec7655e9c8b8f33bfc1.pdf',
     'MS-20: 3250 × 1400 × 2360 mm; 2000 mm drum; 2.57 kW; 400 V, 50/60 Hz. Drum and auger speeds control residence/peeling.'),
    ('MAT','Nippon Steel SUS304','https://www.nipponsteel.com/product/catalog_download/pdf/S008.pdf',
     'Reference density 7930 kg/m³, proof strength 205 MPa, E 193 GPa. Actual tube and weld properties require supplier certificates.'),
    ('SCREW','KWS screw conveyor horsepower','https://www.kwsmfg.com/engineering-guides/screw-conveyor/screw-conveyor-horsepower/',
     'Friction and material resistance must be considered. Here empirical potato peeling and transport inputs are independent provisional assumptions.'),
    ('JOINT','Nord-Lock preload guidance','https://www.nord-lock.com/learnings/bolting-tips/2025/what-is-preload-and-why-is-it-important/',
     'Retained preload matters for removable joints. Welded main frames do not replace shaft alignment or fatigue assessment.'),
]


def configuration(index,overrides=None):
    if index not in DIM:raise ValueError('Peeler station must be 3 or 4')
    c=dict(COMMON,**STAGE_DEFAULTS[index])
    if overrides is not None:
        if not isinstance(overrides,dict):raise ValueError('Configuration must be a JSON object')
        extra=set(overrides)-set(c)
        if extra:raise ValueError('Unknown inputs: '+', '.join(sorted(extra)))
        c.update(overrides)
    if c['material']!='SUS304':raise ValueError('Structural material is SUS304')
    zero_ok={'water_hold_up_kg','waste_hold_up_kg','water_m3_h','lateral_accel_g','mass_allowance_fraction',
             'peeling_loss_fraction','chute_extra_vertical_n','running_fraction','energy_rate_krw_kwh','extra_demand_charge_krw_month'}
    for k,v in c.items():
        if k=='material':continue
        if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or v<0 or (not v and k not in zero_ok):
            raise ValueError(f'Invalid input {k}={v!r}')
    for k in ('packing_fraction','axial_efficiency','normal_fill_limit','blocked_fill_fraction','lead_efficiency',
              'screw_gear_efficiency','peeling_gear_efficiency','motor_efficiency','vfd_efficiency','motor_pf','low_speed_torque_factor'):
        if not 0<c[k]<=1:raise ValueError(k+' must be in (0,1]')
    if not 0<=c['peeling_loss_fraction']<1 or not 0<=c['running_fraction']<=1:raise ValueError('Invalid fraction')
    for k in ('vertical_dynamic_factor','yield_safety_factor','breakaway_factor','drive_service_factor','transport_reserve_factor'):
        if c[k]<1:raise ValueError(k+' must be >= 1')
    if not 3<=c['screw_min_rpm']<=c['screw_rpm']<=c['screw_max_rpm']<=8:raise ValueError('Screw speed range is 3..8 rpm')
    if not c['peeling_min_rpm']<=c['peeling_rpm']<=c['peeling_max_rpm']:raise ValueError('Invalid peeling speed range')
    if c['blocked_fill_fraction']<c['normal_fill_limit']:raise ValueError('Blocked fill must exceed normal fill')
    if c['peeling_drive_count']!=STAGE_DEFAULTS[index]['peeling_drive_count']:raise ValueError('Drive count must match geometry')
    if not 1/6<=c['leg_load_share']<=1 or not 1/3<=c['crossbeam_load_share']<=1:raise ValueError('Invalid load share')
    if not 4<=c['chute_sheet_mm']<=10 or not 60<=c['chute_section_mm']<=100 or not 3<=c['chute_wall_mm']<=8:
        raise ValueError('Chute stock dimensions outside supported envelope')
    if not 3<=c['roller_core_wall_mm']<=8:raise ValueError('Roller wall must be 3..8 mm')
    if not 35<=c['roller_shaft_d_mm']<=45:raise ValueError('Roller shaft must be 35..45 mm')
    if c['supply_hz']!=60:raise ValueError('Motor map is based on 60 Hz')
    return c


class Geometry(so.Geometry):
    def __init__(self,index,c):super().__init__(c);self.index=index
    def add(self,s,**kw):
        s.update(name=f'{self.index:02d}_'+s['name'],group=self.group,material='SUS304',density_kg_m3=self.c['steel_density_kg_m3'])
        s.update(kw);self.specs.append(s);return s
    def tube(self,name,a,b,section):return self.member(name,a,b,section[0],t=section[1])


def imported_specs(index):
    import build_line
    return getattr(build_line,f'draft_station{index}')()


def classify(name):
    if 'Transport_Auger' in name or ('Auger_' in name and any(t in name for t in ('Shaft','Stub'))):return 'Transport Auger'
    if name.startswith('CRP_Roller_') and not any(t in name for t in ('Drive','Bearing','Timing','Pulley')):return 'Peeling Rollers'
    if name.startswith(('MS_Knife_','MS_Blue_Drum','MS_Drum_')):return 'Peeling Drum and Knives'
    if any(t in name for t in ('Motor','Gearbox','Fan','_Fin_','Drive','Pulley','Timing','Suspension_Belt')):return 'Drives and Transmission'
    if any(t in name for t in ('Bearing','Spider','Stub')):return 'Bearing Supports'
    if any(t in name for t in ('Spray','Water','Waste','Peel_Collection')):return 'Water and Waste'
    if any(t in name for t in ('Control','EStop','Readout')):return 'Electrical Controls'
    return 'Housing and Service Covers'


def make_specs(index,c,base=None):
    base,meta=imported_specs(index) if base is None else base
    d=DIM[index];g=Geometry(index,c);specs=[]
    removed=('CRP_Post_','CRP_Foot_','CRP_Level_Screw_','CRP_End_Cross_','CRP_Long_Rail_',
             'CRP_Brace_','CRP_Feed_Cabinet_','CRP_Feed_Floor','CRP_Feed_Inner_Guide_','CRP_Product_Outfeed') if index==3 else (
             'MS_Leg_','MS_Foot_','MS_Level_Screw_','MS_Frame_Cross_','MS_Frame_Long_','MS_Brace_',
             'MS_Product_Infeed','MS_Infeed_Lip','MS_Product_Outfeed')
    for original in base:
        if original['name'].startswith(removed):continue
        s=dict(original);name=s['name'];s['group']=classify(name)
        s.update(material='SUS304',density_kg_m3=c['steel_density_kg_m3'])
        # Retain removable service supports but represent their hollow steel section.
        if s.get('part_type')=='Profile':
            w,h=s['profile_section_mm'];t=min(4.,min(w,h)/6)
            s['loops']=(tuple(reversed(core.rect(w-2*t,h-2*t))),)
            s['part_type']='Service Support';s['section_wall_mm']=t
        if s['kind']=='helix':s['normal_thickness']=True
        if index==3 and name.endswith('_Core') and name.startswith('CRP_Roller_'):
            s['inner']=s['radius']-c['roller_core_wall_mm']
        if index==3 and name.startswith('CRP_Roller_'):
            shaft_r=c['roller_shaft_d_mm']/2
            if name.endswith('_Shaft'):s['radius']=shaft_r
            elif name.endswith('_Bearing_Block'):s['holes']=((0.,0.,shaft_r+2),)
            elif name.endswith('_Bearing'):s.update(inner=shaft_r+1,radius=shaft_r+14)
            elif 'Timing_Pulley' in name or 'Pulley_Flange' in name:s['inner']=shaft_r
        if 'Carborundum_Sleeve' in name:
            s.update(material='Bonded abrasive composite (assumed)',density_kg_m3=c['abrasive_density_kg_m3'])
        elif 'MS_Knife_' in name:s['material']='Hardened stainless knife (grade pending)'
        elif any(t in name for t in ('_Belt_','_Gasket','_Shaft_Seal','Handle','Latch','Fan_Cover','Drive_Fan','Drum_Fan','Auger_Fan')):
            s.update(material='Polymer / elastomer envelope',density_kg_m3=1200.)
        # Motor housings represent bought-in items, not solid SUS304 blocks.
        if 'Gearbox' in name:
            s['mass_override_kg']=20. if 'Auger' in name else c['peeling_gear_mass_kg']
            s['material']='Purchased gearbox assembly'
        if ('Motor' in name and not any(t in name for t in ('Fin','Mount','Seat','Plate'))):
            s['mass_override_kg']=14. if 'Auger' in name else c['peeling_motor_mass_kg']
            s['material']='Purchased electric motor'
        if any(t in name for t in ('Motor_Fin','Fan_Cover','Drive_Fan','Drum_Fan','Auger_Fan')):
            s['mass_override_kg']=0.;s['material']='Visual detail included in motor mass'
        if name=='MS_Control_Cabinet':
            s['mass_override_kg']=c['control_cabinet_mass_kg'];s['material']='Purchased control cabinet incl. internals'
        specs.append(s)
    if index==3:
        g.group='Peeling Rollers'
        for s in list(specs):
            if s['name'].startswith('CRP_Roller_') and s['name'].endswith('_Core'):
                for j,offset in enumerate((0.,s['depth']-8)):
                    a=add(s['origin'],mul(s['axes'][2],offset))
                    g.cyl(s['name']+f'_End_Disc_{j}',a,add(a,mul(s['axes'][2],8)),s['inner'],inner=c['roller_shaft_d_mm']/2)
    main_frame(g,d,c)
    for port in d['ports']:supported_chute(g,port,c,d)
    specs.extend(g.specs)
    names=[s['name'] for s in specs]
    if len(names)!=len(set(names)):raise ValueError('Duplicate peeler component name')
    return specs,meta


def main_frame(g,d,c):
    g.group='Welded Support Frame';x0,x1,h=d['x0'],d['x1'],d['half'];xm=(x0+x1)/2
    zb=d['beam_z'];leg,beam,brace,aux=(d[x] for x in ('leg','beam','brace','aux'))
    for x in (x0,xm,x1):
        for side in (-1,1):
            y=side*h;top=d['column_top'] if x!=xm else zb+beam[0]/2
            g.tube(f'Main_Column_{x:g}_{side}',(x,y,20),(x,y,top),leg)
            b=c['main_foot_mm']
            g.box(f'Anchor_Foot_{x:g}_{side}',(x-b/2,y-b/2,0),(b,b,20),core.FRAME,
                  holes=tuple((a*(b/2-30),b_*(b/2-30),9) for a in (-1,1) for b_ in (-1,1)))
        g.tube(f'Base_Crossbeam_{x:g}',(x,-h,d['cross_z']),(x,h,d['cross_z']),beam)
    for side in (-1,1):
        y=side*h
        g.tube(f'Main_Longitudinal_{side}',(x0,y,zb),(x1,y,zb),beam)
        g.tube(f'Lower_Tie_{side}',(x0,y,300),(x1,y,300),aux)
        for j,(a,b) in enumerate(((x0,xm),(xm,x1))):
            g.tube(f'Side_Diagonal_{side}_{j}',(a,y,350),(b,y,zb-80),brace)
        if g.index==3:
            g.tube(f'Upper_Rail_{side}',(x0,y,3020),(x1,y,3020),aux)
            # End-frame cross plates carry the bearing spiders into the columns.
            for x in (x0,x1):
                g.tube(f'Upper_Side_Knee_{x:g}_{side}',(x,y,2650),(x+(250 if x==x0 else -250),y,3020),brace)
        else:
            g.tube(f'Upper_Rail_{side}',(x0,y,2280),(x1,y,2280),aux)
            for x in (x0,x1):
                g.tube(f'Upper_Side_Knee_{x:g}_{side}',(x,y,1900),(x+(250 if x==x0 else -250),y,2280),brace)
    for x in (x0,x1):
        g.tube(f'Transverse_Diagonal_{x:g}',(x,-h,300),(x,h,zb-80),brace)
        if g.index==3:
            g.tube(f'Upper_Cross_{x:g}',(x,-h,3020),(x,h,3020),aux)
            g.tube(f'Waste_Tray_Cross_{x:g}',(x,-h,1175),(x,h,1175),aux)
            g.box(f'Waste_Seat_{x:g}',(x-40,-200,1215),(80,400,5))
        else:
            g.tube(f'Upper_Cross_{x:g}',(x,-h,2280),(x,h,2280),aux)
        for side in (-1,1):
            # Vertical triangular gussets at beam-to-column joints.
            g.poly(f'Node_Gusset_{x:g}_{side}',((0,0),(-side*180,0),(0,-180)),8,
                   (x-4,side*h,zb+beam[0]/2),AX,core.FRAME)
    # End frames/roller bearing plates have broad seats, independent of side skins.
    for x in (d['x0']-50 if g.index==3 else d['x0'], d['x1']+45 if g.index==3 else d['x1']):
        if g.index==3:
            for side in (-1,1):
                g.box(f'End_Frame_Seat_{x:g}_{side}',(x-60,side*h-(250 if side>0 else 0),zb+beam[0]/2),
                      (120,250,20))
        else:
            g.box(f'End_Frame_Seat_{x:g}',(x-60,-h,zb+beam[0]/2),(120,2*h,20))


def supported_chute(g,p,c,d):
    key=p['key'];g.group=key+' and Support';a,b=p['a'],p['b'];w0,w1=p['w0'],p['w1'];t=c['chute_sheet_mm']
    x0,_,z0=a;x1,_,z1=b;h=p['h'];section=(c['chute_section_mm'],c['chute_wall_mm']);sb=section[0]
    g.quad(key+'_Floor',((x0,-w0/2,z0),(x1,-w1/2,z1),(x1,w1/2,z1),(x0,w0/2,z0)),t)
    for side in (-1,1):
        g.quad(key+f'_Guide_{side}',((x0,side*w0/2,z0),(x1,side*w1/2,z1),
               (x1,side*w1/2,z1+h),(x0,side*w0/2,z0+h)),t)
    slope=(z1-z0)/(x1-x0);nz=1/math.sqrt(1+slope*slope)
    floor=lambda x:z0+slope*(x-x0)
    rail_y=min(w0,w1)/2-70;leg_y=max(w0,w1)/2+80
    for side in (-1,1):
        g.tube(key+f'_Underfloor_Rail_{side}',(x0,side*rail_y,floor(x0)-(t+sb/2)/nz),
               (x1,side*rail_y,floor(x1)-(t+sb/2)/nz),section)
    for j,x in enumerate(p['xs']):
        z=floor(x)-(t+sb)/nz-sb/2
        g.tube(key+f'_Cradle_{j}',(x,-leg_y,z),(x,leg_y,z),section)
        for side in (-1,1):
            y=side*leg_y
            g.tube(key+f'_Support_Leg_{j}_{side}',(x,y,16),(x,y,z-sb/2),section)
            g.box(key+f'_Foot_{j}_{side}',(x-90,y-90,0),(180,180,16),core.FRAME,
                  holes=((-60,-60,9),(60,-60,9),(60,60,9),(-60,60,9)))
            g.poly(key+f'_Cradle_Gusset_{j}_{side}',((0,0),(-side*130,0),(0,-130)),8,
                   (x-4,y,z-sb/2),AX,core.FRAME)
        g.tube(key+f'_Lower_Cross_{j}',(x,-leg_y,300),(x,leg_y,300),(50.,4.))
        g.tube(key+f'_End_Diagonal_{j}',(x,-leg_y,300),(x,leg_y,z-sb-80),(50.,4.))
    xa,xb=p['xs']
    for side in (-1,1):
        y=side*leg_y
        g.tube(key+f'_Lower_Longitudinal_{side}',(xa,y,300),(xb,y,300),(50.,4.))
        g.tube(key+f'_Side_Diagonal_{side}',(xa,y,350),(xb,y,floor(xb)-(t+sb)/nz-sb-80),(50.,4.))
    # Floor ribs limit unsupported plate width without obstructing potatoes.
    for j,x in enumerate((x0+(x1-x0)/3,x0+2*(x1-x0)/3)):
        width=w0+(w1-w0)*(x-x0)/(x1-x0)
        g.member(key+f'_Floor_Rib_{j}',(x,-width/2,floor(x)-t/nz-20),
                 (x,width/2,floor(x)-t/nz-20),8,40)
    # Independent gravity support, with two-level lateral ties into the main
    # columns. Tall short stands must not rely on their unanchored footprint.
    attach_x=p['xs'][1] if key=='Infeed' else p['xs'][0]
    frame_x=d['x0'] if key=='Infeed' else d['x1']
    upper=min(d['beam_z'],floor(attach_x)-(t+sb)/nz-sb-150)
    for side in (-1,1):
        for j,z in enumerate((350.,upper)):
            g.tube(key+f'_Frame_Stability_Tie_{side}_{j}',(attach_x,side*leg_y,z),
                   (frame_x,side*d['half'],z),section)


def mass_info(s,c):
    if s['kind']=='helix':
        vol,r2,_,_=so.flight_section_data(s)
        mass=vol*s['density_kg_m3'];cg=add(s['origin'],mul(s['axes'][2],s['pitch']/8))
        return mass,cg,vol,mass*r2
    if s['kind']=='circle':
        area=math.pi*(s['radius']**2-s.get('inner',0)**2);mx=my=0.
    else:
        area,(cx,cy)=core.polygon_area_centroid(s['points']);mx=area*cx;my=area*cy
        for loop in s.get('loops',()):
            a,(cx,cy)=core.polygon_area_centroid(loop);area-=a;mx-=a*cx;my-=a*cy
    for x,y,radius in s.get('holes',()):
        a=math.pi*radius**2;area-=a;mx-=a*x;my-=a*y
    if area<=0:raise ValueError('Non-positive net section: '+s['name'])
    vol=area*s['depth']/1e9;mass=s.get('mass_override_kg',vol*s['density_kg_m3'])
    cg=s['origin']
    for axis,coordinate in zip(s['axes'],(mx/area,my/area,s['depth']/2)):
        cg=add(cg,mul(axis,coordinate))
    if vol<=0 or mass<0:raise ValueError('Invalid mass/volume: '+s['name'])
    J=mass*(s.get('radius',0)**2+s.get('inner',0)**2)/2e6 if s['kind']=='circle' else 0.
    return mass,cg,vol,J


def analyze(index,overrides=None,specs=None):
    c=configuration(index,overrides);d=DIM[index]
    if specs is None:specs,_=make_specs(index,c)
    groups=defaultdict(float);bom=[];mom=[0.,0.,0.];augerJ=0.;peelingJ=0.
    for s in specs:
        m,cg,v,J=mass_info(s,c);groups[s['group']]+=m
        for j in range(3):mom[j]+=m*cg[j]
        if s['group']=='Transport Auger':augerJ+=J
        if s['group']=='Peeling Rollers':peelingJ+=J
        if s['group']=='Peeling Drum and Knives':
            peelingJ+=m*((cg[1]/1000)**2+((cg[2]-d['axis_z'])/1000)**2)+J
        bom.append(dict(name=s['name'],group=s['group'],material=s['material'],mass_kg=m,volume_m3=v,
                        basis='구매품 추정 질량' if 'mass_override_kg' in s else 'Rib 단면 해석 근사' if s['kind']=='helix' else '순 체적 × 재료 밀도'))
    bare=sum(groups.values());dead=bare*(1+c['mass_allowance_fraction']);cg=[x/bare for x in mom]
    rho=c['potato_density_kg_m3']*c['packing_fraction'];L=d['length']/1000;R=d['process_radius']/1000;r=d['shaft_radius']/1000
    # Usable process envelope: lower half of the roller bed (3), whole drum (4).
    gross=(.5 if index==3 else 1)*math.pi*R*R*L
    screw_volume=sum(row['volume_m3'] for row in bom if row['group']=='Transport Auger')
    displacement=screw_volume*(.5 if index==3 else 1)
    free=max(0,gross-displacement);geometric_kg=free*rho
    pitch=d['pitch']/1000;speed=pitch*c['screw_rpm']/60*c['axial_efficiency'];residence=L/speed
    working=c['target_kg_h']/3600*residence
    nominal_limit=geometric_kg*c['normal_fill_limit'];blocked=geometric_kg*c['blocked_fill_fraction']
    capacity=nominal_limit/residence*3600
    kd=c['vertical_dynamic_factor'];allow=c['yield_mpa']/c['yield_safety_factor'];E=c['E_mpa'];checks=[]
    def ck(name,demand,limit,unit_,basis):
        checks.append(dict(name=name,demand=demand,limit=limit,unit=unit_,utilization=demand/limit,
                           result='가정 내 충족' if demand<=limit else '재선정 필요',basis=basis))
    ck('정상 재고 / 작업 충전 제한',working,nominal_limit,'kg','Q × 이동시간; 제품 품질/실측 체류시간 아님')
    ck('목표 유량 + 여유',c['target_kg_h']*c['transport_reserve_factor'],capacity,'kg/h','기하+이송효율 모형, 실측 처리량 아님')
    io=[]
    for p in d['ports']:
        length=norm(sub(p['b'],p['a']))/1000;volume=length*(p['w0']+p['w1'])/2000*p['h']/1000
        potato=volume*rho;mass=groups[p['key']+' and Support']*(1+c['mass_allowance_fraction'])
        load=(potato+mass)*G*kd+c['chute_extra_vertical_n'];span=max(p['w0'],p['w1'])+160
        sec=core.section_properties(c['chute_section_mm'],c['chute_wall_mm']);sleg=sec
        P=load*.60;M=P*span/4;legP=load*.35;legL=max(p['a'][2],p['b'][2])-150
        rankine=1/(1/(sleg['area_mm2']*c['yield_mpa'])+1/(math.pi**2*E*sleg['inertia_mm4']/legL**2))
        label='투입' if p['key']=='Infeed' else '배출'
        ck(label+' 받침보 굽힘',M/sec['modulus_mm3'],allow,'MPa','한 포털 60% 하중, 단순지지 중앙 집중')
        ck(label+' 받침보 처짐',P*span**3/(48*E*sec['inertia_mm4']),span/300,'mm','L/300')
        railspan=p['xs'][1]-p['xs'][0]
        overhang=max(p['xs'][0]-p['a'][0],p['b'][0]-p['xs'][1])
        ck(label+' 종방향 보 굽힘',load/2*max(railspan/4,overhang)/sec['modulus_mm3'],allow,'MPa','보 2개, 지지 경간과 돌출 끝 집중하중 중 큰 굽힘모멘트')
        ck(label+' 기둥 압축·좌굴',legP/(rankine/c['yield_safety_factor'])+legP*20/sleg['modulus_mm3']/allow,1.,'비율','K=1 Rankine, 편심 20 mm, 한 기둥 35%')
        stress=legP/(.707*c['weld_leg_mm']*4*c['chute_section_mm'])
        ck(label+' 기둥 접합 직접전단',stress,allow/math.sqrt(3),'MPa','둘레 필릿, 용접 피로·프라잉 별도')
        dx=railspan;dz=legL-430;bl=math.hypot(dx,dz);bs=core.section_properties(50.,4.)
        brace_load=(potato+mass)*G*c['lateral_accel_g']/2/(dx/bl)
        brace_limit=1/(1/(bs['area_mm2']*c['yield_mpa'])+1/(math.pi**2*E*bs['inertia_mm4']/bl**2))/c['yield_safety_factor']
        ck(label+' 측면 가새 좌굴',brace_load,brace_limit,'N','수평 관성하중, 양 측 가새의 종방향 성분')
        foot_pressure=legP/(180**2-4*math.pi*9**2)
        ck(label+' 발판 굽힘',3*foot_pressure*((180-c['chute_section_mm'])/2)**2/16**2,allow,'MPa','발판 캔틸레버 스트립; 앵커·콘크리트는 미확정')
        # Pressure from full retained potato depth, not a person stepping on the floor.
        pressure=rho*G*p['h']/1000*kd/1e6;floor_span=min(p['w0'],p['w1'])-140
        ck(label+' 바닥판 굽힘',.75*pressure*floor_span**2/c['chute_sheet_mm']**2,allow,'MPa','정체 감자 균일 압력, 종방향 보 사이 스트립')
        io.append(dict(key=p['key'],length_mm=length*1000,volume_m3=volume,blocked_potato_kg=potato,
                       structure_kg=mass,design_load_n=load,cradle_span_mm=span,leg_load_n=legP))
    blocked_total=blocked+sum(x['blocked_potato_kg'] for x in io)
    total=dead+blocked_total+c['water_hold_up_kg']+c['waste_hold_up_kg'];wd=total*G*kd;horizontal=total*G*c['lateral_accel_g']
    beam=core.section_properties(*d['beam']);leg=core.section_properties(*d['leg']);brace=core.section_properties(*d['brace'])
    span=2*d['half'];P=wd*c['crossbeam_load_share'];legP=wd*c['leg_load_share'];legL=d['column_top']-20
    ck('주 횡보 굽힘',P*span/4/beam['modulus_mm3'],allow,'MPa','전체 구조·정체 감자·물·폐기물의 40%, 보수적 중앙 집중')
    ck('주 횡보 처짐',P*span**3/(48*E*beam['inertia_mm4']),span/300,'mm','단순지지 L/300')
    longspan=(d['x1']-d['x0'])/2
    ck('주 종보 굽힘',wd*.25*longspan/4/beam['modulus_mm3'],allow,'MPa','중간 기둥으로 경간을 절반으로 나눔')
    euler=math.pi**2*E*leg['inertia_mm4']/legL**2
    rankine=1/(1/(leg['area_mm2']*c['yield_mpa'])+1/euler)
    ck('주 기둥 압축·좌굴',legP/(rankine/c['yield_safety_factor'])+legP*c['leg_eccentricity_mm']/leg['modulus_mm3']/allow,1.,'비율','6개 중 1개에 25%, 전장 K=1, 편심')
    braceL=math.hypot(longspan,d['beam_z']-430);braceF=horizontal/2/(longspan/braceL)
    braceRank=1/(1/(brace['area_mm2']*c['yield_mpa'])+1/(math.pi**2*E*brace['inertia_mm4']/braceL**2))
    ck('주 측면 가새 압축',braceF,braceRank/c['yield_safety_factor'],'N','수평 등가하중을 두 가새에 배분')
    ck('주 기둥 용접 직접전단',math.hypot(legP,horizontal/4)/(.707*c['weld_leg_mm']*4*d['leg'][0]),allow/math.sqrt(3),'MPa','둘레 필릿; 피로·상세 응력집중 별도')
    # Unanchored whole-frame transverse tipping screen; local chutes are tied
    # to the main frame and their anchors still require installation design.
    cg_z=(dead*cg[2]+(total-dead)*d['axis_z'])/total
    tip=(d['half']+c['main_foot_mm']/2)/(c['lateral_accel_g']*cg_z) if c['lateral_accel_g'] else None
    if tip is not None:ck('전체 횡전도 선별',1.5,tip,'안전율','관성하중, 주 프레임 발판 폭; 종방향·충돌·앵커는 별도')
    screw_mass=groups['Transport Auger'];shaftL=(3080. if index==3 else 2320.)
    radial=(screw_mass+blocked)*G*kd/2;axial=2*math.pi*c['screw_limiter_nm']/pitch
    M=(screw_mass+blocked)*G*kd*shaftL/8
    shaftstress=1.6*32*M/(math.pi*(2*d['shaft_radius'])**3)+axial/(math.pi*d['shaft_radius']**2)
    tau=1.3*16*c['screw_limiter_nm']*1000/(math.pi*(2*d['shaft_radius'])**3)
    ck('나선 축 복합응력',math.sqrt(shaftstress**2+3*tau**2),allow,'MPa','등분포 자중/정체 감자, 응력집중계수, 리미터 토크')
    ck('나선 베어링 방사 요구',radial,c['bearing_radial_allowable_n'],'N','구매 요구 정격; 공급사 수명/회전수 확인 필요')
    ck('나선 고정측 베어링 축 요구',axial,c['bearing_axial_allowable_n'],'N','리미터 토크의 이상 리드 추력, 부동측 축방향 자유 필요')
    screw_cases=[];screw_available=c['screw_motor_kw']*1000/(c['motor_base_rpm']*2*math.pi/60)*c['low_speed_torque_factor']
    for rpm in (c['screw_min_rpm'],c['screw_rpm'],c['screw_max_rpm']):
        om=rpm*2*math.pi/60;v=pitch*rpm/60*c['axial_efficiency'];inventory=c['target_kg_h']/3600*L/v
        run=c['screw_empty_nm']+c['potato_friction']*inventory*G*pitch/(2*math.pi*c['lead_efficiency'])
        start=(c['screw_empty_nm']+c['potato_friction']*blocked*G*pitch/(2*math.pi*c['lead_efficiency']))*c['breakaway_factor']
        start+=(augerJ+blocked*(d['screw_radius']/2000)**2)*om/c['start_seconds']
        design=start*c['drive_service_factor']
        screw_cases.append(dict(rpm=rpm,run_nm=run,start_nm=start,design_nm=design,shaft_kw=run*om/1000,
             motor_required_nm=design/(c['screw_ratio']*c['screw_gear_efficiency'])+c['screw_motor_inertia_kg_m2']*om*c['screw_ratio']/c['start_seconds'],motor_rpm=rpm*c['screw_ratio'],
             vfd_hz=rpm*c['screw_ratio']/c['motor_base_rpm']*60,
             feed_limit_kg_h=min(c['target_kg_h'],nominal_limit/(L/v)*3600/c['transport_reserve_factor'])))
    worst=max(x['design_nm'] for x in screw_cases)
    ck('나선 모터 기동 토크',max(x['motor_required_nm'] for x in screw_cases),screw_available,'N·m','정체·가속·서비스계수 / 감속비·효율, 저속 토크 감액')
    ck('나선 감속기 연속 토크',max(x['run_nm'] for x in screw_cases)*c['drive_service_factor'],c['screw_gear_continuous_nm'],'N·m','최저속에서 공급량 유지 가정')
    ck('나선 리미터 기동 여유',worst,c['screw_limiter_nm'],'N·m','설계 기동 토크가 리미터 설정 이하')
    ck('나선 감속기 순간 보호',c['screw_limiter_nm'],c['screw_gear_peak_nm'],'N·m','끼임 시 리미터로 제한')
    peel_cases=[];peel_available=c['peeling_motor_kw']*1000/(c['motor_base_rpm']*2*math.pi/60)*c['low_speed_torque_factor']
    for rpm in (c['peeling_min_rpm'],c['peeling_rpm'],c['peeling_max_rpm']):
        om=rpm*2*math.pi/60;process_kw=c['peeling_specific_kwh_t']*c['target_kg_h']/1000
        # Roller contact speed acts at r=62 mm, not at the 443 mm bed envelope.
        effective_radius=.062 if index==3 else R
        run=process_kw*1000/om+c['peeling_empty_nm'];start=run*c['breakaway_factor']+(peelingJ+blocked*effective_radius**2)*om/c['start_seconds']
        design=start*c['drive_service_factor'];share=1. if index==3 else .60
        peel_cases.append(dict(rpm=rpm,run_nm=run,start_nm=start,design_nm=design,shaft_kw=run*om/1000,
            per_motor_required_nm=design*share/(c['peeling_ratio']*c['peeling_gear_efficiency'])+c['peeling_motor_inertia_kg_m2']*om*c['peeling_ratio']/c['start_seconds'],
            motor_rpm=rpm*c['peeling_ratio'],vfd_hz=rpm*c['peeling_ratio']/c['motor_base_rpm']*60))
    ck('탈피 구동 모터 기동 토크',max(x['per_motor_required_nm'] for x in peel_cases),peel_available,'N·m','제품별 탈피 에너지 가정 + 공회전 + 회전체 관성; 4번 두 모터 중 한 대 60% 분담')
    if index==3:
        ck('롤러 리미터 기동 여유',max(x['design_nm'] for x in peel_cases),c['roller_limiter_nm'],'N·m','정체 시 기계식 토크 제한, 전체 구동 입력축 기준')
        roll_load=(groups['Peeling Rollers']+blocked)*G*kd/12
        sd=c['roller_shaft_d_mm'];sigma=32*roll_load/2*55/(math.pi*sd**3)
        tau=16*c['roller_limiter_nm']*1000/(math.pi*sd**3)
        ck('롤러 입력축 굽힘·비틀림',math.sqrt((1.6*sigma)**2+3*(1.3*tau)**2),allow,'MPa','구동 롤러축에 전체 리미터 토크, 베어링-코어 간 오버행 55 mm')
    ck('모터 최고 주파수',max(x['vfd_hz'] for x in screw_cases+peel_cases),60.,'Hz','기저속도 이하, 380 V/60 Hz 인버터 대응 명판 기준')
    suspension=None
    if index==4:
        rotating=groups['Peeling Drum and Knives'];sine=410/math.hypot(450,410)
        required=(rotating+blocked)*G*kd*.35/sine
        ck('드럼 상부 벨트 유효 지지 요구',required,c['suspension_belt_allowable_n'],'N','4개 상부 루프 중 한 개 35%, 수직성분 보수 근사; 하부 2개는 중량지지에 미산입')
        suspension=dict(rotating_drum_kg=rotating,required_per_loop_n=required,assumed_allowable_n=c['suspension_belt_allowable_n'])
    normal_kw=(screw_cases[1]['shaft_kw']/c['screw_gear_efficiency']+peel_cases[1]['shaft_kw']/c['peeling_gear_efficiency'])/(c['motor_efficiency']*c['vfd_efficiency'])+c['control_power_kw']+(1+c['peeling_drive_count'])*c['motor_fixed_loss_kw']
    installed=c['screw_motor_kw']+c['peeling_motor_kw']*c['peeling_drive_count']
    rated_kw=installed/(c['motor_efficiency']*c['vfd_efficiency'])+c['control_power_kw']
    hours=c['hours_per_day']*c['days_per_month'];kwh=(normal_kw*c['running_fraction']+c['control_power_kw']*(1-c['running_fraction']))*hours
    current=installed*1000/(math.sqrt(3)*c['supply_v']*c['motor_efficiency']*c['motor_pf'])
    bounds=[]
    for s in specs:
        q=dict(s)
        if q['kind']=='helix':q.update(kind='circle',depth=q['pitch']/4,inner=0)
        bounds.append(q)
    warnings=[x['name']+': 재선정 필요' for x in checks if x['utilization']>1]
    return dict(index=index,revision=REVISION,inputs=c,dimensions=d,checks=checks,warnings=warnings,
        status='예비 설계 / CATIA 실행·실제 탈피 성능·피로수명 확인 전',bom=bom,groups_mass_kg=dict(groups),
        bare_mass_kg=bare,dead_mass_kg=dead,dead_cg_mm=cg,bbox=core.bounding_box(bounds),
        gross_process_m3=gross,rotor_displacement_m3=displacement,free_process_m3=free,geometric_potato_kg=geometric_kg,
        working_potato_kg=working,normal_inventory_limit_kg=nominal_limit,blocked_potato_kg=blocked,
        operating_total_kg=dead+working+c['water_hold_up_kg']+c['waste_hold_up_kg'],blocked_total_kg=total,
        raw_kg_min=c['target_kg_h']/60,output_kg_h=c['target_kg_h']*(1-c['peeling_loss_fraction']),
        waste_kg_h=c['target_kg_h']*c['peeling_loss_fraction'],capacity_model_kg_h=capacity,
        axial_speed_m_min=speed*60,residence_seconds=residence,io_supports=io,
        total_vertical_design_n=wd,total_lateral_design_n=horizontal,leg_design_n=legP,allowable_mpa=allow,
        screw_mass_kg=screw_mass,screw_inertia_kg_m2=augerJ,peeling_inertia_kg_m2=peelingJ,
        bearing_radial_n=radial,bearing_axial_n=axial,screw_cases=screw_cases,peeling_cases=peel_cases,suspension=suspension,
        installed_motor_kw=installed,input_power_kw=normal_kw,nameplate_input_kw=rated_kw,estimated_current_a=current,
        month_kwh=kwh,month_cost_krw=kwh*c['energy_rate_krw_kwh']+c['extra_demand_charge_krw_month'],
        water_m3_month=c['water_m3_h']*hours*c['running_fraction'],
        fatigue_cycles=c['peeling_rpm']*60*hours*12*c['design_years'],transverse_tip_factor=tip,
        input_sha256=hashlib.sha256(json.dumps(dict(index=index,inputs=c,dimensions=d),sort_keys=True).encode()).hexdigest())


def station_geometry(index,overrides=None):
    c=configuration(index,overrides);specs,source_meta=make_specs(index,c);r=analyze(index,c,specs);d=DIM[index]
    meta=dict(source_meta,name=d['name'],description=d['label']+' with welded support frame and independently supported infeed/outfeed.',
        inlet=d['ports'][0]['a'],outlet=d['ports'][1]['b'],inlet_width_mm=d['ports'][0]['w0'],outlet_width_mm=d['ports'][1]['w1'],
        engineering_revision=REVISION,engineering_inputs=c,input_sha256=r['input_sha256'],
        engineering_warnings=r['warnings'],geometry_envelope_mm=r['bbox'],
        joint_design='Welded main/chute frame; service covers, bearings and purchased drives remain removable.',
        material_assignment='Specification metadata only; no CATIA material catalogue assignment.',
        modifications=['Feed cabinet exterior removed; internal guides and main side covers retained.' if index==3 else 'Original process drum retained.',
                       'Sealed SUS304 tube load paths; independent four-leg chute supports; mass/drive review.'])
    return specs,meta


def write_report(index,output_dir,overrides=None):
    from peeler_report import report_html
    r=analyze(index,overrides);folder=Path(output_dir);folder.mkdir(parents=True,exist_ok=True)
    stem=f'{index:02d}_{DIM[index]["code"]}_Design_Review'
    path=folder/(stem+'.html');path.write_text(report_html(r),encoding='utf-8')
    (folder/f'{index:02d}_{DIM[index]["code"]}_Calculations.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return path,r


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--stage',type=int,choices=(3,4),required=True)
    ap.add_argument('--config',type=Path);ap.add_argument('--output-dir',type=Path)
    args=ap.parse_args();directory=args.output_dir or Path(__file__).resolve().parent/'Overall_Review'/f'{args.stage:02d}_{DIM[args.stage]["code"]}_Design_Review'
    try:
        config=json.loads(args.config.read_text(encoding='utf-8-sig')) if args.config else None
        path,r=write_report(args.stage,directory,config)
    except (OSError,ValueError) as exc:ap.error(str(exc))
    print('SAVED '+str(path.resolve()),flush=True)
    for warning in r['warnings']:print('DESIGN REVIEW: '+warning,flush=True)


if __name__=='__main__':main()
