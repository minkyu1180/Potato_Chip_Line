"""Native, floor-mounted receiver and elevator for the CC downward outlet.

Local X points toward station 5's -Y side. Station 5 remains on the floor.
Dimensions describe the supplied CC stand, not an arbitrary vendor machine.
"""
import math

REVISION='TRANSFER-05-06-R22'
SIDE_AXES=((0.,-1.,0.),(1.,0.,0.),(0.,0.,1.))


def design_data(outlet_z=500.,inlet_z=1200.,inlet_width=700.):
    if outlet_z<400 or inlet_z<500:
        raise ValueError('05-06 receiver requires the CC outlet >=400 mm and downstream inlet >=500 mm')
    run=max(3200.,(inlet_z-140.)/math.tan(math.radians(19.)))
    return dict(revision=REVISION,receiver_width_mm=440.,receiver_deck_z_mm=150.,
        receiver_start_x_mm=-300.,receiver_end_x_mm=1000.,receiver_guide_top_z_mm=220.,
        incline_start_mm=[1100.,0.,140.],incline_end_mm=[1100.+run,0.,inlet_z],
        outlet_mm=[1300.+run,0.,inlet_z],incline_width_mm=max(500.,inlet_width),
        incline_horizontal_run_mm=run,incline_angle_deg=math.degrees(math.atan2(inlet_z-140.,run)),
        outlet_z_mm=outlet_z,drop_to_belt_mm=outlet_z-150.,station5_elevation_mm=0.,
        stand_lower_tie_bottom_z_mm=250.,nominal_tie_clearance_mm=30.,
        receiver_outer_rail_half_width_mm=248.,nominal_column_clearance_mm=12.,
        receiver_rail_top_z_mm=70.,stand_foot_plate_bottom_z_mm=88.,nominal_foot_plate_clearance_mm=18.,
        station6_yaw_relative_to_station5_deg=-90.,
        dimensions_basis='Current CC stand: outlet X419, columns X119/1478, Y+/-460; lower ties Z250..300.',
        scope='Generated editable geometry and port layout; CATIA clash, sanitation and load validation by user.')


def geometry(upstream,downstream):
    import build_line as b
    from finishing_design import weld_and_assign,configuration
    d=design_data(upstream['outlet'][2],downstream['inlet'][2],downstream.get('inlet_width_mm',700.))
    s=[];name='Transfer_05_06';w=d['receiver_width_mm'];deck=d['receiver_deck_z_mm']
    # Narrow rails pass between CC columns and below the Z250 lower ties.
    # End bearings and the outboard motor are away from the tie crossing at X460.
    for label,z in (('Carrying_Belt',147.),('Return_Belt',94.)):
        s.append(b.box(name+'_'+label,(-300.,-w/2,z),(1300.,w,3.),b.BELT))
    for x in (-300.,1000.):
        s.append(b.cylinder(name+f'_Drum_{x:g}',(x,-220,122),(x,220,122),25,b.ROLLER,22))
        s.append(b.cylinder(name+f'_Axle_{x:g}',(x,-254,122),(x,254,122),10,b.FRAME))
        for side in (-1,1):
            y=side*240.
            s.append(b.poly(name+f'_Bearing_{x:g}_{side}',b.rect(60,40),16,
                (x,y-8,122),b.AY,b.MOTOR,holes=((0,0,10),)))
            s.append(b.box(name+f'_Bearing_Riser_{x:g}_{side}',(x-30,y-8,70),(60,16,32)))
            s.append(b.tube(name+f'_Receiver_Leg_{x:g}_{side}',(x,y,12),(x,y,40),30,30,3))
            s.append(b.box(name+f'_Receiver_Foot_{x:g}_{side}',(x-40,y-40,0),(80,80,12)))
        s.append(b.tube(name+f'_Receiver_Cross_{x:g}',(x,-225,25),(x,225,25),30,30,3))
    for side in (-1,1):
        s.append(b.tube(name+f'_Receiver_Rail_{side}',(-330,side*240,55),(1030,side*240,55),16,30,2.5))
    b.continuous_guides(s,name+'_Receiver_Guide',((-300,0,deck),(1000,0,deck)),w,70,3)
    # An open-bottom four-wall receiver, not a plate blocking the cone outlet.
    upper=[(-250,-250,d['outlet_z_mm']),(250,-250,d['outlet_z_mm']),
           (250,250,d['outlet_z_mm']),(-250,250,d['outlet_z_mm'])]
    lower=[(-250,-220,220),(250,-220,220),(250,220,220),(-250,220,220)]
    for i in range(4):
        j=(i+1)%4
        s.append(b.quad_sheet(name+f'_Receiving_Hopper_Wall_{i+1}',(upper[i],upper[j],lower[j],lower[i]),3))
    # Back closure; the forward opening above the moving belt remains 70 mm high.
    s.append(b.box(name+'_Receiver_Back',(-253,-220,150),(3,440,70)))
    s.append(b.box(name+'_Drip_Tray',(-330,-220,40),(1360,440,2),holes=((500,0,12),)))
    for side in (-1,1):
        s.append(b.box(name+f'_Tray_Edge_{side}',(-330,side*220-(2 if side>0 else 0),42),(1360,2,18)))
    b.fryer_drive(s,name+'_Receiver_Drive',(1000,0,122),w,840)
    # Gearbox feet fill the gap to its shelf, which has a grounded pedestal.
    s.append(b.box(name+'_Receiver_Gearbox_Foot',(950,240,51),(100,64,6)))
    s.append(b.tube(name+'_Receiver_Motor_Post',(1000,320,12),(1000,320,37),40,40,3))
    s.append(b.box(name+'_Receiver_Motor_Foot',(950,270,0),(100,100,12)))
    start=tuple(d['incline_start_mm']);end=tuple(d['incline_end_mm']);iw=d['incline_width_mm']
    b.prep_tapered_chute(s,name+'_Belt_Bridge',(1000,0,150),start,w,iw,100)
    first=len(s);est=dict(b.PREP_ESTIMATES,mesh_tile_length=10000.)
    b.fryer_conveyor(s,name+'_Elevator',start,end,iw,35,est,iw+400,True)
    # Continuous purchased food-contact belt: coarse mesh openings would drop slices.
    for q in s[first:]:
        if '_MeshTile_' in q['name']:q['loops']=();q['material']='Food-contact conveyor belt; purchased specification pending'
    direction=b.unit(b.vec(start,end));normal=b.unit(b.cross(direction,(0,1,0)))
    # Terminate rails before bearing housings: the generic conveyor's full-length
    # rails otherwise occupy the same space as its end bearings.
    for n in range(first,len(s)):
        q=s[n]
        if '_SideRail_' in q['name']:
            a,z=q['profile_ends']
            s[n]=b.tube(q['name'],b.plus(a,b.scale(direction,80)),b.plus(z,b.scale(direction,-80)),35,45,3)
    for j,p in enumerate((start,end),1):
        c=b.plus(p,b.scale(normal,-44))
        for side in (-1,1):
            y=side*(iw/2+24)
            s.append(b.tube(name+f'_End_Bearing_Post_{j}_{side}',(c[0],y,12),(c[0],y,c[2]-48),30,30,3))
            s.append(b.box(name+f'_End_Bearing_Foot_{j}_{side}',(c[0]-40,y-40,0),(80,80,12)))
    c=b.plus(end,b.scale(normal,-44));y=iw/2+100
    s.append(b.tube(name+'_Elevator_Motor_Post',(c[0],y,12),(c[0],y,c[2]-85),50,50,3))
    s.append(b.box(name+'_Elevator_Motor_Foot',(c[0]-60,y-60,0),(120,120,12)))
    s.append(b.box(name+'_Elevator_Gearbox_Foot',(c[0]-50,iw/2+20,c[2]-71),(100,64,6)))
    b.continuous_guides(s,name+'_Elevator_Guide',(start,end),iw,120,3)
    length=b.norm(b.vec(start,end))
    for n in range(1,int(length//200)):
        center=b.plus(start,b.scale(direction,n*200.))
        s.append(b.poly(name+f'_Elevator_Cleat_{n:02d}',b.rect(8,iw-12),15,center,(direction,(0,1,0),normal),b.BELT))
    # Legs meet the sloping rail underside via fitted wedge seats, not through it.
    slope=(end[2]-start[2])/(end[0]-start[0])
    rail_bottom=lambda x:start[2]+slope*(x-start[0])-(35+22.5)/normal[2]
    for x in (start[0]+120.,(start[0]+end[0])/2,end[0]-120.):
        low=rail_bottom(x-20)-6
        for side in (-1,1):
            y=side*(iw/2+35)
            s.append(b.tube(name+f'_Elevator_Leg_{x:g}_{side}',(x,y,12),(x,y,low),40,40,3))
            s.append(b.box(name+f'_Elevator_Foot_{x:g}_{side}',(x-55,y-55,0),(110,110,12)))
            vertices=((x-20,-low),(x+20,-low),(x+20,-rail_bottom(x+20)),(x-20,-rail_bottom(x-20)))
            s.append(b.poly(name+f'_Fitted_Rail_Seat_{x:g}_{side}',vertices,40,(0,y-20,0),b.AY))
        s.append(b.tube(name+f'_Elevator_Cross_{x:g}',(x,-iw/2-15,35),(x,iw/2+15,35),30,30,3))
    # Final horizontal nose opens directly at station 6's inlet.
    b.prep_tapered_chute(s,name+'_Discharge',end,tuple(d['outlet_mm']),iw,downstream.get('inlet_width_mm',700.),120)
    for q in s:
        if 'Carrying_Belt' in q['name'] or 'Return_Belt' in q['name'] or '_Cleat_' in q['name']:
            q['material']='Food-contact conveyor belt; purchased specification pending'
    s=weld_and_assign(6,s,configuration(6))
    for q in s:
        if q.get('part_type')=='Welded Member' or '_Seal_Cap_' in q['name'] or '_Fitted_Rail_Seat_' in q['name']:
            q.update(category='Frame',group='Welded Support Frame')
    return s,dict(name=name,description='Low receiver under CC stand, side withdrawal and cleated elevator to blancher.',
        inlet=(0.,0.,d['outlet_z_mm']),outlet=d['outlet_mm'],inlet_width_mm=492.,
        outlet_width_mm=downstream.get('inlet_width_mm',700.),length=d['outlet_mm'][0],
        connection_revision=REVISION,upstream_station=5,downstream_station=6,
        inlet_axes_relative_to_upstream=SIDE_AXES,outlet_axes_relative_to_transfer=b.I,
        design=d)
