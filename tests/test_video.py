import io
import random

import pytest

av = pytest.importorskip("av")
np = pytest.importorskip("numpy")

from robot_data_check.engine.loader import load_dataset  # noqa: E402
from robot_data_check.engine.video import RangeFile, iter_episode_frames  # noqa: E402
from robot_data_check.engine.views import connect  # noqa: E402
from tests.synthetic import CAMERA, EPISODE_LENGTHS, FPS, VIDEO_FILE  # noqa: E402


def bytes_fetcher(data: bytes):
    return lambda a, b: data[a : b + 1]


def test_range_file_reads_match_the_underlying_bytes():
    data = bytes(random.Random(0).randbytes(10_000))
    f = RangeFile(bytes_fetcher(data), len(data), block=256, max_blocks=4)
    rng = random.Random(1)
    for _ in range(200):
        pos, n = rng.randrange(len(data)), rng.randrange(1, 900)
        f.seek(pos)
        got = b""
        while len(got) < n and (chunk := f.read(min(n - len(got), 300))):
            got += chunk  # reads may stop at block boundaries
        assert got == data[pos : pos + n]
    f.seek(-10, io.SEEK_END)
    assert f.read(100) == data[-10:]
    assert len(f._cache) <= 4  # LRU bound holds


def write_gray_ramp_video(path, n_frames: int, fps: int) -> None:
    """AV1 video whose frame k is uniformly gray with brightness k (so k identifies it)."""
    with av.open(str(path), "w") as out:
        s = out.add_stream("libsvtav1", rate=fps)
        s.width, s.height, s.pix_fmt = 64, 64, "yuv420p"
        for k in range(n_frames):
            img = np.full((64, 64, 3), k, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(img, format="rgb24")
            frame.pts = k
            for pkt in s.encode(frame):
                out.mux(pkt)
        for pkt in s.encode():
            out.mux(pkt)


@pytest.fixture
def video_dataset(dataset_dir):
    write_gray_ramp_video(dataset_dir / VIDEO_FILE, sum(EPISODE_LENGTHS), FPS)
    ds = load_dataset(str(dataset_dir))
    return ds, connect(ds), dataset_dir


@pytest.mark.parametrize("episode", [0, 2, 4])
def test_episode_frames_are_decoded_and_numbered_from_the_segment(video_dataset, episode):
    ds, con, _ = video_dataset
    frames = list(iter_episode_frames(ds, con, CAMERA, episode))
    assert [fi for fi, _ in frames] == list(range(EPISODE_LENGTHS[episode]))
    start = sum(EPISODE_LENGTHS[:episode])  # global index of the episode's first frame
    means = [float(img.mean()) for _, img in frames]
    # Frame k of the file has brightness k; allow for lossy coding error.
    expected = [start + j for j in range(len(frames))]
    assert max(abs(m - e) for m, e in zip(means, expected, strict=True)) < 4


def test_the_range_file_path_decodes_the_same_frames(video_dataset):
    ds, con, root = video_dataset
    data = (root / VIDEO_FILE).read_bytes()
    rf = RangeFile(bytes_fetcher(data), len(data), block=4096)
    shared = io.BufferedReader(rf)
    via_range = [(fi, img.mean()) for fi, img in iter_episode_frames(ds, con, CAMERA, 3, shared)]
    direct = [(fi, img.mean()) for fi, img in iter_episode_frames(ds, con, CAMERA, 3)]
    assert via_range == direct
    # The shared file object stays usable for the next episode.
    assert len(list(iter_episode_frames(ds, con, CAMERA, 4, shared))) == EPISODE_LENGTHS[4]
    assert rf.bytes_fetched <= len(data)
