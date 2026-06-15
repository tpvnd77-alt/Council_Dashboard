with open("app.js", "r", encoding="utf-8") as f:
    content = f.read()

lines = content.split('\n')

def print_around(pattern, limit=40):
    for idx, line in enumerate(lines):
        if pattern in line:
            start = max(0, idx - 2)
            end = min(len(lines), idx + limit)
            print(f"\n--- Around line {idx+1} ({pattern}) ---")
            for i in range(start, end):
                print(f"{i+1}: {lines[i]}")
            break

print_around("let result = STATE.db.meetings.filter")
