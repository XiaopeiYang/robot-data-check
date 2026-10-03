"""timestamps: dropped frames, non-monotonic or off-fps timestamps.

Severity: error for non-monotonic / large gaps, warning for small fps drift.
Hint: ``timestamp - LAG(timestamp) OVER (PARTITION BY episode_index ORDER BY frame_index)``
compared with ``1 / ctx.fps``. A gap of ~k/fps means k-1 dropped frames.
Note: timestamps are float32 in DROID, so allow a tolerance (decide it from data).

TODO(you): implement, then add this module to ALL_CHECKS in checks/__init__.py
and add a fault-injection test (see tests/fault_injection/test_frame_index.py).
"""

from __future__ import annotations

import duckdb

from ..registry import CheckContext
from ..results import Issue

NAME = "timestamps"
VERSION = "1"


def run(con: duckdb.DuckDBPyConnection, ctx: CheckContext) -> list[Issue]:
    raise NotImplementedError
