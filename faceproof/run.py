"""Stage 3 command surface and end-to-end demo driver (S24).

This wraps - it does not replace - Person 1's ``faceproof.cli``.  Stage 1
(``probe``) and consent management are delegated straight to it; Stage 3
adds discovery-consumption, bundle assembly, anchoring, verification and
the tamper demo around that existing interface.

    python -m faceproof.run banner
    python -m faceproof.run index-stats
    python -m faceproof.run probe   --img data/demo/synthetic_face.jpg --subject alice
    python -m faceproof.run stage2  --run-dir out/run-<id>            # Person 2 discovery -> stage2.json
    python -m faceproof.run search  --run-dir out/run-<id>            # or --img/--subject
    python -m faceproof.run search  --run-dir out/run-<id> --real-stage2   # run Person 2 first
    python -m faceproof.run anchor  --run-dir out/run-<id>
    python -m faceproof.run verify  --run-dir out/run-<id> [--chain]
    python -m faceproof.run tamper  --run-dir out/run-<id>
    python -m faceproof.run abstain
    python -m faceproof.run forget  --subject alice
    python -m faceproof.run deploy   |   anvil   |   demo
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from faceproof.bundle import (
    BUNDLE_FILENAME,
    PROOFS_FILENAME,
    AbstainError,
    assemble_bundle,
    recompute_root,
    write_abstain,
)
from faceproof.config import banner, cfg
from faceproof.handoff import load_record
from faceproof.manifest import Manifest, new_run_id
from faceproof.stage2_adapter import load_stage2
from faceproof.verify import tamper_demonstration, verify_run

console = Console()
_CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "contracts"
_ANVIL_ACCT0_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _latest_run_dir() -> Optional[Path]:
    runs = sorted(cfg.out_dir.glob("run-*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return runs[0] if runs else None


def _resolve_run_dir(run_dir: Optional[str]) -> Path:
    if run_dir:
        return Path(run_dir)
    latest = _latest_run_dir()
    if latest is None:
        console.print("[red]no run directory given and none found under out/[/red]")
        raise SystemExit(3)
    console.print(f"[dim]using latest run: {latest}[/dim]")
    return latest


def _run_stage1(image: str, subject: str) -> Path:
    """Delegate Stage 1 to Person 1's CLI, then return its run directory."""
    from faceproof.cli import cmd_probe

    run_id = new_run_id()
    code = cmd_probe(image, subject, run_id=run_id)
    run_dir = cfg.run_dir(run_id)
    if code != 0:
        raise AbstainError(f"Stage 1 did not accept the probe (cli exit {code})")
    return run_dir


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_banner(_: argparse.Namespace) -> int:
    console.print(banner())
    return 0


def cmd_index_stats(_: argparse.Namespace) -> int:
    snap = cfg.data_dir / "index" / "snapshot.json"
    if snap.exists():
        console.print(snap.read_text(encoding="utf-8"))
    else:
        console.print(f"[yellow]no index snapshot at {snap}[/yellow]")
        console.print("Stage 2 (Person 2) owns index construction; Stage 3 only reads its id.")
    return 0


def cmd_stage2(args: argparse.Namespace) -> int:
    """Run Person 2's real Channel A / Channel B / fusion; write stage2.json."""
    from faceproof.stage2_bridge import Stage2Unavailable, index_stats, run_stage2

    run_dir = _resolve_run_dir(args.run_dir)
    stats = index_stats()
    if stats:
        console.print("[cyan]Stage 2 index[/cyan]")
        console.print(json.dumps(stats, indent=2, sort_keys=True))
    else:
        console.print("[yellow]no local FAISS index under data/index/[/yellow] - "
                      "Channel A cannot retrieve; Person 2's fusion will ABSTAIN.")
    try:
        payload = run_stage2(run_dir)
    except Stage2Unavailable as exc:
        console.print(f"[red]{exc}[/red]")
        return 3
    console.print(
        f"[green]stage2.json written[/green]  outcome={payload['fusion_outcome']}  "
        f"channels={payload['channels_used']}"
    )
    return 0 if payload["fusion_outcome"] != "ABSTAIN" else 1


def cmd_probe(args: argparse.Namespace) -> int:
    from faceproof.cli import cmd_probe as _p

    if not args.img:
        console.print("[red]--img is required for probe[/red]")
        return 3
    return _p(args.img, args.subject)


def cmd_search(args: argparse.Namespace) -> int:
    """Stage 1 handoff -> Stage 2 result -> 8-group bundle (+ optional anchor)."""
    if args.run_dir:
        run_dir = Path(args.run_dir)
    elif args.img:
        try:
            run_dir = _run_stage1(args.img, args.subject)
        except AbstainError as exc:
            console.print(f"[yellow]ABSTAIN: {exc}[/yellow]")
            return 1
    else:
        run_dir = _resolve_run_dir(None)

    manifest = Manifest(run_dir)
    stage1 = load_record(run_dir)
    if stage1.get("status") == "rejected":
        write_abstain(run_dir, stage1, {"fusion_outcome": "ABSTAIN", "source": "stage1-reject"})
        manifest.log("STAGE 3", "ABSTAIN", reason="stage1_rejected")
        console.print("[yellow]ABSTAIN: Stage 1 rejected this probe; no bundle.[/yellow]")
        return 1

    if getattr(args, "real_stage2", False):
        from faceproof.stage2_bridge import Stage2Unavailable, run_stage2

        try:
            p2 = run_stage2(run_dir)
            console.print(
                f"[cyan]Stage 2 (Person 2 bridge)[/cyan]  outcome={p2['fusion_outcome']}  "
                f"channels={p2['channels_used']}"
            )
        except Stage2Unavailable as exc:
            console.print(f"[yellow]real Stage 2 unavailable: {exc}[/yellow]")

    stage2 = load_stage2(run_dir)
    manifest.log(
        "STAGE 2", "consumed", source=stage2["source"], outcome=stage2["fusion_outcome"]
    )

    try:
        bundle, _proofs = assemble_bundle(run_dir, stage1, stage2)
    except AbstainError as exc:
        write_abstain(run_dir, stage1, stage2)
        manifest.log("STAGE 3", "ABSTAIN", reason=str(exc))
        console.print(f"[yellow]ABSTAIN: {exc}[/yellow]")
        return 1

    root = recompute_root(run_dir / BUNDLE_FILENAME)
    manifest.artifact("STAGE 3", run_dir / BUNDLE_FILENAME)
    manifest.artifact("STAGE 3", run_dir / PROOFS_FILENAME)
    manifest.log("STAGE 3", "merkle_root", root=root)
    console.print(f"[green]bundle assembled - 8 groups[/green]  root={root}")

    if args.anchor:
        from faceproof.anchor import anchor as _anchor

        try:
            _anchor(run_dir)
        except Exception as exc:
            console.print(f"[yellow]anchor skipped: {exc}[/yellow]")

    verify_run(run_dir, check_chain=args.anchor)
    if not args.no_tamper:
        tamper_demonstration(run_dir)
    return 0


def cmd_anchor(args: argparse.Namespace) -> int:
    from faceproof.anchor import anchor as _anchor

    _anchor(_resolve_run_dir(args.run_dir))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    return 0 if verify_run(_resolve_run_dir(args.run_dir), check_chain=args.chain) else 1


def cmd_tamper(args: argparse.Namespace) -> int:
    orig_ok, detected = tamper_demonstration(_resolve_run_dir(args.run_dir))
    return 0 if (orig_ok and detected) else 1


def cmd_abstain(args: argparse.Namespace) -> int:
    """Show the abstain path: a probe the quality gate rejects yields no bundle."""
    from faceproof.cli import cmd_probe as _p

    img = args.img or str(cfg.data_dir / "demo" / "noface.jpg")
    code = _p(img, args.subject)
    console.print(
        f"[cyan]probe exit {code}[/cyan] - Stage 3 builds no bundle and anchors nothing."
    )
    return 0


def cmd_forget(args: argparse.Namespace) -> int:
    from faceproof.cli import cmd_consent_revoke

    return cmd_consent_revoke(args.subject)


def _forge(*forge_args: str) -> int:
    try:
        return subprocess.call(["forge", *forge_args], cwd=str(_CONTRACTS_DIR))
    except FileNotFoundError:
        console.print("[red]forge not found[/red] - install Foundry (https://getfoundry.sh)")
        console.print(f"would run: forge {' '.join(forge_args)}  (cwd={_CONTRACTS_DIR})")
        return 127


def cmd_deploy(args: argparse.Namespace) -> int:
    rpc = args.rpc or "http://127.0.0.1:8545"
    key = args.private_key or _ANVIL_ACCT0_KEY  # public Anvil dev key; override for real chains
    _forge("build")
    return _forge(
        "script", "script/Deploy.s.sol:DeployScript",
        "--rpc-url", rpc, "--broadcast", "--private-key", key,
    )


def cmd_anvil(_: argparse.Namespace) -> int:
    try:
        return subprocess.call(["anvil"])
    except FileNotFoundError:
        console.print("[red]anvil not found[/red] - install Foundry")
        return 127


def cmd_demo(args: argparse.Namespace) -> int:
    console.rule("banner")
    cmd_banner(args)
    console.rule("search (Stage 1 handoff -> Stage 2 -> bundle)")
    ns = argparse.Namespace(
        run_dir=args.run_dir, img=args.img, subject=args.subject,
        anchor=args.anchor, no_tamper=False, chain=args.anchor,
        real_stage2=getattr(args, "real_stage2", False),
    )
    rc = cmd_search(ns)
    if rc == 0 and not args.anchor:
        console.rule("verify (local)")
        verify_run(_resolve_run_dir(args.run_dir), check_chain=False)
    return rc


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m faceproof.run", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def with_common(sp, *, img=False, run_dir=False, anchor=False, chain=False, subject=False,
                    real_stage2=False):
        if img:
            sp.add_argument("--img", "--image", dest="img", default=None)
        if subject or img:
            sp.add_argument("--subject", "-s", default="alice")
        if run_dir:
            sp.add_argument("--run-dir", dest="run_dir", default=None)
        if real_stage2:
            sp.add_argument(
                "--real-stage2", dest="real_stage2", action="store_true",
                help="run Person 2's real discovery/fusion first (writes stage2.json)",
            )
        if anchor:
            sp.add_argument("--anchor", action="store_true")
            sp.add_argument("--no-tamper", dest="no_tamper", action="store_true")
        if chain:
            sp.add_argument("--chain", action="store_true", help="also check the on-chain anchor")
        return sp

    with_common(sub.add_parser("banner", help="print the public pipeline config"))
    with_common(sub.add_parser("index-stats", help="print the index snapshot id/stats"))
    with_common(sub.add_parser("probe", help="Stage 1 probe (delegates to faceproof.cli)"), img=True)
    with_common(sub.add_parser("stage2", help="Person 2 discovery/fusion -> stage2.json"), run_dir=True)
    with_common(sub.add_parser("search", help="assemble the evidence bundle"),
                img=True, run_dir=True, anchor=True, real_stage2=True)
    with_common(sub.add_parser("anchor", help="anchor the bundle root on-chain"), run_dir=True)
    with_common(sub.add_parser("verify", help="independent re-verification"), run_dir=True, chain=True)
    with_common(sub.add_parser("tamper", help="single-character tamper demonstration"), run_dir=True)
    with_common(sub.add_parser("abstain", help="show the abstain path (no bundle)"), img=True)
    fp = with_common(sub.add_parser("forget", help="revoke consent, destroy the salt"))
    fp.add_argument("--subject", "-s", default="alice")
    dp = with_common(sub.add_parser("deploy", help="forge script Deploy.s.sol"))
    dp.add_argument("--rpc", default=None)
    dp.add_argument("--private-key", dest="private_key", default=None)
    with_common(sub.add_parser("anvil", help="start a local anvil node"))
    with_common(sub.add_parser("demo", help="banner -> search -> verify"),
                img=True, run_dir=True, anchor=True, real_stage2=True)
    return p


_DISPATCH = {
    "banner": cmd_banner,
    "index-stats": cmd_index_stats,
    "probe": cmd_probe,
    "stage2": cmd_stage2,
    "search": cmd_search,
    "anchor": cmd_anchor,
    "verify": cmd_verify,
    "tamper": cmd_tamper,
    "abstain": cmd_abstain,
    "forget": cmd_forget,
    "deploy": cmd_deploy,
    "anvil": cmd_anvil,
    "demo": cmd_demo,
}


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    return _DISPATCH[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
