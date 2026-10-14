"""episode_bounds: metadata length != actual frame count.

Severity: error.
Hint: join ``episodes`` (length, dataset_from_index, dataset_to_index) with a
per-episode ``count(*)`` from ``frames``. Also worth checking that the global
``index`` column of each episode spans exactly [dataset_from_index, dataset_to_index).

TODO: written by hand by the user (code + fault-injection test), then reviewed with
the review-check skill. Start from checks/frame_index.py and its test.
"""

from __future__ import annotations

import duckdb

from ..registry import CheckContext
from ..results import Issue

NAME = "episode_bounds"
VERSION = "1"


def run(con: duckdb.DuckDBPyConnection, ctx: CheckContext) -> list[Issue]:
    raise NotImplementedError
