#!/usr/bin/env python3
"""Control the changed RF layout on identical geometry and test short joins."""
from pathlib import Path
import json
import math
import subprocess
import sys
import tempfile
import numpy as np
from coverage import fields

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'design/final/revision'

def main():
    current=json.loads((ROOT/'design/final/candidate.json').read_text())
    baseline=json.loads((OUT/'baseline-32-candidate.json').read_text())
    model=json.loads((ROOT/'design/final/coverage/area-model.json').read_text())
    with tempfile.TemporaryDirectory(prefix='radio-controls-',dir='/tmp') as temp:
        tmp=Path(temp)
        subprocess.run([sys.executable,str(ROOT/'scripts/final/prepare_coverage_model.py'),
                        '--join-max','.15','--output-dir',str(tmp/'area015')],check=True)
        alternate=json.loads((tmp/'area015/area-model.json').read_text());results=[]
        for name,area,design,step in [('old_layout_new_geometry',model,baseline,.25),('current_layout_join015',alternate,current,.5)]:
            field=fields(area,design['antennas'],step,cache_dir=tmp/name)
            loss=np.array([next(r['total_loss_db'] for r in design['rf_points'] if r['frequency_mhz']==2600 and r['antenna']==a['id']) for a in design['antennas']])
            signal=6-loss[:,None]-(20*math.log10(2600)-27.55+25*np.log10(field['radius']))-field['wall']-field['columns'];scores={}
            for mode,extra,closed in [('nominal',0,False),('reserve3',3,False),('closed_reserve3',3,True)]:
                best=(signal-extra-(field['closed'] if closed else 0)).max(axis=0)
                scores[mode]=float(field['weights'][best>-90].sum()/21)
            best=(signal-5*np.log10(field['radius'])).max(0)
            scores['n3']=float(field['weights'][best>-90].sum()/21)
            results.append(dict(name=name,step_m=step,scores=scores,groups=len(area['groups']),
                                uncertain_rooms=[g['rooms'] for g in area['groups'] if abs(g['relative_area_difference'])>.1],
                                area_join_max_m=area['metadata']['area_join_max_m']))
            print(results[-1],flush=True)
        (OUT/'control-comparison.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
