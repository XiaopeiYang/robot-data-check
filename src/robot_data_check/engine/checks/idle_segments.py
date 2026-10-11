"""idle_segments: robot not moving for long stretches.

Severity: warning.
Hint: rolling-window change of ``"observation.state"``; flag runs where the
change stays below a data-derived threshold for longer than N seconds
(convert seconds to frames with ctx.fps).

Set ``frame_start`` / ``frame_end`` on each Issue to the affected frames.

TODO: the user writes docs/specs/idle_segments.md first; tests and implementation then
follow the check-workflow skill (.claude/skills/check-workflow/SKILL.md).
"""

from __future__ import annotations

import duckdb

from ..registry import CheckContext
from ..results import Issue

NAME = "idle_segments"
VERSION = "1"


def run(con: duckdb.DuckDBPyConnection, ctx: CheckContext) -> list[Issue]:
    raise NotImplementedError
