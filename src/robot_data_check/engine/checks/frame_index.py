"""frame_index: gaps, duplicates or a wrong start in per-episode frame indices.

In LeRobot, ``frame_index`` counts 0, 1, 2, ... within each episode. From
min / max / count / count-distinct per episode we get:

- duplicates = count - count_distinct
- missing    = (max - min + 1) - count_distinct      (holes inside the range)
- bad start  = min != 0

All three are errors: any of them means frames were lost or written twice.
"""

from __future__ import annotations

import duckdb

from ..registry import CheckContext
from ..results import Issue

NAME = "frame_index"
VERSION = "1"

SQL = """
WITH per_ep AS (
    SELECT
        episode_index,
        count(*)                    AS n,
        count(DISTINCT frame_index) AS n_distinct,
        min(frame_index)            AS lo,
        max(frame_index)            AS hi
    FROM frames
    GROUP BY episode_index
)
SELECT episode_index, 'duplicates' AS kind, n - n_distinct AS value FROM per_ep
WHERE n > n_distinct
UNION ALL
SELECT episode_index, 'missing', (hi - lo + 1) - n_distinct FROM per_ep
WHERE (hi - lo + 1) > n_distinct
UNION ALL
SELECT episode_index, 'bad_start', lo FROM per_ep
WHERE lo <> 0
ORDER BY episode_index, kind
"""

_DETAIL = {
    "duplicates": "{v:.0f} duplicated frame_index value(s)",
    "missing": "{v:.0f} frame_index value(s) missing inside the episode",
    "bad_start": "frame_index starts at {v:.0f} instead of 0",
}


def run(con: duckdb.DuckDBPyConnection, ctx: CheckContext) -> list[Issue]:
    return [
        Issue(episode_index=ep, severity="error", value=v, detail=_DETAIL[kind].format(v=v))
        for ep, kind, v in con.execute(SQL).fetchall()
    ]
