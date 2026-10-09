"""Three repeated full-data sweeps of the paged BUC; plots use median runtime.

All runs use streamed CSV input/output. BUC runtime excludes CSV staging,
which is separately recorded in the raw benchmark table. Memory is in bytes.
"""
from pathlib import Path
import tempfile
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from BUC_in_memory import DEFAULT_DIMENSIONS_12
from BUC_out_of_memory import run_buc_to_csv

BASE=Path(__file__).resolve().parent


def main():
    source=BASE/'cleaned/census_encoded.csv'
    out=BASE/'cleaned/performance'
    out.mkdir(parents=True,exist_ok=True)
    assets=BASE/'report_assets'
    dimensions=['age','education_code','class_of_worker_code','marital_status_code',
                'race_code','sex_code','hispanic_origin_code','industry_code_major_code']
    fixed=['race_code','sex_code','citizenship_code','marital_status_code']
    cases=[]
    for support in [1000,10000,50000]:
        cases.append(('minsup',support,dimensions[:6],support,4*1024**2))
    for budget in [512*1024,1024**2,4*1024**2,16*1024**2]:
        cases.append(('memory',budget,fixed,1000,budget))
    for count in [2,4,6,8]:
        cases.append(('dimensions',count,dimensions[:count],50000,4*1024**2))
    rows=[]
    with tempfile.TemporaryDirectory(prefix='perf_output_') as directory:
        for sweep,x,dims,support,budget in cases:
            for repeat in range(1,4):
                _,stats=run_buc_to_csv(source,dims,'COUNT',support,budget,Path(directory)/'cube.csv')
                row=dict(sweep=sweep,x=x,repeat=repeat,dimensions=len(dims),
                         minsup=support,memory_bytes=budget,**stats)
                rows.append(row)
                pd.DataFrame(rows).to_csv(out/'runs.csv',index=False)
                print(f'{sweep}={x} repeat={repeat}: {stats["elapsed_sec"]:.3f}s, {stats["cells_output"]} cells',flush=True)
    frame=pd.DataFrame(rows)
    # groupby here summarizes benchmark records; it is never used to compute a cube.
    summary=frame.groupby(['sweep','x'],as_index=False).agg(
        runtime_median_sec=('elapsed_sec','median'),runtime_min_sec=('elapsed_sec','min'),
        runtime_max_sec=('elapsed_sec','max'),cells=('cells_output','first'))
    summary.to_csv(out/'summary.csv',index=False)
    for sweep,label,filename in [
        ('minsup','Minimum support (6 dims; 4 MiB)','minsup_vs_runtime.png'),
        ('memory','Workspace budget (MiB; 4 dims; minsup=1000)','memory_vs_runtime.png'),
        ('dimensions','Number of dimensions (4 MiB; minsup=50000)','dimensions_vs_runtime.png')]:
        sub=summary[summary.sweep==sweep]
        x=sub.x/(1024**2) if sweep=='memory' else sub.x
        y=sub.runtime_median_sec
        fig,ax=plt.subplots(figsize=(7,4))
        ax.errorbar(x,y,yerr=[y-sub.runtime_min_sec,sub.runtime_max_sec-y],fmt='o-',capsize=4)
        ax.set(xlabel=label,ylabel='BUC runtime (seconds)',title='Full census: median and range of three runs')
        ax.grid(alpha=.25)
        fig.tight_layout()
        fig.savefig(assets/filename,dpi=160)
        plt.close(fig)


if __name__=='__main__':
    main()
