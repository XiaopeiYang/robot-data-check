"""Census of LeRobot datasets on the Hub: the evidence for Phase 2 inclusion criteria.

Two steps, so the numbers in docs/research/hub_census.md can be reproduced from the
committed sample without hitting the Hub again:

    uv run python tools/research/hub_census.py collect   # sample + fetch meta/info.json
    uv run python tools/research/hub_census.py report    # statistics from the CSV

Only ``meta/info.json`` is fetched per dataset. Set ``HF_TOKEN`` to avoid rate limits.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "research" / "hub_census_sample.csv"
FIELDS = [
    "repo_id",
    "downloads",
    "last_modified",
    "readable",
    "error",
    "codebase_version",
    "robot_type",
    "fps",
    "total_episodes",
    "total_frames",
    "n_cameras",
]


def fetch(repo_id: str) -> dict:
    from huggingface_hub import hf_hub_download

    for attempt in range(4):
        try:
            path = hf_hub_download(repo_id, "meta/info.json", repo_type="dataset")
            info = json.loads(Path(path).read_text())
            feats = info.get("features") or {}
            return {
                "readable": True,
                "error": "",
                "codebase_version": info.get("codebase_version", ""),
                "robot_type": info.get("robot_type", ""),
                "fps": info.get("fps", ""),
                "total_episodes": info.get("total_episodes", ""),
                "total_frames": info.get("total_frames", ""),
                "n_cameras": sum(1 for f in feats.values() if f.get("dtype") in ("video", "image")),
            }
        except Exception as e:  # noqa: BLE001 - every failure is data for the census
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status == 429:
                time.sleep(5 * (attempt + 1))
                continue
            return {"readable": False, "error": type(e).__name__}
    return {"readable": False, "error": "rate_limited"}


def collect(n: int, seed: int, jobs: int) -> None:
    from huggingface_hub import HfApi

    api = HfApi()
    listed = list(api.list_datasets(filter="LeRobot", limit=1_000_000))
    print(f"{len(listed)} datasets tagged LeRobot ({datetime.now(timezone.utc):%Y-%m-%d})")
    sample = random.Random(seed).sample(listed, n)

    def row(d) -> dict:
        r = {
            "repo_id": d.id,
            "downloads": d.downloads or 0,
            "last_modified": f"{d.last_modified:%Y-%m-%d}" if d.last_modified else "",
        }
        r.update(fetch(d.id))
        return r

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        rows = list(pool.map(row, sample))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    meta = OUT.with_suffix(".json")
    meta.write_text(
        json.dumps(
            {
                "population": len(listed),
                "sample": n,
                "seed": seed,
                "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
            indent=2,
        )
    )
    print(f"wrote {OUT.relative_to(ROOT)} and {meta.relative_to(ROOT)}")


# ---------- report ----------


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (centre - half, centre + half)


def share(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.1f}% (95% CI {100 * lo:.1f}–{100 * hi:.1f}%)"


def quantiles(xs: list[float]) -> str:
    qs = statistics.quantiles(xs, n=20, method="inclusive")  # 5% steps
    pick = {"min": min(xs), "p10": qs[1], "p25": qs[4], "median": qs[9], "p75": qs[14],
            "p90": qs[17], "max": max(xs)}  # fmt: skip
    return ", ".join(f"{k} {v:,.0f}" for k, v in pick.items())


def report() -> None:
    meta = json.loads(OUT.with_suffix(".json").read_text())
    rows = list(csv.DictReader(OUT.open()))
    n = len(rows)
    ok = [r for r in rows if r["readable"] == "True"]
    print(f"population {meta['population']:,} (tagged LeRobot), sample {n}, seed {meta['seed']}, "
          f"collected {meta['collected_at'][:10]}")  # fmt: skip
    print(f"readable meta/info.json: {share(len(ok), n)}")
    print("unreadable reasons:", dict(Counter(r["error"] for r in rows if r["readable"] != "True")))
    print()
    vers = Counter(r["codebase_version"] for r in ok)
    for v, k in vers.most_common():
        print(f"codebase_version {v or '(missing)'}: {share(k, len(ok))}")
    print()
    eps = [int(r["total_episodes"]) for r in ok if r["total_episodes"].isdigit()]
    frames = [int(r["total_frames"]) for r in ok if r["total_frames"].isdigit()]
    print(f"total_episodes ({len(eps)} with a value): {quantiles(eps)}")
    print(f"total_frames   ({len(frames)} with a value): {quantiles(frames)}")
    for t in (0, 5, 10, 20, 50):
        k = sum(e <= t for e in eps) if t == 0 else sum(e < t for e in eps)
        label = "== 0" if t == 0 else f"< {t}"
        print(f"episodes {label}: {share(k, len(eps))}")
    print()
    print("robot_type top 10:", Counter(r["robot_type"] or "(missing)" for r in ok).most_common(10))
    print("cameras:", sorted(Counter(r["n_cameras"] for r in ok).items(), key=lambda x: int(x[0])))
    print("fps:", Counter(r["fps"] for r in ok).most_common(6))
    dl = [int(r["downloads"]) for r in rows]
    print(
        f"downloads (all {n}): {quantiles(dl)}; zero downloads: {share(sum(d == 0 for d in dl), n)}"
    )
    years = Counter(r["last_modified"][:7] for r in rows if r["last_modified"])
    print("last modified (top months):", years.most_common(6))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("-n", type=int, default=500)
    c.add_argument("--seed", type=int, default=0)
    c.add_argument("-j", "--jobs", type=int, default=4)
    sub.add_parser("report")
    args = ap.parse_args(argv)
    if args.cmd == "collect":
        collect(args.n, args.seed, args.jobs)
    else:
        report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
