"""robocheck CLI: a thin adapter over the engine."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pyarrow as pa
import pyarrow.parquet as pq
import typer

from ..engine.checks import ALL_CHECKS
from ..engine.loader import EpisodeRange, load_dataset
from ..engine.registry import CheckContext, run_checks
from ..engine.results import RESULTS_SCHEMA, write_results
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


@app.command()
def view(
    dataset: Annotated[str, typer.Argument(help="Hub repo id or local dir (same as for check)")],
    results: Annotated[Path, typer.Option(help="Directory with results.parquet")] = Path("report"),
    episodes: Annotated[
        str | None, typer.Option(help="Half-open range like 0-200, or a single index")
    ] = None,
    revision: Annotated[str | None, typer.Option(help="Hub branch, tag or commit")] = None,
    host: Annotated[str, typer.Option(help="Interface to bind")] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 8000,
) -> None:
    """Browse episodes with synced video, signals and check results."""
    try:
        import uvicorn

        from ..viewer.server import create_app
    except ImportError:
        typer.echo("The viewer needs extra dependencies: uv pip install 'robot-data-check[viewer]'")
        raise typer.Exit(1) from None

    ep_range = EpisodeRange.parse(episodes) if episodes else None
    ds = load_dataset(dataset, episodes=ep_range, revision=revision)

    table = None
    path = results / "results.parquet"
    if path.exists():
        # Older result files may lack newer nullable columns: align to the current schema.
        raw = pq.read_table(path)
        table = pa.table(
            {
                f.name: raw[f.name] if f.name in raw.column_names else pa.nulls(len(raw), f.type)
                for f in RESULTS_SCHEMA
            },
            schema=RESULTS_SCHEMA,
        )
        revs = set(table.column("dataset_revision").to_pylist())
        if revs and revs != {ds.revision}:
            typer.echo(f"warning: results are for revision {revs}, dataset is at {ds.revision}")
    else:
        typer.echo(f"warning: {path} not found, showing episodes without check results")

    typer.echo(f"Episode viewer: http://{host}:{port}/")
    typer.echo(f"Review labels are saved to {results / 'labels.jsonl'}")
    app_ = create_app(ds, table, labels_path=results / "labels.jsonl")
    uvicorn.run(app_, host=host, port=port, log_level="warning")
