with open("app.js", "r", encoding="utf-8") as f:
    content = f.read()

lines = content.split('\n')

# Find hashchange or window load event listener
print("--- Finding hashchange or init/load event listeners ---")
for idx, line in enumerate(lines):
    if "hashchange" in line or "DOMContentLoaded" in line or "init" in line:
        print(f"Line {idx+1}: {line.strip()[:120]}")

# Let's read app.js around hashchange / routing lines
# We will write a snippet print program
def print_around(pattern, limit=40):
    for idx, line in enumerate(lines):
        if pattern in line:
            start = max(0, idx - 5)
            end = min(len(lines), idx + limit)
            print(f"\n--- Around line {idx+1} ({pattern}) ---")
            for i in range(start, end):
                print(f"{i+1}: {lines[i]}")
            break

print_around("hashchange")
print_around("parseHash")
print_around("initApp")
