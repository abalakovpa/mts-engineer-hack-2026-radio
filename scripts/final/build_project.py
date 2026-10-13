#!/usr/bin/env python3
"""Build a transparent CAD-based candidate; unresolved inputs are never certified."""
import csv
import heapq
import json
import math
from itertools import combinations
from functools import lru_cache
from pathlib import Path

import numpy as np
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT=Path(__file__).resolve().parents[2]
DESIGN=ROOT/'design/final'
FINAL=ROOT/'docs/final'
EQUIP=ROOT/'equipment'

def distance(a,b):return math.dist(a,b)

# Simplified design centreline follows measured CAD tray positions. Elbows and
# connections are approximated; this graph is a proposed route, not a CAD layer.
V=[(34.359272,45.786112),(32.659271,45.786112),(32.659271,39.986112),
   (26.339271,39.986112),(26.339271,30.542096),(11.839271,30.542096),
   (11.839271,26.486112),(4.736673,26.486112),(4.736673,28.115735),
   (1.315304,28.115735),(1.315304,4.584693),(29.939271,4.584693),
   (11.408860,30.542096),(11.408860,54.232997),
   (25.987715,30.542096),(25.987715,54.232997)]
EDGES=[(0,1),(1,2),(2,3),(3,4),(4,5),(5,6),(6,7),(7,8),(8,9),(9,10),(10,11),
       (5,12),(12,13),(4,14),(14,15)]
ZONES=[(11.408860,49.0),(25.987715,49.0),(11.839271,30.542096),(1.315304,12.0)]

def projection(p,a,b):
    t=max(0,min(1,np.dot(np.array(p)-a,np.array(b)-a)/distance(a,b)**2))
    q=tuple(np.array(a)+t*(np.array(b)-a))
    return q,t,distance(p,q)

def route(p,q):
    # Include exact perpendicular projections and split their hosting graph edges.
    pp=min((projection(p,V[a],V[b])+(i,) for i,(a,b) in enumerate(EDGES)),key=lambda x:x[2])
    qq=min((projection(q,V[a],V[b])+(i,) for i,(a,b) in enumerate(EDGES)),key=lambda x:x[2])
    nodes=list(V)+[pp[0],qq[0]];adj=[[] for _ in nodes]
    for i,(a,b) in enumerate(EDGES):
        chain=[(0,a),(1,b)]
        if pp[3]==i:chain.append((pp[1],len(V)))
        if qq[3]==i:chain.append((qq[1],len(V)+1))
        chain.sort()
        for (_,u),(_,v) in zip(chain,chain[1:]):
            w=distance(nodes[u],nodes[v]);adj[u].append((v,w));adj[v].append((u,w))
    start=len(V);end=start+1;heap=[(0,start)];best={start:0};prev={}
    while heap:
        cost,u=heapq.heappop(heap)
        if cost!=best[u]:continue
        if u==end:break
        for v,w in adj[u]:
            nc=cost+w
            if nc<best.get(v,float('inf')):best[v]=nc;prev[v]=u;heapq.heappush(heap,(nc,v))
    assert end in best
    path=[end]
    while path[-1]!=start:path.append(prev[path[-1]])
    path.reverse()
    points=[p]+[nodes[i] for i in path]+[q]
    return pp[2]+best[end]+qq[2],points

def style(ws,widths):
    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
    for cell in ws[1]:
        cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='17324D')
        cell.alignment=Alignment(vertical='center',wrap_text=True)
    ws.row_dimensions[1].height=45
    for row in ws.iter_rows(min_row=2):
        for cell in row:cell.alignment=Alignment(vertical='top',wrap_text=True)
    for col,width in widths.items():ws.column_dimensions[col].width=width
    for row in ws.iter_rows(min_row=2):
        line_count=max(max(1,math.ceil(len(str(c.value or ''))/(widths.get(c.column_letter,15)*.85))) for c in row)
        ws.row_dimensions[row[0].row].height=max(21,line_count*15+6)

def local_groups(ids,ants,zone):
    # Partition each zone into 4-antenna groups by actual tray-route length.
    count=len(ids);assert count%4==0
    points=[(ants[i]['x'],ants[i]['y']) for i in ids]
    hubs=[zone]+[min((projection(p,V[a],V[b]) for a,b in EDGES),key=lambda v:v[2])[0]
                 for p in points]
    costs=[[route(h,p)[0] for p in points] for h in hubs]
    feeds=[route(zone,h)[0] for h in hubs]
    best_group={}
    for subset in combinations(range(count),4):
        h=min(range(len(hubs)),key=lambda j:feeds[j]+sum(costs[j][i] for i in subset))
        mask=sum(1<<i for i in subset)
        best_group[mask]=(feeds[h]+sum(costs[h][i] for i in subset),h)
    @lru_cache(None)
    def solve(mask):
        if mask==0:return 0,()
        first=(mask & -mask).bit_length()-1
        rest=[i for i in range(first+1,count) if mask&(1<<i)]
        options=[]
        for peers in combinations(rest,3):
            sub=(1<<first)+sum(1<<i for i in peers)
            cost,tail=solve(mask^sub)
            options.append((best_group[sub][0]+cost,(sub,)+tail))
        return min(options)
    _,partition=solve((1<<count)-1)
    return [([ids[i] for i in range(count) if mask&(1<<i)],hubs[best_group[mask][1]]) for mask in partition]

def main():
    for p in (DESIGN,EQUIP):p.mkdir(parents=True,exist_ok=True)
    geom=json.loads((DESIGN/'cad-geometry.json').read_text())
    rooms=list(csv.DictReader((DESIGN/'room-schedule.csv').open()))
    catalog=load_workbook(FINAL/'source-materials/Перечень вспомогательного оборудования.xlsx',data_only=True)
    items=[r for r in catalog.active.iter_rows(min_row=3,values_only=True) if r[2]]
    assert len(items)==16
    ants=[]
    for r in rooms:
        if r['label_x_m']:
            ants.append(dict(room=r['room'],x=float(r['label_x_m']),y=float(r['label_y_m']),
                             basis='Проектная точка у метки помещения; не утверждённое место крепления'))
    # Additional proposed antennas for the large public zone (490.62 m²).
    ants.extend(dict(room='101',x=x,y=y,basis='Дополнительная проектная точка общественной зоны')
                for x,y in ((10,58),(25,58),(10,40)))
    head=V[0];input_file=DESIGN/'project-input.json'
    if input_file.exists():
        project_input=json.loads(input_file.read_text())
        ants=project_input['antennas'];head=tuple(project_input['head'])
        assert len(ants) in (32,48)
        groups=[[i for i,a in enumerate(ants) if a['zone']==z] for z in range(1,5)]
        assert all(len(g)==len(ants)//4 for g in groups)
    else:
        assert len(ants)==48
        available=set(range(len(ants)));groups=[[] for _ in range(4)]
        for z in range(4):
            take=sorted(available,key=lambda i:distance((ants[i]['x'],ants[i]['y']),ZONES[z]))[:12]
            groups[z]=take;available.difference_update(take)
        assert not available
    count=len(ants);per_zone=count//4;subgroups=per_zone//4
    trunk=[];subfeeds=[];drops=[]
    for z,ids in enumerate(groups):
        length,points=route(head,ZONES[z]);trunk.append(dict(id=f'T{z+1}',length=length,points=points))
        for g,(subset,hub) in enumerate(local_groups(ids,ants,ZONES[z])):
            length,points=route(ZONES[z],hub)
            subfeeds.append(dict(id=f'F{z+1}-{g+1}',length=length,points=points))
            for slot,i in enumerate(subset):
                a=ants[i];a['id']=f'A{z*per_zone+g*4+slot+1:02d}';a['zone']=z+1
                a['subgroup']=g+1;a['hub']=hub
                length,points=route(hub,(a['x'],a['y']))
                a['length78_m']=trunk[-1]['length']
                a['length12_m']=subfeeds[-1]['length']+length
                a['drop12_m']=length
                a['points']=points
                drops.append(dict(id=a['id'],length=length,points=points))
    ants.sort(key=lambda a:a['id'])
    for t in trunk+subfeeds:t['cable']='7/8'
    for t in drops:t['cable']='7/8' if t['length']>15 else '1/2'
    # Co-located devices require a physical connection; zero-length feeder is
    # not a purchasable item. Use the supplied 3 m factory jumper, per branch.
    for t in trunk+subfeeds+drops:
        if t['length']<1e-6:
            t['cable']='jumper';t['jumper_length_m']=3
            t['assumed_loss_db']=0.2  # additional loss, not a datasheet value
    # Supported improvement: lower attenuation cable for subfeeds and long drops.
    for a in ants:
        sub=next(t for t in subfeeds if t['id']==f'F{a["zone"]}-{a["subgroup"]}')
        drop=next(t for t in drops if t['id']==a['id'])
        a['length78_m']=trunk[a['zone']-1]['length']+sub['length']+(drop['length'] if drop['cable']=='7/8' else 0)
        a['length12_m']=drop['length'] if drop['cable']=='1/2' else 0
        a['additional_jumper_loss_db']=sum(t.get('assumed_loss_db',0) for t in (trunk[a['zone']-1],sub,drop))
    allroutes=trunk+subfeeds+drops
    alpha12={1800:10.09,2100:10.99,2600:11.84+(12.66-11.84)*2/3}
    alpha78={1800:5.21,2100:5.67,2600:6.39}
    # Numeric component losses are explicit estimates, not absent datasheet values.
    fixed=6+1+10*math.log10(per_zone)+1+0.8+1
    # All 4 PC221 outputs serve the four zones: 6 dB include the first division.
    # Per-zone tree: 2-way + 4-way for 32, 3-way + 4-way for baseline 48.
    # Excess loss .5 per stage is assumed, not a supplied datasheet value.
    rf=[]
    for a in ants:
        for f in (1800,2100,2600):
            cable=a['length78_m']*alpha78[f]/100+a['length12_m']*alpha12[f]/100
            loss=cable+fixed+a['additional_jumper_loss_db']
            prb={1800:100,2100:75,2600:50}[f]
            p=23-10*math.log10(2*prb)
            for d in (5,10,15,20):
                r=math.hypot(d,5.5);pl=20*math.log10(f)-27.55+25*math.log10(r)
                rf.append(dict(antenna=a['id'],frequency_mhz=f,d_horizontal_m=d,
                               cable_loss_db=cable,total_loss_db=loss,
                               rsrp_dbm=p-loss+3-pl))
    data=dict(status='Проектное решение с явно заданными допущениями; фактические KPI не установлены',
              head=list(head),topology=dict(zones=4,per_zone=per_zone,subgroups=subgroups,leaf_outputs=4),
              antennas=ants,trunks=trunk,subfeeds=subfeeds,drops=drops,
              fixed_loss_db=fixed,rf_points=rf,
              local_jumper_count=2*sum(t['cable']=='jumper' for t in allroutes),
              cable78_installed=2*sum(t['length'] for t in allroutes if t['cable']=='7/8'),
              cable12_installed=2*sum(t['length'] for t in allroutes if t['cable']=='1/2'))
    if input_file.exists() and project_input.get('zone_modes'):
        from route_design import construct
        data=construct(json.loads(input_file.read_text()))
        ants=data['antennas'];trunk=data['trunks'];subfeeds=data['subfeeds'];drops=data['drops']
        allroutes=trunk+subfeeds+drops;rf=data['rf_points'];fixed=data['fixed_loss_db']
    unequal=bool(data['topology'].get('zone_modes')) and any(v=='unequal' for v in data['topology']['zone_modes'].values())
    (DESIGN/'candidate.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    with (DESIGN/'antenna-schedule.csv').open('w',newline='') as stream:
        writer=csv.writer(stream,lineterminator='\n');writer.writerow(['ID','room','zone','x_m','y_m','path78_m','path12_m'])
        for a in ants:writer.writerow([a['id'],a['room'],a['zone'],a['x'],a['y'],a['length78_m'],a['length12_m']])

    wb=Workbook();ws=wb.active;ws.title='Спецификация'
    ws.append(['Категория оборудования','Наименование / модель','Основные характеристики','Количество','Единица измерения'])
    quantities={5:count,6:0,7:8,8:6,9:1+(8 if subgroups==2 else 0),
                10:8 if subgroups==3 else 0,11:8*subgroups,12:0,13:0,14:0,15:0,
                16:math.ceil(data['cable12_installed']*1.1),17:math.ceil(data['cable78_installed']*1.1),
                19:4*sum(t['cable']=='1/2' for t in allroutes),
                20:4*sum(t['cable']=='7/8' for t in allroutes),23:45+2*count+data['local_jumper_count']}
    characteristics={
        5:'Потолочная omni, MIMO; 800–2700 МГц; G=3 dBi; H=360°. Вертикальная диаграмма не предоставлена.',
        7:'Триплексер 1710–1880 / 1920–2170 / 2500–2690 МГц, одинарный; 4.3-10F; IP67. Insertion loss не дано.',
        8:'Гибрид 4×4, 8 портов; 790–2700 МГц; 6 дБ; 4.3-10F; IP65. Изоляция и допустимая мощность не даны.',
        9:'Делитель 2:1; 700–2700 МГц; 4.3-10F; IP65. Идеальное деление 3,01 дБ, excess loss не дано.',
        10:'Делитель 3:1; 700–2700 МГц; 4.3-10F; IP65. Идеальное деление 4,77 дБ, excess loss не дано.',
        11:'Делитель 4:1; 700–2700 МГц; 4.3-10F; IP65. Идеальное деление 6,02 дБ, excess loss не дано.',
        16:'1/2, 50 Ом по PDF LCF12-50J; 10,09 / 10,99 / 12,3867 дБ/100м при 1800/2100/2600 (последние две интерполированы). Пожарная модификация не подтверждена.',
        17:'7/8, 50 Ом по PDF LCF78-50JA-A0; 5,21 / 5,67 / 6,39 дБ/100м при 1800/2100/2600; допуск ±5%. Пожарная модификация не подтверждена.',
        19:'4.3-10 для фидера 1/2. Loss, PIM и конкретная модификация не предоставлены.',
        20:'4.3-10 для фидера 7/8. Loss, PIM и конкретная модификация не предоставлены.',
        23:'4.3-10 male / 4.3-10 male, 3 м. Собственное затухание и тип кабеля не предоставлены.',
    }
    for number,kind,name,unit in items:
        if quantities[number]:ws.append([kind,name,characteristics[number],quantities[number],unit])
    style(ws,{'A':20,'B':70,'C':65,'D':15,'E':15})
    catalogws=wb.create_sheet('Исходный перечень');catalogws.append(['п.п.','Тип','Название','Ед.'])
    for row in items:catalogws.append(row)
    style(catalogws,{'A':10,'B':15,'C':90,'D':10})
    status=wb.create_sheet('Статус');status.append(['Позиция','Обоснование / ограничение'])
    for row in [
        ('Проект','Расчётный вариант финала с явно указанными ограничениями; не комплект для закупки без проверки паспортов и условий монтажа'),
        (f'{count} антенн','Проектные точки выбраны из CAD-привязок и сравнения покрытия. Координаты, распределение и исходные IDs — в project-input.json. Помещение 89 не локализовано.'),
        ('Дерево на одну MIMO-ветвь','PC221: 4 выхода → 4 PC211 → 4 зоны. В каждой зоне PC252: два выхода напрямую на две антенны; третий через PC250 на две; четвёртый через PC252 на четыре. Доли мощности 1/4, 1/8, 1/16; 2+2+4=8 антенн.' if unequal else f'PC221: 4 выхода → 4 PC211 → 4 зоны. В каждой зоне {subgroups}-way делитель → {subgroups} PC252 4-way → {per_zone} антенн. Отдельного головного 4-way после гибрида нет.'),
        ('PC221','6: 3 диапазона × 2 MIMO-ветви. По три входа для операторов; четвёртый B3 для GSM МТС. Все четыре выхода используются. Неизвестные мощности других операторов не подставлены.'),
        ('PC250',f'{quantities[9]}: один делит DCS-пул на два гибрида B3'+('; восемь питают парные подгруппы, по одному на зону/ветвь.' if unequal else '; восемь делят четыре зоны двух MIMO-ветвей на две подгруппы.' if subgroups==2 else '.')),
        ('PC211','8: 4 группы × 2 MIMO-ветви, по одному объединению B3/B1/B7 на каждый головной фидер'),
        ('Фидеры','7/8 — все головные и подгрупповые участки и оконечные длиннее 15 м; 1/2 — короткие оконечные. Метраж схемы ×2 MIMO, затем +10% отдельного закупочного резерва. Правило 15 м — проектное решение, джамперы отдельно.'),
        ('Разъёмы','По два на каждый ненулевой изготовляемый участок фидера. Для связи с male/male джампером оконечный разъём фидера должен быть female; у делителя — male. Пол разъёмов 1/2 и 7/8 в перечне не задан, доступность модификаций не подтверждена. Интерфейсы БС и In06 также не указаны.'),
        (f'{45+2*count+data["local_jumper_count"]} джамперов',f'18 входов LTE + 1 вход GSM + 2 связи после PC250 + 24 связи PC221→PC211 + {2*count} антенных + {data["local_jumper_count"]} местных связей S→Q. При подключённом только МТС 12 входных связей зарезервированы. Порты БС и пригодность длины 3 м не подтверждены.'),
        ('Местные связи',f'{data["local_jumper_count"]} местных соединений: геометрическая длина 0 м означает соседние устройства; соединение выполнено джампером 3 м, по два на ID для MIMO. Добавлено 0,2 дБ на путь, собственное допущение. Монтажные фидеры и отдельные разъёмы для этих связей не считаются.'),
        ('GSM-интерфейс','Один общий RF-выход GSM с двумя TRX принят условно: объединение передатчиков внутри БС не подтверждено. При раздельных RF-выходах требуется дополнительное решение объединения, отсутствующее в исходных данных. Отдельные входы DCS двух других операторов не выделены.'),
        ('Неиспользуемые порты','У B1/B7 гибридов остаются 4 незадействованных входа, а до подключения других операторов ещё 12. Нужны согласованные 50-омные нагрузки: их нет в разрешённом перечне; это открытое несоответствие, не выдуманная позиция спецификации.'),
        ('Потери компонентов','Кроме 6 дБ PC221 и идеального деления паспортные потери не заданы. Использованы сценарные оценки, см. RF-лист.'),
        ('Пожарное исполнение','XLSX требует огнестойкую безгалогеновую оболочку; PDF описывают PE-варианты. Нужна допустимая модификация.'),
        ('ВК',f'Проектная координата {head}; существующая ВК в DWG не найдена. Выделение части 104.2 под аппаратную — собственное решение, не исходное назначение комнаты.' if input_file.exists() else 'Ввод в районе 118 — предложение, существующая ВК не установлена.'),
        ('Удалённое управление','В перечне нет подходящих управляемых модулей. Пассивная схема не подтверждает требование регулировки на удалённых модулях.'),
    ]:status.append(row)
    style(status,{'A':28,'B':120})
    routes=wb.create_sheet('Трассы');routes.append(['Участок','Тип кабеля','Ветвей','Геометрическая длина, м','Длина двух ветвей, м','Источник'])
    for series in (trunk,subfeeds,drops):
        for t in series:
            routes.append([t['id'],t['cable'],2,round(t['length'],4),round(2*t['length'],4),
                           'Соседние устройства: два заводских джампера по 3 м; не нулевой фидер' if t['cable']=='jumper' else 'Проектная аппроксимация CAD-лотков; без запаса'])
    style(routes,{'A':16,'B':18,'C':12,'D':25,'E':28,'F':80})
    radio=wb.create_sheet('RF и RSRP');radio.append(['Антенна','Частота МГц','Расстояние по горизонтали м','Потери кабеля дБ','Полные RF-потери дБ','RSRP P1 n=2.5 без стен дБм'])
    for row in rf:radio.append(list(row.values()))
    style(radio,{'A':15,'B':20,'C':30,'D':25,'E':30,'F':45})
    wb.save(EQUIP/'bill-of-materials.xlsx')

    worst=max(rf,key=lambda r:r['total_loss_db'])
    summary=dict(antennas=len(ants),trunk78_m=data['cable78_installed'],feed12_m=data['cable12_installed'],
                 fixed_loss_db=fixed,min_rf_loss_db=min(r['total_loss_db'] for r in rf),
                 max_rf_loss_db=worst['total_loss_db'],worst_antenna=worst['antenna'],
                 point20_b7_min=min(r['rsrp_dbm'] for r in rf if r['frequency_mhz']==2600 and r['d_horizontal_m']==20))
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
