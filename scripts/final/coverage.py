#!/usr/bin/env python3
"""Compute propagation paths for the selected CAD-based design.

Unknown materials/door states, CRS normalization and area boundaries remain
explicit assumptions. Percentages are predictions of this model, not surveys.
"""
from collections import defaultdict
from pathlib import Path
import hashlib
import json
import math

import numpy as np
from shapely.geometry import Point, LineString, MultiPoint, box, shape
from shapely import STRtree, linestrings


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

def crossings_many(origin,targets,segments,tree,losses,merge=.35):
    """Batch ray query, retaining the scalar function's wall-face clustering."""
    result=np.zeros(len(targets));u=targets-origin
    rays=linestrings(np.stack((np.broadcast_to(origin,targets.shape),targets),axis=1))
    indexes=tree.query(rays,predicate='intersects')
    if not indexes.size:return result
    receiver,wall=indexes;seg=segments[wall];v=seg[:,1]-seg[:,0];w=seg[:,0]-origin;ray=u[receiver]
    den=ray[:,0]*v[:,1]-ray[:,1]*v[:,0];ok=np.abs(den)>1e-9
    t=np.divide(w[:,0]*v[:,1]-w[:,1]*v[:,0],den,out=np.zeros_like(den),where=ok)
    q=np.divide(w[:,0]*ray[:,1]-w[:,1]*ray[:,0],den,out=np.zeros_like(den),where=ok)
    ok&=(t>1e-6)&(t<1-1e-6)&(q>=-1e-6)&(q<=1+1e-6)
    receiver=receiver[ok];distance=t[ok]*np.linalg.norm(ray[ok],axis=1);loss=losses[wall[ok]]
    if not len(receiver):return result
    order=np.lexsort((distance,receiver));receiver=receiver[order];distance=distance[order];loss=loss[order]
    starts=np.r_[0,np.flatnonzero((receiver[1:]!=receiver[:-1])|((distance[1:]-distance[:-1])>merge))+1]
    np.add.at(result,receiver[starts],np.maximum.reduceat(loss,starts))
    return result

def column_losses(origin,targets,columns):
    """Same segment/circle predicate for all receivers without a Python loop."""
    u=targets-origin;norm=np.sum(u*u,axis=1);result=np.zeros(len(targets))
    for c in columns:
        centre=np.array(c['center'])
        t=np.clip(np.divide(u@(centre-origin),norm,out=np.zeros_like(norm),where=norm>=1e-12),0,1)
        separation=np.linalg.norm(centre-(origin+t[:,None]*u),axis=1)
        result+=np.where((norm>=1e-12)&(separation<c['radius_m']-1e-6),30.,0.)
    return result

def test_crossings():
    segments=np.array([[(1,-2),(1,2)],[(1.2,-2),(1.2,2)],[(3,-2),(3,2)]],float)
    tree=STRtree([LineString(s) for s in segments]);losses=np.full(3,15.)
    assert crossings(np.array([0.,0.]),np.array([4.,0.]),segments,tree,losses)==30
    assert crossings(np.array([0.,0.]),np.array([.5,0.]),segments,tree,losses)==0
    assert crossings(np.array([0.,0.]),np.array([4.,4.]),segments,tree,losses)==15
    assert column_loss(np.array([0.,0.]),np.array([4.,0.]),[dict(center=[2,0],radius_m=.3)])==30
    assert column_loss(np.array([0.,1.]),np.array([4.,1.]),[dict(center=[2,0],radius_m=.3)])==0
    receivers=np.array([[4,0],[.5,0],[4,4],[0,0],[4,-1],[1,2],[4,.5]],float)
    assert np.array_equal(crossings_many(np.array([0.,0.]),receivers,segments,tree,losses),
                          np.array([crossings(np.array([0.,0.]),p,segments,tree,losses) for p in receivers]))
    origin=np.array([0.,0.]);targets=np.array([[0,0],[4,0],[4,1],[1,0],[2,.3],[2,.3-1e-5]],float)
    columns=[dict(center=[2,0],radius_m=.3)]
    assert np.array_equal(column_losses(origin,targets,columns),np.array([column_loss(origin,p,columns) for p in targets]))

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

def fields(model,ants,step,cache_dir=None):
    test_crossings()
    coordinates=np.array([(a['x'],a['y']) for a in ants])
    geometry_fingerprint=hashlib.sha256(json.dumps([model,step,'ray-v2'],sort_keys=True).encode()).hexdigest()
    fingerprint=hashlib.sha256(json.dumps([model,[(a['x'],a['y']) for a in ants],step,'ray-v2'],sort_keys=True).encode()).hexdigest()
    folder=Path(cache_dir) if cache_dir is not None else OUT
    folder.mkdir(parents=True,exist_ok=True)
    cache=folder/f'propagation-{step:g}.npz'
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
        cols[j]=column_losses(origin,points,model['columns'])
        wall[j]=crossings_many(origin,points,segments,tree,losses)
        # Re-cluster jointly, so a closed gap cannot count a wall face twice.
        closed[j]=np.maximum(0,crossings_many(origin,points,fullsegments,ctree,closses)-wall[j])
        if j%6==5:print(f'CAD propagation: {j+1}/{len(ants)} antennas, {len(points)} receiver cells',flush=True)
    result=dict(fingerprint=np.array(fingerprint),geometry_fingerprint=np.array(geometry_fingerprint),coordinates=coordinates,
                points=points,weights=weights,gid=gid,areas=areas,
                wall=wall,closed=closed,columns=cols,radius=radius)
    np.savez_compressed(cache,**result)
    return result
