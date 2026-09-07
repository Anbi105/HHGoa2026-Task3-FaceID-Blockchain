"""Stage 3 command surface and end-to-end demo driver (S24).

This wraps - it does not replace - Person 1's ``faceproof.cli``.  Stage 1
(``probe``) and consent management are delegated straight to it; Stage 3
adds discovery-consumption, bundle assembly, anchoring, verification and
the tamper demo around that existing interface.

    python -m faceproof.run banner
    python -m faceproof.run index-stats
    python -m faceproof.run corpus --handles alice.bsky.social   # Channel A corpus (Bluesky)
    python -m faceproof.run corpus-local --root data/corpus      # Channel A corpus (local photos)
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
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.table import Table

from faceproof.bundle import (
    BUNDLE_FILENAME,
    PROOFS_FILENAME,
    AbstainError,
    assemble_bundle,
    recompute_root,
    write_abstain,
)
from faceproof.config import banner, cfg
from faceproof.handoff import PROBE_FILENAME, load_record
from faceproof.manifest import Manifest, new_run_id
from faceproof.stage2_adapter import load_stage2
from faceproof.verify import tamper_demonstration, verify_run

console = Console()
_CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "contracts"
_ANVIL_ACCT0_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
_ANVIL_ACCT0_ADDR = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _latest_run_dir() -> Optional[Path]:
    """Newest run directory that actually carries a Stage 1 handoff.

    A run that dies inside Stage 1 - a missing model stack, a quality-gate
    crash - still leaves ``out/run-<id>/`` behind with only ``manifest.jsonl``
    in it.  Picking purely by mtime therefore selects that corpse, and every
    downstream command fails with a confusing "probe.json does not exist"
    instead of pointing at the run that failed.  Require the handoff.
    """
    runs = sorted(cfg.out_dir.glob("run-*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return next((r for r in runs if (r / PROBE_FILENAME).exists()), None)


def _resolve_run_dir(run_dir: Optional[str]) -> Path:
    if run_dir:
        return Path(run_dir)
    latest = _latest_run_dir()
    if latest is None:
        stale = sorted(cfg.out_dir.glob("run-*"), key=lambda p: p.stat().st_mtime, reverse=True)
        console.print(
            f"[red]no completed run under out/ - none contains {PROBE_FILENAME}.[/red]"
        )
        if stale:
            plural = "y" if len(stale) == 1 else "ies"
            console.print(
                f"[yellow]{len(stale)} run director{plural} exist but Stage 1 never "
                f"finished; newest is {stale[0]}.[/yellow]"
            )
            console.print(
                "[dim]Check its manifest.jsonl for where it stopped, then re-run "
                "Stage 1:[/dim]"
            )
            console.print(
                "[dim]  python -m faceproof.cli probe <image> --subject <id>[/dim]"
            )
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
    """Report the REAL composition of the index, read back from disk."""
    from faceproof.local_corpus import stats as index_stats

    snap = index_stats()
    if snap is None:
        console.print(f"[yellow]no index snapshot at {cfg.data_dir / 'index' / 'snapshot.json'}[/yellow]")
        console.print("Build one:  python -m faceproof.run corpus-local --root data/corpus")
        return 0

    table = Table(title="Channel A index", title_style="bold cyan")
    table.add_column("field"); table.add_column("value")
    table.add_row("snapshot_id", str(snap.get("snapshot_id", "")))
    table.add_row("n_faces", str(snap.get("n_faces", "")))
    table.add_row("n_images", str(snap.get("n_images", "")))
    table.add_row("n_subjects", str(snap.get("n_subjects", "")))
    table.add_row("n_authors", str(snap.get("n_authors", "")))
    table.add_row("dim", str(snap.get("dim") or "unknown"))
    table.add_row("model_id", str(snap.get("model_id", "")))
    table.add_row("source_types", ", ".join(snap.get("source_types", []) or ["-"]))
    console.print(table)

    if snap.get("stale"):
        console.print(
            f"[bold yellow]WARNING: this index is stale - "
            f"{snap['files_missing']} of its source image(s) no longer exist "
            f"on disk (e.g. {snap['missing_examples'][0]}).[/bold yellow]"
        )
        console.print(
            "[yellow]It is left over from an earlier build and its provenance "
            "cannot be re-checked. Rebuild before demonstrating:[/yellow]"
        )
        console.print("[yellow]  python -m faceproof.run corpus-local --root data/corpus[/yellow]")

    subjects = snap.get("subjects") or {}
    if subjects:
        st = Table(title="faces per subject")
        st.add_column("subject"); st.add_column("faces", justify="right")
        for name, n in sorted(subjects.items()):
            st.add_row(str(name), str(n))
        console.print(st)
    return 0


def cmd_corpus_local(args: argparse.Namespace) -> int:
    """Build the Channel A index from local consenting photographs."""
    from faceproof.local_corpus import CorpusError as _CE, build

    try:
        summary = build(args.root, exclude=args.exclude or [],
                        subjects=args.subjects or None,
                        gallery_det=args.gallery_det,
                        log=lambda *a: console.print(*a))
    except _CE as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        return 2
    console.print(f"[green]index built[/green]  snapshot={summary['snapshot_id']}")
    return 0


def cmd_corpus(args: argparse.Namespace) -> int:
    """Build the Channel A corpus: ingest -> fetch -> FAISS index.

    Ingestion and indexing are Person 2's real modules; only the image fetch
    between them is integration-side (see faceproof/stage2_corpus.py).
    """
    from faceproof.stage2_corpus import (
        CorpusError,
        build_index,
        fetch_images,
        ingest,
        raw_path,
    )

    try:
        if not args.skip_ingest:
            if not args.handles:
                console.print(
                    "[red]--handles is required (or pass --skip-ingest to reuse "
                    "an existing raw.jsonl).[/red]"
                )
                console.print(
                    "[dim]Use only handles whose owners have consented to being "
                    "indexed. Public Bluesky AppView; no API key needed.[/dim]"
                )
                return 3
            console.rule("Stage 2 corpus - ingest (Person 2, public Bluesky)")
            n = ingest(args.handles)
            console.print(f"[green]ingested[/green] {n} image records -> {raw_path()}")
            if n == 0:
                console.print(
                    "[yellow]no records: those handles have no public posts with "
                    "images, or the API refused. Nothing is fabricated.[/yellow]"
                )
                return 1

        console.rule("Stage 2 corpus - fetch images (integration glue)")
        records, stats = fetch_images(limit=args.limit, log=console.print)
        console.print(
            f"  rows={stats['rows']}  fetched={stats['fetched']}  "
            f"duplicate={stats['duplicate']}  failed={stats['failed']}  "
            f"too_small={stats['too_small']}"
        )
        if not records:
            console.print("[yellow]no images fetched - cannot build an index.[/yellow]")
            return 1

        console.rule("Stage 2 corpus - build index (Person 2)")
        summary = build_index(records)
    except CorpusError as exc:
        console.print(f"[red]{exc}[/red]")
        return 3

    console.print(json.dumps(summary, indent=2, sort_keys=True))
    console.print(
        f"[green]index built[/green]  faces={summary.get('n_faces')}  "
        f"images={summary.get('n_images')}  authors={summary.get('n_authors')}"
    )
    console.print("[dim]Channel A is now live; `run stage2` will query it.[/dim]")
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

    from faceproof.stage2_adapter import Stage2ResultMissing

    try:
        stage2 = load_stage2(run_dir, allow_synthetic=getattr(args, "demo", False))
    except Stage2ResultMissing as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        return 3
    if stage2["source"] == "synthetic-stub":
        console.print(
            "[yellow]--demo: Stage 2 result is the labelled synthetic fixture, "
            "not a real search.[/yellow]"
        )
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

    anchor_ok: Optional[bool] = None
    if args.anchor:
        from faceproof.anchor import anchor as _anchor

        try:
            _anchor(run_dir)
            anchor_ok = True
        except Exception as exc:
            anchor_ok = False
            console.print(f"[bold red]anchor FAILED: {exc}[/bold red]")

    verified = verify_run(run_dir, check_chain=bool(args.anchor and anchor_ok))
    if not args.no_tamper:
        tamper_demonstration(run_dir)

    if args.anchor and not anchor_ok:
        return 1
    return 0 if verified else 1


def cmd_anchor(args: argparse.Namespace) -> int:
    """Anchor a run's Merkle root.  Refusals are reported, not raised.

    ``anchor()`` deliberately refuses three things - an abstaining run with no
    bundle, a bundle whose recomputed root disagrees with the stored one, and a
    bundle whose verdict is ABSTAIN.  Those are correct outcomes, so they read
    as a message and a non-zero exit rather than as a stack trace.
    """
    from faceproof.anchor import anchor as _anchor

    try:
        _anchor(_resolve_run_dir(args.run_dir))
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[yellow]anchor refused: {exc}[/yellow]")
        return 1
    except Exception as exc:
        console.print(f"[bold red]anchor FAILED: {exc}[/bold red]")
        return 1
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


def _forge(*forge_args: str, env_extra: Optional[dict] = None) -> int:
    """Run ``forge`` in contracts/.  Secrets go in ``env_extra``, never argv."""
    env = None
    if env_extra:
        env = {**os.environ, **env_extra}
    try:
        return subprocess.call(["forge", *forge_args], cwd=str(_CONTRACTS_DIR), env=env)
    except FileNotFoundError:
        console.print("[red]forge not found[/red] - install Foundry (https://getfoundry.sh)")
        console.print(f"would run: forge {' '.join(forge_args)}  (cwd={_CONTRACTS_DIR})")
        return 127


def cmd_ui(args: argparse.Namespace) -> int:
    """Serve the local dashboard over the real pipeline (loopback only)."""
    from faceproof.ui.server import serve

    return serve(port=args.port, open_browser=not args.no_browser)


def cmd_deploy(args: argparse.Namespace) -> int:
    """Deploy EvidenceRegistry without ever placing a key in argv.

    ``forge script`` does not read ``ETH_PRIVATE_KEY`` (verified against the
    Foundry build in this checkout: it still reports "You seem to be using
    Foundry's default sender"), so the previous env-var handoff silently did
    nothing and every deploy failed.  argv is the wrong place to fix that -
    it is world-readable via ``ps`` and lands in shell history - so:

    * against a local node, use ``--unlocked --sender``: Anvil signs for its
      own dev accounts, and no key exists anywhere in the command;
    * against a real chain, require a Foundry keystore (``--account``), which
      prompts for the passphrase on a tty instead of exposing the key.

    ``PRIVATE_KEY`` from ``.env`` is deliberately NOT forwarded to forge.
    """
    rpc = args.rpc or "http://127.0.0.1:8545"
    local = any(h in rpc for h in ("127.0.0.1", "localhost", "0.0.0.0", "[::1]"))

    _forge("build")

    if local:
        console.print(f"[dim]local node: deploying unlocked as {_ANVIL_ACCT0_ADDR}[/dim]")
        return _forge(
            "script", "script/Deploy.s.sol:DeployScript",
            "--rpc-url", rpc, "--broadcast",
            "--unlocked", "--sender", _ANVIL_ACCT0_ADDR,
        )

    account = args.account or os.environ.get("FOUNDRY_ACCOUNT")
    if not account:
        console.print(
            "[bold red]refusing to deploy to a non-local chain without a "
            "keystore.[/bold red]"
        )
        console.print(
            "Passing a private key on the command line exposes it via `ps` "
            "and shell history. Import it once, then deploy:"
        )
        console.print("  cast wallet import deployer --interactive")
        console.print(
            "  python -m faceproof.run deploy --rpc <url> --account deployer"
        )
        return 2

    console.print(f"[dim]deploying with keystore account {account!r} "
                  f"(passphrase prompted; key never in argv)[/dim]")
    return _forge(
        "script", "script/Deploy.s.sol:DeployScript",
        "--rpc-url", rpc, "--broadcast", "--account", account,
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
        demo=True,   # the `demo` subcommand is the deliberate opt-in
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
                    real_stage2=False, demo=False):
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
        if demo:
            sp.add_argument(
                "--demo", dest="demo", action="store_true",
                help="allow the labelled synthetic Stage 2 fixture when no real "
                     "Stage 2 result exists (it describes a positive match and is "
                     "anchorable - opt in deliberately)",
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
    lp = sub.add_parser("corpus-local",
                        help="build the Channel A index from local consenting photos")
    lp.add_argument("--root", nargs="+", default=["data/corpus"],
                    help="one or more corpus roots containing <subject>/*.jpg")
    lp.add_argument("--gallery-det", type=float, default=0.55,
                    help="gallery admission det_score (guide p.20 default 0.55); "
                         "the Stage 1 probe gate is separate and unchanged")
    lp.add_argument("--exclude", nargs="*", default=[],
                    help="image paths to hold out (use for the probe photo)")
    lp.add_argument("--subjects", nargs="*", default=[],
                    help="only index these subject directories")
    with_common(lp)
    cp = sub.add_parser("corpus", help="build the Channel A corpus (ingest -> fetch -> FAISS)")
    cp.add_argument("--handles", nargs="*", default=[],
                    help="consenting Bluesky handles to ingest, e.g. alice.bsky.social")
    cp.add_argument("--skip-ingest", dest="skip_ingest", action="store_true",
                    help="reuse an existing data/index/raw.jsonl")
    cp.add_argument("--limit", type=int, default=None,
                    help="cap how many images are fetched and indexed")
    with_common(sub.add_parser("stage2", help="Person 2 discovery/fusion -> stage2.json"), run_dir=True)
    with_common(sub.add_parser("search", help="assemble the evidence bundle"),
                img=True, run_dir=True, anchor=True, real_stage2=True, demo=True)
    with_common(sub.add_parser("anchor", help="anchor the bundle root on-chain"), run_dir=True)
    with_common(sub.add_parser("verify", help="independent re-verification"), run_dir=True, chain=True)
    with_common(sub.add_parser("tamper", help="single-character tamper demonstration"), run_dir=True)
    with_common(sub.add_parser("abstain", help="show the abstain path (no bundle)"), img=True)
    fp = with_common(sub.add_parser("forget", help="revoke consent, destroy the salt"))
    fp.add_argument("--subject", "-s", default="alice")
    dp = with_common(sub.add_parser("deploy", help="forge script Deploy.s.sol"))
    dp.add_argument("--account", default=None,
                    help="Foundry keystore account name (required off-localhost)")
    dp.add_argument("--rpc", default=None)
    dp.add_argument("--private-key", dest="private_key", default=None)
    with_common(sub.add_parser("anvil", help="start a local anvil node"))
    up = with_common(sub.add_parser("ui", help="serve the local dashboard (127.0.0.1)"))
    up.add_argument("--port", type=int, default=8765)
    up.add_argument("--no-browser", action="store_true",
                    help="do not open a browser window")
    with_common(sub.add_parser("demo", help="banner -> search -> verify"),
                img=True, run_dir=True, anchor=True, real_stage2=True, demo=True)
    return p


_DISPATCH = {
    "banner": cmd_banner,
    "index-stats": cmd_index_stats,
        "corpus-local": cmd_corpus_local,
    "probe": cmd_probe,
    "corpus": cmd_corpus,
    "stage2": cmd_stage2,
    "search": cmd_search,
    "anchor": cmd_anchor,
    "verify": cmd_verify,
    "tamper": cmd_tamper,
    "abstain": cmd_abstain,
    "forget": cmd_forget,
    "deploy": cmd_deploy,
    "anvil": cmd_anvil,
        "ui": cmd_ui,
    "demo": cmd_demo,
}


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    return _DISPATCH[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
