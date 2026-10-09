"""Reproduce notebook preprocessing, DuckDB ETL and all ten query outputs."""
from pathlib import Path
import contextlib
import json
import os
import runpy
import duckdb

BASE=Path(__file__).resolve().parent


def main():
    os.chdir(BASE)
    if (BASE/'warehouse.duckdb').exists():
        raise FileExistsError('warehouse.duckdb already exists; archive it before rebuilding')
    with open(BASE/'validation_log.txt','w',encoding='utf-8') as log, contextlib.redirect_stdout(log):
        notebook=json.loads((BASE/'preprocessing.ipynb').read_text(encoding='utf-8'))
        scope={}
        for index,cell in enumerate(notebook['cells']):
            if cell['cell_type']=='code':
                exec(compile(''.join(cell['source']),f'preprocessing.ipynb:cell{index}','exec'),scope)
        scope['con'].close()
        runpy.run_path(str(BASE/'etl_load.py'),run_name='__main__')
        with duckdb.connect(str(BASE/'warehouse.duckdb'),read_only=True) as con:
            for q in range(1,11):
                result=con.execute((BASE/f'q{q}.sql').read_text()).df()
                result.to_csv(BASE/f'q{q}_result.csv',index=False)
                print(f'Q{q}: {len(result)} rows')
            counts={t:con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                    for t in ['fact_order_items','dim_order','dim_customer','dim_product','dim_seller','dim_seller_acquisition']}
            original=con.execute("SELECT COUNT(*) FROM read_csv_auto('M26_DA_A2_Part1/order_items.csv')").fetchone()[0]
            assert counts['fact_order_items']==original
            counts['revenue']=str(con.execute('SELECT SUM(revenue) FROM fact_order_items').fetchone()[0])
            counts['missing_review_items']=con.execute('SELECT COUNT(*) FROM fact_order_items WHERE review_key IS NULL').fetchone()[0]
            counts['undelivered_orders']=con.execute('SELECT COUNT(*) FROM dim_order WHERE order_delivered_customer_date IS NULL').fetchone()[0]
            assert counts['missing_review_items']>0 and counts['undelivered_orders']>0
            (BASE/'validation_summary.json').write_text(json.dumps(counts,indent=2),encoding='utf-8')
            print(counts)
    print('Part 1 complete; see validation_log.txt and validation_summary.json')


if __name__=='__main__':
    main()
