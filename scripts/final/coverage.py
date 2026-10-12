#!/usr/bin/env python3
"""Evaluate CAD-derived RSRP scenarios and screen realizable antenna counts.

Unknown materials/door states, CRS normalization and area boundaries remain
explicit assumptions. Percentages are predictions of this model, not surveys.
"""
from collections import defaultdict
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
from shapely.geometry import Point, LineString, MultiPoint, box, shape
from shapely import STRtree

from build_project import route, ZONES, V

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'design/final/coverage'

def compact_walls(walls):
    bins=defaultdict(list);other=[]
    for e in walls:
        a,b=e['points']
        if abs(a[1]-b[1])<.001:
            bins[('h',round(a[1]/.02)*.02)].append(sorted((a[0],b[0])))
        elif abs(a[0]-b[0])<.001:
            bins[('v',round(a[0]/.02)*.02)].append(sorted((a[1],b[1])))
        else:other.append(e['points'])
    result=other[:]
    for (axis,c),intervals in bins.items():
        intervals.sort();lo,hi=intervals[0]
        merged=[]
        for a,b in intervals[1:]:
            if a-hi<=.025:hi=max(hi,b)
            else:merged.append((lo,hi));lo,hi=a,b
        merged.append((lo,hi))
        for a,b in merged:result.append([(a,c),(b,c)] if axis=='h' else [(c,a),(c,b)])
    return np.array(result,float)

def crossings(origin,target,segments,tree,losses,merge=.35):
    if np.linalg.norm(target-origin)<1e-10:return 0.0
    indexes=tree.query(LineString((origin,target)),predicate='intersects')
    if not len(indexes):return 0.0
    seg=segments[indexes];v=seg[:,1]-seg[:,0];u=target-origin;w=seg[:,0]-origin
    den=u[0]*v[:,1]-u[1]*v[:,0]
    ok=np.abs(den)>1e-9
    t=np.divide(w[:,0]*v[:,1]-w[:,1]*v[:,0],den,out=np.zeros_like(den),where=ok)
    q=np.divide(w[:,0]*u[1]-w[:,1]*u[0],den,out=np.zeros_like(den),where=ok)
    ok&=(t>1e-6)&(t<1-1e-6)&(q>=-1e-6)&(q<=1+1e-6)
    values=sorted(zip(t[ok]*np.linalg.norm(u),losses[indexes][ok]))
    result=0.;last=None;current=0.
    for d,loss in values:
        if last is not None and d-last>merge:result+=current;current=0.
        current=max(current,float(loss));last=d
    return result+current

def column_loss(origin,target,columns):
    u=target-origin;norm=np.dot(u,u)
    if norm<1e-12:return 0.
    result=0.
    for c in columns:
        centre=np.array(c['center']);t=np.clip(np.dot(centre-origin,u)/norm,0,1)
        if np.linalg.norm(centre-(origin+t*u))<c['radius_m']-1e-6:result+=30
    return result

def test_crossings():
    segments=np.array([[(1,-2),(1,2)],[(1.2,-2),(1.2,2)],[(3,-2),(3,2)]],float)
    tree=STRtree([LineString(s) for s in segments]);losses=np.full(3,15.)
    assert crossings(np.array([0.,0.]),np.array([4.,0.]),segments,tree,losses)==30
    assert crossings(np.array([0.,0.]),np.array([.5,0.]),segments,tree,losses)==0
    assert crossings(np.array([0.,0.]),np.array([4.,4.]),segments,tree,losses)==15
    assert column_loss(np.array([0.,0.]),np.array([4.,0.]),[dict(center=[2,0],radius_m=.3)])==30
    assert column_loss(np.array([0.,1.]),np.array([4.,1.]),[dict(center=[2,0],radius_m=.3)])==0

def samples(model,step):
    points=[];weights=[];gid=[];areas=[]
    for i,g in enumerate(model['groups']):
        poly=shape(g['geometry'])
        for c in model['columns']:poly=poly.difference(Point(c['center']).buffer(c['radius_m'],quad_segs=16))
        x0,y0,x1,y1=poly.bounds;total=0.
        for x in np.arange(math.floor(x0/step)*step,x1,step):
            for y in np.arange(math.floor(y0/step)*step,y1,step):
                piece=poly.intersection(box(x,y,x+step,y+step))
                if piece.area<1e-8:continue
                p=Point(x+step/2,y+step/2)
                if not piece.covers(p):p=piece.representative_point()
                points.append((p.x,p.y));areas.append(piece.area);gid.append(i)
                weights.append(piece.area/poly.area*g['reference_area_m2']);total+=piece.area
        assert abs(total-poly.area)<1e-5
    assert abs(sum(weights)-model['metadata']['located_reference_m2'])<1e-5
    return np.array(points),np.array(weights),np.array(gid),np.array(areas)

def fields(model,ants,step):
    test_crossings()
    coordinates=np.array([(a['x'],a['y']) for a in ants])
    geometry_fingerprint=hashlib.sha256(json.dumps([model,step,'ray-v2'],sort_keys=True).encode()).hexdigest()
    fingerprint=hashlib.sha256(json.dumps([model,[(a['x'],a['y']) for a in ants],step,'ray-v2'],sort_keys=True).encode()).hexdigest()
    cache=OUT/f'propagation-{step:g}.npz'
    if cache.exists():
        with np.load(cache) as stored:
            existing={k:stored[k] for k in stored.files}
        if str(existing['fingerprint'])==fingerprint:
            result=dict(existing)
            if 'coordinates' not in result:
                result.update(coordinates=coordinates,geometry_fingerprint=np.array(geometry_fingerprint))
                np.savez_compressed(cache,**result)
            return result
    points,weights,gid,areas=samples(model,step)
    segments=compact_walls(model['walls']);lines=[LineString(s) for s in segments];tree=STRtree(lines)
    hull=MultiPoint(segments.reshape(-1,2)).convex_hull
    losses=np.array([30 if hull.boundary.distance(LineString(s).interpolate(.5,normalized=True))<.45 else 15 for s in segments])
    closures=np.array(model['assumed_closures'])
    fullsegments=np.concatenate((segments,closures),axis=0)
    ctree=STRtree([LineString(s) for s in fullsegments])
    closses=np.concatenate((losses,np.full(len(closures),15.)))
    wall=np.zeros((len(ants),len(points)),np.float32);closed=np.zeros_like(wall);cols=np.zeros_like(wall);radius=np.zeros_like(wall)
    for j,a in enumerate(ants):
        if cache.exists() and 'geometry_fingerprint' in existing and str(existing['geometry_fingerprint'])==geometry_fingerprint:
            delta=np.linalg.norm(existing['coordinates']-coordinates[j],axis=1)
            index=int(delta.argmin())
            if delta[index]<1e-8:
                for new,key in ((radius,'radius'),(wall,'wall'),(closed,'closed'),(cols,'columns')):
                    new[j]=existing[key][index]
                continue
        origin=np.array((a['x'],a['y']));radius[j]=np.sqrt(((points-origin)**2).sum(axis=1)+5.5**2)
        for k,target in enumerate(points):
            wall[j,k]=crossings(origin,target,segments,tree,losses)
            # Re-cluster all crossings jointly, so a closed gap cannot count
            # the same physical partition twice with its existing faces.
            closed[j,k]=max(0,crossings(origin,target,fullsegments,ctree,closses)-wall[j,k])
            cols[j,k]=column_loss(origin,target,model['columns'])
        if j%6==5:print(f'CAD propagation: {j+1}/{len(ants)} antennas, {len(points)} receiver cells',flush=True)
    result=dict(fingerprint=np.array(fingerprint),geometry_fingerprint=np.array(geometry_fingerprint),coordinates=coordinates,
                points=points,weights=weights,gid=gid,areas=areas,
                wall=wall,closed=closed,columns=cols,radius=radius)
    np.savez_compressed(cache,**result)
    return result

def score(values,weights):return float(weights[values>-90].sum()/2100*100)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--step',type=float,default=1)
    args=parser.parse_args()
    model=json.loads((OUT/'area-model.json').read_text())
    baseline_file=OUT/'baseline-candidate.json'
    if not baseline_file.exists():baseline_file.write_bytes((ROOT/'design/final/candidate.json').read_bytes())
    candidate=json.loads(baseline_file.read_text());ants=candidate['antennas']
    field=fields(model,ants,args.step);weights=field['weights'];radius=field['radius']
    # Three source locations are project alternatives; existing room functions
    # are preserved and no location is claimed to be an existing ВК.
    heads={'H118':V[0],'H104.2':(9.2,31.2),'H137':(.7,32.0)}
    results=[];all_choices=[]
    for name,head in heads.items():
        trunk_new=[route(head,z)[0] for z in ZONES]
        power=[]
        for a in ants:
            old=next(r['total_loss_db'] for r in candidate['rf_points'] if r['antenna']==a['id'] and r['frequency_mhz']==2600)
            delta=(trunk_new[a['zone']-1]-candidate['trunks'][a['zone']-1]['length'])*6.39/100
            power.append(3-(old+delta)+3)
        radio=np.array(power)[:,None]-(20*np.log10(2600)-27.55+25*np.log10(radius))-field['wall']-field['columns']
        for count in (48,32,24,16):
            gain=10*math.log10(48/count)+(.5 if count==16 else 0)
            chosen=list(range(48));quota=count//4
            # Balanced backward deletion; retain a realizable equal-output tree.
            while len(chosen)>count:
                removable=[i for i in chosen if sum(ants[j]['zone']==ants[i]['zone'] for j in chosen)>quota]
                utility=[]
                for i in removable:
                    trial=[j for j in chosen if j!=i]
                    values=radio[trial].max(axis=0)+gain
                    utility.append((score(values,weights),-float(np.maximum(values+90,0).dot(weights)),i))
                # Coverage first, continuous RF margin as tie-breaker.
                remove=max(utility,key=lambda t:(t[0],-t[1],-t[2]))[2]
                chosen.remove(remove)
            vals=radio[chosen].max(axis=0)+gain
            result=dict(head=name,head_xy=head,antennas=count,step_m=args.step,
                        coverage_reference_percent=score(vals,weights),
                        coverage_model_percent=float(field['areas'][vals>-90].sum()/field['areas'].sum()*100),
                        selected_ids=[ants[i]['id'] for i in chosen],
                        nominal_only=True,cable_routes_rebuilt=False)
            results.append(result)
            all_choices.append((result,chosen,vals))
    feasible=[choice for choice in all_choices if choice[0]['coverage_reference_percent']>=95]
    if feasible:
        recommend,best_selection,best_fields=min(feasible,key=lambda choice:(choice[0]['antennas'],-choice[0]['coverage_reference_percent']))
    else:
        recommend,best_selection,best_fields=max(all_choices,key=lambda choice:choice[0]['coverage_reference_percent'])
    (OUT/f'options-{args.step:g}.json').write_text(json.dumps(dict(options=results,screening_best=recommend),ensure_ascii=False,indent=2)+'\n')
    # Save selected points as an explicit proposal; full tree must be rebuilt.
    (OUT/'screening-selection.json').write_text(json.dumps(dict(head=recommend['head_xy'],head_label=recommend['head'],
        requested_count=len(best_selection),antennas=[ants[i] for i in best_selection],
        screening_only=True,baseline_source='baseline-candidate.json'),ensure_ascii=False,indent=2)+'\n')
    fig,ax=plt.subplots(figsize=(9,14))
    chart=ax.scatter(field['points'][:,0],field['points'][:,1],c=best_fields,s=8,cmap='RdYlGn',vmin=-110,vmax=-75,marker='s')
    for g in model['groups']:
        poly=shape(g['geometry']);ax.plot(*poly.exterior.xy,color='#333333',lw=.4)
    for i in best_selection:ax.plot(ants[i]['x'],ants[i]['y'],'k.',ms=3)
    ax.set_aspect('equal');ax.set_xlim(-2,39);ax.set_ylim(-2,66)
    ax.set_title(f'Скрининг B7, P1, n=2,5: {recommend["head"]}, {len(best_selection)} антенн\nСтены 15 / колонны 30 дБ; неизвестная площадь считается непокрытой',fontsize=10)
    fig.colorbar(chart,ax=ax,label='RSRP, дБм');fig.savefig(OUT/f'screening-map-{args.step:g}.png',dpi=170,bbox_inches='tight');plt.close(fig)
    for r in results:print(r['head'],r['antennas'],round(r['coverage_reference_percent'],2),flush=True)
    print('BEST SCREENING',recommend,flush=True)

if __name__=='__main__':main()
