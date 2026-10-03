"""frame_index: gaps, duplicates or a wrong start in per-episode frame indices.

In LeRobot, ``frame_index`` counts 0, 1, 2, ... within each episode. Comparing
each frame with the previous one (``LAG``) gives:

- missing    one issue per gap, located at the missing frame indices
- duplicates one issue per episode, spanning the first..last duplicated index
- bad start  min(frame_index) != 0, located at the frames before the first one

All three are errors: any of them means frames were lost or written twice.
"""

from __future__ import annotations

import duckdb

from ..registry import CheckContext
from ..results import Issue

NAME = "frame_index"
VERSION = "2"

SQL = """
WITH f AS (
    SELECT
        episode_index,
        frame_index,
        LAG(frame_index) OVER (PARTITION BY episode_index ORDER BY frame_index) AS prev
    FROM frames
)
SELECT episode_index, 'missing' AS kind, frame_index - prev - 1 AS value,
       prev + 1 AS frame_start, frame_index - 1 AS frame_end
FROM f WHERE frame_index > prev + 1
UNION ALL
SELECT episode_index, 'duplicates', count(*), min(frame_index), max(frame_index)
FROM f WHERE frame_index = prev GROUP BY episode_index
UNION ALL
SELECT episode_index, 'bad_start', min(frame_index), 0, min(frame_index) - 1
FROM f GROUP BY episode_index HAVING min(frame_index) > 0
ORDER BY episode_index, frame_start, kind
"""

_DETAIL = {
    "duplicates": "{v:.0f} duplicated frame_index value(s)",
    "missing": "{v:.0f} frame_index value(s) missing",
    "bad_start": "frame_index starts at {v:.0f} instead of 0",
}


def run(con: duckdb.DuckDBPyConnection, ctx: CheckContext) -> list[Issue]:
    return [
        Issue(
            episode_index=ep,
            severity="error",
            value=v,
            detail=_DETAIL[kind].format(v=v),
            frame_start=lo,
            frame_end=hi,
        )
        for ep, kind, v, lo, hi in con.execute(SQL).fetchall()
    ]
