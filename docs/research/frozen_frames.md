# Feasibility study: frozen / repeated camera frames

Question: since LeRobot timestamps cannot show recording stalls
([findings/lerobot_format.md](../findings/lerobot_format.md)), do repeated camera frames
occur in real datasets, can they be told apart from a static scene, and what does
detecting them cost?

Reproduce: `uv run python tools/research/frozen_frames.py report` reads the committed
[frozen_frames_pairs.parquet](frozen_frames_pairs.parquet) (121,608 consecutive frame
pairs); `collect` decodes again (about 6 minutes with 4 workers on the development machine).

## Sample

| Dataset | Revision | Episodes | Cameras | Frames per camera |
|---|---|---|---|---|
| `lerobot/droid_1.0.1` | `0eabc778` | 50, sampled from 0–999 with seed 0 | 3 (320×180, 15 fps) | 16,812 |
| `lerobot/svla_so100_sorting` | `13870ca9` | all 52 | 2 (640×480, 30 fps) | 35,713 |

Metric per pair: mean absolute grayscale difference (0–255) of the two decoded frames,
4× downsampled. Robot motion per step: largest absolute change of any `observation.state`
dimension.

## Answer

**Yes, repeated frames occur, they are clearly separable from static scenes, and in one of
the two datasets they affect about 1 frame in 6.**

| Camera | Pairs | Exactly identical | Median difference |
|---|---|---|---|
| DROID `exterior_1_left` | 16,762 | 0 | 2.07 |
| DROID `exterior_2_left` | 16,762 | 0 | 2.27 |
| DROID `wrist_left` | 16,762 | 235 (1.4%) | 6.53 |
| sorting `top` | 35,661 | 5,818 (16.3%) | 2.15 |
| sorting `wrist` | 35,661 | 6,064 (17.0%) | 3.17 |

- **Exactly identical is the right signal, not "small difference".** A static scene still
  differs slightly from frame to frame (sensor noise survives encoding): DROID's fixed
  exterior cameras never produce an identical pair, their smallest differences are
  0.006–0.007. Relative thresholds such as "below 5% of the camera median" mostly catch static
  scenes (DROID exteriors: ~1,100 pairs each) and are not useful.
- **Robot motion separates repeats from stillness.** DROID's 235 identical wrist pairs
  happen almost only while the arm is still (1 of 235 above the median state change), so
  they are consistent with a static view. In `svla_so100_sorting`, repeats happen
  regardless of motion, periodically (every 6th frame), in every episode: logged as
  **unconfirmed** in [findings/svla_so100_sorting.md](../findings/svla_so100_sorting.md).
- **No long freezes.** In both datasets every run of repeats has length 1; no camera
  stalled for several frames in this sample.

## Cost

| Camera | Median seconds per episode | Frames per episode (median) |
|---|---|---|
| DROID (each of 3 cameras) | 3.1–3.6 | ~250 |
| sorting `top` | 10.6 | ~690 |
| sorting `wrist` | 5.7 | ~690 |

Streaming from the Hub with `engine/video.py` (`RangeFile`), one worker processes about
65–120 frames per second including download and decode (DROID 87–96, sorting `top` 67,
sorting `wrist` 121). Whole datasets are therefore
cheap for small datasets (all of `svla_so100_sorting`, both cameras: about 14 worker-minutes)
and expensive for large ones: DROID has 27.6M frames × 3 cameras, roughly 250
worker-hours. Video checks at that scale are a real reason for the Phase 2 pipeline.

## Recommendation

A repeated-frame check is worth adding to M1:

- it is the only recording-integrity signal that works on LeRobot data;
- it already has a real (unconfirmed) finding on an official dataset;
- the rule is simple (identical consecutive frames, interpreted with robot motion and
  periodicity), so most of the work is the spec: what counts as a repeat, whether to report
  per frame or as a per-episode rate, and how to treat static scenes.

The spec is the user's to write; `engine/video.py` provides decoding for it. Running it on
large datasets should sample episodes until Phase 2 can distribute the work.

## Limitations of this study

- Two datasets only; the DROID sample is 50 of 95,658 episodes.
- AV1 decoding is lossy: two different but very similar source frames could in principle
  decode identically. Mitigated by requiring robot motion and by the periodic pattern, not
  excluded.
- The 4× downsampling was checked against full resolution for one episode only.
