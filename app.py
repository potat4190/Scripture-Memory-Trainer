"""Deployment entrypoint.

Vercel's Python runtime looks for a top-level `app` in one of a fixed set of
filenames -- `app.py` is the first it checks -- and runs the whole FastAPI
application as a single function. Keeping the entrypoint here rather than
configuring `tool.vercel.entrypoint` means the `functions` key in `vercel.json`
is unambiguously `app.py`, which is the part of that configuration most likely
to be wrong.

The `sys.path` line is not decoration. This is a src-layout package, so
`scripture_memory_trainer` is importable locally only because `uv sync`
installs the project in editable mode. A deployment that installs dependencies
without installing the project itself would not find it, and the failure looks
like a missing third-party package rather than a layout problem.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripture_memory_trainer.api import app  # noqa: E402

__all__ = ["app"]
