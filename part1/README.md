# Part 1 — DuckDB Snowflake Data Warehouse

Part 1 builds a DuckDB analytical warehouse over Brazilian marketplace data. It covers preprocessing, snowflake-schema design, dimension-first ETL, validation and ten OLAP queries.

[Return to the project README](../README.md) · [Read the full Part 1 report](Report.md)

## Architecture

The fact-table grain is **one row per order item**. Revenue is defined as:

```text
revenue = price + freight_value
```

Normalized hierarchies include:

- Geography: zip-code prefix → city → state → region
- Product: product → translated category
- Seller: seller → acquisition details

![Snowflake schema](report_assets/er_diagram.png)

## Important files

| File | Purpose |
| --- | --- |
| `preprocessing.ipynb` | Profiles and cleans all raw CSV files |
| `seed/state_region_mapping.csv` | Authored Brazilian state-to-region mapping |
| `create_schema.sql` | Creates the DuckDB snowflake schema |
| `etl_load.py` | Loads dimensions top-down and then loads the fact table |
| `run_pipeline.py` | Runs preprocessing, ETL, validation and all ten queries |
| `q1.sql` … `q10.sql` | OLAP queries using roll-up, drill-down, CUBE and related operations |
| `q1_result.csv` … `q10_result.csv` | Saved query results |
| `validation_log.txt` | Detailed preprocessing/ETL validation output |
| `validation_summary.json` | Machine-readable validation counts |
| `Report.md` | Methodology and analytical findings |

## Input data

Place the eleven raw CSV files under:

```text
part1/M26_DA_A2_Part1/
```

The folder is ignored by Git. From the repository root, confirm the main file exists:

```powershell
Test-Path ".\part1\M26_DA_A2_Part1\orders.csv"
```

## Run the complete pipeline

Run from the repository root:

```powershell
Remove-Item -LiteralPath ".\part1\warehouse.duckdb" -ErrorAction SilentlyContinue
python part1/run_pipeline.py
```

The runner executes preprocessing, creates and loads the warehouse, validates row preservation and foreign keys, and regenerates all ten query results. Geolocation normalization is the slowest stage; allow it to finish even if DuckDB's progress estimate fluctuates.

## Run ETL only

Use this only after the notebook has created every file in `part1/cleaned/`:

```powershell
Set-Location ".\part1"
python etl_load.py
Set-Location ".."
```

## Validation

The pipeline checks:

- Fact row count equals the cleaned order-item row count.
- Product, seller and customer foreign keys have no orphans.
- Orders without reviews, payments or delivery timestamps remain present.
- Query outputs are regenerated from the warehouse.

After a successful run:

```powershell
Get-Content ".\part1\validation_log.txt"
Get-Content ".\part1\validation_summary.json"
```

