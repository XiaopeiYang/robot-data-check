"""episode_bounds: metadata length != actual frame count.

Severity: error.
Hint: join ``episodes`` (length, dataset_from_index, dataset_to_index) with a
per-episode ``count(*)`` from ``frames``. Also worth checking that the global
``index`` column of each episode spans exactly [dataset_from_index, dataset_to_index).

TODO: the user writes docs/specs/episode_bounds.md first; tests and implementation then
follow the check-workflow skill (.claude/skills/check-workflow/SKILL.md).
"""

from __future__ import annotations

import duckdb

from ..registry import CheckContext
from ..results import Issue

NAME = "episode_bounds"
VERSION = "1"


def run(con: duckdb.DuckDBPyConnection, ctx: CheckContext) -> list[Issue]:
    raise NotImplementedError
