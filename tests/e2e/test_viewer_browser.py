"""Browser end-to-end tests for the episode viewer (opt-in).

Run with ``ROBOCHECK_E2E=1 uv run --group e2e pytest tests/e2e``; see docs/dev-setup.md for
getting a headless Chromium to start without root. Skipped otherwise, so CI and the
default test run do not need a browser.
"""

from __future__ import annotations

import glob
import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest

if os.environ.get("ROBOCHECK_E2E") != "1":
    pytest.skip("set ROBOCHECK_E2E=1 to run browser tests", allow_module_level=True)
sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

from robot_data_check.engine.checks import ALL_CHECKS  # noqa: E402
from robot_data_check.engine.loader import load_dataset  # noqa: E402
from robot_data_check.engine.registry import CheckContext, run_checks  # noqa: E402
from robot_data_check.engine.results import DATASET_LEVEL, to_table  # noqa: E402
from robot_data_check.engine.views import connect  # noqa: E402
from robot_data_check.viewer.server import create_app  # noqa: E402
from tests.fault_injection.faults import delete_frames  # noqa: E402

pytestmark = pytest.mark.e2e


def find_chromium() -> str | None:
    """CHROMIUM_PATH, else Playwright's headless shell from its browser cache."""
    if os.environ.get("CHROMIUM_PATH"):
        return os.environ["CHROMIUM_PATH"]
    pattern = "~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell"
    found = sorted(glob.glob(os.path.expanduser(pattern)))
    return found[-1] if found else None


@pytest.fixture
def server(dataset_dir: Path, tmp_path: Path):
    """Viewer on the synthetic dataset with one episode-level and one dataset-level issue."""
    delete_frames(dataset_dir, episode=2, frame_indices=[10, 11])
    ds = load_dataset(str(dataset_dir))
    ctx = CheckContext("synthetic", ds.revision, ds.fps, ds.info)
    rows = run_checks(connect(ds), ctx, ALL_CHECKS, shard="all").to_pylist()
    rows.append(
        {**rows[0], "episode_index": DATASET_LEVEL, "frame_start": None, "frame_end": None,
         "check_name": "metadata", "severity": "warning", "detail": "test dataset-level row"}
    )  # fmt: skip
    labels = tmp_path / "labels.jsonl"
    app = create_app(ds, to_table(rows), labels_path=labels)

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not srv.started and time.time() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", labels
    srv.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def page():
    exe = find_chromium()
    if exe is None:
        pytest.skip("no Chromium found; set CHROMIUM_PATH or see docs/dev-setup.md")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe)
        pg = browser.new_page(viewport={"width": 1300, "height": 900})
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        yield pg
        browser.close()


def title(page) -> str:
    return page.evaluate("() => document.getElementById('ep-title').textContent")


def visible(page, element_id: str) -> bool:
    return page.evaluate(f"() => document.getElementById('{element_id}').offsetParent !== null")


def test_list_opens_the_worst_episode_with_its_issue(server, page):
    url, _ = server
    page.goto(url)
    page.wait_for_function("document.getElementById('ep-title').textContent.startsWith('Episode')")
    items = page.evaluate(
        "() => [...document.querySelectorAll('#episode-list li')].map(li => li.dataset.ep)"
    )
    assert items[:2] == ["dataset", "2"]  # fixed Dataset entry, then worst episode first
    assert title(page) == "Episode 2"
    assert "frames 10–11" in page.inner_text("#issues")
    assert page.errors == []


def test_dataset_view_hides_media_and_lists_dataset_level_issues(server, page):
    url, _ = server
    page.goto(url + "/#dataset")
    page.wait_for_function(
        "document.getElementById('ep-title').textContent === 'Dataset-level issues'"
    )
    assert "test dataset-level row" in page.inner_text("#issues")
    assert not any(visible(page, i) for i in ["videos", "controls", "timeline", "charts"])
    page.keyboard.press("j")
    page.wait_for_function("document.getElementById('ep-title').textContent.startsWith('Episode')")
    assert all(visible(page, i) for i in ["controls", "timeline", "charts"])
    assert page.errors == []


def test_label_buttons_write_jsonl_and_survive_a_reload(server, page):
    url, labels = server
    page.goto(url + "/#ep=2")
    page.wait_for_selector("#issues .label-btn")
    page.click("#issues li >> nth=0 >> .label-btn[data-label=real]")
    # Wait for the first POST to land so the two appends cannot race.
    page.wait_for_function(
        "document.querySelector('#issues .label-btn.on')?.dataset.label === 'real'"
    )
    page.click("#issues li >> nth=0 >> .label-btn[data-label=false_positive]")
    page.wait_for_function(
        "document.querySelector('#issues .label-btn.on')?.dataset.label === 'false_positive'"
    )
    assert page.evaluate("() => document.getElementById('frame-label').textContent").startswith(
        "frame 0 "
    )

    page.reload()
    page.wait_for_selector("#issues .label-btn.on")
    on = page.evaluate(
        "() => [...document.querySelectorAll('#issues .label-btn.on')].map(b => b.dataset.label)"
    )
    assert on == ["false_positive"]
    lines = [json.loads(x) for x in labels.read_text().splitlines()]
    assert [x["label"] for x in lines] == ["real", "false_positive"]
    assert page.errors == []
