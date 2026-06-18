import pandas as pd, yaml, os, re
from compute_ratios import load_local_data, ldi
def rec_of(fp):
    with open(fp,encoding='utf-8') as f: c=f.read()
    if c.startswith('---'):
        fm=yaml.safe_load(c.split('---',2)[1]) or {}
        return fm.get('recension','—')
    return '—'
recmap={}
for root,_,fs in os.walk('data/new/astrology'):
    for fn in fs:
        if fn.endswith('.txt'): recmap[fn]=rec_of(os.path.join(root,fn))
for mode,po in [('full',False),('preserved',True)]:
    df=pd.DataFrame(load_local_data('data',preserved_only=po))
    a=df[(df['period']=='Neo Period') & (df['genre'].str.lower().isin({'astrological omens'}))].copy()
    a['rec']=a['filename'].map(recmap)
    print(f"\n==== NEO ASTROLOGY — A vs B  ({mode}) ====")
    print(f"{'group':<28}{'LDI':>7}{'logs':>7}{'tok':>7}")
    for fn in sorted(a['filename'].unique()):
        sub=a[a['filename']==fn]; r,lg,t=ldi(sub)
        print(f"  {fn:<26}{r:>7.3f}{lg:>7}{t:>7}  [rec {recmap.get(fn)}]")
    for rec in ['A (Assyrian)','B (Babylonian)']:
        sub=a[a['rec']==rec]; 
        if len(sub): r,lg,t=ldi(sub); print(f"{('Rec '+rec):<28}{r:>7.3f}{lg:>7}{t:>7}")
    # exclude the discursive IM.124485 to isolate terse canonical EAE 20
    eae=a[a['filename']!='IM.124485.txt']
    r,lg,t=ldi(eae); print(f"{'EAE20 canonical (excl IM)':<28}{r:>7.3f}{lg:>7}{t:>7}")
