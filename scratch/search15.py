import sys
import os

def search_all_files():
    sys.stdout.reconfigure(encoding='utf-8')
    directory = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard"
    keywords = ["발언 #", "발언#"]
    
    for root, dirs, files in os.walk(directory):
        # Skip node_modules or .git if any
        if "node_modules" in root or ".git" in root or "pdf" in root:
            continue
        for file in files:
            if file.endswith((".js", ".html", ".css", ".py")):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        for idx, line in enumerate(f):
                            for kw in keywords:
                                if kw in line:
                                    print(f"{file} Line {idx+1}: {line.strip()[:100]}")
                except Exception as e:
                    pass

if __name__ == "__main__":
    search_all_files()
