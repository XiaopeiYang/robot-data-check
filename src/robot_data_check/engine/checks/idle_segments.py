"""idle_segments: robot not moving for long stretches.

Severity: warning.
Hint: rolling-window change of ``"observation.state"``; flag runs where the
change stays below a data-derived threshold for longer than N seconds
(convert seconds to frames with ctx.fps).

Set ``frame_start`` / ``frame_end`` on each Issue to the affected frames.

TODO(you): implement, then add this module to ALL_CHECKS in checks/__init__.py
and add a fault-injection test (see tests/fault_injection/test_frame_index.py).
"""

from __future__ import annotations

import duckdb

from ..registry import CheckContext
from ..results import Issue

NAME = "idle_segments"
VERSION = "1"


def run(con: duckdb.DuckDBPyConnection, ctx: CheckContext) -> list[Issue]:
    raise NotImplementedError
