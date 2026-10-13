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
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
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

FIGURES = [('План первого этажа',
  'design/final/verification/final-layout.pdf',
  False,
  'Координаты в метрах. Высота антенн — 7 м. Z1–Z4 — группы распределения; M1/M2 — независимые RF-ветви. '
  'Головной узел предусмотрен в проектной зоне 104.2.'),
 ('Подключение передатчиков БС',
  'design/final/verification/bs-connections.pdf',
  True,
  'На каждый LTE TX-порт предусмотрено отдельное дерево. PC221 распределяют диапазоны на четыре направления, '
  'PC211 объединяют B3/B1/B7 в зональный фидер.'),
 ('Распределительное дерево',
  'design/final/verification/distribution-tree.pdf',
  True,
  'На зональном входе: две антенны по 1/4, две по 1/8 и четыре по 1/16 мощности до дополнительных потерь. '
  'Схема повторяется на двух MIMO-ветвях.'),
 ('RSRP B3 / 1800 МГц',
  'design/final/coverage/rsrp-1800-walls.png',
  False,
  '1800 МГц, P1, n=2,5. Порог RSRP >−90 дБм; знаменатель — 2100 м².'),
 ('RSRP B1 / 2100 МГц',
  'design/final/coverage/rsrp-2100-walls.png',
  False,
  '2100 МГц, P1, n=2,5. Порог RSRP >−90 дБм; знаменатель — 2100 м².'),
 ('RSRP B7 / 2600 МГц',
  'design/final/coverage/rsrp-2600-walls.png',
  False,
  '2600 МГц, P1, n=2,5. Порог RSRP >−90 дБм; знаменатель — 2100 м².'),
 ('RSRP B3 / n=3',
  'design/final/coverage/rsrp-1800-n3.png',
  False,
  '1800 МГц, P1, n=3. Мощность пилота, высоты и потери препятствий соответствуют основной модели.'),
 ('RSRP B1 / n=3',
  'design/final/coverage/rsrp-2100-n3.png',
  False,
  '2100 МГц, P1, n=3. Доля площади определяется по весам экспликации относительно 2100 м².'),
 ('RSRP B7 / n=3',
  'design/final/coverage/rsrp-2600-n3.png',
  False,
  '2600 МГц, P1, n=3. Используются текущие координаты 32 антенн и пересчитанные RF-тракты.'),
 ('B7 / проверка запаса 3 дБ',
  'design/final/coverage/rsrp-2600-reserve3.png',
  False,
  '2600 МГц, P1, n=2,5. Дополнительные RF-потери — 3 дБ; эта проверка выполняется отдельно от n=3.'),
 ('B7 / совместный сценарий',
  'design/final/coverage/rsrp-2600-joint-reserve3.png',
  False,
  '2600 МГц, P1, n=2,5. Закрытые архитектурные проёмы, группа 114.2 с нулевым вкладом и дополнительные '
  'RF-потери 3 дБ.'),
 ('DCS / условный BCCH 40 дБм',
  'design/final/verification/dcs-1800-conditional.png',
  False,
  'DCS-1800: BCCH 40 дБм перед PC250, n=2,5. Порог RxLev >−85 дБм; расчёт относится к мощности сигнала.'),
 ('Принадлежность проектной LTE-ячейке',
  'design/final/verification/project-cell-assignment.png',
  False,
  'Одна проектная LTE-ячейка на диапазон. Карта показывает принадлежность внутренней сети без сравнения с '
  'внешними ячейками.'),
 ('Модель площади',
  'design/final/coverage/area-model.png',
  False,
  '36 групп и 45 локализованных помещений. 89 не локализовано; 114.2 проверяется дополнительно. Площадь '
  'взвешена по экспликации.')]


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
        title='Ёмкостной расчёт';subtitle='Нагрузка пользователей · ресурс несущих · число секторов'
        metrics=('1','общий LTE-сектор','B3 / B1 / B7','13 UE','одновременная нагрузка','6 / 4 / 3 без CA','104','Мбит/с полезного DL','13 UE по 8 Мбит/с')
        notes=(('ReportAccent','МОДЕЛЬ СПРОСА',r'360 прогнозных устройств × 35\% RRC × 10\% buffer. Число пользователей округляется вверх до 13.'),
               ('ReportAccent','ПРИНЯТАЯ КОНФИГУРАЦИЯ','Один трёхдиапазонный LTE-сектор при η=3,1505922 бит/с/Гц, загрузке 0,8 и k(1)=1.'))
    elif name == '02-floor-design':
        title='Проект первого этажа';subtitle='Пассивная DAS · схема подключения · размещение · покрытие'
        metrics=(str(len(design['antennas'])),'антенны In06','два независимых RF-дерева',number(shares['P1_n3',2600])+r'\%','площадь B7 при n=3','RSRP >−90 дБм; модель P1',number(design['cable78_installed']+design['cable12_installed'],0),'метров коаксиала','установленная длина двух ветвей')
        notes=(('ReportAccent','АРХИТЕКТУРА','Четыре группы распределения одного LTE-пула. В каждой группе — две непосредственные, две парные и четыре четверные антенны.'),
               ('ReportAccent','РАСЧЁТНЫЕ УСЛОВИЯ','Пилот 23 дБм нормирован на сумму CRS-поднесущих одного порта. Высоты антенны и UE — 7 и 1,5 м; препятствия учитываются по плану.'))
    else:
        title='Расчёт RSRP';subtitle='Мощность опорного сигнала · RF-бюджет · уровни на 5–20 м'
        metrics=('384','расчётных значения','32 антенны × 3 диапазона × 4 расстояния','23 дБм','пилот на выходе БС','нормировка P1','5–20 м','расстояния по горизонтали','высоты антенны / UE: 7 / 1,5 м')
        notes=(('ReportAccent','РАСЧЁТНАЯ МОДЕЛЬ','Мощность одного CRS RE определяется из суммарного пилота. Потери RF-тракта включают кабели, делители, объединители и соединения.'),
               ('ReportAccent','СОСТАВ РЕЗУЛЬТАТОВ','Показаны последовательность расчёта, пример полного тракта, таблицы всех антенных путей и чувствительность карты покрытия.'))
    text = f'\\ReportTitle{{{name[:2]}}}{{{title}}}{{{subtitle}}}\n\n'
    text += '\\ReportMetrics' + ''.join('{' + value + '}' for value in metrics) + '\n\n'
    for color, label, content in notes:
        text += f'\\ReportNote{{{color}}}{{{label}}}{{{content}}}\n\n'
    return text + '\\ReportNavigation\n\n'


def paragraph(c, text, x, top, width, size=10, bold=False, color=INK):
    style = ParagraphStyle('report', fontName='ReportSansBold' if bold else 'ReportSans',
                           fontSize=size, leading=size * 1.4, textColor=HexColor(color),
                           alignment=TA_LEFT if bold else TA_JUSTIFY)
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
            pattern = (r'(A\d{2})\s+(-?\d+[.,]\d+)\s+(-?\d+[.,]\d+)\s+'
                       r'(-?\d+[.,]\d+)\s+(-?\d+[.,]\d+)\s+(-?\d+[.,]\d+)')
            actual = [tuple(v.replace(",", ".") for v in row) for row in re.findall(pattern, text)]
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
