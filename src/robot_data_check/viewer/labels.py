"""Human review labels for flagged issues: "real" or "false_positive".

Labels are appended to a JSON-lines file next to the results, one line per click, so
the full history is kept and the latest label for an issue wins. They are the raw
material for estimating false-positive rates on real data (see docs/vision.md).

An issue is identified by (dataset, revision, episode_index, check_name, frame_start,
frame_end); labels from another dataset revision are ignored.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

Label = Literal["real", "false_positive"]
IssueKey = tuple[int, str, int | None, int | None]


class LabelStore:
    def __init__(self, path: Path, dataset: str, revision: str) -> None:
        self.path = path
        self.dataset = dataset
        self.revision = revision
        self._lock = threading.Lock()

    def add(
        self,
        episode_index: int,
        check_name: str,
        frame_start: int | None,
        frame_end: int | None,
        label: Label,
    ) -> dict:
        record = {
            "dataset": self.dataset,
            "dataset_revision": self.revision,
            "episode_index": episode_index,
            "check_name": check_name,
            "frame_start": frame_start,
            "frame_end": frame_end,
            "label": label,
            "labelled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps(record) + "\n")
        return record

    def latest(self) -> dict[IssueKey, Label]:
        """Latest label per issue for this dataset revision."""
        out: dict[IssueKey, Label] = {}
        if not self.path.exists():
            return out
        with self._lock:
            lines = self.path.read_text().splitlines()
        for line in lines:
            if not line.strip():
                continue
            r = json.loads(line)
            if (r["dataset"], r["dataset_revision"]) != (self.dataset, self.revision):
                continue
            key = (r["episode_index"], r["check_name"], r["frame_start"], r["frame_end"])
            out[key] = r["label"]
        return out
