---
name: review-check
description: Review a quality check (src/robot_data_check/engine/checks/*.py and its fault-injection test) and give the user a reading guide plus explain-back questions. Use as step 5 of check-workflow, or whenever the user asks for a review of a check or wants to understand one.
---

# Review a check and guide the user through it

Checks are written by subagents against the user's spec (`check-workflow`). The review
has two goals: the check is correct, and the **user** can explain and defend it without
notes. The second goal is what makes this the user's project.

## Ground rules

- Do not edit the check or its tests. Problems go back through `check-workflow`
  (implementation agent for code, test agent for tests, user for spec questions).
- Support claims with evidence: run `uv run pytest`, run queries on the synthetic dataset
  or DROID, show the failing case.
- Separate **must fix** (wrong results, broken contract) from **suggestions**.

## Checklist

**Matches the spec**
- [ ] Every rule R1..Rn in `docs/specs/<check>.md` is implemented, and nothing else
- [ ] Every Decision in the spec is reflected in code and tests

**Correctness**
- [ ] Window functions partition by `episode_index` and order by `frame_index`
- [ ] Edge cases: first frame (`LAG` is NULL), single-frame episodes, NULLs, float32
      rounding, episode-range filtering cutting an episode off
- [ ] Runs on a DROID subset without errors, in reasonable time

**Contract** (`engine/registry.py`, `engine/results.py`)
- [ ] Returns `Issue`s only; severity, `value` and `detail` as the spec says
- [ ] Located problems set `frame_start` / `frame_end` (inclusive)
- [ ] SQL in module-level `SQL` / `SQL_*` constants; `NAME`, `VERSION` set; in `ALL_CHECKS`

**Thresholds**: derived from the data's own distribution and explained in the docstring

**Tests**: clean dataset → zero issues; each rule has a violating and a near-miss case;
`tools/mutate_sql.py <check>` has no unexplained survivors

## Output: the reading guide

Write it for the user, in Chinese, short:

1. **Reading order**: which file, which function, which SQL block, in what order.
   Typically the spec → the test names (they read like the spec) → the SQL constant
   block by block → `run()`.
2. **Map to the spec**: for each SQL block or test, the rule (R1..Rn) it implements.
3. **Mutation result**: `killed k/n`, and what any accepted survivor means.
4. **Real data**: what it found on DROID, if run, with the status from `verify-finding`.
5. **Three explain-back questions**, answerable from the code, e.g.:
   - "What does this report when the first two frames of an episode are missing, and why?"
   - "Why is this an `error`, not a `warning`?"
   - "How is the threshold derived, and what happens on a dataset where the robot barely moves?"

The check is done only when the user has answered the questions. If an answer is off,
point to the exact lines to reread; do not just give the answer.
