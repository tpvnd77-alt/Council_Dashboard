import json
import sys

def view_structure():
    sys.stdout.reconfigure(encoding='utf-8')
    filepath = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\data\meetings.json"
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print("generated_at:", data.get("generated_at"))
    print("total_count:", data.get("total_count"))
    
    meetings = data.get("meetings", [])
    if meetings:
        m = meetings[0]
        print("\nFirst Meeting keys:", m.keys())
        print("Filename:", m.get("filename"))
        speakers = m.get("speakers", [])
        if speakers:
            sp = speakers[0]
            print("\nSpeaker keys:", sp.keys())
            print("Name:", sp.get("name"))
            print("Speech count:", sp.get("speech_count"))
            lines = sp.get("lines", [])
            print("Lines length:", len(lines))
            if lines:
                print("First line:", lines[0])
                if len(lines) > 1:
                    print("Second line:", lines[1])

if __name__ == "__main__":
    view_structure()
