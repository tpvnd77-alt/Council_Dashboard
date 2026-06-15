with open("parse_pdfs.py", "r", encoding="utf-8") as f:
    content = f.read()

lines = content.split('\n')

# Find functions or variables containing "keyword" or "stop"
for idx, line in enumerate(lines):
    if any(k in line.lower() for k in ["keyword", "stop", "filter"]):
        print(f"Line {idx+1}: {line.strip()[:120]}")
