"""robocheck CLI: a thin adapter over the engine."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ..engine.checks import ALL_CHECKS
from ..engine.loader import EpisodeRange, load_dataset
from ..engine.registry import CheckContext, run_checks
from ..engine.results import write_results
from ..engine.views import connect
from .report import render_summary

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def _main() -> None:
    """Data quality checks for LeRobot v3 datasets."""


@app.command()
def check(
    dataset: Annotated[str, typer.Argument(help="Hub repo id (e.g. lerobot/pusht) or local dir")],
    episodes: Annotated[
        str | None,
        typer.Option(help="Half-open range like 0-200 (episodes 0..199), or a single index"),
    ] = None,
    revision: Annotated[str | None, typer.Option(help="Hub branch, tag or commit")] = None,
    out: Annotated[Path, typer.Option(help="Output directory")] = Path("report"),
) -> None:
    """Check a dataset and write results.parquet + summary.md."""
    ep_range = EpisodeRange.parse(episodes) if episodes else None
    ds = load_dataset(dataset, episodes=ep_range, revision=revision)
    con = connect(ds)
    ctx = CheckContext(dataset=dataset, revision=ds.revision, fps=ds.fps, info=ds.info)

    shard = f"episodes_{ep_range}" if ep_range else "all"
    results = run_checks(con, ctx, ALL_CHECKS, shard=shard)
    n_episodes = con.execute("SELECT count(*) FROM episodes").fetchone()[0]

    write_results(results, out / "results.parquet")
    summary = render_summary(
        results,
        dataset=dataset,
        revision=ds.revision,
        episodes_scanned=n_episodes,
        checks=[c.name for c in ALL_CHECKS],
    )
    (out / "summary.md").write_text(summary)
    typer.echo(f"{n_episodes} episodes, {results.num_rows} issues -> {out}/")
