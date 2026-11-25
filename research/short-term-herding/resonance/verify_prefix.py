"""Compare board-day factors re-run at the original data cutoff."""
import argparse
import pandas as pd

parser=argparse.ArgumentParser()
parser.add_argument('full')
parser.add_argument('prefix')
options=parser.parse_args()
columns=['cohort','date','seq','members','n5','relative5','breadth5','group_r5',
         'concentration_lo','concentration_hi','boards','max_height']
full=pd.read_pickle(options.full)
truncated=pd.read_pickle(options.prefix)
full=full.loc[full.date.le('2026-09-24'),columns].reset_index(drop=True)
truncated=truncated[columns].reset_index(drop=True)
pd.testing.assert_frame_equal(full,truncated,check_exact=False,atol=3e-10,rtol=1e-8)
print('Prefix verified:',len(full))
