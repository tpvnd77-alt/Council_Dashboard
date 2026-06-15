import json
import urllib.request
import sys

# Configure stdout to use utf-8
sys.stdout.reconfigure(encoding='utf-8')

print("Fetching served JSON...")
req = urllib.request.Request("http://localhost:8765/data/meetings.json")
try:
    with urllib.request.urlopen(req, timeout=5) as response:
        served_data = response.read().decode('utf-8')
    served_db = json.loads(served_data)
    print(f"Loaded served JSON. total_count: {served_db.get('total_count')}")
    
    # Let's search for meetings on 2026-04-22
    for m in served_db.get("meetings", []):
        if m.get("date") == "2026-04-22":
            print(f"\n--- Meeting on 2026-04-22 ({m.get('filename')}) ---")
            speakers = [s.get("name") for s in m.get("speakers", [])]
            print("Speakers:", speakers)
            
            # Let's see if we have 최성희
            choi = [s for s in m.get("speakers", []) if "최성희" in s.get("name")]
            if choi:
                print("Found 최성희 speaker data in served JSON!")
                for s in choi:
                    print(f"Speaker: {s.get('name')}, lines count: {len(s.get('lines', []))}")
                    print("First 3 lines:")
                    for line in s.get('lines', [])[:3]:
                        print(f"  Page {line.get('page')}: {line.get('text')}")
            else:
                print("최성희 NOT found as a speaker in served JSON!")

            noh = [s for s in m.get("speakers", []) if "노종면" in s.get("name")]
            if noh:
                print("Found 노종면 speaker data in served JSON!")
                for s in noh:
                    print(f"Speaker: {s.get('name')}, lines count: {len(s.get('lines', []))}")
                    print("First 3 lines:")
                    for line in s.get('lines', [])[:3]:
                        print(f"  Page {line.get('page')}: {line.get('text')}")
            else:
                print("노종면 NOT found as a speaker in served JSON!")

except Exception as e:
    print(f"Error fetching or parsing: {e}")
