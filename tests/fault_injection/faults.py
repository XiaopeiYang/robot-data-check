"""Fault injectors: each one breaks a synthetic dataset in exactly one known way.

They rewrite the frame data file with a SQL ``SELECT`` over the current frames
(available as the relation ``f``). Metadata is deliberately left untouched, so
for example deleting frames also makes ``episodes.length`` stale, as it would
in a real recording bug.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from tests.synthetic import DATA_FILE


def rewrite_frames(root: Path, select_sql: str) -> None:
    path = root / DATA_FILE
    tmp = path.with_suffix(".tmp.parquet")
    con = duckdb.connect()
    con.execute(f"CREATE VIEW f AS SELECT * FROM '{path}'")
    con.execute(f"COPY ({select_sql}) TO '{tmp}' (FORMAT parquet)")
    tmp.replace(path)


def delete_frames(root: Path, episode: int, frame_indices: list[int]) -> None:
    ids = ", ".join(map(str, frame_indices))
    rewrite_frames(
        root,
        f"SELECT * FROM f WHERE NOT (episode_index = {episode} AND frame_index IN ({ids}))"
        ' ORDER BY "index"',
    )


def duplicate_frame(root: Path, episode: int, frame_index: int) -> None:
    rewrite_frames(
        root,
        f"SELECT * FROM f UNION ALL "
        f"SELECT * FROM f WHERE episode_index = {episode} AND frame_index = {frame_index}"
        ' ORDER BY "index"',
    )
