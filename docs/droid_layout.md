# DROID layout notes (`lerobot/droid_1.0.1`)

Facts checked against the Hub on 2026-10-03, revision `0eabc778`. Keep adding to
this as you explore: every check depends on knowing what the data really looks like.

## Basics (`meta/info.json`)

- `codebase_version`: `v3.0`, `robot_type`: Franka, `fps`: 15
- 95,658 episodes, 27,630,375 frames, 49,630 tasks
- `data_path`: `data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet`, roughly 1,000 episodes per file (~100 MB)

## Files that matter (no videos)

| File | Size | Notes |
|---|---|---|
| `meta/episodes/chunk-000/file-000..006.parquet` | ~87 MB each | 311 columns, mostly per-episode `stats/<feature>/<stat>`; file-000 covers episodes 0–14152 |
| `meta/tasks.parquet` | 1.5 MB | `task_index` + task text in `__index_level_0__` (pandas index) |
| `meta/stats.json` | 45 KB | dataset-wide stats |

## Episode metadata columns (non-stats)

`episode_index`, `tasks` (VARCHAR[]), `length`, `data/chunk_index`, `data/file_index`,
`dataset_from_index`, `dataset_to_index` (half-open global `index` range),
`videos/<camera>/{chunk_index,file_index,from_timestamp,to_timestamp}`,
`meta/episodes/{chunk_index,file_index}`.

Per-episode stats: `stats/<feature>/{min,max,mean,std,count,q01,q10,q50,q90,q99}`.

## Frame columns (data files)

- Indexing: `episode_index`, `frame_index`, `index` (global), `task_index` (all int64), `timestamp` (**float32**)
- `action` float32[8], `observation.state` float32[8]
- Decomposed: `action.{joint_position[7], joint_velocity[7], cartesian_position[6], cartesian_velocity[6], gripper_position, gripper_velocity, original[7]}`,
  `observation.state.{joint_position[7], cartesian_position[6], gripper_position}`
- Episode-level, repeated on every frame: `is_episode_successful`, `building`, `collector_id`, `date`, `task_category`,
  `language_instruction{,_2,_3}`
- RLDS leftovers: `is_first`, `is_last`, `is_terminal`, `reward`, `discount`, `camera_extrinsics.*`

Columns with `.` must be double-quoted in SQL: `"observation.state"`.

## Videos

- AV1, 320×180, 15 fps, 3 cameras: `wrist_left`, `exterior_1_left`, `exterior_2_left`
- Each mp4 is ~504 MB and holds many episodes back to back; `moov` is at the front (faststart)
- An episode's segment: `"videos/<camera>/from_timestamp"` .. `to_timestamp` in `episodes`
  (e.g. episode 30: 577.53 s – 584.27 s = 101 frames / 15 fps)
- The Hub serves them with HTTP range requests (`206`, `access-control-allow-origin: *`)

## Findings so far (episodes 0–999)

- **`date` is a copy of `collector_id`** in 1000 / 1000 episodes (e.g. both `84bd5053`):
  the real recording date is lost in this conversion. → candidate metadata check.
- **209 / 1000 episodes (20.9%) have an empty task** (`tasks[1] = ''`).
  → candidate check; matters for language-conditioned policies.
- `features.<key>.names` for `action` / `observation.state` is `{"axes": [joint_0 … joint_6, gripper]}`.

## Open questions (for you to answer with SQL)

- What does the distribution of `timestamp` deltas look like? Is it exactly 1/15?
- Are `building` / `collector_id` constant within an episode? (Useful for per-site analysis.)
- Is the empty-task rate different across `building`s or between successful and failed episodes?
- How do `action` (8 dims) and the decomposed `action.*` columns relate?
- First 50 episodes: `frame_index` check finds 0 issues (14,357 frames = sum of `length`).
