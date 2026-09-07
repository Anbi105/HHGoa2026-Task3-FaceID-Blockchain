"""Local demonstration dashboard for the FaceProof pipeline.

The UI is a *view*: every number it renders is read back from an artifact that
the existing pipeline wrote (``probe.json``, ``stage2.json``, ``bundle.json``,
``proofs.json``, ``receipt.json``).  No stage is reimplemented here and no
result is synthesised - when a stage abstains, the dashboard shows the abstain.

    python -m faceproof.run ui            # http://127.0.0.1:8765

Nothing in this package is imported by the CLI, so the command surface keeps
working unchanged if the UI is never started.
"""

from __future__ import annotations

__all__ = ["serve", "build_app_state"]


def __getattr__(name: str):  # PEP 562 - keep import cost off the CLI path
    if name in __all__:
        from faceproof.ui import server

        return getattr(server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
