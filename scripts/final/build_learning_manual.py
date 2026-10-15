"""Build a self-contained phone PDF without modifying submission artifacts.

Usage: python scripts/final/build_learning_manual.py
Source: presentation/project-manual.md (one ## heading per reading card).
"""
from __future__ import annotations

import html
import io
import re
from pathlib import Path

import fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, Image, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'presentation/project-manual.md'
OUTPUT = ROOT / 'presentation/project-manual-iphone.pdf'
W, H = 340, 756
MARGIN = 23
CONTENT = W - 2 * MARGIN
RED = colors.HexColor('#D82035')
INK = colors.HexColor('#202A36')
GRAY = colors.HexColor('#626262')
LINE = colors.HexColor('#D9D9D9')
TINT = colors.HexColor('#F2F2F2')
FONT_DIR = Path('/usr/share/fonts/truetype/dejavu')
for name, file in [('Guide', 'DejaVuSans.ttf'), ('GuideBold', 'DejaVuSans-Bold.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
pdfmetrics.registerFontFamily('Guide', normal='Guide', bold='GuideBold',
                              italic='Guide', boldItalic='GuideBold')

BODY = ParagraphStyle('body', fontName='Guide', fontSize=13.2, leading=18,
                      textColor=INK, spaceAfter=8, alignment=TA_LEFT,
                      allowWidows=0, allowOrphans=0, splitLongWords=True)
TITLE = ParagraphStyle('title', parent=BODY, fontName='GuideBold', fontSize=22,
                       leading=27, spaceAfter=18, keepWithNext=True)
SMALL = ParagraphStyle('small', parent=BODY, fontSize=11.4, leading=15.6)
CELL = ParagraphStyle('cell', parent=BODY, fontSize=12, leading=16,
                      spaceAfter=0)
CALLOUT = ParagraphStyle('callout', parent=BODY, fontSize=12.5, leading=17.3,
                         borderColor=LINE, borderWidth=0.6, borderPadding=10,
                         backColor=TINT, spaceBefore=6, spaceAfter=15)
TOC = ParagraphStyle('toc', parent=BODY, fontSize=14, leading=20, spaceAfter=17)


def rich(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    return text


class Heading(Paragraph):
    def __init__(self, title, chapter, section, first):
        super().__init__(rich(title), TITLE)
        self.chapter = chapter
        self.section = section
        self.first = first


class Diagram(Flowable):
    """Small conceptual diagrams, deliberately distinct from physical plans."""
    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.width = CONTENT
        self.height = 240 if kind == 'trees' else 250

    def draw(self):
        c = self.canv

        def box(x, y, width, height, lines, accent=False):
            c.setFillColor(TINT)
            c.setStrokeColor(RED if accent else LINE)
            c.roundRect(x, y, width, height, 7, fill=1, stroke=1)
            c.setFillColor(INK)
            c.setFont('GuideBold' if accent else 'Guide', 11)
            for j, line in enumerate(lines):
                c.drawCentredString(x + width / 2,
                                   y + height / 2 + (len(lines)-1)*7 - j*14 - 4,
                                   line)

        def arrow(x1, y1, x2, y2):
            c.setStrokeColor(RED)
            c.setLineWidth(1)
            c.line(x1, y1, x2, y2)
            c.line(x2, y2, x2-3, y2+6)
            c.line(x2, y2, x2+3, y2+6)

        if self.kind == 'trees':
            for x, tree, port in [(0, 'M1', 'TX1 → порт 1'), (147, 'M2', 'TX2 → порт 2')]:
                box(x, 196, 131, 36, [tree + ': ' + port], True)
                box(x, 133, 131, 42, ['PC221 по B3/B1/B7', '3 устройства'])
                box(x, 70, 131, 42, ['PC211 зоны', 'три диапазона'])
                box(x, 7, 131, 42, ['Делители зоны', '8 антенных портов'])
                for y in [196, 133, 70]:
                    arrow(x+65.5, y, x+65.5, y-21)
        elif self.kind == 'split':
            box(48, 202, 182, 39, ['Зональный PC252', 'вход одного дерева'], True)
            for x, width, count, fraction in [(0, 85, '2 напрямую', 'по 1/4'),
                                                (96, 85, '2: PC250', 'по 1/8'),
                                                (192, 86, '4: PC252', 'по 1/16')]:
                arrow(139, 202, x+width/2, 146)
                box(x, 92, width, 54, [count, fraction])
            box(19, 18, 240, 43, ['2 × 1/4 + 2 × 1/8 + 4 × 1/16 = 1',
                                  'до добавочных потерь'])


class ManualDoc(BaseDocTemplate):
    def __init__(self, path):
        super().__init__(str(path), pagesize=(W, H), leftMargin=MARGIN,
                         rightMargin=MARGIN, topMargin=47, bottomMargin=36,
                         title='Радиосеть ТРК «Эльбрус»: разбор с нуля',
                         author='Павел Абалаков · учебное руководство',
                         subject='Офлайн-подготовка к защите отправленного решения')
        self.chapter = None
        self.chapter_pages = {}
        self.section_pages = []
        self.addPageTemplates(PageTemplate(
            id='mobile', frames=[Frame(MARGIN, 36, CONTENT, H-83,
                                      leftPadding=0, rightPadding=0,
                                      topPadding=0, bottomPadding=0)],
            onPageEnd=self.decorate))

    def afterFlowable(self, item):
        if not isinstance(item, Heading):
            return
        self.chapter = item.chapter
        chapter_number, chapter_title = item.chapter
        destination = f'c{chapter_number}'
        if item.first:
            self.canv.bookmarkPage(destination)
            self.canv.addOutlineEntry(f'{chapter_number:02d}. {chapter_title}',
                                     destination, level=0, closed=True)
            self.chapter_pages[chapter_number] = self.page
        self.canv.bookmarkPage(item.section)
        self.canv.addOutlineEntry(item.getPlainText(), item.section, level=1,
                                 closed=False)
        self.section_pages.append((item.section, self.page, item.getPlainText()))

    def decorate(self, c, doc):
        c.saveState()
        c.setFillColor(GRAY)
        c.setFont('Guide', 8.5)
        if self.chapter:
            num, title = self.chapter
            label = f'{num:02d} / {title}'
        else:
            label = 'ТРК «Эльбрус» / Руководство к защите'
        c.drawString(MARGIN, H-25, label)
        c.setStrokeColor(RED)
        c.setLineWidth(1)
        c.line(MARGIN, H-34, MARGIN+32, H-34)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.line(MARGIN, 27, W-MARGIN, 27)
        c.setFillColor(GRAY)
        c.setFont('Guide', 9)
        c.drawString(MARGIN, 13, 'Оглавление')
        c.linkRect('', 'contents', (MARGIN, 9, MARGIN+82, 23), relative=0,
                   thickness=0)
        c.drawRightString(W-MARGIN, 13, str(doc.page))
        c.restoreState()


def parse_source():
    chapters = []
    chapter = None
    sections = []
    section = None
    for line in SOURCE.read_text(encoding='utf-8').splitlines():
        if line.startswith('# '):
            number, title = line[2:].split(' | ', 1)
            chapter = (int(number), title)
            chapters.append(chapter)
        elif line.startswith('## '):
            section = {'title': line[3:], 'chapter': chapter, 'lines': []}
            sections.append(section)
        elif section is not None:
            section['lines'].append(line)
    return chapters, sections


def paragraph(text, style=BODY):
    return Paragraph(rich(text), style)


def table(lines):
    rows = [[cell.strip() for cell in line.strip().strip('|').split('|')]
            for line in lines]
    rows = [row for row in rows if not all(re.fullmatch(r'[-: ]+', c) for c in row)]
    data = [[paragraph(cell, CELL) for cell in row] for row in rows]
    t = Table(data, colWidths=[CONTENT*.50, CONTENT*.50], hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TINT),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LINEABOVE', (0, 0), (-1, 0), .6, LINE),
        ('LINEBELOW', (0, -1), (-1, -1), .6, LINE),
        ('LINEBELOW', (0, 0), (-1, 0), .4, LINE),
    ]))
    return [t, Spacer(1, 12)]


def image_flow(path, maximum_height):
    source = path
    if path.suffix == '.pdf':
        raise ValueError('PDF image must select a slide explicitly')
    im = Image(str(source))
    factor = min(CONTENT/im.imageWidth, maximum_height/im.imageHeight)
    im.drawWidth = im.imageWidth * factor
    im.drawHeight = im.imageHeight * factor
    im.hAlign = 'CENTER'
    return im


def blocks(lines):
    items = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        if line.startswith('@diagram '):
            items.extend([Diagram(line.split()[1]), Spacer(1, 14)])
        elif line.startswith('@image '):
            items.extend([image_flow(ROOT / line[7:], 300), Spacer(1, 14)])
        elif line.startswith('@slide '):
            index = int(line.split()[1])-1
            with fitz.open(ROOT/'presentation/defense-preview.pdf') as slides:
                pix = slides[index].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                image_data = io.BytesIO(pix.tobytes('png'))
            im = Image(image_data, width=CONTENT, height=CONTENT*pix.height/pix.width)
            items.extend([im, Spacer(1, 14)])
        elif line.startswith('|'):
            table_lines = [line]
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1
            items.extend(table(table_lines))
        else:
            group = [line]
            while i < len(lines) and lines[i].strip():
                group.append(lines[i].strip())
                i += 1
            value = ' '.join(group)
            items.append(paragraph(value[2:] if value.startswith('> ') else value,
                                   CALLOUT if value.startswith('> ') else BODY))
    return items


def make_story(chapters, sections, chapter_pages):
    story = [Spacer(1, 39), paragraph('РАЗБОР ПРОЕКТА С НУЛЯ', SMALL), Spacer(1, 12)]
    cover = ParagraphStyle('cover', parent=TITLE, fontSize=31, leading=37)
    story += [paragraph('Радиосеть<br/>ТРК «Эльбрус»'.replace('<br/>', '\n'), cover),
              paragraph('От посетителей и радиоресурса до схемы, карт и ответов жюри.', BODY),
              Spacer(1, 25), paragraph('Для Павла Абалакова', BODY),
              paragraph('МТС Engineer Hack 2026<br/>Подготовка к защите 17 октября'.replace('<br/>', ' · '), SMALL),
              Spacer(1, 24), paragraph('Понятия → пример → расчёт → ответ на защите → самопроверка', CALLOUT),
              paragraph('Узкие страницы для iPhone. Интернет для чтения не нужен. Основано на отправленной версии 14.10.2026.', SMALL),
              PageBreak()]
    for toc_part in range(2):
        heading = Paragraph('Оглавление' + (' / продолжение' if toc_part else ''), TITLE)
        story.append(heading)
        if toc_part == 0:
            # A zero-height marker is kept next to the contents heading.
            class ContentsMarker(Flowable):
                width = 0
                height = 0
                def draw(self):
                    self.canv.bookmarkPage('contents')
            story.append(ContentsMarker())
        for number, title in chapters[toc_part*7:(toc_part+1)*7]:
            p = chapter_pages.get(number, 0)
            story.append(Paragraph(
                f'<link href="#c{number}" color="#202A36">'
                f'<font color="#D82035"><b>{number:02d}</b></font>  '
                f'{html.escape(title)} <font color="#626262">· {p}</font></link>', TOC))
        if toc_part == 1:
            story.append(paragraph('Нажми название главы. Ссылка внизу любой страницы возвращает к этому списку.', SMALL))
        story.append(PageBreak())
    seen = set()
    for i, section in enumerate(sections):
        chapter = section['chapter']
        first = chapter not in seen
        seen.add(chapter)
        story.append(Heading(section['title'], chapter, f's{i+1}', first))
        story.extend(blocks(section['lines']))
        if i < len(sections)-1:
            story.append(PageBreak())
    return story


def build():
    chapters, sections = parse_source()
    document = ManualDoc(OUTPUT)
    document.build(make_story(chapters, sections, {}))
    chapter_pages = document.chapter_pages.copy()
    document = ManualDoc(OUTPUT)
    document.build(make_story(chapters, sections, chapter_pages))
    if document.chapter_pages != chapter_pages:
        raise RuntimeError('Contents page numbering changed between passes')
    print(f'Built {OUTPUT.relative_to(ROOT)}: {document.page} pages, '
          f'{len(chapters)} chapters, {len(sections)} reading cards; '
          f'{OUTPUT.stat().st_size:,} bytes')
    print('Chapter pages:', document.chapter_pages)
    return document


if __name__ == '__main__':
    build()
