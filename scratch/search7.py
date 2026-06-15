import sys

def search_index_html():
    sys.stdout.reconfigure(encoding='utf-8')
    filepath = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\index.html"
    with open(filepath, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if "modal" in line.lower() or "sidebar" in line.lower() or "viewer" in line.lower():
                print(f"Line {idx+1}: {line.strip()[:120]}")

if __name__ == "__main__":
    search_index_html()
