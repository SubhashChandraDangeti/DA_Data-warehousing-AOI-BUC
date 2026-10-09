"""
M26 Data Analytics 2 - Part 2: Attribute-Oriented Induction (AOI)
====================================================================
Classic two-threshold AOI (Han, Kamber & Pei):

  attribute generalization threshold (per attribute) - if an attribute
  still has more distinct values than its threshold, generalize it one
  level up its concept hierarchy (or remove it if no hierarchy exists,
  or if it has already been generalized to the hierarchy's root "ANY").

  relation generalization threshold (whole table) - after every attribute
  individually satisfies its threshold, if the merged generalized relation
  still has more distinct tuples than this threshold, the attribute with
  the most remaining distinct values is generalized/removed further, and
  tuples are re-merged. Repeats until the relation is small enough.

DESIGN NOTE - attribute set for AOI vs. BUC:
For the four hierarchies derived from real detailed/summary pairs
(industry, occupation, household, geography), AOI uses the DETAILED-level
column (e.g. industry_code_detailed, 52 values) rather than the
major/summary column used as the BUC cube dimension. This lets AOI
actually walk the full 3-level hierarchy (detailed -> major -> ANY) built
and validated earlier, instead of starting one level up and only having a
trivial "collapse to ANY" step available. age/education use the same
column as BUC since their hierarchy already starts at the finest level.

Weights:
  t-weight (characteristic rule, target = income >50K):
      count_target_in_tuple / total_target_count  (x100%)
      "what % of the >50K population looks like this"
  d-weight (discriminant rule, target vs contrasting <=50K):
      count_target_in_tuple / (count_target_in_tuple + count_contrast_in_tuple)  (x100%)
      "of people who look like this, what % are >50K"
"""

import pandas as pd
import numpy as np
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "cleaned", "census_encoded.csv")
HIER_DIR = os.path.join(BASE_DIR, "cleaned", "hierarchies")
OUT_DIR = os.path.join(BASE_DIR, "cleaned", "aoi")
DEFINITION_PATH = os.path.join(BASE_DIR, "hierarchies", "hierarchy_definitions.json")
os.makedirs(OUT_DIR, exist_ok=True)

with open(DEFINITION_PATH, encoding="utf-8") as file:
    HIERARCHY_DEFINITIONS = json.load(file)["hierarchies"]

# Hierarchy-backed attribute configuration is loaded from submitted data.
AOI_ATTRIBUTES = {
    name: (definition["level0_column"], name)
    for name, definition in HIERARCHY_DEFINITIONS.items()
}
AOI_ATTRIBUTES.update({
    "class_of_worker": ("class_of_worker", None),
    "marital_status": ("marital_status", None),
    "race": ("race", None),
    "sex": ("sex", None),
    "tax_filer_status": ("tax_filer_status", None),
    "citizenship": ("citizenship", None),
    "employment_status": ("employment_status", None),
})

ATTR_THRESHOLD_DEFAULT = 5
ATTR_THRESHOLD_OVERRIDE = {"age": 7, "education": 7}
RELATION_THRESHOLD = 350


def load_hierarchy(name):
    path = os.path.join(HIER_DIR, f"{name}_hierarchy.csv")
    table = pd.read_csv(path, dtype=str)
    level0_to_level1 = dict(zip(table["level0_value"], table["level1_value"]))
    return level0_to_level1


def generalize_column(df, attr_name, source_col, hierarchy_name, threshold, log):
    """Returns the generalized pandas Series, or None if the attribute
    should be removed. `log` accumulates a human-readable trace."""
    series = df[source_col].astype(str)
    level = 0

    if series.nunique() <= threshold:
        log.append(f"{attr_name}: kept as-is ({series.nunique()} values, within threshold {threshold})")
        return series, 0

    if hierarchy_name is None:
        log.append(f"{attr_name}: REMOVED (no hierarchy, {series.nunique()} values > threshold {threshold})")
        return None, 0

    # level 1: apply the detailed -> major/summary/band/tier map
    mapping = load_hierarchy(hierarchy_name)
    series = series.map(mapping)
    if series.isna().any():
        raise ValueError(f'{attr_name}: hierarchy does not cover every source value')
    level = 1
    if series.nunique() <= threshold:
        log.append(f"{attr_name}: generalized to level1 ({series.nunique()} values, within threshold {threshold})")
        return series, 1

    # level 2: collapse to the universal root
    series = pd.Series(["ANY"] * len(series), index=series.index)
    log.append(f"{attr_name}: generalized to level2 = ANY (was still > threshold {threshold} at level1)")
    return series, 2


def build_generalized_relation(df):
    log = []
    generalized = {}
    current_level = {}  # attr -> 0/1/2, tracks how far we've generalized (for relation-threshold step)

    for attr, (col, hier) in AOI_ATTRIBUTES.items():
        thr = ATTR_THRESHOLD_OVERRIDE.get(attr, ATTR_THRESHOLD_DEFAULT)
        result, level = generalize_column(df, attr, col, hier, thr, log)
        if result is not None:
            generalized[attr] = result
            current_level[attr] = level

    gdf = pd.DataFrame(generalized)
    gdf["income_flag"] = df["income_flag"].values

    # relation-threshold pass: if still too many distinct tuples, keep
    # generalizing/removing the attribute with the most distinct values
    attr_cols = [c for c in gdf.columns if c != "income_flag"]
    n_tuples = gdf[attr_cols].drop_duplicates().shape[0]
    log.append(f"After per-attribute generalization: {len(attr_cols)} attributes kept, {n_tuples} distinct tuples")

    while n_tuples > RELATION_THRESHOLD and attr_cols:
        nunique_per_attr = {c: gdf[c].nunique() for c in attr_cols}
        worst = max(nunique_per_attr, key=nunique_per_attr.get)
        hier = AOI_ATTRIBUTES[worst][1]
        lvl = current_level.get(worst, 0)

        if hier and lvl == 0:
            mapping = load_hierarchy(hier)
            gdf[worst] = gdf[worst].astype(str).map(mapping)
            if gdf[worst].isna().any():
                raise ValueError(f'{worst}: incomplete hierarchy mapping')
            current_level[worst] = 1
            log.append(f"[relation-threshold] generalized '{worst}' to level1 ({gdf[worst].nunique()} values)")
        elif hier and lvl == 1:
            gdf[worst] = "ANY"
            current_level[worst] = 2
            log.append(f"[relation-threshold] generalized '{worst}' to ANY")
        else:
            gdf = gdf.drop(columns=[worst])
            attr_cols.remove(worst)
            log.append(f"[relation-threshold] removed '{worst}' (no further generalization available)")

        n_tuples = gdf[attr_cols].drop_duplicates().shape[0]

    log.append(f"Final generalized relation: {len(attr_cols)} attributes, {n_tuples} distinct tuples")
    return gdf, attr_cols, log


def compute_weights(gdf, attr_cols):
    total_target = int((gdf["income_flag"] == 1).sum())
    total_contrast = int((gdf["income_flag"] == 0).sum())
    if total_target == 0 or total_contrast == 0:
        raise ValueError('Both target and contrasting classes must be present')

    grouped = gdf.groupby(attr_cols)["income_flag"].agg(
        count_target=lambda s: (s == 1).sum(),
        count_contrast=lambda s: (s == 0).sum(),
    ).reset_index()

    grouped["t_weight_pct"] = (grouped["count_target"] / total_target * 100).round(2)
    grouped["d_weight_pct"] = (
        grouped["count_target"] / (grouped["count_target"] + grouped["count_contrast"]) * 100
    ).round(2)
    grouped["total_count"] = grouped["count_target"] + grouped["count_contrast"]
    assert int(grouped['total_count'].sum()) == len(gdf)

    return grouped, total_target, total_contrast


def main():
    df = pd.read_csv(DATA_PATH)
    gdf, attr_cols, log = build_generalized_relation(df)

    print("=== Generalization trace ===")
    for line in log:
        print(" ", line)
    print()

    rules, total_target, total_contrast = compute_weights(gdf, attr_cols)
    print(f"Target class (income>50K): {total_target} rows")
    print(f"Contrasting class (income<=50K): {total_contrast} rows")
    print(f"Generalized relation: {len(rules)} rows, columns = {attr_cols}")

    rules_path = os.path.join(OUT_DIR, "generalized_relation_weights.csv")
    rules.to_csv(rules_path, index=False)
    print(f"[save] {rules_path}")

    # Characteristic rules: top tuples by t-weight (biggest share of the target class)
    characteristic = rules.sort_values("t_weight_pct", ascending=False).head(10)
    char_path = os.path.join(OUT_DIR, "characteristic_rules_top10.csv")
    characteristic.to_csv(char_path, index=False)
    print(f"[save] {char_path}")

    # Discriminant rules: tuples with a meaningful sample size (>=30) and
    # high d-weight (strongly indicative of the target class)
    discriminant = rules[rules["total_count"] >= 30].sort_values("d_weight_pct", ascending=False).head(10)
    disc_path = os.path.join(OUT_DIR, "discriminant_rules_top10.csv")
    discriminant.to_csv(disc_path, index=False)
    print(f"[save] {disc_path}")

    with open(os.path.join(OUT_DIR, "generalization_log.json"), "w") as f:
        json.dump(log, f, indent=2)

    print()
    print("=== Top 5 characteristic rules (income > $50K) ===")
    print(characteristic.head(5).to_string(index=False))
    print()
    print("=== Top 5 discriminant rules (income > $50K vs <= $50K, min 30 records) ===")
    print(discriminant.head(5).to_string(index=False))


if __name__ == "__main__":
    main()
