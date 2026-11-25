"""Prepare the snapshot-era market universe and a display-only name mapping."""
import json
import re
from pathlib import Path

import duckdb

ROOT=Path(__file__).resolve().parents[3]
con=duckdb.connect()
pattern=r'^(sh\.60[0135][0-9]{3}|sz\.00[0123][0-9]{3})$'
recent={row[0].replace('.','') for row in con.execute("""
    select distinct code from read_parquet('raw/bars_daily/*.parquet')
    where date between '2026-09-01' and '2026-09-24' and regexp_matches(code,?)
""",[pattern]).fetchall()}
directory=json.loads((ROOT/'data/stocks.json').read_text())['stocks']
names={row['code']:row['name'] for row in directory
       if re.fullmatch(r'(60[0135]|00[0123])[0-9]{3}',row['code'])}
known=set()
for path in Path('raw/bars_daily').glob('CN_*.parquet'):
    parts=path.stem.split('_')
    if len(parts)==3 and parts[1] in ('SSE','SZSE'):
        known.add(('sh' if parts[1]=='SSE' else 'sz')+parts[2])
display_codes={('sh' if code.startswith('60') else 'sz')+code for code in names}
target=sorted(recent|(display_codes-known))
Path('universe.json').write_text(json.dumps({'codes':target,'names':names},ensure_ascii=False))
print('target stocks',len(target),'new codes',sorted(set(target)-recent))
