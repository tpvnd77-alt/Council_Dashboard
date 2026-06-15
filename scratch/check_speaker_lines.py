import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("data/meetings.json", "r", encoding="utf-8") as f:
    db = json.load(f)

for m in db.get("meetings", []):
    if m.get("date") == "2026-04-22":
        print(f"Meeting: {m.get('filename')}")
        
        # Print first few lines of 최성희 on Page 10
        choi = [s for s in m.get("speakers", []) if s.get("name") == "최성희"]
        if choi:
            print("\n--- 최성희 Page 10 Lines ---")
            for line in choi[0].get("lines", []):
                if line.get("page") == 10:
                    print(f"  Page {line.get('page')}: {line.get('text')}")
                    
        # Print first few lines of 노종면 on Page 10
        noh = [s for s in m.get("speakers", []) if s.get("name") == "노종면"]
        if noh:
            print("\n--- 노종면 Page 10 Lines ---")
            for line in noh[0].get("lines", []):
                if line.get("page") == 10:
                    print(f"  Page {line.get('page')}: {line.get('text')}")
