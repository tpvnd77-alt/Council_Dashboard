import sys
import re

def search_hash_symbols():
    sys.stdout.reconfigure(encoding='utf-8')
    filepath = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\app.js"
    # Matches '#' followed by letters or non-hex characters
    pattern = re.compile(r'#[a-zA-Z가-힣_]+')
    
    with open(filepath, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            matches = pattern.findall(line)
            if matches:
                # Filter out color codes or CSS selectors if possible
                filtered = [m for m in matches if not re.match(r'^#[0-9a-fA-F]{3,6}$', m) and m not in ['#dynamic', '#modal', '#btn', '#tab', '#calendar', '#speech']]
                if filtered:
                    print(f"Line {idx+1}: {line.strip()[:120]}")

if __name__ == "__main__":
    search_hash_symbols()
