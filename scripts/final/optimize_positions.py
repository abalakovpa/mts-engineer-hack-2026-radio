#!/usr/bin/env python3
"""Local ceiling-position search in weak CAD groups; adoption needs full rerun."""
from pathlib import Path
import json
import math
import numpy as np
from shapely import STRtree
from shapely.geometry import shape,Point,LineString,MultiPoint
from shapely.ops import polylabel
from coverage import compact_walls,crossings,column_loss
from build_project import route

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'design/final/coverage'

def main():
    model=json.loads((OUT/'area-model.json').read_text())
    cand=json.loads((ROOT/'design/final/candidate.json').read_text())
    baseline=json.loads((OUT/'baseline-candidate.json').read_text())
    inp=json.loads((ROOT/'design/final/project-input.json').read_text())
    cache=np.load(OUT/'propagation-0.5.npz');xy=cache['points'];w=cache['weights'];gid=cache['gid']
    by_xy={(round(a['x'],8),round(a['y'],8)):i for i,a in enumerate(baseline['antennas'])}
    indexes=[by_xy[(round(a['x'],8),round(a['y'],8))] for a in cand['antennas']]
    loss=np.array([next(r['total_loss_db'] for r in cand['rf_points'] if r['antenna']==a['id'] and r['frequency_mhz']==2600) for a in cand['antennas']])
    radio=(6-loss[:,None]-(20*math.log10(2600)-27.55+25*np.log10(cache['radius'][indexes]))-cache['wall'][indexes]-cache['columns'][indexes])
    seg=compact_walls(model['walls']);tree=STRtree([LineString(s) for s in seg]);hull=MultiPoint(seg.reshape(-1,2)).convex_hull
    losses=np.array([30 if hull.boundary.distance(LineString(s).interpolate(.5,normalized=True))<.45 else 15 for s in seg])
    proposals=[]
    for group_index,g in enumerate(model['groups']):
        region=gid==group_index;best=radio.max(axis=0)
        if w[region&(best>-90)].sum()/g['reference_area_m2']>=.95:continue
        poly=shape(g['geometry']);x0,y0,x1,y1=poly.bounds
        local=(xy[:,0]>x0-3)&(xy[:,0]<x1+3)&(xy[:,1]>y0-3)&(xy[:,1]<y1+3)
        receivers=xy[local];weights=w[local]
        for j,a in enumerate(cand['antennas']):
            if a['room'] not in g['rooms']:continue
            origin=np.array([a['x'],a['y']]);other=np.delete(radio[:,local],j,axis=0).max(axis=0)
            current_score=float(weights[np.maximum(other,radio[j,local])>-90].sum())
            points=[origin+np.array((dx,dy)) for dx in (-1.5,0,1.5) for dy in (-1.5,0,1.5)]
            centre=polylabel(poly,tolerance=.05)
            if math.dist(origin,(centre.x,centre.y))<3:points.append(np.array((centre.x,centre.y)))
            best_score=current_score;winner=None;winner_values=None
            drop=next(t for t in cand['drops'] if t['id']==a['id'])
            old_drop=drop['length']*(6.39 if drop['cable']=='7/8' else 12.386666666666667)/100
            for p in points:
                if not poly.covers(Point(p)) or np.linalg.norm(p-origin)<.01:continue
                # Stay in the local region closest to the original room seed.
                peer=[b for b in cand['antennas'] if b['room'] in g['rooms'] and b['id']!=a['id']]
                if peer and any(math.dist(p,(b['x'],b['y']))<np.linalg.norm(p-origin) for b in peer):continue
                if any(math.dist(p,c['center'])<c['radius_m']+.2 for c in model['columns']):continue
                near=tree.query(Point(p).buffer(.15),predicate='intersects')
                if len(near):continue
                new_length=route(tuple(a['hub']),tuple(p))[0]
                new_loss=loss[j]-old_drop+new_length*(6.39 if new_length>15 else 12.386666666666667)/100
                vals=[]
                for target in receivers:
                    r=math.sqrt(float(((target-p)**2).sum())+5.5**2)
                    wall=crossings(p,target,seg,tree,losses)+column_loss(p,target,model['columns'])
                    vals.append(6-new_loss-(20*math.log10(2600)-27.55+25*math.log10(r))-wall)
                vals=np.array(vals);s=float(weights[np.maximum(other,vals)>-90].sum())
                if s>best_score+.1:best_score=s;winner=p;winner_values=vals
            if winner is not None:
                proposals.append(dict(id=a['id'],baseline_id=a.get('baseline_id'),room=a['room'],
                    before=origin.tolist(),after=winner.tolist(),local_gain_reference_m2=best_score-current_score,
                    adopted=False,full_field_recheck_required=True))
                radio[j,local]=winner_values
                match=next(b for b in inp['antennas'] if b['baseline_id']==a['baseline_id'])
                match['x'],match['y']=map(float,winner)
                match['basis']='Проектная точка перемещена внутри CAD-группы по локальному расчёту; полный перерасчёт обязателен'
    (OUT/'position-proposal.json').write_text(json.dumps(dict(proposals=proposals,project_input=inp),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(proposals,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
