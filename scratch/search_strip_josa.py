import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("parse_pdfs.py", "r", encoding="utf-8") as f:
    content = f.read()

lines = content.split('\n')

def print_around(pattern, limit=40):
    found = False
    for idx, line in enumerate(lines):
        if pattern in line:
            start = max(0, idx - 2)
            end = min(len(lines), idx + limit)
            print(f"\n--- Around line {idx+1} ({pattern}) ---")
            for i in range(start, end):
                print(f"{i+1}: {lines[i]}")
            found = True
            break
    if not found:
        print(f"Pattern '{pattern}' not found!")

print_around("def strip_josa")
