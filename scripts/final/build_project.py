#!/usr/bin/env python3
"""Build a transparent CAD-based candidate; unresolved inputs are never certified."""
import csv
import heapq
import json
import math
from itertools import combinations
from functools import lru_cache
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

ROOT=Path(__file__).resolve().parents[2]
DESIGN=ROOT/'design/final'
FINAL=ROOT/'docs/final'
EQUIP=ROOT/'equipment'
PRES=ROOT/'presentation'

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
    for p in (DESIGN,EQUIP,PRES):p.mkdir(parents=True,exist_ok=True)
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
    # Supported improvement: lower attenuation cable for subfeeds and long drops.
    for a in ants:
        sub=next(t for t in subfeeds if t['id']==f'F{a["zone"]}-{a["subgroup"]}')
        drop=next(t for t in drops if t['id']==a['id'])
        a['length78_m']=trunk[a['zone']-1]['length']+sub['length']+(drop['length'] if drop['cable']=='7/8' else 0)
        a['length12_m']=drop['length'] if drop['cable']=='1/2' else 0
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
            loss=cable+fixed
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
              cable78_installed=2*sum(t['length'] for t in allroutes if t['cable']=='7/8'),
              cable12_installed=2*sum(t['length'] for t in allroutes if t['cable']=='1/2'))
    (DESIGN/'candidate.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    with (DESIGN/'antenna-schedule.csv').open('w',newline='') as stream:
        writer=csv.writer(stream,lineterminator='\n');writer.writerow(['ID','room','zone','x_m','y_m','path78_m','path12_m'])
        for a in ants:writer.writerow([a['id'],a['room'],a['zone'],a['x'],a['y'],a['length78_m'],a['length12_m']])

    fig,ax=plt.subplots(figsize=(10,16))
    arch=[e['points'] for e in geom['lines'] if not any(v in e['layer'] for v in ('CABL','AREA'))]
    ax.add_collection(LineCollection(arch,colors='#929292',linewidths=.45))
    ax.add_collection(LineCollection([[V[a],V[b]] for a,b in EDGES],colors='#1676b5',linewidths=2))
    colors=['#bc3f46','#22846d','#ad701e','#774b9d']
    for a in ants:
        color=colors[a['zone']-1]
        ax.plot(*zip(*a['points']),color=color,lw=.7,alpha=.8)
        ax.scatter(a['x'],a['y'],s=30,color=color,zorder=5)
        ax.text(a['x']+.25,a['y']+.3,a['id'],fontsize=6,color=color)
    for i,p in enumerate(ZONES):
        ax.scatter(*p,marker='s',s=65,c=colors[i]);ax.text(p[0]+.4,p[1],f'Z{i+1}: {per_zone} антенн',fontsize=7)
    ax.scatter(*head,marker='*',s=160,c='#14293e');ax.text(head[0]-5,head[1]+1,'Проектная ВК',fontsize=8)
    ax.set_xlim(-3,40);ax.set_ylim(-3,66);ax.set_aspect('equal');ax.grid(alpha=.12)
    ax.set_xlabel('CAD X, м');ax.set_ylabel('CAD Y, м')
    ax.set_title(f'Проект: 1 LTE-пул + 1 DCS-пул, {count} In06\nЧетыре группы фидеров — не четыре LTE-сектора',fontsize=11)
    fig.savefig(DESIGN/'candidate-layout.png',dpi=180,bbox_inches='tight')
    fig.savefig(DESIGN/'candidate-layout.pdf',bbox_inches='tight');plt.close(fig)

    # Diagnostic field only: no wall geometry, no area mask, no KPI percentage.
    xs=np.arange(0,38,.5);ys=np.arange(0,64,.5);xx,yy=np.meshgrid(xs,ys)
    best=np.full(xx.shape,-np.inf)
    for a in ants:
        loss=next(r['total_loss_db'] for r in rf if r['antenna']==a['id'] and r['frequency_mhz']==2600)
        rr=np.sqrt((xx-a['x'])**2+(yy-a['y'])**2+5.5**2)
        value=3-loss+3-(20*np.log10(2600)-27.55+25*np.log10(rr))
        best=np.maximum(best,value)
    fig,ax=plt.subplots(figsize=(9,13))
    field=ax.pcolormesh(xx,yy,best,cmap='RdYlGn',vmin=-105,vmax=-70,shading='auto')
    ax.add_collection(LineCollection(arch,colors='#222222',linewidths=.3))
    ax.set_aspect('equal');ax.set_xlim(-1,38);ax.set_ylim(-1,64)
    ax.set_title('Диагностическое поле B7, P1, n=2,5\nБез стен и маски площади; выполнение KPI не установлено',fontsize=11)
    ax.set_xlabel('CAD X, м');ax.set_ylabel('CAD Y, м');fig.colorbar(field,ax=ax,label='RSRP от сильнейшей антенны, дБм')
    fig.savefig(DESIGN/'rsrp-b7-no-walls.png',dpi=160,bbox_inches='tight');plt.close(fig)

    wb=Workbook();ws=wb.active;ws.title='Спецификация'
    ws.append(['Категория оборудования','Наименование / модель','Основные характеристики','Количество','Единица измерения'])
    quantities={5:count,6:0,7:8,8:6,9:1+(8 if subgroups==2 else 0),
                10:8 if subgroups==3 else 0,11:8*subgroups,12:0,13:0,14:0,15:0,
                16:math.ceil(data['cable12_installed']*1.1),17:math.ceil(data['cable78_installed']*1.1),
                19:4*sum(t['cable']=='1/2' for t in allroutes),
                20:4*sum(t['cable']=='7/8' for t in allroutes),23:45+2*count}
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
        ('Проект','Рабочий кандидат, не закупочная спецификация и не подтверждённый проект'),
        (f'{count} антенн','Проектные точки выбраны из CAD-привязок и сравнения покрытия. Координаты, распределение и исходные IDs — в project-input.json. Помещение 89 не локализовано.'),
        ('Дерево на одну MIMO-ветвь',f'PC221: 4 выхода → 4 PC211 → 4 зоны. В каждой зоне {subgroups}-way делитель → {subgroups} PC252 4-way → {per_zone} антенн. Отдельного головного 4-way после гибрида нет.'),
        ('PC221','6: 3 диапазона × 2 MIMO-ветви. По три входа для операторов; четвёртый B3 для GSM МТС. Все четыре выхода используются. Неизвестные мощности других операторов не подставлены.'),
        ('PC250',f'{quantities[9]}: один делит DCS-пул на два гибрида B3'+('; восемь делят четыре зоны двух MIMO-ветвей на две подгруппы.' if subgroups==2 else '.')),
        ('PC211','8: 4 группы × 2 MIMO-ветви, по одному объединению B3/B1/B7 на каждый головной фидер'),
        ('Фидеры','7/8 — все головные и подгрупповые участки и оконечные длиннее 15 м; 1/2 — короткие оконечные. Метраж схемы ×2 MIMO, затем +10% отдельного закупочного резерва. Правило 15 м — проектное решение, джамперы отдельно.'),
        ('Разъёмы','По два на каждый изготовляемый участок фидера; антенны/устройства/джамперы — 4.3-10, интерфейсы БС не подтверждены'),
        (f'{45+2*count} джамперов',f'18 входов LTE + 1 вход GSM + 2 связи после PC250 + 24 связи PC221→PC211 + {2*count} антенных. При подключённом только МТС 12 входных связей зарезервированы. Порты БС и пригодность длины 3 м не подтверждены.'),
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
            routes.append([t['id'],t['cable'],2,round(t['length'],4),round(2*t['length'],4),'Проектная аппроксимация CAD-лотков; без запаса'])
    style(routes,{'A':16,'B':18,'C':12,'D':25,'E':28,'F':80})
    radio=wb.create_sheet('RF и RSRP');radio.append(['Антенна','Частота МГц','Расстояние по горизонтали м','Потери кабеля дБ','Полные RF-потери дБ','RSRP P1 n=2.5 без стен дБм'])
    for row in rf:radio.append(list(row.values()))
    style(radio,{'A':15,'B':20,'C':30,'D':25,'E':30,'F':45})
    wb.save(EQUIP/'bill-of-materials-draft.xlsx')

    prs=Presentation();prs.slide_width=Inches(13.333);prs.slide_height=Inches(7.5)
    def slide(title,lines,image=None,notes=''):
        s=prs.slides.add_slide(prs.slide_layouts[6])
        bg=s.background.fill;bg.solid();bg.fore_color.rgb=RGBColor.from_string('F7F9FC')
        box=s.shapes.add_textbox(Inches(.6),Inches(.35),Inches(12.1),Inches(.75)).text_frame
        p=box.paragraphs[0];p.text=title;p.font.size=Pt(28);p.font.bold=True;p.font.color.rgb=RGBColor.from_string('17324D')
        width=5.4 if image else 11.9
        frame=s.shapes.add_textbox(Inches(.7),Inches(1.4),Inches(width),Inches(5.5)).text_frame
        frame.word_wrap=True
        for i,line in enumerate(lines):
            p=frame.paragraphs[0] if i==0 else frame.add_paragraph();p.text=line;p.font.size=Pt(20);p.space_after=Pt(18)
        if image:s.shapes.add_picture(str(image),Inches(7.4),Inches(1.15),height=Inches(5.95))
        s.notes_slide.notes_text_frame.text=notes
    slide('Павел Абалаков · Indoor Radio Design',[
        'УрТИСИ · третий курс',
        '11.03.02 «Инфокоммуникационные технологии и системы связи»',
        'II место: Всероссийский хакатон связи, 2025',
        'Проект: Svyaz Hack Payment OCR',
        '[Дополнить: текущая роль и профессиональные интересы]'],
        notes='Источник: https://github.com/abalakovpa/abalakovpa, прочитан 12.10.2026. Факты из профиля; актуальность третьего курса подтвердить. 25 секунд.')
    slide('Новые вводные меняют модель спроса',[
        '360 прогнозных 4G × 35% RRC × 10% buffer = 12,6 → 13 UE',
        'DL: 13 × 8 = 104 Мбит/с вместо 2304',
        'B3/B1/B7: 6 + 4 + 3 = 13 UE без CA',
        'Один общий пул — кандидат; прежнее правило k=1,10 даёт два',
        'Распределение антенн не создаёт новые секторы'],notes='45 секунд. Объяснить изменение k(1)=1: пространственный перекос внутри одного пула не повышает суммарный спрос. Не заявлять запас на временные пики.')
    slide('Проект на фактической CAD-подложке',[
        '46 помещений, итог экспликации 2097,06 м²',
        f'{count} In06: схема после расчётного сравнения',
        '4 группы фидеров, 2 независимые MIMO-ветви',
        'Проектная ВК: часть 104.2; собственное допущение',
        'Помещение 89 ещё не локализовано'],DESIGN/'candidate-layout.png',notes='50 секунд. План — кандидат, а не утверждённое размещение. Точки привязаны к меткам помещений. Ограничения проговорить.')
    worst=max(rf,key=lambda r:r['total_loss_db'])
    slide('RSRP: расчёт и существенные ограничения',[
        'Контрольные точки: 5 / 10 / 15 / 20 м',
        'Пилот 23 дБм: несколько возможных нормировок',
        f'Худшая ветвь кандидата: {worst["total_loss_db"]:.1f} дБ RF-потерь',
        'Потери стен: 15 дБ; колонн и фасада: 30 дБ',
        'Покрытие со стенами: отдельный сценарный отчёт'],notes='45 секунд. P1 — условное суммирование мощности 2N_PRB CRS-поднесущих на одном порту; отсутствует определение в задании. Расчёт n=2.5 без калибровки. Не выдавать уровни за измерения.')
    slide('Спецификация связана с деревом DAS',[
        'Только позиции из предоставленного перечня',
        f'{count} антенн; {quantities[11]} PC252; {quantities[10]} PC251; 8 PC211; 6 PC221; {quantities[9]} PC250',
        f'Фидеры без резерва: 1/2 — {data["cable12_installed"]:.1f} м; 7/8 — {data["cable78_installed"]:.1f} м',
        'В закупочный метраж добавлено 10% отдельно',
        'Пожарная модификация и component losses требуют уточнения'],notes='40 секунд. Количества проекта условны; PASсивная схема не выполняет буквальное требование управляемых удалённых модулей. Не считать комплект закупочным.')
    slide('Три решения и контроль готовности',[
        'Один общий LTE-пул: сохранение ёмкости без собственных межсекторных помех',
        'Два раздельных MIMO-тракта до каждого In06',
        'Трассы и спецификация рассчитываются из одной структуры',
        'До сдачи: ВК, помещение 89, пилот, параметры компонентов, карты KPI',
        'Рабочий проект. Полное соответствие ТЗ пока не заявляется.'],notes='35 секунд; суммарно 240 секунд. Это черновик защиты со статусом работ, не окончательная презентация выполненного проекта.')
    prs.save(PRES/'defense-draft.pptx')
    summary=dict(antennas=len(ants),trunk78_m=data['cable78_installed'],feed12_m=data['cable12_installed'],
                 fixed_loss_db=fixed,min_rf_loss_db=min(r['total_loss_db'] for r in rf),
                 max_rf_loss_db=worst['total_loss_db'],worst_antenna=worst['antenna'],
                 point20_b7_min=min(r['rsrp_dbm'] for r in rf if r['frequency_mhz']==2600 and r['d_horizontal_m']==20))
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
