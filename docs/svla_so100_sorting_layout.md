# Layout notes: `lerobot/svla_so100_sorting`

Second development dataset, chosen 2026-10-15: an official LeRobot dataset recorded with an
SO-100 arm, among the most downloaded SO-100/101 datasets (15.9k downloads at selection).
It gives the behaviour checks data from a different robot, task and recording setup than
DROID. It does **not** help timing checks: like every LeRobot dataset its timestamps are
`frame_index / fps` (see [findings/lerobot_format.md](findings/lerobot_format.md)).

Facts checked on revision `13870ca9` (`13870ca969084d8ce4d8a0391b06cead78e804ba`).

## Basics (`meta/info.json`)

- `codebase_version`: `v3.0`, `robot_type`: `so100`, `fps`: 30
- 52 episodes, 35,713 frames, 1 task:
  "Put the red cube in the right box and the blue cube in the left box."
- Episode length 51–962 frames (median 693.5; 1.7–32.1 s)

## Files

| Path | Files | Size |
|---|---|---|
| `data/` | 1 | 0.9 MB |
| `meta/episodes/` | 1 | 0.1 MB |
| `videos/` | 3 | 830.8 MB |

The whole tabular part is about 1 MB: a full run of `robocheck check` takes well under a
second once downloaded.

## Columns

Frames: `action` float32[6], `observation.state` float32[6], `timestamp`, `frame_index`,
`episode_index`, `index`, `task_index`. Dimension names (a plain list, unlike DROID's
`{"axes": [...]}`): `main_shoulder_pan`, `main_shoulder_lift`, `main_elbow_flex`,
`main_wrist_flex`, `main_wrist_roll`, `main_gripper`.

Episodes: `episode_index`, `tasks`, `length`, `data/{chunk,file}_index`,
`dataset_{from,to}_index`, `videos/<camera>/{chunk_index,file_index,from_timestamp,to_timestamp}`,
`meta/episodes/{chunk,file}_index`, plus per-episode `stats/*`.

## Videos

- 2 cameras: `observation.images.top`, `observation.images.wrist`; AV1, 640×480, 30 fps
- `top` spans two files: episodes 0–45 in `file-000.mp4`, 46–51 in `file-001.mp4`;
  `wrist` is a single file. So the same episode sits at different offsets per camera, e.g.
  episode 51: `top` 109.37–130.47 s in `file-001`, `wrist` 1169.33–1190.43 s in `file-000`.
  The viewer seeks each camera with its own offset.

## Differences from DROID that matter for checks

- No success flag, no site / operator / date columns: nothing to cross-tabulate findings
  against except episode length and position. `verify-finding` step 2 is weaker here.
- 6-dim action / state (5 joints + gripper) instead of 8; 30 fps instead of 15, so
  per-frame deltas are about half as large for the same motion. Thresholds must come from
  each dataset's own distribution.
- Single task: task-text checks have little to say.

## Runs

- `robocheck check lerobot/svla_so100_sorting` (all 52 episodes, checks: `frame_index`):
  0 issues.
- Viewer API smoke test: both cameras resolve for episodes 0 and 51 (including the
  `file-001` case); action / state series have 6 dimensions with the names above.
