#!/usr/bin/env python3
"""Update KPI and defense facts from the selected calculation."""
from pathlib import Path
import hashlib
import json
import math
import re

ROOT=Path(__file__).resolve().parents[2]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def number(value,places=2):return f'{value:.{places}f}'.replace('.',',')
def update(path,transform):
    p=ROOT/path;p.write_text(transform(p.read_text()))

def main():
    d=json.loads((ROOT/'design/final/candidate.json').read_text())
    c=json.loads((ROOT/'design/final/coverage/coverage-report.json').read_text())
    e=json.loads((ROOT/'design/final/verification/engineering-review.json').read_text())
    control=json.loads((ROOT/'design/final/coverage/geometry-control.json').read_text())
    fp=digest(ROOT/'design/final/candidate.json')
    assert fp==c['design_fingerprint']==e['design_fingerprint']==control['design_fingerprint']
    shares={(v['scenario'],v['frequency_mhz']):v['reference_percent_2100'] for v in c['scenarios']}
    total=d['cable78_installed']+d['cable12_installed']
    genders=e['connector_genders_required']
    local='/'.join(r['id'] for r in d['trunks']+d['subfeeds']+d['drops'] if r['cable']=='jumper')
    fmt=lambda scenario:'/'.join(number(shares[scenario,f]) for f in (1800,2100,2600))+'%'
    rows={
      'RSRP >−90 на 95%':f'| RSRP >−90 на 95% | Проходит в условной P1 | Номинал B3/B1/B7 {fmt("P1_n2.5")}; B7 +3 дБ {number(shares["P1_extra_RF_3dB",2600])}%; измеренный KPI не установлен |',
      'Закрытые проёмы / спорный контур / +3 дБ':f'| Закрытые проёмы / спорный контур / +3 дБ | Проходит P1 | B3/B1/B7 {fmt("P1_closed_gaps_geometry_uncertain_fail_RF3")}; знаменатель 2100 м² |',
      'n=3 / P2':f'| n=3 | Проходит во всех диапазонах P1 | B3/B1/B7 {fmt("P1_n3")}; с закрытыми проёмами {fmt("P1_n3_closed_gaps")} |\n| P2 | Не проходит 95% | B3/B1/B7 {fmt("P2_carrier23")}; нормировка пилота остаётся неоднозначной |',
      'n=3':f'| n=3 | Проходит во всех диапазонах P1 | B3/B1/B7 {fmt("P1_n3")}; с закрытыми проёмами {fmt("P1_n3_closed_gaps")} |',
      'P2':f'| P2 | Не проходит 95% | B3/B1/B7 {fmt("P2_carrier23")}; нормировка пилота остаётся неоднозначной |',
      'Худшая ветвь 20 м без стен':f'| Худшая ветвь 20 м без стен | Ниже −90 отдельным путём | {number(min(r["rsrp_dbm"] for r in d["rf_points"] if r["frequency_mhz"]==2600 and r["d_horizontal_m"]==20))} дБм B7; площадь оценивается по всем антеннам |',
      'XLSX спецификация':f'| XLSX спецификация | Обновлена по принятому варианту | {e["total_jumper_count"]} джамперов, {sum(genders["1/2"].values())}/{sum(genders["7/8"].values())} разъёма; закупочно {math.ceil(d["cable78_installed"]*1.1)} м 7/8 и {math.ceil(d["cable12_installed"]*1.1)} м 1/2; {len(c["scenarios"])} сценариев |',
      'DCS RxLev >−85 на 95%':f'| DCS RxLev >−85 на 95% | Условная карта рассчитана | {number(e["dcs_scenarios"][0]["reference_percent_2100"])}% при 40 дБм BCCH/TRX, n=2,5; рабочая мощность и измерения не заданы |'}
    quality=json.loads((ROOT/'design/final/quality/quality-report.json').read_text())
    assert quality['design_fingerprint']==fp and quality['area_model_sha256']==c['area_model_sha256']
    base=[r for r in quality['lte_results'] if r['scenario']=='L2']
    rq='/'.join(number(r['rsrq_gt_minus12_percent']) for r in base)
    snr=lambda key:'/'.join(number(r[key]) for r in base)
    dc=next(r for r in quality['dcs_results'] if r['bcch_dbm']==40 and r['interference_dbm_200khz']==-70)
    rows['RSRQ >−12 на 80%']=f'| RSRQ >−12 на 80% | Проверено сценарно | L2: {rq}% B3/B1/B7; два TX-порта, β=0,5, ρ=0,8, NF=7 дБ, I=−115 дБм/15 кГц; при β=1 критерий не проходит |'
    rows['SINR ≥17/7/1 на 40/80/95%']=f'| SINR ≥17/7/1 на 40/80/95% | Проверено сценарно | L2: ≥17 — {snr("sinr_ge17_percent")}; ≥7 — {snr("sinr_ge7_percent")}; ≥1 — {snr("sinr_ge1_percent")}; идеальное разделение потоков |'
    rows['DCS C/I >20 на 95%']=f'| DCS C/I >20 на 95% | Проверено сценарно | {number(dc["ci_gt20_percent"])}% при BCCH 40 дБм и I=−70 дБм/200 кГц; для 95% требуется I<−65,94 дБм; ARFCN не задан |'
    presentation=json.loads((ROOT/'presentation/presentation-status.json').read_text())
    rows['Презентация']=(f'| Презентация | Техническая и личная части заполнены | '
                          f'6 слайдов, {presentation["word_count"]} слов, план 240 секунд; '
                          'требуются открытие PPTX на компьютере защиты и реальная репетиция |')
    if presentation['pending_profile_fields']:
        rows['Презентация']='| Презентация | Требуются личные сведения | Заполнить profile-input.json и пересобрать пакет |'
    def kpi(text):
        return ('\n'.join(rows.get(line.split('|')[1].strip(),line) if line.startswith('|') and len(line.split('|'))>2 else line
                         for line in text.splitlines())+'\n').replace('Статус на 13.10.2026','Статус на 14.10.2026').replace('фактические KPI и полное соответствие ТЗ не установлены', 'качество SINR/RSRQ/C/I также проверено сценарно; полное соответствие ТЗ не установлено')
    update('docs/final/kpi-checklist.md',kpi)
    update('docs/final/assumptions.md',lambda t:re.sub(r'^\| A19 \|.*$',
        f'| A19 | Местные связи {local}: джампер 3 м, 0,2 дБ на путь; {d["local_jumper_count"]} физических связи | Собственное решение принятого варианта n=3 | Нулевые фидеры не закупаются; потери джампера оценочные |',t,flags=re.M)
        .replace('это не новый KPI задания и не подтверждение P2, n=3, помеховых показателей или измерений',
                 'это не новый KPI задания; n=3 проверен отдельно, P2 и помеховые показатели остаются ограничениями'))
    def answer(heading,text):
        update('presentation/jury-questions.md',lambda t:re.sub(
            r'(## '+re.escape(heading)+r'\n\n).*?(?=\n## |\Z)',
            lambda m:m.group(1)+text+'\n',t,flags=re.S))
    answer('Почему 32 антенны, а не 48?',
           'В принятом проекте 32 In06 и четыре распределительные группы с двумя независимыми MIMO-ветвями. '
           'Две антенны зоны получают 1/4, две — 1/8, четыре — 1/16 мощности зонального входа. '
           'Это расчётный вариант, проверенный на покрытие; глобальный минимум числа антенн не доказан. '
           f'Установленный коаксиал двух ветвей — {number(total)} м; закупочный запас 10% добавляется отдельно.')
    answer('Насколько надёжен расчётный результат?',
           f'Номинал B7 — {number(shares["P1_n2.5",2600])}%, n=3 — {number(shares["P1_n3",2600])}%, '
           f'n=3 с закрытыми проёмами — {number(shares["P1_n3_closed_gaps",2600])}%, +3 дБ — {number(shares["P1_extra_RF_3dB",2600])}%. '
           f'Совместный сценарий при n=2,5: закрытые проёмы, 114.2 как непрошедшее и +3 дБ — {number(shares["P1_closed_gaps_geometry_uncertain_fail_RF3",2600])}%. '
           'n=3 и +3 дБ проверены отдельно; их одновременное сочетание не проверялось. '
           f'P2 — {number(shares["P2_carrier23",2600])}%, ниже 95%. Нормировка пилота остаётся условной; SINR/RSRQ/C/I рассчитаны для явных сценариев. Фактические параметры помех и приёмника не заданы.')
    answer('Почему виртуальные стыки не стали стенами?',
           'Короткие стыки ≤0,25 м соединяют чертёжные границы A-AREA и стеновые контуры для восстановления площади. '
           'Они не доказывают материал на луче, поэтому дополнительные 15 дБ не добавляются. '
           f'При пределе 0,15 м и сетке 0,5 м B7 +3 дБ — {number(control["scores"]["reserve3"])}%, '
           f'закрытые проёмы +3 дБ — {number(control["scores"]["closed_reserve3"])}%. '
           'Это контроль текущего проекта; 114.2 остаётся спорным, 89 не локализовано.')
    update('docs/final/assumptions.md',lambda t:re.sub(r'^\| A11 \|.*$',
           '| A11 | 32 In06, 4 группы фидеров: 2 непосредственные + 2 парные + 4 четверные антенны | Проектное решение | '
           'Точки, классы мощности и S-узлы заданы в design/final/project-input.json; монтажная пригодность не подтверждена |',t,flags=re.M))
    status=ROOT/'presentation/presentation-status.json'
    if status.exists():
        words=json.loads(status.read_text())['word_count']
        update('presentation/README.md',lambda t:re.sub(r'\d+ слов, план',f'{words} слов, план',t))
    print('Updated current KPI and defense facts.')

if __name__=='__main__':main()
