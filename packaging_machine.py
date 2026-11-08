# -*- coding: utf-8 -*-
"""CATIA V5 감자칩 포장기: 원형 독립 계량 10채널 + 포장기 10대.

파일 하나만 필요합니다. Windows CPython + pywin32, 실행 중인 CATIA V5가 필요합니다.
실행: py packaging_machine.py
코드 검사: py packaging_machine.py --self-test
CATIA 없는 미리보기: py packaging_machine.py --dry-run
대표 형상 시험 생성: py packaging_machine.py --smoke-test

출력: 12_Packaging_10Line/12_Packaging_10Line.CATProduct
      12_Packaging_10Line/Parts/*.CATPart
      12_Packaging_10Line.zip
기존 결과가 있으면 generated_날짜_시각 폴더 아래 새로 저장합니다.

원형 배치: 각 Line_01~Line_10은 독립 순중량 계량부 1개와 VFFS 포장기 1대입니다.
10개 호퍼의 조합으로 한 봉을 채우던 구조를 독립 계량 방식으로 변경했습니다.
각 계량부 -> 전용 중공 슈트 -> 같은 번호의 포장기로 연결됩니다.
공통 경사벨트 1대 -> 중앙 분배부 -> 독립 진동 분배통로 10개 -> 각 라인 버퍼.
분배통로는 벨트가 아닙니다. 경사벨트는 폭800 / 종동롤러50 / 구동풀리100 mm.
색상, 볼트 브라켓, 단일 폐곡선 Pad 프로파일과 공유 참조 부품을 유지합니다.
작업대 외경10100 mm, 포장기 배치 반경4000 mm, 작업대 높이2200 mm는 개념 설계값입니다.
85g/봉, 30봉/분/대는 목표값입니다. 합계300봉/분이나 실측 성능 보장이 아닙니다.
CAD 개념 모델이며 실제 자동 운전 PLC, DMU, 제작 검증, 전체 간섭 검사를 포함하지 않습니다.
"""
from __future__ import annotations


# ============================================================================
# MODEL AND GEOMETRY
# ============================================================================


from dataclasses import dataclass, field, asdict
from math import sin, cos, sqrt, pi, acos, atan2, ceil, isfinite
from collections import Counter
import json

ROOT_NAME = "12_Packaging_10Line"
DEFAULTS = {
    "belt_width": 800.0,
    "roller_diameter": 50.0,
    "drive_pulley_diameter": 100.0,
    "belt_thickness": 3.0,
    "conveyor_tail": [-11200.0, 0.0, 450.0],
    "conveyor_head": [-350.0, 0.0, 5700.0],
    "line_count": 10,
    "station_radius": 4000.0,
    "platform_inner_radius": 2750.0,
    "platform_outer_radius": 5050.0,
    "platform_deck_z": 2200.0,
    "nominal_fill_g": 85.0,
    "target_bags_per_min_per_line": 30.0,
    "assumed_effective_factor": 0.75,
}

X, Y, Z = (1., 0., 0.), (0., 1., 0.), (0., 0., 1.)
ZERO = (0., 0., 0.)
# Display colors only; these do not assign physical CATIA materials.
# Edit these RGB values to recolor the next generated assembly and CATParts.
SILVER = (192, 201, 212)   # Aluminium profiles, shafts and rollers
PLATE = (214, 220, 225)    # Stainless sheet, hoppers and platform
BRACKET = (55, 66, 82)    # Connection brackets and bearing housings
BLUE = (25, 98, 210)      # Conveyor belt and drive motors
DARK = (61, 68, 79)
BLACK = (39, 44, 51)
ORANGE = (246, 155, 38)   # Seal heaters and functional highlights
CABINET = (236, 239, 242)
SCREEN = (30, 184, 220)
FILM = (239, 231, 208)

def add(a, b): return tuple(x+y for x, y in zip(a, b))
def sub(a, b): return tuple(x-y for x, y in zip(a, b))
def mul(a, s): return tuple(x*s for x in a)
def dot(a, b): return sum(x*y for x, y in zip(a, b))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def norm(a): return sqrt(dot(a, a))
def unit(a):
    n = norm(a)
    if n < 1e-9: raise ValueError("Zero length direction")
    return mul(a, 1/n)
def num(n): return f"{n:.3f}".rstrip('0').rstrip('.').replace('.', 'p')

def pose(p=ZERO, x=X, y=Y, z=Z): return tuple(x)+tuple(y)+tuple(z)+tuple(p)
def apply(m, p): return tuple(m[9+i]+m[i]*p[0]+m[3+i]*p[1]+m[6+i]*p[2] for i in range(3))
def direction(m, p): return tuple(m[i]*p[0]+m[3+i]*p[1]+m[6+i]*p[2] for i in range(3))
def compose(a, b):
    return pose(apply(a, b[9:]), direction(a, b[:3]), direction(a, b[3:6]), direction(a, b[6:9]))

def along(p, axis, x_hint=X):
    z = unit(axis)
    if abs(dot(unit(x_hint), z)) > .99: x_hint = Y
    x = unit(sub(x_hint, mul(z, dot(x_hint, z))))
    return pose(p, x, cross(z, x), z)

def rect(w, h): return [(-w/2,-h/2), (w/2,-h/2), (w/2,h/2), (-w/2,h/2)]
def poly(points): return {"type": "polygon", "points": [list(p) for p in points]}
def circle(r, center=(0., 0.)): return {"type":"circle", "radius":r, "center":list(center)}

def pad(loops, length, origin=ZERO, u=X, v=Y, name="Pad"):
    return {"op":"pad", "loops":loops, "length":float(length),
            "origin":origin, "u":u, "v":v, "name":name}

def pocket(loops, depth, origin, u=X, v=Y, name="Pocket"):
    result = pad(loops, depth, origin, u, v, name)
    result["op"] = "pocket"
    return result

def box_feature(w,h,t,origin=ZERO,name="Plate"):
    return pad([poly(rect(w,h))],t,origin,name=name)

def ring_feature(ro,ri,length,origin=ZERO,name="Ring"):
    loops = [circle(ro)] + ([circle(ri)] if ri else [])
    return pad(loops,length,origin,name=name)

def tslot_outline(w,h):
    """One simple closed outline; external T slots, no disconnected contours.
    Concept section. 40 mm sides: one slot, 80 mm sides: two slots.
    Central extrusion chambers are deliberately omitted.
    """
    def edge(length, depth):
        centers = [-20.,20.] if length >= 79.9 else [0.]
        result = [(-length/2,depth)]
        for c in centers:
            result += [(c-5,depth),(c-5,depth-4),(c-9,depth-4),
                       (c-9,depth-10),(c+9,depth-10),(c+9,depth-4),
                       (c+5,depth-4),(c+5,depth)]
        result += [(length/2,depth)]
        return result
    a = edge(w,h/2)
    b = [(y,-x) for x,y in edge(h,w/2)]
    c = [(-x,-y) for x,y in edge(w,h/2)]
    d = [(-y,x) for x,y in edge(h,w/2)]
    return list(reversed(a[:-1]+b[:-1]+c[:-1]+d[:-1]))

def belt_loop(length, r0, r1):
    """Exact common tangents + circular end wraps (unequal pulleys)."""
    a = acos((r0-r1)/length)
    p0u=(r0*cos(a), r0*sin(a)); p0d=(r0*cos(a),-r0*sin(a))
    p1u=(length+r1*cos(a),r1*sin(a)); p1d=(length+r1*cos(a),-r1*sin(a))
    return {"type":"segments", "segments":[
        {"type":"arc","center":[0.,0.],"radius":r0,"a0":a,"a1":2*pi-a},
        {"type":"line","p0":p0d,"p1":p1d},
        {"type":"arc","center":[length,0.],"radius":r1,"a0":2*pi-a,"a1":2*pi+a},
        {"type":"line","p0":p1u,"p1":p0u}]}

@dataclass
class PartSpec:
    name: str
    features: list
    color: tuple = SILVER
    note: str = ""
    kind: str = "general"
    parameters: dict = field(default_factory=dict)

@dataclass
class Occurrence:
    part: str
    path: tuple
    matrix: tuple

class Model:
    def __init__(self, config=None):
        self.cfg = {**DEFAULTS, **(config or {})}
        self.parts = {}
        self.occ = []
        self.contacts = []
        self.bearing_sets = []
        self.transform = pose()
        self.station = None
        self.connections = []
        self.platform_openings = []
        self.feed_routes = []
        self.smoke_only = False
        if self.cfg["line_count"] != 10:
            raise ValueError("This reviewed radial layout requires exactly 10 lines.")
        if self.cfg["station_radius"] < 4000:
            raise ValueError("Station radius must be at least 4000 mm for this bagger envelope.")
        if not 0 < self.cfg["assumed_effective_factor"] <= 1:
            raise ValueError("Effective factor must be in (0, 1].")
        if self.cfg["nominal_fill_g"] <= 0 or self.cfg["target_bags_per_min_per_line"] <= 0:
            raise ValueError("Fill mass and speed targets must be positive.")

    def define(self, p):
        if p.name in self.parts and asdict(self.parts[p.name]) != asdict(p):
            raise ValueError("Part-name collision: " + p.name)
        self.parts[p.name] = p
        return p.name

    def put(self, name, path, m):
        self.occ.append(Occurrence(name, tuple(path)+(name+"_Group",), compose(self.transform,tuple(m))))

    def group(self, category, system, subtype=None):
        roots={"Profile":("01_Frame","01_Profile"), "Plate":("01_Frame","02_Plate"),
               "Bracket":("01_Frame","03_Bracket"), "Fastener":("01_Frame","04_Fastener"),
               "Spacer":("01_Frame","05_Spacer"), "Internal":("02_Internal",),
               "Control":("03_ExternalControl",)}
        return roots[category]+(system,)+((self.station,) if self.station else ())+((subtype,) if subtype else ())

    def simple_box(self,name,w,h,t,color=PLATE,holes=()):
        fs=[box_feature(w,h,t)]
        if holes:
            fs.append(pocket([circle(r,(x,y)) for x,y,r in holes],t,(0,0,t),name="MountingHoles"))
        return self.define(PartSpec(name,fs,color))

    def ring(self,name,ro,ri,length,color=SILVER):
        return self.define(PartSpec(name,[ring_feature(ro,ri,length)],color))

    def beam(self,system,role,a,b,w=80,h=80,hint=X):
        # Rotated copies share the same master despite floating-point roundoff.
        length=round(norm(sub(b,a)),3)
        name=f"Profile_{role}_{num(w)}x{num(h)}_L{num(length)}"
        p=PartSpec(name,[pad([poly(tslot_outline(w,h))],length,name="SingleOutlinePad")],
                   SILVER,"One closed profile, one Pad; shared references", "profile",
                   {"width":w,"height":h,"length":length})
        self.define(p); self.put(name,self.group("Profile",system),along(a,sub(b,a),hint))
        return name

    def bolt(self,system,p,axis,length=20):
        name=f"Bolt_M8_L{num(length)}_Simplified"
        self.define(PartSpec(name,[ring_feature(4,0,length),ring_feature(6.5,0,5,(0,0,length))],DARK,
                            "Thread omitted; nominal M8 envelope", "fastener"))
        self.put(name,self.group("Fastener",system),along(p,axis))

    def tnut(self,system,p,axis):
        name=self.simple_box("Tnut_M8_18x10x6",18,10,6,DARK,[(0,0,3.4)])
        self.put(name,self.group("Fastener",system),along(p,axis))

    def bracket(self,system,m,leg=40,width=40,thick=6,fasteners=True):
        name=f"Bracket_L{num(leg)}_W{num(width)}_T{num(thick)}"
        outline=[(0,0),(leg,0),(leg,thick),(thick,thick),(thick,leg),(0,leg)]
        fs=[pad([poly(outline)],width,name="LBracketPad")]
        # Each hole cuts opposite its sketch normal, through its bracket leg.
        fs += [pocket([circle(4.5,(leg*.65,width/2))],thick,(0,thick,0),X,(0,0,-1),"HorizontalHole")]
        # The first sketch uses -Z; its local y center is therefore -width/2.
        fs[-1]["loops"]=[circle(4.5,(leg*.65,-width/2))]
        fs += [pocket([circle(4.5,(leg*.65,width/2))],thick,(thick,0,0),Y,Z,"VerticalHole")]
        self.define(PartSpec(name,fs,BRACKET,kind="bracket"))
        self.put(name,self.group("Bracket",system),m)
        if fasteners:
            for p,axis in [((leg*.65,thick-20,width/2),Y),((thick-20,leg*.65,width/2),X)]:
                self.bolt(system,apply(m,p),direction(m,axis))
            # The slots receive separate, reusable T-nut instances.
            self.tnut(system,apply(m,(leg*.65,-7,width/2)),direction(m,Y))
            self.tnut(system,apply(m,(-7,leg*.65,width/2)),direction(m,X))

    def flush_panel(self,system,name,w,h,t,m,stand_off=0):
        """Panel starts on mounting face. Explicit spacer fills any stand-off."""
        holes=[(sx*(w/2-18),sy*(h/2-18),4.5) for sx in (-1,1) for sy in (-1,1)]
        pn=self.simple_box(name,w,h,t,PLATE,holes)
        self.put(pn,self.group("Plate",system),compose(m,pose((0,0,stand_off))))
        if stand_off:
            sn=self.ring(f"Spacer_D18_d9_L{num(stand_off)}",9,4.5,stand_off,BRACKET)
            for x,y,_ in holes:
                self.put(sn,self.group("Spacer",system),compose(m,pose((x,y,0))))
        for x,y,_ in holes:
            bolt_length=max(20,ceil((stand_off+t+12)/5)*5)
            self.bolt(system,apply(m,(x,y,stand_off+t-bolt_length)),direction(m,Z),bolt_length)
        self.contacts.append({"joint":name,"gap":stand_off,"spacer":stand_off})

    def bearing_unit(self,system,m,shaft_d=25):
        """Cylindrical seat 52 x 22; 52 x 25 x 15 bearing; shoulder and cover.
        Local +Z points OUT from the roller. Flange at Z=30..38.
        """
        hn="Housing_D80_Seat52_Shoulder28_Flange100"
        fs=[ring_feature(40,26,22,name="CylindricalSeat"),
            ring_feature(40,14,8,(0,0,22),"ShaftShoulder"),
            pad([poly(rect(100,100)),circle(14)],8,(0,0,30),name="BoltedFlange"),
            pocket([circle(4.5,(x,y)) for x in (-38,38) for y in (-38,38)],8,(0,0,38),name="FlangeHoles")]
        self.define(PartSpec(hn,fs,BRACKET,"Stationary housing, not a stay-rod support","housing"))
        self.put(hn,self.group("Internal",system,"BearingHousing"),m)
        for name,ro,ri in [("Bearing_OuterRace_52x43x15",26,21.5),
                           ("Bearing_InnerRace_36x25x15",18,12.5),
                           ("Bearing_Seal_43x36x15",21.5,18)]:
            pn=self.ring(name,ro,ri,15,BLACK if "Seal" in name else SILVER)
            self.put(pn,self.group("Internal",system,"Bearing"),compose(m,pose((0,0,4))))
        cn=self.ring("Bearing_Cover_80x28x4",40,14,4,DARK)
        self.put(cn,self.group("Internal",system,"BearingCover"),compose(m,pose((0,0,-4))))
        for x in (-38,38):
            for y in (-38,38):
                self.bolt(system,apply(m,(x,y,18)),direction(m,Z),20)
        self.bearing_sets.append({"system":system,"shaft_d":shaft_d,"bearing_id":25,
                                  "bearing_od":52,"seat_d":52,"bearing_z":[4,19],"seat_z":[0,22]})

    def shaft_roller(self,system,role,diam,width,center,axis=Y,motor=False):
        a=unit(axis); half=width/2
        shaft_l=width+260
        roll=self.ring(f"{role}_D{num(diam)}_W{num(width)}",diam/2,12.5,width,SILVER)
        self.put(roll,self.group("Internal",system,"Roller"),along(add(center,mul(a,-half)),a))
        sh=self.ring(f"Shaft_D25_L{num(shaft_l)}",12.5,0,shaft_l,DARK)
        self.put(sh,self.group("Internal",system,"Shaft"),along(add(center,mul(a,-shaft_l/2)),a))
        for s in (-1,1):
            outward=mul(a,s)
            bm=along(add(center,mul(a,s*(half+20))),outward,cross(Z,outward))
            self.bearing_unit(system,bm)
            # Full bearing flange contacts mounting plate; no air gap.
            # Four holes align with the actual flange holes, NOT the plate corners.
            pn=self.simple_box("BearingMount_130x160x8",130,160,8,PLATE,
                               [(x,y+30,4.5) for x in (-38,38) for y in (-38,38)])
            self.put(pn,self.group("Plate",system),compose(bm,pose((0,-30,38))))
            self.contacts.append({"joint":"Bearing flange to plate","gap":0,"spacer":0})
        if motor:
            coupling=self.ring("Coupling_D50_d25_L60",25,12.5,60,ORANGE)
            cp=add(center,mul(a,half+80))
            self.put(coupling,self.group("Internal",system,"Coupling"),along(cp,a))
            gear=self.simple_box("Gearmotor_Gearbox_160x160x100",160,160,100,DARK)
            motor_p=add(center,mul(a,half+140))
            self.put(gear,self.group("Control",system,"Drive"),along(motor_p,a))
            mot=self.ring("Gearmotor_Motor_D120_L180",60,0,180,BLUE)
            self.put(mot,self.group("Control",system,"Drive"),along(add(motor_p,mul(a,100)),a))
            # Motor has a bolted foot plate below its envelope.
            self.flush_panel(system,"MotorFoot_240x200x10",240,200,10,
                             pose(add(motor_p,(-20,0,-90))),0)

    def conveyor(self):
        s="01_InclinedConveyor"; c=self.cfg
        tail=tuple(c["conveyor_tail"]); head=tuple(c["conveyor_head"])
        u=unit(sub(head,tail)); v=Y; n=cross(u,v)
        L=norm(sub(head,tail)); w=c["belt_width"]; t=c["belt_thickness"]
        r0=c["roller_diameter"]/2; r1=c["drive_pulley_diameter"]/2
        frame=pose(tail,u,v,n)
        bm=pose(add(tail,mul(v,w/2)),u,n,mul(v,-1))
        name="Belt_800_ClosedLoop_D50_D100"
        self.define(PartSpec(name,[pad([belt_loop(L,r0+t,r1+t),belt_loop(L,r0,r1)],w)],BLUE,
                            "Continuous solid belt, tangent spans and true circular wraps", "belt",
                            {"width":w,"r0":r0,"r1":r1,"centers":L,"thickness":t}))
        self.put(name,self.group("Internal",s,"Belt"),bm)
        self.shaft_roller(s,"TailRoller",2*r0,w+20,tail)
        self.shaft_roller(s,"DrivePulley",2*r1,w+20,head,motor=True)
        a=acos((r0-r1)/L); normal=(cos(a),0,sin(a))
        # Common tangent upper run; rollers are tangent to its inside surface.
        for f in (.2,.4,.6,.8):
            q=add((f*L,0,0),mul(normal,r0+(r1-r0)*f-r0))
            self.shaft_roller(s,"SupportRoller",2*r0,w+20,apply(frame,q))
        for side in (-1,1):
            # Bearing mounting plate outer face y=+/-476 contacts rail inner face.
            p0=apply(frame,(-70,side*(w/2+116),-100))
            p1=apply(frame,(L+70,side*(w/2+116),-100))
            self.beam(s,"SideRail",p0,p1,80,80,hint=v)
            guide=self.simple_box(f"GuidePlate_L{num(L)}",L,100,3,PLATE)
            # Longitudinal fixed side guides immediately outside the belt edges.
            gm=pose(apply(frame,(L/2,side*(w/2+3),65)),u,n,mul(v,-1))
            self.put(guide,self.group("Plate",s),gm)
        # Cleats on both runs; these are static positions of belt-mounted parts.
        cleat=self.simple_box("BeltCleat_780x35x8",w-20,35,8,BLUE)
        for top in (-1,1):
            for i in range(1,int(L//300)):
                f=i*300/L
                nx,nz=cos(a),sin(a)*top
                q=(f*L+nx*(r0+(r1-r0)*f+t),0,nz*(r0+(r1-r0)*f+t))
                # Center 17.5 mm outside the belt; local Z follows the run.
                outward=direction(frame,(nx,0,nz))
                cm=pose(add(apply(frame,q),mul(outward,17.5)),v,outward,cross(v,outward))
                self.put(cleat,self.group("Internal",s,"Cleat"),cm)
        # Three pairs of bolted support legs, attached below the side rails.
        for j,f in enumerate((.08,.46,.84),1):
            p=apply(frame,(L*f,0,-140))
            for side in (-1,1):
                y=side*(w/2+116)
                a0=(p[0],y,20); a1=(p[0],y,p[2])
                self.beam(s,f"Leg{j}",a0,a1)
                self.flush_panel(s,"ConveyorFoot_140x140x20",140,140,20,pose((p[0],y,0)))
                # Four connector gussets around the leg / rail junction.
                for sign in (-1,1):
                    mm=pose((p[0]+sign*40,y-20,p[2]-40),mul(X,sign),Z,mul(Y,-sign))
                    self.bracket(s,mm)
            self.beam(s,f"CrossTie{j}",(p[0],-w/2-76,p[2]-180),(p[0],w/2+76,p[2]-180))
        # Discharge above the central distributor; the ten routes stay separate downstream.
        lip_x,lip_z=100.,5450.
        for side in (-1,1):
            pts=[(head[0]-10,side*400,head[2]-10),(lip_x,side*200,lip_z),
                 (lip_x,side*200,lip_z+100),(head[0]-10,side*400,head[2]+90)]
            self.sheet_from_points(s,"DischargeSide",pts,3,"Internal")
        self.sheet_from_points(s,"DischargeFloor",[(head[0]-10,-400,head[2]-10),(lip_x,-200,lip_z),
                               (lip_x,200,lip_z),(head[0]-10,400,head[2]-10)],3,"Internal")

    def sheet_from_points(self,system,role,points,thickness,category="Plate"):
        """Planar sheet with a local sketch, used by hopper panels and chutes."""
        origin=points[0]; u=unit(sub(points[1],origin))
        n=unit(cross(u,sub(points[2],origin))); v=cross(n,u)
        coords=[(dot(sub(p,origin),u),dot(sub(p,origin),v)) for p in points]
        for p in points:
            if abs(dot(sub(p,origin),n))>.001: raise ValueError("Nonplanar sheet "+role)
        # A dimension signature prevents accidental same-name/different-shape reuse.
        import hashlib
        sig=hashlib.sha1(json.dumps([[round(x,5),round(y,5)] for x,y in coords]).encode()).hexdigest()[:8]
        name=f"Plate_{role}_{sig}"
        self.define(PartSpec(name,[pad([poly(coords)],thickness)],PLATE))
        self.put(name,self.group(category,system),pose(origin,u,v,n))

    def frustum(self,name,r_bottom,r_top,height,wall=3,color=PLATE):
        outline=[(r_bottom,0),(r_top,height),(r_top-wall,height),(r_bottom-wall,0)]
        return self.define(PartSpec(name,[{"op":"revolve","profile":outline,"name":"Shaft360"}],color,
                                   "Open-ended revolved shell"))

    def line_pose(self,index):
        """Front (-local Y) points radially OUT; local X is tangential."""
        angle=2*pi*(index+.5)/self.cfg["line_count"]
        radial=(cos(angle),sin(angle),0)
        tangent=(-sin(angle),cos(angle),0)
        return pose(mul(radial,self.cfg["station_radius"]),tangent,mul(radial,-1),Z)

    def rectangular_hopper(self,system,kind,center,bottom,top,height,gate=True):
        """Four reusable, open sheet walls. Bottom and top are clear nominal sizes."""
        w0,d0=bottom; w1,d1=top
        b=[(-w0/2,-d0/2,0),(w0/2,-d0/2,0),(w0/2,d0/2,0),(-w0/2,d0/2,0)]
        t=[(-w1/2,-d1/2,height),(w1/2,-d1/2,height),(w1/2,d1/2,height),(-w1/2,d1/2,height)]
        for j in range(4):
            self.sheet_from_points(system,kind+f"Wall{j+1}",
                                   [add(center,p) for p in (b[j],b[(j+1)%4],t[(j+1)%4],t[j])],2,"Internal")
        if gate:
            gn=self.simple_box(f"{kind}_Gate_{num(w0)}x{num(d0)}x2",w0,d0,2,ORANGE)
            self.put(gn,self.group("Internal",system,kind+"Gate"),pose(add(center,(0,0,-2))))
            pin=self.ring(f"{kind}_Hinge_D8_L{num(d0+40)}",4,0,d0+40,DARK)
            self.put(pin,self.group("Internal",system,kind+"Gate"),along(add(center,(-w0/2,-d0/2-20,0)),Y))
            actuator=self.simple_box(kind+"_GateActuator_60x45x55",60,45,55,BLUE)
            self.put(actuator,self.group("Control",system,"GateActuator"),pose(add(center,(-w0/2-40,0,0))))

    def distribution(self):
        """One common infeed, ten individually controlled vibratory branches.

        These open moving troughs are NOT belts. There are no holes through the
        continuous 800 mm belt, and no combined multihead discharge funnel.
        """
        s="02_CommonDistribution"; R=self.cfg["station_radius"]
        cone_outline=[(700,0),(80,350),(77,350),(697,0)]
        cone=self.define(PartSpec("DistributionCone_Capped_D1400_H350",
            [{"op":"revolve","profile":cone_outline,"name":"ConeShaft"},
             ring_feature(80,0,3,(0,0,347),"ClosedTopCap")],PLATE,
            "Closed central tip distributes chips onto ten separate vibratory troughs"))
        self.put(cone,self.group("Internal",s,"Distributor"),pose((0,0,4950)))
        inlet=self.frustum("CommonInlet_D600_to240_H150",120,300,150)
        self.put(inlet,self.group("Internal",s,"Inlet"),pose((0,0,5350)))
        support=self.ring("DistributionSupport_D1900_d1300_T30",950,650,30,BRACKET)
        self.put(support,self.group("Internal",s,"Support"),pose((0,0,4770)))
        cone_mount_h=150+(697-690)*350/620
        cone_mount=self.ring("ConeSupport_D24_d10_H"+num(cone_mount_h),12,5,cone_mount_h,BRACKET)
        for j in range(8):
            a=2*pi*j/8
            self.put(cone_mount,self.group("Internal",s,"Support"),pose((690*cos(a),690*sin(a),4800)))
        for x,y in ((-600,-600),(-600,600),(600,-600),(600,600)):
            self.beam(s,"DistributorColumn",(x,y,20),(x,y,4762))
            self.flush_panel(s,"DistributorFoot_200x200x20",200,200,20,pose((x,y,0)))
            self.flush_panel(s,"DistributorColumnCap_160x160x8",160,160,8,pose((x,y,4762)))
            self.bracket(s,pose((x+40,y-20,4722),X,Z,(0,-1,0)))
        # Supports meet the hopper outer rim, clear of the central product stream.
        for side in (-1,1):
            self.beam(s,"InletUpright",(side*600,600,4800),(side*600,600,5500),40,40)
            self.beam(s,"InletOverarm",(side*600,600,5480),(side*180,600,5480),40,40)
            self.beam(s,"InletSupportArm",(side*180,600,5480),(side*180,240,5480),40,40)
        for i in range(10):
            a=2*pi*(i+.5)/10
            self.station=f"Line_{i+1:02d}"
            self.transform=pose(ZERO,(cos(a),sin(a),0),(-sin(a),cos(a),0),Z)
            r0,r1=650.,R-600.
            z0,z1=4950.,4350.
            points=[(r0,-110,z0),(r1,-180,z1),(r1,180,z1),(r0,110,z0)]
            self.sheet_from_points(s,"RadialDistributionFloor",points,3,"Internal")
            for side in (-1,1):
                self.sheet_from_points(s,"RadialDistributionSide",
                    [(r0,side*110,z0),(r1,side*180,z1),
                     (r1,side*180,z1+100),(r0,side*110,z0+100)],3,"Internal")
            # Drive is outside the falling-product outlet, on the inner span.
            r_drive=900.; z_drive=z0+(z1-z0)*(r_drive-r0)/(r1-r0)
            drive=self.simple_box("DistributionVibrator_180x120x60",180,120,60,BLUE)
            self.put(drive,self.group("Control",s,"BranchVibrator"),pose((r_drive,0,z_drive-63)))
            mount=self.simple_box("DistributionDriveMount_230x180x10",230,180,10,BRACKET)
            self.put(mount,self.group("Bracket",s),pose((r_drive,0,z_drive-73)))
            isolator_h=z_drive-73-4800
            if isolator_h<=0:
                raise ValueError("Distributor drive needs a positive isolator height.")
            isolator=self.ring("DistributionIsolator_H"+num(isolator_h),20,5,isolator_h,BLACK)
            for yy in (-60,60):
                self.put(isolator,self.group("Internal",s,"VibrationIsolation"),pose((r_drive,yy,4800)))
            self.feed_routes.append({"line":self.station,"from":"CommonDistributor",
                                    "to":"Buffer_"+self.station,"inlet":apply(self.transform,(r0,0,z0)),
                                    "outlet":apply(self.transform,(r1,0,z1))})
        self.transform=pose(); self.station=None

    def independent_weigher(self):
        """One net-weighing channel per bagger, NOT one combination-weigher head.

        Buffer -> independently driven coarse/fine vibratory feeder -> one load
        cell hopper -> dedicated transfer tube. PLC timing remains a design spec.
        """
        s="02_IndependentNetWeigher"; deck=self.cfg["platform_deck_z"]
        self.rectangular_hopper(s,"LaneBuffer",(0,600,3650),(180,180),(450,450),600,False)
        level=self.simple_box("BufferLevelSensor_40x30x35",40,30,35,SCREEN)
        self.put(level,self.group("Control",s,"LevelSensor"),pose((245,600,4140)))
        # Feeder is separate from the load-cell hopper, with a real free-fall gap.
        self.sheet_from_points(s,"MeteringFeederFloor",[(-100,700,3610),(-100,-30,3510),
                               (100,-30,3510),(100,700,3610)],3,"Internal")
        for side in (-1,1):
            self.sheet_from_points(s,"MeteringFeederSide",[(side*100,700,3610),(side*100,-30,3510),
                                   (side*100,-30,3570),(side*100,700,3670)],2,"Internal")
        vf=self.simple_box("MeteringVibrator_180x120x60",180,120,60,BLUE)
        feed_z=3510+100*(300+30)/730
        self.put(vf,self.group("Control",s,"CoarseFineFeedDrive"),pose((0,300,feed_z-63)))
        support_top=feed_z-63
        self.beam(s,"FeederSupport",(-340,300,support_top-40),(340,300,support_top-40))
        self.rectangular_hopper(s,"NetWeighHopper",(0,0,3200),(150,150),(250,250),200,True)
        # The lip bracket transfers load to the moving end of a separate load cell.
        load=self.simple_box("NetWeighLoadCell_120x35x30",120,35,30,ORANGE)
        self.put(load,self.group("Internal",s,"LoadCell"),pose((280,0,3390)))
        fixed=self.simple_box("LoadCellFixedMount_100x80x20",100,80,20,BRACKET)
        self.put(fixed,self.group("Bracket",s),pose((350,0,3370)))
        link=self.simple_box("NetWeighMovingLink_125x30x8",125,30,8,SILVER)
        self.put(link,self.group("Internal",s,"LoadCellMovingLink"),pose((187.5,0,3420)))
        lug=self.simple_box("NetWeighLipLug_8x30x20",8,30,20,SILVER)
        self.put(lug,self.group("Internal",s,"LoadCellMovingLink"),pose((125,0,3400)))
        for x in (-380,380):
            for y in (-260,900):
                self.beam(s,"LaneWeigherColumn",(x,y,deck+16),(x,y,4260))
                self.flush_panel(s,"LaneWeigherFoot_140x140x8",140,140,8,pose((x,y,deck+8)))
            self.beam(s,"LaneWeigherSide",(x,-220,3330),(x,860,3330))
            self.beam(s,"BufferSupportSide",(x,-220,4202),(x,900,4202))
        for yy in (-260,900):
            self.beam(s,"LaneWeigherCross",(-420,yy,4300),(420,yy,4300))
            for xx in (-380,380):
                self.bracket(s,pose((xx+(-40 if xx>0 else 40),yy-20,4260),
                    mul(X,-1 if xx>0 else 1),mul(Z,-1),mul(Y,-1 if xx>0 else 1)))
        # Buffer brackets are structural; the metering hopper stays on its load cell.
        for side in (-1,1):
            buffer_bracket=self.simple_box("BufferSupportLug_195x80x8",195,80,8,BRACKET)
            self.put(buffer_bracket,self.group("Bracket",s),pose((side*302.5,600,4242)))
            self.bolt(s,(side*380,600,4220),Z,30)
        # Exactly one hollow chute connects this scale to THIS bagger inlet.
        funnel=self.frustum("LaneTransferFunnel_D320_to180_H248",90,160,248)
        self.put(funnel,self.group("Internal",s,"DedicatedTransfer"),pose((0,0,2950)))
        tube=self.ring("LaneTransferTube_D180_d174_L840",90,87,840)
        self.put(tube,self.group("Internal",s,"DedicatedTransfer"),pose((0,0,2110)))
        # External split clamp supports the transfer tube without touching the weigh hopper.
        clamp=self.define(PartSpec("TransferClamp_D204_d180_WithLug_T20",
                    [ring_feature(102,90,20),box_feature(60,40,20,(120,0,0),"ClampLug")],BRACKET))
        for z in (2300,2860):
            self.put(clamp,self.group("Bracket",s),pose((0,0,z)))
            arm=self.simple_box("TransferClampArm_230x40x8",230,40,8,BRACKET)
            self.put(arm,self.group("Bracket",s),pose((265,0,z)))
            self.beam(s,"TransferSupport",(380,-220,z-40),(380,860,z-40))
        # Clear stop / ready / weight feedback is specified for each independent lane.
        self.connections.append({
            "line":self.station,"weigher":self.station+"/NetWeighHopper",
            "bagger":self.station+"/VFFSBagger","mode":"independent_net_weighing",
            "nominal_fill_g":self.cfg["nominal_fill_g"],
            "target_bags_per_min":self.cfg["target_bags_per_min_per_line"],
            "weigh_hopper_litres":(250**2+150**2+250*150)*200/3/1e6,
            "weigher_outlet":apply(self.transform,(0,0,3200)),
            "funnel_inlet":apply(self.transform,(0,0,3198)),
            "funnel_outlet":apply(self.transform,(0,0,2950)),
            "tube_inlet":apply(self.transform,(0,0,2950)),
            "tube_outlet":apply(self.transform,(0,0,2110)),
            "bagger_inlet":apply(self.transform,(0,0,2110)),
            "floor_opening_center":apply(self.transform,(0,0,deck)),
            "frame":self.transform,
            "required_handshake":["buffer_request","weight_ready","bagger_ready","dump_complete"]})

    def platform(self):
        """Shared annular deck: ten real transfer holes, railings and one stair."""
        s="03_AnnularPlatform"; c=self.cfg; deck=c["platform_deck_z"]
        ri,ro,R=c["platform_inner_radius"],c["platform_outer_radius"],c["station_radius"]
        if not (ri+650<R<ro-650):
            raise ValueError("Platform radii do not clear the station supports and transfer holes.")
        half=pi/10; steps=12
        angles=[-half+2*half*j/steps for j in range(steps+1)]
        outline=[(ro*cos(a),ro*sin(a)) for a in angles]+[(ri*cos(a),ri*sin(a)) for a in reversed(angles)]
        panel=self.define(PartSpec("AnnularDeckSector_R"+num(ri)+"_R"+num(ro)+"_36deg_T8",
            [pad([poly(outline),circle(120,(R,0))],8,name="DeckWithTransferOpening")],PLATE,
            "One 36 degree sector, one real D240 transfer opening; reused ten times","plate"))
        for i in range(10):
            a=2*pi*(i+.5)/10
            self.put(panel,self.group("Plate",s),pose((0,0,deck),(cos(a),sin(a),0),(-sin(a),cos(a),0),Z))
            self.platform_openings.append({"line":f"Line_{i+1:02d}","center":(R*cos(a),R*sin(a),deck),
                                           "diameter":240.,"tube_diameter":180.})
        r_inner,r_outer=ri+200,ro-40
        for i in range(10):
            a,b=2*pi*i/10,2*pi*(i+1)/10
            radial=(cos(a),sin(a),0); tangent=(-sin(a),cos(a),0)
            for radius,role in ((r_inner,"Inner"),(r_outer,"Outer")):
                x,y=radius*cos(a),radius*sin(a)
                self.beam(s,"PlatformLeg",(x,y,20),(x,y,deck-80))
                self.flush_panel(s,"AnnularFoot_180x180x20",180,180,20,pose((x,y,0)))
                self.beam(s,"Annular"+role+"Chord",(radius*cos(a),radius*sin(a),deck-40),
                          (radius*cos(b),radius*sin(b),deck-40))
                self.bracket(s,pose((x,y,deck-80),radial,mul(Z,-1),tangent))
            self.beam(s,"RadialDeckBeam",add(mul(radial,r_inner+40),(0,0,deck-40)),
                      add(mul(radial,r_outer-40),(0,0,deck-40)))
            # Two members straddle each transfer tube; none crosses its opening.
            ca=2*pi*(i+.5)/10; rr=(cos(ca),sin(ca),0); tt=(-sin(ca),cos(ca),0)
            for side in (-1,1):
                self.beam(s,"TransferOpeningBeam",add(add(mul(rr,r_inner),mul(tt,side*180)),(0,0,deck-40)),
                          add(add(mul(rr,r_outer),mul(tt,side*180)),(0,0,deck-40)))
            # Side bracing between columns beneath the platform, clear of baggers.
            self.beam(s,"InnerDiagonal",(r_inner*cos(a),r_inner*sin(a),350),
                      (r_inner*cos(b),r_inner*sin(b),deck-200),40,80)
        # Guardrails have a 14 degree stair opening on +X only.
        for radius,role in ((ri,"Inner"),(ro,"Outer")):
            degs=list(range(0,360,18)) if role=="Inner" else [7]+list(range(18,343,18))+[353]
            for d in degs:
                a=d*pi/180
                self.beam(s,role+"GuardPost",(radius*cos(a),radius*sin(a),deck+8),
                          (radius*cos(a),radius*sin(a),deck+1058),40,40)
            pairs=list(zip(degs,degs[1:]))
            if role=="Inner": pairs.append((degs[-1],360))
            for d0,d1 in pairs:
                a,b=d0*pi/180,d1*pi/180
                for z in (deck+550,deck+1058):
                    self.beam(s,role+"GuardRail",(radius*cos(a),radius*sin(a),z),
                              (radius*cos(b),radius*sin(b),z),40,40)
        # Short horizontal landing bridges the circular edge to the stair.
        self.flush_panel(s,"StairLanding_500x1000x8",500,1000,8,pose((ro+150,0,deck)))
        for yy in (-440,440):
            self.beam(s,"LandingBeam",(ro-100,yy,deck-40),(ro+400,yy,deck-40))
        steps=11; run=250.; rise=deck/steps
        for i in range(steps):
            xx=ro+525+(steps-1-i)*run; zz=(i+1)*rise
            self.flush_panel(s,"StairTread_250x800x8",250,800,8,pose((xx,0,zz)))
            for side in (-1,1):
                self.bracket(s,pose((xx-20,side*400,zz),mul(Y,-side),mul(Z,-1),mul(X,side)))
        for side in (-1,1):
            self.beam(s,"StairStringer",(ro+3150,side*440,80),(ro+400,side*440,deck-50))
            self.beam(s,"StairHandrail",(ro+3150,side*440,1080),(ro+400,side*440,deck+950),40,40)
            for f in (0.,.5,1.):
                xx=ro+3150-2750*f; zz=80+(deck-130)*f
                self.beam(s,"StairRailPost",(xx,side*440,zz),(xx,side*440,zz+1000),40,40)


    def bagger(self):
        s="04_VFFSBagger"
        for x in (-510,510):
            for y in (-560,560):
                self.beam(s,"BaggerLeg",(x,y,20),(x,y,2010))
                self.flush_panel(s,"BaggerFoot_140x140x20",140,140,20,pose((x,y,0)))
        for z in (180,970,2050):
            end=550 if z==2050 else 470
            for y in (-560,560): self.beam(s,"BaggerCrossX",(-end,y,z),(end,y,z))
            for x in (-510,510): self.beam(s,"BaggerCrossY",(x,-520,z),(x,520,z))
        for x in (-510,510):
            for y in (-560,560):
                sx=-1 if x>0 else 1
                for z in (140,930,2010):
                    self.bracket(s,pose((x+sx*40,y-20,z),mul(X,sx),mul(Z,-1),mul(Y,sx)))
        # Rear and side skins contact the outside faces of the profiles.
        self.flush_panel(s,"RearSkin_1100x1740x3",1100,1740,3,pose((0,600,1090),(-1,0,0),Z,Y))
        for side in (-1,1):
            self.flush_panel(s,"SideSkin_1120x820x3",1120,820,3,
                             pose((side*550,0,590),Y,mul(Z,side),mul(X,side)))
        tube=self.ring("FillingTube_D140_d134_L950",70,67,950)
        self.put(tube,self.group("Internal",s,"Former"),pose((0,0,1000)))
        neck=self.frustum("Transition_D180_to140_H160",70,90,160)
        self.put(neck,self.group("Internal",s,"Former"),pose((0,0,1950)))
        collar=self.frustum("FormerCollar_Concept_D460_to146_H220",73,230,220)
        self.put(collar,self.group("Internal",s,"Former"),pose((0,0,1650)))
        # Film stock is wound material, NOT a conveyor pulley.
        film=self.ring("FilmRoll_D320_Core76_W460",160,38,460,FILM)
        self.put(film,self.group("Internal",s,"FilmSupply"),along((-230,380,1350),X))
        # A core mandrel plus both stationary cylindrical bearing housings.
        self.shaft_roller(s,"FilmMandrel",76,460,(0,380,1350),X)
        self.shaft_roller(s,"FilmGuideRoller",50,460,(0,320,1920),X)
        self.shaft_roller(s,"FilmGuideRoller",50,460,(0,120,1980),X)
        for yy in (-95,95):
            self.shaft_roller(s,"FilmNipRoller",50,260,(0,yy,1100),X,motor=yy<0)
        # Roll mounting crossmembers under the support plates.
        for yy,zz in ((380,1240),(320,1810),(120,1870),(-95,990),(95,990)):
            self.beam(s,"RollSupport",(-470,yy,zz),(470,yy,zz),80,80)
        # Longitudinal heat seal; a separate backing block and heater block.
        for name,yy,color in (("VerticalSealBacking",72,SILVER),("VerticalSealHeater",100,ORANGE)):
            pn=self.simple_box(name+"_30x20x450",30,20,450,color)
            self.put(pn,self.group("Internal",s,"VerticalSeal"),pose((0,yy,1150)))
        # Horizontal sealing jaws open around the product path.
        for side in (-1,1):
            jaw=self.simple_box("HorizontalSealJaw_340x30x40",340,30,40,ORANGE)
            self.put(jaw,self.group("Internal",s,"HorizontalSeal"),pose((0,side*55,730)))
            carrier=self.simple_box("SealCarriage_600x50x90",600,50,90,BRACKET)
            self.put(carrier,self.group("Internal",s,"HorizontalSeal"),pose((0,side*95,705)))
            # Linear bearing blocks are cylindrical, around guide rods.
            for x in (-250,250):
                rn=self.ring("LinearBush_D50_d20_L50",25,10,50,SILVER)
                self.put(rn,self.group("Internal",s,"LinearBearing"),along((x,side*95-25,750),Y))
            cyl=self.ring("SealCylinder_D63_d20_L160",31.5,10,160,BLUE)
            rod=self.ring("SealPistonRod_D20_L160",10,0,160,SILVER)
            self.put(cyl,self.group("Control",s,"PneumaticCylinder"),along((0,side*400,750),mul(Y,-side)))
            self.put(rod,self.group("Internal",s,"PistonRod"),along((0,side*240,750),mul(Y,-side)))
        for x in (-250,250):
            pn=self.ring("SealGuideRod_D20_L800",10,0,800,SILVER)
            self.put(pn,self.group("Internal",s,"GuideRod"),along((x,-400,750),Y))
        for yy in (-420,420):
            self.flush_panel(s,"SealSupport_700x120x10",700,120,10,
                             pose((0,yy,750),X,Z,(0,-1,0)))
        # Outlet chute belongs to the bagger; reference item 5 is not included.
        self.sheet_from_points(s,"BagOutlet",[(-200,-120,570),(200,-120,570),
                               (200,-620,350),(-200,-620,350)],3,"Internal")

    def control(self):
        s="04_VFFSBagger"
        for y in (-100,100):
            self.beam(s,"CabinetBacker",(510,y,1010),(510,y,2010))
        cabinet=self.simple_box("ElectricalCabinet_350x180x650",350,180,650,CABINET)
        self.put(cabinet,self.group("Control",s,"Cabinet"),pose((753,0,1070)))
        # Stand-off 20 is explicitly filled by spacers.
        self.flush_panel(s,"CabinetMountPlate_180x650x8",180,650,8,
                         pose((550,0,1395),Y,Z,X),20)
        screen=self.simple_box("HMI_220x150x25",220,150,25,SCREEN)
        self.put(screen,self.group("Control",s,"HMI"),pose((753,-90,1510),X,Z,(0,-1,0)))
        for name,x,z,r,color in [("StartButton",683,1320,12,(50,178,91)),
                                  ("StopButton",743,1320,12,(204,53,54)),
                                  ("EmergencyStop",803,1320,20,(225,40,43))]:
            pn=self.ring(name,r,0,20,color)
            self.put(pn,self.group("Control",s,"Pushbutton"),along((x,-90,z),(0,-1,0)))

    def build(self):
        self.conveyor(); self.distribution(); self.platform()
        for i in range(self.cfg["line_count"]):
            self.station=f"Line_{i+1:02d}"
            self.transform=self.line_pose(i)
            self.independent_weigher(); self.bagger(); self.control()
        self.transform=pose(); self.station=None
        return self

    def capacity(self):
        per_lane=self.cfg["target_bags_per_min_per_line"]
        total=self.cfg["line_count"]*per_lane
        mass=total*self.cfg["nominal_fill_g"]*60/1000
        factor=self.cfg["assumed_effective_factor"]
        return {"status":"DESIGN TARGETS ONLY - not measured or guaranteed",
                "lines":self.cfg["line_count"],"nominal_fill_g":self.cfg["nominal_fill_g"],
                "target_bags_per_min_per_line":per_lane,"theoretical_bags_per_min":total,
                "finished_product_kg_per_hour_at_target":mass,
                "assumed_effective_factor":factor,"scenario_bags_per_min":total*factor,
                "scenario_finished_product_kg_per_hour":mass*factor,
                "required_verification":["individual net weighing speed and accuracy",
                    "shared conveyor and distribution throughput >= full target product mass flow",
                    "film draw, seal dwell and product fall cycle",
                    "nitrogen supply, compressed air and electrical load",
                    "chip breakage, bridging and bulk density"],
                "note":"Increasing bagger count alone does not guarantee tenfold output."}

    def audit(self):
        errors=[]
        for o in self.occ:
            m=o.matrix; a,b,c=m[:3],m[3:6],m[6:9]
            if len(m)!=12 or not all(isfinite(x) for x in m): errors.append("Invalid transform: "+o.part)
            if max(abs(norm(v)-1) for v in (a,b,c))>1e-7 or abs(dot(a,b))>1e-7 or norm(sub(cross(a,b),c))>1e-7:
                errors.append("Non-rigid transform: "+o.part)
            if o.part not in self.parts: errors.append("Missing master: "+o.part)
        for p in self.parts.values():
            if p.kind=="profile":
                if len(p.features)!=1 or p.features[0]["op"]!="pad" or len(p.features[0]["loops"])!=1:
                    errors.append("Not single-profile Pad: "+p.name)
            for f in p.features:
                if f["op"] in ("pad","pocket") and f["length"]<=0: errors.append("Nonpositive feature: "+p.name)
        for j in self.contacts:
            if abs(j["gap"]-j["spacer"])>1e-8: errors.append("Unfilled stand-off: "+j["joint"])
        for b in self.bearing_sets:
            if b["shaft_d"]!=b["bearing_id"] or b["bearing_od"]!=b["seat_d"]:
                errors.append("Bearing nominal fit mismatch")
            if b["bearing_z"][0]<b["seat_z"][0] or b["bearing_z"][1]>b["seat_z"][1]:
                errors.append("Bearing outside cylindrical seat")
        expected={f"Line_{i+1:02d}" for i in range(self.cfg["line_count"])}
        if not self.smoke_only and ({c["line"] for c in self.connections}!=expected or len(self.connections)!=10):
            errors.append("Expected exactly ten dedicated weigh-to-bag connections")
        if not self.smoke_only and (len(self.feed_routes)!=10 or {r["line"] for r in self.feed_routes}!=expected):
            errors.append("Expected ten independent distribution branches")
        openings={p["line"]:p for p in self.platform_openings}
        for connection in self.connections:
            label=connection["line"]
            for first,second in (("funnel_outlet","tube_inlet"),("tube_outlet","bagger_inlet")):
                if norm(sub(connection[first],connection[second]))>1e-6:
                    errors.append(label+": product path disconnected at "+first)
            if norm(sub(connection["weigher_outlet"][:2],connection["bagger_inlet"][:2]))>1e-6:
                errors.append(label+": scale and bagger axes do not align")
            if label not in openings or norm(sub(openings[label]["center"],connection["floor_opening_center"]))>1e-6:
                errors.append(label+": missing or misaligned platform opening")
            if label in openings and openings[label]["diameter"]<=openings[label]["tube_diameter"]:
                errors.append(label+": tube does not clear deck")
            station_occ=[o for o in self.occ if label in o.path]
            for name in ("NetWeighHopper_Gate_150x150x2","NetWeighLoadCell_120x35x30",
                         "LaneTransferTube_D180_d174_L840","FillingTube_D140_d134_L950"):
                if sum(o.part==name for o in station_occ)!=1:
                    errors.append(label+": expected exactly one "+name)
        if "CollectionFunnel_D1100_to180_H350" in self.parts:
            errors.append("Old combined-discharge funnel must not remain in ten-line design")
        counts=Counter(o.part for o in self.occ)
        return {"passed":not errors,"errors":errors,"master_parts":len(self.parts),
                "instances":len(self.occ),"reused_masters":sum(q>1 for q in counts.values()),
                "profile_masters":sum(p.kind=="profile" for p in self.parts.values()),
                "bearing_units":len(self.bearing_sets),"panel_stack_checks":len(self.contacts),
                "independent_weighers":len(self.connections),"baggers":counts["FillingTube_D140_d134_L950"],
                "dedicated_connections":len(self.connections),"platform_transfer_holes":len(self.platform_openings),
                "scope":("Smoke geometry subset; not a complete machine." if self.smoke_only else
                         "Analytic layout checks only; no CATIA solid update or full clash analysis.")}

    def serializable(self):
        return {"root":ROOT_NAME,"config":self.cfg,
                "parts":{k:asdict(v) for k,v in self.parts.items()},
                "occurrences":[asdict(o) for o in self.occ],"connections":self.connections,
                "feed_routes":self.feed_routes,"platform_openings":self.platform_openings,
                "capacity":self.capacity(),"audit":self.audit()}

def sample_loop(loop, steps=32):
    if loop["type"]=="polygon": return loop["points"]
    if loop["type"]=="circle":
        x,y=loop["center"]; r=loop["radius"]
        return [(x+r*cos(i*2*pi/steps),y+r*sin(i*2*pi/steps)) for i in range(steps)]
    out=[]
    for s in loop["segments"]:
        if s["type"]=="line": out.append(s["p0"])
        else:
            n=max(3,int(steps*(s["a1"]-s["a0"])/(2*pi)))
            x,y=s["center"]; r=s["radius"]
            out.extend((x+r*cos(s["a0"]+(s["a1"]-s["a0"])*i/n),
                        y+r*sin(s["a0"]+(s["a1"]-s["a0"])*i/n)) for i in range(n+1))
    return out

# ============================================================================
# SVG PREVIEW
# ============================================================================

from math import sin,cos,pi
from pathlib import Path
import json

def geometry_faces(spec):
    faces=[]
    for f in spec.features:
        if spec.kind=="profile":
            # Preview simplification only: CAD retains the single-contour T-slot sketch.
            f={**f,"loops":[poly(rect(spec.parameters["width"],spec.parameters["height"]))]}
        if f["op"]=="pocket": continue
        if f["op"]=="revolve":
            pts=f["profile"]; steps=24
            for k in range(len(pts)):
                r0,z0=pts[k]; r1,z1=pts[(k+1)%len(pts)]
                for i in range(steps):
                    a=i*2*pi/steps; b=(i+1)*2*pi/steps
                    faces.append([[(r0*cos(a),r0*sin(a),z0),(r0*cos(b),r0*sin(b),z0),
                                   (r1*cos(b),r1*sin(b),z1),(r1*cos(a),r1*sin(a),z1)]])
        else:
            u=f["u"]; v=f["v"]; n=cross(u,v)
            m=pose(f["origin"],u,v,n)
            loops=[sample_loop(loop,20) for loop in f["loops"]]
            for z in (0,f["length"]):
                faces.append([[apply(m,(x,y,z)) for x,y in points] for points in loops])
            for points in loops:
                for i,a in enumerate(points):
                    b=points[(i+1)%len(points)]
                    if norm(sub(a,b))<1e-7: continue
                    faces.append([[apply(m,(*a,0)),apply(m,(*b,0)),
                                   apply(m,(*b,f["length"])),apply(m,(*a,f["length"]))]])
    return faces

def scene(model,system=None,detail=False,line=None):
    out=[]; cache={}
    for occurrence in model.occ:
        if system and not any(s.startswith(system+"_") for s in occurrence.path): continue
        if line and line not in occurrence.path: continue
        spec=model.parts[occurrence.part]
        if not detail and (spec.kind=="fastener" or "Tnut_" in spec.name): continue
        if spec.name not in cache: cache[spec.name]=geometry_faces(spec)
        for face in cache[spec.name]:
            out.append(([[apply(occurrence.matrix,p) for p in loop] for loop in face],spec.color))
    return out

def project_scene(faces,view="iso",width=1400,height=900):
    if view=="top":
        right=(1,0,0); up=(0,1,0); depth=(0,0,1)
    elif view=="side":
        right=(1,0,0); up=(0,0,1); depth=(0,-1,0)
    else:
        right=unit((.88,.47,0)); depth=unit((.43,-.8,.43)); up=unit(cross(depth,right))
    projected=[]
    for loops,color in faces:
        pts=[p for loop in loops for p in loop]
        if len(pts)<3: continue
        n=cross(sub(pts[1],pts[0]),sub(pts[2],pts[0]))
        light=.72+.28*abs(dot(unit(n),unit((-.4,-.2,1)))) if norm(n)>1e-9 else .85
        rgb=tuple(int(c*light) for c in color)
        flat=[[(dot(p,right),-dot(p,up)) for p in loop] for loop in loops]
        d=sum(dot(p,depth) for p in pts)/len(pts)
        projected.append({"loops":flat,"color":rgb,"depth":d})
    if not projected: return []
    xs=[x for face in projected for loop in face["loops"] for x,y in loop]
    ys=[y for face in projected for loop in face["loops"] for x,y in loop]
    scale=min((width-120)/(max(xs)-min(xs)),(height-190)/(max(ys)-min(ys)))
    ox=(width-(max(xs)-min(xs))*scale)/2-min(xs)*scale
    oy=110-min(ys)*scale
    for f in projected:
        f["loops"]=[[(round(x*scale+ox,2),round(y*scale+oy,2)) for x,y in loop] for loop in f["loops"]]
    return sorted(projected,key=lambda f:f["depth"])

def write_svg(path,projected,title,subtitle,width=1400,height=900):
    lines=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="#f6f8fb"/>',
           f'<text x="42" y="45" font-family="Arial,sans-serif" font-size="27" font-weight="bold" fill="#18273c">{title}</text>',
           f'<text x="42" y="74" font-family="Arial,sans-serif" font-size="15" fill="#52657b">{subtitle}</text>']
    for f in projected:
        d=' '.join('M '+' L '.join(f'{x},{y}' for x,y in loop)+' Z' for loop in f["loops"])
        color='#%02x%02x%02x'%tuple(f["color"])
        lines.append(f'<path d="{d}" fill="{color}" fill-rule="evenodd" stroke="#455367" stroke-width="0.24"/>')
    lines += [f'<text x="42" y="{height-34}" font-family="Arial,sans-serif" font-size="14" fill="#52657b">CONCEPT ASSEMBLY | mm | Profile + plate + bolted bracket | Not a CATIA-validated manufacturing model</text>', '</svg>']
    path.write_text('\n'.join(lines),encoding="utf-8")

def write_previews(model,folder,render_json=None):
    folder=Path(folder)
    names={"01":"Common inclined conveyor","02":"10 INDEPENDENT net weighers + distribution", "03":"Annular platform and stairs","04":"10 individual VFFS baggers"}
    views=[(None,"iso","assembly_preview.svg",None),(None,"top","assembly_top.svg",None),
           (None,"iso","line_01_detail.svg","Line_01")]
    views += [(system,"iso",f'{system}_preview.svg',None) for system in names]
    for system,view,name,line in views:
        faces=project_scene(scene(model,system,line=line),view)
        title=(system+' / '+names[system]) if system else "13 / RADIAL PACKAGING / 10 WEIGHERS : 10 BAGGERS"
        if line: title="LINE 01 / ONE WEIGHER - ONE DEDICATED CHUTE - ONE BAGGER"
        subtitle="Concept | 800 mm belt | D50 idlers / D100 drive | Profiles simplified in preview only"
        write_svg(folder/name,faces,title,subtitle)
        if render_json and system is None and view=="iso" and line is None:
            Path(render_json).write_text(json.dumps({"width":1400,"height":900,"title":title,"subtitle":subtitle,"faces":faces}),encoding="utf-8")
        if render_json and line:
            Path(render_json).with_name("line_01_render.json").write_text(json.dumps({"width":1400,"height":900,"title":title,"subtitle":subtitle,"faces":faces}),encoding="utf-8")


# ============================================================================
# CATIA COM BUILD AND SAVE
# ============================================================================

import argparse
from collections import Counter
from datetime import datetime
import csv
import json
import logging
from pathlib import Path
import shutil
import sys
import traceback
import zipfile


HERE=Path(__file__).resolve().parent
LOG=logging.getLogger("packaging")

class CatiaBuilder:
    root_name=ROOT_NAME
    progress_label='12 Packaging'

    def __init__(self, folder, launch=False, app=None, namespace="",root_name=ROOT_NAME):
        self.namespace=namespace
        self.root_name=root_name
        if app is not None:
            self.app=app  # The line runner owns the COM session.
        else:
            try:
                import pythoncom
                from win32com.client import dynamic
            except ImportError as e:
                raise RuntimeError("Install Windows CPython and pywin32: py -m pip install pywin32") from e
            pythoncom.CoInitialize()
            try:
                obj=pythoncom.GetActiveObject("CATIA.Application")
                self.app=dynamic.Dispatch(obj.QueryInterface(pythoncom.IID_IDispatch))
            except pythoncom.com_error as e:
                if not launch:
                    raise RuntimeError("Open CATIA V5 first, then run again. "
                                       "Alternatively use --launch to start it.") from e
                self.app=dynamic.Dispatch("CATIA.Application")
        self.app.Visible=True
        self.folder=Path(folder)
        self.parts_dir=self.folder/"Parts"
        self.products_dir=self.folder/"Products"
        self.parts_dir.mkdir(parents=True,exist_ok=True)
        self.products_dir.mkdir(parents=True,exist_ok=True)
        self.docs={}  # Only currently open documents created by this builder.
        self.warnings=[]
        self.root_doc=None

    def identifier(self,name):
        return self.namespace+name

    def part_path(self,name):
        import hashlib
        # Keep deep project paths usable by CATIA's legacy file dialogs.
        key=hashlib.sha256(name.encode()).hexdigest()[:10]
        return self.parts_dir/(self.identifier(key+'_'+name[:28])+".CATPart")

    def arr(self,values):
        # Dispatch has CATIA type information and marshals a sequence itself.
        # Wrapping it in VARIANT a second time causes the SAFEARRAY TypeError.
        return tuple(float(v) for v in values)

    def sketch(self,part,body,feature):
        origin=feature.get("origin",(0,0,0)); u=feature.get("u",(1,0,0)); v=feature.get("v",(0,1,0))
        n=cross(u,v)
        # CATIA plane convention is Ax+By+Cz=D, not Ax+By+Cz+D=0.
        if all(abs(x)<1e-9 for x in origin) and u==(1,0,0) and v==(0,1,0):
            support=part.OriginElements.PlaneXY
        else:
            hb=part.HybridBodies.Item("Construction")
            plane=part.HybridShapeFactory.AddNewPlaneEquation(*n,dot(n,origin))
            hb.AppendHybridShape(plane)
            part.UpdateObject(plane)
            support=part.CreateReferenceFromObject(plane)
        part.InWorkObject=body
        sk=body.Sketches.Add(support)
        sk.Name=feature.get("name","Feature")+"_Sketch"
        sk.SetAbsoluteAxisData(self.arr(tuple(origin)+tuple(u)+tuple(v)))
        return sk

    @staticmethod
    def line(fac,a,b):
        return fac.CreateLine(float(a[0]),float(a[1]),float(b[0]),float(b[1]))

    def draw_loop(self,fac,loop):
        if loop["type"]=="circle":
            x,y=loop["center"]
            fac.CreateClosedCircle(float(x),float(y),float(loop["radius"]))
        elif loop["type"]=="polygon":
            pts=loop["points"]
            # Explicit shared end points keep the single contour connected.
            vertices=[fac.CreatePoint(float(p[0]),float(p[1])) for p in pts]
            for i,a in enumerate(pts):
                j=(i+1)%len(pts)
                edge=self.line(fac,a,pts[j])
                edge.StartPoint=vertices[i]; edge.EndPoint=vertices[j]
            for vertex in vertices:
                vertex.Construction=True
        else:
            for s in loop["segments"]:
                if s["type"]=="line": self.line(fac,s["p0"],s["p1"])
                else:
                    x,y=s["center"]
                    fac.CreateCircle(float(x),float(y),float(s["radius"]),float(s["a0"]),float(s["a1"]))

    def create_part(self,spec):
        key=('Part',spec.name)
        doc=self.app.Documents.Add("Part")
        self.docs[key]=doc
        try:
            return self._write_part_features(doc,spec)
        except Exception as exc:
            raise RuntimeError("CATPart failed: "+spec.name+"; saved earlier parts are preserved.") from exc
        finally:
            # No feature, Selection, or Part proxies from the helper survive here.
            self.close_owned_document(key)

    def _write_part_features(self,doc,spec):
        part=doc.Part
        doc.Activate(); part.Update()
        doc.Product.PartNumber=self.identifier(spec.name)
        hb=part.HybridBodies.Add(); hb.Name="Construction"
        body=part.MainBody; body.Name="PartBody"
        for f in spec.features:
            if f["op"]=="revolve":
                # Radius/height sketch on XZ, revolved about its V axis.
                sf={"name":f["name"],"origin":(0,0,0),"u":(1,0,0),"v":(0,0,1)}
                sk=self.sketch(part,body,sf)
                fac=sk.OpenEdition()
                self.draw_loop(fac,poly(f["profile"]))
                axis=fac.CreateLine(0.,-1.,0.,max(p[1] for p in f["profile"])+1.)
                axis.Construction=True
                sk.CenterLine=axis
                sk.CloseEdition(); part.Update()
                part.InWorkObject=body
                feat=part.ShapeFactory.AddNewShaft(sk)
                feat.FirstAngle.Value=360.; feat.SecondAngle.Value=0.
            else:
                sk=self.sketch(part,body,f)
                fac=sk.OpenEdition()
                for loop in f["loops"]: self.draw_loop(fac,loop)
                sk.CloseEdition(); part.Update()
                part.InWorkObject=body
                method=part.ShapeFactory.AddNewPad if f["op"]=="pad" else part.ShapeFactory.AddNewPocket
                feat=method(sk,float(f["length"]))
            feat.Name=f["name"]
            part.Update()
            if not part.IsUpToDate(feat): raise RuntimeError("Feature did not update: "+feat.Name)
            sel=doc.Selection; sel.Clear(); sel.Add(sk); sel.VisProperties.SetShow(1); sel.Clear()
        # Informational parameters are not falsely represented as driving geometry.
        part.Parameters.CreateString("DesignStatus","CONCEPT - dimensions require engineering review")
        if spec.note: part.Parameters.CreateString("DesignNote",spec.note)
        for name,value in spec.parameters.items():
            part.Parameters.CreateReal("Info_"+name,float(value))
        sel=doc.Selection
        sel.Clear(); sel.Add(body); sel.VisProperties.SetRealColor(*spec.color,1); sel.Clear()
        sel.Add(hb); sel.VisProperties.SetShow(1); sel.Clear()
        try:
            for reference in (part.OriginElements.PlaneXY,part.OriginElements.PlaneYZ,part.OriginElements.PlaneZX):
                sel.Add(reference)
            sel.VisProperties.SetShow(1)
        except Exception as e:
            self.warnings.append("Origin plane visibility: "+spec.name+": "+str(e))
        finally:
            sel.Clear()
        part.Update()
        path=self.part_path(spec.name)
        doc.SaveAs(str(path))
        if not path.is_file() or path.stat().st_size==0: raise RuntimeError("Part was not saved: "+str(path))
        return path

    def product_path(self,key):
        import hashlib
        if not key:return self.folder/(self.identifier(self.root_name)+".CATProduct")
        tag=hashlib.sha256('/'.join(key).encode()).hexdigest()[:10]
        return self.products_dir/(self.identifier(tag+'_'+key[-1][:28])+".CATProduct")

    @staticmethod
    def product_plan(model):
        """All group datums stay at identity; occurrences retain their world pose."""
        groups={():dict(occurrences=[],children=[])}
        for occurrence in model.occ:
            path=tuple(occurrence.path)
            for length in range(1,len(path)+1):
                key=path[:length]
                if key not in groups:
                    groups[key]=dict(occurrences=[],children=[])
                    groups[key[:-1]]['children'].append(key)
            groups[path]['occurrences'].append(occurrence)
        # Children are saved and closed before any parent reads their files.
        return [(key,groups[key]) for key in sorted(groups,key=lambda k:(-len(k),k))]

    def close_owned_document(self,key):
        doc=self.docs.get(key)
        if doc is None:return
        try:doc.Close()
        except Exception as exc:
            # Never continue opening more windows if one cannot be released.
            raise RuntimeError('Could not close generated document '+str(key)+
                               '; stopping before opening the next document.') from exc
        del self.docs[key]

    def _write_product(self,doc,key,plan,counts,total):
        """Only the current group's COM references live in this stack frame."""
        import hashlib
        product=doc.Product
        label=self.root_name if not key else key[-1]
        tag='' if not key else hashlib.sha256('/'.join(key).encode()).hexdigest()[:10]+'_'
        product.PartNumber=self.identifier(tag+label)
        doc.Activate()
        path=self.product_path(key)
        refs={}
        for child in plan['children']:
            product.Products.AddComponentsFromFiles((str(self.product_path(child)),),"All")
            inst=product.Products.Item(product.Products.Count)
            inst.Name=child[-1]
            inst.Position.SetComponents(self.arr(pose()))
            doc.SaveAs(str(path))  # Preserve each attached subgroup, including root.
        for index,o in enumerate(plan['occurrences'],1):
            if o.part not in refs:
                product.Products.AddComponentsFromFiles((str(self.part_path(o.part)),),"All")
                inst=product.Products.Item(product.Products.Count)
                refs[o.part]=inst.ReferenceProduct
            else:
                inst=product.Products.AddComponent(refs[o.part])
            counts[o.part]+=1
            inst.Name=f"{o.part}.{counts[o.part]:03d}"
            inst.Position.SetComponents(self.arr(o.matrix))
            # Color is already stored in the CATPart. Repeating Selection/color
            # work 4,709 times used to add substantial COM and display overhead.
            self.placed_count+=1
            if self.placed_count%100==0:
                print(f'{self.progress_label}: {self.placed_count}/{total} instances placed',flush=True)
            if index%250==0:
                product.Update();doc.SaveAs(str(path))
        product.Update();doc.SaveAs(str(path))
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError('Product was not saved: '+str(path))
        # Nothing except the document itself is retained by the caller.
        return path

    def create_product(self,key,plan,counts,total,keep_open=False):
        owned=('Product',key)
        doc=self.app.Documents.Add("Product")
        self.docs[owned]=doc
        success=False
        try:
            path=self._write_product(doc,key,plan,counts,total)
            success=True
            return path,doc if keep_open else None
        finally:
            if not (success and keep_open):self.close_owned_document(owned)


    def check_open_names(self,model):
        # Earlier failed documents can reserve the requested PartNumbers in V5.
        # Stop BEFORE creating anything; never close somebody else's document.
        reserved={self.identifier(name) for name in model.parts}|{self.identifier(self.root_name)}
        conflicts=[]
        for i in range(1,self.app.Documents.Count+1):
            document=self.app.Documents.Item(i)
            try:
                part_number=str(document.Product.PartNumber)
            except Exception:
                continue
            if part_number in reserved: conflicts.append(str(document.Name))
        if conflicts:
            raise RuntimeError("Previous generated documents with the same names are still open. "
                "Close ONLY those documents in CATIA, preserving any edits you need, and run again:\n"+
                "\n".join(conflicts[:15]))

    def close_failed_documents(self):
        # Track only Documents.Add handles owned by this run. Never enumerate
        # and close the user's documents or references loaded by another root.
        old_alerts=None
        try:
            old_alerts=self.app.DisplayFileAlerts
            self.app.DisplayFileAlerts=False
        except Exception as exc:self.warnings.append('Cannot set alerts during failure cleanup: '+str(exc))
        try:
            for key in list(self.docs):
                try:self.close_owned_document(key)
                except Exception as exc:self.warnings.append(str(exc))
        finally:
            if old_alerts is not None:
                try:self.app.DisplayFileAlerts=old_alerts
                except Exception as exc:self.warnings.append('Cannot restore alerts after failure: '+str(exc))

    def build(self,model):
        self.check_open_names(model)
        old_refresh=self.app.RefreshDisplay
        old_alerts=self.app.DisplayFileAlerts
        old_doc=self.app.ActiveDocument if self.app.Documents.Count else None
        try:
            self.app.RefreshDisplay=False
            self.app.DisplayFileAlerts=False
            self.root_doc=None
            # Do not create a root Product or keep all master windows open here.
            for i,spec in enumerate(model.parts.values(),1):
                self.create_part(spec)
                print(f'SAVED + CLOSED MASTER {i}/{len(model.parts)}: {spec.name}',flush=True)
            self.placed_count=0
            counts=Counter()
            plan=self.product_plan(model)
            for index,(key,group) in enumerate(plan,1):
                is_root=not key
                path,doc=self.create_product(key,group,counts,len(model.occ),keep_open=is_root)
                if is_root:self.root_doc=doc
                label='/'.join(key) if key else self.root_name
                print(f'{"SAVED ROOT" if is_root else "SAVED + CLOSED PRODUCT"} '
                      f'{index}/{len(plan)}: {label} -> {path}',flush=True)
            root_path=self.product_path(())
            self.root_doc.Activate()
            self.app.RefreshDisplay=True
            try:self.app.ActiveWindow.ActiveViewer.Reframe()
            except Exception as exc:self.warnings.append('View reframe only: '+str(exc))
            # The final root is intentionally left open for the caller/user.
            self.docs.pop(('Product',()),None)
            return root_path
        except Exception:
            self.close_failed_documents()
            if old_doc is not None:
                try:old_doc.Activate()
                except Exception:pass
            raise
        finally:
            # An RPC-disconnected application may reject even property setters.
            # Keep the original feature/build exception instead of masking it.
            for name,value in (('RefreshDisplay',old_refresh),('DisplayFileAlerts',old_alerts)):
                try:setattr(self.app,name,value)
                except Exception as exc:self.warnings.append('Cannot restore '+name+': '+str(exc))

def write_reports(model,folder):
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"layout_manifest.json").write_text(json.dumps(model.serializable(),indent=2,ensure_ascii=False),encoding="utf-8")
    (folder/"validation.json").write_text(json.dumps(model.audit(),indent=2),encoding="utf-8")
    (folder/"capacity_targets.json").write_text(json.dumps(model.capacity(),indent=2,ensure_ascii=False),encoding="utf-8")
    with (folder/"line_connections.csv").open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.writer(f)
        writer.writerow(["Line","Weigher","DedicatedTransfer","Bagger","Fill_g","Target_bags_per_min","TubeAxis_X_mm","TubeAxis_Y_mm"])
        for c in model.connections:
            writer.writerow([c["line"],c["weigher"],c["line"]+"/DedicatedTransfer",c["bagger"],
                             c["nominal_fill_g"],c["target_bags_per_min"],*c["bagger_inlet"][:2]])
    (folder/"control_sequence.txt").write_text(
        "DESIGN SEQUENCE ONLY - this Python file generates CAD, not executable PLC logic.\n"
        "Repeat independently for Line_01 ... Line_10:\n"
        "1. Buffer-low sensor requests the matching radial distribution branch.\n"
        "2. Metering feeder runs coarse, then fine, using its own load cell feedback.\n"
        "3. Stop feeding and wait for stable target weight. Signal WEIGHT_READY.\n"
        "4. Wait for this lane's BAGGER_READY / formed-bag bottom seal confirmation.\n"
        "5. Open only this lane's weigh hopper gate into its dedicated hollow chute.\n"
        "6. Confirm DUMP_COMPLETE, close gate, confirm zero/tare, and refill.\n"
        "7. The bagger controls film index, gas flush, sealing and cutting.\n"
        "Stop/refill/overweight/fault timing and food trials remain to be engineered.\n"
        "No tenfold performance guarantee: common infeed and each net-weighing cycle must meet the target.\n",
        encoding="utf-8")
    counts=Counter(o.part for o in model.occ)
    with (folder/"BOM.csv").open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.writer(f); writer.writerow(["PartNumber","Quantity","Type","Note"])
        for p in model.parts.values(): writer.writerow([p.name,counts[p.name],p.kind,p.note])
    tree={}
    for o in model.occ:
        node=tree
        for item in o.path: node=node.setdefault(item,{})
        node[o.part+" [shared CATPart]"]={}
    lines=[ROOT_NAME]
    def visit(node,depth):
        for key,value in node.items():
            lines.append("  "*depth+key)
            visit(value,depth+1)
    visit(tree,1)
    (folder/"product_tree.txt").write_text("\n".join(lines),encoding="utf-8")

def archive_generated(folder):
    dest=folder.parent/(ROOT_NAME+".zip")
    if dest.exists(): raise FileExistsError("Archive already exists: "+str(dest))
    with zipfile.ZipFile(dest,"x",zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file(): z.write(p,p.relative_to(folder.parent))
    return dest

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config",type=Path,help="Optional explicit JSON settings file")
    parser.add_argument("--out",type=Path,help="Parent folder; generated folder is always '12_Packaging_10Line'")
    parser.add_argument("--dry-run",action="store_true",help="Write manifest, BOM, audit and SVG previews only; CATIA not required")
    parser.add_argument("--smoke-test",action="store_true",help="Test critical COM features in a small separate assembly")
    parser.add_argument("--launch",action="store_true",help="Start CATIA when no running instance exists")
    args=parser.parse_args(argv)
    cfg=json.loads(args.config.read_text(encoding="utf-8-sig")) if args.config else {}
    unknown=set(cfg)-set(DEFAULTS)
    if unknown: parser.error("Unknown configuration keys: "+", ".join(sorted(unknown)))
    model=Model(cfg).build()
    audit=model.audit()
    if not audit["passed"]: raise RuntimeError(json.dumps(audit,indent=2))
    if args.smoke_test:
        # One occurrence of each critical geometry, kept separate from the full model.
        keep={next(p.name for p in model.parts.values() if p.kind=="profile"),
              next(p.name for p in model.parts.values() if p.kind=="bracket"),
              next(p.name for p in model.parts.values() if p.kind=="belt"),
              next(p.name for p in model.parts.values() if p.kind=="housing"),
              "LaneTransferFunnel_D320_to180_H248","DistributionCone_Capped_D1400_H350",
              "TransferClamp_D204_d180_WithLug_T20",
              next(k for k in model.parts if k.startswith("AnnularDeckSector_"))}
        complete=model
        model=Model(cfg); model.smoke_only=True
        model.parts={k:v for k,v in complete.parts.items() if k in keep}
        seen=set()
        for o in complete.occ:
            if o.part in keep and o.part not in seen:
                model.occ.append(o); seen.add(o.part)
        audit=model.audit()
    if args.out:
        parent=args.out.expanduser().resolve()
    else:
        prefix="preview" if args.dry_run else "smoke_test" if args.smoke_test else "generated"
        # The first full run uses the user's requested folder directly.
        parent=HERE if not (args.dry_run or args.smoke_test) else HERE/(prefix+"_"+datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
        if (parent/ROOT_NAME).exists() or (parent/(ROOT_NAME+".zip")).exists():
            parent=HERE/(prefix+"_"+datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    folder=parent/ROOT_NAME
    if (parent/(ROOT_NAME+".zip")).exists() and not args.dry_run:
        raise FileExistsError("ZIP already exists; choose a new --out directory")
    if folder.exists() and any(folder.iterdir()):
        raise FileExistsError("Refusing to replace existing files. Choose a new --out directory: "+str(folder))
    folder.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(),logging.FileHandler(folder/"build.log",encoding="utf-8")])
    write_reports(model,folder)
    write_previews(model,folder)
    if args.dry_run:
        LOG.info("OFFLINE PASS: %s",json.dumps(audit))
        LOG.info("No CATPart or CATProduct was created. Reports: %s",folder)
        return 0
    try:
        builder=CatiaBuilder(folder,args.launch)
        root_path=builder.build(model)
        for name in ("build_catia.py","model.py","preview.py","config.json","README_KO.md"):
            if (HERE/name).is_file():
                (folder/"Source").mkdir(exist_ok=True)
                shutil.copy2(HERE/name,folder/"Source"/name)
        entry=Path(sys.modules["__main__"].__file__).resolve()
        if entry.is_file():
            (folder/"Source").mkdir(exist_ok=True)
            shutil.copy2(entry,folder/"Source"/entry.name)
        # README is embedded by the single-file distribution.
        if globals().get("EMBEDDED_README"):
            (folder/"README_KO.md").write_text(EMBEDDED_README,encoding="utf-8")
        (folder/"build_status.json").write_text(json.dumps({"CATIA_saved":True,"assembly":str(root_path),
                 "master_parts":len(model.parts),"instances":len(model.occ),"warnings":builder.warnings},indent=2),encoding="utf-8")
        # Flush the log before packaging. ZIP contains actual generated CAD files.
        logging.shutdown()
        archive=archive_generated(folder)
        print("Saved assembly:",root_path)
        print("Saved ZIP:",archive)
        return 0
    except Exception:
        LOG.exception("Build stopped; no success archive has been created. See FAILED.txt.")
        (folder/"FAILED.txt").write_text(traceback.format_exc(),encoding="utf-8")
        return 1


# ============================================================================
# OFFLINE GEOMETRY CHECKS
# ============================================================================

import unittest
from math import cos,sin,pi
from collections import Counter

def signed_area(points):
    return sum(points[i][0]*points[(i+1)%len(points)][1]-points[(i+1)%len(points)][0]*points[i][1]
               for i in range(len(points)))/2

def orient(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])

class GeometryChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.model=Model().build()

    def test_all_placements_are_right_handed_rigid_transforms(self):
        self.assertTrue(self.model.audit()["passed"],self.model.audit())

    def test_profile_contours_are_simple_closed_boundaries(self):
        for w,h in ((40,40),(40,80),(80,80)):
            pts=tslot_outline(w,h); n=len(pts)
            self.assertEqual(len(set(pts)),n)
            self.assertGreater(signed_area(pts),0)
            self.assertLess(signed_area(pts),w*h)
            for i in range(n):
                a,b=pts[i],pts[(i+1)%n]
                self.assertGreater(norm(sub(a,b)),0)
                for j in range(i+2,n):
                    if i==0 and j==n-1: continue
                    c,d=pts[j],pts[(j+1)%n]
                    proper_cross=orient(a,b,c)*orient(a,b,d)<0 and orient(c,d,a)*orient(c,d,b)<0
                    self.assertFalse(proper_cross,(w,h,i,j))

    def test_continuous_belt_arc_line_joints_and_tangency(self):
        b=next(p for p in self.model.parts.values() if p.kind=="belt")
        for loop in b.features[0]["loops"]:
            seg=loop["segments"]
            def ends(s):
                if s["type"]=="line": return s["p0"],s["p1"]
                x,y=s["center"]; r=s["radius"]
                return [(x+r*cos(a),y+r*sin(a)) for a in (s["a0"],s["a1"])]
            for i,s in enumerate(seg):
                self.assertLess(norm(sub(ends(s)[1],ends(seg[(i+1)%len(seg)])[0])),1e-8)
                if s["type"]=="arc":
                    self.assertGreaterEqual(s["a0"],0)
                    self.assertLess(s["a0"],2*pi)
                    self.assertLessEqual(s["a1"],4*pi)
            for j in (1,3):
                line=seg[j]; preceding=seg[j-1]
                radial=sub(line["p0"],preceding["center"])
                tangent=sub(line["p1"],line["p0"])
                self.assertAlmostEqual(dot(radial,tangent),0,places=7)

    def test_required_conveyor_dimensions(self):
        b=next(p for p in self.model.parts.values() if p.kind=="belt")
        self.assertEqual(b.parameters["width"],800)
        self.assertEqual(b.parameters["r0"]*2,50)
        self.assertEqual(b.parameters["r1"]*2,100)
        self.assertEqual(b.features[0]["length"],800)

    def test_repeated_profiles_reference_one_master(self):
        counts=Counter(o.part for o in self.model.occ)
        name="Profile_PlatformLeg_80x80_L2100"
        self.assertEqual(counts[name],20)
        part=self.model.parts[name]
        self.assertEqual(len(part.features),1)
        self.assertEqual(len(part.features[0]["loops"]),1)

    def test_assembly_has_exactly_three_root_categories(self):
        self.assertEqual({o.path[0] for o in self.model.occ},
                         {"01_Frame","02_Internal","03_ExternalControl"})
        for o in self.model.occ:
            self.assertEqual(o.path[-1],o.part+"_Group")

    def test_bearings_are_seated_and_shaft_bore_matches(self):
        self.assertEqual(len(self.model.bearing_sets),112)
        for b in self.model.bearing_sets:
            self.assertEqual(b["shaft_d"],b["bearing_id"])
            self.assertEqual(b["bearing_od"],b["seat_d"])
            self.assertGreaterEqual(b["bearing_z"][0],b["seat_z"][0])
            self.assertLessEqual(b["bearing_z"][1],b["seat_z"][1])

    def test_standoff_mount_uses_a_real_spacer(self):
        names=[o.part for o in self.model.occ]
        self.assertEqual(names.count("Spacer_D18_d9_L20"),40)
        for joint in self.model.contacts: self.assertEqual(joint["gap"],joint["spacer"])

    def test_ten_independent_weighers_feed_ten_baggers(self):
        for i in range(10):
            line=f"Line_{i+1:02d}"
            names=Counter(o.part for o in self.model.occ if line in o.path)
            for part in ("NetWeighLoadCell_120x35x30","NetWeighHopper_Gate_150x150x2",
                         "LaneTransferTube_D180_d174_L840","FillingTube_D140_d134_L950",
                         "MeteringVibrator_180x120x60","ElectricalCabinet_350x180x650"):
                self.assertEqual(names[part],1,(line,part))
        self.assertNotIn("CollectionFunnel_D1100_to180_H350",self.model.parts)

    def test_actual_part_ports_meet_in_each_lane(self):
        for i in range(10):
            line=f"Line_{i+1:02d}"
            instances={o.part:o for o in self.model.occ if line in o.path}
            tube=instances["LaneTransferTube_D180_d174_L840"]
            funnel=instances["LaneTransferFunnel_D320_to180_H248"]
            neck=instances["Transition_D180_to140_H160"]
            gate=instances["NetWeighHopper_Gate_150x150x2"]
            self.assertLess(norm(sub(apply(tube.matrix,(0,0,0)),apply(neck.matrix,(0,0,160)))),1e-6)
            self.assertLess(norm(sub(apply(tube.matrix,(0,0,840)),apply(funnel.matrix,(0,0,0)))),1e-6)
            self.assertLess(norm(sub(apply(funnel.matrix,(0,0,248)),apply(gate.matrix,(0,0,0)))),1e-6)
            # Filling tube interfaces retain their hollow, matching ID/OD pairs.
            self.assertEqual(self.model.parts[tube.part].features[0]["loops"][1]["radius"],87)

    def test_real_deck_holes_align_with_transfer_tubes(self):
        decks=[o for o in self.model.occ if o.part.startswith("AnnularDeckSector_")]
        self.assertEqual(len(decks),10)
        holes=[]
        for deck in decks:
            f=self.model.parts[deck.part].features[0]
            opening=f["loops"][1]
            self.assertEqual(opening["type"],"circle")
            self.assertEqual(opening["radius"],120)
            holes.append(apply(deck.matrix,(*opening["center"],0)))
        for o in self.model.occ:
            if o.part!="LaneTransferTube_D180_d174_L840": continue
            at_deck=apply(o.matrix,(0,0,self.model.cfg["platform_deck_z"]-2110))
            self.assertEqual(sum(norm(sub(at_deck,h))<1e-6 for h in holes),1)

    def test_bagger_envelopes_are_separate_with_200mm_margin(self):
        # Actual part vertices must lie inside a conservative local envelope.
        xmin,xmax,ymin,ymax=-600.,980.,-680.,680.
        verts={}
        prototype=self.model.line_pose(0)
        for o in self.model.occ:
            if "04_VFFSBagger" not in o.path or "Line_01" not in o.path: continue
            if o.part not in verts:
                verts[o.part]=[p for face in geometry_faces(self.model.parts[o.part]) for loop in face for p in loop]
            for v in verts[o.part]:
                delta=sub(apply(o.matrix,v),prototype[9:])
                x,y=dot(delta,prototype[:3]),dot(delta,prototype[3:6])
                self.assertTrue(xmin-1e-5<=x<=xmax+1e-5,(o.part,x))
                self.assertTrue(ymin-1e-5<=y<=ymax+1e-5,(o.part,y))
        # Inflate each envelope by 100 mm; separating-axis test must still pass.
        rectangles=[]
        for i in range(10):
            m=self.model.line_pose(i)
            rectangles.append([apply(m,(x,y,0))[:2] for x,y in
                ((xmin-100,ymin-100),(xmax+100,ymin-100),(xmax+100,ymax+100),(xmin-100,ymax+100))])
        for i,a in enumerate(rectangles):
            for b in rectangles[i+1:]:
                separated=False
                for r in (a,b):
                    for k in range(2):
                        d=sub(r[k+1],r[k]); axis=(-d[1],d[0])
                        pa=[dot(p,axis) for p in a]; pb=[dot(p,axis) for p in b]
                        if max(pa)<min(pb) or max(pb)<min(pa): separated=True
                self.assertTrue(separated,"Bagger envelopes overlap")

    def test_profile_members_clear_transfer_holes(self):
        holes=[p["center"] for p in self.model.platform_openings]
        for o in self.model.occ:
            spec=self.model.parts[o.part]
            if "03_AnnularPlatform" not in o.path or spec.kind!="profile": continue
            a=apply(o.matrix,(0,0,0)); b=apply(o.matrix,(0,0,spec.parameters["length"]))
            half_diag=(spec.parameters["width"]**2+spec.parameters["height"]**2)**.5/2
            if max(a[2],b[2])+half_diag<2110 or min(a[2],b[2])-half_diag>self.model.cfg["platform_deck_z"]+8: continue
            ab=sub(b,a); denom=dot(ab,ab)
            for h in holes:
                frac=max(0,min(1,dot(sub(h,a),ab)/denom))
                p=tuple(a[j]+frac*ab[j] for j in range(3))
                self.assertGreater(norm(sub(h,p)),90+half_diag,(o.part,h))

    def test_platform_support_beams_clear_bagger_top(self):
        # Highest bagger frame is z=2050 +/- 40; overhead beams require clearance.
        bagger_top=2090
        members=[o for o in self.model.occ if "03_AnnularPlatform" in o.path and
                 any(tag in o.part for tag in ("Chord_","RadialDeckBeam_","TransferOpeningBeam_"))]
        self.assertTrue(members)
        for o in members:
            for face in geometry_faces(self.model.parts[o.part]):
                for loop in face:
                    for p in loop:
                        self.assertGreaterEqual(apply(o.matrix,p)[2]-bagger_top,29.999,(o.part,p))

    def test_capacity_targets_are_not_claimed_as_measured(self):
        cap=self.model.capacity()
        self.assertEqual(cap["theoretical_bags_per_min"],300)
        self.assertEqual(cap["finished_product_kg_per_hour_at_target"],1530)
        self.assertIn("not measured",cap["status"])


EMBEDDED_README = '# 12_Packaging_10Line — 원형 독립 계량 10채널 / 포장기 10대\n\n실행 파일은 packaging_machine.py 하나입니다.\n\n1. CATIA V5를 켭니다. 이전 생성 모델과 같은 이름의 문서가 열려 있다면 필요한 편집을 저장한 후 해당 문서만 닫습니다.\n2. Windows PowerShell에서 실행합니다.\n\n    py -m pip install pywin32\n    py packaging_machine.py\n\npywin32가 설치되어 있다면 설치 명령은 생략합니다.\nCATIA 실행 로그가 표시되는 창 대신 PS C:\\...> 프롬프트가 있는 PowerShell을 사용합니다.\n부품 생성과 약 4,700개 인스턴스 배치가 끝날 때까지 CATIA를 조작하거나 닫지 않습니다.\n마지막 Saved assembly와 Saved ZIP이 모두 표시되면 저장까지 완료입니다.\n\n선택 명령:\n    py packaging_machine.py --self-test\n    py packaging_machine.py --dry-run\n    py packaging_machine.py --smoke-test\nsmoke-test는 대표 형상 일부만 생성하며 완성된 생산 설비가 아닙니다.\n\n생성 구조:\n    12_Packaging_10Line/\n      12_Packaging_10Line.CATProduct\n      Parts/                  개별 CATPart\n      Products/               별도 문서로 생성되는 하위 Product\n      Source/                 실행한 Python 파일\n      BOM.csv, product_tree.txt, layout_manifest.json, validation.json\n      line_connections.csv    Line_01~Line_10의 일대일 연결표\n      capacity_targets.json   생산 목표와 가정\n      control_sequence.txt    제어 순서 설명 (실행되는 PLC가 아님)\n      build_status.json, build.log, 미리보기 SVG\n    12_Packaging_10Line.zip\n기존 출력이 있으면 generated_날짜_시각 폴더로 분리하여 새로 생성합니다.\nCATProduct를 열 때 Parts와 Products 폴더를 함께 보관합니다.\n\n구성은 1~4번입니다. 배출 컨베이어·검사기 등 원본 사진의 5~7번은 포함하지 않습니다.\n1. 공통 경사 벨트 컨베이어: 폭800, 종동/지지 롤러Ø50, 구동 풀리Ø100.\n2. 중앙 분배부와 독립 계량 10채널: 진동 분배통로 -> 공급 버퍼 -> 개별 진동 정량 공급기 -> 로드셀 계량 호퍼.\n3. 원형 작업대: 외경10100, 내경5500, 높이2200, 전용 낙하관 관통 구멍Ø240 10개, 계단과 난간.\n4. 원형으로 배치한 VFFS 포장기 10대: 배치 중심 반경4000. 각 기계의 전면과 HMI는 바깥쪽을 향합니다.\n\nLine_01 계량부 -> Line_01 전용 중공관 -> Line_01 포장기.\n같은 방식으로 Line_10까지 10개 독립 경로를 구성했습니다.\n기존 조합계량기의 호퍼 하나를 독립 정량기처럼 취급하지 않습니다.\n각 계량부가 목표 중량 한 봉분을 독립적으로 만들도록 버퍼, 정량 공급 구동기, 로드셀, 배출 게이트와 신호를 구분합니다.\n기존 중앙 집합 슈트는 제거했습니다. 다른 라인의 계량 제품을 합치지 않습니다.\n계량 호퍼는 약8.17 L의 개념 용량입니다. 실제 85g 칩의 쌓임 부피와 파손·걸림 시험에 따라 조정해야 합니다.\n긴 낙하 경로는 칩 파손과 배출 시간을 시험하고 필요하면 완충 슈트 등으로 상세 설계해야 합니다.\n\n생산 목표:\n- 한 봉85g, 라인당30봉/분, 10개 라인 합계300봉/분은 설계 목표입니다.\n- 위 목표의 완제품 공급량은1530kg/h입니다. 원료 감자 투입량과는 다릅니다.\n- 유효 생산계수0.75를 가정한 시나리오는225봉/분,1147.5kg/h입니다. 실측값이 아닙니다.\n- 실제 생산량은 공통 공급/분배 능력, 독립 계량 속도·정확도, 봉지 성형·실링, 질소·압축공기 공급과 가동률에 따라 결정됩니다.\n- 포장기 개수만 늘려10배 생산을 보장할 수 없습니다. 단일 계량의 최종 정량 정확도와 조합계량의 성능도 다릅니다.\n\n제품 트리:\n01_Frame -> 01_Profile / 02_Plate / 03_Bracket / 04_Fastener / 05_Spacer -> 장치 -> Line_번호 -> 부품 그룹.\n02_Internal -> 장치 -> Line_번호 -> 기능 그룹 -> 부품 그룹.\n03_ExternalControl -> 장치 -> Line_번호 -> 기능 그룹 -> 부품 그룹.\n동일 형상은 CATPart 하나를 Products.AddComponent 참조로 재사용합니다.\n각 프로파일은 단일 폐곡선 스케치와 하나의 Pad입니다. UI의 Multi Instantiation 명령을 직접 실행하는 방식은 아닙니다.\n\n표시 색상: 프레임 은색, 판재/호퍼 밝은 회색, 브라켓/하우징 진회색, 벨트/모터 파랑,\n실링부 주황, 제어함 흰색, HMI 청록, 필름 롤 크림색. 실제 재료 물성을 지정한 것은 아닙니다.\n베어링은 원통 시트에 들어가며, 레이스웨이·볼·나사산·끼워맞춤 공차는 단순화했습니다.\n성형 칼라는 개념 원추 쉘입니다. 실제 필름 전개면이 아닙니다.\n미리보기의 프로파일은 외곽 사각형으로 단순화하지만 CATPart는 T홈 단면을 사용합니다.\n\n이 모델은 정적 CAD 개념 조립품입니다. 전체 실형상 간섭 검사, 하중/처짐, 식품 위생 상세 설계,\n안전장치 및 실제 제어 배선·PLC·DMU 운동·가스 배관의 제작 설계가 완료된 상태가 아닙니다.\n코드 검사와 수학적 배치 검사는 실제 CATIA 형상 업데이트 검사와 다릅니다.\n오류 시 해당 실행 폴더의 FAILED.txt 및 build.log를 확인합니다.\n\n참고:\nhttps://www.heatandcontrol.com/index.php/blog/economies-of-scale-ishida-ccw-as-multihead-weigher\nhttps://www.heatandcontrol.com/model/left-right-center-diverting-weigher-infeed\nhttps://pycatia.readthedocs.io/en/latest/api/pycatia/product_structure_interfaces/products.html\nhttps://pycatia.readthedocs.io/en/latest/api/pycatia/sketcher_interfaces/factory_2D.html\nhttps://pycatia.readthedocs.io/en/latest/api/pycatia/in_interfaces/vis_property_set.html\n'


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(GeometryChecks)
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print("ERROR:", error, file=sys.stderr)
        raise SystemExit(1)
