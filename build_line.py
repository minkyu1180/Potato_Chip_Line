"""CATIA potato line R13: engineered welded 01-11 with per-machine reviews.

py build_line.py --stage 2                     # rebuilt screw uses native Rib
py build_line.py --stages 3 4 5                 # save each before the next
py build_line.py --all                         # all eleven individual machines
py build_line.py --assemble --zip              # whole line and dependencies
py build_line.py --stage 11 --seasoning-angle 40
py build_line.py --stages 5 6 7 8 9 10 11 --report-only  # no CATIA needed
py build_line.py --stages 5 6 7 8 9 10 11 --rebuild      # save each before next
py build_line.py --stage 9 --finish-config finishing_config.json
py build_line.py --stage 2 --so-config station2_config.json
py build_line.py --clean --dry-run            # list generated outputs; change nothing
py build_line.py --clean                      # delete generated models/reports only
py build_line.py --clean reports              # reports only; keep native models
No arguments: station 1 report only, preserving the existing entry point.
Keep station1_design.py, station2_design.py, peeler_design.py, peeler_report.py
and slicer_design.py, build_catia.py, slicer_review.py, finishing_design.py,
clean_outputs.py beside this script.
--rebuild creates a fresh numbered folder; existing/partial CAD stays intact.

Stations 1/2 retain the welded SUS304 geometry, calculations, functional Product
groups and material specification parameters. Screw flights use an analytical
helix + one fully constrained Rib profile, with normal-thickness compensation.
Stations 3/4 add welded load paths and engineering reviews.
Stations 6-11 retain R13; station 5 is replaced by the R16 welded-frame CC centrifugal slicer.
Station 5 uses a CC-DL casing, fixed 1.5 mm knives and a separate 800 mm feeder.
Calculations are preliminary and expose assumptions and pending purchase data.
The merged assembly aligns actual ports along +X for the redesigned station 2.
Python integration checks only; CATIA execution is left to the user.
All lengths mm. Windows, CATIA V5 and pywin32 are required for native modeling.
"""
from __future__ import annotations
import argparse
import re
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback
import zipfile

BASE = Path(__file__).resolve().parent
VBK_CONFIG = {}
SO_CONFIG = {}
CRP_CONFIG = {}
MS_CONFIG = {}
FINISH_CONFIGS = {}
STEEL = (185, 192, 200)
FRAME = (79, 101, 119)
BELT = (46, 115, 151)
RUBBER = (55, 62, 69)
ROLLER = (212, 216, 219)
MOTOR = (47, 92, 158)
GUARD = (234, 155, 48)
ABRASIVE = (116, 107, 96)
SO_MOTOR = (235, 104, 35)
MS_BLUE = (35, 73, 179)
CAT_CST_DISTANCE = 1
CAT_CST_ON = 2
CAT_CST_RADIUS = 14
CAT_CST_DRIVING = 0
REVISION = 13
I = ((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))
AX = ((0.,1.,0.),(0.,0.,1.),(1.,0.,0.))
AY = ((1.,0.,0.),(0.,0.,-1.),(0.,1.,0.))

def vec(a,b): return tuple(b[i]-a[i] for i in range(3))
def norm(v): return math.sqrt(sum(q*q for q in v))
def unit(v): return tuple(q/norm(v) for q in v)
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def plus(a,b): return tuple(a[i]+b[i] for i in range(3))
def scale(v,k): return tuple(q*k for q in v)
def rect(w,h): return ((-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2))

def poly(name, points, depth, origin, axes=I, color=STEEL, holes=(), loops=()):
    return dict(name=name,kind='poly',points=points,loops=loops,depth=depth,
                origin=origin,axes=axes,color=color,holes=holes)

def box(name, corner, size, color=STEEL, holes=()):
    x,y,z=corner; w,d,h=size
    return poly(name,rect(w,d),h,(x+w/2,y+d/2,z),color=color,holes=holes)

def tube(name, start, end, w=60, h=60, wall=4, color=FRAME):
    z=unit(vec(start,end)); ref=(0.,0.,1.) if abs(z[2])<0.9 else (0.,1.,0.)
    x=unit(cross(ref,z)); y=cross(z,x)
    spec=poly(name,rect(w,h),norm(vec(start,end)),start,(x,y,z),color)
    spec.update(part_type='Profile',profile_section_mm=(w,h),profile_ends=(start,end))
    return spec

def cylinder(name, start, end, radius, color=ROLLER, inner=0):
    z=unit(vec(start,end)); ref=(0.,0.,1.) if abs(z[2])<0.9 else (0.,1.,0.)
    x=unit(cross(ref,z)); y=cross(z,x)
    return dict(name=name,kind='circle',radius=radius,inner=inner,
                depth=norm(vec(start,end)),origin=start,axes=(x,y,z),color=color,holes=())

def plate_between(name, start, end, width, thickness, color=STEEL):
    """Plate runs in the XZ plane; width is global Y, thickness along its normal."""
    x=unit(vec(start,end)); y=(0.,1.,0.); z=unit(cross(x,y))
    center=scale(plus(start,end),0.5)
    return poly(name,rect(norm(vec(start,end)),width),thickness,
                plus(center,scale(z,-thickness)),(x,y,z),color)

def chute(specs,name,start,end,width=600,wall_h=180,t=5):
    if abs(start[1]-end[1]) > 1e-8:
        raise ValueError('chute requires a constant Y; rotate its specs for a Y-directed chute')
    specs.append(plate_between(name+'_Floor',start,end,width,t))
    x0,y0,z0=start; x1,_,z1=end
    for side in (-1,1):
        # Local coordinates map (u,v,n) -> (X,-Z,Y).
        points=((x0,-z0),(x1,-z1),(x1,-z1-wall_h),(x0,-z0-wall_h))
        specs.append(poly(name+('_Left' if side<0 else '_Right'),points,t,
                          (0,y0+side*(width/2)-(t if side<0 else 0),0),AY))

def roller(specs,name,x,z,width=600,r=40,y=0):
    specs.append(cylinder(name+'_Drum',(x,y-width/2,z),(x,y+width/2,z),r,ROLLER))
    specs.append(cylinder(name+'_Axle',(x,y-width/2-40,z),(x,y+width/2+40,z),12,FRAME))
    for side in (-1,1):
        a=(x,y+side*(width/2+8),z);b=(x,y+side*(width/2+38),z)
        bearing_housing(specs,name+f'_Bearing_{side}',a,b,12,28)
        specs.append(tagged(box(name+f'_Bearing_Base_{side}',(x-32,y+side*(width/2+24)-18,z-48),(64,36,20)),
                            'Bracket','Roller_Bearing_Bases','Frame'))


def frame(specs,length,width,top,member=60):
    for ix,x in enumerate((100,length-100)):
        for iy,y in enumerate((-width/2,width/2)):
            specs.append(tube(f'Frame_Leg_{ix}_{iy}',(x,y,35),(x,y,top),member,member))
            specs.append(box(f'Foot_{ix}_{iy}',(x-60,y-60,15),(120,120,15),FRAME,
                              holes=((-40,-40,6),(40,-40,6),(40,40,6),(-40,40,6))))
            specs.append(cylinder(f'Level_Screw_{ix}_{iy}',(x,y,0),(x,y,40),16,RUBBER))
    for y in (-width/2,width/2):
        for z in (260,top-member/2):
            specs.append(tube(f'Frame_Long_{y}_{z}',(100,y,z),(length-100,y,z),member,member))
    for x in (100,length-100):
        specs.append(tube(f'Frame_Cross_{x}',(x,-width/2,top-member/2),(x,width/2,top-member/2),member,member))

def drive(specs,name,x,y,z):
    specs.append(box(name+'_Mount',(x-120,y-100,z-100),(240,330,15),FRAME))
    specs.append(box(name+'_Gearbox',(x-75,y-70,z-85),(150,140,170),MOTOR))
    specs.append(cylinder(name+'_Motor',(x,y+70,z),(x,y+270,z),65,MOTOR))
    specs.append(cylinder(name+'_FanCover',(x,y+270,z),(x,y+300,z),70,RUBBER))
    for i in range(5):
        specs.append(cylinder(name+f'_CoolingRing_{i}',(x,y+90+32*i,z),(x,y+96+32*i,z),70,MOTOR))
    specs.append(box(name+'_TerminalBox',(x-35,y+135,z+62),(70,75,35),MOTOR))

def belt(specs,name,start,end,width=600,cleats=False):
    """Visible belt with end drums; cleats follow an inclined belt surface."""
    specs.append(plate_between(name+'_UpperRun',start,end,width,8,BELT))
    lower0=plus(start,(0,0,-105));lower1=plus(end,(0,0,-105))
    specs.append(plate_between(name+'_ReturnRun',lower0,lower1,width,7,RUBBER))
    for j,p in enumerate((start,end)):
        roller(specs,name+f'_EndDrum_{j}',p[0],p[2]-52,width,52,p[1])
    axis=unit(vec(start,end)); n=unit(cross(axis,(0,1,0))); L=norm(vec(start,end))
    for side in (-1,1):
        a=plus(start,(0,side*(width/2+28),-85));b=plus(end,(0,side*(width/2+28),-85))
        specs.append(tube(name+f'_Stringer_{side}',a,b,45,65,4))
    if cleats:
        for i in range(1,int(L/160)):
            p=plus(start,scale(axis,i*160))
            specs.append(poly(name+f'_Cleat_{i:02d}',rect(16,width-20),45,p,(axis,(0,1,0),n),BELT))



def bind_point(part,sketch,point,x,y,label):
    """Fix both point DOFs numerically, never with a Fix or a sketch colour.

    Nonzero coordinates are normal distances to the absolute axis lines. Their
    initial side is defined by CreatePoint(x,y). A zero coordinate is coincidence
    with that axis, avoiding a degenerate zero-distance constraint.
    """
    axis=sketch.AbsoluteAxis
    reference=part.CreateReferenceFromObject(point)
    for coord,line_name,value in (('X','VDirection',x),('Y','HDirection',y)):
        axis_ref=part.CreateReferenceFromObject(axis.GetItem(line_name))
        if abs(value)<1e-8:
            c=sketch.Constraints.AddBiEltCst(CAT_CST_ON,reference,axis_ref)
        else:
            c=sketch.Constraints.AddBiEltCst(CAT_CST_DISTANCE,reference,axis_ref)
            c.Mode=CAT_CST_DRIVING
            c.Dimension.Value=abs(float(value))
        c.Name=f'{label}_{coord}'

def finish_sketch(part,sketch):
    sketch.CloseEdition()
    part.Update()
    # Check only when the user actually builds the model. This does not claim to
    # measure DOFs: those are eliminated by the construction in the two builders.
    for i in range(1,sketch.Constraints.Count+1):
        constraint=sketch.Constraints.Item(i)
        if int(constraint.Status)!=0:
            raise RuntimeError(f'{sketch.Name}: unresolved constraint {constraint.Name} '
                               f'(CATIA status {constraint.Status})')

def polygon_sketch(part,body,points,loops=(),name='Fully_Constrained_Profile',support=None,axis_data=None,closing_points=None):
    part.InWorkObject=body
    sk=body.Sketches.Add(part.OriginElements.PlaneXY if support is None else support);sk.Name=name
    if axis_data is not None:sk.SetAbsoluteAxisData(tuple(axis_data))
    f=sk.OpenEdition()
    for k,coords in enumerate((points,*loops)):
        coords=tuple(coords)
        pts=[f.CreatePoint(float(x),float(y)) for x,y in coords]
        for i,(p,q) in enumerate(zip(coords,coords[1:]+coords[:1])):
            line=f.CreateLine(float(p[0]),float(p[1]),float(q[0]),float(q[1]))
            line.StartPoint=pts[i];line.EndPoint=pts[(i+1)%len(pts)]
        if closing_points is not None and k==0:
            closing_points.append(part.CreateReferenceFromObject(pts[0]))
        for i,(p,(x,y)) in enumerate(zip(pts,coords)):
            bind_point(part,sk,p,x,y,f'Loop{k+1}_Vertex{i+1}')
    finish_sketch(part,sk)
    return sk

def circle_sketch(part,body,circles,support=None,name='Fully_Constrained_Circles'):
    part.InWorkObject=body
    sk=body.Sketches.Add(part.OriginElements.PlaneXY if support is None else support);sk.Name=name
    f=sk.OpenEdition()
    for i,(x,y,r) in enumerate(circles):
        center=f.CreatePoint(float(x),float(y))
        c=f.CreateClosedCircle(float(x),float(y),float(r));c.CenterPoint=center
        bind_point(part,sk,center,x,y,f'Circle{i+1}_Center')
        cs=sk.Constraints.AddMonoEltCst(CAT_CST_RADIUS,part.CreateReferenceFromObject(c))
        cs.Mode=CAT_CST_DRIVING;cs.Dimension.Value=float(r);cs.Name=f'Circle{i+1}_Radius'
    finish_sketch(part,sk)
    return sk

def length_parameter(part,name,value):
    p=part.Parameters.CreateDimension(name,'LENGTH',0.)
    p.ValuateFromString(f'{value:.10g}mm')
    return p

def hide(doc,items):
    if not items:return
    sel=doc.Selection;sel.Clear()
    for item in items: sel.Add(item)
    sel.VisProperties.SetShow(1);sel.Clear()

def helix_quarter(part,body,spec,hidden):
    """A 90-degree native solid Rib with a dimensioned radial/axial section.

    The previous multi-section solid failed while adding closed loft sections.
    This construction has ONE closed sketch and an analytical helical path;
    it has no loft sections, closing-point references or automatic loft spine.

    The path starts strictly inside the rectangle at its mid-radius. PullingDir
    is global Z, so the sketch's vertical direction remains axial while its
    horizontal direction turns radially. Default KeepAngle/Frenet transport can
    twist a broad screw flight; it is deliberately not used here.

    CATIA CAA interfaces used:
    HybridShapeFactory.AddNewHelix(axis, invertAxis, start, pitch, height,
                                   clockwise, startingAngle, taperAngle, outward)
    ShapeFactory.AddNewRibFromRef(profileReference, centerCurveReference)
    Sweep.PullingDirElement = axisReference
    """
    r,R,t,pitch=(float(spec[k]) for k in ('inner','radius','thickness','pitch'))
    if not (0 < r < R and 0 < t < pitch and pitch > 0):
        raise ValueError('Flight requires 0 < inner < radius and 0 < thickness < pitch')
    height=pitch/4.0
    middle_radius=(r+R)/2.0
    refs=part.HybridBodies.Add();refs.Name='Hidden_Helix_Construction'
    hsf=part.HybridShapeFactory

    def point(name,xyz):
        p=hsf.AddNewPointCoord(*xyz);p.Name=name
        refs.AppendHybridShape(p)
        part.UpdateObject(p)
        return part.CreateReferenceFromObject(p)

    axis_start=point('Screw_Axis_Start',(0.,0.,0.))
    axis_end=point('Screw_Axis_End',(0.,0.,height+100.))
    path_start=point('Flight_Path_Start',(middle_radius,0.,0.))
    axis=hsf.AddNewLinePtPt(axis_start,axis_end);axis.Name='Screw_Axis_Z'
    refs.AppendHybridShape(axis);part.UpdateObject(axis)
    axis_ref=part.CreateReferenceFromObject(axis)
    path=hsf.AddNewHelix(axis_ref,False,path_start,pitch,height,False,0.,0.,False)
    path.Name='Flight_Helix_90deg'
    refs.AppendHybridShape(path)
    part.UpdateObject(path)

    # Local sketch (u,v) maps to (X,Z). All four shared vertices get driving
    # coordinates; width and axial thickness therefore have no free DOFs.
    if spec.get('normal_thickness'):
        rise=pitch/(2*math.pi)
        ti=t*math.hypot(r,rise)/r
        to=t*math.hypot(R,rise)/R
        profile=((r,-ti/2),(R,-to/2),(R,to/2),(r,ti/2))
    else:
        profile=((r,-t/2),(R,-t/2),(R,t/2),(r,t/2))
    sk=polygon_sketch(part,body,profile,name='Constrained_Flight_Radial_Section',
                      support=part.OriginElements.PlaneZX,
                      axis_data=(0.,0.,0.,1.,0.,0.,0.,0.,1.))
    part.InWorkObject=body
    rib=part.ShapeFactory.AddNewRibFromRef(part.CreateReferenceFromObject(sk),
                                         part.CreateReferenceFromObject(path))
    rib.Name='Helical_Flight_Rib'
    rib.IsThin=False
    rib.MoveProfileToPath=False
    # Set the direction BEFORE updating the solid, so no unconstrained sweep
    # orientation is evaluated. This preserves a radial/vertical section.
    rib.PullingDirElement=axis_ref
    part.InWorkObject=rib
    part.UpdateObject(rib)
    part.Update()
    hidden.extend((sk,refs))

def auger(specs,name,start,end,radius,pitch=350,inner=35,thickness=6):
    direction=unit(vec(start,end));L=norm(vec(start,end))
    ref=(0.,0.,1.) if abs(direction[2])<0.9 else (0.,1.,0.)
    a=unit(cross(ref,direction));b=cross(direction,a)
    specs.append(cylinder(name+'_Shaft',start,end,inner,FRAME))
    count=int(L/(pitch/4))
    for i in range(count):
        th=i*math.pi/2
        u=plus(scale(a,math.cos(th)),scale(b,math.sin(th)))
        v=plus(scale(a,-math.sin(th)),scale(b,math.cos(th)))
        specs.append(dict(name=f'{name}_Flight_{i+1:02d}',kind='helix',radius=radius,
                          inner=inner-1,thickness=thickness,pitch=pitch,
                          origin=plus(start,scale(direction,i*pitch/4)),
                          axes=(u,v,direction),color=GUARD,holes=()))



def timing_belt(specs,name,x,start_yz,end_yz,radius=38,width=12):
    """Closed belt around equal pulleys; one constrained annular capsule pad.

    The local profile is reused for adjacent roller pairs. Its orientation maps
    local normal to +X, so all pulleys and belts lie in the rear drive plane.
    """
    dy=end_yz[0]-start_yz[0];dz=end_yz[1]-start_yz[1]
    distance=math.hypot(dy,dz)
    length=round(distance,8)
    along=(0.,dy/distance,dz/distance)
    across=(0.,-dz/distance,dy/distance)
    def capsule(r):
        right=tuple((length/2+r*math.cos(-math.pi/2+i*math.pi/8),
                     r*math.sin(-math.pi/2+i*math.pi/8)) for i in range(9))
        left=tuple((-length/2+r*math.cos(math.pi/2+i*math.pi/8),
                    r*math.sin(math.pi/2+i*math.pi/8)) for i in range(9))
        return right+left
    origin=(x,(start_yz[0]+end_yz[0])/2,(start_yz[1]+end_yz[1])/2)
    specs.append(poly(name,capsule(radius+4),width,origin,
                      (along,across,(1.,0.,0.)),RUBBER,
                      loops=(tuple(reversed(capsule(radius))),)))

def source_station3():
    """CRP-12: longitudinal roller trough and coaxial horizontal transport screw.

    X is product flow; Y is width; Z is floor height. Published dimensions are
    identified in the returned metadata. All internal construction dimensions
    below are modelling assumptions based on the catalogue illustration.
    """
    s=[]
    roller_radius=62.;bed_radius=505.;axis_height=2250.
    # Full-height corner posts, adjustable feet and the 1040 mm lower bracing.
    for x in (600,3450):
        for side in (-1,1):
            y=side*690
            s.append(tube(f'CRP_Post_{x}_{side}',(x,y,70),(x,y,3065),70,70,4,STEEL))
            s.append(cylinder(f'CRP_Foot_{x}_{side}',(x,y,0),(x,y,18),55,MOTOR))
            s.append(cylinder(f'CRP_Level_Screw_{x}_{side}',(x,y,18),(x,y,95),14,STEEL))
        for z in (1040,1180,3040):
            s.append(tube(f'CRP_End_Cross_{x}_{z}',(x,-690,z),(x,690,z),60,60,4,STEEL))
    for side in (-1,1):
        y=side*690
        for z in (940,1360,3040):
            s.append(tube(f'CRP_Long_Rail_{side}_{z}',(600,y,z),(3450,y,z),60,60,4,STEEL))
        s.append(tube(f'CRP_Brace_In_{side}',(620,y,500),(1060,y,930),40,40,3,STEEL))
        s.append(tube(f'CRP_Brace_Out_{side}',(3430,y,500),(2990,y,930),40,40,3,STEEL))

    # Exactly twelve parallel abrasive rollers. +/-7.5 degree rollers are the
    # lowest pair; the other ten rise progressively around the screw axis.
    centers=[]
    for i in range(12):
        angle=math.radians(-82.5+15*i)
        y=bed_radius*math.sin(angle);z=axis_height-bed_radius*math.cos(angle)
        centers.append((y,z));tag=f'CRP_Roller_{i+1:02d}'
        s.append(cylinder(tag+'_Shaft',(580,y,z),(3470,y,z),14,FRAME))
        s.append(cylinder(tag+'_Core',(650,y,z),(3350,y,z),58,STEEL))
        s.append(cylinder(tag+'_Carborundum_Sleeve',(650,y,z),(3350,y,z),
                          roller_radius,ABRASIVE,58))
        for label,x in (('Front',610),('Rear',3385)):
            s.append(poly(tag+'_'+label+'_Bearing_Block',rect(78,78),25,
                          (x,y,z),AX,MOTOR,holes=((0,0,16),)))
            s.append(cylinder(tag+'_'+label+'_Bearing',(x+25,y,z),(x+35,y,z),28,STEEL,16))
        # Two timing grooves permit adjacent belts to occupy alternating planes.
        s.append(cylinder(tag+'_Timing_Pulley',(3420,y,z),(3460,y,z),38,MOTOR,14))
        for x in (3417,3460):
            s.append(cylinder(tag+f'_Pulley_Flange_{x}',(x,y,z),(x+3,y,z),43,STEEL,14))
    for i in range(11):
        timing_belt(s,f'CRP_Roller_Timing_Belt_{i+1:02d}',3422+(i%2)*20,
                    centers[i],centers[i+1])

    # Current Helix/Rib generator is used unchanged, rotated from local Z to X.
    # 4.5 turns x 600 mm = 2700 mm, matching the active roller length.
    auger(s,'CRP_Transport_Auger',(650,0,axis_height),(3350,0,axis_height),
          radius=425,pitch=600,inner=50,thickness=8)
    for label,start,end in (('Front',(520,0,axis_height),(650,0,axis_height)),
                            ('Rear',(3350,0,axis_height),(3585,0,axis_height))):
        s.append(cylinder('CRP_Auger_'+label+'_Shaft',start,end,50,FRAME))
    for label,x in (('Front',520),('Rear',3500)):
        s.append(cylinder('CRP_Auger_'+label+'_Bearing',(x,0,axis_height),
                          (x+35,0,axis_height),88,MOTOR,51))
        for side in (-1,1):
            s.append(tube(f'CRP_Auger_{label}_Bearing_Stay_{side}',
                          (x+15,side*75,axis_height+30),(x+15,side*600,2820),35,35,3,STEEL))

    # End plates have real product openings. Inner loops are opposite winding.
    end_outline=((-725,1410),(725,1410),(725,3065),(-725,3065))
    front_open=((-457.5,2070),(-457.5,2660),(457.5,2660),(457.5,2070))
    rear_open=((-305,1680),(-305,2530),(305,2530),(305,1680))
    s.append(poly('CRP_Front_End_Plate_With_Feed_Opening',end_outline,5,(550,0,0),AX,
                  loops=(front_open,)))
    s.append(poly('CRP_Rear_End_Plate_With_Outfeed_Opening',end_outline,5,(3495,0,0),AX,
                  loops=(rear_open,)))
    # Side covers can be hidden in the CATProduct tree to expose all internals.
    for side in (-1,1):
        y=-735 if side<0 else 730
        s.append(box(f'CRP_Upper_Side_Cover_{side}',(640,y,2050),(2740,5,1015)))
        s.append(box(f'CRP_Lower_Service_Cover_{side}',(640,y,1430),(2740,5,610)))
        for x in (675,3340):
            s.append(box(f'CRP_Cover_Hinge_{side}_{x}',(x,side*740-6,2025),(36,12,65)))
            s.append(box(f'CRP_Cover_Latch_{side}_{x}',(x,side*748-4,1510),(30,8,65),FRAME))
        # Handle stand-off sets the catalogue 1515 mm width envelope.
        for x in (1250,2700):
            for z in (2310,2440):
                s.append(cylinder(f'CRP_Handle_Standoff_{side}_{x}_{z}',
                                  (x,side*735,z),(x,side*752.5,z),5,RUBBER))
            s.append(cylinder(f'CRP_Cover_Handle_{side}_{x}',
                              (x,side*752.5,2310),(x,side*752.5,2440),5,RUBBER))

    # Three open safety grilles, not opaque top slabs. Mesh bars are simplified
    # 70/80 mm pitch; each rectangular bar still has a constrained sketch.
    for panel,x in enumerate((650,1570,2490),1):
        for side in (-1,1):
            s.append(box(f'CRP_Grille_{panel}_Long_{side}',(x,side*690-15,3065),(880,30,15)))
        for end in (x,x+850):
            s.append(box(f'CRP_Grille_{panel}_End_{end}',(end,-675,3065),(30,1350,15)))
        for j in range(1,13):
            s.append(box(f'CRP_Grille_{panel}_Crosswire_{j}',(x+j*65,-675,3073),(4,1350,4)))
        for j in range(1,17):
            s.append(box(f'CRP_Grille_{panel}_Longwire_{j}',(x+30,-675+j*80,3069),(820,4,4)))
        for side in (-1,1):
            y=side*540
            for handle_x in (x+380,x+500):
                s.append(box(f'CRP_Grille_{panel}_Handle_Leg_{side}_{handle_x}',
                             (handle_x,y-5,3077),(10,10,13),RUBBER))
            s.append(box(f'CRP_Grille_{panel}_Handle_{side}',(x+380,y-5,3090),(130,10,5),RUBBER))

    # Front feed enclosure: published top=2220, clear width=915. The lip floor
    # at 2200 and its descending inner floor are inferred, not catalogue values.
    s.append(plate_between('CRP_Feed_Floor',(2,0,2200),(640,0,2080),915,5))
    guide=((0,-2200),(640,-2080),(640,-2220),(0,-2220))
    for side in (-1,1):
        s.append(poly(f'CRP_Feed_Inner_Guide_{side}',guide,5,(0,side*457.5-(5 if side<0 else 0),0),AY))
        s.append(box(f'CRP_Feed_Cabinet_Side_{side}',(10,side*725-2.5,1200),(540,5,1020)))
    s.append(box('CRP_Feed_Cabinet_Front',(0,-727.5,1200),(5,1455,980)))
    for y in (-500,500):
        s.append(cylinder(f'CRP_Feed_Cabinet_Handle_{y}',(8,y,1560),(8,y,1740),6,RUBBER))
    # Inferred rear chute dimensions; exit floor height and width are published.
    chute(s,'CRP_Product_Outfeed',(3490,0,1700),(3815,0,1550),600,250,5)

    # Continuous folded peel/water trough beneath the rollers, with an open
    # round drain through a notch in the rear end cap.
    waste_section=((-680,1730),(-200,1220),(200,1220),(680,1730),
                   (676,1734),(198,1225),(-198,1225),(-676,1734))
    s.append(poly('CRP_Peel_Collection_Trough',waste_section,2850,(600,0,0),AX))
    waste_front=((-676,1730),(-198,1225),(198,1225),(676,1730))
    waste_rear=((-676,1730),(-198,1225),(-65,1225),(-65,1345),
                (65,1345),(65,1225),(198,1225),(676,1730))
    s.append(poly('CRP_Waste_Front_Cap',waste_front,5,(600,0,0),AX))
    s.append(poly('CRP_Waste_Rear_Cap',waste_rear,5,(3450,0,0),AX))
    s.append(cylinder('CRP_Waste_Drain',(3445,0,1285),(3600,0,1285),55,STEEL,50))

    # Water spray manifolds above the auger and rollers.
    for side in (-1,1):
        y=side*580
        s.append(cylinder(f'CRP_Spray_Header_{side}',(650,y,2850),(3370,y,2850),15,STEEL,11))
        for j in range(9):
            x=740+j*305
            s.append(cylinder(f'CRP_Spray_Nozzle_{side}_{j+1}',(x,y,2845),
                              (x,side*540,2790),7,MOTOR,4))
    s.append(cylinder('CRP_Water_Cross_Header',(3370,-580,2850),(3370,740,2850),15,STEEL,11))

    # Rear auger geared motor and the separate roller drive, with rear guarding.
    s.append(box('CRP_Auger_Gearbox',(3505,-85,2170),(160,170,160),SO_MOTOR))
    s.append(cylinder('CRP_Auger_Drive_Motor',(3585,0,2330),(3585,0,2580),75,SO_MOTOR))
    s.append(cylinder('CRP_Auger_Fan_Cover',(3585,0,2580),(3585,0,2610),82,SO_MOTOR))
    for j in range(6):
        s.append(cylinder(f'CRP_Auger_Motor_Fin_{j}',(3585,0,2345+j*36),
                          (3585,0,2352+j*36),80,SO_MOTOR))
    drive_y,drive_z=centers[-1]
    s.append(box('CRP_Roller_Drive_Gearbox',(3465,drive_y-65,drive_z-65),(120,130,130),MOTOR))
    s.append(cylinder('CRP_Roller_Drive_Motor',(3585,drive_y,drive_z),(3760,drive_y,drive_z),78,MOTOR))
    s.append(cylinder('CRP_Roller_Drive_Fan',(3760,drive_y,drive_z),(3785,drive_y,drive_z),85,RUBBER))
    return s,dict(name='03_CRP_12',inlet=(0,0,2200),inlet_direction=(1,0,0),
                  outlet=(3815,0,1550),outlet_direction=(1,0,0),length=3815,
                  catalogue_envelope_mm=(3815,1515,3095),catalogue_rollers=12,
                  catalogue_feed_enclosure_height_mm=2220,catalogue_feed_width_mm=915,
                  catalogue_outlet_width_mm=600,catalogue_outlet_bottom_mm=1550,
                  assumed_roller=dict(diameter_mm=124,active_length_mm=2700,
                                      center_arc_radius_mm=505,angles_deg=[-82.5+15*i for i in range(12)]),
                  assumed_screw=dict(diameter_mm=850,pitch_mm=600,shaft_diameter_mm=100,
                                     flight_thickness_mm=8,flight_length_mm=2700,axis_height_mm=2250),
                  fidelity='Catalogue envelope and 12-roller layout; inferred internal dimensions, mesh pitch and drive detail; static layout, no kinematics.',
                  description='CRP-12 roller peeler: twelve abrasive rollers in a U-shaped bed, horizontal transport auger, mesh covers and waste trough.')

def tapered_chute(specs,name,start,end,width0,width1,wall_h=180,t=5,slots=False):
    """Planar floor and tapered vertical sides, all built with constrained pads."""
    if abs(start[1]-end[1])>1e-8 or end[0]<=start[0]:
        raise ValueError('tapered_chute needs increasing X and constant Y')
    along=unit(vec(start,end));l=norm(vec(start,end));normal=cross(along,(0.,1.,0.))
    floor=((-l/2,-width0/2),(l/2,-width1/2),(l/2,width1/2),(-l/2,width0/2))
    center=scale(plus(start,end),0.5)
    specs.append(poly(name+'_Floor',floor,t,plus(center,scale(normal,-t)),
                      (along,(0.,1.,0.),normal)))
    for side in (-1,1):
        a=plus(start,(0.,side*width0/2,0.));b=plus(end,(0.,side*width1/2,0.))
        run=math.hypot(b[0]-a[0],b[1]-a[1]);rise=b[2]-a[2]
        u=((b[0]-a[0])/run,(b[1]-a[1])/run,0.);v=(0.,0.,1.);n=cross(u,v)
        profile=((0.,0.),(run,rise),(run,rise+wall_h),(0.,wall_h))
        loops=[]
        if slots:
            for j in range(1,int(run/34)):
                x=j*34.;low=rise*x/run+30;high=rise*x/run+wall_h-30
                loops.append(((x-6,low),(x-6,high),(x+6,high),(x+6,low)))
        origin=a if side<0 else plus(a,scale(n,-t))
        specs.append(poly(name+f'_Side_Guard_{side}',profile,t,origin,(u,v,n),loops=tuple(loops)))

def unequal_pulley_belt(specs,name,x,large_center,small_center,large_radius,small_radius,width=14,t=6):
    """Faceted closed belt following external tangents of unequal pulleys.

    Each belt is an annular pad, not a solid web filling the space between its
    pulleys. The drum suspension is a static geometric representation.
    """
    dy=small_center[0]-large_center[0];dz=small_center[1]-large_center[1]
    d=math.hypot(dy,dz)
    if d<=abs(large_radius-small_radius):raise ValueError('Invalid belt pulley spacing')
    alpha=math.acos((large_radius-small_radius)/d)
    u=(0.,dy/d,dz/d);v=(0.,-dz/d,dy/d)
    def outline(offset):
        r=small_radius+offset;R=large_radius+offset
        small=tuple((d+r*math.cos(-alpha+2*alpha*i/12),
                     r*math.sin(-alpha+2*alpha*i/12)) for i in range(13))
        large=tuple((R*math.cos(alpha+(2*math.pi-2*alpha)*i/36),
                     R*math.sin(alpha+(2*math.pi-2*alpha)*i/36)) for i in range(37))
        return small+large
    specs.append(poly(name,outline(t),width,(x,*large_center),(u,v,(1.,0.,0.)),
                      RUBBER,loops=(tuple(reversed(outline(0))),)))

def source_station4():
    """MS-20 knife peeler, using the published 2000 mm drum configuration.

    X is flow, Z is floor height. The housing is centred at Y=0; the optional
    control box extends the -Y side, giving total width 1400 (-810 to +590).
    All blade counts, internal diameters and positions are explicitly inferred.
    """
    s=[];zc=1770.;drum_inner=410.;drum_radius=445.
    # Four feet, open underframe and diagonal braces.
    for x in (550,2700):
        for side in (-1,1):
            y=side*520
            s.append(tube(f'MS_Leg_{x}_{side}',(x,y,65),(x,y,930),60,60,4,STEEL))
            s.append(cylinder(f'MS_Foot_{x}_{side}',(x,y,0),(x,y,16),55,MOTOR))
            s.append(cylinder(f'MS_Level_Screw_{x}_{side}',(x,y,16),(x,y,90),13,STEEL))
        s.append(tube(f'MS_Frame_Cross_{x}',(x,-520,850),(x,520,850),60,60,4,STEEL))
    for side in (-1,1):
        y=side*520
        s.append(tube(f'MS_Frame_Long_{side}',(550,y,850),(2700,y,850),60,60,4,STEEL))
        s.append(tube(f'MS_Brace_Front_{side}',(560,y,520),(950,y,840),40,40,3,STEEL))
        s.append(tube(f'MS_Brace_Rear_{side}',(2690,y,520),(2300,y,840),40,40,3,STEEL))

    # Hollow drum: sixty blue carriers with three real through-slots each.
    # Twelve facets and five axial modules are inferred from the product photo.
    # The blades are separate tapered metal pads on the INNER face of the drum.
    for sector in range(12):
        theta=2*math.pi*sector/12
        u=(1.,0.,0.);v=(0.,math.sin(theta),-math.cos(theta))
        n=(0.,math.cos(theta),math.sin(theta))
        for row,xc in enumerate((800.,1200.,1600.,2000.,2400.),1):
            angle=math.radians(32 if (sector+row)%2 else -32)
            ca,sa=math.cos(angle),math.sin(angle)
            along=plus(scale(u,ca),scale(v,sa))
            across=plus(scale(u,-sa),scale(v,ca))
            loops=[]
            for k,slot_x in enumerate((-120.,0.,120.),1):
                opening=tuple((slot_x+a*ca-b*sa,a*sa+b*ca) for a,b in rect(150,14))
                loops.append(tuple(reversed(opening)))
                # Across-slot coordinate 1..13 covers one slot edge, leaving
                # an open peel discharge gap on the other side of the blade.
                blade_section=((1.,2.5),(13.,0.),(13.,3.),(1.,3.))
                base=plus((xc+slot_x,0.,zc),scale(n,407.))
                base=plus(base,scale(along,-73.))
                s.append(poly(f'MS_Knife_{sector+1:02d}_{row}_{k}',blade_section,146,
                              base,(across,n,along),ROLLER))
            origin=plus((xc,0.,zc),scale(n,drum_inner))
            s.append(poly(f'MS_Blue_Drum_Carrier_{sector+1:02d}_{row}',rect(380,218),15,
                          origin,(u,v,n),MS_BLUE,loops=tuple(loops)))
    for label,x in (('Front',600),('Rear',2540)):
        s.append(cylinder(f'MS_Drum_{label}_Belt_Seat',(x,0,zc),(x+60,0,zc),drum_radius,MS_BLUE,405))
    for x in (990,1390,1790,2190):
        s.append(cylinder(f'MS_Drum_Intermediate_Ring_{x}',(x,0,zc),(x+20,0,zc),442,STEEL,405))

    # Horizontal screw uses the existing numerical section constraints and
    # Helix/Rib implementation unchanged. 4 turns x 500 = 2000 mm.
    auger(s,'MS_Transport_Auger',(600,0,zc),(2600,0,zc),385,500,45,8)
    s.append(cylinder('MS_Auger_Front_Stub',(500,0,zc),(600,0,zc),45,FRAME))
    s.append(cylinder('MS_Auger_Rear_Stub',(2600,0,zc),(2820,0,zc),45,FRAME))
    for label,x in (('Front',500),('Rear',2680)):
        s.append(cylinder(f'MS_Auger_{label}_Bearing',(x,0,zc),(x+30,0,zc),75,MOTOR,46))
        for side in (-1,1):
            s.append(tube(f'MS_Auger_{label}_Bearing_Stay_{side}',(x+15,side*65,zc+30),
                          (x+15,side*400,2230),30,30,3,STEEL))
    # Sixteen illustrative spray nozzles on the flight outer circumference.
    for j in range(16):
        phase=(j+0.5)*math.pi/2;x=600+(j+0.5)*125
        radial=(0.,math.cos(phase),math.sin(phase))
        s.append(cylinder(f'MS_Flight_Spray_Nozzle_{j+1:02d}',
                          plus((x,0,zc),scale(radial,368)),
                          plus((x,0,zc),scale(radial,390)),6,MOTOR,3))

    # Three suspension/drive belt loops at EACH drum end, with one small
    # pulley per loop. Front and rear top-left pulleys each get a drive motor.
    pulley_centers=((-450.,2180.),(450.,2180.),(0.,1100.))
    for label,x0 in (('Front',602.),('Rear',2542.)):
        for j,(y,z) in enumerate(pulley_centers):
            x=x0+j*20
            unequal_pulley_belt(s,f'MS_{label}_Suspension_Belt_{j+1}',x,(0.,zc),(y,z),445,45)
            s.append(cylinder(f'MS_{label}_Suspension_Pulley_{j+1}',(x-2,y,z),(x+16,y,z),45,MOTOR,14))
            # Shafts reach the end-frame plate; mounting holes are cut below.
            a,b=(510.,x+18) if label=='Front' else (x-5,2705.)
            s.append(cylinder(f'MS_{label}_Pulley_Shaft_{j+1}',(a,y,z),(b,y,z),14,FRAME))
            bx=510. if label=='Front' else 2685.
            s.append(cylinder(f'MS_{label}_Pulley_Bearing_{j+1}',(bx,y,z),(bx+15,y,z),30,STEEL,15))

    # Folded stainless housing; true openings for the drum and pulley shafts.
    end=((-545,900),(545,900),(585,1200),(585,2130),
         (430,2335),(-430,2335),(-585,2130),(-585,1200))
    shaft_holes=((0,zc,455),)+tuple((y,z,16) for y,z in pulley_centers)
    for label,x in (('Front',520),('Rear',2680)):
        s.append(poly(f'MS_{label}_End_Frame',end,10,(x,0,0),AX,holes=shaft_holes))
    s.append(box('MS_Housing_Roof',(530,-430,2330),(2150,860,5)))
    for side in (-1,1):
        bevel=((side*430,2335),(side*580,2130),(side*575,2128),(side*426,2330))
        s.append(poly(f'MS_Roof_Bevel_{side}',bevel,2150,(530,0,0),AX))
        y=-580 if side<0 else 575
        s.append(box(f'MS_Upper_Cleaning_Hatch_{side}',(540,y,1700),(2130,5,425)))
        s.append(box(f'MS_Lower_Cleaning_Hatch_{side}',(540,y,1350),(2130,5,340)))
        for x in (640,2500):
            s.append(box(f'MS_Hatch_Hinge_{side}_{x}',(x,side*580-5,1670),(55,10,45)))
            s.append(cylinder(f'MS_Hatch_Latch_{side}_{x}',(x,side*585,1480),(x,side*585,1540),5,RUBBER))
        for z in (1800,1920):
            s.append(cylinder(f'MS_Hatch_Handle_Stand_{side}_{z}',(1600,side*580,z),(1600,side*585,z),5,RUBBER))
        s.append(cylinder(f'MS_Hatch_Handle_{side}',(1600,side*585,1800),(1600,side*585,1920),5,RUBBER))
    for x in (850,2350):
        s.append(box(f'MS_Lifting_Eye_Base_{x}',(x-10,-10,2335),(20,20,10)))
        s.append(cylinder(f'MS_Lifting_Eye_{x}',(x,-6,2350),(x,6,2350),10,STEEL,6))

    # Peel funnel below the rotating drum, with an open central bottom outlet.
    for side in (-1,1):
        slope=((side*580,1350),(side*190,890),(side*185,894),(side*575,1354))
        s.append(poly(f'MS_Waste_Funnel_Side_{side}',slope,2140,(540,0,0),AX))
    for x in (540,2675):
        s.append(poly(f'MS_Waste_Funnel_End_{x}',((-575,1350),(-190,890),(190,890),(575,1350)),
                      5,(x,0,0),AX))
    s.append(box('MS_Waste_Floor_Front',(540,-190,885),(477.5,380,5)))
    s.append(box('MS_Waste_Floor_Rear',(2202.5,-190,885),(477.5,380,5)))
    for y in (-190,185):
        s.append(box(f'MS_Waste_Outlet_Lip_{y}',(1017.5,y,840),(1185,5,50)))

    # Feed floor and slotted guards taper from published 660 to inferred 460.
    tapered_chute(s,'MS_Product_Infeed',(5,0,1535),(550,0,1420),660,460,280,5,slots=True)
    s.append(box('MS_Infeed_Lip',(0,-330,1527),(8,660,8)))
    tapered_chute(s,'MS_Product_Outfeed',(2695,0,1340),(3070,0,1140),600,500,200,5)

    # Two drum drives plus one auger drive = three motors, as in the brochure.
    for label,x,sgn in (('Front',430.,-1.),('Rear',2800.,1.)):
        y,z=pulley_centers[0]
        s.append(box(f'MS_{label}_Drum_Gearbox',(x-45,y-65,z-65),(90,130,130),SO_MOTOR))
        s.append(cylinder(f'MS_{label}_Drum_Motor',(x+sgn*45,y,z),(x+sgn*290,y,z),72,SO_MOTOR))
        s.append(cylinder(f'MS_{label}_Drum_Fan',(x+sgn*290,y,z),(x+sgn*315,y,z),80,SO_MOTOR))
        shaft_a,shaft_b=(x+45,625.) if sgn<0 else (2540.,x-45)
        s.append(cylinder(f'MS_{label}_Drum_Drive_Axle',(shaft_a,y,z),(shaft_b,y,z),14,FRAME))
    s.append(box('MS_Auger_Gearbox',(2710,-75,1695),(140,150,150),SO_MOTOR))
    s.append(cylinder('MS_Auger_Motor',(2850,0,zc),(3080,0,zc),70,SO_MOTOR))
    s.append(cylinder('MS_Auger_Fan',(3080,0,zc),(3105,0,zc),76,SO_MOTOR))

    # Optional control cabinet is included because it defines the 1400 mm
    # published total width. Indicator faces have geometry, not embedded text.
    s.append(tube('MS_Control_Box_Bracket',(2685,-500,1450),(2900,-680,1450),40,40,3,STEEL))
    s.append(box('MS_Control_Cabinet',(2750,-790,1400),(500,200,510)))
    s.append(box('MS_Control_Door',(2758,-796,1408),(484,6,494)))
    s.append(box('MS_Control_Display_Bezel',(2820,-802,1680),(340,6,160),RUBBER))
    for x in (2840,3020):
        s.append(box(f'MS_Control_Readout_{x}',(x,-804,1750),(120,2,60),(45,65,75)))
    for i,(x,col) in enumerate(((2860,(32,170,75)),(2950,(210,45,35)),(3040,(45,90,170)))):
        s.append(cylinder(f'MS_Control_Button_{i+1}',(x,-796,1620),(x,-810,1620),14,col))
    s.append(cylinder('MS_EStop_Backplate',(3130,-796,1510),(3130,-802,1510),34,GUARD))
    s.append(cylinder('MS_EStop',(3130,-802,1510),(3130,-810,1510),24,(210,35,30)))
    return s,dict(name='04_MS_20',inlet=(0,0,1535),inlet_direction=(1,0,0),
                  outlet=(3070,0,1140),outlet_direction=(1,0,0),length=3250,
                  catalogue_envelope_mm=(3250,1400,2360),catalogue_drum_length_mm=2000,
                  catalogue_housing_width_mm=1180,catalogue_inlet_width_mm=660,
                  catalogue_outlet_width_mm=500,catalogue_inlet_height_mm=1535,
                  catalogue_outlet_height_mm=1140,catalogue_motors=3,
                  assumed_drum=dict(facets=12,axial_modules=5,knife_count=180,
                                    carrier_inner_radius_mm=410,carrier_thickness_mm=15,
                                    belt_seat_radius_mm=445,axis_height_mm=1770),
                  assumed_screw=dict(diameter_mm=770,pitch_mm=500,shaft_diameter_mm=90,
                                     flight_thickness_mm=8,flight_length_mm=2000),
                  fidelity='MS-20 catalogue envelope; inferred internal dimensions, blade count/angles and static suspension; no kinematics.',
                  description='MS-20 knife peeler: slotted blue drum with separate blades, horizontal auger, six suspension belts, cleaning hatches and control cabinet.')

def sheet_quad(specs,name,corners,t=3,color=STEEL):
    """An arbitrary planar sheet, expressed as a numerically constrained pad."""
    origin=corners[0];u=unit(vec(origin,corners[1]))
    n=unit(cross(u,vec(origin,corners[3])));v=cross(n,u)
    coordinates=[]
    for p in corners:
        d=vec(origin,p)
        if abs(sum(d[i]*n[i] for i in range(3)))>1e-6:
            raise ValueError(f'{name}: sheet corners are not planar')
        coordinates.append(tuple(round(sum(d[i]*a[i] for i in range(3)),8) for a in (u,v)))
    specs.append(poly(name,tuple(coordinates),t,origin,(u,v,n),color))





def transfer34():
    """Passive connection: CRP outlet 1550 to MS-20 inlet 1535, no lift needed."""
    s=[]
    tapered_chute(s,'Transfer_03_04',(0,0,1550),(300,0,1535),600,660,180,5)
    for x,width,z in ((0,600,1550),(275,660,1535)):
        for side in (-1,1):
            s.append(box(f'Transfer34_Mount_{x}_{side}',(x,side*(width/2)-10,z-30),(25,20,25)))
    return s,dict(name='Transfer_03_04',inlet=(0,0,1550),outlet=(300,0,1535),
                  description='Short tapered gravity chute connecting CRP-12 to MS-20.')

def transfer23():
    """Custom incline from SO outlet (1520) to CRP feed floor (2200)."""
    s=[]
    belt(s,'Transfer_02_03',(0,0,1480),(2400,0,2280),550,cleats=True)
    chute(s,'Transfer_02_03_Drop',(2400,0,2280),(2700,0,2200),550,140,5)
    for x in (130,2200):
        top=1480+x/3-95
        for side in (-1,1):
            y=side*305
            s.append(tube(f'Transfer23_Leg_{x}_{side}',(x,y,35),(x,y,top),60,60,4))
            s.append(box(f'Transfer23_Foot_{x}_{side}',(x-60,y-60,0),(120,120,15),FRAME))
        s.append(tube(f'Transfer23_Cross_{x}',(x,-305,top),(x,305,top),60,60,4))
    for side in (-1,1):
        s.append(tube(f'Transfer23_Low_Rail_{side}',(130,side*305,350),(2200,side*305,350),45,45,3))
        s.append(tube(f'Transfer23_Brace_{side}',(130,side*305,370),(2200,side*305,1700),40,40,3))
        rail=((0,-1480),(2400,-2280),(2400,-2450),(0,-1650))
        s.append(poly(f'Transfer23_Side_Guide_{side}',rail,5,(0,side*280,0),AY))
    drive(s,'Transfer23_Drive',2400,350,2228)
    return s,dict(name='Transfer_02_03',inlet=(0,0,1480),outlet=(2700,0,2200),
                  description='Custom rising conveyor from SO-50/250-R to the CRP-12 feed enclosure.')

def transfer12():
    """Custom link: rises from the existing VBK discharge to the SO tank rim."""
    s=[]
    belt(s,'Transfer_01_02',(0,0,980),(1800,0,1280),550,cleats=True)
    chute(s,'Transfer_Drop',(1800,0,1280),(2010,0,1200),550,140,5)
    for x in (100,1650):
        top=980+x*(300/1800)-95
        for side in (-1,1):
            y=side*305
            s.append(tube(f'Transfer_Leg_{x}_{side}',(x,y,35),(x,y,top),50,50,3))
            s.append(box(f'Transfer_Foot_{x}_{side}',(x-50,y-50,0),(100,100,15),FRAME))
        s.append(tube(f'Transfer_Cross_{x}',(x,-305,top),(x,305,top),50,50,3))
    for side in (-1,1):
        s.append(tube(f'Transfer_Low_Rail_{side}',(100,side*305,260),
                      (1650,side*305,260),40,40,3))
        rail=((0,-980),(1800,-1280),(1800,-1430),(0,-1130))
        s.append(poly(f'Transfer_Side_Guide_{side}',rail,5,(0,side*280,0),AY))
    drive(s,'Transfer_Drive',1800,350,1228)
    return s,dict(name='Transfer_01_02',inlet=(0,0,980),outlet=(2010,0,1200),
                  description='Custom cleated transfer conveyor between the existing VBK and the SO tank.')

def create_part(catia,spec,path,part_number=None):
    doc=catia.Documents.Add('Part');part=doc.Part;body=part.MainBody
    doc.Product.PartNumber=part_number or spec['name'];part.InWorkObject=body
    if spec.get('material'):
        # Catalog material assignment is intentionally not faked: these are readable metadata.
        part.Parameters.CreateString('Engineering_Material',spec['material'])
        part.Parameters.CreateString('Material_Status','Specification only; CATIA material catalog not assigned')
        if 'mass_override_kg' in spec:
            part.Parameters.CreateReal('Purchased_Mass_Estimate_kg',float(spec['mass_override_kg']))
        else:
            part.Parameters.CreateReal('Design_Density_kg_m3',float(spec['density_kg_m3']))
    hidden=[part.OriginElements.PlaneXY,part.OriginElements.PlaneYZ,part.OriginElements.PlaneZX]
    if spec['kind']=='helix':
        helix_quarter(part,body,spec,hidden)
    elif spec['kind']=='poly':
        sk=polygon_sketch(part,body,spec['points'],spec.get('loops',()))
    elif spec['kind']=='circle':
        circles=[(0.,0.,spec['radius'])]
        if spec.get('inner',0):circles.append((0.,0.,spec['inner']))
        sk=circle_sketch(part,body,circles)
    else:
        raise ValueError(f'Unknown shape kind: {spec["kind"]}')
    if spec['kind']!='helix':
        hidden.append(sk)
        length_parameter(part,'Extrusion_mm',spec['depth'])
        pad=part.ShapeFactory.AddNewPad(sk,float(spec['depth']));pad.Name='Profile_Pad'
        part.Relations.CreateFormula('Drive_Pad_Length','',pad.FirstLimit.Dimension,'Extrusion_mm')
        part.Update()
    if spec.get('holes'):
        refs=part.HybridBodies.Add();refs.Name='Hidden_Reference_Planes'
        plane=part.HybridShapeFactory.AddNewPlaneOffset(part.OriginElements.PlaneXY,float(spec['depth']),False)
        refs.AppendHybridShape(plane);part.Update()
        part.InWorkObject=body
        sk2=circle_sketch(part,body,spec['holes'],part.CreateReferenceFromObject(plane),'Mounting_Holes_Constrained')
        pocket=part.ShapeFactory.AddNewPocket(sk2,float(spec['depth']));pocket.Name='Through_Mounting_Holes'
        part.Update();hidden.extend([sk2,refs])
    hide(doc,hidden)
    sel=doc.Selection;sel.Clear();sel.Add(body);sel.VisProperties.SetRealColor(*spec['color'],1)
    if spec.get('transparency') is not None:sel.VisProperties.SetRealOpacity(255-round(255*spec['transparency']/100),1)
    sel.Clear()
    path.parent.mkdir(parents=True,exist_ok=True)
    doc.SaveAs(str(path))
    return doc

def pack(folder,dependencies=()):
    target=folder.with_suffix('.zip')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        seen=set()
        for source in (folder,*dependencies):
            for f in sorted(source.rglob('*')):
                if f.is_file() and f.resolve() not in seen:
                    z.write(f,Path(source.name)/f.relative_to(source))
                    seen.add(f.resolve())
    return target

def update_status(base,name,record):
    from review_layout import status_path
    path=status_path(base);path.parent.mkdir(parents=True,exist_ok=True)
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    data[name]=record;path.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')

def open_document(catia,path):
    """Reuse an already open document, including the user's existing stage 1."""
    path=path.resolve()
    for i in range(1,catia.Documents.Count+1):
        doc=catia.Documents.Item(i)
        if str(doc.FullName) and Path(str(doc.FullName)).resolve()==path:
            return doc
    return catia.Documents.Open(str(path))

def show_document(catia,doc):
    doc.Activate()
    catia.Visible=True
    # View changes are cosmetic. A missing standard camera must not discard a
    # successfully built assembly on a CATIA installation with customized cameras.
    try:
        viewer=catia.ActiveWindow.ActiveViewer
        try:viewer.Viewpoint3D=doc.Cameras.Item('* iso').Viewpoint3D
        except Exception:pass
        viewer.Reframe()
        viewer.Update()
    except Exception as exc:
        print(f'VIEW: document is open; Fit All In manually if needed: {exc}',flush=True)

def place(component,origin=(0.,0.,0.),axes=I):
    component.Position.SetComponents(tuple(float(q) for a in axes for q in a)
                                     +tuple(float(q) for q in origin))

def new_folder(base,name):
    """Never overwrite previously generated native documents or partial work."""
    folder=base/name
    if folder.exists():
        n=1
        while (base/f'{name}_r{REVISION}_{n:02d}').exists():n+=1
        folder=base/f'{name}_r{REVISION}_{n:02d}'
    folder.mkdir(parents=True)
    from clean_outputs import mark_model_folder
    mark_model_folder(folder,name)
    return folder




def transform_point(point,origin=(0.,0.,0.),axes=I):
    return tuple(origin[i]+sum(axes[j][i]*point[j] for j in range(3)) for i in range(3))






FRYER_SOURCES = {
    'primary_drawing': 'https://www.heatandcontrol.com/sites/default/files/content/resource/pdf/2026-06/Potato%20Chip%20Fryer_HeatandControl.pdf',
    'secondary_reference': 'https://www.bxmachinery.com/products/full-automatic-potato-chips-production-line/',
}

FRYER_MODELS = {
    'PC4':  dict(A=7900., B=1300., C=510., D=1190., E=1020.),
    'PC10': dict(A=8200., B=1630., C=910., D=1140., E=1020.),
    'PC14': dict(A=9500., B=1860., C=1170., D=1220., E=910.),
    'PC21': dict(A=10400., B=2240., C=1520., D=1220., E=910.),
    'PC32': dict(A=12200., B=2390., C=1680., D=1270., E=970.),
    'PC42': dict(A=13100., B=2770., C=1980., D=1320., E=1020.),
    'PC50': dict(A=14300., B=2770., C=1980., D=1320., E=1020.),
}

FRYER_ESTIMATES = {
    'pan_start_fraction': .02, 'pan_end_fraction': .975,
    'pan_width_margin': 180., 'insulation_gap': 45.,
    'pan_floor_below_feed': 570., 'pan_floor_below_carrier': 200.,
    'pan_rim_below_feed': 90.,
    'wet_wall_thickness': 6., 'cladding_thickness': 3.,
    'oil_level_below_feed': 280., 'oil_level_below_outlet': 140.,
    'carrier_below_feed': 370., 'carrier_below_outlet': 230.,
    'feed_end_fraction': .15, 'carrier_end_fraction': .70,
    'submerger_start_fraction': .32, 'submerger_end_fraction': .69,
    'submerger_lower_above_carrier': 60.,
    'discharge_start_fraction': .72, 'discharge_end_margin': 80.,
    'discharge_tip_above_E': 15., 'mesh_thickness': 3.,
    'mesh_pitch': 85., 'mesh_web': 5., 'mesh_tile_length': 425.,
    'carrier_drum_radius': 55., 'submerger_drum_radius': 50.,
    'discharge_drum_radius': 35.,
    'paddle_count': 3, 'paddle_radius': 65., 'paddle_thickness': 4.,
    'hood_start_fraction': .055, 'hood_end_fraction': .85,
    'hood_bottom_above_rim': 30., 'hood_eave_above_feed': 260.,
    'hood_ridge_above_feed': 500., 'hood_thickness': 3.,
    'hood_max_lift': 650., 'hood_transparency': 65,
    'stack_fraction': .45, 'stack_plenum_width': 380.,
    'stack_radius': 130., 'stack_wall': 4.,
    'stack_top_above_ridge': 1000.,
    'frame_tube': 70., 'frame_wall': 4.,
    'oil_port_radius': 40., 'oil_port_wall': 4.,
}

PREP_SOURCES = {
    'dimensions_and_photos': 'https://www.bxmachinery.com/products/full-automatic-potato-chips-production-line/',
    'baixin_video': 'https://www.youtube.com/watch?v=ShJeZMuuqgo&t=36s',
    'process_reference_video': 'https://www.youtube.com/watch?v=3TCps0cEurM',
}

PREP_ENVELOPES = {
    6: dict(length=4500.,width=1200.,height=1300.,vendor_row=7),
    7: dict(length=1800.,width=1000.,height=1300.,vendor_row=8),
    8: dict(length=3500.,width=1000.,height=1600.,vendor_row=9),
}

PREP_INTERFACES = {
    6: dict(inlet_height=1200.,outlet_height=1220.,inlet_width=700.,outlet_width=700.),
    7: dict(inlet_height=1220.,outlet_height=1200.,inlet_width=700.,outlet_width=700.),
    8: dict(inlet_height=1200.,outlet_height=1190.,inlet_width=700.,outlet_width=510.),
}

PREP_ESTIMATES = {
    'sheet': 3., 'wet_sheet': 5., 'mesh_thickness': 3.,
    'mesh_pitch': 55., 'mesh_web': 4., 'mesh_tile_length': 350.,
    'frame_member': 50., 'frame_wall': 3., 'belt_drum_radius': 35.,
    'blancher_floor': 640., 'blancher_rim': 1120.,
    'blancher_water_level': 990., 'blancher_belt_level': 850.,
    'blancher_hood_top': 1260.,
    'dewater_frame_top': 880., 'drain_pan_floor': 900.,
    'leaf_spring_thickness': 4., 'leaf_spring_layers': 3,
    'dryer_deck_drop': 60.,
    'dryer_nozzle_clearance': 100., 'dryer_fan_radius': 115.,
    'dryer_lift_cleat_height': 20.,
}

class AssemblySpecs(list):
    """Assign a functional product to parts made by existing geometry helpers."""
    def __init__(self):
        super().__init__();self.current_group='Main Assembly'

    def append(self,spec):
        spec=dict(spec);spec.setdefault('group',self.current_group)
        super().append(spec)

    @contextmanager
    def section(self,name):
        previous=self.current_group;self.current_group=name
        try:yield self
        finally:self.current_group=previous

def fryer_mesh(specs,name,start,end,width,est,color=BELT):
    """Open grid tiles: a Pad with constrained inner loops, not a solid plane.

    Equal tiles share one CATPart. Pitch is a coarse visual representation,
    not the manufacturing wire spacing.
    """
    direction=unit(vec(start,end));length=norm(vec(start,end))
    transverse=(0.,1.,0.);normal=unit(cross(direction,transverse))
    pitch=est['mesh_pitch'];web=est['mesh_web'];thick=est['mesh_thickness']
    count=max(1,math.ceil(length/est['mesh_tile_length']))
    tile_length=length/count
    nx=max(1,int(tile_length/pitch));ny=max(1,int(width/pitch))
    dx=tile_length/nx;dy=width/ny;openings=[]
    for ix in range(nx):
        for iy in range(ny):
            cx=-tile_length/2+(ix+.5)*dx;cy=-width/2+(iy+.5)*dy
            openings.append(tuple(reversed(tuple((x+cx,y+cy) for x,y in rect(dx-web,dy-web)))))
    for i in range(count):
        center=plus(start,scale(direction,(i+.5)*tile_length))
        origin=plus(center,scale(normal,-thick))
        specs.append(poly(f'{name}_MeshTile_{i+1:02d}',rect(tile_length,width),thick,
                          origin,(direction,transverse,normal),color,loops=tuple(openings)))

def fryer_drive(specs,name,center,width,overall_width,color=MOTOR):
    """Shaft coupling, gearbox, motor and shelf attached to the driven Y shaft."""
    first=len(specs)
    x,_,z=center;motor1=overall_width/2-20
    clearance=motor1-width/2
    if clearance<95:
        raise ValueError(f'{name}: insufficient side clearance for the compact gearmotor')
    gear_width=min(90.,clearance*.4);y=width/2+20+gear_width/2
    specs.append(cylinder(name+'_Shaft_Coupling',(x,width/2,z),(x,y,z),18,FRAME))
    specs.append(box(name+'_Gearbox',(x-65,y-gear_width/2,z-65),(130,gear_width,130),color))
    motor0=y+gear_width/2
    specs.append(cylinder(name+'_Motor',(x,motor0,z),(x,motor1-20,z),52,color))
    specs.append(cylinder(name+'_FanCover',(x,motor1-20,z),(x,motor1,z),57,RUBBER))
    for i in range(5):
        yf=motor0+5+(motor1-motor0-30)*i/4
        specs.append(cylinder(f'{name}_MotorFin_{i+1}',(x,yf,z),(x,yf+4,z),57,color))
    specs.append(box(name+'_Mount',(x-70,width/2+12,z-85),
                      (140,motor1-width/2-12,14),FRAME))
    for spec in specs[first:]:spec['group']='Drive System'

def fryer_conveyor(specs,name,start,end,width,radius,est,overall_width,drive_at_end=False):
    """End drums, carrying and return mesh runs, bearings and side rails."""
    direction=unit(vec(start,end));normal=unit(cross(direction,(0.,1.,0.)))
    fryer_mesh(specs,name+'_Carrying',start,end,width,est)
    clearance=6.
    shift=scale(normal,-2*radius-est['mesh_thickness']-2*clearance)
    fryer_mesh(specs,name+'_Return',plus(start,shift),plus(end,shift),width,est,RUBBER)
    centers=[]
    for i,p in enumerate((start,end)):
        c=plus(p,scale(normal,-radius-est['mesh_thickness']-clearance));centers.append(c)
        roller(specs,f'{name}_End_{i+1}',c[0],c[2],width,radius,c[1])
    for side in (-1,1):
        shift=plus((0,side*(width/2+35),0),scale(normal,-radius))
        specs.append(tube(f'{name}_SideRail_{side}',plus(start,shift),plus(end,shift),35,45,3))
    if drive_at_end:
        fryer_drive(specs,name+'_Drive',centers[-1],width,overall_width)

def fryer_paddle(specs,name,x,z,width,radius,thickness,phase=0.):
    specs.append(cylinder(name+'_Shaft',(x,-width/2-40,z),(x,width/2+40,z),18,FRAME))
    specs.append(cylinder(name+'_Hub',(x,-width/2,z),(x,width/2,z),23,ROLLER))
    for side in (-1,1):
        specs.append(box(f'{name}_Bearing_{side}',(x-26,side*(width/2+26)-16,z-26),
                          (52,32,52),MOTOR))
    for i in range(4):
        theta=phase+i*math.pi/2
        radial=(math.cos(theta),0.,math.sin(theta))
        tangent=(math.sin(theta),0.,-math.cos(theta))
        profile=((20,-thickness/2),(radius,-thickness/2),
                 (radius,thickness/2),(20,thickness/2))
        specs.append(poly(f'{name}_Blade_{i+1}',profile,width,(x,-width/2,z),
                          (radial,tangent,(0.,1.,0.)),GUARD))

def quad_sheet(name,vertices,thickness=3.,color=STEEL):
    """Native Pad for a planar four-corner sheet, including tapered side guides."""
    p=vertices[0];u=unit(vec(p,vertices[1]));n=unit(cross(u,vec(p,vertices[-1])))
    v=cross(n,u)
    points=tuple((sum(a*b for a,b in zip(vec(p,q),u)),
                  sum(a*b for a,b in zip(vec(p,q),v))) for q in vertices)
    return poly(name,points,thickness,plus(p,scale(n,-thickness)),(u,v,n),color)

def conveyor_guides(specs,name,start,end,width,height=75.,thickness=3.):
    for label,side in (('Left',-1),('Right',1)):
        a=plus(start,(0,side*(width/2),0));b=plus(end,(0,side*(width/2),0))
        specs.append(quad_sheet(name+'_'+label,(a,b,plus(b,(0,0,height)),
                                               plus(a,(0,0,height))),thickness))

def prep_metadata(index,name,description):
    env=PREP_ENVELOPES[index];port=PREP_INTERFACES[index]
    return dict(name=name,description=description,length=env['length'],
                inlet=(0.,0.,port['inlet_height']),
                outlet=(env['length'],0.,port['outlet_height']),
                inlet_width_mm=port['inlet_width'],outlet_width_mm=port['outlet_width'],
                published_envelope_mm={k:env[k] for k in ('length','width','height')},
                source_website_row=env['vendor_row'],source_urls=PREP_SOURCES,
                estimated_interfaces_mm=dict(port),estimated_details=dict(PREP_ESTIMATES),
                dimension_basis='Manufacturer L/W/H; internal geometry and interfaces are estimates, not production drawings.',
                axes='X=flow, Y=belt width, Z=height; ground Z=0',
                product_structure='Equipment / functional subassembly / native CATPart')

def prep_control_box(specs,prefix,x,y,z,width=240.,depth=60.,height=260.):
    specs.append(box(prefix+'_Cabinet',(x,y,z),(width,depth,height),FRAME))
    specs.append(poly(prefix+'_Display',rect(width*.55,height*.25),3,
                      (x+width/2,y-3,z+height*.72),AY,MOTOR))
    for i,color in enumerate((GUARD,(48,155,84),(195,48,40))):
        specs.append(cylinder(prefix+f'_Pushbutton_{i+1}',(x+50+i*65,y,z+55),
                              (x+50+i*65,y-6,z+55),12,color))

def dryer_blower(specs,name,x,deck_z,width,height,est):
    """Top-mounted axial blower connected to an open, tapered full-width air knife."""
    r=est['dryer_fan_radius'];fan0=height-260;fan1=height-145
    nozzle=deck_z+est['dryer_nozzle_clearance'];wide=260.;slit=24.;duct_width=width-20
    # Four walls form an open rectangular transition; the bottom slot stays open.
    for side in (-1,1):
        vertices=((x+side*wide/2,-duct_width/2,fan0),
                  (x+side*wide/2,duct_width/2,fan0),
                  (x+side*slit/2,duct_width/2,nozzle),
                  (x+side*slit/2,-duct_width/2,nozzle))
        specs.append(quad_sheet(name+f'_AirKnife_Wall_{side}',vertices,3,STEEL))
    for side in (-1,1):
        vertices=((x-wide/2,side*duct_width/2,fan0),
                  (x+wide/2,side*duct_width/2,fan0),
                  (x+slit/2,side*duct_width/2,nozzle),
                  (x-slit/2,side*duct_width/2,nozzle))
        specs.append(quad_sheet(name+f'_AirKnife_End_{side}',vertices,3,STEEL))
    specs.append(box(name+'_Plenum_Top',(x-wide/2,-duct_width/2,fan0),
                      (wide,duct_width,3),STEEL,holes=((0,0,r-4),)))
    specs.append(cylinder(name+'_Fan_Casing',(x,0,fan0+3),(x,0,fan1),r,MOTOR,r-4))
    for z in (fan0+3,fan1-6):
        specs.append(cylinder(name+f'_Casing_Flange_{z:g}',(x,0,z),(x,0,z+6),r+12,FRAME,r-4))
    specs.append(cylinder(name+'_Impeller_Hub',(x,0,fan0+45),(x,0,fan1+15),24,FRAME))
    for i in range(8):
        a=i*math.pi/4;u=(math.cos(a),math.sin(a),0.);v=(-math.sin(a),math.cos(a),0.)
        specs.append(poly(name+f'_Impeller_Blade_{i+1}',((20,-10),(r-10,-18),(r-10,18),(20,10)),
                          4,(x,0,fan0+65),(u,v,(0,0,1)),GUARD))
    # Motor spider physically spans the open casing and supports the shaft/motor.
    for a in (0.,math.pi/2):
        u=(math.cos(a),math.sin(a),0.);v=(-math.sin(a),math.cos(a),0.)
        specs.append(poly(name+f'_Motor_Support_{a:g}',rect(2*r,18),8,(x,0,fan1),(u,v,(0,0,1)),FRAME))
    specs.append(cylinder(name+'_Motor_Base',(x,0,fan1+8),(x,0,fan1+20),58,MOTOR))
    specs.append(cylinder(name+'_Motor',(x,0,fan1+20),(x,0,height-15),48,MOTOR))
    specs.append(cylinder(name+'_Motor_Fan_Cover',(x,0,height-15),(x,0,height),53,FRAME))
    for i in range(4):
        z=fan1+35+i*20
        specs.append(cylinder(name+f'_Motor_Fin_{i+1}',(x,0,z),(x,0,z+4),53,MOTOR))
    # Sliding sleeves on vertical posts indicate a height-adjustable nozzle mount.
    for side in (-1,1):
        y=side*(width/2+50)
        specs.append(tube(name+f'_Adjustable_Stand_{side}',(x,y,960),(x,y,fan0+35),30,30,3))
        specs.append(tube(name+f'_Slide_Sleeve_{side}',(x,y,fan0-25),(x,y,fan0+20),40,40,3,GUARD))
        specs.append(tube(name+f'_Plenum_Bracket_{side}',(x,side*duct_width/2,fan0-8),
                          (x,y,fan0-8),20,20,2,FRAME))

def prep_tapered_chute(specs,name,start,end,width0,width1,wall_h=75.,thickness=3.):
    left0=plus(start,(0,-width0/2,0));right0=plus(start,(0,width0/2,0))
    left1=plus(end,(0,-width1/2,0));right1=plus(end,(0,width1/2,0))
    specs.append(quad_sheet(name+'_Floor',(left0,left1,right1,right0),thickness))
    for label,a,b in (('Left',left0,left1),('Right',right0,right1)):
        specs.append(quad_sheet(name+'_'+label,(a,b,plus(b,(0,0,wall_h)),
                                                plus(a,(0,0,wall_h))),thickness))

def source_station6():
    """06 hot-water blancher: insulated pan, immersed belt and rising outfeed."""
    s=AssemblySpecs();e=PREP_ESTIMATES;d=PREP_ENVELOPES[6];p=PREP_INTERFACES[6]
    L,W,H=d['length'],d['width'],d['height'];bw=p['outlet_width']
    bottom=e['blancher_floor'];rim=e['blancher_rim'];level=e['blancher_belt_level']
    tank0=60.;tank1=L-230;wet_half=W/2-95;t=e['wet_sheet']
    drain_x=L*.44
    with s.section('Support Frame'):
        frame(s,L,W-180,bottom,e['frame_member'])
        for side in (-1,1):
            s.append(tube(f'06_Central_Leg_{side}',(L/2,side*(W/2-90),30),
                          (L/2,side*(W/2-90),bottom),50,50,3))
            s.append(box(f'06_Central_Foot_{side}',(L/2-55,side*(W/2-90)-55,12),(110,110,18),FRAME))
    with s.section('Process Tank'):
        s.append(box('06_Wet_Pan_Floor',(tank0,-wet_half,bottom),(tank1-tank0,2*wet_half,t),
                     holes=((drain_x-(tank0+tank1)/2,0,28),)))
        for side in (-1,1):
            y=-wet_half if side<0 else wet_half-t
            s.append(box(f'06_Wet_Pan_Side_{side}',(tank0,y,bottom),(tank1-tank0,t,rim-bottom)))
            y=-W/2+35 if side<0 else W/2-38
            s.append(box(f'06_Insulated_Outer_Skin_{side}',(tank0,y,bottom-25),
                         (tank1-tank0,3,rim-bottom+25)))
            s.append(box(f'06_Upper_Rim_{side}',(tank0,-W/2+35 if side<0 else wet_half-t,rim-5),
                         (tank1-tank0,65,5),ROLLER))
        s.append(box('06_Inlet_End_Wall',(tank0,-wet_half,bottom),(t,2*wet_half,rim-bottom)))
        gate=bw/2+55;gate_z=1080.
        section=((-wet_half,bottom),(wet_half,bottom),(wet_half,rim),(gate,rim),
                 (gate,gate_z),(-gate,gate_z),(-gate,rim),(-wet_half,rim))
        s.append(poly('06_Outlet_End_With_Belt_Clearance',section,t,(tank1-t,0,0),AX))
    with s.section('Infeed'):
        prep_tapered_chute(s,'06_Infeed',(0,0,p['inlet_height']),(500,0,level+10),
                      p['inlet_width'],bw,75)
    with s.section('Immersion Conveyor'):
        fryer_conveyor(s,'06_Immersion_Belt',(500,0,level),(3040,0,level),bw,35,e,W,True)
        conveyor_guides(s,'06_Bath_Guide',(500,0,level),(3100,0,level),bw,200)
        # A light upper hold-down belt prevents buoyant slices leaving the lane.
        fryer_conveyor(s,'06_Hold_Down_Belt',(900,0,level+135),(2840,0,level+135),
                       bw-20,30,e,W,True)
        for x in (500,900,2840,3040):
            for side in (-1,1):
                s.append(tube(f'06_Belt_Bearing_Bracket_{x}_{side}',
                              (x,side*(bw/2+35),level-60),
                              (x,side*(wet_half-5),level-60),35,45,3))
    with s.section('Outfeed'):
        start=(3180.,0.,level);end=(L-130,0.,p['outlet_height']+5)
        fryer_mesh(s,'06_Transfer_Bridge',(3040,0,level),start,bw,e,ROLLER)
        fryer_conveyor(s,'06_Discharge_Belt',start,end,bw,35,e,W,True)
        conveyor_guides(s,'06_Discharge_Guide',start,end,bw,70)
        prep_tapered_chute(s,'06_Discharge_Lip',end,(L,0,p['outlet_height']),bw,bw,70)
        direction=unit(vec(start,end));normal=unit(cross(direction,(0,1,0)))
        for distance in range(180,int(norm(vec(start,end)))-80,180):
            pos=plus(start,scale(direction,distance))
            s.append(poly(f'06_Discharge_Cleat_{distance}',rect(10,bw-30),18,pos,
                          (direction,(0,1,0),normal),BELT))
        for side in (-1,1):
            s.append(tube(f'06_Discharge_Support_{side}',(L-130,side*(bw/2+35),bottom),
                          (L-130,side*(bw/2+35),end[2]-60),45,45,3))
    with s.section('Covers'):
        hood0=300.;hood1=3000.;zt=e['blancher_hood_top'];panel=(hood1-hood0)/3
        for i in range(3):
            x=hood0+i*panel
            s.append(box(f'06_Removable_Lid_{i+1}',(x,-wet_half,zt-3),(panel-4,2*wet_half,3)))
            for side in (-1,1):
                s.append(box(f'06_Lid_Skirt_{i+1}_{side}',(x,side*wet_half,1145),
                             (panel-4,3,zt-1145)))
            for hx in (x+panel/2-70,x+panel/2+70):
                s.append(cylinder(f'06_Lid_Handle_Stem_{i}_{hx:g}',(hx,0,zt),(hx,0,H-8),8,FRAME))
            s.append(cylinder(f'06_Lid_Handle_{i+1}',(x+panel/2-70,0,H-8),
                              (x+panel/2+70,0,H-8),8,FRAME))
            s.append(tube(f'06_Lid_Fixed_Support_{i}',(x+20,-wet_half,rim),
                          (x+20,-wet_half,zt-3),20,20,2))
            s.append(tube(f'06_Lid_Fixed_Support_Right_{i}',(x+20,wet_half,rim),
                          (x+20,wet_half,zt-3),20,20,2))
    with s.section('Heating and Water Circuit'):
        # Simplified electric immersion bank; power/thermal design is not inferred.
        for i,x in enumerate((1050.,1750.,2450.),1):
            s.append(box(f'06_Heater_Terminal_{i}',(x-100,-W/2+5,bottom+40),(200,85,100),MOTOR))
            for j in range(3):
                s.append(cylinder(f'06_Immersion_Element_{i}_{j}',(x-60+j*60,-wet_half-10,bottom+85),
                                  (x-60+j*60,wet_half-40,bottom+85),9,GUARD))
        s.append(cylinder('06_Drain_Nozzle',(drain_x,0,bottom-150),(drain_x,0,bottom+t),28,STEEL,24))
        s.append(cylinder('06_Drain_Flange',(drain_x,0,bottom-150),(drain_x,0,bottom-138),48,FRAME,24))
        s.append(cylinder('06_Drain_Valve_Body',(drain_x,0,bottom-125),(drain_x,0,bottom-70),38,MOTOR,24))
        s.append(box('06_Drain_Valve_Lever',(drain_x-8,-120,bottom-100),(16,130,8),GUARD))
        s.append(cylinder('06_Fill_Pipe',(650,wet_half-50,rim+25),(650,wet_half-50,rim-180),18,MOTOR,14))
        s.append(tube('06_Fill_Pipe_Clip',(650,wet_half-50,rim-50),(650,wet_half,rim-50),20,20,2))
    with s.section('Electrical Controls'):
        prep_control_box(s,'06_Control',L*.72,-W/2+10,710)
    meta=prep_metadata(6,'06_Continuous_Blancher','Hot-water blancher with immersion mesh conveyor, covers and inclined draining outfeed.')
    meta['water_level_reference_mm']=e['blancher_water_level']
    meta['inlet_dependency']='Station 5 interface not supplied; inlet is an adjustable estimate.'
    return s,meta

def source_station7():
    """07 vibratory dewaterer, with a moving perforated deck on leaf springs."""
    s=AssemblySpecs();e=PREP_ESTIMATES;d=PREP_ENVELOPES[7];p=PREP_INTERFACES[7]
    L,W,H=d['length'],d['width'],d['height'];bw=p['inlet_width']
    z0=p['inlet_height'];z1=p['outlet_height']
    def deck_z(x):return z0+(z1-z0)*x/L
    with s.section('Support Frame'):
        frame(s,L,W-240,e['dewater_frame_top'],50)
    with s.section('Vibrating Deck'):
        fryer_mesh(s,'07_Perforated_Screen',(80,0,deck_z(80)),(L-100,0,deck_z(L-100)),bw,e,ROLLER)
        conveyor_guides(s,'07_Tray_Sidewall',(80,0,deck_z(80)),(L-100,0,deck_z(L-100)),bw,80)
        for side in (-1,1):
            s.append(tube(f'07_Moving_Longitudinal_Beam_{side}',(80,side*380,deck_z(80)-25),
                          (L-100,side*380,deck_z(L-100)-25),40,40,3))
        for x in (420.,900.,1470.):
            s.append(tube(f'07_Moving_Crossbeam_{x:g}',(x,-380,deck_z(x)-25),
                          (x,380,deck_z(x)-25),40,40,3))
    with s.section('Infeed'):
        prep_tapered_chute(s,'07_Infeed',(0,0,z0),(80,0,deck_z(80)),bw,bw,80)
    with s.section('Outfeed'):
        prep_tapered_chute(s,'07_Outfeed',(L-100,0,deck_z(L-100)),(L,0,z1),bw,p['outlet_width'],75)
    with s.section('Suspension'):
        # Inclined spring leaves, fixed lower clamps, moving upper clamps.
        # The deflection and oscillation are not simulated by this static model.
        for i,x in enumerate((350.,1400.),1):
            upper=x+70;bottom=e['dewater_frame_top'];top=deck_z(upper)-45
            for side in (-1,1):
                y=side*380;prefix=f'07_Spring_Pack_{i}_{side}'
                s.append(box(prefix+'_Lower_Clamp',(x-25,y-45,bottom-5),(90,90,12),FRAME,
                             holes=((-28,-28,5),(28,-28,5),(28,28,5),(-28,28,5))))
                s.append(box(prefix+'_Upper_Clamp',(upper-25,y-45,top-5),(90,90,12),FRAME))
                for j in range(e['leaf_spring_layers']):
                    shift=j*9.
                    s.append(plate_between(prefix+f'_Leaf_{j+1}',
                                           (x+shift,y,bottom+7),(upper+shift,y,top+5),
                                           60,e['leaf_spring_thickness'],GUARD))
                s.append(cylinder(prefix+'_Lower_Clamp_Pin',(x+25,y-52,bottom+4),
                                  (x+25,y+52,bottom+4),6,ROLLER))
                s.append(cylinder(prefix+'_Upper_Clamp_Pin',(upper+25,y-52,top+2),
                                  (upper+25,y+52,top+2),6,ROLLER))
    with s.section('Exciter Drive'):
        # Pair of counter-rotating vibration motors, mounted to the moving tray.
        for i,x in enumerate((760.,1090.),1):
            z=1040.;prefix=f'07_Vibration_Motor_{i}';red=(174,67,49)
            s.append(cylinder(prefix+'_Housing',(x,-110,z),(x,110,z),65,red))
            s.append(cylinder(prefix+'_Rotor_Shaft',(x,-175,z),(x,175,z),16,FRAME))
            for side in (-1,1):
                y=side*120
                # Eccentric mass is visible as an offset pad behind an end guard.
                s.append(cylinder(prefix+f'_Eccentric_Weight_{side}',(x+20,y,z-18),
                                  (x+20,y+side*18,z-18),34,GUARD))
                s.append(cylinder(prefix+f'_End_Guard_{side}',(x,side*145,z),
                                  (x,side*180,z),74,red,69))
                s.append(cylinder(prefix+f'_End_Cap_{side}',(x,side*180,z),
                                  (x,side*184,z),74,red))
            for j in range(5):
                y=-88+j*44
                s.append(cylinder(prefix+f'_Fin_{j}',(x,y,z),(x,y+4,z),70,red))
            s.append(box(prefix+'_Mounting_Plate',(x-95,-140,z+66),(190,280,12),FRAME))
            for side in (-1,1):
                s.append(tube(prefix+f'_Mount_Stay_{side}',(x,side*110,z+78),
                              (x,side*110,deck_z(x)-20),35,35,3))
            s.append(box(prefix+'_Terminal_Box',(x+58,-40,z-25),(42,80,50),red))
    with s.section('Drainage'):
        drain_x=L*.65;z=e['drain_pan_floor'];pan0=100.;pan1=L-120;pw=bw+80
        s.append(box('07_Drain_Pan_Floor',(pan0,-pw/2,z),(pan1-pan0,pw,3),
                     holes=((drain_x-(pan0+pan1)/2,0,25),)))
        for side in (-1,1):
            s.append(box(f'07_Drain_Pan_Side_{side}',(pan0,side*pw/2,z),(pan1-pan0,3,40)))
        for x in (pan0,pan1-3):
            s.append(box(f'07_Drain_Pan_End_{x:g}',(x,-pw/2,z),(3,pw,40)))
        s.append(cylinder('07_Drain_Outlet',(drain_x,0,z-140),(drain_x,0,z+3),25,STEEL,21))
        for x in (300.,L-300):
            s.append(tube(f'07_Drain_Pan_Support_{x:g}',(x,-380,z-15),(x,380,z-15),30,30,3))
    with s.section('Electrical Controls'):
        prep_control_box(s,'07_Control',200,-W/2+10,470)
    meta=prep_metadata(7,'07_Vibratory_Dewaterer','Perforated vibrating tray, leaf-spring suspension, twin exciters and separate drain pan.')
    meta['suspension_note']='Leaf-spring geometry is an inferred static arrangement, not a dynamic spring-rate calculation.'
    return s,meta

def source_station8():
    """08 air dryer: three short cascade decks, six blowers, final lift and taper.

    Cascade positions are an inferred layout within the catalogue envelope.
    They are not a claim that the manufacturer supplied this internal drawing.
    """
    s=AssemblySpecs();e=PREP_ESTIMATES;d=PREP_ENVELOPES[8];p=PREP_INTERFACES[8]
    L,W,H=d['length'],d['width'],d['height'];bw=p['inlet_width']
    z0=p['inlet_height'];drop=e['dryer_deck_drop']
    decks=(((120.,0.,z0),(940.,0.,z0)),
           ((1120.,0.,z0-drop),(1940.,0.,z0-drop)),
           ((2120.,0.,z0-2*drop),(2780.,0.,z0-2*drop)))
    with s.section('Support Frame'):
        frame(s,L,W-180,960,50)
        for side in (-1,1):
            s.append(tube(f'08_Central_Leg_{side}',(L/2,side*410,30),(L/2,side*410,960),50,50,3))
            s.append(box(f'08_Central_Foot_{side}',(L/2-55,side*410-55,12),(110,110,18),FRAME))
    with s.section('Infeed'):
        prep_tapered_chute(s,'08_Infeed',(0,0,z0),decks[0][0],bw,bw,75)
    with s.section('Drying Conveyors'):
        for i,(start,end) in enumerate(decks,1):
            fryer_conveyor(s,f'08_Drying_Deck_{i}',start,end,bw,35,e,W,True)
            conveyor_guides(s,f'08_Deck_Guide_{i}',start,end,bw,75)
            for x in (start[0],end[0]):
                for side in (-1,1):
                    s.append(tube(f'08_Deck_{i}_Bearing_Stand_{x:g}_{side}',
                                  (x,side*(bw/2+35),960),(x,side*(bw/2+35),start[2]-50),35,35,3))
            if i<len(decks):
                fryer_mesh(s,f'08_Cascade_Transfer_{i}',end,decks[i][0],bw,e,ROLLER)
                conveyor_guides(s,f'08_Cascade_Guide_{i}',end,decks[i][0],bw,75)
    with s.section('Outfeed'):
        start=(2850.,0.,z0-2*drop);end=(L-320,0.,p['outlet_height']+10)
        fryer_mesh(s,'08_Lift_Transfer',decks[-1][1],start,bw,e,ROLLER)
        fryer_conveyor(s,'08_Discharge_Lift',start,end,bw,35,e,W,True)
        conveyor_guides(s,'08_Lift_Guide',start,end,bw,75)
        direction=unit(vec(start,end));normal=unit(cross(direction,(0,1,0)))
        for distance in range(80,int(norm(vec(start,end)))-30,80):
            pos=plus(start,scale(direction,distance))
            s.append(poly(f'08_Lift_Cleat_{distance}',rect(8,bw-30),e['dryer_lift_cleat_height'],
                          pos,(direction,(0,1,0),normal),BELT))
        prep_tapered_chute(s,'08_Fryer_Infeed_Transition',end,(L,0,p['outlet_height']),bw,p['outlet_width'],75)
        for side in (-1,1):
            for x,z in ((start[0],start[2]),(end[0],end[2])):
                s.append(tube(f'08_Lift_Stand_{x:g}_{side}',(x,side*(bw/2+35),960),
                              (x,side*(bw/2+35),z-55),35,35,3))
    with s.section('Air Handling System'):
        fan_positions=((420.,z0),(820.,z0),(1400.,z0-drop),
                       (1800.,z0-drop),(2320.,z0-2*drop),(2620.,z0-2*drop))
        for i,(x,z) in enumerate(fan_positions,1):
            dryer_blower(s,f'08_Blower_{i}',x,z,bw,H,e)
    with s.section('Drainage and Guards'):
        z=875.;pan0=120.;pan1=L-360;pw=bw+60;drain_x=2700.
        s.append(box('08_Drip_Tray_Floor',(pan0,-pw/2,z),(pan1-pan0,pw,3),
                     holes=((drain_x-(pan0+pan1)/2,0,22),)))
        for side in (-1,1):
            s.append(box(f'08_Drip_Tray_Side_{side}',(pan0,side*pw/2,z),(pan1-pan0,3,45)))
            s.append(box(f'08_Lower_Side_Guard_{side}',(120,side*455,965),(L-240,3,65),STEEL))
        for x in (pan0,pan1-3):
            s.append(box(f'08_Drip_Tray_End_{x:g}',(x,-pw/2,z),(3,pw,45)))
        s.append(cylinder('08_Drain_Connection',(drain_x,0,z-130),(drain_x,0,z+3),22,STEEL,18))
    with s.section('Electrical Controls'):
        prep_control_box(s,'08_Control',150,-W/2+10,580)
    meta=prep_metadata(8,'08_Air_Dryer','Cascade mesh-belt air dryer with six fan/air-knife units, drainage and tapered fryer outfeed.')
    meta['internal_layout_note']='Estimated three sequential cascade decks, not a manufacturer-confirmed multi-pass layout.'
    meta['downstream_match']='09 PC4 inlet: 1190 mm high, 510 mm wide. Other fryer models require adjusted interfaces.'
    return s,meta

def source_station9(model='PC4',hood_lift=0.,hood_transparent=False):
    """09: continuous fryer based on the PC-series general arrangement drawing.

    Datum: floor Z=0, inlet X=0, belt centre Y=0, product flow along +X.
    Published inlet/outlet heights refer to product contact surfaces.
    Equipment 1-8 is neither opened nor rebuilt by this function.
    """
    d=dict(FRYER_MODELS[model]);e=dict(FRYER_ESTIMATES)
    if not 0 <= hood_lift <= e['hood_max_lift']:
        raise ValueError(f"hood_lift must be 0..{e['hood_max_lift']} mm")
    A,B,C,D,E=(d[k] for k in ('A','B','C','D','E'))
    s=[];pan0=A*e['pan_start_fraction'];pan1=A*e['pan_end_fraction']
    pan_width=B-e['pan_width_margin'];half=pan_width/2
    t=e['wet_wall_thickness'];ct=e['cladding_thickness'];gap=e['insulation_gap']
    carrier_z=min(D-e['carrier_below_feed'],E-e['carrier_below_outlet'])
    floor_z=min(D-e['pan_floor_below_feed'],carrier_z-e['pan_floor_below_carrier'])
    rim_z=D-e['pan_rim_below_feed'];wet_half=half-gap
    oil_z=min(D-e['oil_level_below_feed'],E-e['oil_level_below_outlet'])
    discharge0=A*e['discharge_start_fraction']
    carrier0=A*e['feed_end_fraction']
    carrier1=min(A*e['carrier_end_fraction'],discharge0-180)
    port_xs=(A*.18,A*.64)

    # Closed pan with real Pocket oil ports. Only the product outlet is notched.
    floor_center=(pan0+pan1)/2
    ports=tuple((x-floor_center,0,e['oil_port_radius']) for x in port_xs)
    s.append(box('09_Oil_Pan_Floor_With_Ports',(pan0,-wet_half,floor_z),
                 (pan1-pan0,2*wet_half,t),STEEL,holes=ports))
    for side in (-1,1):
        y=-wet_half if side<0 else wet_half-t
        s.append(box(f'09_Oil_Pan_Wet_Wall_{side}',(pan0,y,floor_z),
                     (pan1-pan0,t,rim_z-floor_z),STEEL))
        y=-half if side<0 else half-ct
        s.append(box(f'09_Insulation_Outer_Cladding_{side}',(pan0,y,floor_z-30),
                     (pan1-pan0,ct,rim_z-floor_z+30),STEEL))
        s.append(box(f'09_Pan_Top_Fold_{side}',(pan0,-half if side<0 else wet_half-t,rim_z-t),
                     (pan1-pan0,gap+t,t),ROLLER))
    s.append(box('09_Oil_Pan_Inlet_End',(pan0,-wet_half,floor_z),
                 (t,2*wet_half,rim_z-floor_z),STEEL))
    gate_half=C/2+65
    gate_bottom=E-2*e['discharge_drum_radius']-20
    end_profile=((-wet_half,floor_z),(wet_half,floor_z),(wet_half,rim_z),
                 (gate_half,rim_z),(gate_half,gate_bottom),(-gate_half,gate_bottom),
                 (-gate_half,rim_z),(-wet_half,rim_z))
    s.append(poly('09_Pan_Outlet_End_With_Belt_Opening',end_profile,t,(pan1-t,0,0),AX))

    # Pan support portals and a final discharge stand, with drilled feet.
    frame_y=half-35;member=e['frame_tube'];support_z=floor_z-member/2
    support_xs=(A*.12,A*.48,A*.84,A-e['discharge_end_margin'])
    for i,x in enumerate(support_xs,1):
        for side in (-1,1):
            y=side*frame_y
            s.append(tube(f'09_Frame_Portal_{i}_Leg_{side}',(x,y,35),(x,y,support_z),
                          member,member,e['frame_wall']))
            s.append(box(f'09_Foot_{i}_{side}',(x-70,y-70,15),(140,140,18),FRAME,
                         holes=((-48,-48,7),(48,-48,7),(48,48,7),(-48,48,7))))
            s.append(cylinder(f'09_Leveling_Stem_{i}_{side}',(x,y,0),(x,y,50),18,RUBBER))
        s.append(tube(f'09_Frame_Portal_{i}_Crossmember',(x,-frame_y,support_z),
                      (x,frame_y,support_z),member,member,e['frame_wall']))
    for side in (-1,1):
        for z in (240,support_z):
            s.append(tube(f'09_Frame_Longitudinal_{side}_{z:g}',(support_xs[0],side*frame_y,z),
                          (support_xs[-1],side*frame_y,z),member,member,e['frame_wall']))

    # Feed slide -> oil bath -> draining incline -> downstream lip.
    chute(s,'09_Infeed_Slide',(0,0,D),(carrier0,0,carrier_z+10),C,130,4)
    fryer_conveyor(s,'09_Lower_Process_Belt',(carrier0,0,carrier_z),
                   (carrier1,0,carrier_z),C,e['carrier_drum_radius'],e,B,True)
    fryer_mesh(s,'09_Transfer_Bridge',(carrier1,0,carrier_z),
               (discharge0,0,carrier_z+8),C,e,ROLLER)
    out_start=(discharge0,0,carrier_z+8)
    out_end=(A-e['discharge_end_margin'],0,E+e['discharge_tip_above_E'])
    fryer_conveyor(s,'09_Draining_Discharge',out_start,out_end,C,
                   e['discharge_drum_radius'],e,B,True)
    chute(s,'09_Discharge_Lip',out_end,(A,0,E),C,100,3)
    # Side guides leave the underside of the draining belt open.
    for side in (-1,1):
        points=((out_start[0],-out_start[2]),(out_end[0],-out_end[2]),
                (out_end[0],-out_end[2]-130),(out_start[0],-out_start[2]-130))
        s.append(poly(f'09_Discharge_Side_Guide_{side}',points,3,
                      (0,side*(C/2+12),0),AY))
        s.append(box(f'09_Bath_Belt_Side_Guide_{side}',
                     (carrier0,side*(C/2+12),carrier_z-5),
                     (carrier1-carrier0,3,180),STEEL))

    sub0=A*e['submerger_start_fraction'];sub1=min(A*e['submerger_end_fraction'],carrier1-75)
    sub_r=e['submerger_drum_radius']
    # Lower tangent of upper conveyor holds slices below the oil surface.
    sub_top=carrier_z+e['submerger_lower_above_carrier']+2*sub_r-e['mesh_thickness']
    fryer_conveyor(s,'09_Upper_Submerger',(sub0,0,sub_top),(sub1,0,sub_top),
                   C-20,sub_r,e,B,True)
    for i in range(e['paddle_count']):
        x=carrier0+(sub0-carrier0)*(i+1)/(e['paddle_count']+1)
        z=carrier_z+e['paddle_radius']+20
        name=f'09_Metering_Paddle_{i+1}'
        fryer_paddle(s,name,x,z,C-30,e['paddle_radius'],e['paddle_thickness'],i*math.pi/12)
        fryer_drive(s,name+'_Drive',(x,0,z),C-30,B)

    # Bearing carriers join each conveyor to the side walls, outside the belt lane.
    carrier_supports=((carrier0,carrier_z-e['carrier_drum_radius']),
                      (carrier1,carrier_z-e['carrier_drum_radius']),
                      (out_start[0],out_start[2]-e['discharge_drum_radius']),
                      (out_end[0],out_end[2]-e['discharge_drum_radius']),
                      (sub0,sub_top-sub_r),(sub1,sub_top-sub_r))
    for i,(x,z) in enumerate(carrier_supports,1):
        for side in (-1,1):
            s.append(tube(f'09_Conveyor_Mount_{i}_{side}',
                          (x,side*(C/2+35),z-26),(x,side*(half-12),z-26),30,40,3))
    for side in (-1,1):
        s.append(tube(f'09_Discharge_Stand_Riser_{side}',
                      (out_end[0],side*frame_y,support_z),
                      (out_end[0],side*frame_y,out_end[2]-e['discharge_drum_radius']-26),
                      member,member,e['frame_wall']))

    # Liftable gabled hood with thin walls. Default pose is closed.
    hood_first=len(s)
    hx0=A*e['hood_start_fraction'];hx1=A*e['hood_end_fraction'];hh=half+10
    hb=rim_z+e['hood_bottom_above_rim'];he=D+e['hood_eave_above_feed']
    hr=D+e['hood_ridge_above_feed'];ht=e['hood_thickness']
    stack_x=A*e['stack_fraction'];plenum=e['stack_plenum_width'];ph=plenum/2
    for side in (-1,1):
        y=-hh if side<0 else hh-ht
        s.append(box(f'09_Hood_Side_{side}',(hx0,y,hb),(hx1-hx0,ht,he-hb),STEEL))
        s.append(tube(f'09_Hood_Base_Rail_{side}',(hx0,side*(hh-10),hb),
                      (hx1,side*(hh-10),hb),25,25,3,STEEL))
        # Centre roof strips leave an actual square plenum aperture.
        for j,(x0,x1,inner_y) in enumerate(((hx0,stack_x-ph,0),
                                          (stack_x-ph,stack_x+ph,ph),
                                          (stack_x+ph,hx1,0)),1):
            inner_z=hr-(hr-he)*inner_y/hh
            section=((side*hh,he),(side*inner_y,inner_z),
                     (side*inner_y,inner_z-ht),(side*hh,he-ht))
            s.append(poly(f'09_Hood_Roof_{side}_{j}',section,x1-x0,(x0,0,0),AX))
    end=((-hh,hb),(hh,hb),(hh,he),(0,hr),(-hh,he))
    for i,x in enumerate((hx0,hx1-ht),1):
        s.append(poly(f'09_Hood_End_{i}',end,ht,(x,0,0),AX))
    # Hollow exhaust: roof opening -> square plenum -> round tube.
    stack_base=hr-(hr-he)*ph/hh
    stack_cap=hr+260
    s.append(poly('09_Exhaust_Square_Plenum',rect(plenum,plenum),stack_cap-stack_base,
                  (stack_x,0,stack_base),loops=(tuple(reversed(rect(plenum-2*ht,plenum-2*ht))),)))
    sr=e['stack_radius'];sw=e['stack_wall']
    s.append(box('09_Exhaust_Transition_Cap',(stack_x-ph,-ph,stack_cap),
                 (plenum,plenum,ht),STEEL,holes=((0,0,sr-sw),)))
    s.append(cylinder('09_Exhaust_Hollow_Stack',(stack_x,0,stack_cap+ht),
                      (stack_x,0,hr+e['stack_top_above_ridge']),sr,STEEL,sr-sw))
    for z in (stack_cap+ht,hr+e['stack_top_above_ridge']-12):
        s.append(cylinder(f'09_Exhaust_Flange_{z:g}',(stack_x,0,z),(stack_x,0,z+12),
                          sr+20,FRAME,sr-sw))
    for spec in s[hood_first:]:
        spec['origin']=plus(spec['origin'],(0,0,hood_lift))
        if hood_transparent:spec['transparency']=e['hood_transparency']

    # Four simplified screw-jack cores; travelling nuts follow the hood lift.
    for i,x in enumerate((A*.20,A*.72),1):
        for side in (-1,1):
            y=side*(half+35);name=f'09_Hood_Jack_{i}_{side}'
            s.append(box(name+'_Base',(x-65,y-55,floor_z-160),(130,110,110),MOTOR))
            s.append(cylinder(name+'_Lower_Column',(x,y,floor_z-50),(x,y,hb-100),28,FRAME))
            s.append(cylinder(name+'_Screw_Core',(x,y,hb-100),
                              (x,y,hb+e['hood_max_lift']+200),14,ROLLER))
            moving_z=hb+120+hood_lift
            s.append(cylinder(name+'_Travelling_Nut',(x,y,moving_z-35),(x,y,moving_z+35),33,GUARD))
            s.append(tube(name+'_Hood_Bracket',(x,side*(hh-10),moving_z),
                          (x,y,moving_z),35,35,3,FRAME))
            s.append(tube(name+'_Frame_Bracket',(x,side*frame_y,floor_z-105),
                          (x,y,floor_z-105),40,50,4,FRAME))
    # Ports connect to floor Pocket holes. External heater/filter skid is not
    # dimensioned in the drawing; leave interfaces instead of inventing its size.
    for i,x in enumerate(port_xs,1):
        pr=e['oil_port_radius'];pw=e['oil_port_wall'];z=floor_z-170
        s.append(cylinder(f'09_Oil_Connection_{i}',(x,0,z),(x,0,floor_z+t),pr,STEEL,pr-pw))
        s.append(cylinder(f'09_Oil_Connection_Flange_{i}',(x,0,z),(x,0,z+12),pr+25,MOTOR,pr-pw))

    s.append(box('09_Control_Enclosure',(A*.10,-B/2,floor_z+35),(330,70,300),FRAME))
    s.append(poly('09_Control_Display',rect(160,100),4,
                  (A*.10+165,-B/2,floor_z+220),AY,MOTOR))
    return s,dict(
        name=f'09_Potato_Chip_Fryer_{model}',
        description=f'PC-series continuous fryer {model}: native constrained profiles, open mesh conveyors and liftable hood.',
        inlet=(0,0,D),outlet=(A,0,E),length=A,
        axes='X=product flow, Y=belt width, Z=height; ground Z=0',
        source_urls=FRYER_SOURCES,published_dimensions_mm=d,
        published_dimensions_note='PDF p.2 metric values, rounded by manufacturer; A/B/C/D/E only.',
        estimated_geometry_mm_and_fractions=e,
        estimated_geometry_note='Wall, frame, pan, hood, exhaust and internal mechanism geometry are inferred; mesh pitch is visualization only.',
        oil_level_reference_mm=oil_z,hood_lift_mm=hood_lift,hood_transparent=hood_transparent,
        external_interfaces='Two oil ports below pan; external heater/filter skid omitted because no dimensioned drawing was supplied.',
        source_priority='Heat and Control plan/side drawing first; Baixin functional reference only.',
        source_model_not_as_built=True)

# ---- Revision 10: physical joints and equipment corrections ----
def remove_named(specs,*tokens):
    specs[:]=[q for q in specs if not any(t in q['name'] for t in tokens)]

def tagged(spec,part_type=None,family=None,category=None):
    if part_type:spec['part_type']=part_type
    if family:spec['family']=family
    if category:spec['category']=category
    return spec

def bolted_support(specs,name,start,end,w=40.,h=None):
    """Profile plus drilled end plates. End faces meet the stated contacts."""
    if norm(vec(start,end))<1e-6:return
    member=tube(name+'_Profile',start,end,w,h or w,3,STEEL)
    specs.append(tagged(member,'Profile',name.split('_')[0]+'_Supports','Frame'))
    u,v,n=member['axes']
    for i,p in enumerate((start,plus(end,scale(n,-6))),1):
        holes=tuple((a*w*.65,b*w*.65,4.5) for a in (-1,1) for b in (-1,1))
        specs.append(tagged(poly(name+f'_End_Bracket_{i}',rect(w*1.8,w*1.8),6,p,(u,v,n),STEEL,holes=holes),'Bracket','Support_End_Brackets','Frame'))
        for j,(a,b,r) in enumerate(holes):
            q=plus(p,plus(scale(u,a),scale(v,b)))
            specs.append(tagged(cylinder(name+f'_Bolt_{i}_{j}',q,plus(q,scale(n,10)),4,FRAME),'Fastener','Support_Bolts','Frame'))

def angle_joint(specs,name,origin,axes=I,size=60.,t=6.,width=45.):
    # A single L-shaped closed contour. Two mating faces are real pad faces.
    points=((0,0),(size,0),(size,t),(t,t),(t,size),(0,size))
    specs.append(tagged(poly(name,points,width,origin,axes,STEEL),'Bracket','Angle_Brackets','Frame'))
    u,v,n=axes
    for label,a,b,d in (('Horizontal',size*.65,t,n),('Vertical',t,size*.65,n)):
        q=plus(origin,plus(scale(u,a),plus(scale(v,b),scale(n,width/2))))
        # Clamp heads are on the mating faces, rather than floating beside them.
        direction=v if label=='Horizontal' else u
        specs.append(tagged(cylinder(name+'_'+label+'_Bolt',q,plus(q,scale(direction,8)),5,FRAME),'Fastener','Joint_Bolts','Frame'))

def flange_pipe(specs,name,start,end,r=40.,wall=4.):
    pipe=cylinder(name+'_Nozzle',start,end,r,STEEL,r-wall)
    specs.append(tagged(pipe,'Pipe',name,'Internal'))
    u,v,n=pipe['axes'];holes=tuple(((r+13)*math.cos(i*math.pi/2),(r+13)*math.sin(i*math.pi/2),5.) for i in range(4))
    flange=cylinder(name+'_Flange',start,plus(start,scale(n,12)),r+25,STEEL,r-wall)
    flange['holes']=holes
    specs.append(tagged(flange,'Pipe',name,'Internal'))
    specs.append(tagged(cylinder(name+'_Gasket',plus(start,scale(n,-2)),start,r+22,RUBBER,r-wall),'Seal',name,'Internal'))

def pipe_chamber(specs,name,center,size,ports):
    """Sealed rectangular service elbow/tee. Each port is a real bore.
    ports maps face (axis, sign) to hole radius; pipes meet the outer faces.
    Flat ported faces avoid solid walls blocking intersecting hollow tubes.
    """
    t=4.;half=size/2
    for axis in range(3):
        for side in (-1,1):
            n=tuple(side if i==axis else 0. for i in range(3))
            ref=(0,0,1) if axis!=2 else (0,1,0)
            u=unit(cross(ref,n));v=cross(n,u)
            origin=plus(center,scale(n,half-t))
            r=ports.get((axis,side));holes=((0.,0.,r),) if r else ()
            specs.append(tagged(poly(name+f'_Face_{axis}_{side}',rect(size,size),t,origin,(u,v,n),STEEL,holes=holes),'Pipe',name,'Internal'))

def bearing_housing(specs,name,start,end,shaft_radius,outer_radius=None):
    r=outer_radius or shaft_radius+32
    n=unit(vec(start,end));length=norm(vec(start,end))
    specs.append(tagged(cylinder(name+'_Cylindrical_Housing',start,end,r,STEEL,shaft_radius+13),'Bearing',name,'Internal'))
    a=plus(start,scale(n,5));b=plus(end,scale(n,-5))
    specs.append(tagged(cylinder(name+'_Bearing_Race',a,b,shaft_radius+13,ROLLER,shaft_radius+.6),'Bearing',name,'Internal'))
    for i,p in enumerate((start,plus(end,scale(n,-5)))):
        specs.append(tagged(cylinder(name+f'_Shaft_Seal_{i}',p,plus(p,scale(n,5)),shaft_radius+13,RUBBER,shaft_radius+.3),'Seal',name,'Internal'))
    f=cylinder(name+'_Bolted_Flange',start,plus(start,scale(n,8)),r+22,STEEL,shaft_radius+13)
    f['holes']=tuple(((r+11)*math.cos(a),(r+11)*math.sin(a),4.5) for a in (0,math.pi/2,math.pi,3*math.pi/2))
    specs.append(tagged(f,'Bearing',name,'Internal'))

def bearing_spider(specs,name,x,z,shaft_radius,reach):
    """Three-web mounting plate surrounding an enclosed cylindrical bearing."""
    r=shaft_radius+45;inner=r+55;points=[]
    for degree in (90,210,330):
        for delta,rad in ((-25,inner),(-5,reach),(5,reach),(25,inner)):
            a=math.radians(degree+delta);points.append((rad*math.cos(a),rad*math.sin(a)))
    specs.append(tagged(poly(name+'_Mounting_Spider',tuple(points),12,(x,0,z),AX,STEEL,holes=((0,0,r),)),'Bracket','Bearing_Spiders','Frame'))
    bearing_housing(specs,name,(x-8,0,z),(x+42,0,z),shaft_radius,r)
    for j,degree in enumerate((90,210,330)):
        a=math.radians(degree);y=(reach-15)*math.cos(a);zz=z+(reach-15)*math.sin(a)
        specs.append(tagged(cylinder(name+f'_Frame_Bolt_{j}',(x-5,y,zz),(x+17,y,zz),6,FRAME),'Fastener','Bearing_Frame_Bolts','Frame'))

def continuous_guides(specs,name,points,width,height=120.,t=4.):
    for i,(a,b) in enumerate(zip(points,points[1:]),1):
        # Inner face at belt edge; lower edge reaches below belt top by 3 mm.
        for side in (-1,1):
            profile=((a[0],-a[2]+3),(b[0],-b[2]+3),(b[0],-b[2]-height),(a[0],-a[2]-height))
            y=-width/2-t if side<0 else width/2
            specs.append(tagged(poly(name+f'_{i}_{side}',profile,t,(0,y,0),AY),'Plate',name,'Internal'))

def corrected_meta(meta,**extra):
    meta=dict(meta);meta.update(extra)
    meta['revision']=REVISION
    meta['joint_design']='Bolted profile/plate brackets; inferred geometry, not a structural calculation.'
    return meta

def station1():
    from station1_design import station_geometry
    return station_geometry(VBK_CONFIG)

def station2():
    from station2_design import station_geometry
    return station_geometry(SO_CONFIG)

def draft_station3():
    s,m=source_station3()
    remove_named(s,'CRP_Grille_','CRP_Waste_Rear_Cap','CRP_Waste_Drain','CRP_Auger_Front_Bearing','CRP_Auger_Rear_Bearing')
    cap=((-680,1730),(-200,1220),(200,1220),(680,1730))
    s.append(poly('CRP_Waste_Rear_Cap_Ported',cap,5,(3450,0,0),AX,holes=((0,1285,55),)))
    flange_pipe(s,'CRP_Waste_Drain',(3600,0,1285),(3445,0,1285),55,5)
    for label,x in (('Front',550),('Rear',3500)):
        bearing_spider(s,'CRP_Auger_'+label,x,2250,50,750)
    for side in (-1,1):
        for x in (675,3340):
            bolted_support(s,f'CRP_Cover_Pedestal_{x}_{side}',(x,side*690,1390),(x,side*690,1430),35)
            for z in (1510,2100,2800):
                bolted_support(s,f'CRP_Cover_Spacer_{x}_{z}_{side}',(x,side*725,z),(x,side*730,z),30)
        for x in (555,3485):
            s.append(tagged(box(f'CRP_End_Plate_Spacer_{x}_{side}',(x,side*690-30,1410),(10,60,1655)),'Bracket','End_Plate_Spacers','Frame'))
    return s,corrected_meta(m,inlet_width_mm=915,outlet_width_mm=600,description='CRP-12 roller peeler with housed bearings, fitted waste drain and bolted covers; top grilles removed.',
        corrections=['Top grilles removed; housed auger bearings with bolted spiders; drain circle fits rear cap; cover spacers.'])

def draft_station4():
    s,m=source_station4()
    remove_named(s,'MS_Auger_Front_Bearing','MS_Auger_Rear_Bearing','MS_Waste_')
    for label,x in (('Front',520),('Rear',2690)):
        bearing_spider(s,'MS_Auger_'+label,x,1770,45,510)
    old_bearings=[q for q in s if 'Pulley_Bearing' in q['name']]
    for q in old_bearings:
        s.remove(q);x,y,z=q['origin'];x=500 if 'Front' in q['name'] else 2690
        bearing_housing(s,q['name'],(x,y,z),(x+20,y,z),14,32)
    for side in (-1,1):
        for x in (600,2620):
            bolted_support(s,f'MS_Housing_Post_{x}_{side}',(x,side*550,880),(x,side*550,2130),40)
            for z in (1450,1800,2080):
                bolted_support(s,f'MS_Hatch_Spacer_{x}_{z}_{side}',(x,side*570,z),(x,side*575,z),30)
        section=((side*580,1350),(side*190,885),(side*185,890),(side*575,1354))
        s.append(poly(f'MS_Waste_Continuous_Slope_{side}',section,2140,(540,0,0),AX))
    cap=((-580,1350),(-190,890),(190,890),(580,1350))
    for x in (540,2675):s.append(poly(f'MS_Waste_Fitted_End_{x}',cap,5,(x,0,0),AX))
    s.append(box('MS_Waste_Closed_Floor',(540,-190,885),(2140,380,5),holes=((850,0,70),)))
    flange_pipe(s,'MS_Waste_Drain',(2460,0,710),(2460,0,890),70,5)
    for x in (550,2700):
        for side in (-1,1):
            s.append(tagged(box(f'MS_Frame_Seat_Plate_{x}_{side}',(x-30,side*520-30,880),(60,60,20)),'Bracket','Housing_Seat_Plates','Frame'))
    return s,corrected_meta(m,inlet_width_mm=660,outlet_width_mm=500,
        corrections=['Auger bearings enclosed in cylindrical housings on three-web bolted plates; pulley bearing housings; fitted waste floor, ends and flange drain; supported side covers.'])

def station3():
    from peeler_design import station_geometry
    return station_geometry(3,CRP_CONFIG)


def station4():
    from peeler_design import station_geometry
    return station_geometry(4,MS_CONFIG)


def station5(slice_thickness=None):
    """R16: CC-DL slicer, vertical conical shells and welded square-tube supports."""
    import slicer_design as source
    config=dict(FINISH_CONFIGS.get(5,{}))
    if slice_thickness is not None:config['slice_mm']=float(slice_thickness)
    model=source.geometry(config);bounds=source.bounds(model)
    meta=dict(name='05_Urschel_CC_R15',
        description='CC-DL centrifugal slicer / fixed knives 1.5 mm / welded SUS304 square tube',
        inlet=source.INLET,outlet=source.OUTLET,port_interfaces=model.interfaces,
        inlet_width_mm=800.,outlet_width_mm=492.,outlet_direction=(0,0,-1),
        length=bounds['max_mm'][0],slice_thickness_mm=1.5,
        engineering_inputs=model.c,geometry_bbox=bounds,
        product_structure='Frame/Internal/External > type > family > shared CATPart instances',
        fidelity='CC-DL public casing reference; custom welded square-tube stand, supported feed chute and unpublished internals')
    return model.parts,meta


def build_station5(catia,base,rebuild=False,slice_thickness=None):
    from build_catia import build
    from slicer_review import write_report
    _,meta=station5(slice_thickness);folder=new_folder(base,meta['name'])
    doc=build(catia,folder,meta['engineering_inputs'])
    write_report(folder,meta['engineering_inputs'])
    # The native builder uses a session-unique filename on every build.
    meta.update(product=str(Path(doc.FullName).resolve()),
                generator_revision=16,build_status='complete')
    (folder/'MODEL_INFO.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    update_status(base,meta['name'],meta)
    return doc,meta


def enclosed_chain(specs,name,a,b,y,r=38.,width=12.):
    """Hollow racetrack chain envelope with real open centre, normal along Y."""
    start=(a[0],y,a[1]);end=(b[0],y,b[1]);u=unit(vec(start,end));n=(0,1,0);v=cross(n,u);length=norm(vec(start,end))
    def contour(rad):
        p=[(length+rad*math.cos(-math.pi/2+i*math.pi/12),rad*math.sin(-math.pi/2+i*math.pi/12)) for i in range(13)]
        p += [(rad*math.cos(math.pi/2+i*math.pi/12),rad*math.sin(math.pi/2+i*math.pi/12)) for i in range(13)]
        return tuple(p)
    specs.append(tagged(poly(name+'_Chain',contour(r+4),width,start,(u,v,n),RUBBER,loops=(tuple(reversed(contour(r-4))),)),'Transmission',name,'Internal'))
    for i,(x,z) in enumerate((a,b)):
        specs.append(tagged(cylinder(name+f'_Sprocket_{i}',(x,y-2,z),(x,y+width+2,z),r,FRAME,15),'Transmission',name,'Internal'))

def dry_side_drive(specs,name,x,z,shaft_y,wet_half,category='Internal',side_clearance=82.,motor_direction=1.):
    """Dry right-angle gearbox outside the wet wall; motor runs along X."""
    gy=wet_half+side_clearance;sgn=motor_direction;gear_width=min(76.,2*(side_clearance-25))
    specs.append(cylinder(name+'_Extended_Shaft',(x,shaft_y,z),(x,gy,z),14,FRAME))
    bearing_housing(specs,name+'_Bearing',(x,wet_half+8,z),(x,wet_half+25,z),14,33)
    specs.append(box(name+'_Gearbox',(x-55,gy-gear_width/2,z-55),(110,gear_width,110),MOTOR))
    specs.append(cylinder(name+'_Motor_Coupling',(x+sgn*55,gy,z),(x+sgn*65,gy,z),18,FRAME))
    specs.append(cylinder(name+'_Motor',(x+sgn*65,gy,z),(x+sgn*220,gy,z),40,MOTOR))
    specs.append(cylinder(name+'_Fan_Cover',(x+sgn*220,gy,z),(x+sgn*235,gy,z),45,RUBBER))
    specs.append(tagged(box(name+'_Mount_Bracket',(x-60 if sgn>0 else x-240,wet_half+3,z-70),(300,side_clearance+43,15)),'Bracket','Motor_Mounts','Frame'))

def draft_station6():
    s,m=source_station6();s=list(s);wet=505.;rim=1120.
    remove_named(s,'06_Immersion_Belt_Drive','06_Hold_Down_Belt_Drive','06_Belt_Bearing_Bracket')
    # Rounded bearing centres include the mesh/drum clearance in fryer_conveyor.
    for name,x,z,bw in (('Immersion',3040.,806.,700.),('Hold_Down',2840.,946.,680.)):
        top=1185.;chain_y=440.
        s.append(cylinder(f'06_{name}_Transmission_Shaft',(x,bw/2,z),(x,chain_y+12,z),14,FRAME))
        enclosed_chain(s,'06_'+name+'_Dry_Transmission',(x,z),(x,top),chain_y)
        dry_side_drive(s,'06_'+name+'_Dry_Drive',x,top,chain_y,wet,side_clearance=50.)
        bolted_support(s,'06_'+name+'_Motor_Pedestal',(x,560,640),(x,560,top-70),40)
    for x,z in ((500,806),(3040,806),(900,946),(2840,946)):
        for side in (-1,1):
            # Rim-supported hangers: no unsealed penetration through a wet wall.
            bolted_support(s,f'06_Bath_Hanger_{x}_{side}',(x,side*475,1120),(x,side*475,z-30),35)
            bolted_support(s,f'06_Bearing_Shelf_{x}_{side}',(x,side*475,z-30),(x,side*385,z-30),35)
    # Infeed joins exactly to the immersion belt top, leaving no unsupported drop.
    remove_named(s,'06_Infeed_')
    prep_tapered_chute(s,'06_Infeed',(0,0,1200),(500,0,850),700,700,90)
    for x in (200,500,3000,4200):
        for side in (-1,1):
            bolted_support(s,f'06_Pan_Seat_{x}_{side}',(x,side*510,615),(x,side*510,640),40)
    # Continuous overlapping seams and a 130 mm freeboard above 990 mm water.
    for side in (-1,1):
        s.append(tagged(box(f'06_Wet_Floor_Seam_{side}',(65,side*500-3,645),(4200,6,15)),'Seal','Wet_Pan_Seams','Internal'))
    for x in (65,4260):
        s.append(tagged(box(f'06_Wet_End_Seam_{x}',(x,-500,645),(10,1000,15)),'Seal','Wet_Pan_Seams','Internal'))
    # Outlet drive is dry above the tank. Its mount reaches the existing stand.
    remove_named(s,'06_Discharge_Belt_Drive')
    end=(4370.,0.,1225.);start=(3180.,0.,850.);n=unit(cross(unit(vec(start,end)),(0,1,0)))
    c=plus(end,scale(n,-44))
    dry_side_drive(s,'06_Discharge_Dry_Drive',c[0],c[2],350,wet,side_clearance=50.,motor_direction=-1.)
    bolted_support(s,'06_Discharge_Motor_Seat',(4370,560,640),(c[0],560,c[2]-70),40)
    for i in range(3):
        x=300+i*900
        s.append(box(f'06_Lid_Seam_Backup_{i}',(x-4,-505,1250),(12,1010,7)))
    return s,corrected_meta(m,corrections=['Rim-hung immersion conveyors with bolted bearing shelves; sealed wet-pan seams; above-water dry drives; supported lid joints.'],
        water_containment='Continuous floor/end/side solids, 990 water reference, outlet notch at 1080; no below-water drive shaft penetrations.')

def station6():
    from finishing_design import station_geometry
    return station_geometry(6,FINISH_CONFIGS.get(6))


def draft_station7():
    s,m=source_station7();s=list(s)
    remove_named(s,'07_Tray_Sidewall','07_Infeed_','07_Outfeed_')
    continuous_guides(s,'07_Raised_Product_Guard',((80,0,1220-20*80/1800),(1700,0,1220-20*1700/1800)),700,120)
    prep_tapered_chute(s,'07_Infeed',(0,0,1220),(80,0,1220-20*80/1800),700,700,120)
    prep_tapered_chute(s,'07_Outfeed',(1700,0,1220-20*1700/1800),(1800,0,1200),700,700,120)
    for side in (-1,1):
        s.append(tagged(box(f'07_Exciter_Side_Panel_{side}',(160,-453 if side<0 else 450,920),(1480,3,210)),'Plate','Exciter_Side_Panels','Frame'))
        for x in (250,900,1550):
            bolted_support(s,f'07_Panel_Bracket_{x}_{side}',(x,side*380,855),(x,side*450,960),25)
    bolted_support(s,'07_Control_Mount',(250,-380,650),(250,-430,650),30)
    return s,corrected_meta(m,raised_guard_height_mm=120,model_height_mm=1340,
        corrections=['Fixed exciter side panels outside moving spring packs; continuous 120 mm product side guards.'],
        envelope_note='Base dimensions retained; raised guards intentionally add 40 mm above the nominal 1300 mm height.')

def station7():
    from finishing_design import station_geometry
    return station_geometry(7,FINISH_CONFIGS.get(7))


def draft_station8():
    s,m=source_station8();s=list(s)
    s[:]=[q for q in s if 'Bearing_Stand' not in q['name'] and '08_Lift_Stand' not in q['name']]
    drums=[q for q in s if q['name'].endswith('_Drum') and q['name'].startswith(('08_Drying_Deck','08_Discharge_Lift'))]
    for i,q in enumerate(drums):
        x,_,z=q['origin']
        for side in (-1,1):bolted_support(s,f'08_Roller_Pedestal_{i}_{side}',(x,side*385,960),(x,side*385,z-48),35)
    remove_named(s,'08_Drip_Tray_','08_Drain_Connection','08_Lower_Side_Guard','Level_Screw','Lever_Screw')
    # Full-length tray pitches toward one end. Drain and hole share one normal.
    a=(0.,0.,875.);b=(3500.,0.,810.);direction=unit(vec(a,b));normal=cross(direction,(0,1,0))
    point=(3420.,0.,875-65*3420/3500)
    floor=plate_between('08_Full_Length_Sloped_Drip_Floor',a,b,950,4)
    delta=vec(floor['origin'],point);u=sum(delta[i]*direction[i] for i in range(3))
    floor['holes']=((u,0.,40.),);s.append(floor)
    flange_pipe(s,'08_End_Drain',plus(point,scale(normal,-145)),point,40,4)
    for side in (-1,1):
        profile=((0,-871),(3500,-806),(3500,-985),(0,-985))
        s.append(tagged(poly(f'08_Full_Length_Drain_Guard_{side}',profile,4,
                            (0,-479 if side<0 else 475,0),AY),'Plate','Drain_Guards','Internal'))
        # Attached outside panels; the wet tray lies inside them.
        panel=((0,-875),(3500,-810),(3500,-1030),(0,-1030))
        s.append(tagged(poly(f'08_Full_Length_Side_Panel_{side}',panel,3,
                            (0,-485 if side<0 else 482,0),AY),'Plate','Side_Panels','Frame'))
        for x in (100,900,1750,2600,3400):
            z=875-65*x/3500
            bolted_support(s,f'08_Tray_Seat_{x}_{side}',(x,side*410,810),(x,side*410,z-4),30)
            bolted_support(s,f'08_Panel_Tie_{x}_{side}',(x,side*435,960),(x,side*482,960),25)
        for x in (100,3400):s.append(box(f'08_Fixed_Foot_Shim_{x}_{side}',(x-25,side*410-25,30),(50,50,5)))
    for x,z in ((0,875),(3496,810)):
        s.append(box(f'08_Drip_Tray_End_Seal_{x}',(x,-475,z-4),(4,950,985-z+4)))
    for x,z in ((80,1200),(3300,1196)):
        for side in (-1,1):
            bolted_support(s,f'08_Chute_Attachment_{x}_{side}',(x,side*385,960),(x,side*385,z-4),30)
    for x in (100,1750,3400):
        for side in (-1,1):s.append(box(f'08_Fixed_Ground_Pad_{x}_{side}',(x-55,side*410-55,0),(110,110,15)))
    bolted_support(s,'08_Control_Mount',(200,-410,700),(200,-430,700),30)
    # All upper guides share belt edges rather than remaining 8 mm outboard.
    return s,corrected_meta(m,drum_mesh_clearance_mm=6,drain_slope_mm=65,
        corrections=['Cascade transfer runs lengthened to clear drums; 6 mm normal mesh/drum clearance; fixed feet; supported panels and outfeed; full 3500 mm sloped tray with matching fryer-style flange.'])

def station8():
    from finishing_design import station_geometry
    return station_geometry(8,FINISH_CONFIGS.get(8))


def draft_station9(model='PC4',hood_lift=0.,hood_transparent=False):
    s,m=source_station9(model,0.,False);d=FRYER_MODELS[model];e=FRYER_ESTIMATES
    if not 0<=hood_lift<=e['hood_max_lift']:raise ValueError('hood_lift must be 0..650 mm')
    A,B,C,D,E=(d[k] for k in ('A','B','C','D','E'))
    half=(B-e['pan_width_margin'])/2;wet=half-e['insulation_gap']
    floor=min(D-e['pan_floor_below_feed'],min(D-370,E-230)-200)
    rim=D-90;cz=min(D-370,E-230);c0=A*.15;c1=min(A*.70,A*.72-180)
    out0=(A*.72,0,cz+8);out1=(A-80,0,E+15)
    sub0=A*.32;sub1=min(A*.69,c1-75);subtop=cz+60+100-3
    remove_named(s,'_Drive','09_Conveyor_Mount','09_Bath_Belt_Side_Guide','09_Discharge_Side_Guide',
                 '09_Hood_End_','09_Infeed_Slide','09_Transfer_Bridge')
    chute(s,'09_Infeed_Slide',(0,0,D),(c0,0,cz),C,130,4)
    remove_named(s,'09_Infeed_Slide_Left','09_Infeed_Slide_Right','09_Discharge_Lip_Left','09_Discharge_Lip_Right')
    fryer_mesh(s,'09_Transfer_Bridge',(c1,0,cz),out0,C,e,ROLLER)
    continuous_guides(s,'09_Continuous_Product_Guard',((0,0,D),(c0,0,cz),(c1,0,cz),out0,out1,(A,0,E)),C,130)
    # Hood end returns touch the chute cheek surfaces, with an open product gate.
    hh=half+10;hb=rim+30;he=D+260;hr=D+500;hx0=A*.055;hx1=A*.85
    for i,x in enumerate((hx0,hx1-3),1):
        if i==1:z=D+(cz-D)*x/c0
        else:z=out0[2]+(out1[2]-out0[2])*(x-out0[0])/(out1[0]-out0[0])
        gate=C/2+4;top=max(z+138,hb+20)
        outline=((-hh,hb),(-wet,rim+6),(-gate,z-4),(-gate,top),(gate,top),
                 (gate,z-4),(wet,rim+6),(hh,hb),(hh,he),(0,hr),(-hh,he))
        s.append(poly(f'09_Hood_End_Portal_{i}',outline,3,(x,0,0),AX))
    # The complete cassette has its own bolted longitudinal frame beneath the belts.
    first=len(s);rail_y=wet-45;rail_z=floor+40
    for side in (-1,1):
        bolted_support(s,f'09_Lifting_Cassette_Long_{side}',(c0,side*rail_y,rail_z),(out1[0],side*rail_y,rail_z),40)
    convs=[('Lower',(c0,0,cz),(c1,0,cz),C,55),
           ('Submerger',(sub0,0,subtop),(sub1,0,subtop),C-20,50),
           ('Outfeed',out0,out1,C,35)]
    centres={}
    for name,a,b,bw,r in convs:
        n=unit(cross(unit(vec(a,b)),(0,1,0)))
        pair=[plus(p,scale(n,-r-e['mesh_thickness']-6)) for p in (a,b)]
        centres[name]=pair
        for j,p in enumerate(pair):
            x,_,z=p
            bolted_support(s,f'09_{name}_Cassette_Cross_{j}',(x,-rail_y,rail_z),(x,rail_y,rail_z),40)
            for side in (-1,1):
                y=side*(bw/2+24)
                bolted_support(s,f'09_{name}_Bearing_Pedestal_{j}_{side}',(x,y,rail_z+20),(x,y,z-23),35)
    # Hood, conveyors and paddles share four jack-supported lifting portals.
    for x in (A*.20,A*.72):
        bolted_support(s,f'09_Lift_Crosshead_{x:g}',(x,-(half+35),hr+50),(x,half+35,hr+50),50)
        for side in (-1,1):
            bolted_support(s,f'09_Jack_Nut_Riser_{x:g}_{side}',(x,side*(half+35),hb+120),(x,side*(half+35),hr+50),40)
            bolted_support(s,f'09_Cassette_Hanger_{x:g}_{side}',(x,side*rail_y,hr+50),(x,side*rail_y,rail_z),40)
            bolted_support(s,f'09_Hood_Rail_Drop_{x:g}_{side}',(x,side*(hh-10),hb+120),(x,side*(hh-10),hb),35)
    # Two dry motor/gearbox units are outside the oil pan and above its rim.
    # Chain drops are INSIDE the wet pan, so no lifting shaft penetrates a wet wall.
    chain_y=C/2+(wet-C/2)*.52;drive_z=rim+135
    for name in ('Lower','Submerger'):
        c=centres[name][-1];x,z=c[0],c[2];bw=C if name=='Lower' else C-20
        s.append(cylinder(f'09_{name}_Inner_Extended_Shaft',(x,bw/2,z),(x,chain_y+14,z),14,FRAME))
        enclosed_chain(s,f'09_{name}_Lift_Transmission',(x,z),(x,drive_z),chain_y)
        dry_side_drive(s,f'09_{name}_Dry_Drive',x,drive_z,chain_y,wet)
        bolted_support(s,f'09_{name}_Motor_Shelf',(x,rail_y,drive_z-70),(x,wet+100,drive_z-70),40)
        bolted_support(s,f'09_{name}_Motor_Tower',(x,rail_y,rail_z),(x,rail_y,drive_z-70),40)
    # Discharge and metering paddles are coupled to the lower drive; no submerged motor.
    a=centres['Lower'][-1];b=centres['Outfeed'][-1]
    enclosed_chain(s,'09_Discharge_Coupled_Transmission',(a[0],a[2]),(b[0],b[2]),chain_y+20)
    for c in (a,b):s.append(cylinder(f'09_Coupled_Extended_Shaft_{c[0]:g}',(c[0],C/2,c[2]),(c[0],chain_y+34,c[2]),14,FRAME))
    previous=centres['Lower'][0]
    for i in range(e['paddle_count']):
        x=c0+(sub0-c0)*(i+1)/(e['paddle_count']+1);z=cz+e['paddle_radius']+20
        enclosed_chain(s,f'09_Paddle_Coupled_Transmission_{i}',(previous[0],previous[2]),(x,z),chain_y+20)
        s.append(cylinder(f'09_Paddle_Extended_Shaft_{i}',(x,(C-30)/2,z),(x,chain_y+34,z),18,FRAME))
        for side in (-1,1):bolted_support(s,f'09_Paddle_Bearing_Stand_{i}_{side}',(x,side*(C/2+11),rail_z),(x,side*(C/2+11),z-26),35)
        previous=(x,0,z)
    for q in s[first:]:q['moving_with_hood']=True
    moving_tokens=('09_Hood_','09_Exhaust_','09_Lower_Process_','09_Upper_Submerger','09_Draining_Discharge',
                   '09_Metering_Paddle','09_Transfer_Bridge','09_Continuous_Product_Guard','09_Infeed_Slide','09_Discharge_Lip')
    for q in s:
        name=q['name'];is_jack='09_Hood_Jack_' in name
        moves=q.get('moving_with_hood',False) or (any(name.startswith(t) for t in moving_tokens) and not is_jack)
        moves=moves or (is_jack and ('Travelling_Nut' in name or 'Hood_Bracket' in name))
        if moves:
            q['origin']=plus(q['origin'],(0,0,hood_lift));q['moving_with_hood']=True
            if 'profile_ends' in q:q['profile_ends']=tuple(plus(p,(0,0,hood_lift)) for p in q['profile_ends'])
        if hood_transparent and name.startswith(('09_Hood_Side','09_Hood_Roof','09_Hood_End')):q['transparency']=65
    # Ground controls and tank remain fixed during service lift.
    bolted_support(s,'09_Control_Fixed_Bracket',(A*.10,-half,floor+180),(A*.10,-B/2+70,floor+180),30)
    return s,corrected_meta(m,inlet_width_mm=C,outlet_width_mm=C,hood_lift_mm=hood_lift,hood_transparent=hood_transparent,
        nominal_closed_envelope_mm=(A,B,D+1500),inlet=(0,0,D+hood_lift),outlet=(A,0,E+hood_lift),
        motor_count=2,drum_mesh_clearance_mm=6,
        corrections=['Continuous product guides; notched hood end portals; jack crossheads and common lifting cassette; two dry external drives, coupled discharge/paddles; shaft bearings and seals; mesh/drum clearance.'],
        lift_note='Static maintenance pose. Hood, paddles, conveyors, motor drives and their supports translate together; tank/jack bases remain fixed. Full line assembly requires lift=0.',
        wet_shaft_penetrations=False)


def station9(model='PC4',hood_lift=0.,hood_transparent=False):
    from finishing_design import station_geometry
    return station_geometry(9,dict(FINISH_CONFIGS.get(9,{}),fryer_model=model),hood_lift=hood_lift,hood_transparent=hood_transparent)


def source_station10():
    """07 vibratory dewaterer, with a moving perforated deck on leaf springs."""
    s=AssemblySpecs();e=dict(PREP_ESTIMATES,dewater_frame_top=680.,drain_pan_floor=700.);d=dict(length=1800.,width=1000.,height=1140.);p=dict(inlet_height=1020.,outlet_height=1000.,inlet_width=510.,outlet_width=510.)
    L,W,H=d['length'],d['width'],d['height'];bw=p['inlet_width']
    z0=p['inlet_height'];z1=p['outlet_height']
    def deck_z(x):return z0+(z1-z0)*x/L
    with s.section('Support Frame'):
        frame(s,L,W-240,e['dewater_frame_top'],50)
    with s.section('Vibrating Deck'):
        fryer_mesh(s,'10_Perforated_Screen',(80,0,deck_z(80)),(L-100,0,deck_z(L-100)),bw,e,ROLLER)
        conveyor_guides(s,'10_Tray_Sidewall',(80,0,deck_z(80)),(L-100,0,deck_z(L-100)),bw,80)
        for side in (-1,1):
            s.append(tube(f'10_Moving_Longitudinal_Beam_{side}',(80,side*380,deck_z(80)-25),
                          (L-100,side*380,deck_z(L-100)-25),40,40,3))
        for x in (420.,900.,1470.):
            s.append(tube(f'10_Moving_Crossbeam_{x:g}',(x,-380,deck_z(x)-25),
                          (x,380,deck_z(x)-25),40,40,3))
    with s.section('Infeed'):
        prep_tapered_chute(s,'10_Infeed',(0,0,z0),(80,0,deck_z(80)),bw,bw,80)
    with s.section('Outfeed'):
        prep_tapered_chute(s,'10_Outfeed',(L-100,0,deck_z(L-100)),(L,0,z1),bw,p['outlet_width'],75)
    with s.section('Suspension'):
        # Inclined spring leaves, fixed lower clamps, moving upper clamps.
        # The deflection and oscillation are not simulated by this static model.
        for i,x in enumerate((350.,1400.),1):
            upper=x+70;bottom=e['dewater_frame_top'];top=deck_z(upper)-45
            for side in (-1,1):
                y=side*380;prefix=f'10_Spring_Pack_{i}_{side}'
                s.append(box(prefix+'_Lower_Clamp',(x-25,y-45,bottom-5),(90,90,12),FRAME,
                             holes=((-28,-28,5),(28,-28,5),(28,28,5),(-28,28,5))))
                s.append(box(prefix+'_Upper_Clamp',(upper-25,y-45,top-5),(90,90,12),FRAME))
                for j in range(e['leaf_spring_layers']):
                    shift=j*9.
                    s.append(plate_between(prefix+f'_Leaf_{j+1}',
                                           (x+shift,y,bottom+7),(upper+shift,y,top+5),
                                           60,e['leaf_spring_thickness'],GUARD))
                s.append(cylinder(prefix+'_Lower_Clamp_Pin',(x+25,y-52,bottom+4),
                                  (x+25,y+52,bottom+4),6,ROLLER))
                s.append(cylinder(prefix+'_Upper_Clamp_Pin',(upper+25,y-52,top+2),
                                  (upper+25,y+52,top+2),6,ROLLER))
    with s.section('Exciter Drive'):
        # Pair of counter-rotating vibration motors, mounted to the moving tray.
        for i,x in enumerate((760.,1090.),1):
            z=840.;prefix=f'10_Vibration_Motor_{i}';red=(174,67,49)
            s.append(cylinder(prefix+'_Housing',(x,-110,z),(x,110,z),65,red))
            s.append(cylinder(prefix+'_Rotor_Shaft',(x,-175,z),(x,175,z),16,FRAME))
            for side in (-1,1):
                y=side*120
                # Eccentric mass is visible as an offset pad behind an end guard.
                s.append(cylinder(prefix+f'_Eccentric_Weight_{side}',(x+20,y,z-18),
                                  (x+20,y+side*18,z-18),34,GUARD))
                s.append(cylinder(prefix+f'_End_Guard_{side}',(x,side*145,z),
                                  (x,side*180,z),74,red,69))
                s.append(cylinder(prefix+f'_End_Cap_{side}',(x,side*180,z),
                                  (x,side*184,z),74,red))
            for j in range(5):
                y=-88+j*44
                s.append(cylinder(prefix+f'_Fin_{j}',(x,y,z),(x,y+4,z),70,red))
            s.append(box(prefix+'_Mounting_Plate',(x-95,-140,z+66),(190,280,12),FRAME))
            for side in (-1,1):
                s.append(tube(prefix+f'_Mount_Stay_{side}',(x,side*110,z+78),
                              (x,side*110,deck_z(x)-20),35,35,3))
            s.append(box(prefix+'_Terminal_Box',(x+58,-40,z-25),(42,80,50),red))
    with s.section('Drainage'):
        drain_x=L*.65;z=e['drain_pan_floor'];pan0=100.;pan1=L-120;pw=bw+80
        s.append(box('10_Drain_Pan_Floor',(pan0,-pw/2,z),(pan1-pan0,pw,3),
                     holes=((drain_x-(pan0+pan1)/2,0,25),)))
        for side in (-1,1):
            s.append(box(f'10_Drain_Pan_Side_{side}',(pan0,side*pw/2,z),(pan1-pan0,3,40)))
        for x in (pan0,pan1-3):
            s.append(box(f'10_Drain_Pan_End_{x:g}',(x,-pw/2,z),(3,pw,40)))
        s.append(cylinder('10_Drain_Outlet',(drain_x,0,z-140),(drain_x,0,z+3),25,STEEL,21))
        for x in (300.,L-300):
            s.append(tube(f'10_Drain_Pan_Support_{x:g}',(x,-380,z-15),(x,380,z-15),30,30,3))
    with s.section('Electrical Controls'):
        prep_control_box(s,'10_Control',200,-W/2+10,470)
    meta=prep_metadata(7,'10_Vibratory_Deoiler','Perforated vibrating tray, leaf-spring suspension, twin exciters and separate drain pan.')
    meta['suspension_note']='Leaf-spring geometry is an inferred static arrangement, not a dynamic spring-rate calculation.'
    return s,meta

def draft_station10():
    s,m=source_station10();s=list(s)
    remove_named(s,'10_Tray_Sidewall','10_Infeed_','10_Outfeed_')
    continuous_guides(s,'10_Product_Guard',((80,0,1020-20*80/1800),(1700,0,1020-20*1700/1800)),510,120)
    prep_tapered_chute(s,'10_Infeed',(0,0,1020),(80,0,1020-20*80/1800),510,510,120)
    prep_tapered_chute(s,'10_Outfeed',(1700,0,1020-20*1700/1800),(1800,0,1000),510,510,120)
    for side in (-1,1):
        s.append(tagged(box(f'10_Exciter_Side_Panel_{side}',(160,-453 if side<0 else 450,720),(1480,3,210)),'Plate','Exciter_Side_Panels','Frame'))
        for x in (250,900,1550):bolted_support(s,f'10_Panel_Bracket_{x}_{side}',(x,side*380,655),(x,side*450,760),25)
    return s,corrected_meta(m,name='10_Vibratory_Deoiler',description='Concept vibratory deoiler derived from the supplied station 7 suspension, with oil collection pan.',
        inlet=(0,0,1020),outlet=(1800,0,1000),inlet_width_mm=510,outlet_width_mm=510,
        published_envelope_mm=None,model_nominal_envelope_mm=(1800,1000,1140),source_website_row=None,
        estimated_interfaces_mm=dict(inlet_height=1020.,outlet_height=1000.,inlet_width=510.,outlet_width=510.),
        dimension_basis='No station 10 file supplied; inferred station 7 derivative for continuity of the requested 1-11 line.')


def station10():
    from finishing_design import station_geometry
    return station_geometry(10,FINISH_CONFIGS.get(10))


def source_station11():
    s=[]
    # Enclosed drum with controlled potato, seasoning and discharge openings.
    cx0,cx1,zc=340.,2140.,1240.
    r=390.;inner=384.
    # 2400 mm long underframe, steel members and adjustable feet.
    frame(s,2400,1050,930,member=55)
    # Cylindrical wall is closed along its length; end caps seal both ends.
    s.append(cylinder('S11_Open_Drum_Shell',(cx0,0,zc),(cx1,0,zc),r,STEEL,inner))
    for label,x in [('Feed',cx0),('Discharge',cx1-18)]:
        s.append(cylinder(f'S11_{label}_Rim',(x,0,zc),(x+18,0,zc),402,STEEL,378))
    # Feed end cap: two independent holes in the same solid plate.
    # Local sketch x/y correspond to transverse Y/Z, centred at drum axis.
    # Potato inlet radius 115 at local (0,-110).
    # Seasoning port radius 28 at local (0,+205).
    s.append(dict(name='S11_Sealed_Feed_End_Cap',kind='circle',
                  radius=384.,inner=0.,depth=12.,
                  circles=((0.,-110.,115.),(0.,205.,28.)),
                  origin=(cx0+5,0,zc),axes=AX,color=STEEL,holes=()))
    # Discharge end cap: a single, much smaller controlled exit opening.
    s.append(dict(name='S11_Sealed_Discharge_End_Cap',kind='circle',
                  radius=384.,inner=0.,depth=12.,
                  circles=((0.,-115.,135.),),
                  origin=(cx1-17,0,zc),axes=AX,color=STEEL,holes=()))
    # Separate short seasoning inlet tube, passing through the upper feed port.
    s.append(cylinder('S11_Seasoning_Inlet_Tube',
                      (cx0-145,0,zc+205),(cx0+35,0,zc+205),
                      27.,STEEL,21.))
    s.append(cylinder('S11_Seasoning_Hopper_Collar',
                      (cx0-145,0,zc+205),(cx0-125,0,zc+205),
                      43.,STEEL,21.))
    # Twelve internal longitudinal mixing ribs, separate editable parts.
    for i in range(12):
        a=2*math.pi*i/12
        yy=inner*math.cos(a);zz=zc+inner*math.sin(a)
        radial=(0.,math.cos(a),math.sin(a))
        tangent=(0.,-math.sin(a),math.cos(a))
        # A rectangular pad with X as extrusion axis, tangential width 44.
        s.append(poly(f'S11_Lifter_{i+1:02d}',rect(44,35),1720,
                      (380,yy,zz),(tangent,radial,(1.,0.,0.)),STEEL))
    # External drive annulus, collar and mounting plates.
    s.append(cylinder('S11_Drive_Ring',(560,0,zc),(615,0,zc),438,FRAME,388))
    s.append(cylinder('S11_Drive_Guard_Front',(535,0,zc),(550,0,zc),485,GUARD,444))
    s.append(cylinder('S11_Drive_Guard_Back',(625,0,zc),(640,0,zc),485,GUARD,444))
    for i in range(12):
        a=2*math.pi*i/12
        y=417*math.cos(a);z=zc+417*math.sin(a)
        s.append(cylinder(f'S11_Drive_Magnet_{i+1:02d}',(551,y,z),(565,y,z),12,MOTOR))
    # Drum support rollers beneath the shell, at two axial stations.
    for x in (510,1970):
        for side in (-1,1):
            y=side*265;z=900
            s.append(cylinder(f'S11_Support_Roller_{x}_{side}',(x-60,y,z),(x+60,y,z),75,RUBBER))
            s.append(box(f'S11_Support_Bearing_{x}_{side}',(x-80,y-50,800),(160,100,65),FRAME))
    # Gear motor outside the drum, with motor shaft and gearbox.
    s.append(box('S11_Gearbox',(560,-665,1050),(250,210,250),MOTOR))
    s.append(cylinder('S11_Gear_Motor',(685,-665,1180),(685,-955,1180),105,MOTOR))
    s.append(cylinder('S11_Motor_Fan_Cover',(685,-955,1180),(685,-1000,1180),112,RUBBER))
    s.append(cylinder('S11_Drive_Shaft',(615,-510,1180),(615,-420,1180),25,FRAME))
    # Product chutes connect to end-cap openings; open above for loading.
    chute(s,'S11_Feed_Chute',(0,0,1470),(340,0,1130),210,130,5)
    chute(s,'S11_Discharge_Chute',(2140,0,1125),(2440,0,1010),250,130,5)
    # AUTOMATIC CHIP INFEED: belt reaches the potato-only end-cap aperture.
    # Top run ends at X=345, Z=1130; side rails funnel chips into the inlet.
    s.append(plate_between('AUTO_Chip_Conveyor_Top_Belt',
                           (-1350,0,1280),(325,0,1130),190,9,BELT))
    s.append(plate_between('AUTO_Chip_Conveyor_Return_Belt',
                           (-1350,0,1170),(325,0,1020),190,7,RUBBER))
    for x,z in ((-1310,1225),(-900,1188),(-480,1150),(280,1085)):
        s.append(cylinder(f'AUTO_Chip_Belt_Roller_{x}',
                          (x,-112,z),(x,112,z),38,ROLLER))
    for side in (-1,1):
        y=side*125
        s.append(tube(f'AUTO_Conveyor_Rail_{side}',
                      (-1360,y,1190),(325,y,1040),35,50,3,FRAME))
        s.append(box(f'AUTO_Conveyor_Sidewall_{side}',
                     (-1330,y-3,1230),(1600,6,110),STEEL))
    for x in (-1150,-400):
        for side in (-1,1):
            s.append(tube(f'AUTO_Conveyor_Leg_{x}_{side}',
                          (x,side*135,30),(x,side*135,1120),45,45,3,FRAME))
    s.append(box('AUTO_Chip_Conveyor_Drive_Gearbox',
                 (-1350,-275,1130),(145,130,145),MOTOR))
    s.append(cylinder('AUTO_Chip_Conveyor_Drive_Motor',
                      (-1280,-275,1200),(-1280,-470,1200),64,MOTOR))

    # AUTOMATIC SEASONING: covered powder hopper + metering screw and
    # downpipe routed to the separate upper feed-end aperture.
    # Hopper is a hollow box; top cover is removable in CATIA tree.
    s.append(box('AUTO_Seasoning_Hopper_Floor',
                 (-365,-220,1740),(390,440,8),STEEL))
    for y in (-220,212):
        s.append(box(f'AUTO_Seasoning_Hopper_YWall_{y}',
                     (-365,y,1748),(390,8,430),STEEL))
    for x in (-365,17):
        s.append(box(f'AUTO_Seasoning_Hopper_XWall_{x}',
                     (x,-212,1748),(8,424,430),STEEL))
    s.append(box('AUTO_Seasoning_Hopper_Lid',
                 (-365,-220,2178),(390,440,10),STEEL))
    # Screw feeder tube is horizontal in X; drive at upstream end.
    s.append(cylinder('AUTO_Seasoning_Screw_Casing',
                      (-355,0,1715),(75,0,1715),37,STEEL,29))
    s.append(cylinder('AUTO_Seasoning_Metering_Shaft',
                      (-345,0,1715),(65,0,1715),12,ROLLER))
    # Represent screw flights as individual thin inclined paddles (schematic).
    for j in range(12):
        x=-320+j*32
        a=j*math.pi/2
        s.append(poly(f'AUTO_Seasoning_Flight_{j+1:02d}',
                      rect(42,5),7,(x,0,1715),
                      ((0,math.cos(a),math.sin(a)),
                       (0,-math.sin(a),math.cos(a)),(1,0,0)),ROLLER))
    s.append(box('AUTO_Seasoning_Metering_Gearbox',
                 (-490,-75,1640),(125,150,150),MOTOR))
    s.append(cylinder('AUTO_Seasoning_Metering_Motor',
                      (-560,0,1715),(-755,0,1715),57,MOTOR))
    # The outlet drops into the existing upper feed-end hole at Z=1445.
    s.append(cylinder('AUTO_Seasoning_Drop_Pipe',
                      (55,0,1450),(55,0,1715),25,STEEL,20))
    s.append(cylinder('AUTO_Seasoning_Transfer_Pipe',
                      (55,0,1445),(375,0,1445),25,STEEL,20))
    s.append(box('AUTO_Seasoning_Level_Sensor_Housing',
                 (-60,-245,1980),(80,35,70),MOTOR))
    s.append(box('AUTO_Chip_Infeed_Sensor_Housing',
                 (235,-180,1210),(55,45,65),MOTOR))
    # Support stays and an emergency-stop box.
    for side in (-1,1):
        s.append(tube(f'S11_Infeed_Stay_{side}',(150,side*265,920),(150,side*265,1390),35,35,3))
        s.append(tube(f'S11_Outfeed_Stay_{side}',(2310,side*280,920),(2310,side*280,1060),35,35,3))
    s.append(box('S11_Control_Box',(120,-630,1070),(190,115,230),FRAME))
    s.append(cylinder('S11_Emergency_Stop',(215,-640,1270),(215,-680,1270),30,GUARD))
    return s

def triangle_sheet(specs,name,a,b,c,t=4.):
    u=unit(vec(a,b));n=unit(cross(u,vec(a,c)));v=cross(n,u)
    coords=tuple((sum(x*y for x,y in zip(vec(a,p),u)),sum(x*y for x,y in zip(vec(a,p),v))) for p in (a,b,c))
    specs.append(poly(name,coords,t,plus(a,scale(n,-t)),(u,v,n)))

def draft_station11(seasoning_angle=40.):
    if not 38<=seasoning_angle<=50:raise ValueError('seasoning_angle must be 38..50 degrees')
    s=source_station11()
    remove_named(s,'S11_Open_Drum','S11_Sealed_','S11_Feed_Rim','S11_Discharge_Rim',
        'S11_Lifter_','S11_Drive_Ring','S11_Drive_Guard','S11_Drive_Magnet',
        'S11_Support_Roller','S11_Support_Bearing','S11_Feed_Chute','S11_Discharge_Chute',
        'S11_Infeed_Stay','S11_Outfeed_Stay','S11_Drive_Shaft','AUTO_Chip_Conveyor_',
        'AUTO_Chip_Belt_Roller','AUTO_Conveyor_','AUTO_Seasoning_Drop_Pipe','AUTO_Seasoning_Transfer_Pipe',
        'S11_Seasoning_Inlet_Tube','S11_Seasoning_Hopper_Collar','AUTO_Seasoning_Screw_Casing')
    x0,x1,zc=340.,2140.,1240.;r0,r1,wall=340.,440.,6.
    def radius(x):return r0+(r1-r0)*(x-x0)/(x1-x0)
    # Thirty-two planar shell facets give a genuinely expanding open drum.
    # Slight angular overlap closes the seams while keeping both mouths open.
    for i in range(32):
        a=2*math.pi*i/32-.001;b=2*math.pi*(i+1)/32+.001
        points=((x0,r0*math.cos(a),zc+r0*math.sin(a)),(x0,r0*math.cos(b),zc+r0*math.sin(b)),
                (x1,r1*math.cos(b),zc+r1*math.sin(b)),(x1,r1*math.cos(a),zc+r1*math.sin(a)))
        s.append(tagged(quad_sheet(f'S11_Expanding_Open_Drum_Facet_{i+1:02d}',points,wall),'Shell','Expanding_Open_Drum','Internal'))
    for label,x,r in (('Feed',340.,r0),('Discharge',2122.,radius(2122))):
        s.append(cylinder(f'S11_{label}_Open_Rim',(x,0,zc),(x+18,0,zc),r+8,STEEL,r-wall-2))
    for i in range(12):
        a=2*math.pi*i/12;c,ss=math.cos(a),math.sin(a)
        ra=radius(380)-wall;rb=radius(2100)-wall
        points=((380,ra*c,zc+ra*ss),(2100,rb*c,zc+rb*ss),
                (2100,(rb-35)*c,zc+(rb-35)*ss),(380,(ra-35)*c,zc+(ra-35)*ss))
        s.append(quad_sheet(f'S11_Tapered_Lifter_{i+1:02d}',points,4))
    # Bearing-mounted support rollers are tangent to the corresponding cone radius.
    for x in (510.,1970.):
        rr=radius(x)+75
        z=zc-rr*math.sqrt(3)/2
        bolted_support(s,f'S11_Roller_Frame_Cross_{x:g}',(x,-525,z-120),(x,525,z-120),60)
        for side in (-1,1):
            y=side*rr/2
            s.append(cylinder(f'S11_Support_Roller_{x:g}_{side}',(x-55,y,z),(x+55,y,z),75,RUBBER,15))
            s.append(cylinder(f'S11_Roller_Shaft_{x:g}_{side}',(x-100,y,z),(x+100,y,z),14,FRAME))
            s.append(tagged(box(f'S11_Roller_Base_Plate_{x:g}_{side}',(x-110,y-40,z-96),(220,80,6)),'Bracket','Roller_Base_Plates','Frame'))
            for xx in (x-90,x+60):
                bearing_housing(s,f'S11_Roller_Bearing_{xx:g}_{side}',(xx,y,z),(xx+30,y,z),14,34)
                bolted_support(s,f'S11_Roller_Bearing_Pedestal_{xx:g}_{side}',(xx+15,y,z-90),(xx+15,y,z-34),35)
    ring_r=radius(585)
    s.append(cylinder('S11_Drive_Ring',(560,0,zc),(615,0,zc),ring_r+45,FRAME,ring_r-3))
    # Existing external gearbox drives a pinion at the outside of the new ring.
    py=-(ring_r+45+35)
    s.append(cylinder('S11_Drive_Pinion',(560,py,zc),(615,py,zc),35,MOTOR,15))
    s.append(cylinder('S11_Drive_Pinion_Shaft',(540,py,zc),(685,py,zc),14,FRAME))
    bolted_support(s,'S11_Main_Gearbox_Shelf',(685,-525,930),(685,-600,1035),55)
    s.append(box('S11_Drive_Transfer_Gearbox',(615,py-60,1180),(90,120,120),MOTOR))
    s.append(cylinder('S11_Gearbox_Connecting_Shaft',(685,-455,1180),(685,py,1180),14,FRAME))
    # Chip infeed passes through the open feed mouth, with guards following its slope.
    a=(-1350.,0.,1100.);b=(420.,0.,1040.);est=dict(PREP_ESTIMATES,mesh_tile_length=350.)
    fryer_conveyor(s,'S11_Chip_Infeed',a,b,190,38,est,1000,False)
    continuous_guides(s,'S11_Chip_Infeed_Guard',(a,b),190,100)
    n=unit(cross(unit(vec(a,b)),(0,1,0)));drive=plus(a,scale(n,-47))
    fryer_drive(s,'S11_Chip_Infeed_Drive',drive,190,1000)
    for x in (-1150,-400,200):
        z=1100+(1040-1100)*(x+1350)/1770
        for side in (-1,1):
            bolted_support(s,f'S11_Infeed_Leg_{x}_{side}',(x,side*130,30),(x,side*130,z-47),45)
            s.append(box(f'S11_Infeed_Foot_{x}_{side}',(x-45,side*130-45,12),(90,90,18)))
    # No discharge cap. The curved bottom of the open mouth becomes a flat lip.
    count=16;inner=r1-wall
    for i in range(count):
        a=math.radians(210+120*i/count);b=math.radians(210+120*(i+1)/count)
        p=(2140.,inner*math.cos(a),zc+inner*math.sin(a));q=(2140.,inner*math.cos(b),zc+inner*math.sin(b))
        r=(2440.,-250+500*i/count,740.);t=(2440.,-250+500*(i+1)/count,740.)
        # Reverse Y mapping: cos(210) is negative and cos(330) positive.
        triangle_sheet(s,f'S11_Continuous_Discharge_{i:02d}_A',p,q,t)
        triangle_sheet(s,f'S11_Continuous_Discharge_{i:02d}_B',p,t,r)
    for side in (-1,1):
        y=side*inner*math.sqrt(3)/2;z=zc-inner/2
        s.append(quad_sheet(f'S11_Discharge_Sidewall_{side}',((2140,y,z),(2440,side*250,740),
                           (2440,side*250,890),(2140,y,z+150)),4))
        bolted_support(s,f'S11_Discharge_Support_{side}',(2310,side*280,30),(2310,side*280,790),35)
        s.append(box(f'S11_Discharge_Foot_{side}',(2265,side*280-45,12),(90,90,18)))
    # Open the hopper floor and screw casing so powder can enter the feeder.
    for q in s:
        if q['name']=='AUTO_Seasoning_Hopper_Floor':
            q['loops']=(tuple(reversed(tuple((x,y) for x,y in rect(300,34)))),)
    angles=[math.radians(120+300*i/60) for i in range(61)]
    profile=tuple((37*math.cos(a),37*math.sin(a)) for a in angles)+tuple((29*math.cos(a),29*math.sin(a)) for a in reversed(angles))
    s.append(poly('S11_Seasoning_Open_Throat_Casing',profile,430,(-355,0,1715),AX))
    s.append(box('S11_Feeder_Outlet_Top_Cover',(25,-20,1747),(50,40,5)))
    end_z=1686-355*math.tan(math.radians(seasoning_angle))
    chute(s,'S11_Angled_Seasoning_Inlet',(75,0,1686),(430,0,end_z),50,80,3)
    s.append(plate_between('S11_Seasoning_Inlet_Cover',(75,0,1766),(430,0,end_z+80),56,3))
    s.append(cylinder('S11_Metering_Motor_Coupling',(-560,0,1715),(-490,0,1715),14,FRAME))
    for side in (-1,1):
        bolted_support(s,f'S11_Seasoning_Hopper_Stand_{side}',(-170,side*210,30),(-170,side*210,1740),45)
        s.append(box(f'S11_Hopper_Foot_{side}',(-215,side*210-45,12),(90,90,18)))
    # Use process numbering and a nonnegative inlet datum across the integrated line.
    for q in s:
        q['name']=q['name'].replace('AUTO_','S11_')
        q['origin']=plus(q['origin'],(1350,0,0))
        if 'profile_ends' in q:q['profile_ends']=tuple(plus(p,(1350,0,0)) for p in q['profile_ends'])
    return s,corrected_meta(dict(name='11_Seasoning_Drum',description='Expanding open seasoning drum with supported chip conveyor and continuous discharge shoe.',
        inlet=(0,0,1100),outlet=(3790,0,740),length=3790,inlet_width_mm=190,outlet_width_mm=500),
        seasoning_angle_deg=seasoning_angle,drum_inlet_diameter_mm=680,drum_outlet_diameter_mm=880,
        corrections=['Both drum mouths open; no sealed discharge cap; angled powder inlet with actual feed throat; belt-following guards; curved-to-flat discharge; housed support rollers.'],
        fidelity='Faceted native-pad expanding shell and inferred feeder geometry; static adjustment, not kinematics.')

def station11(seasoning_angle=40.):
    from finishing_design import station_geometry
    return station_geometry(11,dict(FINISH_CONFIGS.get(11,{}),seasoning_angle_deg=seasoning_angle))


def functional_path(spec):
    """Stable semantic groups, not one product per position or per generated file."""
    name=spec['name'];lower=name.lower();typ=spec.get('part_type');category=spec.get('category')
    if not typ:
        if any(t in lower for t in ('bolt','screw','adjuster','leveling_stem')):typ='Fastener'
        elif any(t in lower for t in ('bearing','bushing')):typ='Bearing'
        elif any(t in lower for t in ('seal','gasket')):typ='Seal'
        elif any(t in lower for t in ('motor','gearbox','coupling','fancover','fan_cover')):typ='Drive'
        elif any(t in lower for t in ('control','display','readout','estop','emergency','sensor','pushbutton')):typ='Control'
        elif any(t in lower for t in ('bracket','hinge','clamp','spacer','mount','seat_plate')):typ='Bracket'
        elif any(t in lower for t in ('pipe','nozzle','flush','riser','flange','header','drain_connection')):typ='Pipe'
        elif spec['kind']=='helix':typ='Auger'
        elif any(t in lower for t in ('meshtile','belt','chain','pulley','sprocket','paddle')):typ='Conveyor'
        elif any(t in lower for t in ('shaft','axle','roller','drum','rotor','lifter','knife','blade')):typ='Mechanism'
        else:typ='Plate'
    if not category:
        if typ in ('Control','Drive'):category='External'
        elif typ in ('Profile','Bracket','Fastener') or any(t in lower for t in ('cover','hood','housing','hatch','panel','frame','foot','rim')):category='Frame'
        else:category='Internal'
    family=spec.get('family')
    if not family:
        if typ=='Profile':
            if any(t in lower for t in ('leg','post','stand','pedestal','hanger','riser')):family='Support_Profiles'
            elif any(t in lower for t in ('cross','bridge','portal')):family='Cross_Profiles'
            elif any(t in lower for t in ('brace','diagonal')):family='Brace_Profiles'
            else:family='Longitudinal_Profiles'
        elif typ=='Fastener':family='Bolts_and_Clamps'
        else:
            # Remove instance coordinates and positions, retaining the function.
            words=re.sub(r'(?<![A-Za-z])[-+]?\d+(?:\.\d+)?','',name).split('_')
            family='_'.join(w for w in words if w and w.lower() not in ('front','rear','left','right'))
            family=family[:65] or typ
    words=re.sub(r'(?<![A-Za-z])[-+]?\d+(?:\.\d+)?','',family).split('_')
    family='_'.join(w for w in words if w and w.lower() not in ('front','rear','left','right'))[:65] or typ
    return category,typ,family

def prepare_specs(specs,meta):
    specs=[dict(q) for q in specs]
    # Add removable L joints to primary source-frame members. New supports
    # already carry explicit drilled end brackets and are not double-fastened.
    for q in tuple(specs):
        if q.get('part_type')!='Profile' or q['name'].endswith('_Profile'):continue
        if not any(t in q['name'].lower() for t in ('frame','leg','post','rail','cross','brace','stand','stringer')):continue
        u,v,n=q['axes'];w,h=q['profile_section_mm'];start,end=q['profile_ends']
        for i,p in enumerate((start,plus(end,scale(n,-60)))):
            o=plus(p,plus(scale(u,w/2),scale(v,-20)))
            before=len(specs)
            angle_joint(specs,q['name']+f'_Connection_Bracket_{i}',o,(n,u,v),45,5,40)
            for extra in specs[before:]:extra['moving_with_hood']=q.get('moving_with_hood',False)
    for q in specs:
        category,typ,family=functional_path(q)
        q.update(category=category,part_type=typ,family=family)
    names=[q['name'] for q in specs]
    if len(names)!=len(set(names)):raise ValueError(f"{meta['name']}: duplicate component names")
    return specs

def canonical(value):
    if isinstance(value,float):return round(value,8)
    if isinstance(value,dict):return {k:canonical(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [canonical(v) for v in value]
    return value

def geometry_key(spec):
    metadata={'name','origin','axes','group','profile_ends','profile_section_mm','moving_with_hood'}
    return hashlib.sha256(json.dumps(canonical({k:v for k,v in spec.items() if k not in metadata}),sort_keys=True).encode()).hexdigest()

def model_signature(specs):
    return hashlib.sha256(json.dumps(canonical(specs),sort_keys=True).encode()).hexdigest()

def model_bounds(specs):
    """CAD-data bounds, conservative for quarter-helical flights."""
    low=[float('inf')]*3;high=[-float('inf')]*3
    for q in specs:
        u,v,n=q['axes'];p=q['origin']
        if q['kind']=='poly':
            points=[transform_point((x,y,z),p,q['axes']) for x,y in q['points'] for z in (0,q['depth'])]
            lo=[min(p[i] for p in points) for i in range(3)];hi=[max(p[i] for p in points) for i in range(3)]
        else:
            if q['kind']=='helix':
                a=plus(p,scale(n,-q['thickness']/2));b=plus(p,scale(n,q['pitch']/4+q['thickness']/2))
            else:a=p;b=plus(p,scale(n,q['depth']))
            ext=[q['radius']*math.hypot(u[i],v[i]) for i in range(3)]
            lo=[min(a[i],b[i])-ext[i] for i in range(3)];hi=[max(a[i],b[i])+ext[i] for i in range(3)]
        low=[min(low[i],lo[i]) for i in range(3)];high=[max(high[i],hi[i]) for i in range(3)]
    return dict(minimum_mm=low,maximum_mm=high,size_mm=[high[i]-low[i] for i in range(3)],
                note='Bounds of generated static parts including brackets and drives; helical flights use conservative circular bounds.')

def existing_station(base,meta,signature):
    from review_layout import status_path
    candidates=[];status=status_path(base)
    if not status.exists():status=base/'BUILD_STATUS.json'  # Legacy read-only compatibility.
    if status.exists():
        record=json.loads(status.read_text(encoding='utf-8')).get(meta['name'],{})
        if record.get('product'):candidates.append(Path(record['product']))
    candidates.append(base/meta['name']/meta.get('product_filename',meta['name']+'.CATProduct'))
    for path in candidates:
        info=path.parent/'MODEL_INFO.json'
        if path.is_file() and info.is_file():
            record=json.loads(info.read_text(encoding='utf-8'))
            if record.get('model_signature')==signature:
                return dict(record,product=str(path.resolve()))
    return None

def product_group(spec):
    """Explicit groups for 6-8; functional classification for legacy 1/2/9."""
    if spec.get('group'):return spec['group']
    name=spec['name'].lower()
    if 'control' in name:return 'Electrical Controls'
    if 'hood_jack' in name:return 'Hood Lift System'
    if 'hood' in name or 'exhaust' in name:return 'Hood and Exhaust'
    if any(key in name for key in ('drive','motor','gearbox','fan_cover')):return 'Drive System'
    if 'paddle' in name:return 'Metering System'
    if any(key in name for key in ('oil_connection','water_inlet','tank_drain')):return 'Fluid Connections'
    if any(key in name for key in ('frame','foot','level','brace','stand_riser')):return 'Support Frame'
    if 'access' in name:return 'Service Covers'
    if 'hopper' in name or 'top_rim' in name or 'top_end_rim' in name:return 'Hopper'
    if any(key in name for key in ('pan','cladding','insulation','tank')):return 'Process Tank'
    if 'screw' in name:return 'Screw Elevator'
    if any(key in name for key in ('outfeed','discharge','draining','exit_lip')):return 'Outfeed'
    if 'infeed' in name:return 'Infeed'
    if 'submerger' in name:return 'Submerger Conveyor'
    if any(key in name for key in ('belt','conveyor','transfer','live_bottom')):return 'Process Conveyor'
    return 'Main Structure'


def build_engineering_specs(catia,specs,meta,base,rebuild=False):
    index=int(meta['name'][:2])
    signature=hashlib.sha256((model_signature(specs)+'|rib-v1|'+meta.get('input_sha256','')).encode()).hexdigest()
    if not rebuild:
        found=existing_station(base,meta,signature)
        if found:
            print('REUSE '+found['product'],flush=True)
            return open_document(catia,Path(found['product'])),found
    folder=new_folder(base,meta['name'])
    product_path=folder/(meta['name']+'.CATProduct')
    if index==1:
        from station1_design import write_report
        report_path,_=write_report(folder,VBK_CONFIG)
    elif index==2:
        from station2_design import write_report
        report_path,_=write_report(folder,SO_CONFIG)
    elif index in (3,4):
        from peeler_design import write_report
        report_path,_=write_report(index,folder,CRP_CONFIG if index==3 else MS_CONFIG)
    else:
        from finishing_design import write_report
        report_path,_=write_report(index,folder,meta['engineering_inputs'],specs,meta)
    print('SAVED DESIGN REPORT '+str(report_path),flush=True)
    doc=catia.Documents.Add('Product');root=doc.Product;root.PartNumber=meta['name']
    root.Nomenclature=meta['description'];cache={};created=0;completed=0
    grouped={};subassemblies=[]
    for spec in specs:grouped.setdefault(product_group(spec),[]).append(spec)
    subfolder=folder/'Subassemblies';subfolder.mkdir(parents=True,exist_ok=True)
    identity=tuple(q for a in I for q in a)+(0.,0.,0.)
    for group_no,(group_name,members) in enumerate(grouped.items(),1):
        slug=group_name.replace(' ','_')
        group_path=subfolder/f'{group_no:02d}_{slug}.CATProduct'
        group_doc=catia.Documents.Add('Product');group_product=group_doc.Product
        group_product.PartNumber=meta['name']+'_'+slug
        group_product.Nomenclature=group_name
        for i,spec in enumerate(members,1):
            # A grouping change must not turn equal geometry into extra CATParts.
            geometry={k:v for k,v in spec.items() if k not in ('name','origin','axes','group')}
            key=hashlib.sha256(json.dumps(geometry,sort_keys=True).encode()).hexdigest()
            try:
                if key not in cache:
                    path=folder/'Parts'/slug/(spec['name']+'.CATPart')
                    prefix=f'{index:02d}_'
                    part_number=spec['name'] if spec['name'].startswith(prefix) else prefix+spec['name']
                    pdoc=create_part(catia,spec,path,part_number);cache[key]=path;created+=1
                else:
                    path=cache[key];pdoc=catia.Documents.Open(str(path))
                comp=group_product.Products.AddExternalComponent(pdoc)
                comp.Name=f'{i:03d}_{spec["name"]}'
                # All group roots use the equipment datum; no transform is applied twice.
                comp.Position.SetComponents(tuple(q for a in spec['axes'] for q in a)+tuple(spec['origin']))
                pdoc.Close()
            except Exception as exc:
                raise RuntimeError(f'{meta["name"]} / {group_name} / {spec["name"]}: {exc}') from exc
            completed+=1
            if completed%20==0:print(f'{meta["name"]}: {completed}/{len(specs)} components [{group_name}]',flush=True)
        group_product.Update();group_doc.SaveAs(str(group_path))
        assembly=root.Products.AddExternalComponent(group_doc)
        assembly.Name=group_name;assembly.Position.SetComponents(identity)
        group_doc.Close()
        subassemblies.append(dict(name=group_name,components=len(members),product=str(group_path)))
        print('SAVED SUBASSEMBLY '+str(group_path),flush=True)
    root.Update();doc.SaveAs(str(product_path))
    meta.update(generator_revision=REVISION,model_signature=signature,helix_builder='Native Rib / analytical helix',components=len(specs),unique_catparts=created,product=str(product_path),
                sketch_constraints='Driving XY coordinates and circle radii; no fake sketch colours',
                planes_and_sketches='Hidden',subassemblies=subassemblies,
                product_structure='Equipment / functional CATProduct / editable CATPart')
    (folder/'MODEL_INFO.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
    update_status(base,meta['name'],meta)
    archive=pack(folder)
    print('SAVED '+str(product_path),flush=True);print('ZIP '+str(archive),flush=True)

    return doc,meta


def build_specs(catia,specs,meta,base,rebuild=False):
    specs=prepare_specs(specs,meta);signature=model_signature(specs)
    if not rebuild:
        found=existing_station(base,meta,signature)
        if found:
            print('REUSE '+found['product'],flush=True)
            return open_document(catia,Path(found['product'])),found
    folder=new_folder(base,meta['name']);product_path=folder/(meta['name']+'.CATProduct')
    doc=catia.Documents.Add('Product');root=doc.Product;root.PartNumber=meta['name'];root.Nomenclature=meta['description']
    # All subproducts are embedded and saved with the root CATProduct. Parts
    # remain external native CATParts. No active-document switch changes parents.
    products={};groups={};cache={};serials={};counts={};component_records=[]
    labels={'Frame':'1_Frame','Internal':'2_Internal_Geometry','External':'3_External_Controls'}
    types=('Profile','Plate','Bracket','Fastener','Bearing','Seal','Pipe','Conveyor','Mechanism','Auger','Shell','Transmission','Drive','Control')
    for cat,label in labels.items():
        sub=root.Products.AddNewProduct(meta['name']+'_'+label);sub.Name=label;products[(cat,)]=sub
    for i,q in enumerate(specs,1):
        cat,typ,family=q['category'],q['part_type'],q['family'];family_key=(cat,typ,family)
        if (cat,typ) not in products:
            idx=types.index(typ)+1 if typ in types else len(types)+1
            label=f'{labels[cat][0]}-{idx}_{typ}'
            sub=products[(cat,)].Products.AddNewProduct(meta['name']+'_'+label);sub.Name=label
            products[(cat,typ)]=sub
        if family_key not in products:
            sub=products[(cat,typ)].Products.AddNewProduct(meta['name']+'_'+typ+'_'+family);sub.Name=family
            products[family_key]=sub
        parent=products[family_key];key=geometry_key(q)
        print(f'{meta["name"]}: {i}/{len(specs)} {q["name"]}',flush=True)
        try:
            if key not in cache:
                serials[family_key]=serials.get(family_key,0)+1
                part_number=f'{meta["name"][:2]}_{cat[0]}_{typ}_{family}_P{serials[family_key]:03d}'
                path=folder/'Parts'/(part_number+'.CATPart')
                pdoc=create_part(catia,q,path,part_number)
                comp=parent.Products.AddExternalComponent(pdoc);cache[key]=comp.ReferenceProduct
                doc.Activate();pdoc.Close()
            else:comp=parent.Products.AddComponent(cache[key])
            counts[family_key]=counts.get(family_key,0)+1
            comp.Name=f'{family}_{counts[family_key]:03d}'
            comp.DescriptionInst=q['name'];place(comp,q['origin'],q['axes'])
            component_records.append(dict(source_name=q['name'],instance=comp.Name,group=family_key,reference_key=key,
                                          origin_mm=q['origin'],moving_with_hood=q.get('moving_with_hood',False)))
            if i%50==0:doc.SaveAs(str(product_path))
        except Exception as exc:
            try:doc.SaveAs(str(product_path))
            except Exception:pass
            raise RuntimeError(f'Failed component {i}/{len(specs)}: {q["name"]}; partial work is preserved in {folder}') from exc
    root.Update();doc.SaveAs(str(product_path))
    result=dict(meta,generator_revision=REVISION,product=str(product_path.resolve()),components=len(specs),unique_catparts=len(cache),model_bounds=model_bounds(specs),
                model_signature=signature,product_structure='Frame/Internal Geometry/External Controls -> type -> function -> repeated instances',
                profile_representation='Native Pad from specified closed contours; welded hollow members use outer/inner loops and separate end caps.',
                sketch_constraints='Driving vertex X/Y and circle radius/center dimensions; coincident zero coordinates; no Fix or sketch-colour workaround.',
                instances=component_records)
    (folder/'MODEL_INFO.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    update_status(base,meta['name'],result)
    print('SAVED '+str(product_path),flush=True)
    return doc,result

def station_specs(index,**options):
    if index==5:return station5(options.get('slice_thickness'))
    if index==9:return station9(options.get('fryer_model','PC4'),options.get('hood_lift',0.),options.get('hood_transparent',False))
    if index==11:return station11(options.get('seasoning_angle',40.))
    return {1:station1,2:station2,3:station3,4:station4,6:station6,7:station7,8:station8,10:station10}[index]()

def build_station(catia,index,base=BASE,rebuild=False,**options):
    if index==5:return build_station5(catia,base,rebuild,options.get('slice_thickness'))
    specs,meta=station_specs(index,**options)
    return build_engineering_specs(catia,specs,meta,base,rebuild)

def transfer_between(index,upstream,downstream):
    """Ground-based connecting conveyor with no imposed station elevation shift."""
    z0=upstream['outlet'][2];z1=downstream['inlet'][2]
    width0=upstream.get('outlet_width_mm',600.);width1=downstream.get('inlet_width_mm',600.)
    run=max(500.,abs(z1-z0)/.28+300.);width=max(width0,width1)
    s=[];name=f'Transfer_{index:02d}_{index+1:02d}';est=dict(PREP_ESTIMATES)
    p0=(0.,0.,z0);p1=(run,0.,z1);belt0=(80.,0.,z0);belt1=(run-80,0.,z1)
    prep_tapered_chute(s,name+'_Entry',p0,belt0,width0,width,120)
    fryer_conveyor(s,name+'_Conveyor',belt0,belt1,width,35,est,width+300,True)
    continuous_guides(s,name+'_Guard',(belt0,belt1),width,120)
    prep_tapered_chute(s,name+'_Exit',belt1,p1,width,width1,120)
    for x,z in ((80,z0),(run-80,z1)):
        for side in (-1,1):
            y=side*(width/2+35)
            bolted_support(s,name+f'_Leg_{x:g}_{side}',(x,y,30),(x,y,z-70),50)
            s.append(box(name+f'_Foot_{x:g}_{side}',(x-55,y-55,12),(110,110,18)))
        bolted_support(s,name+f'_Cross_{x:g}',(x,-width/2-35,z-95),(x,width/2+35,z-95),45)
    from finishing_design import weld_and_assign,configuration
    s=weld_and_assign(6,s,configuration(6))
    return s,dict(name=name,description='Estimated welded SUS304 transfer conveyor between actual equipment ports.',
                  inlet=p0,outlet=p1,inlet_width_mm=width0,outlet_width_mm=width1,length=run)

def line_placements(metas,transfers):
    # Engineered stations 1/2 and imported stations 3-11 all convey along +X.
    # Align actual port locations without changing any station floor datum.
    turn=I;stations={1:((0.,0.,0.),I)};links={}
    for index in range(1,len(metas)):
        out=transform_point(metas[index]['outlet'],*stations[index])
        axes=I if index==1 else turn
        link_origin=vec(transform_point(transfers[index]['inlet'],axes=axes),out)
        links[index]=(link_origin,axes)
        inlet_world=transform_point(transfers[index]['outlet'],link_origin,axes)
        station_axes=turn
        station_origin=vec(transform_point(metas[index+1]['inlet'],axes=station_axes),inlet_world)
        stations[index+1]=(station_origin,station_axes)
    return dict(stations=stations,transfers=links)

def export_step(doc,product_path):
    path=Path(product_path);target=path.with_suffix('.stp');n=1
    while target.exists():target=path.with_name(f'{path.stem}_{n:02d}.stp');n+=1
    try:doc.ExportData(str(target),'stp')
    except Exception as exc:raise RuntimeError(f'Native model saved at {path}; STEP export failed. Check CATIA STEP license/settings.') from exc
    print('STEP '+str(target),flush=True)

def build_assembly(catia,base=BASE,rebuild=False,through=11,step=False,**options):
    if options.get('hood_lift',0):raise ValueError('Full line assembly requires --hood-lift 0; use --stage 9 for a service pose.')
    docs={};metas={};tdocs={};tmetas={};dependencies=[]
    for i in range(1,through+1):
        doc,meta=build_station(catia,i,base,rebuild,**options);docs[i]=doc;metas[i]=meta
        dependencies.append(Path(meta['product']).parent)
        if step:export_step(doc,meta['product'])
    for i in range(1,through):
        s,m=transfer_between(i,metas[i],metas[i+1])
        tdocs[i],tmetas[i]=build_specs(catia,s,m,base,rebuild)
        dependencies.append(Path(tmetas[i]['product']).parent)
    locations=line_placements(metas,tmetas);name='Potato_Line_01_'+f'{through:02d}'
    folder=new_folder(base,name);path=folder/(name+'.CATProduct')
    doc=catia.Documents.Add('Product');root=doc.Product;root.PartNumber=name
    root.Nomenclature='Integrated potato chips process line with separately saved machine assemblies'
    for i in range(1,through+1):
        c=root.Products.AddExternalComponent(docs[i]);c.Name=metas[i]['name'];place(c,*locations['stations'][i])
        if i<through:
            c=root.Products.AddExternalComponent(tdocs[i]);c.Name=tmetas[i]['name'];place(c,*locations['transfers'][i])
    root.Update();doc.SaveAs(str(path))
    info=dict(name=name,generator_revision=REVISION,product=str(path.resolve()),
              stations=[metas[i]['product'] for i in metas],transfers=[tmetas[i]['product'] for i in tmetas],placements_mm=locations,
              layout_note='Estimated transfer lengths reconcile actual model ports; floor-level placements; not a surveyed factory layout.')
    (folder/'MODEL_INFO.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    update_status(base,name,info);return doc,info,dependencies

def main():
    global BASE,VBK_CONFIG,SO_CONFIG,CRP_CONFIG,MS_CONFIG,FINISH_CONFIGS
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    action=ap.add_mutually_exclusive_group()
    action.add_argument('--stage',type=int,choices=range(1,12))
    action.add_argument('--stages',type=int,nargs='+',choices=range(1,12))
    action.add_argument('--all',action='store_true',help='save eleven separate machine assemblies')
    action.add_argument('--assemble',action='store_true',help='save machines and the full line')
    action.add_argument('--clean',nargs='?',const='all',choices=('all','models','reports'),
                        help='delete recognized generated outputs only; does not build or open CATIA')
    ap.add_argument('--dry-run',action='store_true',help='with --clean, preview without deleting anything')
    ap.add_argument('--through',type=int,choices=range(1,12),default=None)
    ap.add_argument('--fryer-model',choices=tuple(FRYER_MODELS),default='PC4')
    ap.add_argument('--hood-lift',type=float,default=0.)
    ap.add_argument('--hood-transparent',action='store_true')
    ap.add_argument('--seasoning-angle',type=float,default=40.)
    ap.add_argument('--slice-thickness',type=float,choices=(1.5,),default=None,
                    help='Station 5 CC R16: fixed slicing gap 1.5 mm')
    ap.add_argument('--output-dir',type=Path,default=BASE)
    ap.add_argument('--rebuild',action='store_true')
    ap.add_argument('--step',action='store_true')
    ap.add_argument('--zip',action='store_true')
    ap.add_argument('--vbk-config',type=Path)
    ap.add_argument('--so-config',type=Path)
    ap.add_argument('--crp-config',type=Path)
    ap.add_argument('--ms-config',type=Path)
    ap.add_argument('--finish-config',type=Path,help='JSON object keyed by station number 5..11')
    ap.add_argument('--report-only',action='store_true',help='station 1-11 reports without CATIA')
    args=ap.parse_args()
    if args.clean:
        # Cleanup is a separate action and must exit before reports/default stage/COM.
        if (args.through is not None or args.rebuild or args.step or args.zip or args.report_only or
            any((args.vbk_config,args.so_config,args.crp_config,args.ms_config,args.finish_config)) or
            args.hood_lift or args.hood_transparent or args.fryer_model!='PC4' or
            args.seasoning_angle!=40. or args.slice_thickness is not None):
            ap.error('--clean accepts only --dry-run and --output-dir; use a separate command to build')
        from clean_outputs import clean
        try:result=clean(args.output_dir,args.clean,args.dry_run)
        except (OSError,ValueError) as exc:ap.error(str(exc))
        if result['errors']:raise SystemExit(1)
        return
    if args.dry_run:ap.error('--dry-run requires --clean')
    if args.stage is None and not args.stages and not args.all and not args.assemble:
        args.stage=1;args.report_only=True
    assemble=args.assemble
    if args.through is not None and not assemble:ap.error('--through requires --assemble')
    if assemble and args.hood_lift:ap.error('--hood-lift is for separate station 9 service poses')
    if not 0<=args.hood_lift<=650:ap.error('--hood-lift must be 0..650')
    if not 38<=args.seasoning_angle<=50:ap.error('--seasoning-angle must be 38..50')
    requested=(list(range(1,(args.through or 11)+1)) if assemble else
               (list(range(1,12)) if args.all else (args.stages or [args.stage])))
    if len(requested)!=len(set(requested)):ap.error('--stages must not contain duplicate station numbers')
    if args.report_only and assemble:ap.error('--report-only uses --stage, --stages or --all; not --assemble')
    if args.vbk_config and 1 not in requested:ap.error('--vbk-config requires station 1')
    if args.so_config and 2 not in requested:ap.error('--so-config requires station 2')
    if args.crp_config and 3 not in requested:ap.error('--crp-config requires station 3')
    if args.ms_config and 4 not in requested:ap.error('--ms-config requires station 4')
    if 9 not in requested and (args.hood_lift or args.hood_transparent or args.fryer_model!='PC4'):
        ap.error('Fryer options require station 9')
    BASE=base=args.output_dir.expanduser().resolve()
    from review_layout import migrate_legacy,station_folder,write_index as write_full_index
    base.mkdir(parents=True,exist_ok=True)
    migrate_legacy(base)
    FINISH_CONFIGS={}
    if args.finish_config:
        try:
            raw=json.loads(args.finish_config.read_text(encoding='utf-8-sig'))
            if not isinstance(raw,dict) or any(k not in tuple(map(str,range(5,12))) for k in raw):
                raise ValueError('finish-config must contain station keys "5".."11"')
            if any(not isinstance(v,dict) for v in raw.values()):
                raise ValueError('Each finish-config station value must be a JSON object')
            FINISH_CONFIGS={int(k):v for k,v in raw.items()}
        except (OSError,ValueError,TypeError) as exc:ap.error(str(exc))
    for index in range(5,12):
        if index not in requested:continue
        from finishing_design import configuration,write_report,write_index,NAMES
        try:
            c=dict(FINISH_CONFIGS.get(index,{}))
            if index==5:
                # Previous belt-slicer configuration cannot define the new centrifugal mechanism.
                if 'machine_other_mass_kg' in c or 'slice_thickness_mm' in c or c.get('blade_count')==10:
                    print('Station 5: obsolete belt-slicer inputs ignored; using CC R16 inputs.',flush=True)
                    c={}
                if args.slice_thickness is not None:c['slice_mm']=args.slice_thickness
            if index==9:
                if args.fryer_model!='PC4' or 'fryer_model' not in c:c['fryer_model']=args.fryer_model
            if index==11:
                if args.seasoning_angle!=40. or 'seasoning_angle_deg' not in c:c['seasoning_angle_deg']=args.seasoning_angle
            FINISH_CONFIGS[index]=configuration(index,c)
            if index==5:args.slice_thickness=FINISH_CONFIGS[5]['slice_mm']
            if index==9:args.fryer_model=FINISH_CONFIGS[9]['fryer_model']
            if index==11:args.seasoning_angle=FINISH_CONFIGS[11]['seasoning_angle_deg']
            report_args={}
            if index==9:
                from finishing_design import station_geometry
                sp,mt=station_geometry(9,FINISH_CONFIGS[9],hood_lift=args.hood_lift,hood_transparent=args.hood_transparent)
                report_args=dict(specs=sp,meta=mt)
            report,r=write_report(index,station_folder(base,index),FINISH_CONFIGS[index],**report_args)
            print('SAVED DESIGN REPORT '+str(report),flush=True)
            write_index(base)
            for warning in r['warnings']:print('DESIGN REVIEW: '+warning,flush=True)
        except (OSError,ValueError,TypeError) as exc:ap.error(f'Station {index} report: {exc}')
    # Reports are saved before attempting COM import or activating CATIA.
    for index,config_path,report_name in ((1,args.vbk_config,'01_VBK_Design_Review'),
                                          (2,args.so_config,'02_SO_Design_Review'),
                                          (3,args.crp_config,'03_CRP_Design_Review'),
                                          (4,args.ms_config,'04_MS_Design_Review')):
        if index not in requested:continue
        if index==1:
            from station1_design import configuration,write_report
        elif index==2:
            from station2_design import configuration,write_report
        else:
            import peeler_design
            configuration=lambda overrides:peeler_design.configuration(index,overrides)
            write_report=lambda folder,config:peeler_design.write_report(index,folder,config)
        try:
            overrides=json.loads(config_path.read_text(encoding='utf-8-sig')) if config_path else {}
            config=configuration(overrides)
            if index==1:VBK_CONFIG=config
            elif index==2:SO_CONFIG=config
            elif index==3:CRP_CONFIG=config
            else:MS_CONFIG=config
            report_path,calculation=write_report(station_folder(base,index),config)
        except (OSError,ValueError,TypeError) as exc:
            ap.error(f'Station {index} configuration/report: {exc}')
        print('SAVED DESIGN REPORT '+str(report_path),flush=True)
        write_full_index(base)
        for warning in calculation['warnings']:print('DESIGN REVIEW: '+warning,flush=True)
    if args.report_only:return
    try:
        import pythoncom
        import win32com.client as win32
    except ImportError as exc:raise SystemExit('Install pywin32: py -m pip install pywin32') from exc
    base.mkdir(parents=True,exist_ok=True)
    opts=dict(fryer_model=args.fryer_model,hood_lift=args.hood_lift,hood_transparent=args.hood_transparent,
              seasoning_angle=args.seasoning_angle,slice_thickness=args.slice_thickness)
    pythoncom.CoInitialize()
    try:
        try:catia=win32.GetActiveObject('CATIA.Application')
        except Exception:catia=win32.Dispatch('CATIA.Application')
        old_alerts=catia.DisplayFileAlerts;catia.DisplayFileAlerts=False;catia.Visible=True
        try:
            if assemble:
                doc,meta,deps=build_assembly(catia,base,args.rebuild,args.through or 11,args.step,**opts)
                if args.step:export_step(doc,meta['product'])
                if args.zip:print('ZIP '+str(pack(Path(meta['product']).parent,deps)),flush=True)
            else:
                for index in requested:
                    doc,meta=build_station(catia,index,base,args.rebuild,**opts)
                    if args.step:export_step(doc,meta['product'])
                    if args.zip and index==5:print('ZIP '+str(pack(Path(meta['product']).parent)),flush=True)
            show_document(catia,doc);print('DONE: saved CATProduct is open in CATIA.',flush=True)
        finally:catia.DisplayFileAlerts=old_alerts
    finally:pythoncom.CoUninitialize()

if __name__=='__main__':
    try:main()
    except Exception:
        traceback.print_exc()
        print('Build stopped. Completed machines and partial parts were preserved.',file=sys.stderr)
        if sys.stdin.isatty():
            try:input('Press Enter to close this console...')
            except (EOFError,KeyboardInterrupt):pass
        raise SystemExit(1)
