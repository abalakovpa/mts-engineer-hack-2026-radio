#!/usr/bin/env python3
"""Check the selected design against a smaller area-join tolerance."""
from pathlib import Path
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import numpy as np
from coverage import fields

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'design/final/coverage'

def main():
    selected = ROOT / 'design/final/candidate.json'
    current = json.loads(selected.read_text())
    with tempfile.TemporaryDirectory(prefix='radio-geometry-', dir='/tmp') as temp:
        folder = Path(temp)
        subprocess.run([sys.executable, str(ROOT/'scripts/final/prepare_coverage_model.py'),
                        '--join-max', '.15', '--output-dir', str(folder/'area')], check=True)
        model = json.loads((folder/'area/area-model.json').read_text())
        field = fields(model, current['antennas'], .5, cache_dir=folder/'rays')
        loss = np.array([next(r['total_loss_db'] for r in current['rf_points']
                             if r['frequency_mhz'] == 2600 and r['antenna'] == a['id'])
                         for a in current['antennas']])
        signal = (6-loss[:, None]-(20*math.log10(2600)-27.55+25*np.log10(field['radius']))
                  -field['wall']-field['columns'])
        variants = {'nominal': signal, 'reserve3': signal-3,
                    'closed_reserve3': signal-field['closed']-3,
                    'n3': signal-5*np.log10(field['radius'])}
        scores = {name: float(field['weights'][value.max(0) > -90].sum()/21)
                  for name, value in variants.items()}
        result = dict(step_m=.5, scores=scores, groups=len(model['groups']),
                      uncertain_rooms=[g['rooms'] for g in model['groups'] if abs(g['relative_area_difference']) > .1],
                      area_join_max_m=model['metadata']['area_join_max_m'],
                      design_fingerprint=hashlib.sha256(selected.read_bytes()).hexdigest(),
                      area_model_sha256=hashlib.sha256((OUT/'area-model.json').read_bytes()).hexdigest())
        (OUT/'geometry-control.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
