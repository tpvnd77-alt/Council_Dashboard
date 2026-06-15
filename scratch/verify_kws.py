import json

with open('data/meetings.json', 'r', encoding='utf-8') as f:
    db = json.load(f)

target_words = ["하고법안", "육성에", "하는데", "등의", "운영", "법안", "하고법안 통과"]
output_lines = []

output_lines.append("Checking for EXACT match of forbidden keywords in global_keywords:")
found_exact_global = 0
for kw in db['global_keywords']:
    if kw['word'] in target_words:
        output_lines.append(f"❌ EXACT MATCH in global: {kw['word']} ({kw['count']})")
        found_exact_global += 1

if found_exact_global == 0:
    output_lines.append("No exact matches of forbidden keywords in global_keywords.")

output_lines.append("\nChecking for EXACT match of forbidden keywords inside meeting keywords:")
found_exact_meetings = 0
for m in db['meetings']:
    for kw in m.get('keywords', []):
        if kw['word'] in target_words:
            output_lines.append(f"❌ EXACT MATCH in meeting ({m['filename'][:50]}): {kw['word']} ({kw['count']})")
            found_exact_meetings += 1

if found_exact_meetings == 0:
    output_lines.append("No exact matches of forbidden keywords in any meetings. Perfect!")

with open('scratch/verify_exact_result.txt', 'w', encoding='utf-8') as f_out:
    f_out.write("\n".join(output_lines))

print("Exact match verification complete. Results saved to scratch/verify_exact_result.txt")
