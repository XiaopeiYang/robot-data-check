# Findings: the LeRobot format itself

Findings that hold for every dataset written by LeRobot, not for one dataset.

| Finding | Status |
|---|---|
| [`timestamp` is always `frame_index / fps`](#timestamp-is-always-frame_index--fps) | by design |

---

### `timestamp` is always `frame_index / fps`

- **Status:** by design
- **Observed (2026-10-14):** in every dataset checked, consecutive-frame `timestamp`
  deltas are exactly `1 / fps` and `max |timestamp - frame_index / fps|` is below 2e-6
  (float32 rounding). Episodes 0–199 of each (fewer where the dataset is smaller):

  | Dataset | Revision | Episodes | Frame pairs | fps | max \|ts − idx/fps\| |
  |---|---|---|---|---|---|
  | `lerobot/svla_so100_sorting` | `13870ca9` | 52 | 35,661 | 30 | 8.9e-07 |
  | `lerobot/svla_so100_pickplace` | `728583b5` | 50 | 19,581 | 30 | 8.9e-07 |
  | `hungho77/so101-ai20k-multitask` | `7634de51` | 200 | 66,305 | 30 | 8.9e-07 |
  | `witsense-ai/so101_longhorizon_dataset` | `3c73d627` | 200 | 90,021 | 30 | 1.8e-06 |
  | `Artefacts/shape-sorting-so101-30fps` | `3738b5e6` | 200 | 36,911 | 30 | 8.9e-07 |
  | `IlyaGusev/so101_pick_gum` | `82136b23` | 155 | 26,992 | 20 | 7.6e-07 |
  | `zmfldlwx/community-v1-so101-pick_and_place-converted` | `865e15ec` | 199 | 76,907 | 30 | 8.9e-07 |
  | `lerobot/droid_1.0.1` (converted from RLDS) | `0eabc778` | 1000 | 300,366 | 15 | 3.6e-06 |

- **Query** (per dataset):
  ```sql
  WITH d AS (
    SELECT timestamp, frame_index,
           timestamp - LAG(timestamp) OVER (PARTITION BY episode_index ORDER BY frame_index) AS dt
    FROM frames)
  SELECT median(dt), min(dt), max(dt), max(abs(timestamp - frame_index / <fps>))
  FROM d WHERE dt IS NOT NULL;
  ```
- **Evidence:** `huggingface/lerobot` `src/lerobot/datasets/dataset_writer.py:225` at
  `ca69a206` (2026-10-07), in `add_frame`: `timestamp = frame_index / self._meta.fps`.
  Its docstring says callers "must not provide `timestamp` or `frame_index`; those are
  computed automatically."
- **Meaning for users:** `timestamp` carries no information about real recording timing.
  If the control loop stalled or a camera delivered late frames during recording, the
  dataset still shows a perfect `1 / fps` cadence.
- **Meaning for this project:**
  - A timestamp-based check can only catch files not produced by the standard writer
    (custom converters, manual edits). How to handle the planned `timestamps` check is
    an open decision for the user.
  - Real recording problems leave indirect traces only: repeated or frozen camera frames
    in the video, and state changes too large for one `1 / fps` step. See
    [research/frozen_frames.md](../research/frozen_frames.md) once written.
