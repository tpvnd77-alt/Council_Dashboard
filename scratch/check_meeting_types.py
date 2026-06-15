import json
from collections import Counter
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("data/meetings.json", "r", encoding="utf-8") as f:
    db = json.load(f)

types = [m.get("meeting_type") for m in db.get("meetings", [])]
c = Counter(types)
print("Unique meeting_type in meetings.json:")
for t, cnt in c.items():
    print(f"  '{t}': {cnt}")
