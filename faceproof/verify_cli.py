"""Standalone re-verification entry point — no face stack required (§7).

The attestation is only worth something if a third party can check it
independently.  That third party has a bundle, a receipt and a chain; they
should not need InsightFace, OpenCV or a 330 MB model download to recompute
a keccak root.

    pip install "faceproof[verify]"
    python -m faceproof.verify_cli out/run-<id>
    python -m faceproof.verify_cli out/run-<id> --chain     # also read the chain
    python -m faceproof.verify_cli out/run-<id> --tamper    # then prove detection

Imports only the crypto core (``canonical`` / ``merkle`` / ``bundle`` /
``verify``); ``chain`` is imported lazily and only when ``--chain`` is given.
Exit code is 0 when every requested check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m faceproof.verify_cli",
        description="Independently re-verify a FaceProof evidence bundle.",
    )
    p.add_argument("run_dir", help="a run directory containing bundle.json")
    p.add_argument(
        "--chain", action="store_true",
        help="also compare against the on-chain record named by receipt.json",
    )
    p.add_argument(
        "--tamper", action="store_true",
        help="after verifying, flip one character and show detection",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])

    # imported here so --help works with nothing but the stdlib installed
    from faceproof.verify import tamper_demonstration, verify_run

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"not a directory: {run_dir}", file=sys.stderr)
        return 2

    ok = verify_run(run_dir, check_chain=args.chain)

    if args.tamper:
        original_ok, detected = tamper_demonstration(run_dir)
        ok = ok and original_ok and detected

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
