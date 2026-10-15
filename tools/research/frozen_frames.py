"""Feasibility study: do frozen / repeated camera frames occur in real LeRobot datasets?

LeRobot stores timestamp = frame_index / fps, so recording stalls are invisible in the
tabular data (docs/findings/lerobot_format.md). A stalled camera shows up as an image that
does not change between frames **while the robot state does**: a static scene with a
still robot is not evidence of anything.

    uv run python tools/research/frozen_frames.py collect   # decode sampled episodes
    uv run python tools/research/frozen_frames.py report    # statistics from the parquet

``collect`` writes one row per consecutive frame pair (dataset, camera, episode,
frame_index, image difference, state change) to docs/research/frozen_frames_pairs.parquet,
so ``report`` is reproducible without decoding again.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from robot_data_check.engine.loader import EpisodeRange, load_dataset
from robot_data_check.engine.video import iter_episode_frames
from robot_data_check.engine.views import connect

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "research" / "frozen_frames_pairs.parquet"
STRIDE = 4  # spatial downsampling before comparing frames

SAMPLES = [
    # (repo, revision, episode range loaded, how many episodes to sample from it)
    ("lerobot/droid_1.0.1", "0eabc778f959c54b8c5aa3626cc1128d2d2e54d4", (0, 1000), 50),
    ("lerobot/svla_so100_sorting", "13870ca969084d8ce4d8a0391b06cead78e804ba", (0, 52), 52),
]


def episode_pairs(ds, con, camera: str, ep: int) -> tuple[list[dict], dict]:
    t = time.perf_counter()
    prev, rows = None, []
    for fi, img in iter_episode_frames(ds, con, camera, ep):
        small = img[::STRIDE, ::STRIDE].astype(np.int16)
        if prev is not None:
            rows.append({"frame_index": fi, "img_diff": float(np.abs(small - prev[1]).mean())})
        prev = (fi, small)
    cost = {"seconds": time.perf_counter() - t, "frames": len(rows) + (prev is not None)}
    return rows, cost


def state_deltas(con, ep: int) -> dict[int, float]:
    """Largest absolute per-dimension change of observation.state from the previous frame."""
    rows = con.execute(
        """
        WITH s AS (
            SELECT frame_index, "observation.state" AS st,
                   LAG("observation.state") OVER (ORDER BY frame_index) AS prev
            FROM frames WHERE episode_index = ?)
        SELECT frame_index,
               list_max(list_transform(range(1, len(st) + 1), i -> abs(st[i] - prev[i])))
        FROM s WHERE prev IS NOT NULL
        """,
        [ep],
    ).fetchall()
    return {fi: float(d) for fi, d in rows}


def collect(jobs: int, seed: int) -> None:
    out_rows, costs = [], []
    for repo, rev, (a, b), n in SAMPLES:
        ds = load_dataset(repo, episodes=EpisodeRange(a, b), revision=rev)
        con = connect(ds)
        all_eps = [
            r[0] for r in con.execute("SELECT episode_index FROM episodes ORDER BY 1").fetchall()
        ]
        eps = sorted(random.Random(seed).sample(all_eps, min(n, len(all_eps))))
        deltas = {ep: state_deltas(con.cursor(), ep) for ep in eps}
        tasks = [(cam, ep) for cam in ds.video_keys for ep in eps]
        print(f"{repo}: {len(eps)} episodes x {len(ds.video_keys)} cameras", flush=True)

        def run(task, ds=ds, con=con, repo=repo):
            cam, ep = task
            rows, cost = episode_pairs(ds, con.cursor(), cam, ep)
            return repo, cam, ep, rows, cost

        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for i, (repo_, cam, ep, rows, cost) in enumerate(pool.map(run, tasks), 1):
                for r in rows:
                    r.update(dataset=repo_, camera=cam, episode_index=ep,
                             state_delta=deltas[ep].get(r["frame_index"]))  # fmt: skip
                out_rows += rows
                costs.append({"dataset": repo_, "camera": cam, "episode_index": ep, **cost})
                if i % 20 == 0:
                    print(f"  {i}/{len(tasks)}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(out_rows), OUT, compression="zstd")
    meta = {
        "samples": [{"repo": r, "revision": v, "range": list(g), "n": n} for r, v, g, n in SAMPLES],
        "seed": seed,
        "stride": STRIDE,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "costs": costs,
    }
    OUT.with_suffix(".json").write_text(json.dumps(meta, indent=1))
    print(f"wrote {len(out_rows)} pairs to {OUT.relative_to(ROOT)}")


# Every number in docs/research/frozen_frames.md comes from one of these queries.
REPORT = {
    "Cost per episode and camera (seconds, frames)": """
        SELECT dataset, camera, count(*) AS episodes, round(median(seconds), 2) AS median_s,
               round(max(seconds), 1) AS max_s, sum(frames) AS frames,
               round(sum(frames) / sum(seconds)) AS frames_per_s
        FROM c GROUP BY ALL ORDER BY ALL""",
    "Image difference of consecutive frames (mean |delta gray|, 0-255)": """
        SELECT dataset, camera, count(*) AS pairs,
               round(quantile_cont(img_diff, 0.001), 3) AS p0_1,
               round(quantile_cont(img_diff, 0.01), 3) AS p1,
               round(quantile_cont(img_diff, 0.1), 2) AS p10,
               round(median(img_diff), 2) AS p50,
               round(quantile_cont(img_diff, 0.9), 2) AS p90
        FROM p GROUP BY ALL ORDER BY ALL""",
    "Exactly identical vs. merely small differences": """
        SELECT dataset, camera, count(*) AS pairs,
               count(*) FILTER (img_diff = 0) AS identical,
               round(100.0 * count(*) FILTER (img_diff = 0) / count(*), 1) AS identical_pct,
               min(img_diff) FILTER (img_diff > 0) AS smallest_nonzero,
               count(*) FILTER (img_diff < 0.05 * m.med) AS below_5pct_of_median
        FROM p JOIN (SELECT dataset, camera, median(img_diff) AS med FROM p GROUP BY ALL) m
             USING (dataset, camera)
        GROUP BY ALL ORDER BY ALL""",
    "Robot motion during identical pairs (state change above the dataset median?)": """
        SELECT dataset, camera, count(*) AS identical,
               count(*) FILTER (state_delta > s.med) AS while_moving
        FROM p JOIN (SELECT dataset, median(state_delta) AS med FROM p GROUP BY ALL) s
             USING (dataset)
        WHERE img_diff = 0 GROUP BY ALL ORDER BY ALL""",
    "Gap in frames between consecutive identical pairs (top 3 per camera)": """
        WITH z AS (
            SELECT dataset, camera, frame_index - LAG(frame_index) OVER (
                       PARTITION BY dataset, camera, episode_index ORDER BY frame_index) AS gap
            FROM p WHERE img_diff = 0),
        g AS (SELECT dataset, camera, gap, count(*) AS n FROM z WHERE gap IS NOT NULL
              GROUP BY dataset, camera, gap)
        SELECT dataset, camera, gap, n,
               round(100.0 * n / sum(n) OVER (PARTITION BY dataset, camera), 1) AS pct
        FROM g
        QUALIFY row_number() OVER (PARTITION BY dataset, camera ORDER BY n DESC) <= 3
        ORDER BY dataset, camera, n DESC""",
    "Per-episode share of identical pairs (%)": """
        SELECT dataset, camera, round(min(r), 1) AS min_pct, round(median(r), 1) AS median_pct,
               round(max(r), 1) AS max_pct
        FROM (SELECT dataset, camera, episode_index,
                     100.0 * count(*) FILTER (img_diff = 0) / count(*) AS r
              FROM p GROUP BY dataset, camera, episode_index)
        GROUP BY dataset, camera ORDER BY ALL""",
    "Identical in two cameras at the same frame (same episode)": """
        SELECT a.dataset, a.camera AS camera_a, b.camera AS camera_b,
               count(*) FILTER (a.img_diff = 0 AND b.img_diff = 0) AS both_identical
        FROM p a JOIN p b ON a.dataset = b.dataset AND a.episode_index = b.episode_index
             AND a.frame_index = b.frame_index AND a.camera < b.camera
        GROUP BY ALL ORDER BY ALL""",
    "Longest run of consecutive identical pairs": """
        WITH z AS (
            SELECT dataset, camera, episode_index,
                   frame_index - row_number() OVER (
                       PARTITION BY dataset, camera, episode_index ORDER BY frame_index) AS grp
            FROM p WHERE img_diff = 0)
        SELECT dataset, camera, count(*) AS runs, max(n) AS longest
        FROM (SELECT dataset, camera, episode_index, grp, count(*) AS n FROM z GROUP BY ALL)
        GROUP BY ALL ORDER BY ALL""",
}


def report() -> None:
    meta = json.loads(OUT.with_suffix(".json").read_text())
    con = duckdb.connect()
    con.execute(f"CREATE VIEW p AS SELECT * FROM '{OUT}'")
    con.register("c", pa.Table.from_pylist(meta["costs"]))
    print(f"collected {meta['collected_at'][:10]}, seed {meta['seed']}, stride {meta['stride']}")
    for title, sql in REPORT.items():
        print(f"\n## {title}")
        con.sql(sql).show(max_width=200)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("-j", "--jobs", type=int, default=4)
    c.add_argument("--seed", type=int, default=0)
    sub.add_parser("report")
    args = ap.parse_args(argv)
    collect(args.jobs, args.seed) if args.cmd == "collect" else report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
