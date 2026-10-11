---
name: check-workflow
description: Build one quality check end to end with separated roles - user-written spec, a test subagent that never sees the implementation, an implementation subagent that may not touch tests, user adjudication, SQL mutation testing, then review and a reading guide. Use when the user asks to implement, build or "do" a check (episode_bounds, metadata, timestamps, ...).
---

# Check workflow

Why: one agent writing both code and tests can put the same misunderstanding in both
(e.g. treating an inclusive bound as exclusive) and the suite still goes green. The
separation only works through **information isolation**, so follow the read/write rules
exactly. The user's understanding comes from three steps they do themselves: the spec,
the rulings, and the explain-back questions.

`<check>` below is the module name, e.g. `episode_bounds`.

## 0. Gate: the spec exists and is the user's

- `docs/specs/<check>.md` must exist and be written by the user (template:
  `docs/specs/TEMPLATE.md`). If it is missing, stop and ask the user to write it. You
  may answer questions about the data format; never fill in the spec.
- Read it. If a rule is ambiguous enough that tests could go either way, ask the user
  now; record the answer under **Decisions** in the spec (with the date).

## 1. Test subagent (runs first, against the stub)

Spawn a fresh `general-purpose` subagent. Prompt template:

> You write tests for the `<check>` data-quality check of this repo. You are QA: you must
> NOT open, grep or otherwise read any file under `src/robot_data_check/engine/checks/`.
> For the test style, use `tests/fault_injection/test_frame_index.py` instead.
>
> Read: `docs/specs/<check>.md` (the requirements, including Decisions),
> `docs/droid_layout.md` (data format), `src/robot_data_check/engine/results.py`,
> `src/robot_data_check/engine/registry.py`, `src/robot_data_check/engine/views.py`,
> `tests/synthetic.py`, `tests/conftest.py`, `tests/fault_injection/faults.py`,
> `tests/fault_injection/test_frame_index.py`.
>
> Write only: `tests/fault_injection/test_<check>.py`, and new injector functions
> appended to `tests/fault_injection/faults.py` (SQL-based, like the existing ones; do not
> change existing ones).
>
> Requirements: for every rule R1..Rn in the spec, at least one test where the rule is
> violated (assert the exact issues: episode, severity, value, frame_start/frame_end,
> wording that matters) and one near-miss where it is not. One test that the clean
> synthetic dataset yields no issues. Name tests after the rule they cover.
> Use the `run_check` fixture. Run `uv run pytest tests/fault_injection/test_<check>.py`;
> it must fail with NotImplementedError (the check is a stub). Report: tests per rule,
> any spec ambiguity you had to resolve and how.

Afterwards:
- Confirm the run is red because of `NotImplementedError`, not import or fixture errors.
- Any ambiguity the agent resolved on its own goes to the user before continuing.
- Record hashes: `sha256sum tests/fault_injection/test_<check>.py tests/fault_injection/faults.py`.

## 2. Implementation subagent

Spawn a **new** `general-purpose` subagent. Prompt template:

> You implement the `<check>` check in `src/robot_data_check/engine/checks/<check>.py`
> to satisfy `docs/specs/<check>.md` and the tests in
> `tests/fault_injection/test_<check>.py`.
>
> Rules: tests and `tests/fault_injection/faults.py` are READ-ONLY. If you believe a test
> is wrong, stop and report the test name, the spec rule, and your reasoning; do not work
> around it. Write only `engine/checks/<check>.py` and add the module to `ALL_CHECKS` in
> `engine/checks/__init__.py`. Follow `engine/registry.py`: return `Issue`s only; put SQL
> in module-level constants (`SQL` or `SQL_*`) that `run()` reads at call time; set
> `frame_start`/`frame_end` for located problems; thresholds from data, not constants;
> keep `NAME`; set `VERSION = "1"`. Use `checks/frame_index.py` as the style reference.
> Run `uv run pytest -q` and `uv run ruff check . && uv run ruff format --check .`.
> Report what each SQL block does, mapped to spec rules.

Afterwards:
- Re-run `sha256sum` on the two test files. **Any change → discard the implementation**
  (`git checkout` the check file), tell the user, start step 2 again.
- Run the full suite yourself.

## 3. Disagreements → the user decides

If tests fail and the implementation agent says a test is wrong, or the spec is
ambiguous, stop and give the user:

1. the failing test (name + the assertion),
2. the spec text it relies on,
3. the two readings, side by side, with a concrete example of where they differ.

Record the ruling under **Decisions** in the spec. Then send the fix to the side that was
wrong: test agent (fresh subagent, same isolation) or implementation agent. Never fix it
yourself.

## 4. SQL mutation testing

`uv run python tools/mutate_sql.py <check>`

For each survivor, a fresh test subagent (same isolation, no implementation access) gets
the mutant's **description only** (e.g. "changing `>` to `>=` on line 4 of the SQL still
passes") plus the spec, and adds a test that would catch that behaviour. Repeat until no
survivors remain, or the user accepts a survivor as equivalent (record it in Decisions).

## 5. Review and reading guide

Run the `review-check` skill. The check is done only after the user has answered its
explain-back questions.

## 6. Real data

Run on DROID (and the second dataset once added): `uv run robocheck check ...`, look at
flagged episodes in `robocheck view`. Anything that looks like a real finding goes
through `verify-finding` before it is called a defect.

## Known limits of the isolation

Subagents run in the same repository; the read rules are instructions, not enforcement.
Running tests first (while the check is a stub) is the main safeguard; the hash check
enforces the write rule. Do not paste implementation code into a test agent's prompt.
