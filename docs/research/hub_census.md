# Hub census of LeRobot datasets

Evidence for the Phase 2 inclusion criteria ([vision.md](../vision.md)). Reproduce with
`uv run python tools/research/hub_census.py report` (reads the committed sample
[hub_census_sample.csv](hub_census_sample.csv)); `collect` re-samples from the Hub.

## Method

- Population: **80,885** datasets tagged `LeRobot` on 2026-10-15 (unfiltered).
- Simple random sample of **500**, seed 0. Only `meta/info.json` was fetched per dataset.
- Proportions are given with Wilson 95% confidence intervals. Scaled-up counts
  ("≈ N datasets") multiply the sample share by the population and carry the same
  relative uncertainty.

## Results

**Readability**: 490 / 500 = 98.0% (95% CI 96.4–98.9%) have a readable `meta/info.json`.
The 10 others: 7 have no `meta/info.json`, 3 are gated.

**Format version** (of the 490 readable):

| `codebase_version` | Share |
|---|---|
| `v3.0` | 341 / 490 = 69.6% (95% CI 65.4–73.5%) |
| `v2.1` | 136 / 490 = 27.8% (95% CI 24.0–31.9%) |
| `v2.0` | 13 / 490 = 2.7% (95% CI 1.6–4.5%) |

**Size**: most datasets are tiny.

| | min | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|---|
| `total_episodes` (n = 489) | 0 | 1 | 2 | 10 | 50 | 130 | 60,064 |
| `total_frames` (n = 490) | 0 | 37 | 1,024 | 4,768 | 24,088 | 64,556 | 2,255,591 |

| Episodes | Share of datasets |
|---|---|
| = 0 | 46 / 489 = 9.4% (95% CI 7.1–12.3%) |
| < 5 | 180 / 489 = 36.8% (95% CI 32.7–41.2%) |
| < 10 | 209 / 489 = 42.7% (95% CI 38.4–47.2%) |
| < 20 | 274 / 489 = 56.0% (95% CI 51.6–60.4%) |
| < 50 | 354 / 489 = 72.4% (95% CI 68.3–76.2%) |

All 46 zero-episode datasets also have 0 frames (44 of them `v3.0`): created, never filled.
One dataset has an empty `total_episodes` field.

**Robots, cameras, fps** (of 490): `robot_type` is dominated by SO arms (`so_follower` 158,
`so101_follower` 64, `so100` 27, `so100_follower` 12); 18 have no `robot_type`. Most have
2 cameras (244) or 3 (102); 16 have none. 374 record at 30 fps.

**Downloads** (all 500): median 42, p90 151, max 6,476; none has 0 downloads, so download
counts do not separate abandoned uploads from used datasets.

## What survives candidate criteria

| Criteria | Share of all 500 | ≈ datasets |
|---|---|---|
| readable, `v3.0` | 341 = 68.2% (64.0–72.1%) | ≈ 55,200 |
| + at least 1 episode | 297 = 59.4% (55.0–63.6%) | ≈ 48,000 |
| + at least 5 episodes | 218 = 43.6% (39.3–48.0%) | ≈ 35,300 |
| + at least 10 episodes | 202 = 40.4% (36.2–44.8%) | ≈ 32,700 |
| readable, `v2.x` or `v3.0`, at least 10 episodes | 280 = 56.0% (51.6–60.3%) | ≈ 45,300 |

Adding "at least 1,000 frames" to "at least 10 episodes" removes nothing in this sample.

## Proposal (for the user to decide)

1. **Readable `meta/info.json` with a supported version**: unavoidable.
2. **At least 1 episode**: removes the 9.4% that are empty shells; no judgement involved.
3. **A minimum size** such as 10 episodes (the sample median): removes practice and test
   uploads, keeps about 40% of the Hub, roughly 33k datasets. This one is a judgement call
   and should be stated as such in every scan report.
4. **`v2.1` support** would raise coverage from about 40% to about 56% at the same size
   threshold; worth considering before Phase 2.

Whatever is chosen, every scan report lists how many datasets each criterion removed.
