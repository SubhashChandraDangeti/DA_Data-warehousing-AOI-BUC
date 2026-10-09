"""Benchmark cardinality-descending dimension order against the original order.

Use identical rows/dimensions/measure/minsup for each pair, repeat three times,
and assert that the supported cube is unchanged after restoring column order.
"""
from pathlib import Path
import time
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from BUC_in_memory import run_buc_in_memory
from BUC_out_of_memory import run_buc_out_of_memory
from verify_BUC_out import assert_same, cells

BASE=Path(__file__).resolve().parent


def optimize_dimension_order(df, dim_cols):
    return sorted(dim_cols,key=lambda c:-df[c].nunique())


def main():
    df=pd.read_csv(BASE/'cleaned/census_encoded.csv')
    out=BASE/'cleaned/optimization'
    out.mkdir(parents=True,exist_ok=True)
    dims=['sex_code','race_code','marital_status_code','class_of_worker_code',
          'education_code','age','hispanic_origin_code','industry_code_major_code']
    configs=[('in_memory_8dims',dims,run_buc_in_memory,{}),
             ('paged_6dims',dims[:6],run_buc_out_of_memory,{'memory_budget':4*1024**2})]
    rows=[]
    for label,original,run,kwargs in configs:
        expected=None
        for ordering in ['original','optimized']:
            t=time.perf_counter()
            order=list(original) if ordering=='original' else optimize_dimension_order(df,original)
            prep=time.perf_counter()-t
            for repeat in range(1,4):
                result,stats=run(df,order,'COUNT',1000,**kwargs)
                actual=cells(result[original+['count']],original,'COUNT')
                if expected is None: expected=actual
                else: assert_same(actual,expected)
                row=dict(config=label,ordering=ordering,repeat=repeat,minsup=1000,
                         runtime_sec=stats['elapsed_sec']+prep,reordering_sec=prep,
                         cells=stats['cells_output'],examined=stats['cells_examined'],
                         dimension_order=';'.join(order))
                rows.append(row)
                pd.DataFrame(rows).to_csv(out/'runs.csv',index=False)
                print(row,flush=True)
    frame=pd.DataFrame(rows)
    summary=frame.groupby(['config','ordering'],as_index=False).agg(
        runtime_median_sec=('runtime_sec','median'),examined=('examined','first'),cells=('cells','first'))
    summary.to_csv(out/'summary.csv',index=False)
    fig,ax=plt.subplots(figsize=(7,4))
    summary.pivot(index='config',columns='ordering',values='runtime_median_sec').plot.bar(ax=ax,rot=0)
    ax.set(ylabel='Median runtime (seconds)',xlabel='',title='Dimension reordering: same input, three repeats')
    fig.tight_layout()
    fig.savefig(BASE/'report_assets/optimization_benchmark.png',dpi=160)
    plt.close(fig)


if __name__=='__main__':
    main()
