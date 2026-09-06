import json, time
from pathlib import Path
def event(path, stage, name, **evidence):
    row={"timestamp": time.time(), "stage":stage, "event":name, "evidence":evidence}
    with Path(path).open("a", encoding="utf-8") as f: f.write(json.dumps(row, sort_keys=True)+"\n")
    print(f"{stage} {name}" + (" " + " ".join(f"{k}={v}" for k,v in evidence.items()) if evidence else ""))
