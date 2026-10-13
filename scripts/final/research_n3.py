#!/usr/bin/env python3
"""Research n=3 separately; never modify the selected design or submission.

Power assignments use real listed 2/4-way trees and their fully routed losses.
The search is local and bounded; failure is not a proof of infeasibility.
"""
from pathlib import Path
from itertools import combinations
from functools import lru_cache
import argparse
import copy
import csv
import hashlib
import json
import math
import shutil

import numpy as np
from shapely import STRtree
from shapely.geometry import Point, LineString, MultiPoint, shape
from shapely.ops import polylabel
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from coverage import fields, compact_walls, crossings_many, column_losses
from build_project import route, projection, V, EDGES, ZONES
import route_design

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'design/final/n3'
CACHE=ROOT.parent/'radio-runtime/n3-cache'
FREQUENCIES=((1800,100,5.21,10.09),(2100,75,5.67,10.99),
             (2600,50,6.39,11.84+(12.66-11.84)*2/3))
FIXED=6+1+10*math.log10(8)+1+.8+1


def write(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


@lru_cache(maxsize=200000)
def routed(a,b):
    return route(tuple(a),tuple(b))


def losses_for(design,frequency):
    return np.array([next(r['total_loss_db'] for r in design['rf_points']
        if r['antenna']==a['id'] and r['frequency_mhz']==frequency) for a in design['antennas']])


def score(field,weights):
    return float(weights[field>-90].sum()/21)


def evaluate(model,design,step,folder):
    propagation=fields(model,design['antennas'],step,cache_dir=folder)
    results={};maps={}
    uncertain=np.isin(propagation['gid'],[i for i,g in enumerate(model['groups'])
                                        if abs(g['relative_area_difference'])>.1])
    for frequency,prb,_,_ in FREQUENCIES:
        loss=losses_for(design,frequency)
        common=(23-10*math.log10(2*prb)+3-loss[:,None]-(20*math.log10(frequency)-27.55)
                -propagation['wall']-propagation['columns'])
        for label,n,extra,gaps in [('nominal',2.5,0,False),('n3',3,0,False),
                                 ('reserve3',2.5,3,False),('joint_reserve3',2.5,3,True),
                                 ('n3_closed',3,0,True),('P2',2.5,10*math.log10(6),False)]:
            values=common-10*n*np.log10(propagation['radius'])-extra
            if gaps:values-=propagation['closed']
            best=values.max(axis=0)
            if label=='joint_reserve3':best=best.copy();best[uncertain]=-np.inf
            results[f'{frequency}_{label}']=score(best,propagation['weights'])
            maps[f'{frequency}_{label}']=best
    return results,propagation,maps


class Search:
    def __init__(self,model,selected,step):
        self.model=model;self.selected=copy.deepcopy(selected);self.step=step
        self.head=tuple(selected['head']);self.hubs=[tuple(p) for p in ZONES]
        seed=json.loads((ROOT/'design/final/coverage/baseline-candidate.json').read_text())['antennas']
        current={a['baseline_id']:a for a in selected['antennas']}
        self.ants=[]
        for a in seed:
            source=a['id'];item=copy.deepcopy(current.get(source,a))
            item['baseline_id']=source;item['native_zone']=a['zone'];self.ants.append(item)
        propagation=fields(model,self.ants,step,cache_dir=CACHE/'pool')
        self.xy=propagation['points'];self.w=propagation['weights'];self.gid=propagation['gid']
        self.mask_uncertain=np.isin(self.gid,[i for i,g in enumerate(model['groups'])
                                             if abs(g['relative_area_difference'])>.1])
        self.n3=(6-(20*math.log10(2600)-27.55)-30*np.log10(propagation['radius'])
                 -propagation['wall']-propagation['columns'])
        self.joint=(6-(20*math.log10(2600)-27.55)-25*np.log10(propagation['radius'])
                    -propagation['wall']-propagation['columns']-propagation['closed']-3)
        self.joint[:,self.mask_uncertain]=-np.inf
        self.ids={z:[i for i,a in enumerate(self.ants) if a['baseline_id'] in current
                     and current[a['baseline_id']]['zone']==z] for z in range(1,5)}
        self.classes={z:[current[self.ants[i]['baseline_id']]['power_class'] for i in self.ids[z]]
                      for z in range(1,5)}
        self.loss={z:self.exact_losses(self.ids[z],self.classes[z],self.hubs[z-1]) for z in range(1,5)}
        self.history=[]
        segments=compact_walls(model['walls'])
        self.tree=STRtree([LineString(s) for s in segments])
        hull=MultiPoint(segments.reshape(-1,2)).convex_hull
        material=np.array([30 if hull.boundary.distance(LineString(s).interpolate(.5,normalized=True))<.45
                           else 15 for s in segments])
        self.full=np.concatenate((segments,np.array(model['assumed_closures'])))
        self.full_tree=STRtree([LineString(s) for s in self.full])
        self.material=material;self.segments=segments
        self.full_losses=np.r_[material,np.full(len(model['assumed_closures']),15.)]
        self.schemes=[]
        for high in combinations(range(8),2):
            rest=[i for i in range(8) if i not in high]
            for middle in combinations(rest,2):
                labels=['quartet']*8
                for i in high:labels[i]='direct'
                for i in middle:labels[i]='pair'
                self.schemes.append(labels)

    def path_loss(self,index,hub,root,kind):
        trunk=routed(self.head,root)[0];drop=routed(hub,self.position(index))[0]
        feed=routed(root,hub)[0] if kind!='direct' else None
        lengths=[(trunk,'7/8'),(drop,'7/8' if drop>15 else '1/2')]
        if feed is not None:lengths.append((feed,'7/8'))
        extra=sum(.2 if length<1e-6 else length*(6.39 if cable=='7/8' else 12.386666666666667)/100
                  for length,cable in lengths)
        adjustment={'direct':-10*math.log10(2)-.5,'pair':0,'quartet':10*math.log10(2)}[kind]
        return FIXED+adjustment+extra

    def position(self,i):return (self.ants[i]['x'],self.ants[i]['y'])

    def group_hub(self,ids,root):
        points=[self.position(i) for i in ids]
        possible=[root]+[min((projection(p,V[a],V[b]) for a,b in EDGES),key=lambda v:v[2])[0] for p in points]
        return min(possible,key=lambda h:routed(root,h)[0]+sum(routed(h,p)[0] for p in points))

    def exact_losses(self,ids,labels,root):
        result=np.zeros(8)
        for kind in ('direct','pair','quartet'):
            slots=[i for i,k in enumerate(labels) if k==kind]
            hub=root if kind=='direct' else self.group_hub([ids[i] for i in slots],root)
            for slot in slots:result[slot]=self.path_loss(ids[slot],hub,root,kind)
        return result

    def all_losses(self,ids,root):
        direct=np.array([self.path_loss(i,root,root,'direct') for i in ids])
        group={}
        for size,kind in ((2,'pair'),(4,'quartet')):
            for slots in combinations(range(8),size):
                hub=self.group_hub([ids[i] for i in slots],root)
                group[slots]=[self.path_loss(ids[i],hub,root,kind) for i in slots]
        matrix=np.tile(direct,(len(self.schemes),1))
        for j,labels in enumerate(self.schemes):
            for kind in ('pair','quartet'):
                slots=tuple(i for i,k in enumerate(labels) if k==kind)
                matrix[j,list(slots)]=group[slots]
        return matrix

    def others(self,z):
        ids=[q for q in range(1,5) if q!=z]
        return tuple(np.maximum.reduce([(getattr(self,key)[self.ids[q]]-self.loss[q][:,None]).max(axis=0)
                                         for q in ids]) for key in ('n3','joint'))

    def metric(self,a,b):
        cover_a=float(self.w[a>-90].sum());cover_b=float(self.w[b>-90].sum())
        deficit=float(np.dot(self.w,np.clip(np.minimum(a,b)+90,-20,0)))
        return min(cover_a,cover_b),cover_a+cover_b,deficit

    def optimize(self,z,ids,root):
        other_a,other_b=self.others(z);loss=self.all_losses(ids,root);winner=None
        for first in range(0,len(loss),24):
            chunk=loss[first:first+24]
            a=np.maximum((self.n3[ids][None,:,:]-chunk[:,:,None]).max(axis=1),other_a)
            b=np.maximum((self.joint[ids][None,:,:]-chunk[:,:,None]).max(axis=1),other_b)
            ca=(a>-90)@self.w;cb=(b>-90)@self.w
            deficit=np.clip(np.minimum(a,b)+90,-20,0)@self.w
            k=max(range(len(chunk)),key=lambda i:(min(ca[i],cb[i]),ca[i]+cb[i],deficit[i]))
            candidate=(float(min(ca[k],cb[k])),float(ca[k]+cb[k]),float(deficit[k]),first+k)
            if winner is None or candidate[:3]>winner[:3]:winner=candidate
        return winner,loss[winner[3]]

    def snapshot(self,label):
        a=np.maximum.reduce([(self.n3[self.ids[z]]-self.loss[z][:,None]).max(0) for z in range(1,5)])
        b=np.maximum.reduce([(self.joint[self.ids[z]]-self.loss[z][:,None]).max(0) for z in range(1,5)])
        row=dict(stage=label,n3_b7=score(a,self.w),joint_reserve3_b7=score(b,self.w),
                 roots=self.hubs,rooms={str(z):[self.ants[i]['room'] for i in self.ids[z]] for z in range(1,5)})
        self.history.append(row);write('search-history.json',self.history);print(json.dumps(row,ensure_ascii=False),flush=True)
        project=self.project();write('screening-project-input.json',project)
        routed_design=route_design.construct(project)
        for z in range(1,5):
            for k,i in enumerate(self.ids[z]):
                antenna=next(a for a in project['antennas'] if a['baseline_id']==self.ants[i]['baseline_id'])
                actual=next(r['total_loss_db'] for r in routed_design['rf_points']
                            if r['antenna']==antenna['id'] and r['frequency_mhz']==2600)
                assert math.isclose(actual,float(self.loss[z][k]),abs_tol=1e-8)
        write('screening-candidate.json',routed_design)
        return row

    def project(self):
        current_ids={a['baseline_id']:a['id'] for a in self.selected['antennas']}
        used={current_ids[self.ants[i]['baseline_id']] for z in self.ids for i in self.ids[z]
              if self.ants[i]['baseline_id'] in current_ids}
        unused=[a['id'] for a in self.selected['antennas'] if a['id'] not in used]
        ants=[];classes={}
        for z in range(1,5):
            for k,i in enumerate(self.ids[z]):
                source=self.ants[i];id=current_ids.get(source['baseline_id'])
                if id is None:id=unused.pop(0)
                a={key:source[key] for key in ('baseline_id','room','x','y')}
                a.update(id=id,zone=z,basis='Исследовательская позиция n=3; монтажная доступность не подтверждена')
                ants.append(a);classes[id]=self.classes[z][k]
        assert len({a['baseline_id'] for a in ants})==32
        return dict(head=list(self.head),head_label='Проектная ВК в части 104.2 — без изменения',
                    zone_hubs=self.hubs,zone_modes={str(z):'unequal' for z in range(1,5)},
                    power_classes=classes,antennas=ants)

    def placement_valid(self,i,point):
        group=next(g for g in self.model['groups'] if self.ants[i]['room'] in g['rooms'])
        if not shape(group['geometry']).covers(Point(point)):return False
        if self.tree.query(Point(point).buffer(.15),predicate='intersects').size:return False
        if any(np.linalg.norm(point-np.array(c['center']))<c['radius_m']+.2 for c in self.model['columns']):return False
        return True

    def sweep(self,number,cross_zone=False):
        for z in range(1,5):
            ids=self.ids[z];root=self.hubs[z-1];best,loss=self.optimize(z,ids,root)
            best_ids=ids[:];best_root=root
            # Candidate roots lie on the proposed tray graph; no extra devices.
            roots=[root,ZONES[z-1]]+[min((projection(self.position(i),V[a],V[b])
                   for a,b in EDGES),key=lambda v:v[2])[0] for i in ids]
            for trial_root in dict.fromkeys(tuple(p) for p in roots):
                result,values=self.optimize(z,ids,trial_root)
                if result[:3]>best[:3]:best,loss,best_root=result,values,trial_root
            occupied={i for q in self.ids if q!=z for i in self.ids[q]}
            available=[i for i,a in enumerate(self.ants) if i not in occupied and i not in ids
                       and (cross_zone or a['native_zone']==z)
                       and shape(next(g['geometry'] for g in self.model['groups'] if a['room'] in g['rooms'])).covers(Point(self.position(i)))]
            for slot in range(8):
                for add in available:
                    trial=ids[:];trial[slot]=add
                    result,values=self.optimize(z,trial,best_root)
                    if result[:3]>best[:3]:best,loss,best_ids=result,values,trial
            self.ids[z]=best_ids;self.hubs[z-1]=best_root
            self.classes[z]=self.schemes[best[3]][:];self.loss[z]=loss
            self.snapshot(f'sweep{number}_zone{z}'+('_global' if cross_zone else ''))

    def relocate(self):
        moves=[]
        for z in range(1,5):
            for slot,index in enumerate(self.ids[z]):
                a=self.ants[index];origin=np.array(self.position(index))
                group=next(g for g in self.model['groups'] if a['room'] in g['rooms']);poly=shape(group['geometry'])
                centre=polylabel(poly,tolerance=.1)
                proposals=[origin+np.array(delta) for delta in [(dx,dy) for dx in (-3,0,3) for dy in (-3,0,3)]]
                proposals.append(np.array([centre.x,centre.y]))
                other_a,other_b=self.others(z)
                other_slots=[k for k in range(8) if k!=slot]
                other_a=np.maximum(other_a,(self.n3[np.array(self.ids[z])[other_slots]]-self.loss[z][other_slots,None]).max(0))
                other_b=np.maximum(other_b,(self.joint[np.array(self.ids[z])[other_slots]]-self.loss[z][other_slots,None]).max(0))
                best=self.metric(np.maximum(other_a,self.n3[index]-self.loss[z][slot]),
                                 np.maximum(other_b,self.joint[index]-self.loss[z][slot]))
                winner=None
                for point in proposals:
                    if np.linalg.norm(point-origin)<.01 or not self.placement_valid(index,point):continue
                    peers=[self.position(i) for q in self.ids for i in self.ids[q] if i!=index]
                    if min(math.dist(point,p) for p in peers)<1:continue
                    a.update(x=float(point[0]),y=float(point[1]))
                    losses=self.exact_losses(self.ids[z],self.classes[z],self.hubs[z-1])
                    radius=np.sqrt(((self.xy-point)**2).sum(1)+5.5**2)
                    walls=crossings_many(point,self.xy,self.segments,self.tree,self.material)
                    full=crossings_many(point,self.xy,self.full,self.full_tree,self.full_losses)
                    columns=column_losses(point,self.xy,self.model['columns'])
                    n3=6-(20*math.log10(2600)-27.55)-30*np.log10(radius)-walls-columns
                    joint=6-(20*math.log10(2600)-27.55)-25*np.log10(radius)-full-columns-3
                    joint[self.mask_uncertain]=-np.inf
                    # Moving an antenna can move its shared subgroup hub. Re-evaluate all affected paths.
                    va=self.n3[self.ids[z]].copy();vb=self.joint[self.ids[z]].copy()
                    va[slot]=n3;vb[slot]=joint
                    outside_a,outside_b=self.others(z)
                    value=self.metric(np.maximum(outside_a,(va-losses[:,None]).max(0)),
                                      np.maximum(outside_b,(vb-losses[:,None]).max(0)))
                    if value>best:best=value;winner=(point.copy(),n3,joint,losses)
                a.update(x=float(origin[0]),y=float(origin[1]))
                if winner:
                    point,n3,joint,losses=winner;a.update(x=float(point[0]),y=float(point[1]))
                    self.n3[index]=n3;self.joint[index]=joint;self.loss[z]=losses
                    moves.append(dict(source=a['baseline_id'],room=a['room'],before=origin.tolist(),after=point.tolist()))
                    print('MOVE',a['room'],point.tolist(),flush=True)
            result,loss=self.optimize(z,self.ids[z],self.hubs[z-1])
            self.classes[z]=self.schemes[result[3]][:];self.loss[z]=loss
            self.snapshot(f'relocate_zone{z}')
        write('moves.json',moves)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--step',type=float,default=.5)
    parser.add_argument('--passes',type=int,default=2);parser.add_argument('--global-swap',action='store_true')
    parser.add_argument('--diagnose-only',action='store_true');args=parser.parse_args()
    OUT.mkdir(exist_ok=True,parents=True);CACHE.mkdir(exist_ok=True,parents=True)
    model=json.loads((ROOT/'design/final/coverage/area-model.json').read_text())
    selected=json.loads((ROOT/'design/final/candidate.json').read_text())
    (OUT/'baseline-candidate.json').write_bytes((ROOT/'design/final/candidate.json').read_bytes())
    (OUT/'baseline-project-input.json').write_bytes((ROOT/'design/final/project-input.json').read_bytes())
    for step in (.25,.5):
        source=ROOT/f'design/final/coverage/propagation-{step:g}.npz'
        dest=CACHE/'baseline'/source.name;dest.parent.mkdir(exist_ok=True)
        if source.exists() and not dest.exists():shutil.copyfile(source,dest)
    results,prop,maps=evaluate(model,selected,.25,CACHE/'baseline')
    write('baseline-results.json',results)
    if args.diagnose_only:return
    search=Search(model,selected,args.step);search.snapshot('baseline')
    for sweep in range(args.passes):search.sweep(sweep+1)
    search.relocate()
    if args.global_swap:search.sweep(args.passes+1,cross_zone=True);search.relocate()
    write('best32-project-input.json',search.project())
    write('best32-candidate.json',route_design.construct(search.project()))
    print('Research candidate saved separately. Fine-grid verification remains required.',flush=True)


if __name__=='__main__':main()
