# -*- coding: utf-8 -*-
"""Verify every figure printed in docs/The-Logographic-Shift.md against the corpus.

    py scripts/verify_article.py [-v]

Each check compares a computed value with the value as printed in the article
(encoded here). A check passes when the computed value rounds to the printed
one at the printed precision. Exit code = number of mismatches.
"""
import io, os, re, sys, tempfile, shutil
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import compute_ratios as C

VERBOSE = '-v' in sys.argv
CHECKS = []

# Printed values as updated on 2026-08-19 (post tokenizer fix). ck() consults
# this by label so the encoded historical literals need not be rewritten.
NEW_PRINTED = {
 "T5 bin Old":0.327,"T5 bin Middle":0.699,"T5 bin Neo":0.752,"T5 bin corpus":0.682,
 "T5 macro Old":0.313,"T5 macro Middle":0.627,"T5 macro Neo":0.670,"T5 macro corpus":0.612,
 "T5 micro Old":0.193,"T5 micro Middle":0.513,"T5 micro Neo":0.591,"T5 micro corpus":0.497,
 "T5 ina/ana-log Old":0.327,"T5 ina/ana-log Middle":0.752,"T5 ina/ana-log Neo":0.823,
 "T5 ina/ana-log corpus":0.739,
 "T5 restor-dropped Old":0.311,"T5 restor-dropped Middle":0.678,"T5 restor-dropped Neo":0.737,
 "T5 restor-dropped corpus":0.661,
 "T5 no-particle Old":0.281,"T5 no-particle Middle":0.668,"T5 no-particle Neo":0.728,
 "T5 no-particle corpus":0.651,
 "T5 pure Old":30.1,"T5 pure Middle":54.8,"T5 pure Neo":57.2,"T5 pure corpus":53.0,
 "T5 mixed Middle":15.3,
 "T5 syll Middle":29.9,"T5 syll Neo":24.6,"T5 syll corpus":31.7,
 "prose restor-effect min":0.015,"prose restor-effect max":0.021,
 "prose O->M rise baseline":0.372,"prose O->M rise min":0.314,"prose O->M rise max":0.425,
 "n20/3.3.3 spread floor":0.467,"n20/3.3.3 spread ceiling":0.739,
 "T8 martu Old bin":0.13,
 "T9 napl Middle macro":0.63,
 "T11 martu MB bin":0.72,"T11 martu MB macro":0.63,
 "T11 naplastu MB bin":0.71,
 "T13 Emar.669.txt micro":0.32,
 "T14 lung Neo bin":0.75,"T14 lung Neo macro":0.69,
 "T15 VAT9580 bin":0.73,"T15 VAT9580 macro":0.70,"T15 VAT9580 micro":0.60,
 "T15 K2858 bin":0.79,"T15 K2858 macro":0.75,"T15 K2858 micro":0.67,
 "3.2.3 gap noparticle P":0.65,"3.2.3 gap inaana P":0.77,
 "T20 Rm.267.txt tokens":217,"T20 Rm.267.txt bin":0.71,"T20 Rm.267.txt macro":0.61,
 "T20 Rm.267.txt micro":0.62,"T20 IM124485 tokens":605,
 "T21 EAE20+21+22 macro":0.65,"T21 EAE20+21+22 pure":56.6,"T21 EAE20+21+22 mixed":15.9,
 "T21 EAE20+21+22 syll":27.5,
 "T21 EAE55 pure":65.4,"T21 EAE55 syll":24.7,
 "T21 EAE57 pure":68.8,"T21 EAE57 syll":22.8,
 "T21 pooled macro":0.67,"T21 pooled pure":59.4,"T21 pooled syll":26.5,
 "T23 diag Middle bin":0.52,"T23 diag Middle macro":0.45,
 "3.3.1 Middle diag w/o IM57947":0.48,
 "T24 Neo-Bab pure":45.7,"T24 Neo-Bab mixed":28.4,"T24 Neo-Bab syll":25.9,
 "T24 Neo-Ass pure":45.9,"T24 Neo-Ass mixed":30.5,"T24 Neo-Ass syll":23.6,
 "T23 diag Neo macro":0.62,
 "T25 Emar694 bin":0.48,"T25 Emar694 macro":0.38,"T25 Emar694 micro":0.32,
 "T25 Emar695 bin":0.73,"T25 Emar695 macro":0.69,"T25 Emar695 micro":0.75,
 "T25 StBoT bin":0.24,"T25 StBoT macro":0.21,
 "T27 izbu Middle bin":0.71,"T27 izbu Middle macro":0.64,"T27 izbu Neo bin":0.83,
 "T28 Mid-Hatt bin":0.35,"T28 Mid-Hatt macro":0.32,"T28 Mid-Hatt pure":29.1,
 "T28 Mid-Hatt mixed":6.1,"T28 Mid-Hatt syll":64.8,
 "T28 Neo-Bab pure":64.3,"T28 Neo-Bab syll":18.0,"T28 Neo-Ass pure":65.4,
 "T30 terr Middle bin":0.75,"T30 terr Middle micro":0.60,
 "T30 terr Neo macro":0.70,"T30 terr Neo micro":0.62,"T30 terr total macro":0.66,
 "3.5.1 VAT10849 bin":0.43,
 "T31 Mid-Ass macro":0.68,"T31 Mid-Ass micro":0.60,
 "3.5.2 Bab lead ina/ana":0.07,
 "T32 Nabu macro":0.07,
 "n22 micro>bin texts":4,
}

def ck(label, computed, printed, dec=2):
    """dec: decimals of the printed value; dec='pct1' = one-decimal percent;
    dec='int' = exact integer."""
    printed = NEW_PRINTED.get(label, printed)
    if dec == 'int':
        ok = int(round(computed)) == int(printed)
        cs = f"{computed:.0f}" if isinstance(computed, float) else str(computed)
    elif dec == 'pct1':
        ok = abs(computed - printed) < 0.05
        cs = f"{computed:.1f}"
    else:
        ok = round(computed + 1e-12, dec) == round(printed, dec)
        cs = f"{computed:.{dec+1}f}"
    CHECKS.append((ok, label, cs, printed))

# ---------------------------------------------------------------- loading ----
def _fold(p):
    if p in C.PERIOD_ORDER: return p
    return C.PERIOD_MAPPING.get(p, p)

def _load(annotate=None, preserved=False):
    anns = C.load_local_data("data", preserved_only=preserved, annotate=annotate)
    d = pd.DataFrame(anns)
    d['era'] = d['period'].map(_fold)
    return d

def AK(d):
    return d[d['language'] == 'akkadian']

print("loading corpus (word x2, sign x2) ...", file=sys.stderr)
W  = _load()                                   # word-level, restorations counted
WP = _load(preserved=True)                     # word-level, preserved-only
S  = _load(annotate=C.annotate_signs)          # sign-level
SP = _load(annotate=C.annotate_signs, preserved=True)

# main corpus slices (the three folded periods only = excludes nothing extra;
# every non-excluded file under old/middle/new is the corpus)
CW, CWP = W[W.era.isin(C.PERIOD_ORDER)], WP[WP.era.isin(C.PERIOD_ORDER)]
CS, CSP = S[S.era.isin(C.PERIOD_ORDER)], SP[SP.era.isin(C.PERIOD_ORDER)]

# file -> relative path (topic/feature come from the folder nesting)
RP = {}
for root, _, files in os.walk("data"):
    for f in files:
        if f.endswith(".txt"):
            RP[f] = os.path.relpath(os.path.join(root, f), "data").replace(os.sep, "/")

def sub(frame, feature=None, files=None, era=None, genre=None, contains=None):
    d = frame
    if era:    d = d[d.era == era]
    if genre:  d = d[d.genre == genre]
    if files:  d = d[d.filename.isin(files)]
    if feature is not None:
        d = d[d.filename.map(lambda f: f'/{feature}/' in RP.get(f, ''))]
    if contains is not None:
        d = d[d.filename.map(lambda f: contains in RP.get(f, ''))]
    return d

def B(d):  return C.ldi(AK(d))[0]                    # bin (Akkadian only)
def G(d):  return C.graded_ldi(C._drop_contentless(AK(d)))
def nom(d): return d.groupby(['filename','omen_id']).ngroups   # raw, all languages
def ntx(d): return d.filename.nunique()

# excluded texts (held-out, comparanda, kal5): load via a temp copy with the
# exclude flag stripped, exactly as scripts/corpus_manifest.py does.
def load_stripped(rel_filter, annotate=None, preserved=False):
    with tempfile.TemporaryDirectory() as td:
        n = 0
        for f, rel in RP.items():
            if rel_filter(rel):
                txt = io.open(os.path.join("data", rel), encoding="utf-8").read()
                txt = re.sub(r"^[ \t]*exclude:\s*true.*$\n?", "", txt, flags=re.M)
                dst = os.path.join(td, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                io.open(dst, "w", encoding="utf-8", newline="\n").write(txt)
                n += 1
        if not n: return pd.DataFrame()
        d = pd.DataFrame(C.load_local_data(td, preserved_only=preserved, annotate=annotate))
        if d.empty: return d
        d['era'] = d['period'].map(_fold)
        return d

# region from provenance (mirrors app.py)
_RK = (("Tigunanum", ("tigunanum",)),
       ("Periphery", ("hattusa","ḫattuša","bogazkoy","boğazköy","bogh","emar","meskene",
                      "susa","elam","mari","nuzi","ugarit","alalakh","qatna","ekalte","periphery")),
       ("Assyria",   ("assur","aššur","nineveh","ninive","kuyunjik","kalhu","kalḫu",
                      "nimrud","sultantepe","huzirina","šapiya","sapiya")),
       ("Babylonia", ("babylon","babylonia","nippur","sippar","uruk","warka","sealand",
                      "kish","borsippa","larsa","merkes","southern","umma","jokha")))
def region(prov):
    p = str(prov or "").lower()
    if not p.strip() or any(w in p for w in ("canonical","composite","manuscript")):
        return "Unassigned"
    for r, keys in _RK:
        if any(k in p for k in keys): return r
    return "Unassigned"

for d in (CW, CWP, CS, CSP):
    d['region'] = d['provenance'].map(region) if 'provenance' in d.columns else 'Unassigned'

# ================================================================ Table 1 ====
GEN = {'astrological omens':'astro','diagnostic omens':'diag','extispicy omens':'ext',
       'izbu omens':'izbu','terrestrial omens':'terr'}
T1 = {('astro','Old Period'):(286,6),('astro','Middle Period'):(274,7),('astro','Neo Period'):(453,8),
      ('diag','Old Period'):(33,2),('diag','Middle Period'):(230,13),('diag','Neo Period'):(1173,32),
      ('ext','Old Period'):(188,13),('ext','Middle Period'):(1212,37),('ext','Neo Period'):(534,16),
      ('izbu','Old Period'):(134,5),('izbu','Middle Period'):(220,14),('izbu','Neo Period'):(692,11),
      ('terr','Old Period'):(120,3),('terr','Middle Period'):(418,17),('terr','Neo Period'):(1038,11)}
for (g,e),(o,t) in T1.items():
    d = CW[(CW.genre.map(GEN.get)==g)&(CW.era==e)]
    ck(f"T1 {g} {e.split()[0]} omens", nom(d), o, 'int')
    ck(f"T1 {g} {e.split()[0]} texts", ntx(d), t, 'int')
ck("T1 total omens", nom(CW), 7005, 'int')
ck("T1 total texts", ntx(CW), 195, 'int')

# ================================================================ Table 5 ====
ck("T5 bin Old",    B(sub(CW,era='Old Period')),    0.326, 3)
ck("T5 bin Middle", B(sub(CW,era='Middle Period')), 0.695, 3)
ck("T5 bin Neo",    B(sub(CW,era='Neo Period')),    0.750, 3)
ck("T5 bin corpus", B(CW),                          0.679, 3)
for e,exp in [('Old Period',0.312),('Middle Period',0.623),('Neo Period',0.668)]:
    ck(f"T5 macro {e.split()[0]}", G(sub(CS,era=e))['macro'], exp, 3)
ck("T5 macro corpus", G(CS)['macro'], 0.609, 3)
for e,exp in [('Old Period',0.192),('Middle Period',0.511),('Neo Period',0.590)]:
    ck(f"T5 micro {e.split()[0]}", G(sub(CS,era=e))['micro'], exp, 3)
ck("T5 micro corpus", G(CS)['micro'], 0.495, 3)
for e,exp in [('Old Period',0.326),('Middle Period',0.748),('Neo Period',0.822)]:
    ck(f"T5 ina/ana-log {e.split()[0]}", C.ldi(AK(sub(CW,era=e)),monogram_as_log=True)[0], exp, 3)
ck("T5 ina/ana-log corpus", C.ldi(AK(CW),monogram_as_log=True)[0], 0.736, 3)
for e,exp in [('Old Period',0.310),('Middle Period',0.676),('Neo Period',0.736)]:
    ck(f"T5 restor-dropped {e.split()[0]}", B(sub(CWP,era=e)), exp, 3)
ck("T5 restor-dropped corpus", B(CWP), 0.660, 3)
for e,exp in [('Old Period',0.280),('Middle Period',0.663),('Neo Period',0.726)]:
    ck(f"T5 no-particle {e.split()[0]}", C.ldi(AK(sub(CW,era=e)),exclude_particles=True)[0], exp, 3)
ck("T5 no-particle corpus", C.ldi(AK(CW),exclude_particles=True)[0], 0.649, 3)
for e,pu,mx,sy in [('Old Period',30.0,2.5,67.5),('Middle Period',54.4,15.2,30.4),
                   ('Neo Period',57.0,18.2,24.8)]:
    g = G(sub(CS,era=e)); n = g['pure']+g['mixed']+g['syllabic']
    ck(f"T5 pure {e.split()[0]}",  100*g['pure']/n,  pu, 'pct1')
    ck(f"T5 mixed {e.split()[0]}", 100*g['mixed']/n, mx, 'pct1')
    ck(f"T5 syll {e.split()[0]}",  100*g['syllabic']/n,  sy, 'pct1')
g = G(CS); n = g['pure']+g['mixed']+g['syllabic']
ck("T5 pure corpus",  100*g['pure']/n,  52.8, 'pct1')
ck("T5 mixed corpus", 100*g['mixed']/n, 15.3, 'pct1')
ck("T5 syll corpus",  100*g['syllabic']/n,  31.9, 'pct1')

# post-Table-5 prose (L217-223) + n. 20 + section 3.3.3 range
bins   = {e: B(sub(CW,era=e)) for e in C.PERIOD_ORDER}
nopart = {e: C.ldi(AK(sub(CW,era=e)),exclude_particles=True)[0] for e in C.PERIOD_ORDER}
nores  = {e: B(sub(CWP,era=e)) for e in C.PERIOD_ORDER}
inal   = {e: C.ldi(AK(sub(CW,era=e)),monogram_as_log=True)[0] for e in C.PERIOD_ORDER}
peff = [bins[e]-nopart[e] for e in C.PERIOD_ORDER]
reff = [bins[e]-nores[e]  for e in C.PERIOD_ORDER]
ck("prose particle-effect min", min(peff), 0.024, 3)
ck("prose particle-effect max", max(peff), 0.046, 3)
ck("prose restor-effect min",  min(reff), 0.013, 3)
ck("prose restor-effect max",  max(reff), 0.019, 3)
ck("prose Neo ina/ana raise",  inal['Neo Period']-bins['Neo Period'], 0.072, 3)
rises = [bins['Middle Period']-bins['Old Period'],
         inal['Middle Period']-inal['Old Period'],
         nopart['Middle Period']-nopart['Old Period'],
         nores['Middle Period']-nores['Old Period']]
gm = {e: G(sub(CS,era=e)) for e in C.PERIOD_ORDER}
gp = {e: C.graded_ldi(C._drop_contentless(AK(sub(CS,era=e))), exclude_particles=True) for e in C.PERIOD_ORDER}
rises += [gm['Middle Period']['macro']-gm['Old Period']['macro'],
          gm['Middle Period']['micro']-gm['Old Period']['micro'],
          gp['Middle Period']['micro']-gp['Old Period']['micro']]
ck("prose O->M rise baseline", bins['Middle Period']-bins['Old Period'], 0.369, 3)
ck("prose O->M rise min", min(rises), 0.311, 3)
ck("prose O->M rise max", max(rises), 0.422, 3)
seven = [C.ldi(AK(CW),monogram_as_log=True)[0], B(CW), B(CWP), C.ldi(AK(CW),exclude_particles=True)[0],
         G(CS)['macro'], G(CS)['micro'],
         C.graded_ldi(C._drop_contentless(AK(CS)), exclude_particles=True)['micro']]
ck("n20/3.3.3 spread floor", min(seven), 0.465, 3)
ck("n20/3.3.3 spread ceiling", max(seven), 0.736, 3)

# monogram paragraph counts
tok = CW[CW['type'].isin(['logogram','phonetic'])]
one, full = tok.token.isin(['ina','ana']), tok.token.isin(['i-na','a-na'])
for e,eo,ef in [('Old Period',6,453),('Middle Period',1157,209),('Neo Period',2777,92)]:
    m = tok.era==e
    ck(f"prose ina/ana one-sign {e.split()[0]}", int((one&m).sum()), eo, 'int')
    ck(f"prose ina/ana spelled {e.split()[0]}",  int((full&m).sum()), ef, 'int')

# ============================================================ extispicy ====
EXT = CW[CW.genre=='extispicy omens']; EXTP = CWP[CWP.genre=='extispicy omens']
EXTS = CS[CS.genre=='extispicy omens']
for e,o,t,b in [('Old Period',188,13,0.27),('Middle Period',1212,37,0.70),('Neo Period',534,16,0.71)]:
    d=sub(EXT,era=e)
    ck(f"T6 ext {e.split()[0]} omens", nom(d), o,'int'); ck(f"T6 ext {e.split()[0]} texts", ntx(d), t,'int')
    ck(f"T6 ext {e.split()[0]} bin", B(d), b, 2)
ck("T6 ext total bin", B(EXT), 0.66, 2)
for e,exp in [('Old Period',0.26),('Middle Period',0.62),('Neo Period',0.62)]:
    ck(f"T6 ext {e.split()[0]} macro", G(sub(EXTS,era=e))['macro'], exp, 2)
for e,exp in [('Old Period',0.14),('Middle Period',0.51),('Neo Period',0.52)]:
    ck(f"T6 ext {e.split()[0]} micro", G(sub(EXTS,era=e))['micro'], exp, 2)
ck("T6 ext total macro", G(EXTS)['macro'], 0.59, 2)
ck("T6 ext total micro", G(EXTS)['micro'], 0.46, 2)

# T7 subsection omen counts
T7 = {'bab-ekallim':[26,0,0],'martu':[40,262,136],'naplastu':[26,122,79],
      'padanu':[13,98,221],'pu':[0,54,0],'qerbu':[0,72,0],'lung':[83,568,98]}
for feat,(o1,o2,o3) in T7.items():
    for e,exp in zip(C.PERIOD_ORDER,[o1,o2,o3]):
        d = sub(EXT,feature=feat,era=e) if feat!='lung' else sub(EXT,era=e,contains='extispicy/lung/')
        if exp or len(d): ck(f"T7 {feat} {e.split()[0]}", nom(d), exp, 'int')

# T8 martu (Neo excludes VAT 8611)
MAR = sub(EXT,feature='martu'); MARS = sub(EXTS,feature='martu')
mNeo  = MAR[(MAR.era=='Neo Period')&(MAR.filename!='VAT.8611.txt')]
mNeoS = MARS[(MARS.era=='Neo Period')&(MARS.filename!='VAT.8611.txt')]
ck("T8 martu Old bin",  B(sub(MAR,era='Old Period')), 0.12, 2)
ck("T8 martu Mid bin",  B(sub(MAR,era='Middle Period')), 0.69, 2)
ck("T8 martu Neo bin",  B(mNeo), 0.72, 2)
ck("T8 martu Neo omens", nom(mNeo), 109, 'int')
ck("T8 martu Old macro", G(sub(MARS,era='Old Period'))['macro'], 0.12, 2)
ck("T8 martu Mid macro", G(sub(MARS,era='Middle Period'))['macro'], 0.61, 2)
ck("T8 martu Neo macro", G(mNeoS)['macro'], 0.63, 2)
ck("T8 martu Old micro", G(sub(MARS,era='Old Period'))['micro'], 0.06, 2)
ck("T8 martu Mid micro", G(sub(MARS,era='Middle Period'))['micro'], 0.47, 2)
ck("T8 martu Neo micro", G(mNeoS)['micro'], 0.51, 2)
v8 = MAR[MAR.filename=='VAT.8611.txt']; v8s = MARS[MARS.filename=='VAT.8611.txt']
ck("T8 VAT8611 omens", nom(v8), 27, 'int')
ck("T8 VAT8611 bin",   B(v8), 0.18, 2)
ck("T8 VAT8611 macro", G(v8s)['macro'], 0.18, 2)
ck("T8 VAT8611 micro", G(v8s)['micro'], 0.09, 2)
allNeo = sub(MAR,era='Neo Period'); allNeoS = sub(MARS,era='Neo Period')
ck("T8/n43 martu Neo incl-8611 bin", B(allNeo), 0.60, 2)
ck("3.1.2 prose incl macro", G(allNeoS)['macro'], 0.53, 2)
ck("3.1.2 prose incl micro", G(allNeoS)['micro'], 0.39, 2)

# T9 naplastu, T10 padanu
NAP=sub(EXT,feature='naplastu'); NAPS=sub(EXTS,feature='naplastu')
for e,b,g_,m in [('Old Period',0.04,0.04,0.02),('Middle Period',0.71,0.62,0.55),('Neo Period',0.80,0.69,0.61)]:
    ck(f"T9 napl {e.split()[0]} bin", B(sub(NAP,era=e)), b, 2)
    ck(f"T9 napl {e.split()[0]} macro", G(sub(NAPS,era=e))['macro'], g_, 2)
    ck(f"T9 napl {e.split()[0]} micro", G(sub(NAPS,era=e))['micro'], m, 2)
ck("T9 napl total bin", B(NAP), 0.68, 2)
PAD=sub(EXT,feature='padanu'); PADS=sub(EXTS,feature='padanu')
for e,b,g_,m in [('Old Period',0.00,0.00,0.00),('Middle Period',0.72,0.68,0.63),('Neo Period',0.73,0.64,0.55)]:
    ck(f"T10 pad {e.split()[0]} bin", B(sub(PAD,era=e)), b, 2)
    ck(f"T10 pad {e.split()[0]} macro", G(sub(PADS,era=e))['macro'], g_, 2)
    ck(f"T10 pad {e.split()[0]} micro", G(sub(PADS,era=e))['micro'], m, 2)
ck("T10 pad total bin", B(PAD), 0.70, 2)

# T11 liver by region (Middle only, Babylonia vs Assyria; Emar excluded)
for feat,W_,S_,vals in [('martu',MAR,MARS,(0.71,0.62,0.46,0.81,0.71,0.64)),
                        ('naplastu',NAP,NAPS,(0.70,0.63,0.55,0.82,0.70,0.66)),
                        ('padanu',PAD,PADS,(0.86,0.77,0.65,0.69,0.65,0.62))]:
    # find-spot groupings (T11 caption); the unprovenanced Sealand-tradition
    # CUSAS witness counts as Babylonia (the article's naplastu MB row).
    def _mb(d):
        tr = d['tradition'] if 'tradition' in d.columns else pd.Series('', index=d.index)
        return (d.region=='Babylonia') | ((d.region=='Unassigned') & (tr=='Babylonian'))
    mb  = W_[(W_.era=='Middle Period')&_mb(W_)]
    mbs = S_[(S_.era=='Middle Period')&_mb(S_)]
    ma  = W_[(W_.era=='Middle Period')&(W_.region=='Assyria')]
    mas = S_[(S_.era=='Middle Period')&(S_.region=='Assyria')]
    ck(f"T11 {feat} MB bin",  B(mb), vals[0],2); ck(f"T11 {feat} MB macro", G(mbs)['macro'], vals[1],2)
    ck(f"T11 {feat} MB micro",G(mbs)['micro'],vals[2],2)
    ck(f"T11 {feat} MA bin",  B(ma), vals[3],2); ck(f"T11 {feat} MA macro", G(mas)['macro'], vals[4],2)
    ck(f"T11 {feat} MA micro",G(mas)['micro'],vals[5],2)

# T13 Emar liver rows
for f,vals in [('Emar.669.txt',(0.50,0.47,0.31)),('Emar.670.txt',(0.59,0.54,0.44))]:
    ck(f"T13 {f} bin",  B(CW[CW.filename==f]), vals[0],2)
    ck(f"T13 {f} macro",G(CS[CS.filename==f])['macro'], vals[1],2)
    ck(f"T13 {f} micro",G(CS[CS.filename==f])['micro'], vals[2],2)

# T14 lung
LNG=sub(EXT,contains='extispicy/lung/'); LNGS=sub(EXTS,contains='extispicy/lung/')
for e,b,g_,m in [('Old Period',0.37,0.35,0.20),('Middle Period',0.75,0.67,0.57),('Neo Period',0.74,0.68,0.60)]:
    ck(f"T14 lung {e.split()[0]} bin", B(sub(LNG,era=e)), b, 2)
    ck(f"T14 lung {e.split()[0]} macro", G(sub(LNGS,era=e))['macro'], g_, 2)
    ck(f"T14 lung {e.split()[0]} micro", G(sub(LNGS,era=e))['micro'], m, 2)
ck("T14 lung total bin", B(LNG), 0.70, 2)

# outliers in 3.1
ck("3.1 VAT10206 bin", B(CW[CW.filename=='VAT.10206.txt']), 0.29, 2)

# T15 models/orientation (comparanda + kal5 VAT 9580, stripped)
MODW = load_stripped(lambda r: r in ('_comparanda/CTN4-60-lung-model.txt',
                                     '_comparanda/K.2858-liver-lung-model.txt',
                                     '_comparanda/KAR.444-lung-model.txt'))
MODS = load_stripped(lambda r: r in ('_comparanda/CTN4-60-lung-model.txt',
                                     '_comparanda/K.2858-liver-lung-model.txt',
                                     '_comparanda/KAR.444-lung-model.txt'), annotate=C.annotate_signs)
for f,lab,vals,lines in [('CTN4-60-lung-model.txt','IM64183',(0.79,0.76,0.70),119),
                         ('KAR.444-lung-model.txt','VAT9580',(0.71,0.68,0.58),39),
                         ('K.2858-liver-lung-model.txt','K2858',(0.75,0.71,0.64),75)]:
    d=MODW[MODW.filename==f]; ds=MODS[MODS.filename==f]
    ck(f"T15 {lab} lines", nom(d), lines,'int')
    ck(f"T15 {lab} bin",  B(d), vals[0],2)
    ck(f"T15 {lab} macro",G(ds)['macro'], vals[1],2)
    ck(f"T15 {lab} micro",G(ds)['micro'], vals[2],2)

# ============================================================= astrology ====
AST = CW[CW.genre=='astrological omens']; ASTS = CS[CS.genre=='astrological omens']
ASTP = CWP[CWP.genre=='astrological omens']
for e,o,t,b,g_,m in [('Old Period',286,6,0.48,0.47,0.34),
                     ('Middle Period',274,7,0.69,0.64,0.55),
                     ('Neo Period',453,8,0.73,0.66,0.62)]:
    d=sub(AST,era=e)
    ck(f"T17 astro {e.split()[0]} omens", nom(d), o,'int')
    ck(f"T17 astro {e.split()[0]} bin", B(d), b, 2)
    ck(f"T17 astro {e.split()[0]} macro", G(sub(ASTS,era=e))['macro'], g_, 2)
    ck(f"T17 astro {e.split()[0]} micro", G(sub(ASTS,era=e))['micro'], m, 2)

# BM 86381 (OB) prose 0.53
ck("3.2.1 BM86381 bin", B(CW[CW.filename=='BM.86381.txt']), 0.53, 2)
ck("3.2.1 BM86381 omens", nom(CW[CW.filename=='BM.86381.txt']), 66, 'int')
ck("3.2.1 MS3119 bin", B(CW[CW.filename=='MS.3119.txt']), 0.84, 2)

# restored share helper: share of scored words supplied by the editor
def rshare(fn=None, frame=CW, framep=CWP, mask=None):
    d  = frame if mask is None else frame[mask(frame)]
    dp = framep if mask is None else framep[mask(framep)]
    if fn: d, dp = d[d.filename==fn], dp[dp.filename==fn]
    d, dp = AK(d), AK(dp)
    a = len(C._drop_contentless(d[d['type'].isin(['logogram','phonetic'])]))
    b = len(C._drop_contentless(dp[dp['type'].isin(['logogram','phonetic'])]))
    return 100.0*(a-b)/a if a else 0.0
def binp(fn):  return B(CWP[CWP.filename==fn])
def binf(fn):  return B(CW[CW.filename==fn])

# Table 18
oldm = lambda d: (d.genre=='astrological omens')&(d.era=='Old Period')
ck("T18 Old with-rec",  B(sub(AST,era='Old Period')), 0.48, 2)
ck("T18 Old preserved", B(sub(ASTP,era='Old Period')), 0.47, 2)
ck("T18 Old restored%", rshare(mask=oldm), 9, 'int')
for fn,a,b_,r in [('BM.121034.txt',0.74,0.63,62),('MS.3119.txt',0.84,0.84,2),
                  ('IM.124485.txt',0.66,0.66,10)]:
    ck(f"T18 {fn} with-rec", binf(fn), a, 2)
    ck(f"T18 {fn} preserved", binp(fn), b_, 2)
    ck(f"T18 {fn} restored%", rshare(fn), r, 'int')
# T18's "EAE 20, Rec. A/B" rows are the pooled recension WITNESSES (Sm 246 +
# Rm 267 for A; K 3561 for B), not the eBL composite files: the composites are
# largely editor-restored, so a restored-share on them is not meaningful.
WA = load_stripped(lambda r: r in ('new/astrology/Sm.246.txt','new/astrology/Rm.267.txt'))
WAP = load_stripped(lambda r: r in ('new/astrology/Sm.246.txt','new/astrology/Rm.267.txt'), preserved=True)
WB = load_stripped(lambda r: r=='new/astrology/K.3561.txt')
WBP = load_stripped(lambda r: r=='new/astrology/K.3561.txt', preserved=True)
def rshare2(d, dp):
    d, dp = AK(d), AK(dp)
    a = len(C._drop_contentless(d[d['type'].isin(['logogram','phonetic'])]))
    b = len(C._drop_contentless(dp[dp['type'].isin(['logogram','phonetic'])]))
    return 100.0*(a-b)/a if a else 0.0
ck("T18 EAE20A with-rec", B(WA), 0.71, 2)
ck("T18 EAE20A preserved", B(WAP), 0.71, 2)
ck("T18 EAE20A restored%", rshare2(WA, WAP), 32, 'int')
ck("T18 EAE20B with-rec", B(WB), 0.71, 2)
ck("T18 EAE20B preserved", B(WBP), 0.70, 2)
ck("T18 EAE20B restored%", rshare2(WB, WBP), 23, 'int')

# Table 19 Middle astrology by region
PERI = ['Emar.651.txt','Emar.652.txt','Emar.653.txt','KBo.13.27.txt','KUB.4.64.txt']
mB = CW[(CW.filename=='BM.121034.txt')]
mP = CW[CW.filename.isin(PERI)]
ck("T19 Assyria omens", nom(mB), 51, 'int')
ck("T19 Assyria bin", B(mB), 0.74, 2)
ck("T19 Assyria macro", G(CS[CS.filename=='BM.121034.txt'])['macro'], 0.68, 2)
ck("T19 Assyria micro", G(CS[CS.filename=='BM.121034.txt'])['micro'], 0.64, 2)
ck("T19 Assyria restor", binp('BM.121034.txt'), 0.63, 2)
ck("T19 periphery omens", nom(mP), 207, 'int')
ck("T19 periphery bin", B(mP), 0.67, 2)
ck("T19 periphery macro", G(CS[CS.filename.isin(PERI)])['macro'], 0.62, 2)
ck("T19 periphery micro", G(CS[CS.filename.isin(PERI)])['micro'], 0.51, 2)
ck("T19 periphery restor", B(CWP[CWP.filename.isin(PERI)]), 0.65, 2)
ck("T19 MS3119 bin", binf('MS.3119.txt'), 0.84, 2)
ck("T19 MS3119 restor", binp('MS.3119.txt'), 0.84, 2)
# 3.2.3 convention claims on the Assyria-periphery gap
ck("3.2.3 gap noparticle A", C.ldi(AK(mB),exclude_particles=True)[0], 0.71, 2)
ck("3.2.3 gap noparticle P", C.ldi(AK(mP),exclude_particles=True)[0], 0.64, 2)
ck("3.2.3 gap inaana A", C.ldi(AK(mB),monogram_as_log=True)[0], 0.86, 2)
ck("3.2.3 gap inaana P", C.ldi(AK(mP),monogram_as_log=True)[0], 0.76, 2)

# Table 20 witnesses (held-out singles + IM 124485), with token counts
HO = load_stripped(lambda r: r in ('new/astrology/Sm.246.txt','new/astrology/Rm.267.txt',
                                   'new/astrology/K.3561.txt'))
HOS = load_stripped(lambda r: r in ('new/astrology/Sm.246.txt','new/astrology/Rm.267.txt',
                                    'new/astrology/K.3561.txt'), annotate=C.annotate_signs)
def toks(d):
    d = AK(d)
    return len(C._drop_contentless(d[d['type'].isin(['logogram','phonetic'])]))
for f,o,tk,b,g_,m in [('Sm.246.txt',3,206,0.71,0.60,0.56),('Rm.267.txt',2,229,0.72,0.62,0.63),
                      ('K.3561.txt',13,790,0.71,0.63,0.61)]:
    d=HO[HO.filename==f]; ds=HOS[HOS.filename==f]
    ck(f"T20 {f} omens", nom(d), o,'int')
    ck(f"T20 {f} tokens", toks(d), tk,'int')
    ck(f"T20 {f} bin", B(d), b,2)
    ck(f"T20 {f} macro", G(ds)['macro'], g_,2)
    ck(f"T20 {f} micro", G(ds)['micro'], m,2)
d=CW[CW.filename=='IM.124485.txt']; ds=CS[CS.filename=='IM.124485.txt']
ck("T20 IM124485 omens", nom(d), 7,'int'); ck("T20 IM124485 tokens", toks(d), 606,'int')
ck("T20 IM124485 bin", B(d), 0.66,2)
ck("T20 IM124485 macro", G(ds)['macro'], 0.57,2); ck("T20 IM124485 micro", G(ds)['micro'], 0.52,2)

# Table 21 cross-topic check
ECL = [f for f in RP if re.match(r'new/astrology/EAE2[012]/', RP[f])]
E55 = [f for f in RP if RP[f].startswith('new/astrology/EAE55')]
E57 = [f for f in RP if RP[f].startswith('new/astrology/EAE57')]
def compo(ds):
    g=G(ds); n=g['pure']+g['mixed']+g['syllabic']; return g,100*g['pure']/n,100*g['mixed']/n,100*g['syllabic']/n
for lab,fl,o,t,vals in [('EAE20+21+22',ECL,215,5,(0.72,0.64,0.62,56.3,16.0,27.7)),
                        ('EAE55',E55,107,1,(0.75,0.70,0.66,65.2,10.0,24.8)),
                        ('EAE57',E57,116,1,(0.77,0.73,0.68,68.5,8.3,23.2))]:
    d=CW[CW.filename.isin(fl)]; ds=CS[CS.filename.isin(fl)]
    ck(f"T21 {lab} omens", nom(AK(d)), o,'int')   # scored omens (n. 99)
    ck(f"T21 {lab} bin", B(d), vals[0],2)
    g,pu,mx,sy=compo(ds)
    ck(f"T21 {lab} macro", g['macro'], vals[1],2); ck(f"T21 {lab} micro", g['micro'], vals[2],2)
    ck(f"T21 {lab} pure", pu, vals[3],'pct1'); ck(f"T21 {lab} mixed", mx, vals[4],'pct1')
    ck(f"T21 {lab} syll", sy, vals[5],'pct1')
ALL5=ECL+E55+E57
d=CW[CW.filename.isin(ALL5)]; ds=CS[CS.filename.isin(ALL5)]
ck("T21 pooled omens", nom(AK(d)), 438,'int'); ck("T21 pooled bin", B(d), 0.73,2)
g,pu,mx,sy=compo(ds)
ck("T21 pooled macro", g['macro'], 0.66,2); ck("T21 pooled micro", g['micro'], 0.63,2)
ck("T21 pooled pure", pu, 59.2,'pct1'); ck("T21 pooled mixed", mx, 14.1,'pct1')
ck("T21 pooled syll", sy, 26.7,'pct1')
# n. 57 KBo 8.6 ~0.09
KB = load_stripped(lambda r: r=='middle/astrology/KBo.8.6.txt')
ck("n57 KBo8.6 bin (~)", B(KB), 0.09, 1)

# ============================================================ diagnostic ====
DIA = CW[CW.genre=='diagnostic omens']; DIAS = CS[CS.genre=='diagnostic omens']
for e,o,b,g_,m in [('Old Period',33,0.13,0.12,0.06),('Middle Period',230,0.51,0.44,0.31),
                   ('Neo Period',1173,0.74,0.61,0.54)]:
    ck(f"T23 diag {e.split()[0]} omens", nom(sub(DIA,era=e)), o,'int')
    ck(f"T23 diag {e.split()[0]} bin", B(sub(DIA,era=e)), b,2)
    ck(f"T23 diag {e.split()[0]} macro", G(sub(DIAS,era=e))['macro'], g_,2)
    ck(f"T23 diag {e.split()[0]} micro", G(sub(DIAS,era=e))['micro'], m,2)
ck("T23 diag total bin", B(DIA), 0.68,2)
ck("T23 diag total macro", G(DIAS)['macro'], 0.57,2)
ck("T23 diag total micro", G(DIAS)['micro'], 0.47,2)

SY_M = ['CBS.12580.txt','CBS.3424.txt','Ni.470.txt','Emar.694.txt']
PR_M = ['VAT.10235.txt','VAT.10748.txt','VAT.11122.txt','IM.57947.txt','MDP57.txt',
        'StBoT36.A.txt','StBoT36.B.txt','StBoT36.C.txt','Emar.695.txt']
ck("T22 symptoms Middle", nom(DIA[DIA.filename.isin(SY_M)]), 57,'int')
ck("T22 prognosis Middle", nom(DIA[DIA.filename.isin(PR_M)]), 173,'int')

ck("3.3.1 IM57947 bin", B(CW[CW.filename=='IM.57947.txt']), 0.72, 2)
mid_wo = DIA[(DIA.era=='Middle Period')&(DIA.filename!='IM.57947.txt')]
ck("3.3.1 Middle diag w/o IM57947", B(mid_wo), 0.47, 2)

MBd = ['CBS.12580.txt','CBS.3424.txt','Ni.470.txt']
MAd = ['VAT.10235.txt','VAT.10748.txt','VAT.11122.txt']
def compo3(ds):
    g=G(ds); n=g['pure']+g['mixed']+g['syllabic']
    return g,100*g['pure']/n,100*g['mixed']/n,100*g['syllabic']/n
for lab,fl,vals in [('Mid-Bab',MBd,(0.55,0.48,0.35,37.5,17.6,44.8)),
                    ('Mid-Ass',MAd,(0.62,0.51,0.44,37.4,24.6,38.1))]:
    d=DIA[DIA.filename.isin(fl)]; ds=DIAS[DIAS.filename.isin(fl)]
    ck(f"T24 {lab} bin", B(d), vals[0],2)
    g,pu,mx,sy = compo3(ds)
    ck(f"T24 {lab} macro", g['macro'], vals[1],2); ck(f"T24 {lab} micro", g['micro'], vals[2],2)
    ck(f"T24 {lab} pure", pu, vals[3],'pct1'); ck(f"T24 {lab} mixed", mx, vals[4],'pct1')
    ck(f"T24 {lab} syll", sy, vals[5],'pct1')
ck("T24 note Mid-Bab incl IM57947", B(DIA[DIA.filename.isin(MBd+['IM.57947.txt'])]), 0.63, 2)
NEO = DIA[DIA.era=='Neo Period']; NEOS = DIAS[DIAS.era=='Neo Period']
for lab,reg,vals in [('Neo-Bab','Babylonia',(0.73,0.62,0.54,45.4,28.3,26.3)),
                     ('Neo-Ass','Assyria',(0.76,0.63,0.56,45.7,30.5,23.9))]:
    d=NEO[NEO.region==reg]; ds=NEOS[NEOS.region==reg]
    ck(f"T24 {lab} bin", B(d), vals[0],2)
    g,pu,mx,sy = compo3(ds)
    ck(f"T24 {lab} macro", g['macro'], vals[1],2); ck(f"T24 {lab} micro", g['micro'], vals[2],2)
    ck(f"T24 {lab} pure", pu, vals[3],'pct1'); ck(f"T24 {lab} mixed", mx, vals[4],'pct1')
    ck(f"T24 {lab} syll", sy, vals[5],'pct1')
gapM  = B(DIA[DIA.filename.isin(MAd)]) - B(DIA[DIA.filename.isin(MBd)])
gapMi = C.ldi(AK(DIA[DIA.filename.isin(MAd)]),monogram_as_log=True)[0] - \
        C.ldi(AK(DIA[DIA.filename.isin(MBd)]),monogram_as_log=True)[0]
ck("3.3.2 offset Middle", gapM, 0.07, 2)
ck("3.3.2 offset ina/ana", gapMi, 0.12, 2)

STB = ['StBoT36.A.txt','StBoT36.B.txt','StBoT36.C.txt']
for lab,fl,vals in [('Emar694',['Emar.694.txt'],(0.45,0.35,0.31)),
                    ('Emar695',['Emar.695.txt'],(0.61,0.58,0.67)),
                    ('MDP57',['MDP57.txt'],(0.56,0.50,0.30)),
                    ('StBoT',STB,(0.24,0.21,0.11))]:
    d=DIA[DIA.filename.isin(fl)]; ds=DIAS[DIAS.filename.isin(fl)]
    ck(f"T25 {lab} bin", B(d), vals[0],2)
    ck(f"T25 {lab} macro", G(ds)['macro'], vals[1],2)
    ck(f"T25 {lab} micro", G(ds)['micro'], vals[2],2)

# ================================================================= izbu ====
IZ = CW[CW.genre=='izbu omens']; IZS = CS[CS.genre=='izbu omens']
for e,b,g_,m in [('Old Period',0.19,0.17,0.09),('Middle Period',0.70,0.63,0.50),
                 ('Neo Period',0.82,0.75,0.64)]:
    ck(f"T27 izbu {e.split()[0]} bin", B(sub(IZ,era=e)), b,2)
    ck(f"T27 izbu {e.split()[0]} macro", G(sub(IZS,era=e))['macro'], g_,2)
    ck(f"T27 izbu {e.split()[0]} micro", G(sub(IZS,era=e))['micro'], m,2)
HATI=['Ankara-10605.txt','Bogh-1959-56.txt','KUB29-12.txt','KUB37-183.txt','KUB37-184.txt',
      'KUB37-185.txt','KUB37-188.txt','KUB4-67.txt']
GRPS=[('Mid-Bab',['VAT.17080.txt','VAT.17259.txt','UM.29-16-194.txt'],56,(0.77,0.67,0.62,51.0,26.2,22.8)),
      ('Mid-Ass',['VAT.9908.txt'],18,(0.92,0.90,0.82,87.5,4.5,8.0)),
      ('Mid-Susa',['Suse.XII-4.txt','Suse.XII-6.txt'],99,(0.85,0.76,0.64,61.8,26.5,11.7)),
      ('Mid-Hatt',HATI,47,(0.33,0.31,0.19,27.3,5.7,66.9)),
      ('Neo-Bab',['BM.33793.txt','BM.52728.txt','W.23271.txt','W.23272.txt'],334,(0.82,0.74,0.63,64.2,17.7,18.1)),
      ('Neo-Ass',['K.131.txt','K.2242.txt','K.3688.txt','K.3695.txt','K.4031.txt','K.8806.txt','Sm.502.txt'],358,(0.83,0.76,0.66,65.3,19.3,15.4))]
for lab,fl,o,vals in GRPS:
    d=IZ[IZ.filename.isin(fl)]; ds=IZS[IZS.filename.isin(fl)]
    ck(f"T28 {lab} omens", nom(d), o,'int')
    ck(f"T28 {lab} bin", B(d), vals[0],2)
    g,pu,mx,sy = compo3(ds)
    ck(f"T28 {lab} macro", g['macro'], vals[1],2); ck(f"T28 {lab} micro", g['micro'], vals[2],2)
    ck(f"T28 {lab} pure", pu, vals[3],'pct1'); ck(f"T28 {lab} mixed", mx, vals[4],'pct1')
    ck(f"T28 {lab} syll", sy, vals[5],'pct1')
ck("T28 VAT9908 restor-dropped", B(CWP[CWP.filename=='VAT.9908.txt']), 0.90, 2)

# ============================================================ terrestrial ====
TE = CW[CW.genre=='terrestrial omens']; TES = CS[CS.genre=='terrestrial omens']
TEP = CWP[CWP.genre=='terrestrial omens']
for e,b,g_,m in [('Old Period',0.28,0.27,0.13),('Middle Period',0.74,0.68,0.59),
                 ('Neo Period',0.76,0.69,0.61)]:
    ck(f"T30 terr {e.split()[0]} bin", B(sub(TE,era=e)), b,2)
    ck(f"T30 terr {e.split()[0]} macro", G(sub(TES,era=e))['macro'], g_,2)
    ck(f"T30 terr {e.split()[0]} micro", G(sub(TES,era=e))['micro'], m,2)
ck("T30 terr total bin", B(TE), 0.71,2)
ck("T30 terr total macro", G(TES)['macro'], 0.65,2)
ck("T30 terr total micro", G(TES)['micro'], 0.55,2)
ck("3.5.1 VAT10849 bin", B(CW[CW.filename=='VAT.10849.txt']), 0.38, 2)
MAT = [f for f in TE[TE.era=='Middle Period'].filename.unique() if f.startswith('VAT.')]
ck("3.5.2 Mid-Ass text count", len(MAT), 15, 'int')
for lab,d,ds,vals in [('Mid-Bab',TE[TE.filename=='BM.108874.txt'],TES[TES.filename=='BM.108874.txt'],(0.79,0.72,0.64)),
                      ('Mid-Ass',TE[TE.filename.isin(MAT)],TES[TES.filename.isin(MAT)],(0.74,0.67,0.59)),
                      ('Mid-Hatt',TE[TE.filename=='KBo.36.47.txt'],TES[TES.filename=='KBo.36.47.txt'],(0.64,0.55,0.38))]:
    ck(f"T31 {lab} bin", B(d), vals[0],2)
    ck(f"T31 {lab} macro", G(ds)['macro'], vals[1],2)
    ck(f"T31 {lab} micro", G(ds)['micro'], vals[2],2)
ck("T31 KBo36.47 restor-dropped", B(TEP[TEP.filename=='KBo.36.47.txt']), 0.50, 2)
lead   = B(TE[TE.filename=='BM.108874.txt']) - B(TE[TE.filename.isin(MAT)])
lead_i = C.ldi(AK(TE[TE.filename=='BM.108874.txt']),monogram_as_log=True)[0] - \
         C.ldi(AK(TE[TE.filename.isin(MAT)]),monogram_as_log=True)[0]
ck("3.5.2 Bab lead", lead, 0.05, 2)
ck("3.5.2 Bab lead ina/ana", lead_i, 0.08, 2)

# ========================================================== conclusions ====
CMPW = load_stripped(lambda r: r in ('_comparanda/Maqlu-K.2385.txt',
                                     '_comparanda/Great-Prayer-to-Nabu-K.2361.txt'))
CMPS = load_stripped(lambda r: r in ('_comparanda/Maqlu-K.2385.txt',
                                     '_comparanda/Great-Prayer-to-Nabu-K.2361.txt'),
                     annotate=C.annotate_signs)
for f,lab,lines,vals in [('Maqlu-K.2385.txt','Maqlu',119,(0.60,0.53,0.46,45.8,13.6,40.6)),
                         ('Great-Prayer-to-Nabu-K.2361.txt','Nabu',184,(0.08,0.06,0.04,5.1,3.3,91.5))]:
    d=CMPW[CMPW.filename==f]; ds=CMPS[CMPS.filename==f]
    ck(f"T32 {lab} lines", nom(d), lines,'int')
    ck(f"T32 {lab} bin",  B(d), vals[0],2)
    ck(f"T32 {lab} macro",G(ds)['macro'], vals[1],2)
    ck(f"T32 {lab} micro",G(ds)['micro'], vals[2],2)
    g = G(ds); n = g['pure']+g['mixed']+g['syllabic']
    ck(f"T32 {lab} pure",  100*g['pure']/n,  vals[3],'pct1')
    ck(f"T32 {lab} mixed", 100*g['mixed']/n, vals[4],'pct1')
    ck(f"T32 {lab} syll",  100*g['syllabic']/n, vals[5],'pct1')

# Table 32's reference band: the range across the five Neo disciplines
_band = {}
for _g in ('astrological omens','diagnostic omens','extispicy omens',
           'izbu omens','terrestrial omens'):
    _gg = G(CS[(CS.genre==_g)&(CS.era=='Neo Period')])
    _n = _gg['pure']+_gg['mixed']+_gg['syllabic']
    for _k in ('pure','mixed','syllabic'):
        _band.setdefault(_k, []).append(100*_gg[_k]/_n)
for _k,_lab,_lo,_hi in [('pure','pure',44.8,64.8),('mixed','mixed',13.0,29.7),
                        ('syllabic','syll',16.8,29.0)]:
    ck(f"T32 band {_lab} low",  min(_band[_k]), _lo,'pct1')
    ck(f"T32 band {_lab} high", max(_band[_k]), _hi,'pct1')
ck("4.1 LB2126 bin", B(CW[CW.filename=='LB.2126.txt']), 0.03, 2)
E700 = load_stripped(lambda r: r=='middle/terrestrial/Emar.700.txt')
ck("n103 Emar700 bin", B(E700), 1.00, 2)

# n. 22 macro/micro orderings per text
per = []
for f, ds in CS.groupby('filename'):
    g = G(ds)
    bn = B(CW[CW.filename==f])
    per.append((f, bn, g['macro'], g['micro']))
eps=1e-9
n_gt  = sum(1 for _,_,ma,mi in per if ma>mi+eps)
n_eq  = sum(1 for _,_,ma,mi in per if abs(ma-mi)<=eps)
n_lt  = sum(1 for _,_,ma,mi in per if mi>ma+eps)
n_mb  = sum(1 for _,bn,ma,mi in per if mi>bn+eps)
ck("n22 macro>micro texts", n_gt, 181,'int')
ck("n22 macro=micro texts", n_eq, 7,'int')
ck("n22 micro>macro texts", n_lt, 7,'int')
ck("n22 micro>bin texts",   n_mb, 3,'int')

# T16 astrology subsection counts
MID_ECL=['BM.121034.txt','KBo.13.27.txt','KUB.4.64.txt','Emar.652.txt','MS.3119.txt']
NEO_ECL=[f for f in RP if re.match(r'new/astrology/EAE2[012]/',RP[f])]+['IM.124485.txt']
ck("T16 eclipse Old", nom(sub(AST,era='Old Period')), 286,'int')
ck("T16 eclipse Middle", nom(AST[AST.filename.isin(MID_ECL)]), 187,'int')
ck("T16 eclipse Neo", nom(AST[AST.filename.isin(NEO_ECL)]), 222,'int')
ck("T16 lunar-other (Emar651)", nom(AST[AST.filename=='Emar.651.txt']), 64,'int')
ck("T16 solar (Emar653)", nom(AST[AST.filename=='Emar.653.txt']), 23,'int')
ck("T16 fixed stars", nom(AST[AST.filename.isin(E55+E57)]), 231,'int')

# ------------------------------------------------------------- report ------
fails=[c for c in CHECKS if not c[0]]
print("\n" + "="*74)
print(f"CHECKS: {len(CHECKS)}   PASS: {len(CHECKS)-len(fails)}   FAIL: {len(fails)}")
print("="*74)
for ok,label,cs,exp in CHECKS:
    if not ok or VERBOSE:
        print(f"  {'ok ' if ok else 'DIFF'}  {label:<38} computed {cs:>9}   printed {exp}")
sys.exit(len(fails))
