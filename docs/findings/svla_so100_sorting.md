# Findings: `lerobot/svla_so100_sorting`

Revision `13870ca9` (`13870ca969084d8ce4d8a0391b06cead78e804ba`), all 52 episodes, unless
stated otherwise. Layout notes: [../svla_so100_sorting_layout.md](../svla_so100_sorting_layout.md).

| Finding | Status |
|---|---|
| [About 1 in 6 camera frames repeats the previous frame](#about-1-in-6-camera-frames-repeats-the-previous-frame) | unconfirmed |

---

### About 1 in 6 camera frames repeats the previous frame

- **Status:** unconfirmed (pattern measured and verified pixel by pixel; cause not located)
- **Observed:** decoded consecutive frames that are identical:

  | Camera | Identical pairs | Share | Per-episode share (min / median / max) | Most common gap between repeats |
  |---|---|---|---|---|
  | `top` | 5,818 / 35,661 | 16.3% | 15.5 / 16.3 / 17.0% | 6 frames (87.9% of gaps) |
  | `wrist` | 6,064 / 35,661 | 17.0% | 15.6 / 16.5 / 21.1% | 6 frames (82.6% of gaps) |

  Repeats are isolated (never two in a row) and happen while the arm moves, e.g. episode 0,
  `top`, frames 53, 59, 65, 71 repeat their predecessor while the largest joint change in
  that step is 0.97–2.9 (dataset median 0.88). The two cameras repeat independently: both
  repeat at the same frame only 2,570 times.
- **How it was measured:** `tools/research/frozen_frames.py` (mean absolute grayscale
  difference of consecutive decoded frames, 4× downsampled); data in
  [../research/frozen_frames_pairs.parquet](../research/frozen_frames_pairs.parquet).
  Re-checked at full resolution for episode 0, frames 1–80: every flagged pair is
  identical in all 640×480 pixels (`top`: frames 1, 7, 13, 23, 29, …; `wrist`: 3, 9, 15,
  21, 27, …); the smallest non-zero difference among the others is 0.024.
- **Query** (on the pairs table):
  ```sql
  SELECT camera, count(*) FILTER (img_diff = 0) AS repeats, count(*) AS pairs
  FROM 'docs/research/frozen_frames_pairs.parquet'
  WHERE dataset = 'lerobot/svla_so100_sorting' GROUP BY camera;
  ```
- **Evidence and interpretation:** a repeat every 6th frame at 30 fps is 5 repeats per
  second, which is what a camera delivering about 25 fps into a 30 fps recording loop
  would produce. Independent repeats in the two cameras point at the cameras rather than a
  stalled control loop (a stall would repeat both at once). An encoder cannot explain it:
  the scene is moving, yet whole frames are identical.
- **Meaning for users:** in about one step out of six, the image is one frame (33 ms)
  older than the state and action recorded with it. For policies trained on image +
  state this is a small, systematic misalignment, not a corruption.
- **Next step:** confirm the cause: the cameras' actual frame rate (camera config in the
  dataset card or recording script, or measure on the raw recording if available), and how
  LeRobot's camera reader behaves when read faster than the camera delivers. Only then can
  this become **by design** (known camera limitation) or **defect**.
