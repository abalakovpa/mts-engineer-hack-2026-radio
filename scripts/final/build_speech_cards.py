"""Build six phone-readable rehearsal cards; never touch submission files."""
from pathlib import Path
import re

from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_JUSTIFY

from build_learning_manual import (
    W, MARGIN, CONTENT, RED, INK, GRAY, LINE, rich,
)

H = 840

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'presentation/speech-cards.md'
OUTPUT = ROOT / 'presentation/speech-cards.pdf'

SPEECH = ParagraphStyle('speech', fontName='Guide', fontSize=13.7,
                        leading=18.7, textColor=INK, spaceAfter=10)
TITLE = ParagraphStyle('title', parent=SPEECH, fontName='GuideBold',
                       fontSize=22, leading=26)
NOTE = ParagraphStyle('note', parent=SPEECH, fontSize=10.8, leading=14.4)
ANCHOR = ParagraphStyle('anchor', parent=SPEECH, fontSize=11.3, leading=15.2)


def parse():
    cards = []
    for block in re.split(r'^## ', SOURCE.read_text(), flags=re.M)[1:]:
        header, _, body = block.partition('\n')
        speech, _, notes = body.partition('### Опоры')
        timing = re.search(r'План: (\d+) секунд', speech)
        seconds = int(timing.group(1))
        speech = speech.replace(timing.group(0), '').strip()
        paragraphs = [p.replace('\n', ' ') for p in speech.split('\n\n') if p.strip()]
        anchors = [line[2:] for line in notes.splitlines() if line.startswith('- ')]
        cards.append((header, seconds, paragraphs, anchors))
    assert len(cards) == 6
    assert sum(card[1] for card in cards) == 240
    return cards


def build():
    c = canvas.Canvas(str(OUTPUT), pagesize=(W, H), pageCompression=1,
                      initialFontName='Guide', initialFontSize=13.7)
    c.setTitle('Текст защиты — шесть слайдов')
    c.setAuthor('Павел Абалаков')
    c.setSubject('Короткий текст и опоры для репетиции на четыре минуты')
    cards = parse()
    elapsed = 0
    total_words = 0
    for number, (header, seconds, paragraphs, anchors) in enumerate(cards, 1):
        c.bookmarkPage(f'slide{number}')
        c.addOutlineEntry(f'Слайд {header}', f'slide{number}', 0)
        c.setFillColor(GRAY)
        c.setFont('Guide', 9)
        c.drawString(MARGIN, H-25, f'ТЕКСТ ЗАЩИТЫ / СЛАЙД {number} ИЗ 6')
        c.setStrokeColor(RED)
        c.setLineWidth(1.2)
        c.line(MARGIN, H-35, MARGIN+35, H-35)
        y = H-52

        def draw(text, style, gap=10):
            nonlocal y
            p = Paragraph(rich(text), style)
            _, height = p.wrap(CONTENT, H)
            if y-height < 43:
                raise RuntimeError(f'Card {number} overflows: {text[:45]}')
            p.drawOn(c, MARGIN, y-height)
            y -= height+gap

        draw(header, TITLE, 8)
        start = f'{elapsed//60}:{elapsed%60:02d}'
        elapsed += seconds
        end = f'{elapsed//60}:{elapsed%60:02d}'
        draw(f'Ориентир: {seconds} с · общий план {start}–{end}', NOTE, 16)
        for paragraph in paragraphs:
            draw(paragraph, SPEECH, 10)
        y -= 4
        c.setStrokeColor(LINE)
        c.setLineWidth(.6)
        c.line(MARGIN, y, W-MARGIN, y)
        y -= 20
        draw('ОПОРЫ ДЛЯ ПОВТОРЕНИЯ',
             ParagraphStyle('label', parent=NOTE, fontName='GuideBold',
                            textColor=RED), 8)
        for anchor in anchors:
            draw('• '+anchor, ANCHOR, 5)
        c.setStrokeColor(LINE)
        c.line(MARGIN, 29, W-MARGIN, 29)
        c.setFont('Guide', 8.4)
        c.setFillColor(GRAY)
        c.drawString(MARGIN, 15, 'Текст для репетиции · время проверить с таймером')
        c.drawRightString(W-MARGIN, 15, str(number))
        c.showPage()
        words = sum(len(p.split()) for p in paragraphs)
        total_words += words
        print(f'Slide {number}: {words} words; last content y={y:.1f}')
    c.save()
    print(f'Built {OUTPUT.relative_to(ROOT)}: 6 pages; '
          f'{total_words} speech words; {OUTPUT.stat().st_size:,} bytes')


def build_a4():
    """A conventional A4 handout, two consecutive slides on each page."""
    output = ROOT / 'presentation/speech-cards-a4.pdf'
    width, height = A4
    margin = 50
    available = width - 2 * margin
    speech = ParagraphStyle('a4-speech', fontName='Guide', fontSize=12.5,
                            leading=17, alignment=TA_JUSTIFY, textColor=INK)
    title = ParagraphStyle('a4-title', parent=speech, fontName='GuideBold',
                           fontSize=16, leading=20, alignment=0)
    note = ParagraphStyle('a4-note', parent=speech, fontSize=9.5,
                          leading=12.5, textColor=GRAY, alignment=0)
    anchor = ParagraphStyle('a4-anchor', parent=speech, fontSize=10.3,
                            leading=13.5, alignment=0)
    c = canvas.Canvas(str(output), pagesize=A4, pageCompression=1,
                      initialFontName='Guide', initialFontSize=12.5)
    c.setTitle('Текст выступления — шесть слайдов, A4')
    c.setAuthor('Павел Абалаков')
    cards = parse()
    elapsed = 0
    y = 0

    def draw(text, style, gap=6):
        nonlocal y
        paragraph = Paragraph(rich(text), style)
        _, required = paragraph.wrap(available, height)
        if y-required < 44:
            raise RuntimeError(f'A4 page overflow: {text[:60]}')
        paragraph.drawOn(c, margin, y-required)
        y -= required + gap

    for index, (header, seconds, paragraphs, anchors) in enumerate(cards):
        if index % 2 == 0:
            c.setFillColor(INK)
            c.setFont('GuideBold', 14)
            c.drawString(margin, height-34, 'Текст выступления')
            c.setFillColor(GRAY)
            c.setFont('Guide', 9)
            c.drawRightString(width-margin, height-34, 'МТС Engineer Hack · 4 минуты')
            c.setStrokeColor(RED)
            c.setLineWidth(1)
            c.line(margin, height-45, width-margin, height-45)
            y = height-61
        else:
            y -= 5
            c.setStrokeColor(LINE)
            c.setLineWidth(.5)
            c.line(margin, y, width-margin, y)
            y -= 19
        c.bookmarkPage(f'slide{index+1}')
        c.addOutlineEntry(f'Слайд {header}', f'slide{index+1}', 0)
        draw(header, title, 3)
        start = f'{elapsed//60}:{elapsed%60:02d}'
        elapsed += seconds
        end = f'{elapsed//60}:{elapsed%60:02d}'
        draw(f'Ориентир: {seconds} с · общий план {start}–{end}', note, 9)
        for paragraph in paragraphs:
            draw(paragraph, speech, 6)
        draw('ОПОРЫ ДЛЯ ПОВТОРЕНИЯ — НЕ ВХОДЯТ В ТЕКСТ ДОКЛАДА',
             ParagraphStyle('a4-label', parent=note, fontName='GuideBold',
                            fontSize=9, textColor=RED), 4)
        for item in anchors:
            draw('• '+item, anchor, 2)
        if index % 2 == 1:
            c.setStrokeColor(LINE)
            c.setLineWidth(.5)
            c.line(margin, 32, width-margin, 32)
            c.setFillColor(GRAY)
            c.setFont('Guide', 8.5)
            c.drawString(margin, 19, 'Тайминг плановый. Перед защитой проверить с таймером.')
            c.drawRightString(width-margin, 19, f'{index//2+1} / 3')
            print(f'A4 page {index//2+1}: last content y={y:.1f}')
            c.showPage()
    c.save()
    print(f'Built {output.relative_to(ROOT)}: 3 A4 pages; {output.stat().st_size:,} bytes')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--a4', action='store_true', help='Build the A4 laptop/print edition')
    arguments = parser.parse_args()
    build_a4() if arguments.a4 else build()
