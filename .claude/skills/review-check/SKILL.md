---
name: review-check
description: Review a quality check the user wrote (src/robot_data_check/engine/checks/*.py and its fault-injection test). Use when the user says a check is done, asks for feedback on one, or asks Claude to fix or finish a check.
---

# Review a user-written check

The user writes the checks themselves so they can explain and defend them. Your job is
to make the check correct and the user stronger, not to write it for them.

## Ground rules

- Do **not** edit the check or its test. Point at the line, explain the problem, ask a
  question that leads to the fix. Give a code snippet only if the user explicitly asks
  for one, and keep it minimal.
- Run things to support your review (`uv run pytest`, queries against DROID or the
  synthetic dataset). Evidence beats opinion: show the failing case.
- Separate **must fix** (wrong results, broken contract) from **suggestions**.

## Checklist

**Correctness**
- [ ] SQL logic matches the docstring; window functions partition by `episode_index` and
      order by `frame_index`
- [ ] Edge cases: first frame of an episode (`LAG` is NULL), single-frame episodes,
      NULLs in the data, float32 rounding (e.g. timestamps compared with a tolerance)
- [ ] Runs on the real dataset (DROID subset) without errors, in reasonable time

**Contract** (see `engine/registry.py`, `engine/results.py`)
- [ ] Returns `Issue`s only; no file writes, no full result rows
- [ ] Severity follows the docstring (`error` = data is wrong, `warning` = suspicious)
- [ ] Located problems set `frame_start` / `frame_end` (inclusive)
- [ ] Dataset-level problems use the agreed convention (`episode_index = -1`, documented)
- [ ] `VERSION` bumped if the logic of an existing check changed
- [ ] Added to `ALL_CHECKS` in `checks/__init__.py`

**Thresholds**
- [ ] Derived from the data's own distribution (quantiles, MAD, ...), not constants
- [ ] The derivation is explained in the docstring

**Tests** (pattern: `tests/fault_injection/test_frame_index.py`)
- [ ] Clean synthetic dataset → zero issues
- [ ] Each fault type injected → exactly the expected issue(s), with location
- [ ] New injectors live in `tests/fault_injection/faults.py`, written in SQL

**Results on real data**
- [ ] Run it on DROID (and the second dataset once added); look at a few flagged
      episodes in `robocheck view`
- [ ] Anything that looks like a real finding goes through the `verify-finding` skill

## Finish with explain-back questions

End every review with 2–3 questions the user should be able to answer without notes,
as practice for interviews. For example:

- "Why did you choose this quantile for the threshold, and what happens on a dataset
  where the robot barely moves?"
- "What does this check report if the first two frames of an episode are missing?"
- "Why is this an `error` and not a `warning`?"
