"""
M26 Data Analytics 2 - Part 2 Preprocessing
=============================================
Prepares the census dataset (299,285 rows x 42 cols) for AOI and BUC.

Decisions made here, each tied to a profiling result:

1. NO deduplication. 6,735 rows are exact duplicates of another row, but with
   42 mostly-categorical low-cardinality columns, structurally similar people
   (e.g. infants: age=0, most fields "Not in universe") produce identical
   rows by chance. Each row = one census respondent, so dropping "duplicates"
   would mean discarding real people. (Contrast with Part 1, where a row was
   one order and duplicate payment/review rows DID need collapsing to avoid
   fact-table fan-out -- same instinct, opposite conclusion, because the
   grain differs.)

2. "?" and "Not in universe" are kept as-is. They are valid categorical
   values in census microdata (structural non-response / question doesn't
   apply), not nulls to impute -- same principle as preserving the 2,965
   NULL delivery dates in Part 1.

3. hispanic_origin has 1,279 TRUE NaN values (0.43% of rows), distinct from
   the existing "Do not know" category (446 rows). These are filled with an
   explicit "Not Reported" label rather than merged into "Do not know",
   since conflating "chose not to know" with "did not answer" would muddy
   AOI generalization for this attribute. This is the one genuine null-
   handling decision in this dataset.

4. instance_weight is excluded from the dimension set (per assignment
   instruction) but is KEPT in the output as a candidate secondary measure
   (SUM(instance_weight) = population-weighted count), since that is the
   textbook use of a census sampling weight.

5. Categorical dimensions are label-encoded to small integers for the
   array-based BUC implementation. The encoding map is saved separately so
   results can be decoded back to readable labels, and so the concept
   hierarchy tables (next step) can join against the same codes.
"""

import pandas as pd
import numpy as np
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_PATH = os.path.join(BASE_DIR, "M26_DA_A2_Part2.csv")
OUT_DIR = os.path.join(BASE_DIR, "cleaned")
os.makedirs(OUT_DIR, exist_ok=True)

# The 15 dimensions selected and justified in the previous step.
# NOTE: industry_code_major / occupation_code_major / household_summary /
# region_prev_residence are the dimensions actually used in the cube.
# Their DETAILED counterparts are kept alongside (see DETAIL_PAIRS below)
# purely to validate the concept-hierarchy roll-up logic against ground
# truth -- they are NOT additional cube dimensions.
DIMENSIONS = [
    "age", "education", "class_of_worker", "marital_status", "race", "sex",
    "hispanic_origin", "industry_code_major", "occupation_code_major",
    "household_summary", "region_prev_residence", "tax_filer_status",
    "citizenship", "employment_status", "year",
]

# detailed <-> major/summary pairs kept for hierarchy validation only
DETAIL_PAIRS = {
    "industry_code_major": "industry_code_detailed",
    "occupation_code_major": "occupation_code_detailed",
    "household_summary": "household_family_status",
    "region_prev_residence": "state_prev_residence",
}

LABEL_COL = "income"
WEIGHT_COL = "instance_weight"

KEEP_COLS = DIMENSIONS + list(DETAIL_PAIRS.values()) + [LABEL_COL, WEIGHT_COL]


def load_raw():
    df = pd.read_csv(RAW_PATH)
    assert len(df) == 299285, f"expected 299285 rows, got {len(df)}"
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)

    # Decision 1: no dedup - assert we are not silently dropping anything
    df = df.copy()

    # Decision 3: fill the one column with true nulls
    n_null = df["hispanic_origin"].isnull().sum()
    df["hispanic_origin"] = df["hispanic_origin"].fillna("Not Reported")
    assert df["hispanic_origin"].isnull().sum() == 0

    # subset to the columns we actually need going forward
    df = df[KEEP_COLS].copy()

    after = len(df)
    assert before == after, "row count changed during cleaning - not allowed"
    print(f"[clean] rows preserved: {after} (unchanged)")
    print(f"[clean] hispanic_origin: filled {n_null} true-NaN rows with 'Not Reported'")
    return df


def encode_categoricals(df: pd.DataFrame):
    """
    Label-encode every categorical column in KEEP_COLS (dimensions +
    detail-pair columns). Numeric columns (age, year) and the measure
    columns (income, instance_weight) are left as-is; income is mapped to
    a 0/1 flag separately since AOI/BUC need the class as a clean binary.
    """
    encoded = df.copy()
    mappings = {}

    categorical_cols = [
        c for c in KEEP_COLS
        if c not in ("age", "year", WEIGHT_COL, LABEL_COL)
    ]

    for col in categorical_cols:
        categories = sorted(df[col].dropna().unique().tolist())
        code_map = {cat: i for i, cat in enumerate(categories)}
        encoded[col + "_code"] = df[col].map(code_map)
        mappings[col] = code_map

    # binary target: 1 = ">50K", 0 = "<=50K"
    encoded["income_flag"] = (df[LABEL_COL].str.strip() == ">50K").astype(int)

    return encoded, mappings


def validate(df_raw: pd.DataFrame, df_encoded: pd.DataFrame, mappings: dict):
    # every code column should have no NaNs (i.e. every raw value had a mapping)
    for col in mappings:
        code_col = col + "_code"
        n_missing = df_encoded[code_col].isnull().sum()
        assert n_missing == 0, f"{col}: {n_missing} unmapped values"

    # cardinality sanity check: number of codes should equal nunique in raw data
    for col, code_map in mappings.items():
        assert len(code_map) == df_raw[col].nunique(), f"{col}: code map size mismatch"

    # class balance should match what we profiled earlier
    pos = df_encoded["income_flag"].sum()
    print(f"[validate] income_flag positive class: {pos} ({pos/len(df_encoded)*100:.2f}%)")
    assert pos == 18568, f"expected 18568 positive rows, got {pos}"

    print("[validate] all checks passed")


def main():
    df_raw = load_raw()
    df_clean = clean(df_raw)
    df_encoded, mappings = encode_categoricals(df_clean)
    validate(df_clean, df_encoded, mappings)

    # Save the encoded dataset (this is what AOI / BUC will actually load)
    out_path = os.path.join(OUT_DIR, "census_encoded.csv")
    df_encoded.to_csv(out_path, index=False)
    print(f"[save] {out_path} ({len(df_encoded)} rows, {len(df_encoded.columns)} cols)")

    # Save the encoding maps (needed to decode results + build hierarchies)
    maps_path = os.path.join(OUT_DIR, "category_encodings.json")
    with open(maps_path, "w") as f:
        json.dump(mappings, f, indent=2)
    print(f"[save] {maps_path} ({len(mappings)} columns encoded)")

    # Small summary table: column, #categories, role
    summary_rows = []
    for col in DIMENSIONS:
        role = "dimension"
        n_cat = df_encoded[col + "_code"].nunique() if col in mappings else df_encoded[col].nunique()
        summary_rows.append({"column": col, "role": role, "n_categories": n_cat})
    for major, detailed in DETAIL_PAIRS.items():
        summary_rows.append({"column": detailed, "role": f"hierarchy-check for {major}", "n_categories": df_encoded[detailed].nunique()})
    summary = pd.DataFrame(summary_rows)
    summary_path = os.path.join(OUT_DIR, "dimension_summary.csv")
    summary.to_csv(summary_path, index=False)
    print(f"[save] {summary_path}")
    print()
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
