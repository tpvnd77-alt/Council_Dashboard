import json
import sys

def search_text():
    sys.stdout.reconfigure(encoding='utf-8')
    filepath = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\data\meetings.json"
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    found = False
    for m in data["meetings"]:
        for s in m.get("speakers", []):
            for i, line in enumerate(s.get("lines", [])):
                if "어와서 데이터센터" in line["text"] or "데이터센터를 구축하고" in line["text"]:
                    found = True
                    print(f"Meeting: {m['filename']}")
                    print(f"Speaker: {s['name']}")
                    print(f"Line index: {i}")
                    # Print adjacent lines
                    start = max(0, i - 3)
                    end = min(len(s["lines"]), i + 6)
                    for j in range(start, end):
                        marker = ">>>" if j == i else "   "
                        print(f"{marker} Line {j} (page {s['lines'][j]['page']}): {s['lines'][j]['text']}")
                    print("-" * 50)
    if not found:
        print("Not found in DB!")

if __name__ == "__main__":
    search_text()
