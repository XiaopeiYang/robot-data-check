from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from robot_data_check.engine.loader import EpisodeRange, load_dataset
from robot_data_check.engine.registry import CheckContext
from robot_data_check.engine.results import Issue
from robot_data_check.engine.views import connect
from tests.synthetic import build


@pytest.fixture
def dataset_dir(tmp_path: Path) -> Path:
    """A fresh clean synthetic dataset; tests may inject faults into it."""
    return build(tmp_path / "ds")


@pytest.fixture
def run_check(dataset_dir: Path) -> Callable[..., list[Issue]]:
    """Load the dataset as it is *now* (after any injected faults) and run one check."""

    def _run(module, episodes: EpisodeRange | None = None) -> list[Issue]:
        ds = load_dataset(str(dataset_dir), episodes=episodes)
        ctx = CheckContext(dataset="synthetic", revision=ds.revision, fps=ds.fps, info=ds.info)
        return module.run(connect(ds), ctx)

    return _run
