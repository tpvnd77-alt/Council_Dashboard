import sys

def search_openmodal():
    sys.stdout.reconfigure(encoding='utf-8')
    filepath = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\app.js"
    
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    # Find definition of openModal
    for idx, line in enumerate(lines):
        if "function openmodal" in line.lower() or "const openmodal" in line.lower():
            print(f"openModal found at line {idx+1}: {line.strip()}")
            # Print next 200 lines to see what's there
            for j in range(idx, min(idx + 300, len(lines))):
                print(f"{j+1}: {lines[j]}", end="")
            break

if __name__ == "__main__":
    search_openmodal()
