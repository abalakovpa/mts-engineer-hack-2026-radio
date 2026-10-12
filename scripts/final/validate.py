#!/usr/bin/env python3
"""Cross-check generated artifacts and source integrity; do not certify KPI."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import math
import zipfile

from openpyxl import load_workbook
from pptx import Presentation
from calculate import capacity

ROOT=Path(__file__).resolve().parents[2]
HASHES={
    'Кабель LCF78-50JA-A0.pdf':'b341944deccf6ebebfae2dda0c94b13c62b7794b52d848265328377c858ac739',
    'Параметры планировки и затуханий.png':'aee4bd1e84094f74f7c38f02bddccb99785cf87a77fb1047cb1fbf392bf9e593',
    'Перечень вспомогательного оборудования.xlsx':'b92688685fc219b924e9cf9a4fa47147c13ae18747d3cc75691412e7d1b39cb0',
    'Планировка первого этажа.dwg':'c5f7b901edcdb073f1248ab7dc169d6b85c4b08f80b6cef5e137ef67635f00d7',
    'Планировка первого этажа.png':'13760675a4151a114537d31cbef25631eb8de775d5e3f5289adb034db6891c96',
    'Кабель LCF12-50J.pdf':'047726c01e5ee745efc214c7a5b47d274fb9d2f5e7e984a25bb4bcb75b7fc6bd',
}

def main():
    for name,digest in HASHES.items():
        actual=hashlib.sha256((ROOT/'docs/final/source-materials'/name).read_bytes()).hexdigest()
        assert actual==digest,name
    capacity()  # Independent S/S-1 and exact arithmetic checks.
    data=json.loads((ROOT/'design/final/candidate.json').read_text())
    ants=data['antennas'];assert len(ants)==48 and len({a['id'] for a in ants})==48
    assert Counter(a['zone'] for a in ants)=={1:12,2:12,3:12,4:12}
    assert all(sum(a['zone']==z and a['subgroup']==g for a in ants)==4 for z in range(1,5) for g in range(1,4))
    routes=data['trunks']+data['subfeeds']+data['drops']
    assert len(routes)==64
    assert len({t['id'] for t in routes})==64
    for r in routes:
        measured=sum(math.dist(a,b) for a,b in zip(r['points'],r['points'][1:]))
        assert math.isclose(measured,r['length'],abs_tol=1e-8),(r['id'],measured,r['length'])
    for cable,key in [('7/8','cable78_installed'),('1/2','cable12_installed')]:
        total=2*sum(r['length'] for r in routes if r['cable']==cable)
        assert math.isclose(total,data[key],abs_tol=1e-8)
    points=data['rf_points'];assert len(points)==576
    assert len({(r['antenna'],r['frequency_mhz'],r['d_horizontal_m']) for r in points})==576
    for a in ants:
        for f in (1800,2100,2600):
            vals=[r['rsrp_dbm'] for r in points if r['antenna']==a['id'] and r['frequency_mhz']==f]
            assert len(vals)==4 and all(u>v for u,v in zip(vals,vals[1:]))
    wb=load_workbook(ROOT/'equipment/bill-of-materials-draft.xlsx',data_only=True)
    assert wb['RF и RSRP'].max_row==577 and wb['Трассы'].max_row==65
    for row,r in zip(wb['RF и RSRP'].iter_rows(min_row=2,values_only=True),points):
        assert tuple(row[:3])==(r['antenna'],r['frequency_mhz'],r['d_horizontal_m'])
        assert math.isclose(row[-1],r['rsrp_dbm'],abs_tol=1e-8)
    spec=list(wb['Спецификация'].iter_rows(min_row=2,values_only=True))
    expected={'In06':48,'PC211':8,'PC221':6,'PC250':1,'PC251':8,'PC252':24}
    for name,count in expected.items():
        matched=[r for r in spec if r[1].startswith(name)]
        assert len(matched)==1 and matched[0][3]==count,(name,matched)
    for token,cable,key in [('1/2','1/2','cable12_installed'),('7/8','7/8','cable78_installed')]:
        feeder=next(r for r in spec if r[1].startswith('Фидер') and token in r[1])
        connector=next(r for r in spec if r[1].startswith('Разъем') and token in r[1])
        assert feeder[3]==math.ceil(data[key]*1.1)
        assert connector[3]==4*sum(r['cable']==cable for r in routes)
    prs=Presentation(ROOT/'presentation/defense-draft.pptx')
    assert len(prs.slides)==6
    for slide in prs.slides:
        assert slide.has_notes_slide
        for shape in slide.shapes:
            assert shape.left>=0 and shape.top>=0
            assert shape.left+shape.width<=prs.slide_width and shape.top+shape.height<=prs.slide_height
    for f in (ROOT/'equipment/bill-of-materials-draft.xlsx',ROOT/'presentation/defense-draft.pptx'):
        with zipfile.ZipFile(f) as z:assert z.testzip() is None
    worst=min(r['rsrp_dbm'] for r in points if r['frequency_mhz']==2600 and r['d_horizontal_m']==20)
    assert worst<-90, 'Report must be revisited: previously failed RF scenario has changed'
    print('PASS: 6 source hashes; 7 capacity variants; 48 antennas; 64 routes ×2; 576 RF points; XLSX quantities; 6 slides')
    print(f'RF scenario at 20 m on weakest B7 branch: {worst:.2f} dBm; KPI readiness NOT established')

if __name__=='__main__':main()
