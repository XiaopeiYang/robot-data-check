"""The check interface and the runner that turns check output into result rows.

A check is a plain module-level function plus a name and a version::

    NAME = "frame_index"
    VERSION = "1"          # bump whenever the logic changes: pipelines use it to
                           # decide which results are stale and must be recomputed

    def run(con: duckdb.DuckDBPyConnection, ctx: CheckContext) -> list[Issue]: ...

``run`` may only read the views described in ``views.py`` and the context. It
returns ``Issue``s; it never writes files or builds full result rows.
When a problem sits at a specific place in the episode (a dropped frame, a
spike, an idle stretch), set ``frame_start`` / ``frame_end`` on the Issue so the
viewer can mark it on the timeline.
Anomaly thresholds must be derived from the data itself, not hard-coded.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import duckdb
import pyarrow as pa

from .results import Issue, Provenance, issues_to_rows, to_table


@dataclass(frozen=True)
class CheckContext:
    dataset: str
    revision: str
    fps: float
    info: dict


@dataclass(frozen=True)
class Check:
    name: str
    version: str
    run: Callable[[duckdb.DuckDBPyConnection, CheckContext], list[Issue]]


def run_checks(
    con: duckdb.DuckDBPyConnection,
    ctx: CheckContext,
    checks: list[Check],
    shard: str,
) -> pa.Table:
    prov = Provenance(dataset=ctx.dataset, dataset_revision=ctx.revision, shard=shard)
    rows: list[dict] = []
    for check in checks:
        rows += issues_to_rows(check.run(con, ctx), prov, check.name, check.version)
    return to_table(rows)
