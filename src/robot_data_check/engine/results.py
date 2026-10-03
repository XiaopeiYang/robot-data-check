"""The results table: the one stable contract every interface depends on.

Checks never build full result rows themselves. They return ``Issue`` objects
(what they found), and the runner stamps on provenance (dataset, revision,
shard, check name and version). That way a check cannot get the contract wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pyarrow as pa
import pyarrow.parquet as pq

Severity = Literal["error", "warning"]

RESULTS_SCHEMA = pa.schema(
    [
        pa.field("dataset", pa.string(), nullable=False),
        pa.field("dataset_revision", pa.string(), nullable=False),
        pa.field("shard", pa.string(), nullable=False),
        pa.field("episode_index", pa.int64(), nullable=False),
        pa.field("check_name", pa.string(), nullable=False),
        pa.field("check_version", pa.string(), nullable=False),
        pa.field("severity", pa.string(), nullable=False),
        pa.field("value", pa.float64()),
        pa.field("detail", pa.string()),
    ]
)


@dataclass(frozen=True)
class Issue:
    """One problem found by a check in one episode."""

    episode_index: int
    severity: Severity
    value: float | None
    detail: str


@dataclass(frozen=True)
class Provenance:
    """Where a batch of results came from. Filled in by the runner, not by checks."""

    dataset: str
    dataset_revision: str
    shard: str


def to_table(rows: list[dict]) -> pa.Table:
    return pa.Table.from_pylist(rows, schema=RESULTS_SCHEMA)


def issues_to_rows(
    issues: list[Issue], prov: Provenance, check_name: str, check_version: str
) -> list[dict]:
    return [
        {
            "dataset": prov.dataset,
            "dataset_revision": prov.dataset_revision,
            "shard": prov.shard,
            "episode_index": int(i.episode_index),
            "check_name": check_name,
            "check_version": check_version,
            "severity": i.severity,
            "value": None if i.value is None else float(i.value),
            "detail": i.detail,
        }
        for i in issues
    ]


def write_results(table: pa.Table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)
