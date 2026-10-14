import json

import pytest
from fastapi.testclient import TestClient

from robot_data_check.engine.checks import ALL_CHECKS
from robot_data_check.engine.loader import load_dataset
from robot_data_check.engine.registry import CheckContext, run_checks
from robot_data_check.engine.results import DATASET_LEVEL, to_table
from robot_data_check.engine.views import connect
from robot_data_check.viewer.server import create_app
from tests.fault_injection.faults import delete_frames
from tests.synthetic import CAMERA, EPISODE_LENGTHS, FPS, VIDEO_FILE


@pytest.fixture
def client(dataset_dir):
    delete_frames(dataset_dir, episode=3, frame_indices=[20, 21])
    ds = load_dataset(str(dataset_dir))
    ctx = CheckContext(dataset="synthetic", revision=ds.revision, fps=ds.fps, info=ds.info)
    results = run_checks(connect(ds), ctx, ALL_CHECKS, shard="all")
    return TestClient(create_app(ds, results))


def test_meta(client):
    meta = client.get("/api/meta").json()
    assert meta["fps"] == FPS
    assert meta["cameras"] == [CAMERA]
    assert meta["checks"] == ["frame_index"]
    assert set(meta["series"]) == {"action", "observation.state"}


def test_episode_list_puts_worst_first_and_filters(client):
    eps = client.get("/api/episodes").json()
    assert [e["episode_index"] for e in eps] == [3, 0, 1, 2, 4]
    assert (eps[0]["errors"], eps[0]["checks"], eps[0]["task"]) == (
        1,
        ["frame_index"],
        "pick up the cube",
    )

    only = client.get("/api/episodes", params={"check": "frame_index", "severity": "error"}).json()
    assert [e["episode_index"] for e in only] == [3]
    assert client.get("/api/episodes", params={"severity": "bogus"}).status_code == 422


def test_episode_detail_has_located_issues_and_video_segment(client):
    ep = client.get("/api/episodes/3").json()
    [issue] = ep["issues"]
    assert (issue["frame_start"], issue["frame_end"]) == (20, 21)
    [video] = ep["videos"]
    start = sum(EPISODE_LENGTHS[:3])
    assert video["url"] == f"/videos/{VIDEO_FILE}"
    assert video["from_ts"] == pytest.approx(start / FPS)
    assert video["to_ts"] == pytest.approx((start + EPISODE_LENGTHS[3]) / FPS)
    assert client.get("/api/episodes/99").status_code == 404


def test_series_are_transposed_per_dimension(client):
    s = client.get("/api/episodes/0/series").json()
    assert s["frame_index"] == list(range(EPISODE_LENGTHS[0]))
    assert len(s["series"]["action"]) == 8
    assert len(s["series"]["action"][0]) == EPISODE_LENGTHS[0]


def test_local_videos_support_range_requests_and_stay_inside_videos_dir(client):
    r = client.get(f"/videos/{VIDEO_FILE}", headers={"Range": "bytes=100-199"})
    assert r.status_code == 206
    assert r.content == (bytes(range(256)) * 64)[100:200]
    assert client.get("/videos/meta/info.json").status_code == 404
    assert client.get("/videos/videos/../meta/info.json").status_code == 404


def test_static_page_is_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Episode Viewer" in r.text


@pytest.fixture
def client_with_dataset_issue(dataset_dir):
    ds = load_dataset(str(dataset_dir))
    ctx = CheckContext(dataset="synthetic", revision=ds.revision, fps=ds.fps, info=ds.info)
    rows = run_checks(connect(ds), ctx, ALL_CHECKS, shard="all").to_pylist()
    rows.append({**DATASET_ROW, "dataset_revision": ds.revision})
    return TestClient(create_app(ds, to_table(rows)))


DATASET_ROW = {
    "dataset": "synthetic",
    "shard": "all",
    "episode_index": DATASET_LEVEL,
    "frame_start": None,
    "frame_end": None,
    "check_name": "metadata",
    "check_version": "1",
    "severity": "warning",
    "value": 1.0,
    "detail": "columns a and b are identical in every episode",
}


def test_dataset_level_issues_have_their_own_endpoint_and_stay_out_of_the_episode_list(
    client_with_dataset_issue,
):
    c = client_with_dataset_issue
    assert c.get("/api/meta").json()["dataset_issues"] == {"errors": 0, "warnings": 1}
    [issue] = c.get("/api/dataset").json()["issues"]
    assert issue["check_name"] == "metadata" and issue["frame_start"] is None
    eps = c.get("/api/episodes").json()
    assert DATASET_LEVEL not in [e["episode_index"] for e in eps]
    assert all(e["warnings"] == 0 for e in eps)


@pytest.fixture
def labelling(dataset_dir, tmp_path):
    delete_frames(dataset_dir, episode=3, frame_indices=[20, 21])
    ds = load_dataset(str(dataset_dir))
    ctx = CheckContext(dataset="synthetic", revision=ds.revision, fps=ds.fps, info=ds.info)
    results = run_checks(connect(ds), ctx, ALL_CHECKS, shard="all")
    path = tmp_path / "report" / "labels.jsonl"
    return TestClient(create_app(ds, results, labels_path=path)), path


def test_labels_are_appended_and_the_latest_one_is_shown(labelling):
    client, path = labelling
    issue = {"episode_index": 3, "check_name": "frame_index", "frame_start": 20, "frame_end": 21}
    assert client.get("/api/meta").json()["labels_enabled"] is True
    assert client.get("/api/episodes/3").json()["issues"][0]["label"] is None

    assert client.post("/api/labels", json={**issue, "label": "real"}).status_code == 200
    assert client.post("/api/labels", json={**issue, "label": "false_positive"}).status_code == 200

    assert client.get("/api/episodes/3").json()["issues"][0]["label"] == "false_positive"
    lines = [json.loads(x) for x in path.read_text().splitlines()]
    assert [x["label"] for x in lines] == ["real", "false_positive"]  # full history kept
    assert {"dataset_revision", "labelled_at"} <= set(lines[0])


def test_invalid_labels_are_rejected_and_labelling_can_be_disabled(labelling, client):
    labelled, _ = labelling
    bad = {"episode_index": 3, "check_name": "frame_index", "label": "maybe"}
    assert labelled.post("/api/labels", json=bad).status_code == 422
    ok = {**bad, "label": "real"}
    assert client.post("/api/labels", json=ok).status_code == 409
    assert client.get("/api/meta").json()["labels_enabled"] is False


def test_labels_from_another_revision_are_ignored(tmp_path):
    from robot_data_check.viewer.labels import LabelStore

    path = tmp_path / "labels.jsonl"
    LabelStore(path, "d", "rev1").add(1, "frame_index", 5, 5, "real")
    assert LabelStore(path, "d", "rev2").latest() == {}
    assert LabelStore(path, "d", "rev1").latest() == {(1, "frame_index", 5, 5): "real"}
