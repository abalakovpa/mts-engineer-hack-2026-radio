#!/usr/bin/env python3
"""Fine-grid verification and documentation of the separate n=3 candidate."""
from collections import Counter
from pathlib import Path
import copy
import csv
import hashlib
import json
import math
import shutil

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import shape, Point, LineString

from research_n3 import ROOT, OUT, CACHE, evaluate, losses_for, FREQUENCIES
from route_design import construct
from build_project import V, EDGES, ZONES


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(str(v) for v in row)+' |' for row in rows])+'\n'
def fmt(value,precision=2):return f'{value:.{precision}f}'.replace('.',',')


def quantities(d):
    routes=d['trunks']+d['subfeeds']+d['drops'];counts=Counter(r['cable'] for r in routes)
    return dict(antennas=len(d['antennas']),PC221=6,PC211=8,PC250=9,PC252=16,
                installed78_m=d['cable78_installed'],installed12_m=d['cable12_installed'],
                total_coax_m=d['cable78_installed']+d['cable12_installed'],
                purchase78_m=math.ceil(d['cable78_installed']*1.1),purchase12_m=math.ceil(d['cable12_installed']*1.1),
                segments78=2*counts['7/8'],segments12=2*counts['1/2'],
                connectors78=4*counts['7/8'],connectors12=4*counts['1/2'],
                jumpers3m=109+d['local_jumper_count'],local_jumpers3m=d['local_jumper_count'])


def validate_routes(model,d,project):
    ants=d['antennas'];assert len(ants)==32 and len({a['id'] for a in ants})==32
    assert Counter(a['zone'] for a in ants)=={z:8 for z in range(1,5)}
    for z in range(1,5):
        assert Counter(a['power_class'] for a in ants if a['zone']==z)=={'direct':2,'pair':2,'quartet':4}
        assert math.isclose(2*.25+2*.125+4*.0625,1)
        assert np.allclose(d['trunks'][z-1]['points'][-1],project['zone_hubs'][z-1])
        assert min(LineString((V[a],V[b])).distance(Point(project['zone_hubs'][z-1]))
                   for a,b in EDGES)<1e-8
    for a in ants:
        group=next(g for g in model['groups'] if a['room'] in g['rooms'])
        assert shape(group['geometry']).covers(Point(a['x'],a['y'])),a['id']
    routes=d['trunks']+d['subfeeds']+d['drops'];assert len(routes)==44
    for r in routes:
        measured=sum(math.dist(a,b) for a,b in zip(r['points'],r['points'][1:]))
        assert math.isclose(measured,r['length'],abs_tol=1e-7),r['id']
        if r['length']<1e-6:assert r['cable']=='jumper' and r['jumper_length_m']==3
    fixed=8.8+10*math.log10(8)+1
    for a in ants:
        path=[d['trunks'][a['zone']-1],next(r for r in d['drops'] if r['id']==a['id'])]
        if a['subgroup']:path.append(next(r for r in d['subfeeds'] if r['id']==f'F{a["zone"]}-{a["subgroup"]}'))
        delta={'direct':-10*math.log10(2)-.5,'pair':0,'quartet':10*math.log10(2)}[a['power_class']]
        for frequency,prb,alpha78,alpha12 in FREQUENCIES:
            cable=sum(r['length']*(alpha78 if r['cable']=='7/8' else alpha12)/100
                      for r in path if r['cable']!='jumper')
            loss=fixed+delta+cable+sum(r.get('assumed_loss_db',0) for r in path)
            row=next(r for r in d['rf_points'] if r['antenna']==a['id'] and r['frequency_mhz']==frequency)
            assert math.isclose(loss,row['total_loss_db'],abs_tol=1e-8)
    return True


def map_pair(model,baseline,new,cached,frequency):
    fig,axes=plt.subplots(1,2,figsize=(12,11),layout='constrained')
    for ax,label,values in [(axes[0],'Основная схема',baseline),(axes[1],'Исследовательский вариант',new)]:
        chart=ax.scatter(cached['points'][:,0],cached['points'][:,1],c=values,
                         cmap='RdYlGn',vmin=-110,vmax=-75,s=4,marker='s',rasterized=True)
        for g in model['groups']:
            poly=shape(g['geometry']);ax.plot(*poly.exterior.xy,c='#515963',lw=.35)
        percent=float(cached['weights'][values>-90].sum()/21)
        ax.set_title(f'{label}\n{percent:.2f}% от 2100 м² выше −90 дБм',fontsize=11)
        ax.set_aspect('equal');ax.set_xlim(-2,39);ax.set_ylim(-2,66);ax.set_xlabel('CAD X, м');ax.set_ylabel('CAD Y, м')
    fig.colorbar(chart,ax=axes,label='RSRP, дБм',shrink=.85)
    fig.suptitle(f'P1, n=3 / {frequency} МГц / сетка 0,25 м\n'
                 'Одинаковые контуры, мощность пилота и шкала; 48,44 м² без локализации включены как непрошедшие',fontsize=11)
    for suffix in ('png','pdf'):fig.savefig(OUT/f'n3-{frequency}-comparison.{suffix}',dpi=160,bbox_inches='tight')
    plt.close(fig)


def main():
    model=json.loads((ROOT/'design/final/coverage/area-model.json').read_text())
    original=json.loads((OUT/'baseline-candidate.json').read_text())
    baseline_input=json.loads((OUT/'baseline-project-input.json').read_text())
    proposal=json.loads((OUT/'best32-project-input.json').read_text())
    best=json.loads((OUT/'best32-candidate.json').read_text())
    assert np.allclose(proposal['head'],baseline_input['head'])
    assert validate_routes(model,best,proposal)
    variants={'baseline':original}
    nodes=copy.deepcopy(baseline_input);nodes['zone_hubs']=proposal['zone_hubs'];variants['hubs_only']=construct(nodes)
    powers=copy.deepcopy(baseline_input);powers['power_classes']=proposal['power_classes'];variants['powers_only']=construct(powers)
    unmoved=copy.deepcopy(proposal)
    original_by_source={a['baseline_id']:a for a in original['antennas']}
    seed={a['id']:a for a in json.loads((ROOT/'design/final/coverage/baseline-candidate.json').read_text())['antennas']}
    for a in unmoved['antennas']:
        source=original_by_source.get(a['baseline_id'],seed[a['baseline_id']]);a.update(x=source['x'],y=source['y'])
    variants['without_local_moves']=construct(unmoved)
    variants['best32']=best
    summary=[];fine={};propagations={};maps={}
    for name,design in variants.items():
        folder=CACHE/name;folder.mkdir(exist_ok=True)
        for step in (.25,.5):
            start=CACHE/'baseline'/f'propagation-{step:g}.npz';dest=folder/start.name
            if start.exists() and not dest.exists():shutil.copyfile(start,dest)
        result,cached,values=evaluate(model,design,.25,folder)
        fine[name]=result;propagations[name]=cached;maps[name]=values
        summary.append(dict(variant=name,step_m=.25,receiver_cells=len(cached['points']),
                            results=result,quantities=quantities(design),
                            candidate_canonical_sha256=hashlib.sha256(json.dumps(design,sort_keys=True).encode()).hexdigest()))
        if name!='baseline':write(f'{name}-verified-candidate.json',design)
        print(name,result,flush=True)
    # Match the original authoritative evaluation, not just the search score.
    original_report=json.loads((OUT/'baseline-results.json').read_text())
    for frequency,_,_,_ in FREQUENCIES:
        reference=original_report[f'{frequency}_n3']
        assert math.isclose(reference,fine['baseline'][f'{frequency}_n3'],abs_tol=1e-6)
    for frequency,_,_,_ in FREQUENCIES:
        assert fine['best32'][f'{frequency}_n3']>=95
        assert fine['best32'][f'{frequency}_joint_reserve3']>=95
    coarse,_,_=evaluate(model,best,.5,CACHE/'best32-control')
    last_search=json.loads((OUT/'search-history.json').read_text())[-1]
    assert abs(coarse['2600_n3']-last_search['n3_b7'])<1e-4
    assert abs(coarse['2600_joint_reserve3']-last_search['joint_reserve3_b7'])<1e-4
    for frequency,_,_,_ in FREQUENCIES:
        assert abs(coarse[f'{frequency}_n3']-fine['best32'][f'{frequency}_n3'])<1
    baseline=propagations['baseline'];winner=propagations['best32']
    assert np.allclose(baseline['points'],winner['points']) and np.allclose(baseline['weights'],winner['weights'])
    receiver_weights=baseline['weights'];gid=baseline['gid']
    b7=maps['baseline']['2600_n3'];n7=maps['best32']['2600_n3']
    room_rows=[];diagnostic_rows=[]
    losses=losses_for(original,2600)
    signal=(6-losses[:,None]-(20*math.log10(2600)-27.55)-30*np.log10(baseline['radius'])
            -baseline['wall']-baseline['columns'])
    chosen=signal.argmax(0)
    for i,g in enumerate(model['groups']):
        mask=gid==i;failed=mask&(b7<=-90);target=mask&(n7<=-90)
        row=dict(group=g['id'],rooms=', '.join(g['rooms']),reference_m2=g['reference_area_m2'],
                 baseline_failed_m2=float(receiver_weights[failed].sum()),best_failed_m2=float(receiver_weights[target].sum()),
                 baseline_percent=float(receiver_weights[mask&(b7>-90)].sum()/g['reference_area_m2']*100),
                 best_percent=float(receiver_weights[mask&(n7>-90)].sum()/g['reference_area_m2']*100))
        room_rows.append(row)
        if row['baseline_failed_m2']>.1:
            indexes=np.flatnonzero(failed);ant=chosen[indexes];weights=receiver_weights[failed]
            average=lambda array:float(np.average(array[ant,indexes],weights=weights))
            diagnostic_rows.append(dict(**row,mean_spatial_distance_m=average(baseline['radius']),
                                        mean_wall_loss_db=average(baseline['wall']),
                                        mean_column_loss_db=average(baseline['columns']),
                                        mean_rf_loss_db=float(np.average(losses[ant],weights=weights))))
    for name,rows in [('group-comparison.csv',room_rows),('baseline-diagnostics.csv',diagnostic_rows)]:
        with (OUT/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    for frequency,_,_,_ in FREQUENCIES:
        map_pair(model,maps['baseline'][f'{frequency}_n3'],maps['best32'][f'{frequency}_n3'],winner,frequency)
    fig,axes=plt.subplots(1,2,figsize=(12,11),layout='constrained')
    for ax,label,values in [(axes[0],'Основная схема',b7),(axes[1],'Исследовательский вариант',n7)]:
        deficit=np.maximum(-90-values,0)
        chart=ax.scatter(winner['points'][:,0],winner['points'][:,1],c=deficit,cmap='Reds',vmin=0,vmax=20,s=4,marker='s',rasterized=True)
        for g in model['groups']:
            p=shape(g['geometry']);ax.plot(*p.exterior.xy,c='#777777',lw=.35)
        for row in sorted(diagnostic_rows,key=lambda r:r['baseline_failed_m2'],reverse=True)[:8]:
            group=next(g for g in model['groups'] if g['id']==row['group']);point=shape(group['geometry']).representative_point()
            ax.text(point.x,point.y,row['rooms'],ha='center',fontsize=7,
                    bbox=dict(facecolor='white',edgecolor='none',alpha=.75,pad=1))
        ax.set_title(label);ax.set_aspect('equal');ax.set_xlim(-2,39);ax.set_ylim(-2,66)
        ax.set_xlabel('CAD X, м');ax.set_ylabel('CAD Y, м')
    fig.colorbar(chart,ax=axes,label='Дефицит относительно −90 дБм, дБ (шкала до 20)',shrink=.85)
    fig.suptitle('B7 / P1 / n=3: участки дефицита\nБелый цвет — дефицит 0 дБ; строгий порог >−90 проверяется отдельно',fontsize=12)
    for suffix in ('png','pdf'):fig.savefig(OUT/f'n3-b7-deficit.{suffix}',dpi=160,bbox_inches='tight')
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,14),layout='constrained')
    for g in model['groups']:
        p=shape(g['geometry']);ax.plot(*p.exterior.xy,c='#aeb6bf',lw=.6)
    colors=['#24568a','#8a5592','#008075','#bf701c']
    for r in best['drops']:
        ax.plot(*np.array(r['points']).T,c='#9ea9b5',lw=.5,alpha=.6)
    for r in best['trunks']+best['subfeeds']:
        ax.plot(*np.array(r['points']).T,c='#4a5662',lw=.8)
    for a in best['antennas']:
        ax.scatter(a['x'],a['y'],c=colors[a['zone']-1],s=24)
        ax.annotate(f'{a["id"]}/{a["power_class"][0]}',(a['x'],a['y']),xytext=(3,3),textcoords='offset points',fontsize=6)
    for z,p in enumerate(proposal['zone_hubs'],1):
        ax.scatter(*p,marker='s',c=colors[z-1],s=55);ax.annotate(f'S-Z{z}',p,xytext=(4,-10),textcoords='offset points',fontsize=8)
    ax.scatter(*proposal['head'],marker='*',c='#d82035',s=120);ax.annotate('ВК (проект)',proposal['head'],xytext=(4,7),textcoords='offset points',fontsize=8)
    ax.set_title('Исследовательский вариант n=3 / 32 In06\n'
                 'd — непосредственная; p — парная; q — четверная ветвь; точное положение задают X/Y',fontsize=10)
    ax.set_aspect('equal');ax.set_xlim(-2,39);ax.set_ylim(-2,66);ax.set_xlabel('CAD X, м');ax.set_ylabel('CAD Y, м')
    for suffix in ('png','pdf'):fig.savefig(OUT/f'candidate-layout.{suffix}',dpi=180,bbox_inches='tight')
    plt.close(fig)
    np.savez_compressed(OUT/'verified-fields.npz',points=winner['points'],weights=winner['weights'],gid=winner['gid'],
                        **{f'baseline_{f}':maps['baseline'][f'{f}_n3'] for f,_,_,_ in FREQUENCIES},
                        **{f'best_{f}':maps['best32'][f'{f}_n3'] for f,_,_,_ in FREQUENCIES})
    canonical_paths=['design/final/candidate.json','design/final/project-input.json',
                     'design/final/coverage/area-model.json','submission/mts-radio-final.zip']
    report=dict(date='2026-10-13',baseline_commit='50974e2096c6a78277f793af0a3ec0c004f45f9d',
                geometry_sha256=digest(ROOT/'design/final/coverage/area-model.json'),
                candidate_sha256=digest(OUT/'best32-candidate.json'),source_hashes={p:digest(ROOT/p) for p in canonical_paths},
                variants=summary,coarse_control=coarse,goal_met_all_bands=True,
                full_kpi_compliance=False,adopted_into_submission=False,physical_installation_confirmed=False)
    write('verification.json',report)
    labels={'baseline':'Основная схема','hubs_only':'Только новые S-узлы','powers_only':'Только распределение мощности',
            'without_local_moves':'Узлы, мощности и замены; без локальных переносов','best32':'Полный исследовательский вариант'}
    q0=quantities(original);q1=quantities(best)
    text='# Возможность выполнения RSRP при n=3\n\n'
    text+='Дата: 13.10.2026. Исследование выполнено отдельно от основного пакета. Исходные DOCX, геометрия и архив сдачи не изменены.\n\n'
    text+='## Результат\n\n'
    text+='Найден полностью трассированный пассивный вариант с **32 In06** и прежней мощностью пилота. '
    text+='На сетке **0,25 м** он проходит RSRP >−90 дБм на ≥95% от 2100 м² при n=3 во всех трёх диапазонах. '
    text+='Совместная проверка n=2,5 с закрытыми проёмами, 114.2 как непрошедшим и дополнительными 3 дБ также проходит. '
    text+='Это результат условной модели P1, не измерения и не подтверждение всех KPI. В таблицах «основная схема» означает зафиксированный вариант до принятия.\n\n'
    text+=table(['Диапазон','Основная схема n=3','Новый вариант n=3','Новый: проёмы/контур/+3 дБ'],
        [[f'{f} МГц',fmt(fine['baseline'][f'{f}_n3'])+'%',fmt(fine['best32'][f'{f}_n3'])+'%',
          fmt(fine['best32'][f'{f}_joint_reserve3'])+'%'] for f,_,_,_ in FREQUENCIES])
    text+='\n## Данные задания и принятые допущения\n\n'
    text+='Источники: [задание финала](task.docx), [основная модель покрытия](coverage-review.md), '
    text+='[проверка RF-бюджета](rsrp-calculation.md), предоставленный перечень оборудования.\n\n'
    text+='**Данные задания:** пилот 23 дБм на БС, потолок 7 м, перегородки 15 дБ, внешние стены/ЖБ колонны 30 дБ, '
    text+='полосы B3/B1/B7 20/15/10 МГц; критерий RSRP >−90 дБм на 95%.\n\n'
    text+='**Выбор из перечня:** In06, потолочная omni MIMO, 800–2700 МГц; указано усиление 3 dBi. '
    text+='Его использование как номинального усиления без вертикальной диаграммы остаётся допущением.\n\n'
    text+='**Собственные допущения:** P1 — сумма 2N_PRB CRS-поднесущих в CRS-символе на одном порту; '
    text+='высота UE 1,5 м, G_UE=0, G_In06=3 dBi; идентификация препятствий и экспликационные веса прежние. '
    text+='n=3 — сценарий чувствительности, не отдельное требование задания. Пассивные excess loss, местные джамперы и '
    text+='пригодность лотков сохраняют прежнюю условность. Материал, вертикальная диаграмма, фактическая ВК и монтажная доступность не установлены.\n\n'
    text+='**Критерий этого исследования:** пройти n=3 и сохранить ≥95% совместного сценария запаса; '
    text+='не повышать мощность, не менять геометрию и знаменатель. 45,52 м² помещения 89 и ещё 2,92 м² до 2100 '
    text+='включены как непрошедшие. 114.2 не исключена из площади.\n\n'
    text+='Вес ячейки w_i = (a_i/A_model,group)×A_reference,group по экспликации. Сумма весов '
    text+='2051,56 м²; неизменный знаменатель 2100 м². Это модельная экстраполяция, не подтверждение '
    text+='достоверности всех контуров. Масштаб координат не изменяется.\n\n'
    text+='Формулы: P_CRS_RE = 23−10log10(2N_PRB); L_n = 20log10(f_MHz)−27,55+10n log10(r_m); '
    text+='RSRP_i = P_CRS_RE−L_RF,i+3−L_n−L_walls,i−L_columns,i; r = √(d²+5,5²). '
    text+='Выбран сильнейший отдельный путь; фазовое сложение не учитывается. Доля = 100×Σw[RSRP>−90]/2100. '
    text+='Изменение n=2,5→3 добавляет 5log10(r) дБ потерь, а не постоянные 3 дБ.\n\n'
    text+='## Где возникал дефицит\n\n'
    text+=f'Исходный B7 не проходит на {fmt((100-fine["baseline"]["2600_n3"])*21)} м², включая '
    text+=f'48,44 м² нелокализованной площади. Для достижения 95% требовалось дополнительно покрыть '
    text+=f'{fmt((95-fine["baseline"]["2600_n3"])*21)} м² при прежнем знаменателе.\n\n'
    worst=sorted(diagnostic_rows,key=lambda row:row['baseline_failed_m2'],reverse=True)[:8]
    text+=table(['Помещения','Непрошедшие м²','Среднее r, м','Стены, дБ','RF-потери, дБ'],
        [[r['rooms'],fmt(r['baseline_failed_m2']),fmt(r['mean_spatial_distance_m']),fmt(r['mean_wall_loss_db']),
          fmt(r['mean_rf_loss_db'])] for r in worst])
    text+='\nСредние относятся к сильнейшему пути на провальных ячейках, взвешены по площади; '
    text+='они описывают бюджет, а не доказывают единственную причину. В 106.4/106.5/106.2 основной вклад '
    text+='давали расстояние и RF-потери; в 121 и 114.2 существенны пересечения препятствий.\n\n'
    text+='![Дефицит B7](../../design/final/n3/n3-b7-deficit.png)\n\n'
    text+='## Что изменено\n\n'
    text+='ВК оставлена в проектной точке части 104.2, (9,2;31,2) м. Перенесены S-узлы по предложенному графу лотков; '
    text+='координаты ниже — модельные точки, не согласованные места установки. На каждом S остаются отдельные PC252 для M1/M2.\n\n'
    text+=table(['Узел','Прежние X/Y, м','Новые X/Y, м'],
        [[f'S-Z{z+1}',f'{fmt(a[0],3)} / {fmt(a[1],3)}',f'{fmt(b[0],3)} / {fmt(b[1],3)}']
         for z,(a,b) in enumerate(zip(ZONES,proposal['zone_hubs']))])
    text+='\nДерево 2+2+4 сохранено: две непосредственные антенны, две через PC250 и четыре через PC252. '
    text+='Идеальные зональные доли 2×1/4+2×1/8+4×1/16=1. Выходы головного PC221 по-прежнему делят мощность '
    text+='между четырьмя зонами; два MIMO-порта физически отдельны. Мощности антенн не суммируются как новые источники.\n\n'
    old_by_id={a['id']:a for a in original['antennas']}
    changed=[]
    for a in best['antennas']:
        previous=old_by_id[a['id']]
        if a['room']!=previous['room'] or math.dist((a['x'],a['y']),(previous['x'],previous['y']))>.01 or a['power_class']!=previous['power_class']:
            changed.append([a['id'],previous['room'],a['room'],previous['power_class']+' → '+a['power_class'],
                            f'{fmt(a["x"],3)} / {fmt(a["y"],3)}'])
    text+=table(['ID','Прежняя привязка','Новая привязка','Класс мощности','Новые X/Y, м'],changed)
    text+='\nНомер помещения — исходная привязка/целевая зона. Для объединённых CAD-групп он не удостоверяет '
    text+='нахождение новой позиции в отдельной комнате. Все точки проверены внутри соответствующих восстановленных групп. '
    text+='Полный журнал локальных переносов — moves.json.\n\n'
    text+='![Расположение исследовательского варианта](../../design/final/n3/candidate-layout.png)\n\n'
    text+='## Сравнение полностью трассированных вариантов\n\n'
    text+=table(['Вариант','B7 n=3','B7 совместный +3 дБ','Коаксиал, м'],
        [[labels[row['variant']],fmt(row['results']['2600_n3'])+'%',fmt(row['results']['2600_joint_reserve3'])+'%',
          fmt(row['quantities']['total_coax_m'])] for row in summary])
    move_count=len(json.loads((OUT/'moves.json').read_text()))
    text+='\nКонтроли «только узлы» и «только мощности» переносят соответствующие решения финального кандидата '
    text+='на прежнее размещение. «Без локальных переносов» сохраняет выбранные узлы, мощности и заменённые '
    text+=f'исходные позиции, но отменяет {move_count} локальных смещений. Это самостоятельные абляционные варианты, '
    text+='не результаты их отдельной оптимизации. Для каждого заново рассчитаны подгрупповые узлы и маршруты.\n\n'
    text+='## Комплектация и цена изменения\n\n'
    text+=table(['Позиция','Основная схема','Исследовательский вариант'],
        [[label,fmt(q0[key]) if isinstance(q0[key],float) else q0[key],fmt(q1[key]) if isinstance(q1[key],float) else q1[key]]
         for label,key in [('In06','antennas'),('PC221','PC221'),('PC211','PC211'),('PC250','PC250'),('PC252','PC252'),
             ('7/8 установленный, м','installed78_m'),('1/2 установленный, м','installed12_m'),
             ('7/8 закупочный, м','purchase78_m'),('1/2 закупочный, м','purchase12_m'),
             ('Разъёмы 7/8','connectors78'),('Разъёмы 1/2','connectors12'),('Джамперы 3 м','jumpers3m')]])
    text+='\nВсе количества рассчитаны для двух MIMO-ветвей. '
    text+=f'Общий коаксиал {fmt(q0["total_coax_m"])} → {fmt(q1["total_coax_m"])} м '
    text+=f'({fmt((q1["total_coax_m"]/q0["total_coax_m"]-1)*100)}%). Закупочные длины: ceil(1,10×установленная). '
    text+='Два разъёма на каждый изготовляемый участок; заводские местные джамперы не считаются нулевыми фидерами. '
    text+='Цены не заданы, экономический оптимум не заявляется. Потребность в нагрузках свободных портов и неподтверждённые '
    text+='интерфейсы/исполнения кабеля сохраняются.\n\n'
    text+='## Контроль точности и ограничения\n\n'
    text+=table(['Диапазон','Новый n=3, шаг 0,5 м','Новый n=3, шаг 0,25 м','Новый n=3 с проёмами','P2, n=2,5'],
        [[f'{f} МГц',fmt(coarse[f'{f}_n3'])+'%',fmt(fine['best32'][f'{f}_n3'])+'%',
          fmt(fine['best32'][f'{f}_n3_closed'])+'%',fmt(fine['best32'][f'{f}_P2'])+'%'] for f,_,_,_ in FREQUENCIES])
    text+='\nПроверены независимая сумма сегментов каждого маршрута, потери всех путей на трёх частотах, '
    text+='сохранение идеальных долей мощности, совпадение базового n=3 с основным отчётом и неизменность геометрии. '
    text+='Сетка 0,25 м содержит 35522 ячейки; 0,5 м — контроль дискретизации, не калибровка физической модели.\n\n'
    text+='Число антенн увеличивать для найденного решения не потребовалось; минимальность 32 не доказана. '
    text+='Поиск ограничен 48 исходными позициями с текущими смещениями, 420 распределениями на зону, двумя '
    text+='проходами замен и локальной сеткой ±3 м/центром группы. В каждой зоне выбраны 8 из 12 исходных '
    text+='позиций; межзональные замены в выполненном поиске не применялись. Узлы проверены в конечном наборе проекций на '
    text+='предложенные лотки; глобальный оптимум не установлен.\n\n'
    text+='P2 остаётся отдельным ограничением нормировки мощности. SINR/RSRQ/C/I, UL, MIMO rank, вертикальная диаграмма, '
    text+='нагрузки, PIM, мощности оборудования и пожарное исполнение не подтверждены. Пассивная схема не обеспечивает '
    text+='буквально требуемое удалённое регулирование. Новые измерения или паспорта не выдуманы. Независимые источники '
    text+='по зонам либо активная/гибридная DAS остаются отдельной архитектурной альтернативой при требовании более '
    text+='слабого питания; их преимущества и соответствие пассивному ТЗ здесь не доказаны.\n\n'
    text+='## Карты и воспроизведение\n\n'
    for f,_,_,_ in FREQUENCIES:text+=f'![P1 n=3, {f} МГц](../../design/final/n3/n3-{f}-comparison.png)\n\n'
    text+='Данные: design/final/n3/verification.json, group-comparison.csv, baseline-diagnostics.csv; '
    text+='входы — best32-project-input.json, трассированный кандидат — best32-candidate.json. '
    text+='verified-fields.npz содержит итоговые поля двух вариантов; PNG/PDF карт имеют одинаковые шкалы.\n\n'
    text+='Из корня репозитория с установленными requirements.txt:\n\n```sh\n'
    text+='MPLCONFIGDIR=/tmp/radio-mpl OPENBLAS_NUM_THREADS=1 python scripts/final/research_n3.py --passes 2\n'
    text+='MPLCONFIGDIR=/tmp/radio-mpl OPENBLAS_NUM_THREADS=1 python scripts/final/review_n3.py\n```\n\n'
    text+='Исследовательские кэши находятся вне репозитория. Основные пять артефактов не заменяются этими командами. '
    text+='Рекомендация по результатам исследования — перенести проверенный вариант в основной пакет с обновлением '
    text+='планов, портовой ведомости, спецификации и презентации как отдельный этап.\n'
    (ROOT/'docs/final/n3-feasibility.md').write_text(text)
    print('PASS: all three n=3 bands and joint reserve >=95%, routes/RF verified; primary package unchanged',flush=True)


if __name__=='__main__':main()
