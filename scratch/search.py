import sys

def search_keywords():
    sys.stdout.reconfigure(encoding='utf-8')
    filepath = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\app.js"
    keywords = ["발언", "pdf", "modal", "toast", "highlight", "openpdf", "형광펜"]
    
    with open(filepath, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line_lower = line.lower()
            found = [kw for kw in keywords if kw in line_lower]
            if found:
                print(f"Line {idx+1} ({found}): {line.strip()[:120]}")

if __name__ == "__main__":
    search_keywords()
