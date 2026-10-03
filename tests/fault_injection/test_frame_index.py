"""Template for every check's tests: clean data -> no issues; one fault -> exactly that issue."""

from robot_data_check.engine.checks import frame_index
from tests.fault_injection.faults import delete_frames, duplicate_frame


def test_clean_dataset_has_no_issues(run_check):
    assert run_check(frame_index) == []


def test_deleted_frames_in_the_middle_are_missing_one_issue_per_gap(dataset_dir, run_check):
    delete_frames(dataset_dir, episode=2, frame_indices=[10, 11, 30])

    issues = run_check(frame_index)
    assert [(i.episode_index, i.value, i.frame_start, i.frame_end) for i in issues] == [
        (2, 2, 10, 11),
        (2, 1, 30, 30),
    ]
    assert all(i.severity == "error" and "missing" in i.detail for i in issues)


def test_deleted_first_frame_is_a_bad_start(dataset_dir, run_check):
    delete_frames(dataset_dir, episode=1, frame_indices=[0])

    [issue] = run_check(frame_index)
    assert (issue.episode_index, issue.value, issue.frame_start, issue.frame_end) == (1, 1, 0, 0)
    assert "starts at 1" in issue.detail


def test_duplicated_frame_is_detected(dataset_dir, run_check):
    duplicate_frame(dataset_dir, episode=4, frame_index=7)

    [issue] = run_check(frame_index)
    assert (issue.episode_index, issue.value, issue.frame_start, issue.frame_end) == (4, 1, 7, 7)
    assert "duplicated" in issue.detail
