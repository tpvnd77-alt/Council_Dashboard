import json

with open('data/meetings.json', 'r', encoding='utf-8') as f:
    db = json.load(f)

output_lines = []
found = 0
for m in db['meetings']:
    for s in m.get('speakers', []):
        for line in s.get('lines', []):
            if '고민수' in line['text']:
                output_lines.append(f"File: {m['filename'][:40]} | Speaker: {s['name']} | Line: {line['text']}")
                found += 1
                if found > 20:
                    break
        if found > 20:
            break
    if found > 20:
        break

with open('scratch/gominsoo_context.txt', 'w', encoding='utf-8') as f_out:
    f_out.write("\n".join(output_lines))

print("Saved to scratch/gominsoo_context.txt")
