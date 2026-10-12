#!/usr/bin/env python3
"""Воспроизводимая арифметика финала; не модель измеренного покрытия."""
from decimal import Decimal as D, ROUND_CEILING, ROUND_FLOOR
from itertools import combinations
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/final/calculation-data'

def ceil(x):
    return int(x.to_integral_value(rounding=ROUND_CEILING))

def floor(x):
    return int(x.to_integral_value(rounding=ROUND_FLOOR))

def erlang(a, n):
    b = D(1)
    for i in range(1, n + 1):
        b = a*b/(i+a*b)
    return b

def capacity():
    eta = D('.84') * (D(6)*567/1024) * D('1.6') * D('.8') * D('.9') * D('.98')
    bands = [('B3', D(20)), ('B1', D(15)), ('B7', D(10))]
    rows = []
    for size in (1, 2, 3):
        for indexes in combinations(range(3), size):
            cs = [bands[i][1]*eta*D('.8') for i in indexes]
            m = sum(floor(c/8) for c in cs)
            m_ca = floor(sum(cs)/8)
            old = ceil(D('1.1')*288/m)
            legacy = ceil(D('1.1')*13/m)
            physical = 1 if 13 <= m else legacy
            assert ceil(D('1.1')*288/old) <= m
            assert ceil(D('1.1')*288/(old-1)) > m
            assert (13 if physical == 1 else ceil(D('1.1')*13/physical)) <= m
            if physical > 1:
                previous = 13 if physical == 2 else ceil(D('1.1')*13/(physical-1))
                assert previous > m
            rows.append(dict(bands='+'.join(bands[i][0] for i in indexes),
                             capacity_mbps=str(sum(cs)), users_no_ca=m, users_ca=m_ca,
                             online_sectors=old, final_legacy_sectors=legacy,
                             final_one_pool_sectors=physical))
    assert eta == D('3.1505922')
    assert [r['online_sectors'] for r in rows] == [53,80,106,32,36,46,25]
    assert [r['final_one_pool_sectors'] for r in rows] == [3,4,5,2,2,3,1]
    assert ceil(D(360)*D('.35')*D('.1')) == 13
    assert ceil(D(360)*D('.35')) == 126  # avoid truncating binary floats to 125
    assert erlang(D('7.5'),13) > D('.015') >= erlang(D('7.5'),14)
    return rows

def reference_points():
    rows = []
    for f, prb in ((1800,100),(2100,75),(2600,50)):
        # Scenario: 23 dBm sums 2*PRB CRS subcarriers on one port in a CRS symbol.
        pilot_re = 23 - 10*math.log10(2*prb)
        for d in (5,10,15,20):
            distance = math.hypot(d,5.5)
            for n in (2,2.5,3):
                loss = 20*math.log10(f)-27.55+10*n*math.log10(distance)
                rows.append(dict(frequency_mhz=f, horizontal_m=d, spatial_m=distance,
                                 exponent=n, crs_re_dbm=pilot_re,
                                 propagation_db=loss,
                                 rsrp_zero_feed_zero_wall_dbm=pilot_re+3-loss))
    return rows

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = dict(capacity=capacity(), reference_points=reference_points())
    (OUT/'arithmetic.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print('OK: 7 combinations, S/S-1, RRC=126, buffer=13, Erlang B, 36 reference scenarios')

if __name__ == '__main__':
    main()
