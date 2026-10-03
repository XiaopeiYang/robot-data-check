"""action_jumps: sudden spikes between consecutive actions.

Severity: warning.
Hint: per-dimension delta between consecutive frames; threshold from the
dataset's own delta distribution (e.g. a high quantile times a factor),
never a hard-coded constant.

Set ``frame_start`` / ``frame_end`` on each Issue to the affected frames.

TODO(you): implement, then add this module to ALL_CHECKS in checks/__init__.py
and add a fault-injection test (see tests/fault_injection/test_frame_index.py).
"""

from __future__ import annotations

import duckdb

from ..registry import CheckContext
from ..results import Issue

NAME = "action_jumps"
VERSION = "1"


def run(con: duckdb.DuckDBPyConnection, ctx: CheckContext) -> list[Issue]:
    raise NotImplementedError
