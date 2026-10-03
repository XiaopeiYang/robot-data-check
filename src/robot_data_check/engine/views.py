"""DuckDB views over a loaded dataset. Checks are written as SQL against these.

Views (already filtered to the requested episode range):

- ``frames``   one row per frame; columns exactly as in the dataset's data files
               (``episode_index``, ``frame_index``, ``timestamp``, ``index``, ``task_index``,
               ``action``, ``"observation.state"``, ...).
- ``episodes`` one row per episode from ``meta/episodes``: ``episode_index``, ``length``,
               ``dataset_from_index``, ``dataset_to_index``, ``tasks``, plus per-episode
               stats columns such as ``"stats/action/mean"``.
- ``tasks``    ``task_index``, ``task``.

Column names containing ``.`` or ``/`` must be double-quoted in SQL.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from .loader import LoadedDataset


def _sql_list(paths: list[Path]) -> str:
    return "[" + ", ".join("'" + str(p).replace("'", "''") + "'" for p in paths) + "]"


def connect(ds: LoadedDataset) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    where = ""
    if ds.episode_range is not None:
        r = ds.episode_range
        where = f"WHERE episode_index >= {r.start} AND episode_index < {r.stop}"

    con.execute(
        f"CREATE VIEW frames AS SELECT * FROM read_parquet({_sql_list(ds.data_files)}) {where}"
    )
    con.execute(
        f"CREATE VIEW episodes AS "
        f"SELECT * FROM read_parquet({_sql_list(ds.episode_files)}, union_by_name = true) {where}"
    )

    # tasks.parquet is written by pandas; depending on the writer the task text is
    # a regular "task" column or the leftover pandas index "__index_level_0__".
    tasks_path = _sql_list([ds.tasks_file])[1:-1]
    cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {tasks_path}").fetchall()}
    task_col = "task" if "task" in cols else "__index_level_0__"
    con.execute(f"CREATE VIEW tasks AS SELECT task_index, {task_col} AS task FROM {tasks_path}")
    return con
