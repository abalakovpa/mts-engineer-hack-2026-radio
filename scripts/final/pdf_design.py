"""Shared report introductions, A3 drawing sheets and final PDF navigation.

Only presentation is changed here. All engineering figures and values are read
from the existing, verified design outputs.
"""
from io import BytesIO
from pathlib import Path
import re

import fitz
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
INK = '#202A36'
MUTED = '#627080'
ACCENT = '#D82035'
LINE = '#D9D9D9'
TINT = '#F2F2F2'
FONTS = Path('/usr/share/fonts/truetype/dejavu')
pdfmetrics.registerFont(TTFont('ReportSans', str(FONTS / 'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('ReportSansBold', str(FONTS / 'DejaVuSans-Bold.ttf')))
SHORT_TITLES = {'01-capacity': '01 / Ёмкостной расчёт',
                '02-floor-design': '02 / Проект первого этажа',
                '03-rsrp': '03 / Расчёт RSRP'}

FIGURES = [
    ('План первого этажа', 'design/final/verification/final-layout.pdf', False,
     'Антенны, распределительное оборудование, трассы и предложенная ВК. CAD X/Y — метры; '
     'ВК и монтажные позиции являются проектными решениями. Полная ведомость координат приведена далее.'),
    ('Подключение передатчиков БС', 'design/final/verification/bs-connections.pdf', True,
     'Отдельные пути M1/M2. Три диапазона LTE МТС; резервные операторские входы не подтверждают '
     'фактические нагрузки и мощности других операторов. DCS — отдельный условный источник, не GSM MIMO.'),
    ('Распределительное дерево', 'design/final/verification/distribution-tree.pdf', True,
     'PC252 в каждой зоне: две антенны непосредственно, две через PC250 и четыре через PC252. '
     'Показано одно дерево; вторая MIMO-ветвь физически отдельная. Z1–Z4 не являются четырьмя LTE-ячейками.'),
    ('RSRP B3 / 1800 МГц', 'design/final/coverage/rsrp-1800-walls.png', False,
     'Сценарий P1, n=2,5, высоты 7/1,5 м. Доля выше −90 дБм относится к 2100 м². '
     'Нелокализованная площадь считается непрошедшей. Карта — прогноз модели, не измерения.'),
    ('RSRP B1 / 2100 МГц', 'design/final/coverage/rsrp-2100-walls.png', False,
     'Сценарий P1, n=2,5, высоты 7/1,5 м. Общая шкала карт LTE позволяет сравнивать диапазоны. '
     'Пилот и свойства препятствий приняты условно; SINR/RSRQ из этой карты не следуют.'),
    ('RSRP B7 / 2600 МГц', 'design/final/coverage/rsrp-2600-walls.png', False,
     'Номинальный P1, n=2,5. Порог строго >−90 дБм; знаменатель 2100 м². '
     'Сильнейший отдельный путь не учитывает фазовую интерференцию и не является строгой нижней границей сигнала.'),
    ('RSRP B3 / n=3', 'design/final/coverage/rsrp-1800-n3.png', False,
     'Сценарий P1, показатель распространения n=3. Мощность пилота, высоты, препятствия и знаменатель 2100 м² сохранены. Это модельная проверка чувствительности, не измерения.'),
    ('RSRP B1 / n=3', 'design/final/coverage/rsrp-2100-n3.png', False,
     'Сценарий P1, n=3; порог строго >−90 дБм. Нелокализованная площадь остаётся непрошедшей. Проверка не устанавливает SINR/RSRQ или фактическую скорость.'),
    ('RSRP B7 / n=3', 'design/final/coverage/rsrp-2600-n3.png', False,
     'Принятый вариант n=3: 32 In06, две отдельные MIMO-ветви. Нормировка пилота P1 условна; более слабая трактовка P2 проверена отдельно.'),
    ('B7 / проверка запаса 3 дБ', 'design/final/coverage/rsrp-2600-reserve3.png', False,
     'Дополнительные 3 дБ RF-потерь относительно номинального P1. Проверка запаса — собственный '
     'критерий проекта. n=3 проверен отдельно; запас не подтверждает нормировку P2 и остальные KPI задания.'),
    ('B7 / совместный сценарий', 'design/final/coverage/rsrp-2600-joint-reserve3.png', False,
     'Закрытые архитектурные проёмы, спорная группа 114.2 как непрошедшая и дополнительные 3 дБ RF-потерь. '
     'Виртуальные стыки контуров не трактуются как дополнительные RF-стены.'),
    ('DCS / условный BCCH 40 дБм', 'design/final/verification/dcs-1800-conditional.png', False,
     '40 дБм на BCCH/TRX перед отдельным PC250 — выбранный сценарий, не установленная настройка. '
     'Показана расчётная мощность сигнала; C/I и частотный план не подтверждены.'),
    ('Принадлежность проектной LTE-ячейке', 'design/final/verification/project-cell-assignment.png', False,
     'Одна проектная ячейка на диапазон. Карта не является полноценным Best Server с внешней macro-сетью; '
     'EARFCN/PCI и конкурирующая сеть не заданы.'),
    ('Модель площади', 'design/final/coverage/area-model.png', False,
     '36 восстановленных групп, 45 локализованных помещений. Помещение 89 не локализовано; '
     'расхождение площади >10% остаётся у 114.2. Геометрия не масштабировалась для повышения результата.'),
]


def number(value, places=2):
    return f'{value:.{places}f}'.replace('.', ',')


def display_equations(text):
    """Typeset existing dependencies without changing their definitions."""
    replacements = {
        'P_CRS_RE = 23 − 10log10(2N_PRB).':
            r'\[P_{\mathrm{CRS,RE}} = 23 - 10\log_{10}(2N_{\mathrm{PRB}}).\]',
        'L_RF(f) = Σ[α_i(f)×l_i/100] + ΣL_component(f), дБ,':
            r'\[L_{\mathrm{RF}}(f) = \sum_i\frac{\alpha_i(f)l_i}{100}'
            r' + \sum_j L_{\mathrm{component},j}(f)\quad [\text{дБ}],\]',
        'L_FS = 20log10(f_MHz) − 27,55 + 20log10(r_m).':
            r'\[L_{\mathrm{FS}} = 20\log_{10}(f_{\mathrm{MHz}}) - 27{,}55'
            r' + 20\log_{10}(r_{\mathrm{m}}).\]',
        'L_n = 20log10(f_MHz) − 27,55 + 10n log10(r_m), n = 2,5 или 3.':
            r'\[L_n = 20\log_{10}(f_{\mathrm{MHz}}) - 27{,}55'
            r' + 10n\log_{10}(r_{\mathrm{m}}),\quad n=2{,}5\text{ или }3.\]',
        'RSRP = P_CRS_RE − L_RF + G_ant − L_n − 15N_partition − 30N_external − 30N_column + G_UE.':
            r'\[\begin{aligned}\mathrm{RSRP} &= P_{\mathrm{CRS,RE}} - L_{\mathrm{RF}}'
            r' + G_{\mathrm{ant}} - L_n\\'
            r'&\quad - 15N_{\mathrm{partition}} - 30N_{\mathrm{external}}'
            r' - 30N_{\mathrm{column}} + G_{\mathrm{UE}}.\end{aligned}\]',
    }
    for original, formatted in replacements.items():
        assert text.count(original) == 1, original
        text = text.replace(original, formatted)
    return text


def introduction(name, design, coverage):
    """Overview text uses the same numerical outputs as the technical body."""
    shares = {(r['scenario'], r['frequency_mhz']): r['reference_percent_2100']
              for r in coverage['scenarios']}
    if name == '01-capacity':
        title = 'Ёмкостной расчёт'
        subtitle = 'Корректировка онлайн-этапа по новым параметрам RRC и buffer users'
        metrics = ('1', 'общий LTE-пул', 'кандидат при k(1)=1',
                   '13 UE', 'плановая нагрузка', '6 / 4 / 3 без CA',
                   '104', 'Мбит/с полезного DL', '13 UE по 8 Мбит/с')
        notes = (('ReportBlue', 'ПРИНЯТО В МОДЕЛИ',
                  r'35\% и 10\% применяются последовательно вместо прежних 80\%. '
                  'При буквальном сохранении онлайн-правила перекоса результат — два LTE-сектора.'),
                 ('ReportAmber', 'ГРАНИЦЫ РЕЗУЛЬТАТА',
                  'Один общий пул не имеет запаса на четырнадцатого UE без CA. '
                  'Средняя модель нагрузки не подтверждает временные всплески, покрытие и фактическую скорость.'))
    elif name == '02-floor-design':
        title = 'Проект первого этажа'
        subtitle = 'Пассивная DAS · размещение · подключения · покрытие · ведомости'
        metrics = (str(len(design['antennas'])), 'антенны In06', 'две отдельные MIMO-ветви',
                   number(shares['P1_n3', 2600]) + r'\%', 'B7 при n=3', 'прогноз P1; порог >−90 дБм',
                   number(design['cable78_installed'] + design['cable12_installed'], 0),
                   'метров коаксиала', 'без закупочного запаса')
        notes = (('ReportBlue', 'РАСЧЁТНЫЙ РЕЗУЛЬТАТ',
                  'Неравномерное дерево 2+2+4 сохраняет мощность пилота и число антенн. n=3 и запас 3 дБ проверены отдельно. '
                  'Подробные планы и схемы представлены на листах A3 с отдельными условиями расчёта.'),
                 ('ReportAmber', 'ОГРАНИЧЕНИЯ',
                  r'P2 не проходит 95\%. RSRQ/SINR/C/I/UL, полная комплектация и '
                  'удалённое регулирование пассивной схемой не подтверждены.'))
    else:
        title = 'Расчёт RSRP'
        subtitle = 'Исходные данные · RF-бюджет · контрольные расстояния · чувствительность'
        metrics = (str(len(design['rf_points'])), 'контрольных значений', '32 антенны × 3 диапазона × 4 расстояния',
                   '23 дБм', 'пилот на выходе БС', 'смысл мощности условен',
                   '5–20 м', 'расстояния по горизонтали', 'высоты антенны / UE: 7 / 1,5 м')
        notes = (('ReportBlue', 'ПРИНЯТО В МОДЕЛИ P1',
                  r'23 дБм — сумма мощностей 2N\_PRB CRS-поднесущих в CRS-символе на одном порту. '
                  'Отдельно показаны другие трактовки мощности и показатели распространения.'),
                 ('ReportAmber', 'КАК ЧИТАТЬ РЕЗУЛЬТАТЫ',
                  'Таблицы на 5/10/15/20 м описывают отдельные пути, а не долю покрытия площади. '
                  'Проверка покрытия приведена отдельно; измеренные KPI не заявляются.'))
    text = f'\\ReportTitle{{{name[:2]}}}{{{title}}}{{{subtitle}}}\n\n'
    text += '\\ReportMetrics' + ''.join('{' + value + '}' for value in metrics) + '\n\n'
    for color, label, content in notes:
        text += f'\\ReportNote{{{color}}}{{{label}}}{{{content}}}\n\n'
    return text + '\\ReportNavigation\n\n'


def paragraph(c, text, x, top, width, size=10, bold=False, color=INK):
    style = ParagraphStyle('report', fontName='ReportSansBold' if bold else 'ReportSans',
                           fontSize=size, leading=size * 1.4, textColor=HexColor(color))
    p = Paragraph(text, style)
    _, height = p.wrap(width, 1000)
    p.drawOn(c, x, top - height)
    return height


def drawing_sheet(index):
    title, relative, landscape, caption = FIGURES[index]
    width, height = ((420 * mm, 297 * mm) if landscape else (297 * mm, 420 * mm))
    margin = 18 * mm
    stream = BytesIO()
    c = canvas.Canvas(stream, pagesize=(width, height), pageCompression=1,
                      initialFontName='ReportSans',initialFontSize=8)
    c.setFillColor(HexColor(MUTED))
    c.setFont('ReportSans', 8)
    c.drawString(margin, height - 14 * mm, 'МТС ENGINEER HACK 2026  /  РАДИО')
    c.drawRightString(width - margin, height - 14 * mm, '02 / Проект первого этажа')
    c.setStrokeColor(HexColor(LINE))
    c.line(margin, height - 18 * mm, width - margin, height - 18 * mm)
    paragraph(c, f'ГРАФИЧЕСКИЙ ЛИСТ {index + 1:02d} / A3', margin,
              height - 23 * mm, width - 2 * margin, 9, True, ACCENT)
    paragraph(c, title, margin, height - 32 * mm, width - 2 * margin, 21, True)
    c.setFillColor(HexColor(ACCENT))
    c.rect(margin, height - 49 * mm, 25 * mm, 1.5, stroke=0, fill=1)
    c.setFillColor(HexColor(TINT))
    c.setStrokeColor(HexColor(ACCENT))
    c.setLineWidth(.5)
    c.rect(margin, 22 * mm, width - 2 * margin, 26 * mm, stroke=1, fill=1)
    paragraph(c, 'УСЛОВИЯ И ГРАНИЦЫ ИНТЕРПРЕТАЦИИ', margin + 4 * mm,
              44 * mm, width - 2 * margin - 8 * mm, 8, True, ACCENT)
    paragraph(c, caption.replace('>', '&gt;'), margin + 4 * mm, 39 * mm,
              width - 2 * margin - 8 * mm, 9)
    c.showPage()
    c.save()
    sheet = fitz.open(stream=stream.getvalue(), filetype='pdf')
    frame = fitz.Rect(margin, 54 * mm, width - margin, height - 53 * mm)
    source = ROOT / relative
    if source.suffix == '.pdf':
        with fitz.open(source) as vector:
            sheet[0].show_pdf_page(frame, vector, 0, keep_proportion=True)
    else:
        sheet[0].insert_image(frame, filename=str(source), keep_proportion=True)
    return sheet


def finish_pdf(path, name, title):
    """Replace same-count placeholders in place, preserving TOC links/bookmarks."""
    with fitz.open(path) as document:
        outlines = document.get_toc(simple=False)
        links = [(i, link) for i, page in enumerate(document) for link in page.get_links()
                 if link['kind'] == fitz.LINK_NAMED and link.get('page', -1) >= 0]
        original_heights = [page.rect.height for page in document]
        found = []
        drawing_pages = set()
        for page in document:
            marker = re.search(r'REPORTFIGURE:FIG(\d{2})', page.get_text())
            if not marker:
                continue
            index = int(marker.group(1)) - 1
            assert name == '02-floor-design'
            sheet = drawing_sheet(index)
            # Keep the page object (and all destinations), replace its content.
            blank = document.get_new_xref()
            document.update_object(blank, '<< /Length 0 >>')
            document.update_stream(blank, b'')
            page.set_contents(blank)
            page.set_mediabox(sheet[0].rect)
            page.set_cropbox(sheet[0].rect)
            page.show_pdf_page(page.rect, sheet, 0)
            sheet.close()
            found.append(index)
            drawing_pages.add(page.number)
        assert found == (list(range(len(FIGURES))) if name == '02-floor-design' else []), found
        for i, page in enumerate(document):
            width, height = page.rect.width, page.rect.height
            margin = 18 * mm if width > 600 else 20 * mm
            stream = BytesIO()
            c = canvas.Canvas(stream, pagesize=(width, height), pageCompression=1,
                              initialFontName='ReportSans',initialFontSize=8)
            c.setStrokeColor(HexColor(LINE))
            c.line(margin, 17 * mm, width - margin, 17 * mm)
            c.setFillColor(HexColor(MUTED))
            c.setFont('ReportSans', 8)
            c.drawString(margin, 11 * mm, SHORT_TITLES[name])
            c.drawCentredString(width / 2, 11 * mm, '14.10.2026')
            c.drawRightString(width - margin, 11 * mm, f'{i + 1} / {len(document)}')
            c.showPage()
            c.save()
            with fitz.open(stream=stream.getvalue(), filetype='pdf') as overlay:
                page.show_pdf_page(page.rect, overlay, 0)
        # XeLaTeX named destinations use PDF coordinates. Resolve them explicitly
        # so links still land at the sheet heading after changing A4 to A3.
        for page_number, link in links:
            target = link['page']
            point = (fitz.Point(18 * mm, 23 * mm) if target in drawing_pages else
                     fitz.Point(link['to'].x, original_heights[target] - link['to'].y))
            document[page_number].update_link(dict(kind=fitz.LINK_GOTO,xref=link['xref'],
                **{'from':link['from']},page=target,to=point))
        for entry in outlines:
            destination = entry[3]
            if destination['kind'] == fitz.LINK_NAMED and destination.get('page', -1) >= 0:
                target = destination['page']
                point = (fitz.Point(18 * mm, 23 * mm) if target in drawing_pages else
                         fitz.Point(destination['to'].x, original_heights[target] - destination['to'].y))
                entry[3] = dict(kind=fitz.LINK_GOTO,page=target,to=point,zoom=0,
                                collapse=destination.get('collapse',False))
        document.set_toc(outlines)
        document.set_metadata({'title': title, 'author': 'Павел Абалаков',
                               'subject': 'МТС Engineer Hack 2026 — финал, кейс Радио',
                               'creator': 'Pandoc / XeLaTeX / ReportLab',
                               'keywords': 'Радио, DAS, финал'})
        temporary = path.with_suffix('.styled.pdf')
        document.save(temporary, garbage=4, deflate=True)
    temporary.replace(path)


def inspect_pdf(path, name, design):
    """Check the exported artifact, including values after LaTeX rendering."""
    with fitz.open(path) as document:
        text = '\n'.join(page.get_text() for page in document)
        assert 'REPORTFIGURE:' not in text and '\ufffd' not in text, path.name
        for i, page in enumerate(document):
            assert f'{i + 1} / {len(document)}' in page.get_text(), (path.name, i + 1)
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    x0, y0, x1, y1 = line['bbox']
                    assert x0 >= 17 * mm - 1 and x1 <= page.rect.width - 17 * mm + 1, (
                        path.name, i + 1, 'horizontal safe area', line['bbox'])
                    assert y0 >= 0 and y1 <= page.rect.height, (path.name, i + 1, 'page bounds')
        major_pages = {row[2] - 1 for row in document.get_toc() if row[0] == 1}
        links = [link for link in document[0].get_links() if link['kind'] == fitz.LINK_GOTO]
        assert links and {link['page'] for link in links} == major_pages, path.name
        for row in document.get_toc(simple=False):
            destination = row[3]
            assert destination['kind'] == fitz.LINK_GOTO
            assert 0 <= destination['page'] < len(document)
            assert destination['to'] in document[destination['page']].rect
        sheets = [page for page in document if page.rect.width > 600]
        assert len(sheets) == (len(FIGURES) if name == '02-floor-design' else 0)
        if sheets:
            assert sum(page.rect.width > page.rect.height for page in sheets) == 2
            # Preserve the three vector drawings, not raster screenshots of them.
            assert all(len(sheets[i].get_drawings()) > 20 for i in (0, 1, 2))
        if name == '03-rsrp':
            pattern = (r'(A\d{2})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+'
                       r'(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)')
            actual = re.findall(pattern, text)
            expected = []
            for frequency in (1800, 2100, 2600):
                for antenna in design['antennas']:
                    values = sorted((row for row in design['rf_points']
                        if row['antenna'] == antenna['id'] and row['frequency_mhz'] == frequency),
                        key=lambda row: row['d_horizontal_m'])
                    expected.append(tuple([antenna['id'], f'{values[0]["total_loss_db"]:.3f}'] +
                                          [f'{row["rsrp_dbm"]:.2f}' for row in values]))
            assert actual == expected, (path.name, 'exported RF/RSRP table')
        return dict(layout_checked=True, a3_sheets=len(sheets), navigation_checked=True)


def preview_reports(directory, destination):
    preview = Image.new('RGB',(1620,790),'#e8edf1')
    for i, name in enumerate(SHORT_TITLES):
        with fitz.open(directory / (name + '.pdf')) as document:
            pixmap = document[0].get_pixmap(matrix=fitz.Matrix(1,1))
            thumbnail = Image.frombytes('RGB',(pixmap.width,pixmap.height),pixmap.samples)
            thumbnail.thumbnail((510,740))
            preview.paste(thumbnail,(i*540+(540-thumbnail.width)//2,15))
            ImageDraw.Draw(preview).text((i*540+20,766),name+'.pdf',fill=INK)
    preview.save(destination,optimize=True)
