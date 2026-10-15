# robot-data-check

> Data quality checks for robot learning datasets in the LeRobot format. Runs as a CLI, scales out as a data pipeline, and exposes results to AI agents through an MCP server.

![CI](https://img.shields.io/badge/CI-TODO-lightgrey) ![License](https://img.shields.io/badge/license-Apache--2.0-blue) ![Python](https://img.shields.io/badge/python-3.10%2B-blue)

<!-- TODO: replace with a short GIF: asking Claude "which episodes have dropped frames?" and getting a correct answer -->
![demo](docs/demo.gif)

## Why

Robot learning datasets are recorded by many people, on many machines, across many sites. Small problems slip in silently: dropped frames, broken timestamps, stale normalization stats, idle segments, frozen cameras. Each one quietly degrades policy training, and most datasets are published without any systematic quality check.

**robot-data-check** scans any LeRobot v3 dataset, flags problems per episode and writes every finding to a single, stable results table. Problems come from three places, and the checks are grouped accordingly: **conversion** from other formats (mis-mapped metadata, label consistency), **recording** (dropped frames, timing jitter) and **behaviour** in the demonstration itself (idle stretches, action jumps). See [docs/vision.md](docs/vision.md). Four layers sit on top of one check engine:

- **CLI** — check a dataset locally and get a Markdown report.
- **Episode viewer** — browse episodes worst-first, with synced camera video, action / state plots and every flagged issue marked on the timeline.
- **Pipeline** — run the same checks as stateless shard jobs, orchestrated with incremental processing, writing to object storage.
- **Agent interface** — an MCP server that lets Claude (or any MCP client) query, diagnose and explain dataset quality in natural language, with a measured evaluation of how well it does.

## What it checks

| Check | What it detects | Method | Severity |
|---|---|---|---|
| `episode_bounds` | Metadata length ≠ actual frame count | SQL join episodes ↔ frames | error |
| `timestamps` | Dropped frames, non-monotonic or off-fps timestamps | Window functions vs `1/fps` | error / warning |
| `frame_index` | Gaps or duplicates in frame indices | Min / max / count per episode | error |
| `stats` | `stats.json` inconsistent with the actual data | Recompute mean / std / min / max | warning |
| `action_jumps` | Sudden spikes between consecutive actions | Thresholds from the dataset's own distribution | warning |
| `idle_segments` | Robot not moving for long stretches | Rolling-window state change | warning |
| `metadata` *(planned)* | Duplicated / mis-mapped metadata columns, empty or constant fields, very short episodes | Column comparisons across episodes | warning |

Each episode also gets a quality score aggregated from its issues. <!-- TODO: document the scoring formula once fixed -->

Planned: frozen / black camera frames, instruction ↔ video consistency. See [Roadmap](#roadmap).

## Quickstart

```bash
uv sync

# Check the first 200 episodes (0..199) of a Hub dataset
# (downloads metadata and data only, no videos)
uv run robocheck check lerobot/droid_1.0.1 --episodes 0-200 --out report/

# Run the tests (synthetic data, no network)
uv run pytest
```

Output:

- `report/summary.md` — human-readable report
- `report/results.parquet` — one row per detected issue, queryable with SQL

```bash
# Browse the results: synced video + signals + issues per episode
uv run robocheck view lerobot/droid_1.0.1 --episodes 0-200 --results report/
# -> http://127.0.0.1:8000/
```

```bash
# Example: query results directly with DuckDB
duckdb -c "SELECT check_name, count(*) FROM 'report/results.parquet' GROUP BY 1 ORDER BY 2 DESC"
```

## Results on DROID

<!-- TODO: fill in with real numbers only after running. Never publish placeholder numbers. -->

| Metric | Value |
|---|---|
| Episodes scanned | TODO |
| Episodes with ≥1 error | TODO |
| Most common issue | TODO |
| Scan time / cost | TODO |

**Key finding:** TODO (e.g. how quality metrics differ between successful and failed episodes, or across collection sites).

## Architecture

```mermaid
flowchart LR
    A[Hugging Face Hub<br/>LeRobot v3 dataset] -->|meta + data only| B[Parquet files<br/>local or object storage]
    subgraph Engine["Check engine (pure Python library)"]
        C[DuckDB views<br/>frames / episodes / tasks] --> D[Checks]
    end
    B --> C
    D --> E[(results.parquet<br/>stable schema)]
    E --> F[CLI + Markdown report]
    E --> V[Episode viewer]
    A -.->|video streamed with<br/>HTTP range requests| V
    E --> G[MCP server]
    G --> H[AI agent<br/>Claude, etc.]
    I[Orchestrator<br/>Dagster] -->|one job per shard| Engine
```

The check engine knows nothing about the CLI, the orchestrator, MCP or any agent. Every interface is a thin adapter over the same engine, so any of them can change without touching the checks.

### Results schema (the stable contract)

Every check writes rows with the same schema. Downstream consumers (reports, agents, pipelines, dashboards) depend only on this table.

| Column | Type | Meaning |
|---|---|---|
| `dataset` | string | Hub repo id |
| `dataset_revision` | string | Dataset commit / version scanned |
| `shard` | string | Shard the row was produced by |
| `episode_index` | int | Episode the issue belongs to; `-1` for dataset-level issues (shown separately in reports and the viewer) |
| `frame_start` | int, nullable | First affected `frame_index` (null = whole episode) |
| `frame_end` | int, nullable | Last affected `frame_index`, inclusive |
| `check_name` | string | Which check produced the row |
| `check_version` | string | Version of the check logic |
| `severity` | string | `error` or `warning` |
| `value` | double | Measured value (e.g. number of dropped frames) |
| `detail` | string | Human-readable explanation |

## Episode viewer

![Episode viewer on DROID episode 30](docs/img/viewer.png)

*Real data: `lerobot/droid_1.0.1` episode 30, three cameras in sync with action / state plots. No issues are flagged because only the `frame_index` check exists so far.*

`robocheck view` starts a local web page over the same engine and results table:

- **Episode list** sorted worst-first, filterable by check and severity, with episode attributes (success, building, collector) when the dataset has them.
- **Synced playback** of every camera plus `action` and `observation.state` plots; one video is the clock and the others follow it.
- **Issues on the timeline**: rows with `frame_start` / `frame_end` are drawn as bands on the timeline and plots; clicking an issue jumps to its frames.
- **Keyboard**: space play / pause, ←/→ step one frame, j/k next / previous episode.

Videos are never downloaded in full. A LeRobot v3 video file holds many episodes back to back, so the browser streams it straight from the Hub with HTTP range requests and seeks to the episode's segment: watching one 101-frame DROID episode on three cameras transfers about 13 MB out of 1.5 GB of video files. Text from the dataset (task descriptions) is rendered as plain text only.

The plots use `frame_index / fps` as the time axis, not the recorded `timestamp`, so a broken timestamp shows up as an issue instead of distorting the plot.

## Agent interface (MCP)

| Tool | Description |
|---|---|
| `run_checks(dataset)` | Run all checks, return a summary |
| `query_sql(sql)` | Read-only SQL over dataset views and results |
| `episode_summary(dataset, episode_index)` | All issues for one episode |

Tools return summaries first and paginated detail on request (row limits + offset), so the agent pulls only what it needs instead of flooding its context window.

Example questions an agent can answer:

- "Which episodes have dropped frames?"
- "List the 10 lowest-quality episodes and explain why."
- "Do failed episodes differ from successful ones on any quality metric?"

### Safety

- `query_sql` runs on a **read-only DuckDB connection** with external access disabled and configuration locked. A query cannot write data, read arbitrary local files or reach the network. Credentials (Hugging Face token, cloud keys) are never reachable from that connection.
- Text that comes from datasets (task descriptions, language annotations) is written by third parties and may contain prompt-injection attempts. It is returned **explicitly marked as data**, never as instructions.

### Setup

<!-- TODO: verify once the MCP server is implemented -->

Claude Code:

```bash
claude mcp add robot-data-check -- robocheck mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "robot-data-check": {
      "command": "robocheck",
      "args": ["mcp"]
    }
  }
}
```

### Agent evaluation

A tool interface is only useful if agents answer correctly with it. The agent eval set contains questions with ground-truth answers computed directly in SQL, covering lookups ("how many episodes have dropped frames?"), rankings ("which 5 episodes have the most action spikes?") and analysis ("do failed episodes have more idle time?").

For each question, the agent's answer is compared against the ground truth, and tool calls and tokens used are recorded.

<!-- TODO: fill in after running -->

| Tool design | Accuracy | Avg. tool calls | Avg. tokens |
|---|---|---|---|
| 3 general tools (current) | TODO | TODO | TODO |
| Many narrow tools (baseline) | TODO | TODO | TODO |

Findings: TODO (e.g. where the agent fails, and what interface change fixed it).

## Pipeline at scale

For datasets too large to check on one machine, the same engine runs as a pipeline:

- **Sharding** — the dataset is split into shards of episodes; each shard is one stateless job.
- **Idempotency** — each job writes results keyed by dataset, revision, shard and check version. A failed job is simply re-run and overwrites its own output; nothing needs to be rescued.
- **Incremental processing** — only shards whose data or check version changed are recomputed.
- **Orchestration** — shards are modelled as partitions in Dagster, so backfills, retries and partial re-runs come for free.
- **Storage** — data is queried in place on object storage with DuckDB; results land as Parquet next to it.

<!-- TODO: fill in after running -->

| Metric | Value |
|---|---|
| Episodes processed | TODO |
| Shards / parallel workers | TODO |
| Wall-clock time | TODO |
| Cost | TODO |
| Re-run time after a check version bump on one check | TODO |

## Check evaluation

Each check is tested by injecting known faults into a clean synthetic dataset and measuring detection and false-positive rates.

<!-- TODO: fill in after running -->

| Injected fault | Target check | Detection rate | False positives |
|---|---|---|---|
| Deleted frames | `timestamps`, `episode_bounds` | TODO | TODO |
| Shuffled timestamps | `timestamps` | TODO | TODO |
| Duplicated frame indices | `frame_index` | TODO | TODO |
| Corrupted stats | `stats` | TODO | TODO |
| Action spikes | `action_jumps` | TODO | TODO |
| Inserted idle segments | `idle_segments` | TODO | TODO |

## Design decisions

- **Query Parquet in place with DuckDB** — no ingestion step; the same SQL works locally and on object storage.
- **Metadata-first downloads** — videos are most of the dataset size and are skipped unless a visual check needs them.
- **Thresholds from the data itself** — anomaly thresholds come from each dataset's own distribution, not hard-coded constants.
- **Stream video, never download it** — the viewer seeks inside the Hub's multi-episode video files with HTTP range requests, keeping the metadata-first principle even when looking at video.
- **Engine separated from interfaces** — checks live in a library with no dependency on the CLI, viewer, orchestrator, MCP or any agent framework. The results schema is the contract; everything else is replaceable.
- **Deterministic checks, agent for exploration** — quality checks are SQL and code: reproducible and unit-tested. The agent interprets and explores results; it never decides on its own whether data is broken.
- **Few general tools instead of many narrow ones** — the agent gets a small set of general tools rather than pre-baked answers, so the interface does not encode today's model limitations. This choice is measured in the agent evaluation, not just assumed.
- **Agent access restricted at the engine level, not by filtering SQL** — string-filtering SQL is fragile; a locked-down connection is not.
- **Why not a generic data quality framework?** — tools like Great Expectations validate tables row by row and column by column. Robot data needs per-episode, time-series checks (dropped frames, action continuity, idle stretches) and dataset-specific metadata checks, which are simpler to express directly in SQL over the LeRobot layout.

## Project structure

<!-- TODO: keep in sync with the code -->

```
robot-data-check/
├── src/robot_data_check/
│   ├── engine/        # loading, DuckDB views, checks, results schema
│   ├── cli/           # robocheck CLI + Markdown report
│   ├── viewer/        # episode viewer (FastAPI + static page, thin adapter)
│   ├── mcp/           # MCP server (thin adapter)
│   └── pipeline/      # Dagster assets, shard jobs, storage
├── tests/
│   ├── fault_injection/
│   └── agent_eval/
└── docs/
```

## Roadmap

Full version with completion criteria and risks: [docs/vision.md](docs/vision.md).

**Done**
- [x] Load dataset, DuckDB views, schema inspection
- [x] `frame_index` check + fault-injection test harness
- [x] CLI + Markdown report
- [x] Episode viewer: synced video, signal plots, issues on the timeline

**Now**
- [ ] GitHub remote, CI running, browser end-to-end test in the repo

**M1 wrap-up — checks with real findings**
- [ ] `episode_bounds` → `metadata` → `idle_segments` → `action_jumps` → `stats`
- [ ] Run the checks on a second dataset, `lerobot/svla_so100_sorting` (SO-100), for behaviour checks
- [ ] Verify DROID findings against the original RLDS data ([findings](docs/findings/droid_1.0.1.md))
- [ ] Results on DROID + write-up, quality score

**Outreach**
- [ ] Upstream issue for confirmed defects; first blog post

**Phase 2 — scan the Hub**
- [ ] Inclusion criteria (valid metadata, minimum size, no test uploads), reported with exclusion counts
- [ ] Incremental, idempotent scans keyed by dataset commit sha; Dagster; cloud

**Phase 3 — agent interface**
- [ ] MCP server over results from all scanned datasets
- [ ] Agent eval set with ground-truth answers; tool design comparison

**Later**
- [ ] Visual checks (frozen / black frames), instruction ↔ video consistency

## Limitations

- Only LeRobot `v3.0` datasets are supported. In a random sample of 500 Hub datasets tagged `LeRobot`, 69.6% of the readable ones were `v3.0` (95% CI 65.4–73.5%); the rest were `v2.1` / `v2.0` ([census](docs/research/hub_census.md)).
- LeRobot stores `timestamp = frame_index / fps` for every dataset, so recording stalls are invisible in timestamps; they can only be inferred from indirect signals such as frozen camera frames ([details](docs/findings/lerobot_format.md)).
- The viewer streams AV1 video (LeRobot's default); Safari plays AV1 only on recent hardware.
- Anomaly thresholds are derived per dataset but have so far been validated on a small number of datasets.
- Visual checks are not yet implemented; problems that only show up in video (frozen or black frames) are not detected.
- A flagged issue is not always a real problem: some "idle segments" or "action jumps" may be intentional behaviour. Results are signals for review, not automatic verdicts.

## Acknowledgements

- [LeRobot](https://github.com/huggingface/lerobot) by Hugging Face
- [DROID](https://droid-dataset.github.io/) dataset — please cite the DROID paper if you use results on it

## License

Apache-2.0
