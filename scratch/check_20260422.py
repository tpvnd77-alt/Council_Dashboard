import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("data/meetings.json", "r", encoding="utf-8") as f:
    db = json.load(f)

for m in db.get("meetings", []):
    if m.get("date") == "2026-04-22":
        # Create a shallow copy without the full lines of speakers for concise printing
        m_copy = dict(m)
        if "speakers" in m_copy:
            m_copy["speakers"] = [
                {
                    "name": s.get("name"),
                    "speech_count": s.get("speech_count"),
                    "lines_count": len(s.get("lines", []))
                }
                for s in m.get("speakers", [])
            ]
        print(json.dumps(m_copy, ensure_ascii=False, indent=2))
