# -*- coding: utf-8 -*-
"""Corpus-wide LDI scan of Heeßel 2012 KAL 5, tagged by date/provenance/Babylon-copy.
Tests whether the LDI tracks scribal TRADITION (Assyrian vs Babylonian), not just period."""
import sys, re, os
from collections import defaultdict
from pypdf import PdfReader

# --- pull get_token_type from app.py (stub streamlit/plotly) ---
class _S:
    def __getattr__(self,n): return _S()
    def __call__(self,*a,**k): return _S()
    def __enter__(self): return _S()
    def __exit__(self,*a): return False
for m in ['streamlit','plotly','plotly.express','plotly.graph_objects']:
    sys.modules[m]=_S()
APP=r'C:\Users\wende\Documents\GitHub\logograms-analyser\app.py'
src=open(APP,encoding='utf-8').read().splitlines()
end=max(i for i,l in enumerate(src) if 'return all_anns' in l)
ns={'st':_S()}; exec('\n'.join(src[:end+1]),ns)
get_token_type=ns['get_token_type']

PDF=r'C:\Users\wende\Downloads\Heeßel 2012 Divinatorische Texte II. Opferschau-Omina KAL 5.pdf'
r=PdfReader(PDF)
# concat all pages (layout mode preserves case = the only thing the LDI test needs)
full=[]
for p in r.pages:
    try: full.append(p.extract_text(extraction_mode='layout') or '')
    except Exception: full.append('')
TEXT='\n'.join(full)
lines=TEXT.splitlines()

# --- split into text units by "NN) TABLET ..." headers ---
hdr=re.compile(r'^\s*(\d{1,3})\)\s+([A-ZÄ].{2,})$')
units=[]; cur=None
for ln in lines:
    m=hdr.match(ln)
    # header must look like a tablet siglum (VAT/AO/A/K/Ass/BM/Sm/Rm/...) to avoid false hits
    if m and re.search(r'\b(VAT|AO|A|K|Ass|BM|Sm|Rm|N|MS|Bu|Th|DT|VA)\b|[0-9]', m.group(2)[:30]):
        if cur: units.append(cur)
        cur={'nr':int(m.group(1)),'tablet':m.group(2).strip(),'body':[]}
    elif cur is not None:
        cur['body'].append(ln)
if cur: units.append(cur)

# dedup: keep first occurrence of each Nr (headers can repeat in running heads)
seen={}
for u in units:
    if u['nr'] not in seen and len(u['body'])>4:
        seen[u['nr']]=u
units=[seen[k] for k in sorted(seen)]

DATE_MAP={
 'altbabylonisch':('OB','Bab'),'altassyrisch':('OA','Ass'),
 'mittelbabylonisch':('MB','Bab'),'mittelassyrisch':('MA','Ass'),
 'frühneuassyrisch':('eNA','Ass'),'neuassyrisch':('NA','Ass'),
 'neubabylonisch':('NB','Bab'),'spätbabylonisch':('LB','Bab'),
}
SKIP={'Vs.','Rs.','Vs.!','Rs.!','Seite','a:','b:','(Rand)','(leer)','(abgebrochen)',
 'Spuren','Übersetzung:','Transliteration:','Bemerkungen:','Kollationen:','(Text:','MIN','o','(o)'}

def tokenize_ldi(tl_lines):
    log=tot=0
    for ln in tl_lines:
        # drop parenthetical editorial, leading line refs
        ln=re.sub(r'\([^)]*\)',' ',ln)
        for tok in ln.split():
            t=tok.strip()
            if not t or t in SKIP: continue
            # strip brackets/quotes/correction marks
            t=re.sub(r'[\[\]<>«»|!?]','',t)
            t=t.replace('(','').replace(')','')
            if not t: continue
            # skip pure line numbers / primes / dots / x / ellipses
            if re.fullmatch(r"\d+'?\.?",t): continue
            if re.fullmatch(r"[x.\-–…'’]+",t): continue
            if t in SKIP: continue
            # skip section words
            if t.rstrip('.!') in ('Vs','Rs','Seite'): continue
            tt=get_token_type(t)
            if tt=='other': continue
            if tt=='logogram': log+=1
            tot+=1
    return (log/tot if tot else 0.0), tot

rows=[]
for u in units:
    body='\n'.join(u['body'])
    dm=re.search(r'Datierung:\s*([A-Za-zäöü]+)',body)
    date_raw=dm.group(1).lower() if dm else '?'
    per,trad=DATE_MAP.get(date_raw,('?','?'))
    # Babylon-copy flag: German note or logographic colophon
    babcopy=bool(re.search(r'Vorlage aus Babylon|aus Babylon geschrieben|Babylon.{0,30}geschrieben|GABA\.RI\s*KÁ\.DINGIR\.RA[a-zA-Z]*\s*SAR',body))
    fo=re.search(r'Fundort:\s*([^\n;]+)',body)
    prov=fo.group(1).strip()[:20] if fo else '?'
    # transliteration block
    ti=body.find('Transliteration:')
    if ti<0: continue
    rest=body[ti+len('Transliteration:'):]
    ue=rest.find('Übersetzung:')
    tl=rest[:ue] if ue>=0 else rest[:4000]
    ldi,tok=tokenize_ldi(tl.splitlines())
    if tok<8: continue   # too small to be meaningful
    cat=trad if not babcopy else 'Bab(copy)'
    rows.append((u['nr'],u['tablet'][:24],date_raw[:14],per,trad,babcopy,ldi,tok))

print(f'{"Nr":>3} {"tablet":24} {"date":14} {"per":4} {"trad":9} {"bab?":4} {"LDI":>5} {"tok":>5}')
for x in rows:
    print(f'{x[0]:>3} {x[1]:24} {x[2]:14} {x[3]:4} {x[4]:9} {str(x[5]):4} {x[6]:5.3f} {x[7]:5}')

# aggregates
def agg(rows,keyf,labels):
    print('\n=== aggregate ===')
    buck=defaultdict(lambda:[0,0])  # [sum tok-weighted log, sum tok]
    cnt=defaultdict(int)
    raw=defaultdict(list)
    for x in rows:
        k=keyf(x)
        if k is None: continue
        raw[k].append(x[6]); cnt[k]+=1
    for k in labels:
        if k in raw:
            v=raw[k]
            print(f'{k:16} n={cnt[k]:3}  mean LDI={sum(v)/len(v):.3f}  range {min(v):.2f}-{max(v):.2f}')

# by period+tradition
print('\n=== by period x tradition (mean of per-text LDI) ===')
combo=defaultdict(list)
for x in rows:
    cat = 'Bab(copy)' if x[5] else x[4]
    combo[(x[3],cat)].append(x[6])
for k in sorted(combo):
    v=combo[k]; print(f'{k[0]:4} {k[1]:10} n={len(v):3} meanLDI={sum(v)/len(v):.3f}  range {min(v):.2f}-{max(v):.2f}')

# pure Assyrian vs Babylonian (all periods), copies separated
print('\n=== TRADITION TEST (texts with >=20 scored tokens) ===')
trad_b=defaultdict(list); trad_w=defaultdict(lambda:[0.0,0])
for x in rows:
    if x[7]<20: continue
    if x[5]: k='Babylon-copy'
    elif x[4]=='Ass': k='Assyrian (native)'
    elif x[4]=='Bab': k='Babylonian (native)'
    else: continue
    trad_b[k].append(x[6]); trad_w[k][0]+=x[6]*x[7]; trad_w[k][1]+=x[7]
for k in ['Babylonian (native)','Babylon-copy','Assyrian (native)']:
    if k in trad_b:
        v=trad_b[k]; ww=trad_w[k][0]/trad_w[k][1]
        print(f'{k:22} n={len(v):3} mean(per-text)={sum(v)/len(v):.3f}  token-weighted={ww:.3f}')
print('\nBabylon-copy tablets (Assyrian-period tablets, Babylonian Vorlage):')
for x in rows:
    if x[5]: print(f'  Nr.{x[0]:>3} {x[1]:24} {x[2]:14} LDI={x[6]:.3f} tok={x[7]}')

# --- dump CSV + sorted view for the article appendix ---
import csv
out=r'C:\Users\wende\Documents\GitHub\logograms-analyser\docs\kal5-ldi-by-tradition.csv'
with open(out,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['Nr','tablet','date','period','tradition','babylon_copy','LDI','tokens'])
    for x in sorted(rows,key=lambda r:r[0]):
        w.writerow([x[0],x[1],x[2],x[3],x[4],x[5],f'{x[6]:.3f}',x[7]])
print('\nwrote',out,'with',len(rows),'texts')
