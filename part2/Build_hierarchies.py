"""Build six AOI concept hierarchies from submitted data definitions.

The hierarchy definitions and authored mappings live in ``hierarchies/``;
they are data files, not Python conditionals. Four hierarchies are validated
and derived from detailed/summary column pairs already present in the census
data. Age and education use submitted mapping CSVs. Runtime-normalized tables
are written to ``cleaned/hierarchies/`` for AOI.
"""

import json
import os

import pandas as pd


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IN_PATH = os.path.join(BASE_DIR, "cleaned", "census_encoded.csv")
OUT_DIR = os.path.join(BASE_DIR, "cleaned", "hierarchies")
SOURCE_HIER_DIR = os.path.join(BASE_DIR, "hierarchies")
DEFINITION_PATH = os.path.join(SOURCE_HIER_DIR, "hierarchy_definitions.json")

os.makedirs(OUT_DIR, exist_ok=True)
df = pd.read_csv(IN_PATH)
with open(DEFINITION_PATH, encoding="utf-8") as file:
    hierarchy_definitions = json.load(file)["hierarchies"]

hierarchy_index = {}
exception_log = []


def build_derived_hierarchy(name, definition):
    """Create a detailed-to-summary table and record non-functional pairs.

    If a detailed value maps to several summaries, use its majority summary
    while preserving the observed alternatives in hierarchy_exceptions.json.
    """
    detailed_col = definition["level0_column"]
    summary_col = definition["level1_column"]
    grouped = df.groupby(detailed_col)[summary_col]
    majority = grouped.agg(lambda series: series.value_counts().idxmax())
    violations = grouped.nunique()
    violations = violations[violations > 1]

    for detailed_value in violations.index:
        counts = (
            df[df[detailed_col] == detailed_value][summary_col]
            .value_counts()
            .to_dict()
        )
        exception_log.append({
            "hierarchy": name,
            "detailed_value": str(detailed_value),
            "summary_value_counts": {
                str(key): int(value) for key, value in counts.items()
            },
            "resolution": str(majority[detailed_value]),
        })

    table = majority.reset_index()
    table.columns = ["level0_value", "level1_value"]
    table["level2_value"] = definition["root"]
    out_path = os.path.join(OUT_DIR, f"{name}_hierarchy.csv")
    table.to_csv(out_path, index=False)

    hierarchy_index[name] = {
        "dimension_column": detailed_col,
        "levels": definition["levels"],
        "source": definition["source"],
        "n_violations": int(len(violations)),
        "file": os.path.relpath(out_path, BASE_DIR),
    }
    print(
        f"[{name}] {len(table)} detailed values -> "
        f"{table['level1_value'].nunique()} summary values "
        f"({len(violations)} inconsistent, resolved via majority)"
    )


def build_authored_hierarchy(name, definition):
    """Validate and copy a submitted mapping table into the runtime folder."""
    source_path = os.path.join(SOURCE_HIER_DIR, definition["mapping_file"])
    table = pd.read_csv(source_path, dtype=str)
    expected = {"level0_value", "level1_value", "level2_value"}
    if set(table.columns) != expected:
        raise ValueError(f"{source_path} must contain {sorted(expected)}")

    source_col = definition["level0_column"]
    actual_values = set(df[source_col].astype(str).unique())
    mapped_values = set(table["level0_value"])
    assert actual_values == mapped_values, (
        f"{name} mapping mismatch: {actual_values.symmetric_difference(mapped_values)}"
    )
    assert set(table["level2_value"]) == {definition["root"]}

    out_path = os.path.join(OUT_DIR, f"{name}_hierarchy.csv")
    table.to_csv(out_path, index=False)
    hierarchy_index[name] = {
        "dimension_column": source_col,
        "levels": definition["levels"],
        "source": definition["source"],
        "n_violations": 0,
        "file": os.path.relpath(out_path, BASE_DIR),
    }
    print(
        f"[{name}] {len(table)} detailed values -> "
        f"{table['level1_value'].nunique()} generalized values"
    )


def main():
    for name, definition in hierarchy_definitions.items():
        if definition["kind"] == "derived_pair":
            build_derived_hierarchy(name, definition)
        elif definition["kind"] == "mapping_file":
            build_authored_hierarchy(name, definition)
        else:
            raise ValueError(
                f"Unsupported hierarchy kind for {name}: {definition['kind']}"
            )

    index_path = os.path.join(OUT_DIR, "hierarchy_index.json")
    with open(index_path, "w", encoding="utf-8") as file:
        json.dump(hierarchy_index, file, indent=2)
    print(f"\n[save] {index_path} ({len(hierarchy_index)} hierarchies registered)")

    exception_path = os.path.join(OUT_DIR, "hierarchy_exceptions.json")
    with open(exception_path, "w", encoding="utf-8") as file:
        json.dump(exception_log, file, indent=2)
    print(f"[save] {exception_path} ({len(exception_log)} exceptions documented)")


if __name__ == "__main__":
    main()
