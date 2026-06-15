import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("app.js", "r", encoding="utf-8") as f:
    content = f.read()

lines = content.split('\n')

# Start from line 840 and print 150 lines
start_line = 840
end_line = min(len(lines), start_line + 150)
print(f"--- Printing app.js lines {start_line} to {end_line} ---")
for i in range(start_line - 1, end_line):
    print(f"{i+1}: {lines[i]}")
