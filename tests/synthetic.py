"""Build a small, clean LeRobot v3 dataset on disk, laid out like DROID.

Every check must report zero issues on it; fault-injection tests then break it
in one known way and assert that exactly that fault is found.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

FPS = 10
EPISODE_LENGTHS = [40, 55, 60, 45, 50]
DATA_FILE = "data/chunk-000/file-000.parquet"
EPISODES_FILE = "meta/episodes/chunk-000/file-000.parquet"


def build(root: Path) -> Path:
    for d in ("meta/episodes/chunk-000", "data/chunk-000"):
        (root / d).mkdir(parents=True, exist_ok=True)

    info = {
        "codebase_version": "v3.0",
        "robot_type": "synthetic",
        "fps": FPS,
        "total_episodes": len(EPISODE_LENGTHS),
        "total_frames": sum(EPISODE_LENGTHS),
        "data_path": "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet",
        "features": {},
    }
    (root / "meta/info.json").write_text(json.dumps(info, indent=2))
    (root / "meta/stats.json").write_text("{}")

    con = duckdb.connect()
    values = ", ".join(f"({i}, {n})" for i, n in enumerate(EPISODE_LENGTHS))
    con.execute(
        f"""
        CREATE TABLE eps AS
        SELECT episode_index, length,
               sum(length) OVER (ORDER BY episode_index) - length AS dataset_from_index
        FROM (VALUES {values}) t(episode_index, length)
        """
    )
    # Smooth trajectories: no jumps, no idle stretches.
    con.execute(
        f"""
        COPY (
            SELECT
                episode_index::BIGINT                            AS episode_index,
                frame_index::BIGINT                              AS frame_index,
                (frame_index / {FPS})::FLOAT                     AS timestamp,
                (dataset_from_index + frame_index)::BIGINT       AS "index",
                0::BIGINT                                        AS task_index,
                [sin(frame_index / 10 + d + episode_index)::FLOAT
                    FOR d IN range(8)]                           AS action,
                [cos(frame_index / 10 + d + episode_index)::FLOAT
                    FOR d IN range(8)]                           AS "observation.state"
            FROM (SELECT *, unnest(range(length)) AS frame_index FROM eps)
            ORDER BY "index"
        ) TO '{root / DATA_FILE}' (FORMAT parquet)
        """
    )
    con.execute(
        f"""
        COPY (
            SELECT episode_index::BIGINT AS episode_index,
                   ['pick up the cube'] AS tasks,
                   length::BIGINT AS length,
                   0::BIGINT AS "data/chunk_index",
                   0::BIGINT AS "data/file_index",
                   dataset_from_index::BIGINT AS dataset_from_index,
                   (dataset_from_index + length)::BIGINT AS dataset_to_index
            FROM eps ORDER BY episode_index
        ) TO '{root / EPISODES_FILE}' (FORMAT parquet)
        """
    )
    # Same layout as real LeRobot tasks.parquet: task text in the pandas index column.
    con.execute(
        f"""
        COPY (SELECT 0::BIGINT AS task_index, 'pick up the cube' AS __index_level_0__)
        TO '{root / "meta/tasks.parquet"}' (FORMAT parquet)
        """
    )
    return root
