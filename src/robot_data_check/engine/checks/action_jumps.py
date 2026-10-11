"""action_jumps: sudden spikes between consecutive actions.

Severity: warning.
Hint: per-dimension delta between consecutive frames; threshold from the
dataset's own delta distribution (e.g. a high quantile times a factor),
never a hard-coded constant.

Set ``frame_start`` / ``frame_end`` on each Issue to the affected frames.

TODO: the user writes docs/specs/action_jumps.md first; tests and implementation then
follow the check-workflow skill (.claude/skills/check-workflow/SKILL.md).
"""

from __future__ import annotations

import duckdb

from ..registry import CheckContext
from ..results import Issue

NAME = "action_jumps"
VERSION = "1"


def run(con: duckdb.DuckDBPyConnection, ctx: CheckContext) -> list[Issue]:
    raise NotImplementedError
