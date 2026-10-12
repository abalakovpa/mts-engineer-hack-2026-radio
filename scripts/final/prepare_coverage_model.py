#!/usr/bin/env python3
"""Derive an explicit, reviewable area/obstacle model from preserved CAD."""
from collections import defaultdict
from pathlib import Path
import csv
import json
import math

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from shapely import set_precision
from shapely.geometry import LineString, Point, mapping
from shapely.ops import polygonize, unary_union

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'design/final/coverage'

def close_gaps(segments):
    groups=defaultdict(list)
    for a,b in segments:
        if abs(a[1]-b[1])<.001 and abs(a[0]-b[0])>.05:
            groups[('h',round(a[1],2))].append(sorted((a[0],b[0])))
        if abs(a[0]-b[0])<.001 and abs(a[1]-b[1])>.05:
            groups[('v',round(a[0],2))].append(sorted((a[1],b[1])))
    result=[]
    for (axis,c),intervals in groups.items():
        intervals.sort();end=intervals[0][1]
        for lo,hi in intervals[1:]:
            if .4<lo-end<2.2:
                result.append([(end,c),(lo,c)] if axis=='h' else [(c,end),(c,lo)])
            end=max(end,hi)
    return result

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    raw=json.loads((ROOT/'design/final/cad-geometry.json').read_text())
    rooms=list(csv.DictReader((ROOT/'design/final/room-schedule.csv').open()))
    segments=[e['points'] for e in raw['lines']
              if e['layer'] not in {'S-COLS','E-CABL-TRAY-CNTR'}
              and all(-2<p[0]<39 and -2<p[1]<66 for p in e['points'])]
    closures=close_gaps(segments)
    faces=list(polygonize(unary_union([set_precision(LineString(s),.01) for s in segments+closures])))
    selected={};unlocated=[]
    for room in rooms:
        if not room['label_x_m']:
            unlocated.append(room);continue
        p=Point(float(room['label_x_m']),float(room['label_y_m']))
        candidates=[(i,g) for i,g in enumerate(faces) if g.covers(p)]
        if not candidates:
            unlocated.append(room);continue
        i,poly=min(candidates,key=lambda pair:pair[1].area)
        selected.setdefault(i,[]).append(room)
    groups=[]
    for j,(i,members) in enumerate(sorted(selected.items())):
        poly=faces[i];ref=sum(float(r['area_m2']) for r in members)
        groups.append(dict(id=f'G{j+1:02d}',rooms=[r['room'] for r in members],
                           reference_area_m2=ref,model_area_m2=poly.area,
                           relative_area_difference=(poly.area/ref-1),geometry=mapping(poly)))
    mask=unary_union([faces[i] for i in selected])
    # Full circular shapes at structural-grid locations; inferred reinforced
    # concrete material from organizer PNG is a stated modeling assumption.
    arc_groups=defaultdict(list)
    for c in raw['circles']:
        if c['layer']=='A-FLOR' and abs(c['radius']-.3)<.001:
            arc_groups[tuple(round(v,4) for v in c['center'])].append(c)
    columns=[]
    for centre,arcs in arc_groups.items():
        if sum(c['end']-c['start'] for c in arcs)>5.5:
            columns.append(dict(center=centre,radius_m=.3,loss_db=30,
                                basis='Круглая CAD-конструкция A-FLOR; ЖБ/30дБ — классификационное допущение'))
    wall_layers={'A-WALL','I-WALL','A-PART','A-GLAZ-CWMG','A-GLAZ-CURT','A-GLAZ'}
    walls=[dict(points=e['points'],layer=e['layer'],source_handle=e['handle'])
           for e in raw['lines'] if e['layer'] in wall_layers
           and all(-2<p[0]<39 and -2<p[1]<66 for p in e['points'])
           and math.dist(*e['points'])>.02]
    metadata=dict(precision_m=.01,gap_closure_min_m=.4,gap_closure_max_m=2.2,
                  gap_closure_count=len(closures),mask_area_m2=mask.area,
                  reference_total_m2=sum(float(r['area_m2']) for r in rooms),
                  located_reference_m2=sum(g['reference_area_m2'] for g in groups),
                  unlocated_reference_m2=sum(float(r['area_m2']) for r in unlocated),
                  full_floor_confirmed=False,material_classification_confirmed=False,
                  ray_crossing_merge_m=.35,wall_loss_db=15,column_loss_db=30)
    print('groups',len(groups),'unlocated',[r['room'] for r in unlocated],'area',mask.area)
    assert len(unlocated)==1 and unlocated[0]['room']=='89'
    assert abs(metadata['reference_total_m2']-2097.08)<.001
    model=dict(metadata=metadata,groups=groups,mask=mapping(mask),walls=walls,
               assumed_closures=closures,columns=columns,unlocated_rooms=unlocated)
    (OUT/'area-model.json').write_text(json.dumps(model,ensure_ascii=False,separators=(',',':'))+'\n')
    features=[dict(type='Feature',geometry=g['geometry'],properties={k:v for k,v in g.items() if k!='geometry'}) for g in groups]
    (OUT/'rooms.geojson').write_text(json.dumps(dict(type='FeatureCollection',features=features),ensure_ascii=False,indent=2)+'\n')
    with (OUT/'area-audit.csv').open('w',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['group','rooms','reference_m2','model_m2','difference_percent'])
        for g in groups:w.writerow([g['id'],'+'.join(g['rooms']),g['reference_area_m2'],g['model_area_m2'],100*g['relative_area_difference']])
    fig,ax=plt.subplots(figsize=(10,16))
    for i,g in enumerate(groups):
        poly=faces[list(sorted(selected))[i]]
        coords=list(poly.exterior.coords)
        ax.fill(*zip(*coords),alpha=.3,color=plt.get_cmap('tab20')(i%20))
        for hole in poly.interiors:ax.fill(*zip(*hole.coords),color='white')
        pos=poly.representative_point();ax.text(pos.x,pos.y,'+'.join(g['rooms']),fontsize=5)
    ax.add_collection(LineCollection([e['points'] for e in walls],colors='#555555',linewidths=.35))
    ax.add_collection(LineCollection(closures,colors='#bc2745',linewidths=.6))
    for c in columns:ax.add_patch(plt.Circle(c['center'],c['radius_m'],color='#111111'))
    ax.set_xlim(-2,39);ax.set_ylim(-2,66);ax.set_aspect('equal')
    ax.set_xlabel('CAD X, м');ax.set_ylabel('CAD Y, м')
    ax.set_title(f'Модель площади: {len(groups)} групп, {len(rooms)-len(unlocated)} локализованных помещений\nКрасный: условное закрытие проёмов; помещение 89 не установлено',fontsize=10)
    fig.savefig(OUT/'area-model.png',dpi=180,bbox_inches='tight');plt.close(fig)
    print(json.dumps(metadata,ensure_ascii=False,indent=2));print('columns',len(columns),'wall_segments',len(walls))

if __name__=='__main__':main()
