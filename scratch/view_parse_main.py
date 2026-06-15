import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("parse_pdfs.py", "r", encoding="utf-8") as f:
    content = f.read()

lines = content.split('\n')

start_line = 800
end_line = min(len(lines), start_line + 150)
print(f"--- Printing parse_pdfs.py lines {start_line} to {end_line} ---")
for i in range(start_line - 1, end_line):
    print(f"{i+1}: {lines[i]}")
