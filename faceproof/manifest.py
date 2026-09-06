"""Append-only run manifest (§4).

Every stage boundary writes a JSONL record and echoes it to the terminal.
This is the artifact that makes the recording credible: a viewer watches
lines land in real time, each with a timestamp and a hash, and can see
that stage 3 consumed exactly what stage 2 produced.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console

console = Console()


def new_run_id() -> str:
    """Short, sortable, collision-resistant run identifier."""
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6]


def sha256_file(path: Path | str) -> str:
    """Streaming sha256 of a file — never loads the whole thing into memory."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Manifest:
    """Append-only JSONL log for one run."""

    def __init__(self, run_dir: Path | str, run_id: Optional[str] = None, echo: bool = True):
        self.dir = Path(run_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "manifest.jsonl"
        self.run_id = run_id or self.dir.name.removeprefix("run-")
        self.echo = echo
        self.t0 = time.time()

    # ── Core ────────────────────────────────────────────────────────

    def log(
        self,
        stage: str,
        event: str,
        _echo_hide: tuple[str, ...] = (),
        **fields: Any,
    ) -> Dict[str, Any]:
        """Append one record, echo it, and return it.

        ``_echo_hide`` names fields that are written to the JSONL but kept
        off the terminal — used for full digests, which are evidence but
        would swamp the screen during the recording.
        """
        rec: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_s": round(time.time() - self.t0, 3),
            "run_id": self.run_id,
            "stage": stage,
            "event": event,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")

        if self.echo:
            shown = {k: v for k, v in fields.items() if k not in _echo_hide}
            extra = "  ".join(f"[dim]{k}[/dim]={v}" for k, v in shown.items())
            console.print(f"[bold cyan]{stage}[/bold cyan] [green]{event}[/green]  {extra}")
        return rec

    def artifact(self, stage: str, path: Path | str) -> Dict[str, Any]:
        """Log a file plus its digest, so the chain of custody is visible."""
        p = Path(path)
        digest = sha256_file(p)
        return self.log(
            stage,
            "artifact",
            _echo_hide=("sha256",),
            path=str(p),
            bytes=p.stat().st_size,
            sha256_short=digest[:16] + "...",
            sha256=digest,
        )

    # ── Reading back (used by tests and by stage 2/3) ────────────────

    def records(self) -> list[Dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
