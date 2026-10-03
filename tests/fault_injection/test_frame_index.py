"""Template for every check's tests: clean data -> no issues; one fault -> exactly that issue."""

from robot_data_check.engine.checks import frame_index
from tests.fault_injection.faults import delete_frames, duplicate_frame


def test_clean_dataset_has_no_issues(run_check):
    assert run_check(frame_index) == []


def test_deleted_frames_in_the_middle_are_missing(dataset_dir, run_check):
    delete_frames(dataset_dir, episode=2, frame_indices=[10, 11, 30])

    [issue] = run_check(frame_index)
    assert issue.episode_index == 2
    assert issue.severity == "error"
    assert issue.value == 3
    assert "missing" in issue.detail


def test_deleted_first_frame_is_a_bad_start(dataset_dir, run_check):
    delete_frames(dataset_dir, episode=1, frame_indices=[0])

    [issue] = run_check(frame_index)
    assert (issue.episode_index, issue.value) == (1, 1)
    assert "starts at 1" in issue.detail


def test_duplicated_frame_is_detected(dataset_dir, run_check):
    duplicate_frame(dataset_dir, episode=4, frame_index=7)

    [issue] = run_check(frame_index)
    assert (issue.episode_index, issue.value) == (4, 1)
    assert "duplicated" in issue.detail
