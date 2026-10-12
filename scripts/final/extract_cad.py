#!/usr/bin/env python3
"""Read LibreDWG JSON; preserve original DWG, export model-space geometry only."""
import argparse
import json
import csv
import math
from collections import Counter
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'design/final'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('json_file')
    args=parser.parse_args()
    with open(args.json_file,encoding='utf-8',errors='replace') as stream:
        data=json.load(stream)
    assert data['HEADER']['INSUNITS']==4, 'Expected millimetres; do not guess units'
    objects={o['handle'][-1]:o for o in data['OBJECTS']}
    assert len(objects)==len(data['OBJECTS']), 'Duplicate handles: invalid converter result'
    layers={h:o['name'] for h,o in objects.items() if o.get('object')=='LAYER'}
    blocks={h:o for h,o in objects.items() if o.get('object')=='BLOCK_HEADER'}
    model=next(h for h,b in blocks.items() if b['name']=='*Model_Space')
    lines=[]; texts=[]; polys=[]; circles=[]; counts=Counter(); unsupported=Counter()

    def pt(p,t):
        return (t @ np.array([p[0],p[1],1.0]))[:2].tolist()

    def walk(h,t,depth=0,inherited_layer='0'):
        if depth>20: raise ValueError('Cyclic/nested blocks exceed depth')
        b=blocks[h]
        for ref in b.get('entities',[]):
            o=objects.get(ref[-1])
            if not o: raise ValueError(f'Missing object {ref}')
            typ=o.get('entity'); counts[typ]+=1
            layer=layers.get(o.get('layer',[0])[-1],'?')
            if layer=='0':layer=inherited_layer
            handle=o['handle'][-1]
            if typ=='INSERT':
                target=o.get('block_header',[0])[-1]
                if target not in blocks: raise ValueError(f'Missing block {target}')
                x,y=o['ins_pt'][:2]; sx,sy=o['scale'][:2]; a=o['rotation']
                bx,by=blocks[target]['base_pt'][:2]
                c,s=math.cos(a),math.sin(a)
                m=np.array([[c*sx,-s*sy,x-c*sx*bx+s*sy*by],
                            [s*sx,c*sy,y-s*sx*bx-c*sy*by],[0,0,1]])
                walk(target,t@m,depth+1,layer)
            elif typ=='LINE':
                lines.append(dict(layer=layer,handle=handle,points=[pt(o['start'],t),pt(o['end'],t)]))
            elif typ=='LWPOLYLINE':
                points=[pt(p,t) for p in o['points']]
                closed=bool(o['flag']&512)
                polys.append(dict(layer=layer,handle=handle,points=points,closed=closed,
                                  bulges=o.get('bulges',[])))
                pairs=list(zip(points,points[1:]))
                if closed and points: pairs.append((points[-1],points[0]))
                for a,bp in pairs: lines.append(dict(layer=layer,handle=handle,points=[a,bp]))
            elif typ in ('CIRCLE','ARC'):
                centre=o['center']; radius=o['radius']
                lo=o.get('start_angle',0); hi=o.get('end_angle',2*math.pi)
                if hi<=lo: hi+=2*math.pi
                circles.append(dict(layer=layer,handle=handle,kind=typ,center=pt(centre,t),
                                    radius=radius*math.hypot(t[0,0],t[1,0]),start=lo,end=hi))
                points=[pt([centre[0]+radius*math.cos(a),centre[1]+radius*math.sin(a)],t)
                        for a in np.linspace(lo,hi,33)]
                for a,bp in zip(points,points[1:]):
                    lines.append(dict(layer=layer,handle=handle,points=[a,bp]))
            elif typ in ('TEXT','MTEXT','ATTRIB','ATTDEF'):
                s=o.get('text',o.get('text_value',''))
                texts.append(dict(layer=layer,handle=handle,position=pt(o.get('ins_pt',[0,0]),t),text=s))
            elif typ not in ('HATCH','BLOCK','ENDBLK'):
                unsupported[typ]+=1

    walk(model,np.eye(3))
    # Convert CAD millimetres to metres without area scaling.
    for line in lines:
        line['points']=[[x/1000,y/1000] for x,y in line['points']]
    for poly in polys:
        poly['points']=[[x/1000,y/1000] for x,y in poly['points']]
    for text in texts:
        text['position']=[v/1000 for v in text['position']]
    for circle in circles:
        circle['center']=[v/1000 for v in circle['center']];circle['radius']/=1000
    OUT.mkdir(parents=True,exist_ok=True)
    meta=dict(tool='LibreDWG 0.13.3 + bit_read_H fix from official 0.13.4',units='metres',original_insunits=4,
              expanded_counts=dict(counts),unsupported=dict(unsupported),
              arc_sampling_points=33,polyline_bulges_rendered_as_chords=True)
    retained={'A-WALL','I-WALL','A-PART','A-GLAZ-CURT','A-GLAZ-CWMG','A-GLAZ-CURT-HDLN',
              'A-DOOR-FRAM','A-AREA','A-FLOR','S-COLS','E-CABL-TRAY-CNTR','A-DOOR','A-GLAZ'}
    selected=[e for e in lines if e['layer'] in retained]
    for e in selected:
        e['points']=[[round(v,6) for v in p] for p in e['points']]
    meta['omitted_decorative_line_layers']=True
    (OUT/'cad-geometry.json').write_text(json.dumps(dict(metadata=meta,lines=selected,
        texts=texts,polylines=polys,circles=circles),ensure_ascii=False,separators=(',',':'))+'\n')
    paper=next(b for b in blocks.values() if b['name']=='*Paper_Space' and b.get('entities'))
    paper_text=[objects[ref[-1]] for ref in paper['entities']
                if objects[ref[-1]].get('entity') in ('TEXT','MTEXT')]
    rows=[]
    for e in paper_text:
        pos=e['ins_pt'];value=e.get('text',e.get('text_value',''))
        if 490<pos[0]<495 and 470<pos[1]<780:
            peers=[o for o in paper_text if abs(o['ins_pt'][1]-pos[1])<.05]
            name=next(o.get('text',o.get('text_value','')) for o in peers if 499<o['ins_pt'][0]<501)
            area=next(o.get('text',o.get('text_value','')) for o in peers if o['ins_pt'][0]>570)
            location=next((t['position'] for t in texts if t['layer']=='A-AREA-IDEN' and t['text']==value),None)
            rows.append(dict(room=value,name=name.replace('\\P',' '),area_m2=float(area.split()[0]),
                             label_x_m=location[0] if location else '',label_y_m=location[1] if location else ''))
    rows.sort(key=lambda r:float(r['room']))
    with (OUT/'room-schedule.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys(),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    assert abs(sum(r['area_m2'] for r in rows)-2097.06)<.05  # rounded room areas differ by 0.02
    fig,ax=plt.subplots(figsize=(13,17))
    architecture=[e['points'] for e in lines if not any(x in e['layer'] for x in ['ANNO','GRID','PATT','CABL'])]
    ax.add_collection(LineCollection(architecture,colors='#777777',linewidths=.35))
    trays=[e['points'] for e in lines if 'CABL' in e['layer'] and 'ANNO' not in e['layer']]
    ax.add_collection(LineCollection(trays,colors='#0780b8',linewidths=.7))
    for text in texts:
        if text['layer']=='A-AREA-IDEN':
            ax.text(*text['position'],text['text'],fontsize=5,color='#222222')
    ax.autoscale(); ax.set_xlim(-3,40);ax.set_ylim(-3,66); ax.set_aspect('equal'); ax.grid(alpha=.15)
    ax.set_xlabel('CAD X, м');ax.set_ylabel('CAD Y, м')
    ax.set_title('Подложка DWG: геометрия в метрах; лотки выделены синим')
    fig.savefig(OUT/'cad-floor.png',dpi=180,bbox_inches='tight')
    plt.close(fig)
    print(json.dumps(meta,ensure_ascii=False))
    print('layers',Counter(e['layer'] for e in lines).most_common(20))
    print('polylines',Counter(e['layer'] for e in polys))
    print('room/text labels',len(texts))

if __name__=='__main__':main()
