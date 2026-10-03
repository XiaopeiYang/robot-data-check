"""Locate (and if needed download) the parts of a LeRobot v3 dataset that checks need.

Only metadata and frame data are fetched, never videos. For a Hub dataset only
the episode-metadata files and data files that cover the requested episode
range are downloaded, so checking the first 200 episodes of DROID costs about
two files instead of the whole dataset.

A LeRobot v3 dataset looks like::

    meta/info.json                                  fps, features, path templates
    meta/stats.json                                 dataset-wide normalization stats
    meta/tasks.parquet                              task_index -> task text
    meta/episodes/chunk-XXX/file-YYY.parquet        one row per episode (+ per-episode stats)
    data/chunk-XXX/file-YYY.parquet                 one row per frame, many episodes per file
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

SUPPORTED_VERSIONS = ("v3.0",)


@dataclass(frozen=True)
class EpisodeRange:
    """Half-open range of episode indices: ``start <= episode_index < stop``."""

    start: int
    stop: int

    @classmethod
    def parse(cls, spec: str) -> EpisodeRange:
        """Parse ``"0-200"`` (episodes 0..199) or ``"17"`` (just episode 17)."""
        if "-" in spec:
            a, b = spec.split("-", 1)
            start, stop = int(a), int(b)
        else:
            start = int(spec)
            stop = start + 1
        if start < 0 or stop <= start:
            raise ValueError(f"invalid episode range: {spec!r}")
        return cls(start, stop)

    def __str__(self) -> str:
        return f"{self.start}-{self.stop}"


@dataclass(frozen=True)
class LoadedDataset:
    dataset: str
    revision: str
    info: dict
    episode_range: EpisodeRange | None
    episode_files: list[Path]
    data_files: list[Path]
    tasks_file: Path
    stats_file: Path | None

    @property
    def fps(self) -> float:
        return float(self.info["fps"])


def load_dataset(
    dataset: str, episodes: EpisodeRange | None = None, revision: str | None = None
) -> LoadedDataset:
    """Load a dataset from a local directory or a Hugging Face Hub repo id."""
    local = Path(dataset)
    if local.is_dir():
        fetch, listing, rev = _local_source(local)
    else:
        fetch, listing, rev = _hub_source(dataset, revision)

    info = json.loads(fetch("meta/info.json").read_text())
    version = info.get("codebase_version")
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(
            f"{dataset}: codebase_version {version!r} is not supported "
            f"(supported: {', '.join(SUPPORTED_VERSIONS)})"
        )

    episode_files = _fetch_episode_files(fetch, listing, episodes)
    data_files = [
        fetch(info["data_path"].format(chunk_index=c, file_index=f))
        for c, f in _data_file_indices(episode_files, episodes)
    ]
    stats = "meta/stats.json"
    return LoadedDataset(
        dataset=dataset,
        revision=rev,
        info=info,
        episode_range=episodes,
        episode_files=episode_files,
        data_files=data_files,
        tasks_file=fetch("meta/tasks.parquet"),
        stats_file=fetch(stats) if stats in listing else None,
    )


Fetch = Callable[[str], Path]


def _local_source(root: Path) -> tuple[Fetch, set[str], str]:
    listing = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    return (lambda rel: root / rel), listing, "local"


def _hub_source(repo_id: str, revision: str | None) -> tuple[Fetch, set[str], str]:
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    # Pin to a commit sha so every file comes from the same snapshot and the
    # revision recorded in the results is reproducible.
    sha = api.dataset_info(repo_id, revision=revision).sha
    listing = set(api.list_repo_files(repo_id, repo_type="dataset", revision=sha))

    def fetch(rel: str) -> Path:
        return Path(hf_hub_download(repo_id, rel, repo_type="dataset", revision=sha))

    return fetch, listing, sha


def _fetch_episode_files(
    fetch: Fetch, listing: set[str], episodes: EpisodeRange | None
) -> list[Path]:
    """Fetch episode-metadata files in order until the requested range is covered.

    Files are ordered by episode index, so we can stop as soon as one reaches
    past the end of the range. Files that end before the range starts are skipped.
    """
    rels = sorted(r for r in listing if r.startswith("meta/episodes/") and r.endswith(".parquet"))
    if not rels:
        raise FileNotFoundError("no meta/episodes/*.parquet files found")
    out: list[Path] = []
    for rel in rels:
        path = fetch(rel)
        if episodes is None:
            out.append(path)
            continue
        hi = pc.max(pq.read_table(path, columns=["episode_index"]).column(0)).as_py()
        if hi >= episodes.start:
            out.append(path)
        if hi >= episodes.stop - 1:
            break
    return out


def _data_file_indices(
    episode_files: list[Path], episodes: EpisodeRange | None
) -> list[tuple[int, int]]:
    cols = ["episode_index", "data/chunk_index", "data/file_index"]
    pairs: set[tuple[int, int]] = set()
    for path in episode_files:
        t = pq.read_table(path, columns=cols).to_pydict()
        for ep, c, f in zip(*(t[k] for k in cols), strict=True):
            if episodes is None or episodes.start <= ep < episodes.stop:
                pairs.add((c, f))
    return sorted(pairs)
