"""Station 05: Urschel CC-DL envelope / potato CC operating principle.
Public reference dimensions only; unpublished internals are custom design inputs.
Millimetres. Import has no CAD or file side effects. User executes/validates.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math
from pathlib import Path

REVISION = 'S05-CC-R17-EXTERNAL-GEARCASE-2026-11-06'
PRODUCT_NAME = '05_Urschel_CC_R15'
CORE_REFERENCE_MM = (1578.,947.,871.)
CORE_REFERENCE_MASS_KG = 318.
INLET = (-1528.,0.,1600.)
OUTLET = (419.,0.,500.)
ROOT = Path(__file__).resolve().parent
I=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))
AX=((0.,1.,0.),(0.,0.,1.),(1.,0.,0.))
AY=((1.,0.,0.),(0.,0.,-1.),(0.,1.,0.))
STEEL=(190,198,204); BLUE=(42,115,158); DARK=(58,66,73)
MOTOR=(47,92,158)  # Same motor/gearcase convention as the complete potato line.
DEFAULTS=dict(belt_width_mm=800.,slice_mm=1.5,blade_count=8,
    impeller_paddles=5,impeller_rpm=257.,impeller_radius_mm=240.,
    head_guide_radius_mm=245.,head_height_mm=160.,
    drive_diameter_mm=100.,roller_diameter_mm=50.,belt_thickness_mm=3.,
    product_height_mm=60.,max_product_height_mm=98.,target_kg_h=560.,
    potato_density_kg_m3=1100.,packing_fraction=.65,width_loading_fraction=.50,
    steel_density_kg_m3=7930.,yield_mpa=205.,E_mpa=193000.,
    safety_factor=2.,dynamic_factor=1.5,lateral_accel_g=.10,
    leg_load_share=.40,leg_wall_mm=4.,knife_motor_kw=7.5,
    core_machine_design_min_kg=500.,feed_machine_design_min_kg=200.,
    core_purchase_allowance_kg=150.,feed_purchase_allowance_kg=40.,
    transition_machine_design_min_kg=80.,transition_bed_height_mm=100.,
    weld_leg_mm=3.,section_property_factor=.90,
    motor_base_rpm=1750.,drive_efficiency=.90,motor_efficiency=.90,
    conveyor_motor_kw=.20,conveyor_ratio=300.,conveyor_efficiency=.65,
    conveyor_motor_efficiency=.75,conveyor_friction=.12,
    conveyor_extra_pull_n=100.,start_seconds=3.,service_factor=1.5,
    control_kw=.06,purchased_mass_kg=None,cutting_force_total_n=None,
    electric_rate_krw_kwh=None,measured_input_kw=None,
    manufacturing_labor_quote_krw=None)

def configuration(overrides=None):
    c=dict(DEFAULTS)
    if overrides:
        unknown=set(overrides)-set(c)
        if unknown:raise ValueError('Unknown CC inputs: '+', '.join(sorted(unknown)))
        c.update(overrides)
    for k,v in c.items():
        if v is not None and (isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or v<=0):
            raise ValueError(k+': expected positive finite number or null')
    for k in ('packing_fraction','width_loading_fraction','leg_load_share','drive_efficiency',
              'motor_efficiency','conveyor_efficiency','conveyor_motor_efficiency','section_property_factor'):
        if c[k]>1:raise ValueError(k+' must be <=1')
    fixed=dict(belt_width_mm=800.,slice_mm=1.5,blade_count=8,impeller_paddles=5,
               drive_diameter_mm=100.,roller_diameter_mm=50.,impeller_radius_mm=240.,
               head_guide_radius_mm=245.,head_height_mm=160.,knife_motor_kw=7.5)
    for k,v in fixed.items():
        if c[k]!=v:raise ValueError(f'CC-DL R16 geometry requires {k}={v}')
    if c['product_height_mm']>98:raise ValueError('CC-DL maximum input dimension: 98 mm')
    if not 3<=c['leg_wall_mm']<=6:raise ValueError('Leg wall: supported 3..6 mm')
    if c['weld_leg_mm']>3:raise ValueError('3 mm secondary tube wall limits nominal fillet leg to 3 mm')
    return c

def add(a,b):return tuple(x+y for x,y in zip(a,b))
def mul(a,k):return tuple(x*k for x in a)
def transform(p,o,axes):return tuple(o[i]+sum(p[j]*axes[j][i] for j in range(3)) for i in range(3))
def rectangle(w,h):return [(0.,0.),(w,0.),(w,h),(0.,h)]
def circle(r,n=64):return [(r*math.cos(i*2*math.pi/n),r*math.sin(i*2*math.pi/n)) for i in range(n)]
def channel(w,h,t):
    # Open C section: one boundary, one Pad, no nested contour or fake solid bar.
    return [(0,0),(w,0),(w,t),(t,t),(t,h-t),(w,h-t),(w,h),(0,h)]
def angle(w,h,t):return [(0,0),(w,0),(w,t),(t,t),(t,h),(0,h)]
def polygon_area(p):return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(p,p[1:]+p[:1])))/2

def belt_outline(centers,offset=0.,steps=24):
    """Convex external tangents and arcs, circles ordered counter-clockwise."""
    cs=[(x,z,r+offset) for x,z,r in centers];tang=[]
    for (x,z,r),(xx,zz,rr) in zip(cs,cs[1:]+cs[:1]):
        d=math.hypot(xx-x,zz-z)
        a=math.atan2(zz-z,xx-x)-math.acos((r-rr)/d)
        n=(math.cos(a),math.sin(a))
        tang.append(((x+r*n[0],z+r*n[1]),(xx+rr*n[0],zz+rr*n[1])))
    out=[]
    for j,(x,z,r) in enumerate(cs):
        start=tang[(j-1)%len(cs)][1];end=tang[j][0]
        a=math.atan2(start[1]-z,start[0]-x);b=math.atan2(end[1]-z,end[0]-x)
        while b<=a:b+=2*math.pi
        for k in range(steps+1):
            t=a+(b-a)*k/steps;out.append((x+r*math.cos(t),z+r*math.sin(t)))
    return out

class Model:
    def __init__(self,c):self.c=c;self.parts=[];self.interfaces=[];self.contacts=[];self.welds=[];self.load_group='core'
    def part(self,family,category,kind,origin,axes=I,material='SUS304',density=None,**kw):
        count=1+sum(p['family']==family for p in self.parts)
        p=dict(name=f'{family}.{count}',family=family,category=category,kind=kind,
               origin=tuple(origin),axes=axes,material=material,
               density_kg_m3=density or self.c['steel_density_kg_m3'],
               color=MOTOR if kw.get('part_type')=='Drive' else STEEL,
               support_group=self.load_group,**kw)
        self.parts.append(p);return p
    def plate(self,family,origin,w,h,t,axes=I,category='1_Frame',typ='Plate',holes=(),**kw):
        return self.part(family,category,'poly',origin,axes,points=rectangle(w,h),depth=t,
                         part_type=typ,holes=list(holes),**kw)
    def profile(self,family,start,points,length,axes=I):
        return self.part(family,'1_Frame','poly',start,axes,points=points,depth=length,
                         part_type='Profile',single_closed_profile=True,color_note='SUS304 open channel')

    def weld(self,family,length,location,process='TIG; continuous seal weld'):
        self.welds.append(dict(family=family,length_mm=length,
            leg_mm=self.c['weld_leg_mm'],location_mm=tuple(location),
            support_group=self.load_group,process=process,
            filler='ER308L; procedure and purchased material certificate to be specified'))
    def tube(self,family,start,w,h,wall,length,axes=I,join_ends=(0,1)):
        # One closed outer rectangle Pad, then one rectangular through Pocket.
        # Repeated lengths/sections reuse one CATPart master in the family Product.
        p=self.part(family,'1_Frame','tube',start,axes,
            points=rectangle(w,h),loops=[[(wall,wall),(w-wall,wall),
                (w-wall,h-wall),(wall,h-wall)]],depth=length,
            width_mm=w,height_mm=h,wall_mm=wall,part_type='Square_Tube',
            manufacturing='SUS304 rectangular hollow section; welded assembly')
        # Flush inset end caps close every tube cavity; no exposed open profiles.
        cap_t=min(3.,wall)
        for end,z in enumerate((0.,length-cap_t)):
            self.plate(family+'_End_Cap',transform((wall,wall,z),start,axes),
                w-2*wall,h-2*wall,cap_t,axes=axes)
            self.weld(family+'_Cap_Seal',2*(w+h-4*wall),transform((w/2,h/2,z),start,axes))
        for end in join_ends:
            self.weld(family+'_End_Joint',2*(w+h),transform((w/2,h/2,end*length),start,axes))
        return p

    def cylinder(self,family,start,r,length,axes=I,inner=0.,category='2_Internal',typ='Mechanism',**kw):
        return self.part(family,category,'circle',start,axes,radius=r,inner=inner,depth=length,part_type=typ,**kw)
    def bolt(self,origin,length=25.,axes=I,family='Bolt_M8'):
        # One manufactured fastener, explicit shaft/head geometry; thread cosmetic only.
        return self.part(family,'1_Frame','bolt',origin,axes,diameter=8.,length=length,
                         head_diameter=13.,head_height=5.3,part_type='Fastener',thread='M8, cosmetic')
    def joint(self,origin,axes=I,family='Corner_Bracket_50'):
        # 50x50x5 angle, 50 wide; two actual holes, one in each flange.
        p=self.part(family,'1_Frame','poly',origin,axes,points=angle(50,50,5),depth=50,
                    part_type='Bracket',drills=[dict(center=(25,5,25),normal=(0,1,0),radius=4.5,depth=5),
                                              dict(center=(5,25,25),normal=(1,0,0),radius=4.5,depth=5)])
        for loc,axs in [((25,5,25),((1,0,0),(0,0,-1),(0,1,0))),((5,25,25),AX)]:
            # Shaft points into the flange; the head remains outside its bearing face.
            axs=(axs[0],mul(axs[1],-1),mul(axs[2],-1))
            globaxes=tuple(tuple(sum(axs[j][k]*axes[k][i] for k in range(3)) for i in range(3)) for j in range(3))
            face=transform(loc,origin,axes)
            self.bolt(face,20,globaxes)
            self.cylinder('M8_Washer',add(face,mul(globaxes[2],9)),8,1.6,globaxes,inner=4.2,category='1_Frame',typ='Fastener')
            self.cylinder('M8_Nut',add(face,mul(globaxes[2],10.6)),6.5,6.5,globaxes,inner=4,category='1_Frame',typ='Fastener')
        return p
    def bearing(self,x,y,z,shaft_r=12.5,axis=AY,family='Conveyor_Bearing'):
        # Cartridge sits concentrically INSIDE a cylindrical housing; no stick supports.
        outer=26.;length=15.;start=(x,y,z)
        self.cylinder(family+'_Housing',start,36,24,axis,inner=outer,typ='Bearing')
        self.cylinder(family+'_Outer_Race',add(start,mul(axis[2],4.5)),26,15,axis,inner=22,typ='Bearing',material='Bearing stainless; supplier grade required')
        self.cylinder(family+'_Inner_Race',add(start,mul(axis[2],4.5)),18,15,axis,inner=shaft_r,typ='Bearing',material='Bearing stainless; supplier grade required')
        self.cylinder(family+'_Rolling_Element_Envelope',add(start,mul(axis[2],6)),22,12,axis,inner=18,typ='Bearing',material='Bearing assembly envelope; not a solid race',density=3900.)
        flange_start=add(start,mul(axis[2],-4 if y<0 else 24))
        self.cylinder(family+'_Retaining_Flange',flange_start,44,4,axis,inner=shaft_r+1,typ='Bearing')
        # A full-height seat bears on the conveyor side plate, not two stays.
        self.plate(family+'_Seat',(x-45,y,z-67),90,24,31,category='1_Frame',typ='Bracket')


def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def unit(a):return mul(a,1/math.sqrt(dot(a,a)))
def rotation(a):return ((math.cos(a),math.sin(a),0),(-math.sin(a),math.cos(a),0),(0,0,1))
def polar(r,a):return (r*math.cos(a),r*math.sin(a))
def annular_sector(ri,ro,start,end,n=24):
    angles=[start+(end-start)*i/n for i in range(n+1)]
    return [polar(ro,a) for a in angles]+[polar(ri,a) for a in reversed(angles)]

def panel(m,family,vertices,t=3.,category='1_Frame',typ='Plate'):
    o=vertices[0];u=unit(add(vertices[1],mul(o,-1)))
    n=unit(cross(u,add(vertices[2],mul(o,-1))));v=cross(n,u)
    pts=[(dot(add(p,mul(o,-1)),u),dot(add(p,mul(o,-1)),v)) for p in vertices]
    return m.part(family,category,'poly',o,(u,v,n),points=pts,depth=t,part_type=typ)

def cone(m,family,origin,r0,r1,height,t=3.,category='1_Frame',typ='Plate'):
    # Single meridian section revolved 360 degrees. Open at BOTH ends.
    radial=t*math.sqrt(1+((r1-r0)/height)**2)
    return m.part(family,category,'revolve',origin,section=[(r0,0),(r1,height),
        (r1-radial,height),(r0-radial,0)],part_type=typ,
        wall_thickness_mm=t,manufacturing='Spun/rolled SUS304; flanged detachable assembly')

def bolt_set(m,face,grip,axes=I,family='Joint_Bolt_M8'):
    # Datum at washer bearing face, head outside the joint.
    m.bolt(add(face,mul(axes[2],-1.6)),grip+14,axes,family)
    m.cylinder('M8_Washer',add(face,mul(axes[2],-1.6)),8,1.6,axes,inner=4.2,category='1_Frame',typ='Fastener')
    m.cylinder('M8_Washer',add(face,mul(axes[2],grip)),8,1.6,axes,inner=4.2,category='1_Frame',typ='Fastener')
    m.cylinder('M8_Nut',add(face,mul(axes[2],grip+1.6)),6.5,6.5,axes,inner=4,category='1_Frame',typ='Fastener')

def drill_world(p,entry,normal,depth,r=4.5):
    # Pocket cuts opposite its plane normal, consistently with CATIA.
    rel=add(entry,mul(p['origin'],-1))
    hole=dict(center=tuple(dot(rel,a) for a in p['axes']),
        normal=tuple(dot(normal,a) for a in p['axes']),radius=r,depth=depth)
    if hole not in p.setdefault('drills',[]):p['drills'].append(hole)

def bridge_joint(m,beam,column,face,width=90.,height=100.,family='Frame_Splice_Bracket'):
    # A separate flat splice across the butt joint; through holes in both mating webs.
    x,y,z=face;axs=((1,0,0),(0,0,1),(0,-1,0))
    holes=((20,25,4.5),(20,75,4.5),(width-20,25,4.5),(width-20,75,4.5))
    plate=m.plate(family,face,width,height,6,axes=axs,typ='Bracket',holes=holes)
    for xx,zz,r in holes:
        entry=(x+xx,y-6,z+zz);target=column if xx<width/2 else beam
        drill_world(target,entry,(0,-1,0),12,r)
        bolt_set(m,entry,10,AY)
    return plate


def stand(m,label,xs,ys,top):
    legs={};beams=[];wall=m.c['leg_wall_mm'];xa,xb=xs
    for x in xs:
        for y in ys:
            legs[x,y]=m.tube(label+'_Leg_SHS80',(x-40,y-40,100),80,80,wall,top-100,
                              join_ends=(0,))
            m.plate(label+'_Foot_Plate',(x-60,y-60,88),120,120,12)
            m.cylinder('Leveling_Pad',(x,y,0),55,15,category='1_Frame',typ='Foot')
            m.cylinder('Leveling_Stem',(x,y,15),12,73,category='1_Frame',typ='Foot')
    for y in ys:
        beams.append(m.tube(label+'_Longitudinal_SHS80',(xa+40,y-40,top-80),
                            80,80,wall,xb-xa-80,AX))
        # Lower welded tie: top 300, clear of the CC gravity discharge.
        m.tube(label+'_Lower_Tie_SHS50',(xa+40,y-25,250),50,50,3,xb-xa-80,AX)
        # Solid triangular gussets touch the column and beam underside.
        # Their stiffness is not credited in the conservative column calculation.
        knee_height=min(180.,top-80.-310.)  # Clear the top of the lower tie at Z=300.
        for x,sgn in ((xa+40,1),(xb-40,-1)):
            verts=[(x,y-3,top-80-knee_height),(x,y-3,top-80),(x+sgn*180,y-3,top-80)]
            panel(m,label+'_Welded_Knee_Gusset',verts,6,typ='Bracket')
            m.weld(label+'_Knee_Gusset',2*(knee_height+180),(x,y,top-80))
    for x in xs:
        m.tube(label+'_Cross_SHS80',(x-40,ys[0]+40,top),80,80,wall,ys[1]-ys[0]-80,AY)
        m.tube(label+'_Lower_Cross_SHS50',(x-25,ys[0]+40,300),50,50,3,ys[1]-ys[0]-80,AY)
    return legs,beams

def transition_support(m):
    """Welded load path: chute -> sloping cradle -> posts -> arms -> feeder legs."""
    slope=197./666.;u=unit((1,0,-slope));n=unit((slope,0,1));Y=(0,1,0)
    floor=lambda x:1597.-(x+247.)*slope
    # Arms end at X=140, below the chute and outside the hopper.
    for side in (-1,1):
        y=side*480.
        m.tube('Transition_Cantilever_SHS80',(-360,y-40,1320),80,80,4,500,AX,
               join_ends=(0,))
        # Both vertical and horizontal gusset edges meet the steel surfaces.
        gy=y-40 if side>0 else y+34
        panel(m,'Transition_Welded_Knee_Gusset',
              [(-360,gy,1000),(-360,gy,1320),(140,gy,1320)],6,typ='Bracket')
        m.weld('Transition_Knee_Gusset',2*(320+500),(-360,y,1320))
    for x in (-200.,100.):
        m.tube('Transition_Crossbeam_SHS80',(x-40,-440,1400),80,80,4,880,AY)
    # Sloped 50 mm cradle rails stop 119 mm before the food outlet, above the hopper.
    # Their upper faces coincide with the UNDERSIDE of Feed_Transition_Floor.
    for y in (-180.,180.):
        start=add((-220,y-25,floor(-220)),mul(n,-50))
        m.tube('Transition_Sloped_Rail_SHS50',start,50,50,3,520/u[0],(Y,n,u),join_ends=())
        for x in (-200.,100.):
            saddle_low=floor(x+25)-50/u[0]-6
            m.tube('Transition_Riser_SHS50',(x-25,y-25,1400),50,50,3,saddle_low-1400)
            # Wedge top fills the full gap between vertical post and sloping rail.
            panel(m,'Transition_Fitted_Saddle',
                [(x-25,y+25,saddle_low),(x+25,y+25,saddle_low),
                 (x+25,y+25,floor(x+25)-50/u[0]),
                 (x-25,y+25,floor(x-25)-50/u[0])],50,typ='Bracket')
            m.weld('Transition_Saddle_to_Rail',200,(x,y,saddle_low))
    for x in (-190.,-40.,110.,275.):
        # Three butt-joined segments: no crossmember overlaps a longitudinal tube.
        half=400.-(x+25*u[0]+247.)*250./666.
        for a,b in ((-half,-205.),(-155.,155.),(205.,half)):
            if b-a<25:continue  # Tapered end needs only the central crosspiece.
            start=add((x,a,floor(x)),mul(u,-25))
            m.tube('Transition_Cradle_Cross_SHS50',start,50,50,3,b-a,
                   (u,mul(n,-1),Y))
        m.weld('Transition_Floor_to_Cradle',2*half,(x,0,floor(x)),
               'TIG; continuous food-side seal, underside structural seam')

def geometry(overrides=None):
    c=configuration(overrides);m=Model(c)
    # CC-DL original casing: 1578 x 947 x 871; outlet elevated 500 above floor.
    # The separate stand/feed assembly increases the TOTAL installation envelope.
    stand(m,'CC_Stand',(119.,1478.),(-460.,460.),490.)
    # First chamber rail is the stand end crossrail at X=119.
    for x in (719.,870.):
        m.tube('CC_Additional_Crossrail_SHS80',(x-40,-420,490),80,80,4,840,AY)
    for x in (119.,719.):
        for y in (-315.,315.):
            m.plate('Chamber_Post_Base',(x-45,y-45,490),90,90,10)
            m.tube('Chamber_Post_SHS50',(x-25,y-25,500),50,50,3,275)
            m.plate('Chamber_Post_Top',(x-45,y-45,775),90,90,8)
            m.weld('Chamber_Base_to_Crossrail',320,(x,y,490))
    # Open ring seat around discharge; no plate closes the food outlet.
    m.cylinder('Chamber_Support_Ring',(419,0,783),445,10,inner=406.5,category='1_Frame',typ='Plate')
    discharge=cone(m,'Lower_Discharge_Cone',(419,0,508),246,406.5,272,3,category='2_Internal',typ='Chute')
    # Stationary sealed drive tube through a real Ø70 opening on the +X side.
    # Axis Z700 stays below the support ring/cutting-zone plate (Z780+).
    drill_world(discharge,(850,0,700),(1,0,0),170,35)
    m.cylinder('Discharge_Outlet_Flange_D492',(419,0,500),246,8,inner=242.5,category='2_Internal',typ='Chute')
    m.cylinder('Cutting_Zone_D813',(419,0,780),406.5,150,inner=403.5,category='1_Frame',typ='Plate')
    m.cylinder('Casing_Clamp_Flange_D838',(419,0,923),419,7,inner=400,category='1_Frame',typ='Plate')
    cone(m,'Swing_Away_Cutting_Cover',(419,0,930),406.5,365,220,3)
    m.cylinder('Cover_Top_Annulus',(419,0,1150),365,3,inner=115,category='1_Frame',typ='Plate')
    cone(m,'Infeed_Hopper_D465',(419,0,1153),115,232.5,218,3,category='2_Internal',typ='Hopper')
    # Hinge, swing arm and removable latches, all connected by mounting plates.
    m.cylinder('Hopper_Hinge_Post',(900,0,930),30,290,inner=15,category='1_Frame',typ='Bracket')
    m.cylinder('Hopper_Hinge_Pin',(900,0,920),15,310,category='1_Frame',typ='Fastener')
    m.plate('Hopper_Hinge_Base',(855,-55,917),90,110,13,typ='Bracket')
    m.plate('Hopper_Swing_Arm',(760,-25,1190),140,50,12,typ='Bracket')
    m.plate('Cover_Swing_Arm_Riser',(754,-25,1153),30,50,37,typ='Bracket')
    for deg in (45,135,225,315):
        a=math.radians(deg);axs=rotation(a);o=transform((410,-15,0),(419,0,916),axs)
        m.plate('Cover_Draw_Latch_Mount',o,16,30,24,axes=axs,typ='Bracket')
        m.cylinder('Cover_Latch_Pin',transform((418,0,0),(419,0,930),axs),5,30,typ='Fastener')
    # Fixed 8-station head. Datum guide radius 245, knife edge 243.5 -> 1.5 mm.
    for z in (850.,1035.):
        m.cylinder('Stationary_Head_Ring',(419,0,z),280,15,inner=242,typ='Knife')
    for j in range(8):
        a=j*math.tau/8;axs=rotation(a);r=c['head_guide_radius_mm'];edge=r-c['slice_mm']
        m.part('Adjustable_Cutting_Shoe','2_Internal','poly',(419,0,875),axs,
            points=annular_sector(r,r+8,math.radians(4),math.radians(43)),depth=160,part_type='Knife')
        # Wedge-shaped cross section supplies a real vertical cutting edge.
        blade=[(edge,0),(267,-7),(267,0),(edge+.5,.5)]
        m.part('Stationary_Flat_Knife','2_Internal','poly',(419,0,875),axs,
            points=blade,depth=160,part_type='Knife',
            material='Hardened food knife stainless; OEM insert specification required',density=7700.)
        m.plate('Knife_Clamp_Block',transform((263,-12,0),(419,0,875),axs),15,8,160,axes=axs,category='2_Internal',typ='Knife')
        for z in (864.,1027.):
            pos=transform((266,16,0),(419,0,z),axs)
            m.cylinder('Shoe_Adjustment_Screw_M8',pos,4,20,typ='Adjustment')
            m.plate('Shoe_Adjuster_Block',transform((257,7,0),(419,0,z-5),axs),18,18,5,axes=axs,category='2_Internal',typ='Adjustment')
    for j in range(8):
        axs=rotation(j*math.tau/8)
        m.part('Fixed_Head_Radial_Bracket','2_Internal','poly',(419,0,840),axs,
                points=annular_sector(278,403.5,-.035,.035),depth=10,part_type='Bracket',
                holes=((280,0,4.5),(390,0,4.5)))
    # Five paddles rotate about Z; fixed knives never rotate with the impeller.
    m.cylinder('Impeller_Base_D480',(419,0,865),240,10,inner=30)
    m.cylinder('Impeller_Hub',(419,0,838),60,27,inner=30)
    for j in range(5):
        a=j*math.tau/5;axs=rotation(a)
        m.part('Impeller_Paddle','2_Internal','poly',(419,0,875),axs,
                points=[(60,-3),(236,-25),(236,-19),(60,3)],depth=155,part_type='Mechanism')
        m.plate('Paddle_Bolted_Root',transform((65,-16,0),(419,0,855),axs),65,32,10,axes=axs,
                category='2_Internal',typ='Bracket',holes=((15,8,4.5),(50,24,4.5)))
    m.cylinder('Impeller_Shaft_D60',(419,0,630),30,235)
    # Two rolling bearings are inside one machined cylindrical cartridge.
    housing=m.cylinder('Impeller_Bearing_Housing',(419,0,640),70,190,inner=45,typ='Bearing')
    drill_world(housing,(549,0,700),(1,0,0),110,22)
    for z in (665.,780.):
        m.cylinder('Impeller_Bearing_Inner_Race',(419,0,z),36,25,inner=30,typ='Bearing',material='Purchased stainless bearing race',density=7700.)
        m.cylinder('Impeller_Bearing_Outer_Race',(419,0,z),45,25,inner=41,typ='Bearing',material='Purchased stainless bearing race',density=7700.)
        m.cylinder('Impeller_Bearing_Rolling_Envelope',(419,0,z+2),41,21,inner=36,typ='Bearing',material='Purchased bearing rolling envelope',density=3900.)
    for z in (632.,830.):
        m.cylinder('Impeller_Seal_Retainer',(419,0,z),80,8,inner=31,typ='Bearing')
    # Separate angular drive support and closed hollow gearbox. Internals supplier-defined.
    m.plate('Drive_Frame_Deck',(850,-310,490),668,620,10)
    for x in (870.,1470.):
        for y in (-290.,290.):
            m.tube('Drive_Frame_Post_SHS50',(x-25,y-25,500),50,50,3,417)
    m.plate('Drive_Upper_Deck',(850,-310,917),668,620,8)
    for y in (-240.,200.):
        m.tube('Motor_Seat_Rail_SHS40',(1040,y,500),40,40,4,450,AX,join_ends=())
        m.weld('Motor_Rail_to_Deck',900,(1040,y,500))
    m.plate('Motor_Mount_Plate',(1040,-240,540),450,480,12,
            holes=((60,100,6.5),(340,100,6.5),(60,380,6.5),(340,380,6.5)))
    m.cylinder('Main_Motor_7p5kW_Reference',(1075,0,700),135,395,AX,
            category='3_External',typ='Drive',material='Purchased IP66 stainless motor reference; dimensions pending',density=1600.)
    for x in (1100.,1380.):
        m.plate('Motor_Integral_Foot_Reference',(x,-190,552),65,380,13,category='3_External',typ='Drive',
                material='Purchased motor mounting foot reference',density=7930.)
    m.cylinder('Main_Motor_Fan_Cover',(1470,0,700),137,108,AX,category='3_External',typ='Drive',
            material='Purchased stainless motor cover reference',density=600.)
    m.cylinder('Main_Motor_Coupling',(1005,0,700),45,70,AX,inner=20)
    # The reducer stays OUTSIDE the Ø890 support ring: X885 - (419+445) = 21 mm.
    m.part('External_Reduction_Gearcase','3_External','poly',(885,-100,600),AX,
           points=rectangle(200,200),loops=[[(8,8),(192,8),(192,192),(8,192)]],
           depth=120,part_type='Drive',material='Purchased stainless reduction gearcase reference',density=7930.)
    m.cylinder('Gearbox_Input_Shaft',(945,0,700),20,80,AX)
    m.cylinder('Enclosed_Horizontal_Drive_Shaft',(449,0,700),20,496,AX)
    m.cylinder('Sealed_Drive_Tube',(489,0,700),35,396,AX,inner=32,
               category='2_Internal',typ='Drive',material='SUS304 sealed stationary drive tube')
    bevel=m.cylinder('Central_Bevel_Housing',(419,0,610),95,180,inner=70,
                     category='2_Internal',typ='Drive',material='Sealed bevel housing reference; internal gears supplier-defined')
    drill_world(bevel,(549,0,700),(1,0,0),120,35)
    m.plate('Gearbox_Mount_Shelf',(885,-135,560),135,270,40,typ='Bracket')
    for x in (910.,990.):
        for y in (-110.,110.):
            m.tube('Gearbox_Shelf_Post_SHS50',(x-25,y-25,500),50,50,3,60)
    m.weld('Drive_Tube_to_Discharge_Seal',math.pi*70*1.2,(785,0,700),
           'Continuous hygienic seal around fitted cone opening; weld length estimated')
    # The 800 mm feeder is a SEPARATE conveyor; CC cutting diameter is not scaled to belt width.
    m.load_group='feeder'
    stand(m,'Feed_Stand',(-1450.,-400.),(-480.,480.),1450.)
    w=c['belt_width_mm'];t=c['belt_thickness_mm']
    centers=[(-1500.,-1572.,25.),(-300.,-1547.,50.)]
    b=m.part('Feed_Endless_Belt_800','2_Internal','belt',(0,-400,0),AY,centers=centers,
             belt_thickness=t,depth=w,part_type='Belt',material='Food-contact endless PU belt',density=1200.)
    b['color']=BLUE
    for y in (-430.,436.):
        m.plate('Feed_Side_Plate',(-1540,y,1460),1300,185,6,
                axes=((1,0,0),(0,0,1),(0,-1,0)),category='2_Internal',
                holes=((40,112,13.5),(1240,87,13.5)))
        for x in (-1450.,-400.):
            m.plate('Feed_Fitted_Riser',(x-25,min(y,-430) if y<0 else 424,1450),50,12,10,typ='Bracket')
            m.weld('Feed_Riser_to_Frame',124,(x,y,1450))
            m.weld('Feed_Side_to_Riser',100,(x,y,1460))
    for x,z,r in ((-1500.,1572.,25.),(-300.,1547.,50.)):
        m.cylinder('Feed_Drive_D100' if r==50 else 'Feed_Tail_D50',(x,-410,z),r,820,AY,inner=12.5)
        m.cylinder('Feed_End_Shaft_D25',(x,-470,z),12.5,970,AY)
        for y in (-460.,436.):m.bearing(x,y,z)
    for x in (-1250.,-1000.,-750.,-500.):
        m.cylinder('Feed_Carry_Roller_D50',(x,-410,1572),25,820,AY,inner=10)
        m.cylinder('Feed_Carry_Shaft_D20',(x,-470,1572),10,940,AY)
        for y in (-460.,436.):m.bearing(x,y,1572,shaft_r=10,family='Feed_Carry_Bearing')
    m.cylinder('Feed_Motor_Coupling',(-300,500,1547),23,45,AY,inner=12.5)
    m.plate('Feed_Gearmotor_0p20kW_Reference',(-380,545,1480),160,160,140,
            category='3_External',typ='Drive',material='Purchased stainless geared motor reference; ratio 300',density=1800.)
    m.plate('Feed_Motor_Mount',(-400,430,1468),200,275,12,typ='Bracket')
    for x in (-390.,-290.):
        m.plate('Feed_Motor_Fitted_Spacer',(x,430,1450),50,50,18,typ='Bracket')
        m.weld('Feed_Motor_Spacer',200,(x,430,1450))
    # The motor shelf bears on a welded outrigger tied into the end crossrail.
    m.tube('Feed_Motor_Outrigger_RHS50',(-360,440,1400),50,50,3,120,AX,join_ends=(0,))
    for y in (-404.,407.):
        m.plate('Feed_Product_Guide',(-1528,y,1600),1280,100,3,
                axes=((1,0,0),(0,0,1),(0,-1,0)),category='2_Internal')
    m.load_group='transition'
    # Gravity funnel from wide belt to 465 mm hopper mouth, with no false narrow belt.
    panel(m,'Feed_Transition_Floor',[(-247,-400,1597),(419,-150,1400),(419,150,1400),(-247,400,1597)],3,'2_Internal','Chute')
    for side in (-1,1):
        panel(m,'Feed_Transition_Side',[(-247,side*400,1597),(419,side*150,1400),
              (419,side*150,1500),(-247,side*400,1697)],3,'2_Internal','Chute')
    transition_support(m)
    m.load_group='core'
    # External electrical cabinet matches the right-side placement in CC-DL drawing.
    m.plate('Electrical_Cabinet_533', (930,328,731),533,200,275,
            category='3_External',typ='Control',material='Purchased SUS304 IP66 electrical cabinet reference',density=500.)
    m.tube('Cabinet_Support_Rail_SHS50',(895,265,731),50,50,3,550,AX)
    for x in (950.,1390.):
        m.plate('Cabinet_Fitted_Spacer',(x,315,731),50,13,80,typ='Bracket')
        m.weld('Cabinet_Spacer_to_Rail',160,(x,315,731))
    m.plate('HMI_Panel',(1060,528,840),210,5,120,category='3_External',typ='Control',
            material='Purchased HMI',density=1800.)
    m.cylinder('Emergency_Stop',(1330,528,900),20,30,AY,category='3_External',typ='Control',
               material='Purchased emergency stop',density=1800.)
    m.plate('Hopper_Interlock',(870,25,1180),40,25,60,category='3_External',typ='Control',
            material='Purchased guard interlock',density=1800.)
    m.interfaces=[dict(name='Feed',point_mm=INLET,direction=(1,0,0),width_mm=800),
                  dict(name='CC_Gravity_Discharge',point_mm=OUTLET,direction=(0,0,-1),diameter_mm=492)]
    masters={}
    for p in m.parts:
        key=geometry_key(p)
        if key not in masters:masters[key]=f'S05CC_P{len(masters)+1:03d}'
        p['master']=masters[key]
    return m

def geometry_key(p):
    ignore={'name','origin','axes','master','category','family','support_group'}
    return hashlib.sha256(json.dumps({k:v for k,v in p.items() if k not in ignore},sort_keys=True).encode()).hexdigest()

def contours(p):
    if p['kind'] in ('poly','tube'):return p['points'],p.get('loops',[])
    if p['kind']=='revolve':return circle(max(r for r,z in p['section'])),[]
    if p['kind']=='circle':return circle(p['radius']),([circle(p['inner'])] if p.get('inner') else [])
    if p['kind']=='belt':return belt_outline(p['centers'],p['belt_thickness']),[belt_outline(p['centers'])]
    if p['kind']=='bolt':return circle(p['diameter']/2),[]
    raise ValueError(p['kind'])

def part_volume(p):
    if p['kind']=='revolve':
        q=p['section'];edges=list(zip(q,q[1:]+q[:1]))
        return abs(math.pi/3*sum((a[0]+b[0])*(a[0]*b[1]-b[0]*a[1]) for a,b in edges))
    if p['kind']=='circle':return math.pi*(p['radius']**2-p.get('inner',0)**2)*p['depth']
    if p['kind']=='bolt':return math.pi*((p['diameter']/2)**2*p['length']+(p['head_diameter']/2)**2*p['head_height'])
    a,holes=contours(p);vol=(polygon_area(a)-sum(polygon_area(h) for h in holes))*p['depth']
    vol-=sum(math.pi*r*r*p['depth'] for _,_,r in p.get('holes',[]))
    vol-=sum(math.pi*d['radius']**2*d['depth'] for d in p.get('drills',[]))
    return vol

def bounds(m):
    vertices=[]
    for p in m.parts:
        out,_=contours(p);dep=p.get('depth',p.get('length',0))
        for xy in out:
            for z in ((min(z for r,z in p['section']),max(z for r,z in p['section'])) if p['kind']=='revolve' else (0,dep)):
                vertices.append(transform((*xy,z),p['origin'],p['axes']))
        if p['kind']=='bolt':
            for xy in circle(p['head_diameter']/2):
                vertices.append(transform((*xy,-p['head_height']),p['origin'],p['axes']))
    lo=[min(p[i] for p in vertices) for i in range(3)];hi=[max(p[i] for p in vertices) for i in range(3)]
    return dict(min_mm=lo,max_mm=hi,size_mm=[b-a for a,b in zip(lo,hi)])

def write_geometry(folder=None,overrides=None):
    folder=Path(folder or ROOT/'Overall_Review'/'05_CC_Design_Review');folder.mkdir(parents=True,exist_ok=True);m=geometry(overrides)
    payload=dict(revision=REVISION,configuration=m.c,parts=m.parts,bounds=bounds(m),
                 evidence='CC-DL published envelope and CC potato mechanism; internal dimensions custom, not OEM fabrication drawings',
                 inlet=INLET,outlet=OUTLET,interfaces=m.interfaces,weld_schedule=m.welds,
                 drawing_reference_mm=CORE_REFERENCE_MM,
                 master_count=len({p['master'] for p in m.parts}),component_count=len(m.parts))
    (folder/'05_Geometry.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'05_Config.json').write_text(json.dumps(m.c,ensure_ascii=False,indent=2),encoding='utf-8')
    return m,payload

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output-dir',type=Path,default=ROOT/'Overall_Review'/'05_CC_Design_Review');ap.add_argument('--config',type=Path)
    a=ap.parse_args();m,p=write_geometry(a.output_dir,json.loads(a.config.read_text()) if a.config else None)
    print(REVISION,len(m.parts),'instances /',p['master_count'],'masters',p['bounds'])
