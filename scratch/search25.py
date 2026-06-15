import sys

def view_lines():
    sys.stdout.reconfigure(encoding='utf-8')
    filepath = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\app.js"
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for idx in range(2579, min(2600, len(lines))):
        print(f"{idx+1}: {lines[idx]}", end="")

if __name__ == "__main__":
    view_lines()
