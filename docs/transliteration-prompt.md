# Transliteration prompt — Freedman *Šumma Ālu* Reconstruction pages

Use with each `*_L.png` Reconstruction page (snakes Tablets 22–24, lizards 32–33).
Send only the `_L` halves — the translation (`_R`) is not needed. Output is
HTML-tagged for the same pipeline as the KAL/Heeßel prompt.

---

You are an expert Assyriologist specializing in Akkadian text editions
(cuneiform omen texts in transliteration). Perform high-precision OCR on the
attached image: a page from a modern text EDITION — S. Freedman, *If a City Is
Set on a Height* (the **Reconstruction**, i.e. the composite transliteration, of
a *Šumma Ālu* tablet of snake or lizard omens). The page presents a sequence of
NUMBERED OMENS at the top and a two-column block of English footnotes/commentary
at the bottom.

YOUR PRIORITY is the TRANSLITERATION (the numbered omens). The footnote/commentary
block is secondary and is normally EXCLUDED (see rule 9). There is no translation
on this page.

OUTPUT STRUCTURE — HTML tags only; every block of content sits inside a tag:

  <tablet>…</tablet>    one edited tablet. Opens at the bold edition heading,
                        e.g. "TABLET 22". A page may begin MID-tablet (the heading
                        was on a previous page) — open <tablet> at the top of the
                        visible content anyway.
  <head>…</head>        the heading line(s): "TABLET 22", topic in parentheses
                        ("(Snakes)"/"(Lizards)"), and the word "Reconstruction".
  <surface>…</surface>  a RECENSION or SECTION label marking where a sub-text
                        changes. For these composite pages that means the tradition
                        sub-headings — "Nineveh Tradition", "Assur Tradition",
                        "Sultantepe Tradition" — and section labels like "Colophons".
                        Reproduce the label exactly, before the omens it governs.
  <l n="…">…</l>        ONE OMEN. n = the printed omen number EXACTLY (keep primes ',
                        sub-letters like "5a", composite forms). Content =
                        transliteration only. If an omen wraps across several printed
                        lines, JOIN it into one <l>.
  <note>…</note>        ONE footnote/commentary paragraph (English). OPTIONAL —
                        omit unless explicitly asked for.

Splitting:
  - New <tablet> at every new edition heading ("TABLET 22", "TABLET 32"). If the
    page starts mid-text, open <tablet> at the top regardless.
  - Emit <surface> wherever a tradition/section label is printed, before its omens.
  - ONE <l> per numbered omen (join wrapped lines). The omens are globally numbered
    and run in sequence (1, 2, 3 …; or primed 17', 18' …) — a low number reappearing
    further down the page belongs to the footnotes/translation, NOT a new omen.
  - Whitespace/newlines in your output are ignored downstream; only tags define
    structure.

TRANSLITERATION — STRICT RULES (this is what matters most):
1. CASE IS CRITICAL. Logograms/Sumerograms are printed in CAPITALS — output them
   UPPERCASE exactly (DIŠ, MUŠ, NA, LÚ, IGI, KUR, ŠUB, GAR, ŠÀ, EME.SID, EME.DIR,
   MUŠ.GIM.GURUN.NA, KUN.DAR, ḪABRUD.DA). Syllabic Akkadian is printed lowercase
   italic — output it lowercase (i-na, la-am, ṣa-lil, dan-nu). NEVER change a sign's
   case. The upper/lower distinction is the single most important datum on the page.
2. PHONETIC COMPLEMENTS. The lowercase grammatical ending attached to a logogram by
   a hyphen stays LOWERCASE: KUR-su, SUB-ut, IGI-mar, TUK-ši, GUR-šú, UD.MEŠ-šú.
   Never uppercase a complement.
3. DETERMINATIVES & SUPERSCRIPTS. Signs printed as small SUPERSCRIPT classifiers
   (d, m, f, lú, giš, mul, ki, munus, kur, uru, iti; and note-markers) → wrap in
   <sup>…</sup> exactly as printed: <sup>d</sup>AMAR.UTU. Classifiers Freedman writes
   ON the line as part of the chain (e.g. ITI.BÁRA, GIŠ.NÁ) → keep them inline
   UPPERCASE as printed. Subscript characters → <sub>…</sub>.
4. SIGN INDICES. Preserve index marks EXACTLY as printed — both subscript digits
   (UD₅, TAG₄, KAM₂, NÁ vs NA) and accent indices (á à â, é è, í ì, ú ù). Do NOT
   convert accents to subscript numbers or vice versa; reproduce the printed form.
5. SPECIAL CONSONANTS. Preserve ḫ, š, ś, ṣ, ṭ exactly — never substitute h, s, t.
   Preserve the glottal stop ʾ and ayin ʿ.
6. SIGN JOINS. Inside a logogram join signs with "." as printed (GIŠ.NÁ, KI.MIN,
   MAŠ.EN.GAG, NÍG.TUK). Inside a syllabic word join with "-" (i-na, ṣa-lil).
   Preserve ":" / ";" punctuation (used between variants) as printed.
7. EDITORIAL / PRESERVATION SIGNS — reproduce every one EXACTLY; they encode how
   much survives:
     [ … ]   restoration, incl. partial: G[ÌR, -š]u, [DIŠ MU]Š
     ⌈ ⌉ (or ⸢ ⸣)   half-brackets: damaged-but-legible sign
     x   one illegible sign;   … or [...]   break of unknown length
     !   corrected sign (+ collation in parentheses, e.g. qa!(BI));   ? uncertain
     ‹ › insertion;   «…» deletion;   ( ) as printed
   Keep every bracket attached exactly where printed.
8. LINE NUMBERS. Put the printed omen number verbatim in n="…": keep primes (17'),
   sub-letters (5a), composite forms. If a printed omen has no number, use n="".
9. NO NORMALIZATION, NO EMENDATION, NO TRANSLATION inside <l>. Output only what is
   printed; prioritise visual evidence over linguistic expectation.
10. EXCLUDE entirely: the running head ("Tablet 22"), the page number, the
    two-column footnote/commentary block at the bottom of the page (small type:
    philological notes, cited duplicates, English glosses), any "(gap)" marker, and
    the cuneiform hand-copy. Tag only the heading, recension labels, and the
    numbered omens.

INLINE FORMATTING (HTML only — no markdown **, *, _):
  <b>…</b> bold (the "TABLET NN" heading);  <sup>…</sup>, <sub>…</sub> as above.
  LITERAL CHARACTERS *, [, ], !, ?, +, :, x are LITERAL — output verbatim, never as
  markdown. TAG HYGIENE: every opening tag has a matching closing tag; inline tags
  close within their <l>/<head>; <tablet> properly contains its blocks; no orphan or
  overlapping tags.

Output ONLY the tagged HTML. No explanations, no code fences.

Example (Freedman, Tablet 22 = Snakes; and a Tablet 32 lizard recension):
<tablet><head><b>TABLET 22</b> (Snakes) Reconstruction</head><l n="1">DIŠ ina ITI.BÁRA UD.1.KAM₂ NA la-am TA GIŠ.NÁ GÌR-šú ana KI GAR-nu MUŠ TA ḪABRUD.DA È-ma la-am ma-am-man IGI LÚ IGI LÚ BI ina ŠÀ MU BI UG₇</l><l n="15">DIŠ ina ITI.BÁRA TA UD.1.KAM₂ EN UD.30.KAM₂ MUŠ ina É LÚ IGI ŠU <sup>d</sup>AMAR.UTU ar-ḫiš KUR-su É BI BIR-aḫ</l><l n="76">DIŠ MUŠ ana UGU NA GU₄.UD-am-ma ana KI ŠUB-ut ŠU.BI.DIL.AM₃</l></tablet>
<tablet><head><b>TABLET 32</b> (Lizards) Reconstruction</head><surface>Nineveh Tradition</surface><l n="1">[DIŠ EME.SID] ša₂ 2 KUN.MEŠ-šú ina É NA IGI-ir [šar-li-mu IGI] KUN-su lil-qí-ma ina SU₇</l></tablet>
