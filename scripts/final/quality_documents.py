"""Engineering explanation of conditional quality calculations for standalone reports."""
from pathlib import Path
import json
import math
from final_engineering import table

ROOT=Path(__file__).resolve().parents[2]

def number(value,places=2):return f'{value:.{places}f}'.replace('.',',')
def quality_report():return json.loads((ROOT/'design/final/quality/quality-report.json').read_text())
def section(title,*parts):return '# '+title+'\n\n'+'\n\n'.join(parts)+'\n\n'


def base_quality_table(q):
    rows=[r for r in q['lte_results'] if r['scenario']==q['base_scenario']]
    return table(['Диапазон','SINR ≥17, %','SINR ≥7, %','SINR ≥1, %','RSRQ >−12, %'],
        [[{1800:'B3',2100:'B1',2600:'B7'}[r['frequency_mhz']]]+[number(r[k]) for k in
            ('sinr_ge17_percent','sinr_ge7_percent','sinr_ge1_percent','rsrq_gt_minus12_percent')] for r in rows])


def budget_table(q):
    return table(['Поле','Диапазон','J, дБм/15 кГц','I, дБм/15 кГц'],
        [[b['field'],{1800:'B3',2100:'B1',2600:'B7'}[b['frequency_mhz']],number(b['max_disturbance_dbm']),number(b['max_external_interference_dbm'])] for b in q['lte_budgets']])


def project_quality():
    q=quality_report()
    limit=lambda field:' / '.join(number(b['max_external_interference_dbm']) for b in q['lte_budgets'] if b['field']==field)
    text=section('Сценарный расчёт качества LTE',
        'Для каждого диапазона построены карты SINR и RSRQ на той же сетке, что RSRP. '
        'Рассмотрены два TX-порта и идеальное разделение потоков приёмником. '
        'Остальные антенны одной ячейки не объявляются независимыми источниками межсотовых помех.',
        'На графических листах показан L2: P1, n=2,5, NF UE=7 дБ, загрузка данных ρ=0,8, '
        'отношение EPRE данных к CRS на каждом порту β=0,5 (−3,01 дБ), '
        'суммарная внешняя помеха I=−115 дБм на 15 кГц. NF, ρ, β и I — сценарные параметры проекта, '
        'не предоставленные характеристики приёмника или настройки БС.',
        base_quality_table(q),
        'Целевые доли SINR — 40/80/95%, RSRQ — 80%. В L2 эти критерии выполняются. '
        'При равной EPRE данных и CRS (β=1), двух портах и ρ=0,8 верхняя граница RSRQ равна −12,25 дБ: '
        'критерий >−12 дБ не выполняется даже без внешних помех. Поэтому β является существенным условием модели.',
        'Для β=0,5 и ρ=0,8 определён предельный уровень внешней помехи, при котором одновременно '
        f'выполняются требования SINR и RSRQ. В P1 при n=2,5 это {limit("P1")} дБм '
        f'на 15 кГц для B3/B1/B7; при n=3 — {limit("P1_n3")} дБм. '
        'Рабочий уровень должен лежать ниже соответствующей границы. Расчёт не определяет фактические помехи, '
        'MIMO rank или CQI; полный набор сценариев приведён в ведомости оборудования.')
    b=q['dcs_budgets']
    selected=[r for r in q['dcs_results'] if r['bcch_dbm']==40]
    text+=section('Сценарный расчёт C/I для DCS',
        'C/I определяется отношением мощности полезной BCCH-несущей к суммарной соканальной помехе '
        'на входе UE. Мощности помех заданы в полосе 200 кГц. В расчёт C/I тепловой шум не включается; '
        'он не является бюджетом обратной линии.',
        table(['BCCH, дБм','I, дБм/200 кГц','C/I >20, %','RxLev >−85, %'],
              [[number(r['bcch_dbm'],0),number(r['interference_dbm_200khz'],0),number(r['ci_gt20_percent']),number(r['rx_gt_minus85_percent'])] for r in selected]),
        f'При BCCH 40 дБм для C/I>20 дБ на 95% от 2100 м² требуется I<{number(b[0]["max_interference_dbm"])} дБм '
        f'на 200 кГц. При 36,99 / 30 дБм границы снижаются до {number(b[1]["max_interference_dbm"])} / '
        f'{number(b[2]["max_interference_dbm"])} дБм. ARFCN и внешние БС в исходных материалах не заданы; '
        'расчёт устанавливает допустимый бюджет помех без назначения вымышленных частот.')
    return text


def radio_quality():
    q=quality_report()
    text=section('Модель SINR и RSRQ для двух TX-портов',
        'S — принятый RSRP одного CRS RE, выраженный в мВт. β — отношение EPRE PDSCH к CRS '
        'на каждом TX-порту. ρ — доля занятых RE данных в символах измерения. '
        'Для LTE normal CP в CRS-содержащем символе на RB приняты четыре CRS RE двух портов '
        'и восемь потенциальных RE данных. PDSCH на позициях CRS другого порта не передаётся.',
        r'\[J=I_{\mathrm{ext}}+N_{\mathrm{RE}},\qquad N_{\mathrm{RE,dBm}}=-174+10\log_{10}(15000)+NF.\]',
        r'\[\mathrm{SINR}_{\mathrm{model}}=10\log_{10}\frac{\beta S}{J}.\]',
        r'\[\mathrm{RSSI}=N_{\mathrm{RB}}\big[(4+16\rho\beta)S+12J\big].\]',
        r'\[\mathrm{RSRQ}=10\log_{10}\frac{N_{\mathrm{RB}}S}{\mathrm{RSSI}}=10\log_{10}\frac{S}{(4+16\rho\beta)S+12J}.\]',
        'SINR рассчитан для потока при идеальном разделении MIMO; это оценка модели приёмника. '
        'Фазовое сложение антенных копий и остаточные помехи между потоками не моделируются. '
        'β относится к рассматриваемым символам данных; конкретные P_A/P_B не заданы. '
        'Одноимённые уровни второго TX-порта приняты равными первому. Собственный сигнал второго порта '
        'входит в RSSI, а при идеальном разделении потоков не добавляется в J.',
        'При NF=7 дБ тепловой шум равен −125,24 дБм на 15 кГц. I_ext — суммарная внешняя помеха '
        'на ту же полосу; мощности складываются в линейных единицах. '
        'ρ описывает занятость RE, а u=0,8 в ёмкостном расчёте — эксплуатационную загрузку; '
        'их одинаковые численные значения выбраны отдельно. NF, β, ρ и I_ext являются авторскими сценариями.')
    text+=section('Сценарии качества LTE',
        table(['ID','Поле','I, дБм/15 кГц','NF, дБ','β','ρ'],
              [[s['id'],s['field'],'Только шум' if s['interference_dbm'] is None else number(s['interference_dbm'],0),s['nf_db'],number(s['beta'],1),number(s['rho'],1)] for s in q['scenarios']]),
        'P1 — n=2,5; P1_n3 — n=3; P2 — мощность всей несущей 23 дБм. '
        'Все доли считаются от 2100 м²; неизвестная площадь не засчитывается. '
        'Требования: SINR≥17/7/1 дБ на 40/80/95% площади, RSRQ>−12 дБ на 80%. '
        'Карты представлены для L2. Сценарии с более высоким уровнем помех и равной EPRE '
        'сохраняют непроходящие результаты.')
    for f in (1800,2100,2600):
        rows=[r for r in q['lte_results'] if r['frequency_mhz']==f]
        text+='## '+str(f)+' МГц\n\n'+table(['ID','SINR ≥17, %','SINR ≥7, %','SINR ≥1, %','RSRQ >−12, %'],
            [[r['scenario']]+[number(r[k]) for k in ('sinr_ge17_percent','sinr_ge7_percent','sinr_ge1_percent','rsrq_gt_minus12_percent')] for r in rows])+'\n\n'
    text+=section('Границы допустимых помех LTE',
        r'\[\mathrm{RSRQ}_{\max}=-10\log_{10}(4+16\rho\beta).\]',
        'При β=1 и ρ=0,8 получаются −12,25 дБ; при β=0,5 — −10,17 дБ. '
        'Для выполнения >−12 дБ в идеальном пределе требуется β<0,9257 при ρ=0,8. '
        'С учётом помех условие становится строже.',
        r'\[J\leq\frac{\beta S}{10^{T/10}},\qquad J<\frac{(10^{12/10}-4-16\rho\beta)S}{12}.\]',
        'Для каждого SINR-порога T берётся взвешенный уровень S на требуемой доле площади, '
        'для RSRQ — на 80%. Самая строгая из четырёх границ задаёт допустимое J. '
        'Шум вычитается в линейных единицах, чтобы получить допустимое I_ext. '
        'Таблица относится к β=0,5, ρ=0,8 и NF=7 дБ; рабочий уровень выбирается минимум на 0,1 дБ ниже границы.',
        budget_table(q),
        'Эти границы относятся к SINR/RSRQ. P2 сохраняет непроходящий результат RSRP, '
        'даже если его сценарий качества удовлетворяет указанным ограничениям. '
        f'Шенноновская необходимая граница для q=3,3223 бит/RE/слой — около {number(10*math.log10(2**(6*567/1024)-1))} дБ; '
        'она не доказывает практическую реализацию CQI 11, MIMO rank или скорость каждого UE.')
    text+=section('Модель C/I и результаты DCS',
        r'\[C/I_{\mathrm{dB}}=C_{\mathrm{dBm}}-I_{\mathrm{dBm}}.\]',
        'C — поле BCCH после распределительной системы, I — суммарная соканальная помеха '
        'в полосе 200 кГц. Шум не включается в определение C/I. Используются прежняя геометрия '
        'и три сценарные мощности BCCH: 40 дБм, 36,99 дБм при равном разделении общей мощности '
        'двух TRX и 30 дБм. ARFCN и координаты внешних передатчиков не назначаются.',
        table(['BCCH, дБм','I, дБм/200 кГц','C/I >20, %','RxLev >−85, %'],
              [[number(r['bcch_dbm']),number(r['interference_dbm_200khz'],0),number(r['ci_gt20_percent']),number(r['rx_gt_minus85_percent'])] for r in q['dcs_results']]),
        table(['BCCH, дБм','C на 95%, дБм','Предельное I, дБм/200 кГц'],
              [[number(b['bcch_dbm']),number(b['c95_dbm']),number(b['max_interference_dbm'])] for b in q['dcs_budgets']]),
        'Для строгого C/I>20 дБ помеха должна быть ниже указанной границы. '
        'Расчёт позволяет задать условие частотного планирования; фактический C/I без сведений '
        'о соканальных источниках не определяется. UL, интерфейсы и управляемые удалённые модули '
        'этими DL-расчётами не проверяются.')
    return text
