"""timestamps: dropped frames, non-monotonic or off-fps timestamps.

Severity: error for non-monotonic / large gaps, warning for small fps drift.
Hint: ``timestamp - LAG(timestamp) OVER (PARTITION BY episode_index ORDER BY frame_index)``
compared with ``1 / ctx.fps``. A gap of ~k/fps means k-1 dropped frames.
Note: timestamps are float32 in DROID, so allow a tolerance (decide it from data).

Finding (2026-10-14): LeRobot's writer always stores timestamp = frame_index / fps, so this
check cannot see real recording stalls; it can only catch non-standard writers. Whether to
keep it as a consistency check or fold it into frame_index is an open decision; see
docs/findings/lerobot_format.md.

Set ``frame_start`` / ``frame_end`` on each Issue to the affected frames.

TODO: the user writes docs/specs/timestamps.md first; tests and implementation then
follow the check-workflow skill (.claude/skills/check-workflow/SKILL.md).
"""

from __future__ import annotations

import duckdb

from ..registry import CheckContext
from ..results import Issue

NAME = "timestamps"
VERSION = "1"


def run(con: duckdb.DuckDBPyConnection, ctx: CheckContext) -> list[Issue]:
    raise NotImplementedError
