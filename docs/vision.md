# Vision and roadmap

This is the source of truth for direction. The README summarises it; if they disagree,
this file wins and the README gets fixed.

## Positioning

**Integrity checks for LeRobot datasets**: find what is broken in a dataset, prove it with
reproducible SQL, show it in a viewer, and report confirmed defects upstream.

Checks fall into three families, because problems come from different places:

| Family | Typical source | Examples | Where it shows up |
|---|---|---|---|
| Conversion integrity | Porting from another format (RLDS, ...) | duplicated / mis-mapped metadata columns, label consistency | large converted datasets such as DROID |
| Recording integrity | Recording hardware and software | frozen / repeated camera frames, state jumps too large for one frame, frame-index gaps | datasets recorded directly with LeRobot |
| Behaviour anomalies | The demonstration itself | idle stretches, action jumps | both |

### Why not only converted datasets

The first real findings are conversion-related (see [findings/droid_1.0.1.md](findings/droid_1.0.1.md)),
which makes conversion integrity the natural entry point. But by count, the Hub is
dominated by directly recorded community datasets:

- **79,933** datasets carry the `LeRobot` tag (2026-10-11, unfiltered: includes test
  uploads and tiny practice datasets).
- Random sample of 60, 59 readable: **46 are `v3.0`, about 78% (95% CI ≈ 66–87%, Wilson)**,
  13 are `v2.1`. The most common `robot_type`s are `so_follower` (21) and
  `so101_follower` (10).

Converted datasets are few but large and influential; recorded ones are many and small.
Covering both is what makes a Hub-wide scan meaningful.

### Recording problems do not show up in timestamps

LeRobot's writer always stores `timestamp = frame_index / fps`, for converted and directly
recorded datasets alike (8 datasets measured, code located; see
[findings/lerobot_format.md](findings/lerobot_format.md)). A stalled control loop or a late
camera frame is invisible in the tabular data. Recording integrity therefore has to be
inferred from indirect signals:

- **frozen or repeated camera frames**: the image does not change while the robot state
  does; needs video decoding (feasibility: [research/frozen_frames.md](research/frozen_frames.md))
- **state jumps** larger than the robot can move in one `1 / fps` step (overlaps with
  `action_jumps`)

What to do with the planned timestamp check is an open decision (keep it as a cheap
consistency check for non-standard writers, or fold it into `frame_index`).

### Second dataset

`lerobot/svla_so100_sorting` (official, SO-100, 52 episodes; notes in
[svla_so100_sorting_layout.md](svla_so100_sorting_layout.md)). It gives the behaviour checks a
different robot, task and recording setup than DROID; it cannot help timing checks.

## Roadmap

| Stage | Content | Done when |
|---|---|---|
| **Now** | GitHub remote, CI running, browser end-to-end test script in the repo | CI is green |
| **M1 wrap-up** | User writes a spec per check, agents build it ([check-workflow](../.claude/skills/check-workflow/SKILL.md)), in order: `episode_bounds` → `metadata` (duplicated columns, empty / constant fields, very short episodes) → `idle_segments` → `action_jumps` → `stats`. Run the checks on `lerobot/svla_so100_sorting` as well. Find the source the LeRobot DROID port actually used and verify the DROID findings against it. | README Results and Key finding filled with real numbers |
| **Outreach** | Upstream issue for confirmed defects; first technical blog post | A public issue link |
| **Phase 2: scan the Hub** | Define inclusion criteria first; then incremental, idempotent scans keyed by dataset commit sha; Dagster orchestration; cloud | Can say "scanned N datasets (after filtering M), found these categories of problems" |
| **Phase 3: agent interface** | MCP server + agent eval, querying results across all scanned datasets | Agent eval has real accuracy numbers |

### M1: verifying DROID findings at the source

Before any upstream issue about `task_category` or `date`:

1. Read one TFRecord shard of DROID's RLDS release (public GCS bucket) and decode
   `episode_metadata`.
2. Record whether a `task_category` field exists and what `date` actually contains.
3. Update the findings log; only a **defect** with a located cause gets an issue, sent to
   the party that owns the cause (LeRobot conversion script vs. DROID source data).

### Phase 2: inclusion criteria come first

An unfiltered scan would be dominated by test uploads and empty datasets. Before scanning,
define and document criteria, for example:

- `meta/info.json` parses; `codebase_version` is supported
- at least N episodes and M frames (N, M chosen from the observed distribution)
- not an obvious test upload (to be defined from data, not guessed)

Example of why: `SO-101-robot-learning/so101_pick_place` had 7.6k downloads but
`total_episodes = 0` (2026-10-14). The census in
[research/hub_census.md](research/hub_census.md) gives the distribution these thresholds
should come from.

Every scan report states how many datasets were excluded and why.

## Risks

| Risk | Mitigation |
|---|---|
| **Code ownership**: checks implemented by agents | The user writes each spec, rules on every test/implementation disagreement and answers explain-back questions; tests and implementation come from isolated agents, checked by SQL mutation testing ([CLAUDE.md](../CLAUDE.md), [code-tour.md](code-tour.md)) |
| Overclaiming a finding | `verify-finding` skill; four statuses; source data checked before upstream issues |
| `v2.1` datasets (≈22% of the sample) unsupported | Phase 2 either adds `v2.1` support or reports "v3 only" explicitly |
| Hub rate limits | `HF_TOKEN` for scans; metadata-first downloads keep requests small |
| Scope creep (four interface layers) | Each stage must reach its "done when" before the next starts |
| Arbitrary quality score | Calibrate against human review in the viewer; never equate task failure with bad data |
