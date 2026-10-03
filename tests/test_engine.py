import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from robot_data_check.cli.main import app
from robot_data_check.engine.loader import EpisodeRange, load_dataset
from robot_data_check.engine.results import RESULTS_SCHEMA
from robot_data_check.engine.views import connect
from tests.fault_injection.faults import delete_frames
from tests.synthetic import EPISODE_LENGTHS


@pytest.mark.parametrize("spec, expected", [("0-200", (0, 200)), ("17", (17, 18)), ("3-4", (3, 4))])
def test_episode_range_parse(spec, expected):
    r = EpisodeRange.parse(spec)
    assert (r.start, r.stop) == expected


@pytest.mark.parametrize("spec", ["5-5", "9-3", "-1", "x"])
def test_episode_range_rejects_bad_specs(spec):
    with pytest.raises(ValueError):
        EpisodeRange.parse(spec)


def test_views_are_filtered_to_the_episode_range(dataset_dir):
    con = connect(load_dataset(str(dataset_dir), episodes=EpisodeRange(1, 3)))
    assert con.execute("SELECT DISTINCT episode_index FROM frames ORDER BY 1").fetchall() == [
        (1,),
        (2,),
    ]
    assert con.execute("SELECT count(*) FROM frames").fetchone()[0] == sum(EPISODE_LENGTHS[1:3])
    assert con.execute("SELECT count(*) FROM episodes").fetchone()[0] == 2
    assert con.execute("SELECT task FROM tasks").fetchall() == [("pick up the cube",)]


def test_rejects_unsupported_codebase_version(dataset_dir):
    info = dataset_dir / "meta/info.json"
    info.write_text(info.read_text().replace("v3.0", "v2.1"))
    with pytest.raises(ValueError, match="v2.1"):
        load_dataset(str(dataset_dir))


def test_cli_writes_results_with_the_stable_schema(dataset_dir, tmp_path):
    delete_frames(dataset_dir, episode=2, frame_indices=[5])
    out = tmp_path / "report"

    res = CliRunner().invoke(app, ["check", str(dataset_dir), "--out", str(out)])
    assert res.exit_code == 0, res.output

    table = pq.read_table(out / "results.parquet")
    assert table.schema.equals(RESULTS_SCHEMA)
    row = table.to_pylist()[0]
    assert (row["episode_index"], row["frame_start"], row["frame_end"]) == (2, 5, 5)
    assert row["check_name"] == "frame_index"
    assert row["shard"] == "all"
    summary = (out / "summary.md").read_text()
    assert "Episodes scanned: 5" in summary
    assert "Episodes with ≥1 error: 1" in summary
