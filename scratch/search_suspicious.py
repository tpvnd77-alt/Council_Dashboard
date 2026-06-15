import json

with open('data/meetings.json', 'r', encoding='utf-8') as f:
    db = json.load(f)

output_lines = []
for m in db['meetings']:
    for kw in m.get('keywords', []):
        word = kw['word']
        # check if it is or contains any of the reported/suspicious words
        if word in ['그리', '대표발', '그다음', '이렇', '이훈', '원회상임위원', '필요', '근거', '계약', '중계', '국민', '하지']:
            output_lines.append(f"File: {m['filename'][:40]} | Keyword: {word} | Count: {kw['count']}")
        elif '원회' in word:
            output_lines.append(f"File: {m['filename'][:40]} | Keyword [contains 원회]: {word} | Count: {kw['count']}")

with open('scratch/suspicious_result.txt', 'w', encoding='utf-8') as f_out:
    f_out.write("\n".join(output_lines))

print("Complete. Results saved to scratch/suspicious_result.txt")
