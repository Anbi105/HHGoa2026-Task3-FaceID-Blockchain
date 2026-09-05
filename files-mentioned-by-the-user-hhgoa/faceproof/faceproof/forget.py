from pathlib import Path
def forget(run):
    destroyed=[]
    for name in ("salt.key","bundle.json","proofs.json"):
        p=Path(run)/name
        if p.exists(): p.unlink(); destroyed.append(name)
    print("Destroyed: "+", ".join(destroyed)+". Blockchain anchor was not and cannot be deleted.")
