#!/usr/bin/env python3
"""Validate actual routed design against cached CAD ray intersections."""
from pathlib import Path
import csv
import json
import math
import argparse
import hashlib

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import shape
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'design/final/coverage'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--step',type=float,default=.25)
    parser.add_argument('--resolution-only',action='store_true')
    args=parser.parse_args()
    model=json.loads((OUT/'area-model.json').read_text())
    area_model_sha256=hashlib.sha256((OUT/'area-model.json').read_bytes()).hexdigest()
    current=json.loads((ROOT/'design/final/candidate.json').read_text())
    from coverage import fields
    cached=fields(model,current['antennas'],args.step)
    source_ants=current['antennas']
    weights=cached['weights'];areas=cached['areas'];gid=cached['gid'];points=cached['points']
    old_xy=np.array([(a['x'],a['y']) for a in source_ants]);indexes=[]
    for a in current['antennas']:
        delta=np.linalg.norm(old_xy-np.array((a['x'],a['y'])),axis=1)
        index=int(delta.argmin());assert delta[index]<1e-8
        indexes.append(index)
    assert len(set(indexes))==len(indexes)
    radius=cached['radius'][indexes];walls=cached['wall'][indexes];cols=cached['columns'][indexes];closed=cached['closed'][indexes]
    design_fingerprint=hashlib.sha256((ROOT/'design/final/candidate.json').read_bytes()).hexdigest()
    if args.resolution_only:
        losses=np.array([next(r['total_loss_db'] for r in current['rf_points'] if r['antenna']==a['id'] and r['frequency_mhz']==2600) for a in current['antennas']])
        best=(6-losses[:,None]-(20*math.log10(2600)-27.55+25*np.log10(radius))-walls-cols).max(axis=0)
        result=dict(step_m=args.step,receiver_cells=len(points),reference_percent_2100=float(weights[best>-90].sum()/2100*100),
                    design_fingerprint=design_fingerprint,area_model_sha256=area_model_sha256)
        signal=6-losses[:,None]-(20*math.log10(2600)-27.55+25*np.log10(radius))-walls-cols
        result['scores']={name:float(weights[field.max(0)>-90].sum()/21) for name,field in
                          [('nominal',signal),('n3',signal-5*np.log10(radius)),
                           ('reserve3',signal-3),('closed_reserve3',signal-closed-3)]}
        (OUT/f'resolution-{args.step:g}.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result));return
    rows=[];room_rows=[];saved_fields={};n3_fields={}
    scenarios=[('P1_n2.5',2.5,0,False,False),('P1_n2',2,0,False,False),
               ('P1_n3',3,0,False,False),('P1_n3_closed_gaps',3,0,True,False),('P1_extra_RF_3dB',2.5,3,False,False),
               ('P1_closed_gaps',2.5,0,True,False),('P1_two_ports_total',2.5,10*math.log10(2),False,False),
               ('P2_carrier23',2.5,10*math.log10(6),False,False),('P1_cable78_plus5pct',2.5,0,False,True),
               ('P1_geometry_uncertain_fail',2.5,0,False,False),
               ('P1_closed_gaps_RF3',2.5,3,True,False),
               ('P1_geometry_uncertain_fail_RF3',2.5,3,False,False),
               ('P1_closed_gaps_geometry_uncertain_fail_RF3',2.5,3,True,False)]
    for f,prb in ((1800,100),(2100,75),(2600,50)):
        losses=np.array([next(r['total_loss_db'] for r in current['rf_points'] if r['antenna']==a['id'] and r['frequency_mhz']==f) for a in current['antennas']])
        alpha={1800:5.21,2100:5.67,2600:6.39}[f]
        cable_extra=np.array([a['length78_m']*alpha/100*.05 for a in current['antennas']])
        p=23-10*math.log10(2*prb)
        for name,n,extra,gaps,tolerance in scenarios:
            values=(p+3-losses[:,None]-(20*math.log10(f)-27.55+10*n*np.log10(radius))-walls-cols-extra
                    -(closed if gaps else 0)-(cable_extra[:,None] if tolerance else 0))
            best=values.max(axis=0);passed=best>-90
            if 'geometry_uncertain_fail' in name:
                uncertain=[i for i,g in enumerate(model['groups']) if abs(g['relative_area_difference'])>.1]
                passed&=~np.isin(gid,uncertain)
            row=dict(scenario=name,frequency_mhz=f,step_m=args.step,antennas=len(indexes),
                     reference_covered_m2=float(weights[passed].sum()),
                     reference_percent_2100=float(weights[passed].sum()/2100*100),
                     model_area_percent=float(areas[passed].sum()/areas.sum()*100),
                     worst_dbm=float(best.min()),passed_95=bool(weights[passed].sum()/2100>=.95))
            rows.append(row)
            if name=='P1_n2.5':
                saved_fields[f]=best
                for i,g in enumerate(model['groups']):
                    select=gid==i
                    covered=float(weights[select&passed].sum())
                    room_rows.append(dict(frequency_mhz=f,group=g['id'],rooms='+'.join(g['rooms']),
                                          reference_m2=g['reference_area_m2'],covered_reference_m2=covered,
                                          percent=100*covered/g['reference_area_m2']))
                fig,ax=plt.subplots(figsize=(9,14))
                chart=ax.scatter(points[:,0],points[:,1],c=best,s=7,marker='s',cmap='RdYlGn',vmin=-110,vmax=-75)
                for g in model['groups']:
                    poly=shape(g['geometry']);ax.plot(*poly.exterior.xy,color='#333333',lw=.35)
                for a in current['antennas']:
                    ax.plot(a['x'],a['y'],'k.',ms=3);ax.text(a['x']+.15,a['y'],a['id'],fontsize=4)
                ax.plot(*current['head'],'b*',ms=10)
                ax.set_aspect('equal');ax.set_xlim(-2,39);ax.set_ylim(-2,66)
                ax.set_title(f'{f} МГц, P1, n=2,5: {len(indexes)} антенны\n{row["reference_percent_2100"]:.2f}% от 2100 м² по весам экспликации; помещение 89 — непокрыто',fontsize=10)
                ax.set_xlabel('CAD X, м');ax.set_ylabel('CAD Y, м')
                fig.colorbar(chart,ax=ax,label='Расчётный RSRP, дБм')
                fig.savefig(OUT/f'rsrp-{f}-walls.png',dpi=180,bbox_inches='tight');plt.close(fig)
            elif name=='P1_n3':
                n3_fields[f]=best
                fig,ax=plt.subplots(figsize=(9,14))
                chart=ax.scatter(points[:,0],points[:,1],c=best,s=7,marker='s',cmap='RdYlGn',vmin=-110,vmax=-75)
                for g in model['groups']:
                    poly=shape(g['geometry']);ax.plot(*poly.exterior.xy,color='#333333',lw=.35)
                for a in current['antennas']:ax.plot(a['x'],a['y'],'k.',ms=3)
                ax.set_title(f'{f} МГц, P1, n=3: {len(indexes)} антенны\n{row["reference_percent_2100"]:.2f}% от 2100 м²; непроверенная площадь считается непрошедшей',fontsize=10)
                ax.set_aspect('equal');ax.set_xlim(-2,39);ax.set_ylim(-2,66)
                ax.set_xlabel('CAD X, м');ax.set_ylabel('CAD Y, м');fig.colorbar(chart,ax=ax,label='Расчётный RSRP, дБм')
                fig.savefig(OUT/f'rsrp-{f}-n3.png',dpi=180,bbox_inches='tight');plt.close(fig)
            elif f==2600 and name in ('P1_extra_RF_3dB','P1_closed_gaps_geometry_uncertain_fail_RF3'):
                fig,ax=plt.subplots(figsize=(9,14));display=best.copy()
                if 'geometry_uncertain' in name:display[np.isin(gid,uncertain)]=np.nan
                chart=ax.scatter(points[:,0],points[:,1],c=display,s=7,marker='s',cmap='RdYlGn',vmin=-110,vmax=-75)
                for g in model['groups']:
                    poly=shape(g['geometry']);ax.plot(*poly.exterior.xy,color='#333333',lw=.35)
                for a in current['antennas']:ax.plot(a['x'],a['y'],'k.',ms=3)
                title='Дополнительные 3 дБ RF-потерь' if name=='P1_extra_RF_3dB' else 'Закрытые проёмы, спорный контур и +3 дБ'
                ax.set_title(f'B7, P1, n=2,5: {title}\n{row["reference_percent_2100"]:.2f}% от 2100 м²; непроверенная площадь считается непрошедшей',fontsize=10)
                ax.set_aspect('equal');ax.set_xlim(-2,39);ax.set_ylim(-2,66)
                ax.set_xlabel('CAD X, м');ax.set_ylabel('CAD Y, м');fig.colorbar(chart,ax=ax,label='Расчётный RSRP, дБм')
                filename='rsrp-2600-reserve3.png' if name=='P1_extra_RF_3dB' else 'rsrp-2600-joint-reserve3.png'
                fig.savefig(OUT/filename,dpi=180,bbox_inches='tight');plt.close(fig)
    assert len(rows)==39
    report=dict(status='Сценарные прогнозы; материал/геометрия/мощность не подтверждены измерениями',
                denominator_m2=2100,unknown_reference_m2=45.52,unallocated_difference_m2=2.92,
                located_reference_m2=float(weights.sum()),receiver_cells=len(points),step_m=args.step,
                antennas=len(indexes),source_head=current['head'],model_geometry_area_m2=float(areas.sum()),
                normative_threshold_dbm=-90,strict_greater=True,design_fingerprint=design_fingerprint,area_model_sha256=area_model_sha256,
                actual_routes_rebuilt=True,scenarios=rows)
    (OUT/'coverage-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    with (OUT/'coverage-scenarios.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0].keys(),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    with (OUT/'room-coverage.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=room_rows[0].keys(),lineterminator='\n');writer.writeheader();writer.writerows(room_rows)
    np.savez_compressed(OUT/'validated-fields.npz',points=points,weights=weights,areas=areas,gid=gid,
                        **{f'rsrp_{f}':v for f,v in saved_fields.items()},**{f'rsrp_n3_{f}':v for f,v in n3_fields.items()})
    # Add results to the same workbook; quantities are still generated from routes.
    wb=load_workbook(ROOT/'equipment/bill-of-materials.xlsx')
    for title in ('Покрытие сценарии','Покрытие помещения'):
        if title in wb:del wb[title]
    from build_project import style
    ws=wb.create_sheet('Покрытие сценарии');ws.append(['Сценарий','Частота МГц','Шаг м','Антенн','Покрыто по весам м²','Доля от 2100, %','Доля маски, %','Минимум RSRP, дБм','Модель ≥95%'])
    for r in rows:ws.append(list(r.values()))
    style(ws,{chr(65+i):24 for i in range(len(rows[0]))})
    ws=wb.create_sheet('Покрытие помещения');ws.append(['Частота МГц','Группа','Помещения','Площадь экспликации м²','Покрыто по весам м²','Доля группы, %'])
    for r in room_rows:ws.append(list(r.values()))
    style(ws,{'A':20,'B':12,'C':55,'D':24,'E':28,'F':18})
    wb.save(ROOT/'equipment/bill-of-materials.xlsx')
    for row in rows:print(row['scenario'],row['frequency_mhz'],round(row['reference_percent_2100'],3))

if __name__=='__main__':main()
