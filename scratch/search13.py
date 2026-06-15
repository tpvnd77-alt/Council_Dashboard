import sys

def view_lines():
    sys.stdout.reconfigure(encoding='utf-8')
    filepath = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\app.js"
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for idx in range(1930, min(2300, len(lines))):
        # We can search where the functions start
        line = lines[idx]
        if "function " in line or "const " in line:
            print(f"Line {idx+1}: {line.strip()[:120]}")

if __name__ == "__main__":
    view_lines()
