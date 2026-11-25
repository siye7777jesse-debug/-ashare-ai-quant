import json, shutil
from pathlib import Path
import duckdb,pandas as pd,numpy as np
from analyze_cycles import wings, core_maps, reconstruct, public_calendar, encode, summarize

base=Path('full.duckdb')
canonical=json.loads(Path('full-results.json').read_text())
old=json.loads(Path('archive-results.json').read_text())
joined=duckdb.connect('full.duckdb',read_only=True)
joined.execute("attach 'archive.duckdb' as archive (read_only)")
# Recreate the July-to-September signal panel independently at the original cutoff.
cols='date,code,strict,broad,r5,height,boards5,recent_lo,recent_hi,prior_lo,prior_hi'
left=joined.execute(f"select {cols} from stockday where date<='2026-09-24' order by date,code").df()
right=joined.execute(f"select {cols} from archive.stockday order by date,code").df()
pd.testing.assert_frame_equal(left,right,check_exact=False,atol=3e-10,rtol=1e-8)
print('prefix rows',len(left),flush=True)
joined.close()
shutil.copyfile(base,'sensitivity.duckdb')
con=duckdb.connect('sensitivity.duckdb')
dates=pd.DataFrame({'date':pd.to_datetime(public_calendar())})
con.register('extension_calendar',dates)
# Only a stress test: assume the preceding raw close for unresolved exchange reference
# and freeze the known later directory status at every extension day. No effect on canonical results.
con.execute("""
create temp table prior_quote as
select date,code,lag(close) over(partition by code order by date) prev_close
from (select date,code,close from hist where trading and amount>0
      union all select cast(date as date),code,close from extension_bars)
""")
con.execute("""update extension_bars e set ref=p.prev_close
from prior_quote p where e.code=p.code and e.date=p.date and e.ref is null
  and p.prev_close is not null""")
directory=json.load(open('universe.json'))['names']
changed=canonical['extension_audit']['status_changed_or_inconsistent_directory']
for code in changed:
    con.execute("update extension_bars set risk=? where code=?",
                ['ST' in directory[code[3:]].upper(),code])
daily=wings(con,True)
strict,broad,cohorts=core_maps(con)
episodes,amb=reconstruct(daily,strict,broad,cohorts)
s=summarize(con,daily,episodes,strict,broad)
identity=lambda r:[(e['start'],e['end'],[(m['code'],m['height']) for m in e['members']]) for e in r['episodes']]
match=identity(s)==identity(canonical)
out=dict(prefix_rows=len(left),sensitivity_same_episode_identities=match,
         sensitivity_cohort_follow_10=s['cohort_follow_10'],
         sensitivity_pullback_10=s['pullback_costs']['10'])
if not match:
    out['sensitivity_episodes']=identity(s)
Path('validation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=encode))
print(out,flush=True)
