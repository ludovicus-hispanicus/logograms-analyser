# Sakikkû parallels across milieus — the same omen, different orthography

This file collects the **directly parallel** diagnostic omens — cases where one and the
same canonical *Sakikkû* entry is attested in **two or more** of our second-millennium
witnesses, so that the *content is held constant* and only the scribal milieu varies.
These are the cleanest possible test of the article's central claim: that the logographic
density of an omen tracks the **scribal milieu**, not the omen itself.

The parallels are taken from **Schmidtchen 2021** (*Mesopotamische Diagnostik*, BAM 13),
"Konkordanz der Parallelen mB und mA Textzeugen aus diagnostischen Kontexten"
(book pp. 709–713). Each pairing below was then **verified against the actual text** in
our corpus files, independently of the canonical line-number.

## Method note and a caveat on coverage

Most rows of Schmidtchen's concordance list only **one** witness per canonical line — the
witnesses rarely overlap. After restricting to witnesses we hold on disk
(Nippur: CBS 12580, CBS 3424, Ni. 470, 2N-T 336 = IM 57947; Ḫattuša: StBoT 36 A/B/C only;
Emar: 694/695; Assur: VAT 10235/10748/11122; Susa: MDP 57), the genuine **cross-milieu**
parallels reduce to a small, high-value set — dominated by **Ḫattuša ‖ Assur** and one
**Nippur ‖ Ḫattuša** pair. They are listed first; the loose/fragmentary and
single-milieu-duplicate cases follow.

> **Correction.** An earlier pass (built from a mis-collated `pdftotext` of the table)
> recorded several wrong line→canonical mappings. Read off the rendered table, the
> corrected ones are: **MDP 57 Nr. 11 ii 1 = Sakikkû 13:63(?)**, **ii 2 = 14:71** (Susa
> only — *not* 11:68-69); and for VAT 10235: **:3′=16:45, :4′-6′=3:68, :7′-9′=3:79,
> :10′-11′=19/20:9, :12′=17:90, :19′-20′=3:86-90**. The CBS 12580 obverse runs
> Vs.1=11:68, Vs.2=11:84, Vs.3=11:69, Vs.4=14:245, Vs.5=12:5, Vs.6-7=14:30, Vs.9-13=3:55.

---

## The minimal pairs

LDI below is **excl. opening particle**, computed with the project's own
`compute_ratios.py`. `{d}` determinatives are excluded; `[ ]` are restorations.

### 1. Sakikkû ~3:79 — "chills keep falling on him"

| Witness | Milieu | Text | LDI |
|---|---|---|---:|
| **StBoT 36 C** Vs. 3′–4′ | Ḫattuša (13th c.) | `ḫu-ur-ba-a-šu im-ta-na-aq-qu-ut / i-ta-a-am` | **0.00** |
| **VAT 10235**:7′–9′ | Assur (MA) | `DIŠ ina SAG.DU-šu SIG-iṣ-ma ḫur-ba-šu [ŠUB.ŠUB-su …] GIM DAB-su ŠUB-su UŠ₄-su KUR-šu-ma […] DAB-it {d}DIM.ME.LAGAB […]` | **0.71** |
| **canon 3:79** (Schmidtchen 2021: 254) | 1st-mill. | `DIŠ ina SAG.DU-šú SÌG-iṣ-ma MIR.ŠEŠ ŠUB.ŠUB-su IGI.MEŠ-šú SA₅ u SIG₇ … DAB-it {d}KAMAD.ME.LAGAB … GAM` | **0.81** |

The shared core is *ḫurbāšu* (chills) + *maqātu* (to fall). Ḫattuša spells **both** out
(`ḫu-ur-ba-a-šu im-ta-na-aq-qu-ut`); Assur keeps *ḫurbāšu* syllabic but writes the verb
with the Sumerogram **`ŠUB.ŠUB`**; the canon writes **both** logographically
(**`MIR.ŠEŠ`** for *ḫurbāšu*, `ŠUB.ŠUB` for the verb). A clean monotone climb on the same
omen — **0.00 → 0.71 → 0.81** across milieu and time.

### 2. Sakikkû ~3:86-90 — "from his head to his feet, pustules … he reaches (a woman) in bed = Hand of a god"

| Witness | Milieu | Text | LDI |
|---|---|---|---:|
| **StBoT 36 C** Vs. 9′–12′ | Ḫattuša (13th c.) | `ŠU {d}XXX sà-de₄-er-šu iš-tu SAG.DU-šu a-di GIR.MEŠ-šu / zu-um-mu-ur-šu sa-a-am it-ti si-ni-il-ti i-na ma-ia-li ka-ši-id ŠU {d}UTU …` | **0.31** |
| **VAT 10235**:19′–20′ | Assur (MA) | `DIŠ TA SAG.DU-šu EN GIR.II-šu U.BU.BU.UL ša ma-li u [zumuršu peṣi] / KI MUNUS ina KI.NA ka-šid ŠU {d}EN.ZU` | **0.56** |
| **VAT 10748**:4 (Assur dup.) | Assur (MA) | `DIŠ TA SAG.DU-šu EN GIR.MEŠ-šu U.BU.[BU.UL SA₅]` | 1.00 |
| **canon 3:86 / 3:89** (Schmidtchen 2021: 255) | 1st-mill. | `DIŠ TA SAG.DU-šú EN GÌR.II-šú U₄.BU.BU.UL SA₅ DIRI u SU-šú BABBAR KI MUNUS ina KI.NÁ KUR ŠU XXX` (…3:89 `ŠU {d}UTU`) | **0.88** |

The minimal contrast is on the function-words and *majālu* "bed": Ḫattuša writes
`iš-tu … a-di … ma-ia-li` **syllabically**, Assur and the canon write the same with
**`TA` (ištu), `EN` (adi), `KI.NA/KI.NÁ` (majālu)** logographically. The Assur copy
VAT 10235:19-20 is **near-verbatim the canon** (3:86 = the Hand-of-Sin variant; 3:89 =
Hand of Šamaš, the very entry StBoT 36 C parallels), and the second Assur manuscript
(VAT 10748) duplicates the opening clause identically — so `TA … EN …` is the shared
Assyrian/canonical norm. Again a monotone climb: **0.31 → 0.56 → 0.88**.

### 3. Sakikkû 17:82(?) — "his illness seizes him in the evening/night"

| Witness | Milieu | Text | LDI |
|---|---|---|---:|
| **Ni. 470** Vs. 13 | Nippur | `DIŠ GIG-su ina GE₆.Ù.NA DIB.DIB-su x […]` | **0.75** |
| **StBoT 36 A** Vs. 4 | Ḫattuša | `mu-ru-us-su i-na si-mi-ta-a-an [ṣa]-bi-is-s[u] ma-ḫi-iṣ [BA.ÚŠ]` | **0.17** |
| **canon 17:82** (Heeßel 2000 Taf. 17) | 1st-mill. | `DIŠ ina si-mi-tan GIG-su DAB.DAB-su MAŠKIM` | **0.60** |

Schmidtchen flags the variant himself (`GE₆.Ù.NA statt si-me-tan` — night for evening).
And here the climb is **not** monotone: the canon writes *evening* **syllabically**
(`si-mi-tan`) — exactly as Ḫattuša does — and logographs only `GIG`, `DAB.DAB`, `MAŠKIM`,
landing at 0.60. **Nippur (0.75) out-logographs the canon** by substituting the Sumerogram
`GE₆.Ù.NA` for the very word the canon spells out. A useful corrective: the logographic
shift is a *trend*, not a law applied word-for-word; a single native workshop could push a
given lexeme past the eventual canon.
This is the sharpest pair because it sets **native Nippur against Ḫattuša**: Nippur writes
*every* content word logographically (`GIG-su` = murṣu, `GE₆.Ù.NA` = the time-word,
`DIB.DIB-su` = ṣabit), while Ḫattuša spells all of them out and keeps only the death-verdict
**`BA.ÚŠ`** logographic. 0.75 vs 0.17 — and it runs in the predicted direction
(Nippur cell 0.49 ≫ Ḫattuša cell 0.21).

---

## Secondary / weaker parallels

- **Sakikkû 3:94(?)** — Emar VI/4 694:21 ‖ VAT 10748:4 (Assur), both **fragmentary**;
  the canonical Ḫattuša partner (StBoT 36 H:2) is not in our corpus. Match is loose
  (both mention SAG.DU); not scored as a clean pair.
- **Assur-internal duplicates** (same milieu, control): VAT 10235 i ‖ VAT 10748 overlap
  at 10235:19/10748:4 and 10235:21–22/10748:5–6 — two Assur copies writing the same omens
  the same (logographic) way. Useful as a tradition-internal baseline, not a milieu contrast.

## All cross-witness rows in our corpus (Schmidtchen Konkordanz, pp. 709–713)

Only rows where ≥2 cited witnesses are **both on disk**:

| Sakikkû | Nippur | Ḫattuša | Emar | Assur | type |
|---|---|---|---|---|---|
| 3:79 | — | StBoT 36 C 3′–4′ | — | VAT 10235:7′–9′ | Ḫattuša ‖ Assur ✓ |
| 3:86–90 | — | StBoT 36 C 9′–12′ | — | VAT 10235:19′–20′ (‖ 10748:4) | Ḫattuša ‖ Assur ✓ |
| 17:82(?) | Ni. 470 Vs. 13 | StBoT 36 A Vs. 4 | — | — | Nippur ‖ Ḫattuša ✓ |
| 3:94(?) | — | (StBoT 36 H, n/a) | 694:21 | VAT 10748:4 | Emar ‖ Assur (frag.) |

Witnesses cited by the concordance but **not yet in our corpus** (would unlock more
parallels if ingested): StBoT 36 D₂, F, G, H, J, L, M, N (further Ḫattuša fragments),
and KUB 37,87 / KBo 7,13 / VBoT 54.

## Takeaway

Where the *same* omen survives in more than one milieu, the gap is large and consistent.
For the two Tablet 3 omens the canonical first-millennium version can be added (Schmidtchen
2021: 254-255, edited into [`data/new/diagnostic/Sakikku.canonical.txt`](../data/new/diagnostic/Sakikku.canonical.txt)),
turning each pair into a **monotone diachronic gradient on identical content**:

| omen | Ḫattuša | Assur | canon |
|---|---:|---:|---:|
| 3:79 (chills keep falling) | 0.00 | 0.71 | 0.81 |
| 3:86-90 (head-to-feet pustules) | 0.31 | 0.56 | 0.88 |
| 17:82 (illness seizes at evening) | 0.17 (Ḫattuša) | 0.75 (Nippur) | 0.60 (canon) |

For the two Tablet 3 omens the LDI rises step-by-step from the Anatolian periphery through
Middle Assyrian Assur to the first-millennium canon — exactly as the period-and-place
cells (§III) predict, and a second Assur copy (VAT 10748) plus the near-verbatim canon
confirm the logographic writing is the tradition norm, not scribal accident. The third omen
(17:82) is the honest exception that proves the rule: native **Nippur** logographs *evening*
(`GE₆.Ù.NA`) past even the canon, which keeps it syllabic (`si-mi-tan`) — so the gradient is
a trend over milieu and date, not a word-for-word law. In every case the index is measuring
the workshop and the period, not the omen.

---

## The canonical anchor: the most-paralleled tablets (3, 4, 14)

When we compare a second-millennium witness against "the canon," the obvious worry is
*which* canonical tablet we compare against. We therefore anchor on the canonical tablets
that carry the **most parallels to the older, second-millennium witnesses** — by
Schmidtchen 2021's Konkordanz, **Tablet 3 (15 parallels), Tablet 4 (13), and Tablet 14
(10)**, the top of the whole series. This is deliberate on two grounds:

1. **Comparability.** These are the tablets where the *same* omen is actually attested both
   in the second-millennium witnesses (Nippur, Ḫattuša, Emar, Assur, Susa) *and* in the
   canon, so a like-for-like, content-controlled comparison is possible at all. (They are
   also the *šer'ānu* "cords/veins" tablets — 3 the head, 4 the temple-veins `SA SAG.KI`,
   14 the cords of the limbs `SA ŠU.II / SA GÌR.II`.)

2. **Stability.** If the pooled canonical LDI is roughly the **same** across these three
   independently-sampled tablets, then the canonical value we measure against (~0.69) is a
   property of the recension, not an artefact of tablet choice — and adding further tablets
   would not move it materially. Each tablet is pooled over all its first-millennium
   manuscripts (`data/new/diagnostic/tablet3/`, `tablet4/`, …; computed with
   `scripts/folder_ldi.py`), which weights by preservation and averages out single-copy quirks.

| canonical tablet | parallels | pooled LDI (raw) | LDI (excl. particle) | mss | tokens |
|---|---:|---:|---:|---:|---:|
| Tablet 3 | 15 | 0.702 | **0.680** | 10 | 2385 |
| Tablet 4 | 13 | 0.729 | **0.695** | 10 | 2843 |
| Tablet 14 | 10 | 0.725 | **0.683** | 12 | 2289 |

The prediction holds. The three most-paralleled tablets — sampled completely independently
(32 different manuscripts in all; three different body-regions: head, temple-veins, limb-cords)
— agree to within **0.015** on the excl.-particle LDI: **0.680, 0.695, 0.683**. The canonical
diagnostic anchor is **stable**: the first-millennium *Sakikkû* writes its omens at ≈ 0.69
logographic density regardless of which of its most-attested tablets one measures. The
canonical value the cross-milieu comparison rests on is therefore a property of the recension,
not an artefact of tablet choice, and adding further tablets would not move it materially —
so the Ḫattuša→Assur→canon gradient is anchored on a representative, not a cherry-picked,
figure. (Pooled per tablet over `data/new/diagnostic/tablet{3,4,14}/` with
`scripts/folder_ldi.py`; manuscripts extracted by `scripts/parse_sakikku_ocr.py` /
`parse_sakikku_text.py` from Schmidtchen's score.)
