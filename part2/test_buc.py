"""Regression tests against DuckDB, including external merges and edge cases."""
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
from BUC_in_memory import run_buc_in_memory
from BUC_out_of_memory import run_buc_to_csv
from verify_BUC_out import cells, assert_same, reference


def main():
    rng=np.random.default_rng(2026)
    df=pd.DataFrame({'a':rng.integers(0,7,8000),'b':rng.integers(0,3,8000),
                     'weight':rng.integers(1,10,8000)})
    cases=[(df,'COUNT',500),(df,'weight',4000),(df.head(0),'COUNT',1),
           (df.head(2),'COUNT',10),(df.head(20),'COUNT',0)]
    with tempfile.TemporaryDirectory(prefix='buc_test_') as directory:
        for index,(data,measure,support) in enumerate(cases):
            source=Path(directory)/'data.csv'
            data.to_csv(source,index=False)
            expected=reference(data,['a','b'],measure,support)
            mem,_=run_buc_in_memory(data,['a','b'],measure,support)
            assert_same(cells(mem,['a','b'],measure),expected)
            path,stats=run_buc_to_csv(source,['a','b'],measure,support,512*1024,
                                    Path(directory)/'out.csv')
            actual=cells(pd.read_csv(path),['a','b'],measure)
            assert_same(actual,expected)
            assert all(v>=support for v in actual.values())
            assert stats['workspace_bound_bytes']<=512*1024
            if index==0: assert stats['merge_passes']>0
            print(f'PASS case {index}: {len(actual)} cells; merge passes={stats["merge_passes"]}',flush=True)


if __name__=='__main__':
    main()
