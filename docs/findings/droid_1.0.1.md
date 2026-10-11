# Findings: `lerobot/droid_1.0.1`

All queries run against the `frames` / `episodes` views (`robot_data_check.engine.views.connect`)
on revision `0eabc778` (`0eabc778f959c54b8c5aa3626cc1128d2d2e54d4`), episodes 0–999
(1,000 episodes, 301,366 frames), unless stated otherwise.

Conversion script referenced below: `huggingface/lerobot`
`examples/port_datasets/port_droid.py` at `df0763a2` (last change to that file,
2026-04-12). The dataset revision is dated 2026-06-25, so it was probably produced with
this version of the script; that is not proven.

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

- **Status:** unconfirmed (cause located in code; intent unknown)
- **Observed:** 1000 / 1000 episodes have `task_category = building` (58 distinct buildings).
- **Query:**
  ```sql
  SELECT count(DISTINCT episode_index) AS eps,
         count(DISTINCT episode_index) FILTER (task_category = building) AS same
  FROM frames;
  ```
- **Evidence:** `port_droid.py:253` sets `"task_category": m["building"]`.
- **Meaning for users:** `task_category` carries no task information; do not use it to
  group by task.
- **Next step:** check whether DROID's RLDS `episode_metadata` has a task-category
  field at all. If it does, line 253 mis-maps it (defect); if not, it is a placeholder and
  the right fix is to drop or document the column.

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
- **Evidence:** `port_droid.py:256` maps `"date": m["date"]`, which looks correct. So the
  value is either already wrong in the RLDS source, or the dataset was produced by a
  different script version.
- **Meaning for users:** the recording date is not available from this column.
- **Next step:** decode `episode_metadata.date` from one RLDS shard and compare.

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
