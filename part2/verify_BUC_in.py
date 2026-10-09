"""Verify the in-memory BUC iceberg cube against DuckDB GROUP BY CUBE.

DuckDB is used only as a reference implementation in this verification
harness. The BUC computation itself never calls a database or DataFrame
groupby.
"""

import os

import duckdb
import pandas as pd

from BUC_in_memory import run_buc_in_memory


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "cleaned", "census_encoded.csv")


def to_cellset(result, dim_cols, measure_name):
    cells = set()
    for _, row in result.iterrows():
        key = tuple(row[c] for c in dim_cols)
        cells.add((key, round(float(row[measure_name]), 6)))
    return cells


def verify(df, dim_cols, measure_col, minsup):
    measure_name = "count" if measure_col == "COUNT" else measure_col
    ours, stats = run_buc_in_memory(df, dim_cols, measure_col, minsup)
    ours_set = to_cellset(ours, dim_cols, measure_name)

    # Prevent a false-positive comparison that filters invalid cells only in
    # the verifier instead of requiring the implementation to omit them.
    below_support = ours[ours[measure_name] < minsup]
    assert below_support.empty, (
        f"BUC returned {len(below_support)} cells below minsup={minsup}"
    )

    aggregate_sql = "COUNT(*)" if measure_col == "COUNT" else f"SUM({measure_col})"
    con = duckdb.connect()
    try:
        con.register("t", df)
        sql = f"""
            SELECT {", ".join(dim_cols)}, {aggregate_sql} AS aggregate_value
            FROM t
            GROUP BY CUBE({", ".join(dim_cols)})
            HAVING {aggregate_sql} >= {minsup}
        """
        reference = con.execute(sql).df()
    finally:
        con.close()

    reference_set = set()
    for _, row in reference.iterrows():
        key = tuple(
            "ALL" if pd.isnull(row[c]) else int(row[c]) for c in dim_cols
        )
        reference_set.add((key, round(float(row["aggregate_value"]), 6)))

    missing = reference_set - ours_set
    extra = ours_set - reference_set
    print(
        f"dims={len(dim_cols)} measure={measure_col} minsup={minsup}: "
        f"ours={len(ours_set)}, DuckDB={len(reference_set)}"
    )
    if missing or extra:
        raise AssertionError(
            f"mismatch: {len(missing)} missing and {len(extra)} extra cells"
        )
    print("  MATCH: exact iceberg cube; no below-support cells returned")
    return stats


def main():
    df = pd.read_csv(DATA_PATH)
    configurations = [
        (["sex_code", "race_code", "citizenship_code", "marital_status_code"],
         "COUNT", 1_000),
        (["sex_code", "race_code", "citizenship_code", "marital_status_code",
          "tax_filer_status_code", "employment_status_code"], "COUNT", 500),
        (["sex_code", "race_code", "citizenship_code"],
         "instance_weight", 5_000_000),
    ]
    for dim_cols, measure_col, minsup in configurations:
        verify(df, dim_cols, measure_col, minsup)
    print("\n=== ALL DUCKDB VERIFICATION TESTS PASSED ===")


if __name__ == "__main__":
    main()
