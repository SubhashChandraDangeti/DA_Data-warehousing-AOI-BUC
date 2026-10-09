"""Full-data verification: both BUC implementations versus DuckDB CUBE.

Run this file to write verification.csv/json and a 12-dimensional cube.
The 12-dimensional reference uses separate DuckDB grouping-set batches to
bound its own memory; together these cover every grouping of CUBE exactly.
"""
from pathlib import Path
import csv
import itertools
import json
import tempfile
import time

import duckdb
import numpy as np
import pandas as pd

from BUC_in_memory import DEFAULT_DIMENSIONS_12, run_buc_in_memory
from BUC_out_of_memory import run_buc_to_csv

BASE = Path(__file__).resolve().parent


def cells(frame, dims, measure):
    name = 'count' if measure == 'COUNT' else measure
    result = {}
    for row in frame.itertuples(index=False, name=None):
        key = tuple('ALL' if str(v) == 'ALL' else int(v) for v in row[:len(dims)])
        assert key not in result, f'Duplicate cell: {key}'
        result[key] = float(row[-1])
    return result


def assert_same(actual, expected):
    assert actual.keys() == expected.keys(), (
        f'Missing {len(expected.keys()-actual.keys())}, extra {len(actual.keys()-expected.keys())}')
    for key in actual:
        assert np.isclose(actual[key], expected[key], rtol=1e-10, atol=1e-6), key


def reference(df, dims, measure, minsup):
    agg = 'COUNT(*)' if measure == 'COUNT' else f'SUM("{measure}")'
    quoted = [f'"{d}"' for d in dims]
    result = {}
    with duckdb.connect() as con:
        con.execute("SET threads=2")
        con.execute("SET memory_limit='768MB'")
        con.register('t', df)
        if len(dims) <= 6:
            queries = [(f'SELECT {", ".join(quoted)}, {agg} FROM t '
                        f'GROUP BY CUBE ({", ".join(quoted)}) HAVING {agg} >= {minsup}')]
        else:
            # CUBE(d1,...,dn) is the union of all 2**n grouping sets. Executing
            # one GROUP BY at a time avoids DuckDB retaining thousands of hash
            # tables concurrently. No rows are sampled and no group is omitted.
            queries = []
            for mask in range(1 << len(dims)):
                group = [quoted[i] for i in range(len(dims)) if mask & (1 << i)]
                select = [quoted[i] if mask & (1 << i) else 'NULL' for i in range(len(dims))]
                clause = ' GROUP BY ' + ', '.join(group) if group else ''
                queries.append(f'SELECT {", ".join(select)}, {agg} FROM t{clause} HAVING {agg} >= {minsup}')
        for index, query in enumerate(queries):
            for row in con.execute(query).fetchall():
                key = tuple('ALL' if v is None else int(v) for v in row[:-1])
                result[key] = float(row[-1])
            if len(queries)>1 and (index+1)%512==0:
                print(f'  DuckDB grouping sets: {index+1}/{len(queries)}', flush=True)
    return result


def verify_case(df, dims, measure, minsup, budget, label, out_dir):
    frame, mem_stats = run_buc_in_memory(df, dims, measure, minsup)
    mem = cells(frame, dims, measure)
    assert all(v >= minsup for v in mem.values())
    with tempfile.TemporaryDirectory(prefix='buc_verify_') as directory:
        source = Path(directory)/'input.csv'
        df[list(dims)+([] if measure=='COUNT' else [measure])].to_csv(source, index=False)
        path, disk_stats = run_buc_to_csv(source, dims, measure, minsup, budget,
                                         out_dir/f'{label}_cube.csv')
    disk_frame = pd.read_csv(path, dtype={d: str for d in dims})
    disk = cells(disk_frame, dims, measure)
    assert all(v >= minsup for v in disk.values())
    assert_same(disk, mem)
    ref = reference(df, dims, measure, minsup)
    assert_same(mem, ref)
    row = dict(test=label, rows=len(df), dimensions=len(dims), measure=measure,
               minsup=minsup, budget_bytes=budget, cells=len(mem),
               in_memory_sec=mem_stats['elapsed_sec'],
               paged_sec=disk_stats['elapsed_sec'],
               workspace_bound_bytes=disk_stats['workspace_bound_bytes'],
               spill_files=disk_stats['spill_files_written'], status='PASS')
    print(row, flush=True)
    return row


def main():
    df = pd.read_csv(BASE/'cleaned/census_encoded.csv')
    out = BASE/'cleaned/verification'
    out.mkdir(parents=True, exist_ok=True)
    small = ['sex_code','race_code','citizenship_code','marital_status_code']
    configurations = [
        (small, 'COUNT', 1000, 512*1024, 'count_4dims_512kib'),
        (small, 'COUNT', 1000, 4*1024**2, 'count_4dims_4mib'),
        (small[:3], 'instance_weight', 5000000, 1024**2, 'sum_3dims'),
        (small+['tax_filer_status_code','employment_status_code'], 'COUNT', 500,
         4*1024**2, 'count_6dims'),
        (DEFAULT_DIMENSIONS_12, 'COUNT', 50000, 8*1024**2, 'count_12dims'),
    ]
    results=[]
    for dims, measure, minsup, budget, label in configurations:
        results.append(verify_case(df,dims,measure,minsup,budget,label,out))
        pd.DataFrame(results).to_csv(out/'verification.csv', index=False)
        (out/'verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
