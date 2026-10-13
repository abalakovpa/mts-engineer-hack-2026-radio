#!/usr/bin/env python3
"""Keep status documents and adoption provenance aligned with exported inputs."""
from pathlib import Path
import argparse
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
    parser=argparse.ArgumentParser();parser.add_argument('--finalize',action='store_true');args=parser.parse_args()
    d=json.loads((ROOT/'design/final/candidate.json').read_text())
    c=json.loads((ROOT/'design/final/coverage/coverage-report.json').read_text())
    e=json.loads((ROOT/'design/final/verification/engineering-review.json').read_text())
    n3=ROOT/'design/final/n3';research=json.loads((n3/'verification.json').read_text())
    previous=json.loads((n3/'baseline-candidate.json').read_text())
    fp=digest(ROOT/'design/final/candidate.json')
    assert fp==digest(n3/'best32-candidate.json')==c['design_fingerprint']==e['design_fingerprint']
    shares={(v['scenario'],v['frequency_mhz']):v['reference_percent_2100'] for v in c['scenarios']}
    for f in (1800,2100,2600):
        for scenario in ('P1_n3','P1_n3_closed_gaps','P1_closed_gaps_geometry_uncertain_fail_RF3'):
            assert shares[scenario,f]>=95
    total=d['cable78_installed']+d['cable12_installed'];old_total=previous['cable78_installed']+previous['cable12_installed']
    genders=e['connector_genders_required'];local='/'.join(r['id'] for r in d['trunks']+d['subfeeds']+d['drops'] if r['cable']=='jumper')
    fmt=lambda scenario:'/'.join(number(shares[scenario,f]) for f in (1800,2100,2600))+'%'
    adopted=dict(date='2026-10-13',selected_variant='n3/best32',selected_candidate_sha256=fp,
        selected_input_sha256=digest(ROOT/'design/final/project-input.json'),
        geometry_sha256=c['area_model_sha256'],baseline_candidate_sha256=digest(n3/'baseline-candidate.json'),
        goal_verified_all_bands=True,full_kpi_compliance=False,artifacts_exported=args.finalize)
    if args.finalize:
        manifest=json.loads((ROOT/'submission/manifest.json').read_text());assert manifest['design_fingerprint']==fp
        for item in manifest['files']:assert digest(ROOT/'submission/final'/item['name'])==item['sha256']
        adopted['archive_sha256']=digest(ROOT/'submission/mts-radio-final.zip')
        assert adopted['archive_sha256']==manifest['archive']['sha256']
    (n3/'primary-adoption.json').write_text(json.dumps(adopted,ensure_ascii=False,indent=2)+'\n')
    research.update(adopted_into_submission=args.finalize,current_selected_design_sha256=fp,
                    source_hash_context='Исходные пути и hashes относятся к основной версии 50974e2 до принятия; см. frozen baseline и primary-adoption.json')
    (n3/'verification.json').write_text(json.dumps(research,ensure_ascii=False,indent=2)+'\n')
    rows={
      'RSRP >−90 на 95%':f'| RSRP >−90 на 95% | Проходит в условной P1 | Номинал B3/B1/B7 {fmt("P1_n2.5")}; B7 +3 дБ {number(shares["P1_extra_RF_3dB",2600])}%; измеренный KPI не установлен |',
      'Закрытые проёмы / спорный контур / +3 дБ':f'| Закрытые проёмы / спорный контур / +3 дБ | Проходит P1 | B3/B1/B7 {fmt("P1_closed_gaps_geometry_uncertain_fail_RF3")}; знаменатель 2100 м² |',
      'n=3 / P2':f'| n=3 | Проходит во всех диапазонах P1 | B3/B1/B7 {fmt("P1_n3")}; с закрытыми проёмами {fmt("P1_n3_closed_gaps")} |\n| P2 | Не проходит 95% | B3/B1/B7 {fmt("P2_carrier23")}; нормировка пилота остаётся неоднозначной |',
      'n=3':f'| n=3 | Проходит во всех диапазонах P1 | B3/B1/B7 {fmt("P1_n3")}; с закрытыми проёмами {fmt("P1_n3_closed_gaps")} |',
      'P2':f'| P2 | Не проходит 95% | B3/B1/B7 {fmt("P2_carrier23")}; нормировка пилота остаётся неоднозначной |',
      'Худшая ветвь 20 м без стен':f'| Худшая ветвь 20 м без стен | Ниже −90 отдельным путём | {number(min(r["rsrp_dbm"] for r in d["rf_points"] if r["frequency_mhz"]==2600 and r["d_horizontal_m"]==20))} дБм B7; площадь оценивается по всем антеннам |',
      'XLSX спецификация':f'| XLSX спецификация | Обновлена по принятому варианту | {e["total_jumper_count"]} джамперов, {sum(genders["1/2"].values())}/{sum(genders["7/8"].values())} разъёма; закупочно {math.ceil(d["cable78_installed"]*1.1)} м 7/8 и {math.ceil(d["cable12_installed"]*1.1)} м 1/2; {len(c["scenarios"])} сценариев |',
      'DCS RxLev >−85 на 95%':f'| DCS RxLev >−85 на 95% | Условная карта рассчитана | {number(e["dcs_scenarios"][0]["reference_percent_2100"])}% при 40 дБм BCCH/TRX, n=2,5; рабочая мощность и измерения не заданы |'}
    def kpi(text):
        return '\n'.join(rows.get(line.split('|')[1].strip(),line) if line.startswith('|') and len(line.split('|'))>2 else line
                         for line in text.splitlines())+'\n'
    update('docs/final/kpi-checklist.md',kpi)
    update('docs/final/assumptions.md',lambda t:re.sub(r'^\| A19 \|.*$',
        f'| A19 | Местные связи {local}: джампер 3 м, 0,2 дБ на путь; {d["local_jumper_count"]} физических связи | Собственное решение принятого варианта n=3 | Нулевые фидеры не закупаются; потери джампера оценочные |',t,flags=re.M)
        .replace('это не новый KPI задания и не подтверждение P2, n=3, помеховых показателей или измерений',
                 'это не новый KPI задания; n=3 проверен отдельно, P2 и помеховые показатели остаются ограничениями'))
    summary=f'Принят проверенный вариант n=3: B3/B1/B7 {fmt("P1_n3")}; B7 совместный запас {number(shares["P1_closed_gaps_geometry_uncertain_fail_RF3",2600])}%. Коаксиал {number(old_total)} → {number(total)} м ({number((total/old_total-1)*100)}%); 32 In06 и мощность пилота сохранены.'
    marker='## Принятие варианта n=3 в основной пакет'
    for path in ['docs/final/input-audit.md','docs/final/reserve-review.md']:
        update(path,lambda t:t.split(marker)[0].rstrip()+'\n\n'+marker+'\n\n'+summary+'\n\n'
              'Позиции S-узлов, классы мощности и трассы взяты из проверенного исследования. Паспорта, оригинальные DOCX и геометрия не изменены. '
              'Источник сравнения до принятия — design/final/n3/baseline-candidate.json; текущие входы — design/final/project-input.json.\n')
    status='Вариант принят в основной проект; пять артефактов и архив обновлены.' if args.finalize else 'Вариант принят в основной проект; пять артефактов пересобираются отдельной командой.'
    update('docs/final/n3-feasibility.md',lambda t:re.sub(r'\n\*\*Статус принятия:.*?\n\n','\n',t,flags=re.S,count=1)
        .replace('Основной пакет пока сохраняет прежнюю схему.','В таблицах «основная схема» означает зафиксированную версию до принятия.')
        .replace('Рекомендация по результатам исследования — перенести проверенный вариант в основной пакет с обновлением планов, портовой ведомости, спецификации и презентации как отдельный этап.',
                 'Проверенный вариант перенесён в основной проект; состояние экспорта фиксируется в primary-adoption.json.')
        .replace('\n\nДата:',f'\n\n**Статус принятия:** {status} [Запись принятия](../../design/final/n3/primary-adoption.json).\n\nДата:',1))
    update('design/final/n3/README.md',lambda t:t.replace('Основная схема и архив сдачи сохранены. Здесь находятся самостоятельный\nисследовательский вариант и проверочные данные.',
        'Проверенный вариант принят в основной проект. Здесь сохранены исследование,\nснимок до принятия и проверочные данные; статус экспорта — primary-adoption.json.'))
    update('presentation/jury-questions.md',lambda t:re.sub(r'В текущем варианте номинал B7.*?калибровки не устранена\.',
        f'В принятом варианте номинал B7 — {number(shares["P1_n2.5",2600])}%, n=3 — {number(shares["P1_n3",2600])}%, +3 дБ — {number(shares["P1_extra_RF_3dB",2600])}%, совместный сценарий — {number(shares["P1_closed_gaps_geometry_uncertain_fail_RF3",2600])}%. Это прогноз P1 по весам экспликации. P2 — {number(shares["P2_carrier23",2600])}%, ниже 95%. Нормировка пилота, калибровка и остальные KPI не подтверждены.',t,flags=re.S)
        .replace('1/2 — 42 male и 42 female; 7/8 — 62 male и 22 female',
                 f'1/2 — {genders["1/2"]["male"]} male и {genders["1/2"]["female"]} female; 7/8 — {genders["7/8"]["male"]} male и {genders["7/8"]["female"]} female')
        .replace('## Насколько надёжен результат 96,55%?','## Насколько надёжен расчётный результат?')
        .replace('−96,66', '−'+number(abs(min(r['rsrp_dbm'] for r in d['rf_points'] if r['frequency_mhz']==2600 and r['d_horizontal_m']==20)))))
    update('submission/README.md',lambda t:t.replace('36 LTE-сценариев','39 LTE-сценариев')
        .replace('n=3 и P2 не проходят','n=3, включая закрытые проёмы, проходит; P2 не проходит')
        .replace('Метраж фидеров вырос с 1084 до 1461 м.',f'Метраж коаксиала сокращён с {old_total:.0f} до {total:.0f} м после принятия n=3.')
        .replace('11 графических листов','14 графических листов'))
    update('docs/final/deliverables/README.md',lambda t:t.replace('Исследование возможности прохождения n=3 в редизайн не входит.',
        'Оформление сохранено; проверенный вариант n=3 принят в техническую часть и добавлены три карты диапазонов.')
        .replace('11 листов A3','14 листов A3'))
    update('README.md',lambda t:re.sub(r'\[Отдельное исследование n=3\].*?(?=\n\n)',
        '[Принятый вариант n=3](docs/final/n3-feasibility.md): '+summary+' Основные артефакты обновляются этой версией; P2 и прочие неподтверждённые KPI сохраняют ограничения.',t)
        .replace('113 джамперов, 84/84 разъёма','113 джамперов, 68/100 разъёмов'))
    update('README.md',lambda t:re.sub(r'\[Проверка запаса\].*?(?=\n\n)',
        f'[Проверка запаса](docs/final/reserve-review.md): в принятой схеме B7 номинально {number(shares["P1_n2.5",2600])}%, при +3 дБ {number(shares["P1_extra_RF_3dB",2600])}%, совместный сценарий {number(shares["P1_closed_gaps_geometry_uncertain_fail_RF3",2600])}%. Мощность пилота и 32 антенны сохранены; кабели и разъёмы пересчитаны.',t)
        .replace('Основные артефакты обновляются этой версией','Основные артефакты обновлены этой версией' if args.finalize else 'Основные артефакты обновляются этой версией')
        .replace('но n=3 и нормировка P2 не проходят 95%','n=3, включая закрытые проёмы, также проходит; нормировка P2 не проходит 95%'))
    presentation_status=ROOT/'presentation/presentation-status.json'
    if presentation_status.exists():
        words=json.loads(presentation_status.read_text())['word_count']
        update('presentation/README.md',lambda t:re.sub(r'\d+ слов, план',f'{words} слов, план',t))
    print('Primary status updated; final export verified:',args.finalize)

if __name__=='__main__':main()
