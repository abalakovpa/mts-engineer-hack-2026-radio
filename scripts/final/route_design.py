#!/usr/bin/env python3
"""Route balanced or unequal eight-antenna zones using listed 2/4-way devices."""
import copy
import math
from build_project import route, projection, V, EDGES, ZONES, local_groups

def hub_for(ants,zone):
    points=[(a['x'],a['y']) for a in ants]
    hubs=[zone]+[min((projection(p,V[a],V[b]) for a,b in EDGES),key=lambda v:v[2])[0] for p in points]
    return min(hubs,key=lambda h:route(zone,h)[0]+sum(route(h,p)[0] for p in points))

def construct(project):
    ants=copy.deepcopy(project['antennas']);head=tuple(project['head'])
    assert len(ants)==32 and len({a['id'] for a in ants})==32
    modes={str(z):project.get('zone_modes',{}).get(str(z),'balanced') for z in range(1,5)}
    classes=project.get('power_classes',{})
    zones=project.get('zone_hubs',ZONES)
    assert len(zones)==4 and all(len(point)==2 for point in zones)
    trunk=[];subfeeds=[];drops=[]
    for z in range(1,5):
        local=[a for a in ants if a['zone']==z];assert len(local)==8
        zone=tuple(zones[z-1]);length,points=route(head,zone)
        trunk.append(dict(id=f'T{z}',length=length,points=points,cable='7/8'))
        if modes[str(z)]=='balanced':
            ids=[i for i,a in enumerate(ants) if a['zone']==z]
            partitions=[([ants[i] for i in indexes],hub,g,'balanced') for g,(indexes,hub) in enumerate(local_groups(ids,ants,zone),1)]
        else:
            assert modes[str(z)]=='unequal'
            direct=[a for a in local if classes[a['id']]=='direct'];pair=[a for a in local if classes[a['id']]=='pair'];quartet=[a for a in local if classes[a['id']]=='quartet']
            assert (len(direct),len(pair),len(quartet))==(2,2,4)
            partitions=[(direct,zone,0,'direct'),(pair,hub_for(pair,zone),1,'pair'),(quartet,hub_for(quartet,zone),2,'quartet')]
        for members,hub,g,kind in partitions:
            if g:
                length,points=route(zone,hub)
                subfeeds.append(dict(id=f'F{z}-{g}',length=length,points=points,cable='7/8'))
            for slot,a in enumerate(sorted(members,key=lambda a:a['id']),1):
                a['subgroup']=g;a['hub']=list(hub);a['power_class']=kind;a['leaf_output']=slot
                a['distribution_adjustment_db']=(-10*math.log10(2)-.5 if kind=='direct' else 10*math.log10(2) if kind=='quartet' else 0)
                length,points=route(hub,(a['x'],a['y']));a['points']=points;a['drop12_m']=length
                drops.append(dict(id=a['id'],length=length,points=points,cable='7/8' if length>15 else '1/2'))
    routes=trunk+subfeeds+drops
    for t in routes:
        if t['length']<1e-6:t.update(cable='jumper',jumper_length_m=3,assumed_loss_db=.2)
    for a in ants:
        t=trunk[a['zone']-1];d=next(r for r in drops if r['id']==a['id'])
        path=[t,d]
        if a['subgroup']:path.append(next(r for r in subfeeds if r['id']==f'F{a["zone"]}-{a["subgroup"]}'))
        a['length78_m']=sum(r['length'] for r in path if r['cable']=='7/8')
        a['length12_m']=sum(r['length'] for r in path if r['cable']=='1/2')
        a['additional_jumper_loss_db']=sum(r.get('assumed_loss_db',0) for r in path)
    ants.sort(key=lambda a:a['id']);drops.sort(key=lambda a:a['id'])
    fixed=6+1+10*math.log10(8)+1+.8+1;rf=[]
    for a in ants:
        for f,prb in [(1800,100),(2100,75),(2600,50)]:
            alpha12={1800:10.09,2100:10.99,2600:11.84+(12.66-11.84)*2/3}[f]
            alpha78={1800:5.21,2100:5.67,2600:6.39}[f]
            cable=a['length78_m']*alpha78/100+a['length12_m']*alpha12/100
            loss=fixed+a['distribution_adjustment_db']+a['additional_jumper_loss_db']+cable
            pilot=23-10*math.log10(2*prb)
            for d in (5,10,15,20):
                pl=20*math.log10(f)-27.55+25*math.log10(math.hypot(d,5.5))
                rf.append(dict(antenna=a['id'],frequency_mhz=f,d_horizontal_m=d,cable_loss_db=cable,
                               total_loss_db=loss,rsrp_dbm=pilot-loss+3-pl))
    return dict(status='Расчётный проект; фактические KPI не установлены',head=list(head),
                topology=dict(zones=4,per_zone=8,subgroups=2,leaf_outputs=4,zone_modes=modes),
                antennas=ants,trunks=trunk,subfeeds=subfeeds,drops=drops,fixed_loss_db=fixed,rf_points=rf,
                local_jumper_count=2*sum(t['cable']=='jumper' for t in routes),
                cable78_installed=2*sum(t['length'] for t in routes if t['cable']=='7/8'),
                cable12_installed=2*sum(t['length'] for t in routes if t['cable']=='1/2'))
