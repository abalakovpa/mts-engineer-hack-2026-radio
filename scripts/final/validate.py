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
    ants=data['antennas'];count=len(ants);assert count in (32,48) and len({a['id'] for a in ants})==count
    per_zone=count//4;subgroups=per_zone//4
    assert Counter(a['zone'] for a in ants)=={z:per_zone for z in range(1,5)}
    assert all(sum(a['zone']==z and a['subgroup']==g for a in ants)==4 for z in range(1,5) for g in range(1,subgroups+1))
    routes=data['trunks']+data['subfeeds']+data['drops']
    expected_routes=4+4*subgroups+count
    assert len(routes)==expected_routes
    assert len({t['id'] for t in routes})==expected_routes
    for r in routes:
        measured=sum(math.dist(a,b) for a,b in zip(r['points'],r['points'][1:]))
        assert math.isclose(measured,r['length'],abs_tol=1e-8),(r['id'],measured,r['length'])
    for cable,key in [('7/8','cable78_installed'),('1/2','cable12_installed')]:
        total=2*sum(r['length'] for r in routes if r['cable']==cable)
        assert math.isclose(total,data[key],abs_tol=1e-8)
    points=data['rf_points'];assert len(points)==count*12
    assert len({(r['antenna'],r['frequency_mhz'],r['d_horizontal_m']) for r in points})==count*12
    for a in ants:
        for f in (1800,2100,2600):
            vals=[r['rsrp_dbm'] for r in points if r['antenna']==a['id'] and r['frequency_mhz']==f]
            assert len(vals)==4 and all(u>v for u,v in zip(vals,vals[1:]))
    wb=load_workbook(ROOT/'equipment/bill-of-materials-draft.xlsx',data_only=True)
    assert wb['RF и RSRP'].max_row==count*12+1 and wb['Трассы'].max_row==expected_routes+1
    for row,r in zip(wb['RF и RSRP'].iter_rows(min_row=2,values_only=True),points):
        assert tuple(row[:3])==(r['antenna'],r['frequency_mhz'],r['d_horizontal_m'])
        assert math.isclose(row[-1],r['rsrp_dbm'],abs_tol=1e-8)
    spec=list(wb['Спецификация'].iter_rows(min_row=2,values_only=True))
    expected={'In06':count,'PC211':8,'PC221':6,'PC250':9 if count==32 else 1,
              'PC251':0 if count==32 else 8,'PC252':subgroups*8}
    for name,quantity in expected.items():
        matched=[r for r in spec if r[1].startswith(name)]
        if quantity:assert len(matched)==1 and matched[0][3]==quantity,(name,matched)
        else:assert not matched,(name,matched)
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
    coverage_file=ROOT/'design/final/coverage/coverage-report.json'
    if count==32:assert coverage_file.exists(), 'Actual coverage report required for selected design'
    if coverage_file.exists():
        coverage=json.loads(coverage_file.read_text())
        assert coverage['antennas']==count
        assert math.isclose(coverage['located_reference_m2'],2051.56,abs_tol=1e-6)
        assert coverage['unknown_reference_m2']==45.52
        assert len(coverage['scenarios'])==27
        by_key={(r['scenario'],r['frequency_mhz']):r for r in coverage['scenarios']}
        for f in (1800,2100,2600):
            nominal=by_key[('P1_n2.5',f)]['reference_percent_2100']
            assert nominal<=2051.56/2100*100+1e-6
            for name in ('P1_n3','P1_extra_RF_3dB','P1_closed_gaps','P1_two_ports_total','P2_carrier23','P1_cable78_plus5pct','P1_geometry_uncertain_fail'):
                assert by_key[(name,f)]['reference_percent_2100']<=nominal+1e-6
            assert by_key[('P1_n2',f)]['reference_percent_2100']>=nominal-1e-6
        assert wb['Покрытие сценарии'].max_row==28
        assert coverage['design_fingerprint']==hashlib.sha256((ROOT/'design/final/candidate.json').read_bytes()).hexdigest()
        for row,result in zip(wb['Покрытие сценарии'].iter_rows(min_row=2,values_only=True),coverage['scenarios']):
            assert row[0]==result['scenario'] and row[1]==result['frequency_mhz']
            assert math.isclose(row[5],result['reference_percent_2100'],abs_tol=1e-8)
            assert result['passed_95']==(result['reference_percent_2100']>=95)
        import numpy as np
        with np.load(ROOT/'design/final/coverage/validated-fields.npz') as field:
            assert len(field['points'])==coverage['receiver_cells']
            assert math.isclose(float(field['weights'].sum()),2051.56,abs_tol=1e-6)
            for f in (1800,2100,2600):
                predicted=float(field['weights'][field[f'rsrp_{f}']>-90].sum()/2100*100)
                assert math.isclose(predicted,by_key[('P1_n2.5',f)]['reference_percent_2100'],abs_tol=1e-8)
        resolution=json.loads((ROOT/'design/final/coverage/resolution-0.5.json').read_text())
        assert resolution['design_fingerprint']==coverage['design_fingerprint']
    print(f'PASS: 6 source hashes; 7 capacity variants; {count} antennas; {expected_routes} routes ×2; {count*12} RF points; XLSX quantities; 6 slides')
    print(f'RF scenario at 20 m on weakest B7 branch: {worst:.2f} dBm; KPI readiness NOT established')

if __name__=='__main__':main()
