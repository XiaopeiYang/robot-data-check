"""Render results into a human-readable Markdown summary.

Only reads the results table (plus the number of episodes scanned), so it works
the same on results produced by the CLI or by the pipeline.

TODO(you): add the per-episode quality score once its formula is fixed.
"""

from __future__ import annotations

import duckdb
import pyarrow as pa


def _md_table(header: list[str], rows: list[tuple]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def render_summary(
    results: pa.Table, *, dataset: str, revision: str, episodes_scanned: int, checks: list[str]
) -> str:
    con = duckdb.connect()
    con.register("results", results)

    by_check = con.execute(
        """
        SELECT check_name,
               count(*) FILTER (severity = 'error')   AS errors,
               count(*) FILTER (severity = 'warning') AS warnings,
               count(DISTINCT episode_index)          AS episodes
        FROM results GROUP BY 1 ORDER BY 2 DESC, 3 DESC
        """
    ).fetchall()
    n_bad = con.execute(
        "SELECT count(DISTINCT episode_index) FROM results WHERE severity = 'error'"
    ).fetchone()[0]
    worst = con.execute(
        """
        SELECT episode_index,
               count(*) FILTER (severity = 'error')   AS errors,
               count(*) FILTER (severity = 'warning') AS warnings,
               string_agg(DISTINCT check_name, ', ' ORDER BY check_name) AS checks
        FROM results GROUP BY 1 ORDER BY 2 DESC, 3 DESC, 1 LIMIT 10
        """
    ).fetchall()

    out = [
        f"# Data quality report: `{dataset}`",
        "",
        f"- Revision: `{revision}`",
        f"- Episodes scanned: {episodes_scanned}",
        f"- Episodes with ≥1 error: {n_bad}",
        f"- Checks run: {', '.join(f'`{c}`' for c in checks)}",
        "",
        "## Issues by check",
        "",
    ]
    out.append(
        _md_table(["Check", "Errors", "Warnings", "Episodes affected"], by_check)
        if by_check
        else "No issues found."
    )
    if worst:
        out += ["", "## Episodes with the most issues", ""]
        out.append(_md_table(["Episode", "Errors", "Warnings", "Checks"], worst))
    return "\n".join(out) + "\n"
