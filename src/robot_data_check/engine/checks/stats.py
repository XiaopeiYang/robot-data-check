"""stats: ``meta/stats.json`` inconsistent with the actual data.

Severity: warning. Results here are dataset-level, not per-episode; decide how
to represent that in the results schema (e.g. episode_index = -1) and document it.
Hint: recompute mean / std / min / max of ``action`` and ``"observation.state"``
(list columns: ``UNNEST`` with an ordinal, or ``list_extract``) and compare.
Per-episode stats also live in ``episodes`` as ``"stats/<feature>/<stat>"`` columns.

TODO: the user writes docs/specs/stats.md first; tests and implementation then
follow the check-workflow skill (.claude/skills/check-workflow/SKILL.md).
"""

from __future__ import annotations

import duckdb

from ..registry import CheckContext
from ..results import Issue

NAME = "stats"
VERSION = "1"


def run(con: duckdb.DuckDBPyConnection, ctx: CheckContext) -> list[Issue]:
    raise NotImplementedError
