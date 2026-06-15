import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("data/meetings.json", "r", encoding="utf-8") as f:
    db = json.load(f)

print("Top 100 global keywords:")
g_kws = db.get("global_keywords", [])
for idx, kw in enumerate(g_kws[:100]):
    print(f"  {idx+1:2d}. {kw['word']} ({kw['count']})")
