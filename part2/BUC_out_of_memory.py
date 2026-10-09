"""External-memory BUC with a byte-valued working-memory budget.

CSV input is staged record by record; cube output is streamed to CSV. Large
partitions are sorted with bounded runs and TWO-way merge passes (no unbounded
merge heap). Only one child partition is processed at a time. Small subtrees
use a conservative depth-dependent allowance for NumPy sorting/copies.

The budget covers algorithm data buffers, not the Python interpreter, imported
libraries or OS file cache. The production entry point returns an output PATH,
not a DataFrame. Compatibility wrappers materialize results only after BUC has
finished, and are for verification/benchmark clients that already use pandas.
No database or DataFrame groupby is used in cube computation.
"""

import csv
import math
import os
from pathlib import Path
import struct
import tempfile
import time

import numpy as np

IO_BUFFER = 8192


class ExternalBUC:
    def __init__(self, dimensions, measure, minsup, memory_bytes, directory, writer):
        self.dimensions = list(dimensions)
        self.measure = measure
        self.minsup = minsup
        self.memory_bytes = int(memory_bytes)
        self.directory = Path(directory)
        self.writer = writer
        self.width = len(dimensions) + 1
        self.record = struct.Struct('<' + 'd' * self.width)
        self.row_bytes = self.record.size
        self.next_id = 0
        # At most one suspended grouped-file reader per BUC level; plus merge
        # readers/writer and output. Reserve metadata/record overhead too.
        self.io_reserve = (len(dimensions) + 8) * (IO_BUFFER + 2048)
        if self.memory_bytes < max(262144, 2 * self.io_reserve):
            raise ValueError('memory_bytes too small; use at least 512 KiB')
        self.array_allowance = self.memory_bytes - self.io_reserve
        self.run_rows = max(1, self.array_allowance // (8 * self.row_bytes))
        self.small_rows = max(1, self.array_allowance //
                              (8 * (len(dimensions) + 1) * self.row_bytes))
        self.stats = dict(cells_examined=0, cells_pruned=0, cells_output=0,
                          spill_files_written=0, merge_passes=0,
                          memory_budget_bytes=self.memory_bytes,
                          max_sort_run_rows=self.run_rows,
                          small_partition_rows=self.small_rows,
                          workspace_bound_bytes=self.io_reserve + max(
                              self.run_rows * self.row_bytes * 8,
                              self.small_rows * self.row_bytes * 8 * (len(dimensions)+1)))
        assert self.stats['workspace_bound_bytes'] <= self.memory_bytes

    def path(self):
        self.next_id += 1
        return self.directory / f'p{self.next_id}.bin'

    def stage(self, source):
        path = self.path()
        count, total = 0, 0.0
        with open(source, newline='', encoding='utf-8') as src, open(path, 'wb', buffering=IO_BUFFER) as dst:
            reader = csv.DictReader(src)
            for row in reader:
                values = [int(row[d]) for d in self.dimensions]
                if any(v < 0 or v >= 2**53 for v in values):
                    raise ValueError('Dimensions must be nonnegative integer codes below 2**53')
                weight = 1.0 if self.measure == 'COUNT' else float(row[self.measure])
                if not math.isfinite(weight) or weight < 0:
                    raise ValueError('Measure must be finite and nonnegative')
                dst.write(self.record.pack(*values, weight))
                count += 1
                total += weight
        return path, count, total

    def merge(self, left, right, target, dimension):
        with open(left, 'rb', buffering=IO_BUFFER) as a, open(right, 'rb', buffering=IO_BUFFER) as b, open(target, 'wb', buffering=IO_BUFFER) as out:
            x, y = a.read(self.row_bytes), b.read(self.row_bytes)
            while x and y:
                if self.record.unpack(x)[dimension] <= self.record.unpack(y)[dimension]:
                    out.write(x)
                    x = a.read(self.row_bytes)
                else:
                    out.write(y)
                    y = b.read(self.row_bytes)
            while x:
                out.write(x)
                x = a.read(self.row_bytes)
            while y:
                out.write(y)
                y = b.read(self.row_bytes)

    def sorted_file(self, source, dimension):
        # Run names are predictable: no Python list proportional to run count.
        token = self.next_id
        self.next_id += 1
        count = 0
        with open(source, 'rb', buffering=0) as src:
            while True:
                rows = np.fromfile(src, dtype='<f8', count=self.run_rows*self.width)
                if not rows.size:
                    break
                rows = rows.reshape(-1, self.width)
                order = np.argsort(rows[:, dimension], kind='quicksort')
                ordered = rows[order]
                path = self.directory / f's{token}_0_{count}.bin'
                ordered.tofile(path)
                self.stats['spill_files_written'] += 1
                count += 1
                del rows, order, ordered
        level = 0
        while count > 1:
            for i in range(0, count, 2):
                a = self.directory / f's{token}_{level}_{i}.bin'
                target = self.directory / f's{token}_{level+1}_{i//2}.bin'
                if i+1 == count:
                    a.rename(target)
                else:
                    b = self.directory / f's{token}_{level}_{i+1}.bin'
                    self.merge(a, b, target, dimension)
                    a.unlink()
                    b.unlink()
                    self.stats['spill_files_written'] += 1
            count = (count+1)//2
            level += 1
            self.stats['merge_passes'] += 1
        return self.directory / f's{token}_{level}_0.bin'

    def children(self, source, dimension):
        ordered = self.sorted_file(source, dimension)
        try:
            with open(ordered, 'rb', buffering=IO_BUFFER) as src:
                pending = src.read(self.row_bytes)
                while pending:
                    value = int(self.record.unpack(pending)[dimension])
                    child = self.path()
                    count, total = 0, 0.0
                    with open(child, 'wb', buffering=IO_BUFFER) as out:
                        while pending and int(self.record.unpack(pending)[dimension]) == value:
                            total += self.record.unpack(pending)[-1]
                            count += 1
                            out.write(pending)
                            pending = src.read(self.row_bytes)
                    self.stats['spill_files_written'] += 1
                    try:
                        yield value, child, count, total
                    finally:
                        child.unlink(missing_ok=True)
        finally:
            ordered.unlink(missing_ok=True)

    def supported(self, combo, total):
        self.stats['cells_examined'] += 1
        if total < self.minsup:
            self.stats['cells_pruned'] += 1
            return False
        self.writer.writerow([*combo, total])
        self.stats['cells_output'] += 1
        return True

    def in_memory(self, rows, start, combo):
        total = float(rows[:, -1].sum())
        if not self.supported(combo, total) or not len(rows):
            return
        for d in range(start, len(self.dimensions)):
            order = np.argsort(rows[:, d], kind='quicksort')
            ordered = rows[order]
            del order
            boundaries = np.flatnonzero(np.diff(ordered[:, d])) + 1
            lo = 0
            for hi in (*boundaries, len(ordered)):
                child_combo = combo.copy()
                child_combo[d] = int(ordered[lo, d])
                self.in_memory(ordered[lo:hi], d+1, child_combo)
                lo = hi
            del ordered, boundaries

    def recurse(self, source, count, total, start, combo):
        if count <= self.small_rows:
            rows = np.fromfile(source, dtype='<f8').reshape(-1, self.width)
            self.in_memory(rows, start, combo)
            return
        if not self.supported(combo, total):
            return
        for d in range(start, len(self.dimensions)):
            for value, path, n, weight in self.children(source, d):
                child_combo = combo.copy()
                child_combo[d] = value
                self.recurse(path, n, weight, d+1, child_combo)


def run_buc_to_csv(csv_path, dim_cols, measure_col, minsup, memory_bytes,
                   output_path):
    """Production API: return (output Path, stats) without materializing cube.

    ``memory_bytes`` is the explicit algorithm workspace budget. Staging time
    is reported separately from BUC time; both input and output are streamed.
    """
    if not dim_cols or len(set(dim_cols)) != len(dim_cols):
        raise ValueError('Provide distinct dimension names')
    if not math.isfinite(minsup) or minsup < 0:
        raise ValueError('minsup must be finite and nonnegative')
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    measure_name = 'count' if measure_col == 'COUNT' else measure_col
    with tempfile.TemporaryDirectory(prefix='buc_') as directory:
        with open(output_path, 'w', newline='', encoding='utf-8', buffering=IO_BUFFER) as dst:
            writer = csv.writer(dst)
            writer.writerow([*dim_cols, measure_name])
            algorithm = ExternalBUC(dim_cols, measure_col, minsup, memory_bytes, directory, writer)
            start = time.perf_counter()
            source, n, total = algorithm.stage(csv_path)
            staging = time.perf_counter()-start
            start = time.perf_counter()
            algorithm.recurse(source, n, total, 0, ['ALL']*len(dim_cols))
            stats = algorithm.stats | dict(elapsed_sec=time.perf_counter()-start,
                                           staging_sec=staging, input_rows=n)
    return output_path, stats


def run_buc_out_of_memory_csv(csv_path, dim_cols, measure_col, minsup, memory_budget):
    """Verification convenience API; memory_budget is now BYTES, not rows.

    Reading the finished result as a DataFrame is outside the BUC budget.
    Use run_buc_to_csv for production external-memory execution.
    """
    import pandas as pd
    with tempfile.TemporaryDirectory(prefix='buc_result_') as directory:
        path, stats = run_buc_to_csv(csv_path, dim_cols, measure_col, minsup,
                                     memory_budget, Path(directory)/'cube.csv')
        result = pd.read_csv(path, dtype={d: str for d in dim_cols})
        for d in dim_cols:
            result[d] = result[d].map(lambda v: 'ALL' if v == 'ALL' else int(v))
        return result, stats


def run_buc_out_of_memory(df, dim_cols, measure_col, minsup, memory_budget):
    """Compatibility API for clients that already hold the input in RAM."""
    with tempfile.TemporaryDirectory(prefix='buc_input_') as directory:
        path = Path(directory)/'input.csv'
        columns = list(dim_cols) + ([] if measure_col == 'COUNT' else [measure_col])
        df[columns].to_csv(path, index=False)
        return run_buc_out_of_memory_csv(path, dim_cols, measure_col, minsup, memory_budget)


if __name__ == '__main__':
    from BUC_in_memory import DEFAULT_DIMENSIONS_12
    base = Path(__file__).resolve().parent
    path, stats = run_buc_to_csv(base/'cleaned/census_encoded.csv',
        DEFAULT_DIMENSIONS_12, 'COUNT', 50000, 8*1024**2,
        base/'cleaned/buc_12dim_paged_output.csv')
    print(path)
    print(stats)
