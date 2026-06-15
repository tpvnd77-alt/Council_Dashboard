import sys

def search_modal_tabs():
    sys.stdout.reconfigure(encoding='utf-8')
    filepath = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\app.js"
    with open(filepath, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if "tab-" in line or "modal-" in line or "btn-" in line:
                print(f"Line {idx+1}: {line.strip()[:100]}")

if __name__ == "__main__":
    search_modal_tabs()
