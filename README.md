# Data Warehousing, AOI and Bottom-Up Cube

This repository contains two end-to-end data-analytics projects. Part 1 is a
DuckDB snowflake warehouse and OLAP analysis built on Brazilian marketplace
data. Part 2 implements Attribute-Oriented Induction (AOI), in-memory BUC and
byte-budgeted out-of-memory BUC over 299,285 US census records.

## Project navigation

| Project | Main topics | Documentation |
| --- | --- | --- |
| Part 1 | Snowflake schema, ETL, DuckDB, CUBE, ROLLUP and drill-down | [Part 1 README](part1/README.md) · [Full report](part1/Report.md) |
| Part 2 | AOI, concept hierarchies, iceberg cubes, external-memory BUC and optimization | [Part 2 README](part2/README.md) · [Full report](part2/Report.md) |

## Highlights

- Built and validated a normalized DuckDB warehouse without dropping orders that lack reviews, payments or delivery timestamps.
- Built six data-driven concept hierarchies and generated AOI characteristic and discriminant rules.
- Implemented BUC without a database engine or DataFrame `groupby` for cube computation.
- Verified in-memory and paged BUC exactly against DuckDB, including a 12-dimensional cube.
- Improved paged BUC benchmark runtime from 190.75 seconds to 62.65 seconds using dimension reordering.

## Directory structure

```
Assignment2/
├── requirements.txt
├── part1/       schema, ETL, queries, ER diagram, report  (Olist dataset)
└── part2/       AOI, BUC, verification, benchmarks, report  (census dataset)
```

### part1/

| Path | What it is |
| --- | --- |
| `M26_DA_A2_Part1/` | raw input CSVs, 11 files — not tracked, drop them here before running anything |
| `preprocessing.ipynb` | profiling + cleaning; writes `cleaned/` (also not tracked — regenerate by running this) |
| `seed/state_region_mapping.csv` | authored state → region mapping (region isn't in the raw data) |
| `create_schema.sql` | snowflake schema — 12 dimension tables + 1 fact table |
| `etl_load.py` | loads `cleaned/` into `warehouse.duckdb`, then runs `q1.sql`..`q10.sql` and saves `qN_result.csv` |
| `run_pipeline.py` | runs preprocessing + `etl_load.py` end to end in one shot |
| `q1.sql` .. `q10.sql` | the ten analytical queries |
| `q1_result.csv` .. `q10_result.csv` | their saved outputs |
| `validation_log.txt`, `validation_summary.json` | ETL run log — row counts, orphan-key checks, back up the numbers cited in `Report.md` |
| `report_assets/` | `er_diagram.png` + its `er_diagram.puml` source (rendered via plantuml.com) |
| `Report.md` | Part 1 report |

### part2/

| Path | What it is |
| --- | --- |
| `M26_DA_A2_Part2.csv` | raw census dataset — not tracked, drop it here before running anything |
| `preprocessing.py` | cleans + label-encodes → `cleaned/census_encoded.csv` (not tracked — regenerate by running this) |
| `hierarchies/` | authored concept hierarchies (age, education) — the two with no natural roll-up column in the data |
| `Build_hierarchies.py` | builds all 6 hierarchy tables → `cleaned/hierarchies/` |
| `AOI.py` | attribute-oriented induction → `cleaned/aoi/` (characteristic/discriminant rules) |
| `BUC_in_memory.py` | in-memory BUC |
| `BUC_out_of_memory.py` | out-of-memory BUC — byte-budgeted, pages to disk |
| `verify_BUC_in.py`, `verify_BUC_out.py` | check both BUC versions against each other and against DuckDB `GROUP BY CUBE` → `cleaned/verification/` |
| `test_buc.py` | unit tests for BUC edge cases |
| `performance_analysis.py` | minsup / memory / dimension sweeps → `cleaned/performance/`, `report_assets/*.png` |
| `optimization.py` | dimension-reordering benchmark → `cleaned/optimization/`, `report_assets/optimization_benchmark.png` |
| `cleaned/aoi/`, `cleaned/hierarchies/`, `cleaned/verification/`, `cleaned/performance/`, `cleaned/optimization/` | generated outputs from the scripts above |
| `report_assets/` | plots used by `Report.md` |
| `Report.md` | Part 2 report |

## Setup

```powershell
# Run from the repository root (the folder containing this README).
python -m pip install -r requirements.txt
```

The programs expect raw inputs at `part1/M26_DA_A2_Part1/` and
`part2/M26_DA_A2_Part2.csv`. They have already been placed correctly in this
workspace. For a fresh checkout, copy the assignment data directly to those
two locations; no additional top-level data copy is required.

Confirm the two inputs before running either pipeline:

```powershell
Test-Path ".\part1\M26_DA_A2_Part1\orders.csv"
Test-Path ".\part2\M26_DA_A2_Part2.csv"
```

Both commands must print `True`.

## Reproducing Part 1

Run from the repository root. Remove only a previously generated warehouse
before requesting a complete rebuild; `run_pipeline.py` intentionally refuses
to overwrite one silently.

```powershell
Remove-Item -LiteralPath ".\part1\warehouse.duckdb" -ErrorAction SilentlyContinue
python part1/run_pipeline.py
```

This executes the preprocessing notebook, builds `part1/warehouse.duckdb`
from `create_schema.sql`, runs `q1.sql` through `q10.sql`, and saves each
result to `qN_result.csv`. Detailed output is captured in
`part1/validation_log.txt`. Geolocation normalization is the slowest step, so
allow it to finish even if its progress estimate fluctuates.

To load only after the notebook has already completed successfully, use:

```powershell
Set-Location ".\part1"
python etl_load.py
Set-Location ".."
```

The ER diagram (`report_assets/er_diagram.png`) is rendered from
`report_assets/er_diagram.puml` using [plantuml.com/plantuml](https://www.plantuml.com/plantuml).
If the schema changes, update the `.puml` file to match `create_schema.sql`,
paste it in, and re-export the PNG.

## Reproducing Part 2

Run from the repo root, in this order:

```powershell
python part2/preprocessing.py
python part2/Build_hierarchies.py
python part2/AOI.py
python part2/verify_BUC_in.py
python part2/verify_BUC_out.py
python part2/performance_analysis.py
python part2/optimization.py
```

For a short live demonstration, the following subset shows preprocessing,
hierarchy construction, AOI, edge-case tests, and an exact in-memory
comparison with DuckDB:

```powershell
python part2/preprocessing.py
python part2/Build_hierarchies.py
python part2/AOI.py
python part2/test_buc.py
python part2/verify_BUC_in.py
```

`verify_BUC_out.py`, `performance_analysis.py`, and `optimization.py` are full
benchmark runs and can take many minutes. During a short viva, show their
submitted CSV/JSON summaries and plots instead of rerunning them live.

`preprocessing.py` cleans and label-encodes the census data. `Build_hierarchies.py`
builds the concept hierarchy tables from the detailed/summary column pairs
already in the data, plus the authored age and education hierarchies. `AOI.py`
runs the generalization and writes the characteristic and discriminant rule
tables. `verify_BUC_in.py` and `verify_BUC_out.py` check the two BUC
implementations against each other and against a DuckDB `GROUP BY CUBE`
query. `performance_analysis.py` sweeps minsup, memory budget, and dimension
count and saves the three plots. `optimization.py` benchmarks the
dimension-reordering optimization against the unoptimized order.

The out-of-memory BUC (`BUC_out_of_memory.py`) takes a memory budget in
bytes, not rows - it stages the input to disk, sorts and merges in bounded
chunks, and never keeps more than one partition in memory at a time, so
partitions bigger than the budget spill to disk instead of blowing up RAM.

## Reading the reports

Open `Report.md` in either folder with the Markdown preview (Ctrl+Shift+V in
VS Code).
