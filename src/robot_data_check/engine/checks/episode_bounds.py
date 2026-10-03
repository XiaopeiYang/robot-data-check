"""episode_bounds: metadata length != actual frame count.

Severity: error.
Hint: join ``episodes`` (length, dataset_from_index, dataset_to_index) with a
per-episode ``count(*)`` from ``frames``. Also worth checking that the global
``index`` column of each episode spans exactly [dataset_from_index, dataset_to_index).

TODO(you): implement, then add this module to ALL_CHECKS in checks/__init__.py
and add a fault-injection test (see tests/fault_injection/test_frame_index.py).
"""

from __future__ import annotations

import duckdb

from ..registry import CheckContext
from ..results import Issue

NAME = "episode_bounds"
VERSION = "1"


def run(con: duckdb.DuckDBPyConnection, ctx: CheckContext) -> list[Issue]:
    raise NotImplementedError
