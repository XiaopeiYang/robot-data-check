"""SQL mutation testing for checks: do the tests notice when the SQL is subtly wrong?

Checks keep their logic in module-level SQL constants (``SQL`` or ``SQL_*``). This tool
makes one small change at a time to that SQL (a mutant), runs the check's tests, and
reports mutants the tests did not catch ("survivors"). Each survivor is a concrete gap
in the tests, e.g. "changing ``>`` to ``>=`` on line 3 still passes".

Python mutation tools (mutmut, ...) cannot do this: they mutate Python operators and at
most garble a whole string, never the ``<`` / ``AND`` / ``+ 1`` inside SQL.

Usage::

    uv run python tools/mutate_sql.py frame_index [-j 8]

Mutants are injected into the test process through ``ROBOCHECK_SQL_MUTANT`` (see the
autouse fixture in ``tests/conftest.py``). Mutants that make the SQL invalid are counted
separately: they are caught trivially and say nothing about test strength.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS_PKG = "robot_data_check.engine.checks"
SQL_ERROR = re.compile(r"duckdb\.\w*\.?(Parser|Binder|Catalog|Conversion)Exception")


@dataclass(frozen=True)
class Mutant:
    attr: str  # SQL constant name in the check module
    line: int  # 1-based line inside that SQL string
    description: str
    sql: str


# ---------- SQL scanning ----------


def code_spans(sql: str) -> list[tuple[int, int]]:
    """(start, end) spans of SQL code, excluding string literals, quoted identifiers
    and ``--`` comments, so mutations never touch e.g. ``'a < b'`` or ``"x=y"``."""
    spans, i, start, n = [], 0, 0, len(sql)
    while i < n:
        c = sql[i]
        if c in "'\"":
            spans.append((start, i))
            j = i + 1
            while j < n:
                if sql[j] == c:
                    if j + 1 < n and sql[j + 1] == c:  # escaped quote
                        j += 2
                        continue
                    break
                j += 1
            i = start = j + 1
        elif sql.startswith("--", i):
            spans.append((start, i))
            j = sql.find("\n", i)
            i = start = n if j == -1 else j
        else:
            i += 1
    spans.append((start, n))
    return [(a, b) for a, b in spans if b > a]


def _in_code(spans: list[tuple[int, int]], a: int, b: int) -> bool:
    return any(s <= a and b <= e for s, e in spans)


def _masked(sql: str, spans: list[tuple[int, int]]) -> str:
    """Same length as ``sql`` with non-code characters blanked, for regex scanning."""
    out = [" "] * len(sql)
    for a, b in spans:
        out[a:b] = sql[a:b]
    return "".join(out)


# ---------- mutation operators ----------

# Token-level operators: (pattern, replacement function, label)
_SWAP_CMP = {"<": "<=", "<=": "<", ">": ">=", ">=": ">", "=": "<>", "<>": "=", "!=": "="}
_TOKEN_OPS: list[tuple[re.Pattern[str], Callable[[re.Match[str]], str], str]] = [
    (
        # comparisons; skip the ">" of DuckDB lambdas ("x -> ...")
        re.compile(r"<=|>=|<>|!=|(?<![<>!=])=(?![=>])|<|(?<!-)>"),
        lambda m: _SWAP_CMP[m.group(0)],
        "comparison",
    ),
    (
        re.compile(r"\b(AND|OR)\b", re.I),
        lambda m: "OR" if m.group(0).upper() == "AND" else "AND",
        "logic",
    ),
    (re.compile(r"\s*[+-]\s*1\b(?!\.)"), lambda m: "", "drop ±1"),
    (
        re.compile(r"\b(min|max)(?=\s*\()", re.I),
        lambda m: "max" if m.group(0).lower() == "min" else "min",
        "min/max",
    ),
    (re.compile(r"\bDISTINCT\s+", re.I), lambda m: "", "drop DISTINCT"),
]

_CLAUSE_END = re.compile(
    r"\b(GROUP\s+BY|ORDER\s+BY|UNION|HAVING|LIMIT|WINDOW|QUALIFY|WHERE)\b", re.I
)


def _condition_extent(masked: str, start: int) -> int:
    """End of a WHERE/HAVING condition that starts at ``start``: the next clause
    keyword or closing parenthesis at nesting depth 0."""
    depth, i = 0, start
    while i < len(masked):
        c = masked[i]
        if c == "(":
            depth += 1
        elif c == ")":
            if depth == 0:
                return i
            depth -= 1
        elif depth == 0 and _CLAUSE_END.match(masked, i) and masked[i - 1].isspace():
            return i
        i += 1
    return len(masked)


def _top_level_conjuncts(masked: str, a: int, b: int) -> list[tuple[int, int]]:
    """Spans of the AND-separated parts of the condition masked[a:b] (depth 0 only)."""
    parts, depth, s = [], 0, a
    for m in re.finditer(r"\(|\)|\bAND\b", masked[a:b], re.I):
        tok, pos = m.group(0), a + m.start()
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
        elif depth == 0:
            parts.append((s, pos))
            s = pos + len(tok)
    parts.append((s, b))
    return parts


def mutants_of(attr: str, sql: str) -> Iterator[Mutant]:
    spans = code_spans(sql)
    masked = _masked(sql, spans)

    def make(a: int, b: int, repl: str, label: str) -> Mutant:
        line = sql.count("\n", 0, a) + 1
        before = " ".join(sql[a:b].split()) or "∅"
        after = " ".join(repl.split()) or "∅"
        return Mutant(attr, line, f"{label}: `{before}` → `{after}`", sql[:a] + repl + sql[b:])

    for pattern, repl, label in _TOKEN_OPS:
        for m in pattern.finditer(masked):
            if _in_code(spans, m.start(), m.end()):
                yield make(m.start(), m.end(), repl(m), label)

    for m in re.finditer(r"\b(WHERE|HAVING)\b", masked, re.I):
        a = m.end()
        b = _condition_extent(masked, a)
        cond = sql[a:b]
        trail = cond[len(cond.rstrip()) :]
        yield make(a, b, " TRUE" + trail, f"drop {m.group(0).upper()}")
        conj = _top_level_conjuncts(masked, a, b)
        if len(conj) > 1:
            for s, e in conj:
                yield make(s, e, " TRUE ", f"drop {m.group(0).upper()} conjunct")


# ---------- running ----------


def sql_constants(module) -> dict[str, str]:
    return {
        k: v
        for k, v in vars(module).items()
        if (k == "SQL" or k.startswith("SQL_")) and isinstance(v, str)
    }


def run_tests(test_file: Path, module: str, mutant: Mutant | None) -> tuple[int, str]:
    env = dict(os.environ)
    if mutant is not None:
        env["ROBOCHECK_SQL_MUTANT"] = json.dumps(
            {"module": module, "attr": mutant.attr, "sql": mutant.sql}
        )
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", str(test_file)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    return p.returncode, p.stdout + p.stderr


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("check", help="check module name, e.g. frame_index")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 2)
    args = ap.parse_args(argv)

    module_name = f"{CHECKS_PKG}.{args.check}"
    module = importlib.import_module(module_name)
    test_file = ROOT / "tests" / "fault_injection" / f"test_{args.check}.py"
    if not test_file.exists():
        print(f"no tests: {test_file.relative_to(ROOT)}")
        return 2
    consts = sql_constants(module)
    if not consts:
        print(f"{module_name} has no SQL / SQL_* constants to mutate")
        return 2

    code, out = run_tests(test_file, module_name, None)
    if code != 0:
        print("tests fail without any mutation; fix them first\n" + out[-2000:])
        return 2

    mutants = [m for attr, sql in consts.items() for m in mutants_of(attr, sql)]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        outcomes = list(pool.map(lambda m: run_tests(test_file, module_name, m), mutants))

    survived, invalid = [], []
    for m, (code, out) in zip(mutants, outcomes, strict=True):
        if code == 0:
            survived.append(m)
        elif SQL_ERROR.search(out):
            invalid.append(m)
    valid = len(mutants) - len(invalid)
    killed = valid - len(survived)

    print(f"{args.check}: {len(mutants)} mutants, {len(invalid)} invalid SQL (ignored)")
    if valid:
        print(f"killed {killed}/{valid} ({100 * killed / valid:.0f}%)")
    for m in survived:
        print(f"  SURVIVED  {m.attr} line {m.line}  {m.description}")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
