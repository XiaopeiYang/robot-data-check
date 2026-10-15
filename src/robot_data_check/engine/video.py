"""Decode the camera frames of one episode, locally or straight from the Hub.

A LeRobot v3 video file holds many episodes back to back; an episode's segment is given
by ``"videos/<camera>/from_timestamp"`` / ``to_timestamp`` in the ``episodes`` view. For Hub
datasets the file is read with HTTP range requests (``RangeFile``), so decoding one
episode fetches a few MB instead of the whole file. PyAV's bundled FFmpeg has no HTTPS
support, which is why the reading happens in Python.

Requires the optional ``video`` dependencies (``av``, ``numpy``).
"""

from __future__ import annotations

import io
import urllib.request
from collections import OrderedDict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import duckdb

from .loader import LoadedDataset

Fetch = Callable[[int, int], bytes]  # inclusive byte range -> bytes


def http_fetcher(url: str, timeout: float = 60) -> tuple[Fetch, int]:
    """A range fetcher for ``url`` (redirects resolved once) and the file size."""
    final = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=timeout).url
    head = urllib.request.urlopen(
        urllib.request.Request(final, headers={"Range": "bytes=0-0"}), timeout=timeout
    )
    size = int(head.headers["Content-Range"].rsplit("/", 1)[1])

    def fetch(a: int, b: int) -> bytes:
        req = urllib.request.Request(final, headers={"Range": f"bytes={a}-{b}"})
        return urllib.request.urlopen(req, timeout=timeout).read()

    return fetch, size


class RangeFile(io.RawIOBase):
    """Seekable read-only file over a range fetcher, with an LRU cache of fixed blocks."""

    def __init__(self, fetch: Fetch, size: int, block: int = 1 << 20, max_blocks: int = 64):
        self._fetch, self.size, self._block, self._max = fetch, size, block, max_blocks
        self._pos = 0
        self._cache: OrderedDict[int, bytes] = OrderedDict()
        self.bytes_fetched = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._pos, io.SEEK_END: self.size}[whence]
        self._pos = max(0, base + offset)
        return self._pos

    def _get(self, i: int) -> bytes:
        if i in self._cache:
            self._cache.move_to_end(i)
            return self._cache[i]
        a = i * self._block
        data = self._fetch(a, min(a + self._block, self.size) - 1)
        self.bytes_fetched += len(data)
        self._cache[i] = data
        if len(self._cache) > self._max:
            self._cache.popitem(last=False)
        return data

    def readinto(self, buf) -> int:
        if self._pos >= self.size:
            return 0
        i, off = divmod(self._pos, self._block)
        chunk = self._get(i)[off : off + len(buf)]
        buf[: len(chunk)] = chunk
        self._pos += len(chunk)
        return len(chunk)


@dataclass(frozen=True)
class Segment:
    rel_path: str
    from_ts: float
    to_ts: float
    length: int


def episode_segment(
    ds: LoadedDataset, con: duckdb.DuckDBPyConnection, camera: str, episode_index: int
) -> Segment:
    c = f"videos/{camera}"
    row = con.execute(
        f'SELECT "{c}/chunk_index", "{c}/file_index", "{c}/from_timestamp", '
        f'"{c}/to_timestamp", length FROM episodes WHERE episode_index = ?',
        [episode_index],
    ).fetchone()
    if row is None:
        raise KeyError(f"episode {episode_index} not loaded")
    chunk, file, t0, t1, length = row
    return Segment(ds.video_path(camera, chunk, file), float(t0), float(t1), int(length))


class _KeepOpen(io.RawIOBase):
    """Proxy that ignores close(): PyAV closes the file object it was given, which would
    break reusing one ``RangeFile`` (and its cache) across episodes."""

    def __init__(self, f: BinaryIO):
        self._f = f
        f.seek(0)  # a reused file may be anywhere; the container must start at the header

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def readinto(self, buf) -> int:
        data = self._f.read(len(buf))
        buf[: len(data)] = data
        return len(data)

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        return self._f.seek(offset, whence)

    def tell(self) -> int:
        return self._f.tell()


def open_video(ds: LoadedDataset, rel_path: str) -> BinaryIO:
    if ds.local_root is not None:
        return open(Path(ds.local_root) / rel_path, "rb")
    fetch, size = http_fetcher(ds.remote_url(rel_path))
    return io.BufferedReader(RangeFile(fetch, size), buffer_size=1 << 16)


def iter_episode_frames(
    ds: LoadedDataset,
    con: duckdb.DuckDBPyConnection,
    camera: str,
    episode_index: int,
    fileobj: BinaryIO | None = None,
) -> Iterator[tuple[int, object]]:
    """Yield ``(frame_index, gray uint8 ndarray)`` for every frame of the episode.

    Frames are mapped to ``frame_index = round((pts - from_timestamp) * fps)`` and only
    ``0 <= frame_index < length`` is yielded. Pass ``fileobj`` to reuse an open file (e.g.
    a ``RangeFile`` shared across episodes of the same video file).
    """
    import av

    seg = episode_segment(ds, con, camera, episode_index)
    f = _KeepOpen(fileobj) if fileobj is not None else open_video(ds, seg.rel_path)
    try:
        with av.open(f) as container:
            stream = container.streams.video[0]
            container.seek(int(seg.from_ts / stream.time_base), stream=stream, backward=True)
            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                fi = round((float(frame.pts * stream.time_base) - seg.from_ts) * ds.fps)
                if fi < 0:
                    continue
                if fi >= seg.length:
                    break
                yield fi, frame.to_ndarray(format="gray")
    finally:
        if fileobj is None:
            f.close()
