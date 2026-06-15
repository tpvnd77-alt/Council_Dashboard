import json
import urllib.request

# 1. Read local file
print("Reading local data/meetings.json...")
try:
    with open("data/meetings.json", "r", encoding="utf-8") as f:
        local_db = json.load(f)
    print("Local database loaded. total_count =", local_db.get("total_count"))
    
    # Find meeting on 2026-04-22 or session 433
    target_meeting_local = None
    for m in local_db.get("meetings", []):
        if "2026-04-22" in m.get("date", "") or "433" in str(m.get("session_num", "")):
            # Check if it has 최성희 and 노종면 separated
            print(f"Found local meeting: {m.get('filename')}, date: {m.get('date')}")
            # print speakers
            print("Local Speakers:")
            for s in m.get("speakers", []):
                if s.get("name") in ["노종면", "최성희"]:
                    print(f"  {s}")
            target_meeting_local = m
except Exception as e:
    print("Error reading local meetings.json:", e)

# 2. Fetch from localhost:8765
print("\nFetching from http://localhost:8765/data/meetings.json...")
try:
    req = urllib.request.Request("http://localhost:8765/data/meetings.json")
    with urllib.request.urlopen(req, timeout=5) as response:
        served_data = response.read().decode('utf-8')
    served_db = json.loads(served_data)
    print("Served database loaded. total_count =", served_db.get("total_count"))
    
    for m in served_db.get("meetings", []):
        if "2026-04-22" in m.get("date", "") or "433" in str(m.get("session_num", "")):
            print(f"Found served meeting: {m.get('filename')}, date: {m.get('date')}")
            print("Served Speakers:")
            for s in m.get("speakers", []):
                if s.get("name") in ["노종면", "최성희"]:
                    print(f"  {s}")
except Exception as e:
    print("Error fetching from localhost:8765:", e)
