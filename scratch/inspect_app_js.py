import re

with open("app.js", "r", encoding="utf-8") as f:
    content = f.read()

# Let's find functions related to hash, url, parameter, or init
print("--- Searching for hash/URL handling in app.js ---")
lines = content.split('\n')
for idx, line in enumerate(lines):
    if any(keyword in line for keyword in ["hash", "URL", "param", "search", "filter", "route"]):
        print(f"Line {idx+1}: {line.strip()[:120]}")
