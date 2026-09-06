import json
from itertools import combinations
from pathlib import Path
import numpy as np
from .face import probe_image

def calibrate(root, config, output="data/calibration.json"):
    groups={}
    for subject in Path(root).iterdir():
        if subject.is_dir(): groups[subject.name]=[probe_image(p, config).embedding for p in subject.glob("*")]
    genuine=[float(a@b) for vectors in groups.values() for a,b in combinations(vectors,2)]
    impostor=[float(a@b) for x,y in combinations(groups.values(),2) for a in x for b in y]
    if not genuine or not impostor: raise ValueError("calibration needs at least two subjects with two images each")
    accept=max(impostor)+.03
    result={"genuine_n":len(genuine),"genuine_mean":float(np.mean(genuine)),"genuine_min":min(genuine),"impostor_n":len(impostor),"impostor_mean":float(np.mean(impostor)),"impostor_max":max(impostor),"suggested_accept_at":accept,"true_accept_rate":sum(x>=accept for x in genuine)/len(genuine),"separation":min(genuine)-max(impostor)}
    Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8"); return result

if __name__ == "__main__":
    from .config import load_config
    print(json.dumps(calibrate("data/calib", load_config()), indent=2))
