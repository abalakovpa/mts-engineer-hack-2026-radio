#!/usr/bin/env python3
"""Screen locations and real passive power splits; adopt only after routed check."""
from pathlib import Path
from itertools import combinations
import copy
import hashlib
import json
import math
import argparse
import numpy as np
from shapely import STRtree
from shapely.geometry import shape,Point,LineString,MultiPoint
from shapely.ops import polylabel
from coverage import fields,compact_walls,crossings_many,column_losses
from build_project import route,ZONES
from route_design import construct

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'design/final/revision'

def main():
    p=argparse.ArgumentParser();p.add_argument('--step',type=float,default=.5);p.add_argument('--passes',type=int,default=2);args=p.parse_args()
    OUT.mkdir(exist_ok=True)
    model=json.loads((ROOT/'design/final/coverage/area-model.json').read_text())
    old=json.loads((ROOT/'design/final/candidate.json').read_text())
    base=json.loads((ROOT/'design/final/coverage/baseline-candidate.json').read_text())
    current_by_source={a['baseline_id']:a for a in old['antennas']}
    ants=copy.deepcopy(base['antennas'])
    for a in ants:
        a['baseline_id']=a['id']
        if a['id'] in current_by_source:
            b=current_by_source[a['id']];a.update(x=b['x'],y=b['y'])
    cached=fields(model,ants,args.step);xy=cached['points'];w=cached['weights'];gid=cached['gid']
    head=old['head'];trunk=[route(tuple(head),z)[0] for z in ZONES]
    def estimated_loss(a):
        return 18.83089986991944+(trunk[a['zone']-1]+route(ZONES[a['zone']-1],(a['x'],a['y']))[0])*6.39/100
    losses=np.array([estimated_loss(a) for a in ants]);radius=cached['radius']
    base_radio=6-losses[:,None]-(20*math.log10(2600)-27.55+25*np.log10(radius))-cached['wall']-cached['columns']
    # Primary objective is reserve with closed openings, secondary deficit.
    radio=base_radio-cached['closed'];radio=radio.astype(np.float32)
    selections={z:[i for i,a in enumerate(ants) if a['zone']==z and a['baseline_id'] in current_by_source] for z in range(1,5)}
    gains={z:np.zeros(8,np.float32) for z in range(1,5)};modes={z:'balanced' for z in range(1,5)}
    schemes=[]
    for high in combinations(range(8),2):
        remaining=[i for i in range(8) if i not in high]
        for middle in combinations(remaining,2):
            g=np.full(8,-10*math.log10(2),np.float32);g[list(high)]=10*math.log10(2)+.5;g[list(middle)]=0;schemes.append(g)
    scheme=np.array([np.zeros(8,np.float32)]+schemes)
    def metric(best):
        return float(w[best>-87].sum()),float(np.dot(w,np.clip(best+87,-20,0)))
    def other_field(zone):
        return np.maximum.reduce([(radio[selections[z]]+gains[z][:,None]).max(axis=0) for z in range(1,5) if z!=zone])
    def optimize(zone,ids):
        other=other_field(zone);rows=radio[ids];winner=None
        for first in range(0,len(scheme),24):
            chunk=scheme[first:first+24]
            vals=np.maximum((rows[None,:,:]+chunk[:,:,None]).max(axis=1),other)
            covered=(vals>-87)@w;deficit=np.clip(vals+87,-20,0)@w
            index=max(range(len(chunk)),key=lambda i:(covered[i],deficit[i],-(first+i)))
            result=(float(covered[index]),float(deficit[index]),first+index)
            if winner is None or result[:2]>winner[:2]:winner=result
        return winner
    history=[]
    for sweep in range(args.passes):
        for z in range(1,5):
            ids=selections[z];best=optimize(z,ids);winning_ids=ids[:]
            unused=[i for i,a in enumerate(ants) if a['zone']==z and i not in ids]
            for slot in range(8):
                for add in unused:
                    trial=ids[:];trial[slot]=add;result=optimize(z,trial)
                    if result[:2]>best[:2]:best=result;winning_ids=trial
            selections[z]=winning_ids;gains[z]=scheme[best[2]];modes[z]='balanced' if best[2]==0 else 'unequal'
            row=dict(sweep=sweep+1,zone=z,reserve_closed_estimated_percent=best[0]/21,mode=modes[z],
                     rooms=[ants[i]['room'] for i in winning_ids]);history.append(row);print(row,flush=True)
    # Local ceiling relocation within each seeded CAD group, then full reroute.
    segments=compact_walls(model['walls']);tree=STRtree([LineString(s) for s in segments]);hull=MultiPoint(segments.reshape(-1,2)).convex_hull
    material=np.array([30 if hull.boundary.distance(LineString(s).interpolate(.5,normalized=True))<.45 else 15 for s in segments])
    full=np.concatenate((segments,np.array(model['assumed_closures'])),axis=0);ctree=STRtree([LineString(s) for s in full]);closs=np.r_[material,np.full(len(model['assumed_closures']),15.)]
    moves=[]
    for z in range(1,5):
        for slot,index in enumerate(selections[z]):
            a=ants[index];group=next(g for g in model['groups'] if a['room'] in g['rooms']);poly=shape(group['geometry'])
            origin=np.array([a['x'],a['y']]);all_rows=[radio[selections[q]]+gains[q][:,None] for q in range(1,5)]
            all_rows[z-1]=np.delete(all_rows[z-1],slot,axis=0);other=np.concatenate(all_rows).max(axis=0)
            old_score=metric(np.maximum(other,radio[index]+gains[z][slot]));best_score=old_score;winner=None
            points=[origin+np.array([dx,dy]) for dx in (-3,-1.5,0,1.5,3) for dy in (-3,-1.5,0,1.5,3)]
            centre=polylabel(poly,tolerance=.1)
            if np.linalg.norm(origin-np.array((centre.x,centre.y)))<8:points.append(np.array((centre.x,centre.y)))
            for point in points:
                if np.linalg.norm(point-origin)<.01 or not poly.covers(Point(point)):continue
                if tree.query(Point(point).buffer(.15),predicate='intersects').size:continue
                if any(np.linalg.norm(point-np.array(c['center']))<c['radius_m']+.2 for c in model['columns']):continue
                peers=[b for b in ants if b['room'] in group['rooms'] and b['baseline_id']!=a['baseline_id']]
                if len(group['rooms'])>1 and any(np.linalg.norm(point-np.array((b['x'],b['y'])))<np.linalg.norm(point-origin) for b in peers):continue
                proposed=dict(a,x=float(point[0]),y=float(point[1]));loss=estimated_loss(proposed)
                r=np.sqrt(((xy-point)**2).sum(axis=1)+5.5**2)
                values=6-loss-(20*math.log10(2600)-27.55+25*np.log10(r))-crossings_many(point,xy,full,ctree,closs)-column_losses(point,xy,model['columns'])
                score=metric(np.maximum(other,values+gains[z][slot]))
                if score>best_score:best_score=score;winner=(point,values)
            if winner:
                point,values=winner;moves.append(dict(baseline_id=a['baseline_id'],room=a['room'],before=origin.tolist(),after=point.tolist()))
                a.update(x=float(point[0]),y=float(point[1]),basis='Проектная позиция внутри восстановленного CAD-контура; выбранная по сценарию +3 дБ/закрытые проёмы')
                radio[index]=values
                print('MOVE',a['room'],point.tolist(),'reserve closed estimate',best_score[0]/21,flush=True)
        best=optimize(z,selections[z]);gains[z]=scheme[best[2]];modes[z]='balanced' if best[2]==0 else 'unequal'
    # Stable IDs assigned by zone and previous identity where possible; identities
    # are explicit project identifiers, not an assertion of existing antennas.
    chosen=[];classes={};swaps=[]
    for z in range(1,5):
        original=sorted([a for a in old['antennas'] if a['zone']==z],key=lambda a:a['id'])
        existing={a['baseline_id']:a['id'] for a in original};taken=set();pending=[]
        for slot,index in enumerate(selections[z]):
            a=copy.deepcopy(ants[index]);keep=existing.get(a['baseline_id'])
            if keep:a['id']=keep;taken.add(keep)
            else:pending.append(a)
            a['_slot']=slot;chosen.append(a)
        unused_ids=[a['id'] for a in original if a['id'] not in taken]
        for a,id in zip(pending,unused_ids):
            prev=next(b for b in original if b['id']==id);swaps.append(dict(id=id,before_room=prev['room'],after_room=a['room']))
            a['id']=id
        for a in [a for a in chosen if a['zone']==z]:
            gain=float(gains[z][a.pop('_slot')]);classes[a['id']]='direct' if gain>1 else 'quartet' if gain<-1 else 'pair'
            a.update(baseline_id=a['baseline_id'])
    project=dict(head=head,head_label='Проектная зона ВК в части 104.2',antennas=chosen,
                 zone_modes={str(z):modes[z] for z in range(1,5)},power_classes=classes)
    real=construct(project);actual=fields(model,real['antennas'],args.step)
    loss=np.array([next(r['total_loss_db'] for r in real['rf_points'] if r['frequency_mhz']==2600 and r['antenna']==a['id']) for a in real['antennas']])
    values=6-loss[:,None]-(20*math.log10(2600)-27.55+25*np.log10(actual['radius']))-actual['wall']-actual['columns']
    scores={}
    for name,extra,gap in [('nominal',0,False),('reserve3',3,False),('closed',0,True),('closed_reserve3',3,True)]:
        best=(values-extra-(actual['closed'] if gap else 0)).max(axis=0)
        scores[name]=float(actual['weights'][best>-90].sum()/21)
    result=dict(status='Полностью трассированный вариант на контрольной сетке; принятие требует сетки 0,25 м',
                step_m=args.step,baseline_commit='18204fb09b7dcd327cee8d1a408d0ef8c928512a',scores=scores,
                project_input=project,history=history,moves=moves,swaps=swaps,
                area_model_sha256=hashlib.sha256((ROOT/'design/final/coverage/area-model.json').read_bytes()).hexdigest())
    (OUT/'reserve-proposal.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (OUT/'reserve-candidate.json').write_text(json.dumps(real,ensure_ascii=False,indent=2)+'\n')
    print('ROUTED SCORES',scores,flush=True)

if __name__=='__main__':main()
