# Findings: `lerobot/droid_1.0.1`

All queries run against the `frames` / `episodes` views (`robot_data_check.engine.views.connect`)
on revision `0eabc778` (`0eabc778f959c54b8c5aa3626cc1128d2d2e54d4`), episodes 0–999
(1,000 episodes, 301,366 frames), unless stated otherwise.

Conversion script referenced below: `huggingface/lerobot`
`examples/port_datasets/port_droid.py` at `df0763a2` (last change to that file,
2026-04-12). The dataset revision is dated 2026-06-25, so it was probably produced with
this version of the script; that is not proven.

### Source data checked (2026-10-14)

The public RLDS release `gs://gresearch/robotics/droid/1.0.1` (2048 shards, the shard
count `port_droid.py` expects) was inspected without downloading it:

- `features.json` (`https://storage.googleapis.com/gresearch/robotics/droid/1.0.1/features.json`):
  `episode_metadata` has exactly two fields, `file_path` and `recording_folderpath`.
- The first record of shard `droid_101-train.tfrecord-00000-of-02048`, read with an HTTP
  range request (8-byte length header, then a 14,456,631-byte `tf.train.Example`), has
  the same two `episode_metadata/*` keys and nothing else, e.g.
  `file_path = gs://xembodiment_data/r2d2/r2d2-data-full/BVL/success/2024-02-02/Fri_Feb__2_19:55:01_2024/trajectory.h5`.

So **this release has no `building`, `collector_id`, `date` or `task_category` fields**.
Building, success / failure and the real recording date are only encoded in the path
(`.../<building>/<success|failure>/<YYYY-MM-DD>/...`). Since `port_droid.py` reads
`m["building"]`, `m["collector_id"]` and `m["date"]`, the LeRobot port must have been
built from a different source that carries these fields (a modified TFDS builder or the
`droid_raw` metadata); which one is not yet known.

| Finding | Status |
|---|---|
| [`task_category` equals `building`](#task_category-equals-building) | unconfirmed |
| [`date` equals `collector_id`](#date-equals-collector_id) | unconfirmed |
| [Empty task on failed episodes](#empty-task-on-failed-episodes) | by design (inferred from labels; docs not yet confirmed) |
| [Timestamps are synthesised](#timestamps-are-synthesised) | by design |
| [Very short episodes are all failures](#very-short-episodes-are-all-failures) | by design |
| [No all-zero action episodes](#no-all-zero-action-episodes) | no issue found |

---

### `task_category` equals `building`

- **Status:** unconfirmed (filled from `building` in code; the column has no counterpart in the public source)
- **Observed:** 1000 / 1000 episodes have `task_category = building` (58 distinct buildings).
- **Query:**
  ```sql
  SELECT count(DISTINCT episode_index) AS eps,
         count(DISTINCT episode_index) FILTER (task_category = building) AS same
  FROM frames;
  ```
- **Evidence:** `port_droid.py:253` sets `"task_category": m["building"]`. The public
  RLDS release has no task-category field at all (see "Source data checked"), so the
  column looks like a placeholder rather than a mis-mapped source field.
- **Meaning for users:** `task_category` carries no task information; do not use it to
  group by task.
- **Next step:** confirm that the source LeRobot actually used also lacks a task
  category. If so, this is a misleading placeholder; the fix to propose is dropping or
  documenting the column (phrased as a question to the maintainers, not a bug report).

### `date` equals `collector_id`

- **Status:** unconfirmed (cause not located)
- **Observed:** 1000 / 1000 episodes have `date = collector_id` (e.g. both `84bd5053`);
  68 distinct values each.
- **Query:**
  ```sql
  SELECT count(DISTINCT episode_index) AS eps,
         count(DISTINCT episode_index) FILTER (date = collector_id) AS same
  FROM frames;
  ```
- **Evidence:** `port_droid.py:256` maps `"date": m["date"]`, which looks correct. The
  public RLDS release has no `date` field, but its `file_path` carries the real date
  (`.../BVL/success/2024-02-02/...`). So the value went wrong in the conversion chain
  (the intermediate source with `building` / `collector_id` / `date`, or the step that
  produced it), not in the public RLDS data. The LeRobot dataset does not keep
  `file_path`, so the date cannot be recovered from the published dataset itself.
- **Meaning for users:** the recording date is not available from this column.
- **Next step:** find the source LeRobot used (`droid_raw` metadata, history and issues
  of `port_droid.py`), then compare its `date` with the date in `file_path` for a sample of
  episodes. Only then can the status become **defect**, with the failing step located.

### Empty task on failed episodes

- **Status:** by design (inferred; see evidence)
- **Observed:** 209 / 1000 episodes (20.9%) have an empty task. Cross-tab:

  | `is_episode_successful` | episodes | empty task |
  |---|---|---|
  | false | 164 | 163 (99.4%) |
  | true | 836 | 46 (5.5%) |

- **Query:**
  ```sql
  WITH ep AS (
    SELECT e.episode_index, coalesce(e.tasks[1], '') = '' AS empty_task, a.ok
    FROM episodes e JOIN (
      SELECT episode_index, any_value(is_episode_successful) AS ok FROM frames GROUP BY 1
    ) a USING (episode_index))
  SELECT ok, count(*), count(*) FILTER (empty_task) FROM ep GROUP BY 1;
  ```
- **Evidence:** the pattern is almost entirely explained by the success label. No episode
  has an empty task while `language_instruction` is set, so conversion lost nothing; the
  gap is in the source annotations. DROID's dataset page
  (droid-dataset.github.io/droid/the-droid-dataset.html) does not state which episodes
  are annotated, so "failures are not annotated" is **inferred from the data, not yet
  confirmed by documentation**. A Hub discussion points to the official annotation set
  `KarlP/droid` (Dec 2024) as the place to confirm.
- **Meaning for users:** failed episodes have (almost) no language annotation, and about
  5% of successful ones lack it too; filter or handle them when training
  language-conditioned policies.
- **Next step:** confirm against `KarlP/droid` annotation coverage before stating it as
  documented behaviour.

### Timestamps are synthesised

- **Status:** by design (consequence of conversion)
- **Observed:** over 300,366 consecutive-frame pairs, every `timestamp` delta is 1/15 s
  (min 0.0666657, max 0.0666733); max `|timestamp - frame_index / 15|` is 3.6e-6
  (float32 rounding).
- **Query:**
  ```sql
  WITH d AS (
    SELECT timestamp - LAG(timestamp) OVER (PARTITION BY episode_index ORDER BY frame_index) AS dt,
           timestamp, frame_index
    FROM frames)
  SELECT min(dt), max(dt), max(abs(timestamp - frame_index / 15.0)) FROM d WHERE dt IS NOT NULL;
  ```
- **Meaning for users:** timestamps carry no information about real recording timing.
  For this project: timing checks cannot find anything on DROID; they need a directly
  recorded dataset.

### Very short episodes are all failures

- **Status:** by design
- **Observed:** episode length ranges 6–1563 frames (median 233). All 6 episodes shorter
  than 2 s (< 30 frames) are failed episodes; the shortest successful one has 63 frames.
- **Query:**
  ```sql
  SELECT ok, count(*) FILTER (length < 30), min(length)
  FROM (SELECT e.episode_index, e.length, any_value(f.is_episode_successful) AS ok
        FROM episodes e JOIN frames f USING (episode_index) GROUP BY 1, 2)
  GROUP BY 1;
  ```
- **Meaning for users:** very short episodes are aborted attempts; filtering on success
  removes them.

### No all-zero action episodes

- **Status:** no issue found
- **Observed:** 0 / 1000 episodes have an `action` that is zero in every dimension for
  every frame.
- **Query:**
  ```sql
  WITH e AS (
    SELECT episode_index,
           max(list_reduce(list_transform(action, x -> abs(x)), (a, b) -> greatest(a, b))) AS m
    FROM frames GROUP BY 1)
  SELECT count(*) FILTER (m = 0) FROM e;
  ```
