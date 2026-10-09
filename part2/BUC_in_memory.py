"""
M26 Data Analytics 2 - Part 2: BUC Algorithm (In-Memory)
===========================================================
Classic Beyer & Ramakrishnan (1999) Bottom-Up Cube.

No database engine or dataframe groupby for the cube computation itself --
the partitioning step, the actual heart of BUC, is implemented by hand with
numpy: sort the
current partition's row indices by the next dimension's values, then find
contiguous runs (boundaries where the value changes). This is exactly the
"Partition()" step described in the original BUC paper. pandas is only used
to LOAD the CSV; every dimension column is converted to a plain numpy int
array before the algorithm ever touches it.

Algorithm sketch:
  BUC(indices, dim_index, combo):
      agg = measure(indices)                      # e.g. COUNT
      if agg < minsup: return                      # Apriori-style prune:
                                                    # any further partition
                                                    # is a SUBSET of indices,
                                                    # so its count can only be
                                                    # <= agg (safe to cut)
      emit (combo, agg)                            # only supported cells belong
                                                    # to the iceberg cube
      if dim_index == n_dims: return
      for d in range(dim_index, n_dims):
          for value, sub_indices in partition(dim_arrays[d], indices):
              BUC(sub_indices, d + 1, combo with dim d set to value)

This produces the full CUBE (2^n_dims grouping combinations), restricted to
cells meeting minsup (the iceberg cube).
"""

import numpy as np
import pandas as pd
import os
import time

ALL_MARKER = -1  # sentinel for "this dimension is generalized to ALL"

# Need at least 12 dimensions for the compliance run. Ordered by broadly
# decreasing cardinality so the built-in BUC pruning is effective.
DEFAULT_DIMENSIONS_12 = [
    "age",
    "industry_code_major_code",
    "education_code",
    "occupation_code_major_code",
    "hispanic_origin_code",
    "class_of_worker_code",
    "household_summary_code",
    "employment_status_code",
    "marital_status_code",
    "region_prev_residence_code",
    "tax_filer_status_code",
    "race_code",
]


def partition(values, indices):
    """Manually group `indices` by `values[indices]`, without pandas
    groupby: sort the subset by value, then split on value-change
    boundaries. Returns a list of (value, indices_array) pairs."""
    if not len(indices):
        return []
    sub_vals = values[indices]
    order = np.argsort(sub_vals, kind="stable")
    sorted_idx = indices[order]
    sorted_vals = sub_vals[order]

    boundaries = np.nonzero(np.diff(sorted_vals))[0] + 1
    idx_groups = np.split(sorted_idx, boundaries)
    val_groups = np.split(sorted_vals, boundaries)

    return [(val_groups[i][0], idx_groups[i]) for i in range(len(idx_groups))]


class BUC:
    def __init__(self, dim_arrays, dim_names, measure_array, minsup):
        """
        dim_arrays: list of 1-D numpy int arrays, one per dimension, all
                    the same length as the dataset (aligned by row index)
        dim_names:  matching list of dimension names (for output only)
        measure_array: 1-D numpy array used to compute the aggregate.
                    Pass np.ones(n) for COUNT(*), or e.g. instance_weight
                    for a weighted-count measure. Must be non-negative for
                    the Apriori pruning to be valid (monotone under
                    subsetting).
        minsup:     minimum support threshold for the iceberg cube
        """
        self.dim_arrays = dim_arrays
        self.dim_names = dim_names
        self.n_dims = len(dim_names)
        self.measure_array = measure_array
        self.minsup = minsup
        self.output = []
        self.cells_examined = 0
        self.cells_pruned = 0

    def measure(self, indices):
        return self.measure_array[indices].sum()

    def run(self):
        n = len(self.measure_array)
        all_indices = np.arange(n)
        combo = [ALL_MARKER] * self.n_dims
        self._recurse(all_indices, 0, combo)
        return self.output

    def _recurse(self, indices, dim_index, combo):
        self.cells_examined += 1
        agg = self.measure(indices)

        if agg < self.minsup:
            self.cells_pruned += 1
            return  # Apriori prune: no descendant partition can exceed `agg`

        # The iceberg cube contains supported cells only.  Keeping this after
        # the threshold check is essential: emitting first would return a
        # superset of the DuckDB HAVING COUNT/SUM >= minsup result.
        self.output.append((tuple(combo), agg))

        if dim_index == self.n_dims:
            return

        for d in range(dim_index, self.n_dims):
            for value, sub_indices in partition(self.dim_arrays[d], indices):
                new_combo = combo.copy()
                new_combo[d] = value
                self._recurse(sub_indices, d + 1, new_combo)


def run_buc_in_memory(df, dim_cols, measure_col, minsup):
    """Convenience wrapper: takes a DataFrame, converts the requested
    columns to numpy arrays, runs BUC, returns a tidy result DataFrame."""
    if not dim_cols or len(set(dim_cols)) != len(dim_cols):
        raise ValueError("dim_cols must contain at least one dimension")
    if not np.isfinite(minsup) or minsup < 0:
        raise ValueError("minsup must be non-negative")

    dim_arrays = [df[c].to_numpy() for c in dim_cols]
    for values in dim_arrays:
        if not np.issubdtype(values.dtype, np.integer) or np.any(values < 0):
            raise ValueError('Dimensions must be nonnegative integer codes')
    if measure_col == "COUNT":
        measure_array = np.ones(len(df))
        measure_name = "count"
    else:
        measure_array = df[measure_col].to_numpy(dtype=float)
        measure_name = measure_col
        if not np.isfinite(measure_array).all() or np.any(measure_array < 0):
            raise ValueError("BUC pruning requires a non-negative measure")

    start = time.perf_counter()
    buc = BUC(dim_arrays, dim_cols, measure_array, minsup)
    cells = buc.run()
    elapsed = time.perf_counter() - start

    rows = []
    for combo, agg in cells:
        row = {dim_cols[i]: (combo[i] if combo[i] != ALL_MARKER else "ALL") for i in range(len(dim_cols))}
        row[measure_name] = agg
        rows.append(row)

    result = pd.DataFrame(rows, columns=list(dim_cols) + [measure_name])
    stats = {
        "elapsed_sec": elapsed,
        "cells_examined": buc.cells_examined,
        "cells_pruned": buc.cells_pruned,
        "cells_output": len(cells),
    }
    return result, stats


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    df = pd.read_csv(os.path.join(base_dir, "cleaned", "census_encoded.csv"))

    # Compliance run: needs at least 12 dimensions. A high support keeps
    # this demonstration tractable while still exercising the complete
    # 12-dimensional cube lattice and pruning logic.
    dim_cols = DEFAULT_DIMENSIONS_12
    minsup = 50_000

    result, stats = run_buc_in_memory(df, dim_cols, "COUNT", minsup)
    print(f"BUC in-memory: {stats}")
    print(result.sort_values("count", ascending=False).head(10).to_string(index=False))
    result.to_csv(os.path.join(base_dir, "cleaned", "buc_12dim_output.csv"), index=False)
