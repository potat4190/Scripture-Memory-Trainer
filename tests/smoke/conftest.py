"""Let the smoke test use a browser that is already on the machine.

`playwright install` downloads a build pinned to the installed Playwright
version. That download is blocked in some environments (locked-down CI images,
corporate proxies), and where a compatible Chromium is already present the
download is wasted anyway. Setting `PLAYWRIGHT_EXECUTABLE_PATH` points the
launcher at it::

    PLAYWRIGHT_EXECUTABLE_PATH=/opt/pw-browsers/chromium/chrome \
    SMOKE_URL=https://... uv run pytest tests/smoke -q

Unset -- the normal case, including GitHub Actions -- this changes nothing.
"""

from __future__ import annotations

import os
from typing import Any

import pytest


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict[str, Any]) -> dict[str, Any]:
    executable = os.environ.get("PLAYWRIGHT_EXECUTABLE_PATH")
    if executable:
        return {**browser_type_launch_args, "executable_path": executable}
    return browser_type_launch_args
