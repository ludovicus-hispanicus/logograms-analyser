"""Extract an eBL corpus chapter (composite/reconstructed text) to the project's
transliteration .txt format.

The web URL  https://www.ebl.lmu.de/corpus/D/1/4/SB/55  maps to the API endpoint
    https://www.ebl.lmu.de/api/texts/D/1/4/chapters/SB/55
i.e.  /api/texts/{genre}/{category}/{index}/chapters/{stage}/{name}

Usage:
    python scripts/extract_eae_chapter.py 55 data/new/astrology/EAE55/EAE55.eBL.txt
    python scripts/extract_eae_chapter.py 57 data/new/astrology/EAE57/EAE57.eBL.txt

Each omen line is written as  "<number>. <composite transliteration>".
The eBL English translation is kept as a "#tr.en:" comment beneath each line, and
embedded "#note:"/"//" parallel lines from the reconstruction are preserved as
comments. A second variant (var. b) is written as a "# var:" comment.
"""
import io
import json
import subprocess
import sys
import urllib.request
from collections import Counter

GENRE, CATEGORY, INDEX, STAGE_PATH = "D", 1, 4, "SB"  # Divination / EAE, Standard Babylonian
STAGE_LABEL = "Standard Babylonian"


def fetch_chapter(name):
    url = f"https://www.ebl.lmu.de/api/texts/{GENRE}/{CATEGORY}/{INDEX}/chapters/{STAGE_PATH}/{name}"
    try:
        with urllib.request.urlopen(url) as resp:
            return json.load(resp)
    except Exception:
        # Fallback for Python builds without a CA bundle: shell out to curl.
        raw = subprocess.run(["curl", "-sSf", url], capture_output=True, check=True).stdout
        return json.loads(raw)


def provenances(data):
    c = Counter()
    for m in data.get("manuscripts", []):
        prov = m.get("provenance")
        name = prov.get("name") if isinstance(prov, dict) else prov
        if name:
            c[name] += 1
    return c


def render(data, name):
    out = io.StringIO()
    provs = provenances(data)
    prov_str = ", ".join(f"{p} ({n})" for p, n in provs.most_common())
    n_ms = len(data.get("manuscripts", []))

    out.write("---\n")
    out.write("genre: astrological omens\n")
    out.write("period: Neo-Assyrian / Late Babylonian\n")
    out.write(f"provenance: first-millennium canonical; {n_ms} manuscripts ({prov_str})\n")
    out.write(f"recension: Enūma Anu Enlil {name}, eBL composite (Standard Babylonian)\n")
    out.write("counting: DIŠ\n")
    out.write(f"series: Enūma Anu Enlil {name}\n")
    out.write(
        "edition: electronic Babylonian Library (eBL), corpus D/1/4 chapter SB "
        f"{name}; fetched from /api/texts/D/1/4/chapters/SB/{name}. "
        "Composite (reconstruction) line read off the chapter score.\n"
    )
    out.write(
        "note: Composite text as reconstructed in eBL. Logograms uppercase, syllabic "
        "lowercase, {} determinatives, [] restoration, x illegible. '#tr.en:' lines are "
        "the eBL English translation; '//' and '#note:' are eBL parallels/notes; "
        "'# var:' is a second eBL variant of the line.\n"
    )
    out.write("---\n\n")
    out.write("@text\n")

    for line in data["lines"]:
        if line.get("isBeginningOfSection"):
            out.write("\n")
        number = line["number"]
        variants = line.get("variants", [])
        if not variants:
            continue
        recon_parts = variants[0]["reconstruction"].split("\n")
        text = recon_parts[0].strip()
        out.write(f"{number}. {text}\n")
        # embedded notes / parallels from the reconstruction (kept as comments so
        # the LDI loader, which only skips '#'/'$'/'@' lines, ignores them)
        for extra in recon_parts[1:]:
            extra = extra.strip()
            if extra:
                out.write(f"   {extra}\n" if extra.startswith("#") else f"   # {extra}\n")
        # additional variants
        for v in variants[1:]:
            vtext = v["reconstruction"].split("\n")[0].strip()
            out.write(f"   # var: {vtext}\n")
        # translation
        tr = line.get("translation")
        if tr:
            tr = tr.strip()
            out.write(f"   {tr}\n" if tr.startswith("#") else f"   #tr.en: {tr}\n")

    return out.getvalue()


def main():
    name = sys.argv[1]
    dest = sys.argv[2]
    data = fetch_chapter(name)
    text = render(data, name)
    with open(dest, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"wrote {dest}: {len(data['lines'])} lines, {len(data.get('manuscripts', []))} manuscripts")


if __name__ == "__main__":
    main()
