#!/usr/bin/env python3
"""Six slides and a shared-layout PDF preview; no invented personal details."""
from pathlib import Path
import json
import math
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_AUTO_SIZE
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'presentation'
FONT_DIR=Path('/usr/share/fonts/truetype/dejavu')
for name,file in [('RadioSans','DejaVuSans.ttf'),('RadioBold','DejaVuSans-Bold.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(FONT_DIR/file)))

def wrap(text,font,size,width):
    lines=[]
    for paragraph in text.split('\n'):
        current=''
        for word in paragraph.split():
            candidate=(current+' '+word).strip()
            if current and pdfmetrics.stringWidth(candidate,font,size)>width:
                lines.append(current);current=word
            else:current=candidate
        lines.append(current)
    return lines

class Deck:
    def __init__(self):
        self.prs=Presentation();self.prs.slide_width=Inches(13.333);self.prs.slide_height=Inches(7.5)
        self.pdf=canvas.Canvas(str(OUT/'defense-preview.pdf'),pagesize=(13.333*72,7.5*72))
        self.pdf.setTitle('МТС Engineer Hack 2026 — Павел Абалаков')
        self.slide=None;self.index=0
    def rect(self,x,y,w,h,color):
        s=self.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h))
        s.fill.solid();s.fill.fore_color.rgb=RGBColor.from_string(color);s.line.fill.background()
        self.pdf.setFillColor('#'+color);self.pdf.rect(x*72,(7.5-y-h)*72,w*72,h*72,fill=1,stroke=0)
    def text(self,x,y,w,h,value,size=22,bold=False,color='17324D'):
        font='RadioBold' if bold else 'RadioSans';lines=wrap(value,font,size,w*72-2)
        lineheight=size*1.15
        assert len(lines)*lineheight<=h*72,(self.index,value,len(lines)*lineheight,h*72)
        t=self.slide.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h)).text_frame
        t.margin_left=t.margin_right=t.margin_top=t.margin_bottom=0;t.word_wrap=False;t.auto_size=MSO_AUTO_SIZE.NONE
        for i,line in enumerate(lines):
            p=t.paragraphs[0] if i==0 else t.add_paragraph();p.text=line
            p.font.name='DejaVu Sans';p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=RGBColor.from_string(color)
            p.space_after=Pt(0);p.space_before=Pt(0);p.line_spacing=Pt(lineheight)
            self.pdf.setFillColor('#'+color);self.pdf.setFont(font,size)
            self.pdf.drawString(x*72,(7.5-y)*72-size-i*lineheight,line)
    def image(self,path,x,y,w,h):
        iw,ih=Image.open(path).size;factor=min(w/iw,h/ih);dw,dh=iw*factor,ih*factor
        self.slide.shapes.add_picture(str(path),Inches(x+(w-dw)/2),Inches(y+(h-dh)/2),width=Inches(dw),height=Inches(dh))
        self.pdf.drawImage(ImageReader(str(path)),(x+(w-dw)/2)*72,(7.5-y-(h+dh)/2)*72,dw*72,dh*72)
    def new(self,title,notes):
        if self.slide:self.pdf.showPage()
        self.index+=1;self.slide=self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.rect(0,0,13.333,7.5,'F7F9FC');self.rect(0,0,.18,7.5,'E30611')
        self.text(.55,.35,12.0,.9,title,26,True)
        self.text(.55,7.05,11.8,.25,'МТС Engineer Hack 2026 · Радио · Расчётный вариант · 13.10.2026',9,color='536778')
        self.text(12.4,7.05,.35,.25,str(self.index),10)
        self.slide.notes_slide.notes_text_frame.text=notes
    def finish(self):
        self.prs.save(OUT/'defense.pptx');self.pdf.save()

def main():
    OUT.mkdir(exist_ok=True)
    data=json.loads((ROOT/'design/final/candidate.json').read_text())
    report=json.loads((ROOT/'design/final/coverage/coverage-report.json').read_text())
    profile=json.loads((OUT/'profile-input.json').read_text())
    bykey={(r['scenario'],r['frequency_mhz']):r for r in report['scenarios']}
    nominal=bykey[('P1_n2.5',2600)]['reference_percent_2100']
    adverse=bykey[('P1_extra_RF_3dB',2600)]['reference_percent_2100']
    joint=bykey[('P1_closed_gaps_geometry_uncertain_fail_RF3',2600)]['reference_percent_2100']
    total=data['cable78_installed']+data['cable12_installed']
    purchase78=math.ceil(data['cable78_installed']*1.1);purchase12=math.ceil(data['cable12_installed']*1.1)
    local_jumps=data['local_jumper_count'];jumpers=45+2*len(data['antennas'])+local_jumps
    routes=data['trunks']+data['subfeeds']+data['drops'];conn={c:4*sum(r['cable']==c for r in routes) for c in ('1/2','7/8')}
    worst=max(data['rf_points'],key=lambda r:r['total_loss_db'])
    pending=[k for k in ('role','contribution','interests') if not profile[k]]
    if not profile['course_confirmed']:pending.append('course_confirmed')
    scripts=[
        ('Самопрезентация',25,
         f'Меня зовут {profile["name"]}. Учусь в УрТИСИ по направлению «Инфокоммуникационные технологии и системы связи». '
         'В профиле указаны второе место на хакатоне связи 2025 года и проект Payment OCR. '
         f'Моя текущая роль: {profile["role"] or "[УКАЗАТЬ РОЛЬ]"}. '
         f'Личный вклад в проект: {profile["contribution"] or "[УКАЗАТЬ ВКЛАД]"}. '
         f'Профессиональные интересы: {profile["interests"] or "[УКАЗАТЬ ИНТЕРЕСЫ]"}.'),
        ('Изменение ёмкости',40,
         'На онлайн-этапе я считал 80 процентов прогнозных пользователей одновременно активными: это 288 пользователей и 2304 мегабита в секунду. '
         'Новые вводные разделяют состояние RRC Connected и наличие данных в буфере. Из 360 прогнозных пользователей получаются 126 RRC-подключений и 12,6 буферных пользователей. '
         'Округляю вверх до 13: спрос составляет 104 мегабита в секунду. Три несущие без агрегации обслуживают шесть, четыре и три пользователя. '
         'Выбираю один общий пул. Коэффициент пространственного перекоса внутри него равен единице; при сохранении прежнего правила получились бы два сектора. Запаса на четырнадцатого пользователя нет.'),
        ('Размещение и схема',55,
         'План построен по предоставленному DWG в исходном масштабе. После сравнения вариантов выбраны 32 двухпортовые In06 и четыре распределительные группы. '
         'Это один LTE-пул на каждом диапазоне, а не четыре независимые ячейки. Две MIMO-ветви проходят отдельно до двух портов каждой антенны. '
         'На каждой ветви гибриды объединяют операторов, триплексеры — диапазоны. В зоне две антенны подключены напрямую к PC252, две через PC250 и четыре через второй PC252. '
         'Доли мощности — четверть, восьмая и шестнадцатая. Это перераспределение при сохранении суммарной мощности. '
         'Существующая ВК не найдена: размещение головного узла в части 104.2 является моим проектным допущением. '
         'Помещение 89 не локализовано. Его площадь полностью учитывается как непокрытая. Исправлена геометрия четырёх спорных групп; неопределённость 114.2 сохранена.'),
        ('RSRP и чувствительность',55,
         f'Рассчитаны 384 сочетания антенны, диапазона и расстояния, а также карта с шагом 25 сантиметров. '
         'В модели учитываются кабели, делители, высота и пересечения стен. Пилот 23 дБм условно нормирован на CRS одного порта; определение мощности в задании неоднозначно. '
         f'На B7 номинальный результат составляет {nominal:.2f} процента от заданных 2100 квадратных метров. '
         f'При дополнительных трёх децибелах остаётся {adverse:.2f} процента. '
         f'При закрытых проёмах, исключении спорного контура и ещё трёх децибелах — {joint:.2f} процента. Запас достигнут в модели. '
         f'Худший отдельный путь на 20 метрах даёт {min(r["rsrp_dbm"] for r in data["rf_points"] if r["frequency_mhz"]==2600 and r["d_horizontal_m"]==20):.2f} дБм; площадь оценивается по всем антеннам. '
         'Это сценарный прогноз, а не измерения. RSRP не подтверждает SINR, RSRQ или скорость. Для DCS отдельно проверены условные мощности BCCH, но не внешний C/I.'),
        ('Спецификация',35,
         'Спецификация формируется из той же структуры, что схемы и трассы. В ней только позиции предоставленного перечня. '
         'Учтены 32 антенны, шесть гибридов, восемь триплексеров, девять двухвыходных и шестнадцать четырёхвыходных делителей. '
         f'Кабель с резервом: {purchase78} метров семь восьмых и {purchase12} метров одна вторая. '
         f'Метраж фидеров вырос примерно на {(total/1084.2026152168604-1)*100:.0f} процентов к предыдущему варианту. Это цена запаса. '
         f'Всего {jumpers} джамперов, включая 12 резервных входных и {local_jumps} местных. '
         'Для свободных портов нужны нагрузки, отсутствующие в перечне; пожарная модификация и исполнения разъёмов также не подтверждены.'),
        ('Решения и границы',30,
         'Три главных решения — общий пул с новой моделью спроса, восстановление контуров и неравномерное распределение мощности. Две MIMO-ветви сохранены. '
         'Числа согласованы и воспроизводимы. Номинальная модель и запас три децибела проходят; n=3 и другое определение пилота не проходят. '
         'Полное соответствие заданию не доказано: помеховые показатели неизвестны, пассивная схема не обеспечивает требуемое удалённое регулирование, часть комплектации не подтверждена. '
         'Эти ограничения отражены в документах, а не скрыты за проходящим номинальным результатом.')]
    assert sum(s[1] for s in scripts)==240
    deck=Deck()
    deck.new(profile['name']+' · Indoor Radio Design',scripts[0][2])
    deck.text(.65,1.55,11.8,.9,profile['education']+' · Инфокоммуникационные технологии и системы связи',23,True)
    deck.text(.65,2.65,11.8,.8,profile['profile_facts'],21)
    deck.text(.65,3.8,11.8,.7,'Проект: '+profile['project'],24)
    personal='\n'.join(['Роль: '+(profile['role'] or '[заполнить]'),
                        'Вклад: '+(profile['contribution'] or '[заполнить]'),
                        'Интересы: '+(profile['interests'] or '[заполнить]')])
    deck.rect(.6,4.8,12.1,1.8,'FFF0D8' if pending else 'EAF2F8')
    deck.text(.85,5.0,11.5,1.4,personal,19)
    deck.new('Новые вводные: 288 → 13 пользователей с данными',scripts[1][2])
    deck.text(.65,1.55,12,1.0,'360 × 35% RRC × 10% buffer = 12,6 → 13 UE',27,True)
    deck.rect(.65,2.75,5.8,1.3,'EAF2F8');deck.rect(6.85,2.75,5.8,1.3,'EAF2F8')
    deck.text(.9,3.0,5.3,.9,'104 Мбит/с вместо 2304',25,True)
    deck.text(7.1,3.0,5.3,.9,'6 + 4 + 3 UE без CA',25,True)
    deck.text(.65,4.6,12,.9,'Один общий пул B3/B1/B7: k(1)=1',25,True)
    deck.text(.65,5.65,12,.95,'Прежнее правило k=1,10 → 2 сектора.\nЗапаса на 14-го UE без CA нет.',22)
    deck.new('32 антенны · 4 группы · 2 независимые MIMO-ветви',scripts[2][2])
    deck.image(ROOT/'design/final/verification/final-layout.png',.4,1.3,4.4,5.6)
    deck.text(5.1,1.6,7.55,1.0,'Z1–Z4 — распределение одного пула',24,True)
    deck.text(5.1,2.8,7.55,1.45,'PC221 → PC211 → PC252\nВ зоне: 2 напрямую + 2 через PC250 + 4 через PC252',20)
    deck.text(5.1,4.35,7.55,1.0,'ВК в части 104.2 — проектное допущение',22)
    deck.text(5.1,5.6,7.55,1.0,f'Помещение 89 считается непокрытым.\nФидеры: {total:.0f} м; +{(total/1084.2026152168604-1)*100:.1f}% к прежней схеме.',20)
    deck.new('RSRP: запас 3 дБ проверен в модели P1',scripts[3][2])
    deck.image(ROOT/'design/final/coverage/rsrp-2600-walls.png',.35,1.25,4.5,5.65)
    deck.text(5.1,1.5,7.6,.8,f'B7: {nominal:.2f}% от 2100 м²',29,True)
    deck.text(5.1,2.6,7.6,.8,f'+3 дБ RF-потерь → {adverse:.2f}%',26,True,color='227958')
    deck.text(5.1,3.8,7.6,1.1,f'Проёмы / спорный контур / +3 дБ: {joint:.2f}%\n36 сценариев; {report["receiver_cells"]} ячейки карты',20)
    deck.text(5.1,5.1,7.6,1.2,'P1: 23 дБм — условная сумма CRS на порту.\nSINR / RSRQ и фактические KPI не подтверждены.',20)
    deck.new('Спецификация связана со схемами и трассами',scripts[4][2])
    deck.text(.65,1.55,12,1.2,'32 In06 · 6 PC221 · 8 PC211\n9 PC250 · 16 PC252',26,True)
    deck.text(.65,3.0,12,.85,f'Закупочный метраж: 7/8 — {purchase78} м; 1/2 — {purchase12} м',25,True)
    deck.text(.65,4.05,12,1.0,f'{jumpers} джамперов: 12 резервных; {local_jumps} местных\nРазъёмы: 1/2 — {conn["1/2"]}; 7/8 — {conn["7/8"]}',23)
    deck.text(.65,5.55,12,.95,'Открытые вопросы комплектации: нагрузки, пол разъёмов,\nинтерфейс In06 / БС, пожарное исполнение.',21,color='B22C35')
    deck.new('Три решения и пределы доказанного результата',scripts[5][2])
    deck.text(.65,1.55,12,1.1,'1. Общий пул и последовательные доли RRC / buffer\n2. Проверка контуров по архитектуре\n3. Неравномерное деление мощности; две MIMO-ветви',21,True)
    deck.rect(.6,3.45,12.1,2.8,'FFF0D8')
    deck.text(.85,3.7,11.6,2.2,'P1 и запас 3 дБ проходят; n=3 и нормировка P2 — нет.\nRSRQ / SINR / C/I / UL не подтверждены.\nПассивная схема не выполняет удалённую регулировку.\nПолное соответствие ТЗ не установлено.',21)
    deck.finish()
    wordcount=sum(len(s[2].split()) for s in scripts)
    text=['# Выступление на четыре минуты\n\nПлановый тайминг 240 секунд. '+
          f'Текст содержит {wordcount} слов; тайминг следует проверить реальной репетицией. '
          'Третьекурсность и личные поля не подтверждены пользователем; квадратные поля не читать со сцены.\n']
    for i,(title,seconds,speech) in enumerate(scripts,1):text.append(f'## Слайд {i}. {title} — {seconds} секунд\n\n{speech}\n')
    text.append('## Репетиция\n\nПервый проход — объяснить смысл каждого коэффициента без текста. Второй — прочитать с таймером; '
                'третий — выступить по слайдам. Если превышены четыре минуты, сокращать пояснения, сохраняя числа и ограничения. '
                'Плановый тайминг не является выполненной репетицией пользователя.\n')
    (OUT/'speaker-script.md').write_text('\n'.join(text))
    (OUT/'presentation-status.json').write_text(json.dumps(dict(slides=6,planned_seconds=240,word_count=wordcount,
            pending_profile_fields=pending,official_template_available=False,personal_rehearsal_done=False),ensure_ascii=False,indent=2)+'\n')
    print(f'Presentation: 6 slides, {wordcount} words, 240 seconds planned; pending fields: {pending}')

if __name__=='__main__':main()
