"""Independent re-verification, selective disclosure, and tamper detection (S21-23).

Verification here does **not** trust the bundle.  It:

1. loads ``bundle.json``;
2. ignores ``bundle['merkle_root']`` entirely;
3. re-canonicalises each of the eight groups;
4. recomputes all eight leaves (double keccak);
5. rebuilds the Merkle tree;
6. recomputes the root;
7. compares that root against the stored value **and**, when a receipt is
   present and the on-chain check was requested, against the value returned
   by the on-chain registry (a requested check that cannot run counts as a
   FAILURE, not a skip);
8. verifies a selective-disclosure proof for ``match_location`` - both the
   proof stored in ``proofs.json`` and one regenerated from scratch - each
   against the **anchored** root, so tampering with any group breaks it;
9. prints a single pass/fail verdict.

:func:`tamper_demonstration` flips exactly one character in
``match_location.post_url`` and shows every check above turn red.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from faceproof.bundle import (
    BUNDLE_FILENAME,
    GROUPS,
    PROOFS_FILENAME,
    TREE_DEPTH,
    canonical_leaves,
    recompute_root,
)
from faceproof.merkle import build, hexstr, proof as merkle_proof, root as merkle_root, unhex, verify

console = Console()

_LOCATION_INDEX = GROUPS.index("match_location")


def verify_bundle_locally(
    bundle: Dict[str, Any], proofs: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Recompute everything from ``bundle['groups']`` and check it hangs together."""
    groups = bundle.get("groups", {})
    if tuple(g for g in GROUPS if g in groups) != GROUPS or len(groups) != len(GROUPS):
        raise ValueError(f"bundle must contain exactly the 8 groups {GROUPS}")

    leaves = canonical_leaves(groups)          # step 3-4: canon + double keccak
    layers = build(leaves)                     # step 5
    derived_root = hexstr(merkle_root(layers))  # step 6

    stored_root = bundle.get("merkle_root")
    root_match = bool(stored_root) and derived_root.lower() == str(stored_root).lower()

    # Step 8 - selective disclosure of match_location.  Both proofs are checked
    # against the ANCHORED root (bundle['merkle_root']), never against a root
    # recomputed from these groups: a proof freshly generated from `layers` and
    # checked against `root(layers)` can never fail, and the stored proof
    # checked against `derived_root` moves with the tampered bundle.  Verifying
    # against the anchored root means either check fails the moment any group
    # (this one or another) is altered.
    anchored: Optional[bytes] = None
    if stored_root:
        try:
            anchored = unhex(stored_root)
        except (ValueError, TypeError):
            anchored = None

    loc_leaf = leaves[_LOCATION_INDEX]
    fresh_ok: Optional[bool] = None
    stored_ok: Optional[bool] = None
    if anchored is not None:
        fresh_ok = verify(
            loc_leaf, merkle_proof(layers, _LOCATION_INDEX), anchored,
            expected_len=TREE_DEPTH,
        )
        if proofs and "groups" in proofs and "match_location" in proofs["groups"]:
            entry = proofs["groups"]["match_location"]
            stored_ok = verify(
                loc_leaf, [unhex(p) for p in entry["proof"]], anchored,
                expected_len=TREE_DEPTH,
            )

    return {
        "derived_root": derived_root,
        "stored_root": stored_root,
        "root_match": root_match,
        "leaves": [hexstr(x) for x in leaves],
        "selective_disclosure_regenerated": fresh_ok,
        "selective_disclosure_stored_proof": stored_ok,
        "selective_disclosure_pass": bool(
            root_match and fresh_ok is True and (stored_ok in (None, True))
        ),
    }


def _load(run_dir: Path | str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    run_path = Path(run_dir)
    bundle = json.loads((run_path / BUNDLE_FILENAME).read_text(encoding="utf-8"))
    proofs_path = run_path / PROOFS_FILENAME
    receipt_path = run_path / "receipt.json"
    proofs = json.loads(proofs_path.read_text(encoding="utf-8")) if proofs_path.exists() else None
    receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else None
    return bundle, proofs, receipt


def _check_chain(bundle, proofs, receipt, local) -> Dict[str, Optional[bool]]:  # pragma: no cover - needs a live chain (see tests/test_chain.py + Foundry suite)
    """Compare the recomputed root and a field proof against the on-chain record.

    Raises on any condition that means the on-chain check could not be run
    (unknown chain, unreachable RPC, missing contract) - the caller turns that
    into a verification FAILURE, never a silent pass.
    """
    from faceproof.chain import CHAINS, get_record, get_w3, id_of, rpc_url, verify_field

    out: Dict[str, Optional[bool]] = {"chain_root_match": None, "chain_verify_field": None}
    addr = receipt.get("contract")
    if not addr:
        raise ValueError("receipt has no contract address")
    name = receipt.get("chain")
    if name not in CHAINS:
        raise ValueError(f"receipt names an unknown chain: {name!r}")
    w3 = get_w3(rpc_url(name), name=name)
    if not w3.is_connected():
        raise ConnectionError(f"cannot reach {name} RPC")

    anchor_id = receipt.get("anchor_id")
    if anchor_id is None:
        anchor_id = id_of(w3, addr, local["derived_root"])
    rec = get_record(w3, addr, int(anchor_id))
    out["chain_root_match"] = rec["root"].lower() == local["derived_root"].lower()

    if proofs and "groups" in proofs and "match_location" in proofs["groups"]:
        entry = proofs["groups"]["match_location"]
        out["chain_verify_field"] = verify_field(
            w3, addr, int(anchor_id), local["leaves"][_LOCATION_INDEX], entry["proof"]
        )
    return out


def verify_run(run_dir: Path | str, *, check_chain: bool = True) -> bool:
    """Full re-verification of a run directory. Returns True iff every check passes."""
    run_path = Path(run_dir)
    if not (run_path / BUNDLE_FILENAME).exists():
        console.print(f"[bold red]no {BUNDLE_FILENAME} in {run_path}[/bold red]")
        return False

    bundle, proofs, receipt = _load(run_path)
    local = verify_bundle_locally(bundle, proofs)

    chain: Dict[str, Optional[bool]] = {"chain_root_match": None, "chain_verify_field": None}
    chain_error: Optional[str] = None
    # Only "want" the chain check when it was asked for AND there is a receipt
    # with a contract to check against.  A wanted-but-failed check is a FAIL,
    # not a skip that silently passes.
    want_chain = bool(check_chain and receipt and receipt.get("contract"))
    if want_chain:
        try:
            chain = _check_chain(bundle, proofs, receipt, local)
        except Exception as exc:  # pragma: no cover - network variance
            chain_error = str(exc)
            console.print(f"[bold red]on-chain check FAILED: {exc}[/bold red]")

    table = Table(title="Stage 3 - independent re-verification", title_style="bold cyan")
    table.add_column("check")
    table.add_column("value")
    table.add_column("", justify="center")

    def row(name: str, val: str, ok: Optional[bool]) -> None:
        mark = "-" if ok is None else ("[green]PASS[/green]" if ok else "[red]FAIL[/red]")
        table.add_row(name, val, mark)

    def chain_cell(v: Optional[bool]) -> Optional[bool]:
        if not want_chain:
            return None            # not requested -> not scored
        if chain_error is not None:
            return False
        return v is True

    row("recomputed root", local["derived_root"][:18] + "...", None)
    row("== stored root", str(local["stored_root"])[:18] + "...", local["root_match"])
    row("selective disclosure (regenerated proof)", "match_location", local["selective_disclosure_regenerated"])
    row("selective disclosure (proofs.json)", "match_location", local["selective_disclosure_stored_proof"])
    row("== on-chain root", "EvidenceRegistry.get()", chain_cell(chain["chain_root_match"]))
    row("on-chain verifyField()", "match_location", chain_cell(chain["chain_verify_field"]))
    console.print(table)

    checks = [local["root_match"], local["selective_disclosure_pass"]]
    if want_chain:
        checks.append(
            chain_error is None
            and chain["chain_root_match"] is True
            and chain["chain_verify_field"] is True
        )
    ok = all(checks)
    console.print(
        Panel(
            "[bold green]VERIFICATION PASSED[/bold green]"
            if ok
            else "[bold red]VERIFICATION FAILED[/bold red]",
            border_style="green" if ok else "red",
        )
    )
    return ok


def tamper_demonstration(run_dir: Path | str) -> Tuple[bool, bool]:
    """Flip one character in ``match_location.post_url``; verification must fail.

    Returns ``(original_passed, tamper_detected)``.
    """
    bundle, proofs, _ = _load(run_dir)

    console.print("\n[bold cyan]TAMPER DEMONSTRATION[/bold cyan] (S23)")

    original = verify_bundle_locally(bundle, proofs)
    original_ok = original["root_match"] and original["selective_disclosure_pass"]
    console.print(f"  original root  {original['derived_root']}")
    console.print(f"  original verdict  {'PASS' if original_ok else 'FAIL'}")

    tampered = copy.deepcopy(bundle)
    loc = tampered["groups"]["match_location"]
    url = loc["post_url"] or "https://bsky.app/x"
    i = len(url) - 1
    loc["post_url"] = url[:i] + ("0" if url[i] != "0" else "1") + url[i + 1 :]
    console.print(f"  field          groups.match_location.post_url")
    console.print(f"  before         {url}")
    console.print(f"  after          {loc['post_url']}   (1 character changed)")

    new_root = recompute_root(tampered)
    still_matches_stored = new_root.lower() == str(bundle["merkle_root"]).lower()

    # the shipped proof for match_location can no longer place the tampered leaf
    tleaves = canonical_leaves(tampered["groups"])
    tlayers = build(tleaves)
    field_ok = verify(
        tleaves[_LOCATION_INDEX],
        merkle_proof(tlayers, _LOCATION_INDEX),
        unhex(bundle["merkle_root"]),
    )

    console.print(f"  recomputed root  {new_root}")
    console.print(f"  root still matches anchored value  {'YES' if still_matches_stored else 'NO'}")
    console.print(f"  selective disclosure against anchored root  {'PASS' if field_ok else 'FAIL'}")

    tamper_detected = (not still_matches_stored) and (not field_ok)
    console.print(
        Panel(
            f"original = {'PASS' if original_ok else 'FAIL'}   "
            f"tampered = {'DETECTED' if tamper_detected else 'MISSED'}",
            border_style="green" if (original_ok and tamper_detected) else "red",
        )
    )
    return original_ok, tamper_detected
