# Part 2 — Attribute-Oriented Induction and Bottom-Up Cube

Part 2 processes 299,285 US census records, extracts AOI rules and computes iceberg cubes using independent in-memory and byte-budgeted out-of-memory BUC implementations.

[Return to the project README](../README.md) · [Read the full Part 2 report](Report.md)

## Pipeline

```text
Raw census CSV
    ↓
preprocessing.py
    ↓
Build_hierarchies.py
    ├── AOI.py
    └── BUC implementations
            ↓
       verification
            ↓
       performance analysis and optimization
```

## Main components

| File | Purpose |
| --- | --- |
| `preprocessing.py` | Cleans data, selects dimensions and creates integer encodings |
| `Build_hierarchies.py` | Builds and validates six concept hierarchies |
| `AOI.py` | Performs two-threshold AOI and calculates t-weights/d-weights |
| `BUC_in_memory.py` | NumPy implementation of BUC with manual partitioning |
| `BUC_out_of_memory.py` | External-memory BUC with a byte-valued workspace budget |
| `test_buc.py` | Synthetic regression and edge-case tests |
| `verify_BUC_in.py` | Compares in-memory BUC with DuckDB |
| `verify_BUC_out.py` | Compares both BUC versions with DuckDB and saves evidence |
| `performance_analysis.py` | Benchmarks minsup, memory and dimension count |
| `optimization.py` | Benchmarks descending-cardinality dimension ordering |

## Input data

Place the raw census file at:

```text
part2/M26_DA_A2_Part2.csv
```

It is ignored by Git because it exceeds GitHub's normal per-file limit.

## Run the core workflow

From the repository root:

```powershell
python part2/preprocessing.py
python part2/Build_hierarchies.py
python part2/AOI.py
python part2/test_buc.py
python part2/verify_BUC_in.py
```

## Run the complete experiments

```powershell
python part2/verify_BUC_out.py
python part2/performance_analysis.py
python part2/optimization.py
```

These jobs are intentionally expensive. The 12-dimensional paged verification took about 15 minutes on the machine used for the submitted measurements, while the repeated benchmark sweeps take longer.

## Generated outputs

| Location | Contents |
| --- | --- |
| `cleaned/aoi/` | Generalized relation and top characteristic/discriminant rules |
| `cleaned/hierarchies/` | Runtime hierarchy tables and documented mapping exceptions |
| `cleaned/verification/` | Cube outputs plus CSV/JSON verification summaries |
| `cleaned/performance/` | Every timing run and median/min/max summaries |
| `cleaned/optimization/` | Original-versus-optimized benchmark data |
| `report_assets/` | Performance and optimization plots |

The large reproducible intermediate `cleaned/census_encoded.csv` is ignored by Git; compact evidence tables and plots remain in the repository.

## Key results

- AOI reduced 299,285 records to 328 generalized tuples.
- Education showed the clearest high-income discrimination trend.
- In-memory BUC, paged BUC and DuckDB matched exactly.
- The 12-dimensional verification returned 1,619 supported cells.
- Increasing memory from 512 KiB to 16 MiB reduced paged runtime from 35.7 seconds to 7.1 seconds in the four-dimensional benchmark.
- Dimension reordering provided 1.62× in-memory and 3.05× paged speedups.

## Implementation constraints

- No database engine or DataFrame `groupby` computes the cube.
- Pruning is valid for COUNT and non-negative additive measures.
- The external-memory budget covers algorithm buffers and arrays, not the Python interpreter or operating-system file cache.
- DuckDB is used only as an independent reference implementation.

