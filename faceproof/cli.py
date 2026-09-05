"""CLI for the FaceProof Stage 1 probe.

    python -m faceproof.cli setup
    python -m faceproof.cli config
    python -m faceproof.cli consent grant  <subject_id> [--scope S] [--days N]
    python -m faceproof.cli consent list
    python -m faceproof.cli consent revoke <subject_id>
    python -m faceproof.cli probe <image> --subject <subject_id>
    python -m faceproof.cli calibrate [dir]

Exit codes
----------
    0  probe accepted
    1  probe rejected by the quality gate (an abstain, not a crash)
    2  refused: no valid consent for the subject
    3  usage error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from faceproof import consent as consent_mod
from faceproof.config import banner, cfg
from faceproof.consent import ConsentStore, check as consent_check
from faceproof.face import encode, preload
from faceproof.handoff import build_record, write_embedding, write_record
from faceproof.manifest import Manifest, new_run_id

console = Console(width=88)

EXIT_OK = 0
EXIT_REJECTED = 1
EXIT_NO_CONSENT = 2
EXIT_USAGE = 3


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------


def cmd_probe(image: str, subject: str, run_id: Optional[str] = None) -> int:
    """Run a consent-gated face probe and write the Stage 2 handoff."""
    image_path = Path(image)
    run_id = run_id or new_run_id()
    run_dir = cfg.run_dir(run_id)
    man = Manifest(run_dir, run_id=run_id)

    console.print()
    man.log("probe", "run_start", run_id=run_id, image=str(image_path))
    man.log("probe", "config", model=cfg.model_id, pipeline=cfg.pipeline_version)

    # ── Consent gate — before any biometric processing ──────────────
    store = ConsentStore()
    record = store.get(subject)
    ok, reason = consent_check(record, scope=cfg.consent_scope)

    if not ok:
        man.log("probe", "consent_denied", subject=subject, reason=reason)
        console.print()
        console.print(
            Panel(
                f"CONSENT=[bold red]DENIED[/bold red]\n"
                f"reason={reason}\n\n"
                f"No face was detected, encoded, or stored.\n"
                f"Grant consent first:\n"
                f"  python -m faceproof.cli consent grant {subject}",
                title="Refused",
                border_style="red",
            )
        )
        return EXIT_NO_CONSENT

    man.log(
        "probe",
        "consent_ok",
        scope=record.scope,
        expires_at=record.expires_at,
        subject_commitment="0x" + consent_mod.subject_commitment(record).hex()[:16] + "...",
    )

    # ── Detect + quality gate ───────────────────────────────────────
    probe, rejection = encode(image_path, strict=True)

    if rejection is not None:
        m = rejection.metrics
        man.log(
            "probe",
            "quality_gate",
            result="FAIL",
            reason=str(rejection),
            **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()},
        )
        _print_metrics(m)
        console.print()
        console.print(
            Panel(
                f"QUALITY_GATE=[bold red]FAIL[/bold red]\nreason={rejection}",
                border_style="red",
            )
        )
        rec = build_record(run_id, image_path, record, rejection=rejection)
        path = write_record(run_dir, rec)
        man.artifact("probe", path)
        man.log("probe", "run_end", status="rejected", run_dir=str(run_dir))
        console.print(f"\n[yellow]ABSTAIN[/yellow] — handoff written to {path}")
        return EXIT_REJECTED

    # ── Accepted ────────────────────────────────────────────────────
    m = probe.metrics()
    man.log(
        "probe",
        "quality_gate",
        result="PASS",
        **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()},
    )
    _print_metrics(m)
    console.print()
    console.print(Panel("QUALITY_GATE=[bold green]PASS[/bold green]", border_style="green"))
    console.print()

    norm = float((probe.embedding**2).sum() ** 0.5)
    man.log(
        "probe",
        "encoded",
        dim=int(probe.embedding.shape[0]),
        dtype=str(probe.embedding.dtype),
        l2_norm=round(norm, 6),
    )

    emb_path, emb_sha = write_embedding(run_dir, probe.embedding)
    man.artifact("probe", emb_path)

    rec = build_record(run_id, image_path, record, probe=probe, embedding_digest=emb_sha)
    man.log("probe", "commitment", embedding=rec["embedding"]["commitment"])
    man.log("probe", "commitment", subject=rec["consent"]["subject_commitment"])

    path = write_record(run_dir, rec)
    man.artifact("probe", path)
    man.log("probe", "run_end", status="accepted", run_dir=str(run_dir))

    console.print()
    console.print(
        Panel(
            f"[bold green]PROBE_COMPLETE[/bold green]\n"
            f"run_id   = {run_id}\n"
            f"handoff  = {path}\n"
            f"stage 2  → faceproof.handoff.load_record('{run_dir}')",
            border_style="green",
        )
    )
    return EXIT_OK


def _print_metrics(m: dict) -> None:
    console.print(
        f"faces_detected={m.get('n_faces')}  "
        f"detection_score={_fmt(m.get('det_score'), 2)}  "
        f"face_size={_fmt(m.get('face_px'), 0)}px"
    )
    console.print(
        f"blur_variance={_fmt(m.get('blur_var'), 1)}  "
        f"secondary_ratio={_fmt(m.get('secondary_ratio'), 2)}"
    )


def _fmt(v, p: int) -> str:
    if v is None:
        return "n/a"
    return f"{float(v):.{p}f}"


# ---------------------------------------------------------------------------
# consent
# ---------------------------------------------------------------------------


def cmd_consent_grant(subject: str, scope: Optional[str], days: Optional[int]) -> int:
    store = ConsentStore()
    rec = store.grant(subject, scope=scope, ttl_days=days)
    console.print(
        Panel(
            f"subject_id         = {rec.subject_id}\n"
            f"scope              = {rec.scope}\n"
            f"granted_at         = {rec.granted_at}\n"
            f"expires_at         = {rec.expires_at}\n"
            f"subject_commitment = 0x{consent_mod.subject_commitment(rec).hex()}\n\n"
            f"[dim]Token and salt stored locally at {cfg.consent_store} (mode 600).\n"
            f"Neither ever leaves this host.[/dim]",
            title="Consent granted",
            border_style="green",
        )
    )
    return EXIT_OK


def cmd_consent_list() -> int:
    store = ConsentStore()
    if len(store) == 0:
        console.print("[yellow]No consent records.[/yellow]")
        console.print(f"Grant one:  python -m faceproof.cli consent grant <subject_id>")
        return EXIT_OK

    table = Table(title=f"Consent store — {cfg.consent_store}")
    table.add_column("subject_id", style="bold")
    table.add_column("scope")
    table.add_column("expires_at")
    table.add_column("status")
    for rec in store.list():
        ok, reason = consent_check(rec, scope=cfg.consent_scope)
        status = "[green]valid[/green]" if ok else f"[red]{reason}[/red]"
        table.add_row(rec.subject_id, rec.scope, rec.expires_at, status)
    console.print(table)
    return EXIT_OK


def cmd_consent_revoke(subject: str) -> int:
    store = ConsentStore()
    rec = store.revoke(subject)
    if rec is None:
        console.print(f"[red]No consent record for '{subject}'.[/red]")
        return EXIT_USAGE
    console.print(
        Panel(
            f"subject_id = {rec.subject_id}\n"
            f"revoked_at = {rec.revoked_at}\n"
            f"salt       = [bold red]DESTROYED[/bold red]\n\n"
            f"Every embedding commitment ever made for this subject is now\n"
            f"permanently unverifiable — including anything already anchored\n"
            f"on chain.  That is the erasure path against an immutable ledger.",
            title="Consent revoked",
            border_style="red",
        )
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# setup / config / calibrate
# ---------------------------------------------------------------------------


def cmd_setup() -> int:
    console.print("[bold]Preloading InsightFace buffalo_l (CPU)...[/bold]")
    preload()
    console.print("[green]Model ready.[/green] Weights cached at ~/.insightface/models/")
    return EXIT_OK


def cmd_config() -> int:
    console.print(Panel(banner(), title="FaceProof configuration", border_style="blue"))
    calib = cfg.calibration_json
    if calib.exists():
        console.print(f"[green]calibration[/green] measured — {calib}")
    else:
        console.print(
            f"[yellow]calibration[/yellow] not measured — accept_at={cfg.accept_at} "
            f"is the guide's placeholder. Run: make calibrate"
        )
    return EXIT_OK


def cmd_calibrate(path: Optional[str]) -> int:
    from faceproof.calibrate import main as calibrate_main

    return calibrate_main([path] if path else [])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m faceproof.cli",
        description="FaceProof — Stage 1 probe (detect, gate, encode, consent-bind).",
    )
    sub = p.add_subparsers(dest="cmd")

    pr = sub.add_parser("probe", help="run a consent-gated face probe")
    pr.add_argument("image")
    pr.add_argument("--subject", "-s", required=True, help="consenting subject id")
    pr.add_argument("--run-id", default=None)

    sub.add_parser("setup", help="preload model weights (run before recording)")
    sub.add_parser("config", help="show the effective configuration")

    cal = sub.add_parser("calibrate", help="measure the acceptance threshold")
    cal.add_argument("dir", nargs="?", default=None)

    c = sub.add_parser("consent", help="manage consent records")
    csub = c.add_subparsers(dest="consent_cmd")
    cg = csub.add_parser("grant")
    cg.add_argument("subject_id")
    cg.add_argument("--scope", default=None)
    cg.add_argument("--days", type=int, default=None)
    csub.add_parser("list")
    crv = csub.add_parser("revoke")
    crv.add_argument("subject_id")

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.cmd is None:
        parser.print_help()
        return EXIT_USAGE

    if args.cmd == "probe":
        return cmd_probe(args.image, args.subject, args.run_id)
    if args.cmd == "setup":
        return cmd_setup()
    if args.cmd == "config":
        return cmd_config()
    if args.cmd == "calibrate":
        return cmd_calibrate(args.dir)
    if args.cmd == "consent":
        if args.consent_cmd == "grant":
            return cmd_consent_grant(args.subject_id, args.scope, args.days)
        if args.consent_cmd == "list":
            return cmd_consent_list()
        if args.consent_cmd == "revoke":
            return cmd_consent_revoke(args.subject_id)
        parser.parse_args(["consent", "--help"])
        return EXIT_USAGE

    parser.print_help()
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
