"""Episode viewer: a thin web adapter over the engine and the results table.

Serves a static single-page app plus a small JSON API. Videos of Hub datasets
are streamed by the browser straight from the Hub with HTTP range requests (one
video file holds many episodes; the page seeks to the episode's segment), so
nothing large is downloaded. Local datasets get their videos served from disk.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..engine.loader import LoadedDataset
from ..engine.results import DATASET_LEVEL, RESULTS_SCHEMA
from ..engine.views import connect

STATIC_DIR = Path(__file__).parent / "static"

# Per-episode attributes worth showing next to quality results, when present.
EPISODE_ATTRS = ["is_episode_successful", "building", "collector_id", "date"]
SERIES_KEYS = ["action", "observation.state"]


def create_app(ds: LoadedDataset, results: pa.Table | None = None) -> FastAPI:
    con = connect(ds)
    # Copy into a real table: registered Arrow views are not visible to the
    # per-request cursors below.
    con.register("results_arrow", results if results is not None else RESULTS_SCHEMA.empty_table())
    con.execute("CREATE TABLE results AS SELECT * FROM results_arrow")
    con.unregister("results_arrow")

    frame_cols = {r[0] for r in con.execute("DESCRIBE frames").fetchall()}
    episode_cols = {r[0] for r in con.execute("DESCRIBE episodes").fetchall()}
    attrs = [c for c in EPISODE_ATTRS if c in frame_cols]
    series_keys = [k for k in SERIES_KEYS if k in frame_cols]
    cameras = [k for k in ds.video_keys if f"videos/{k}/from_timestamp" in episode_cols]

    attr_sql = "".join(f', any_value("{c}") AS "{c}"' for c in attrs)
    con.execute(
        f"""
        CREATE TABLE episode_list AS
        SELECT e.episode_index, e.length,
               {"e.tasks[1]" if "tasks" in episode_cols else "NULL"} AS task,
               coalesce(r.errors, 0) AS errors,
               coalesce(r.warnings, 0) AS warnings,
               coalesce(r.checks, []) AS checks
               {"".join(f', a."{c}"' for c in attrs)}
        FROM episodes e
        LEFT JOIN (
            SELECT episode_index,
                   count(*) FILTER (severity = 'error')   AS errors,
                   count(*) FILTER (severity = 'warning') AS warnings,
                   list(DISTINCT check_name ORDER BY check_name) AS checks
            FROM results GROUP BY 1
        ) r USING (episode_index)
        LEFT JOIN (SELECT episode_index {attr_sql} FROM frames GROUP BY 1) a USING (episode_index)
        """
    )

    app = FastAPI(title="robot-data-check viewer")

    def q(sql: str, params: list | None = None) -> list[dict]:
        cur = con.cursor()  # DuckDB connections are not thread-safe; cursors are
        rel = cur.execute(sql, params or [])
        names = [d[0] for d in rel.description]
        return [dict(zip(names, row, strict=True)) for row in rel.fetchall()]

    def video_url(rel: str) -> str:
        return ds.remote_url(rel) or f"/videos/{rel}"

    @app.get("/api/meta")
    def meta() -> dict:
        checks = [r["check_name"] for r in q("SELECT DISTINCT check_name FROM results ORDER BY 1")]
        return {
            "dataset": ds.dataset,
            "revision": ds.revision,
            "fps": ds.fps,
            "cameras": cameras,
            "checks": checks,
            "dataset_issues": q(
                "SELECT count(*) FILTER (severity = 'error') AS errors, "
                "count(*) FILTER (severity = 'warning') AS warnings "
                "FROM results WHERE episode_index = ?",
                [DATASET_LEVEL],
            )[0],
            "attrs": attrs,
            "series": {k: ds.info.get("features", {}).get(k, {}).get("names") for k in series_keys},
        }

    @app.get("/api/episodes")
    def episodes(
        check: str | None = None,
        severity: str | None = Query(None, pattern="^(error|warning)$"),
        sort: str = Query("worst", pattern="^(worst|index)$"),
    ) -> list[dict]:
        where, params = [], []
        if check or severity:
            cond = ["r.episode_index = l.episode_index"]
            if check:
                cond.append("r.check_name = ?")
                params.append(check)
            if severity:
                cond.append("r.severity = ?")
                params.append(severity)
            where.append(f"EXISTS (SELECT 1 FROM results r WHERE {' AND '.join(cond)})")
        order = "errors DESC, warnings DESC, episode_index" if sort == "worst" else "episode_index"
        return q(
            f"SELECT * FROM episode_list l {'WHERE ' + ' AND '.join(where) if where else ''} "
            f"ORDER BY {order}",
            params,
        )

    @app.get("/api/dataset")
    def dataset_issues() -> dict:
        """Issues about the whole dataset (episode_index = DATASET_LEVEL)."""
        issues = q(
            """
            SELECT check_name, check_version, severity, value, detail, frame_start, frame_end
            FROM results WHERE episode_index = ?
            ORDER BY severity, check_name
            """,
            [DATASET_LEVEL],
        )
        return {"issues": issues}

    @app.get("/api/episodes/{episode_index}")
    def episode(episode_index: int) -> dict:
        rows = q("SELECT * FROM episode_list WHERE episode_index = ?", [episode_index])
        if not rows:
            raise HTTPException(404, f"episode {episode_index} not loaded")
        issues = q(
            """
            SELECT check_name, check_version, severity, value, detail, frame_start, frame_end
            FROM results WHERE episode_index = ?
            ORDER BY severity, coalesce(frame_start, -1), check_name
            """,
            [episode_index],
        )
        videos = []
        for cam in cameras:
            c = f"videos/{cam}"
            [seg] = q(
                f'SELECT "{c}/chunk_index" AS chunk, "{c}/file_index" AS file, '
                f'"{c}/from_timestamp" AS t0, "{c}/to_timestamp" AS t1 '
                "FROM episodes WHERE episode_index = ?",
                [episode_index],
            )
            rel = ds.video_path(cam, seg["chunk"], seg["file"])
            videos.append(
                {"camera": cam, "url": video_url(rel), "from_ts": seg["t0"], "to_ts": seg["t1"]}
            )
        return {**rows[0], "issues": issues, "videos": videos}

    @app.get("/api/episodes/{episode_index}/series")
    def series(episode_index: int) -> dict:
        """Per-frame signals, transposed to one array per dimension for plotting."""
        cols = "".join(f', "{k}"' for k in series_keys)
        cur = con.cursor()
        rows = cur.execute(
            f"SELECT frame_index, timestamp {cols} FROM frames "
            "WHERE episode_index = ? ORDER BY frame_index",
            [episode_index],
        ).fetchall()
        if not rows:
            raise HTTPException(404, f"episode {episode_index} not loaded")
        out: dict = {
            "frame_index": [r[0] for r in rows],
            "timestamp": [r[1] for r in rows],
            "series": {},
        }
        for j, key in enumerate(series_keys, start=2):
            first = rows[0][j]
            if isinstance(first, list):
                out["series"][key] = [[r[j][d] for r in rows] for d in range(len(first))]
            else:
                out["series"][key] = [[r[j] for r in rows]]
        return out

    if ds.local_root is not None:
        videos_root = (ds.local_root / "videos").resolve()

        @app.get("/videos/{rel:path}")
        def local_video(rel: str) -> FileResponse:
            path = (ds.local_root / rel).resolve()
            if not path.is_relative_to(videos_root) or not path.is_file():
                raise HTTPException(404)
            return FileResponse(path, media_type="video/mp4")  # supports Range requests

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
