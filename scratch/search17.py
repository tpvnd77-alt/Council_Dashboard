import sys

def search_parser():
    sys.stdout.reconfigure(encoding='utf-8')
    filepath = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\parse_pdfs.py"
    with open(filepath, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if "speaker" in line.lower() or "lines" in line.lower():
                print(f"Line {idx+1}: {line.strip()[:120]}")

if __name__ == "__main__":
    search_parser()
