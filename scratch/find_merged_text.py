import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("data/meetings.json", "r", encoding="utf-8") as f:
    db = json.load(f)

search_phrase = "맞고요. 그게 맞고요"
found = False

for m in db.get("meetings", []):
    for s in m.get("speakers", []):
        for line in s.get("lines", []):
            if search_phrase in line.get("text", ""):
                print(f"Found in Meeting: {m.get('filename')}")
                print(f"Speaker: {s.get('name')}")
                print(f"Page: {line.get('page')}")
                print(f"Full Text of line:\n{line.get('text')}\n")
                found = True

if not found:
    print(f"Phrase '{search_phrase}' not found in any speaker lines!")
