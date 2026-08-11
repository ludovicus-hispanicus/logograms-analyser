"""Fetch a fragment from the eBL API and print its ATF transliteration."""
import json
import sys
import urllib.request

frag_id = sys.argv[1] if len(sys.argv) > 1 else "MS.3117"
url = f"https://www.ebl.lmu.de/api/fragments/{frag_id}"
with urllib.request.urlopen(url) as resp:
    data = json.load(resp)

print(f"# publication: {data.get('publication')}")
print(f"# record: {[(r['user'], r['type'], r['date'][:10]) for r in data.get('record', [])]}")
print("#" + "=" * 60)

for line in data["text"]["lines"]:
    prefix = line.get("prefix", "")
    if line["type"] == "TextLine":
        tokens = [t.get("displayValue", t.get("value", "")) for t in line["content"]]
        print(f"{prefix} {' '.join(tokens)}")
    else:
        # dollar/at/translation lines
        display = "".join(t.get("value", "") for t in line["content"])
        print(f"{prefix}{display}")
