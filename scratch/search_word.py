import json
import sys

# 표준 출력을 UTF-8로 강제 재설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

with open('data/meetings.json', 'r', encoding='utf-8') as f:
    db = json.load(f)

output_lines = []

for m in db.get('meetings', []):
    for s in m.get('speakers', []):
        for line in s.get('lines', []):
            if '어와서 데이터센터' in line.get('text', ''):
                output_lines.append("Found match:")
                output_lines.append(f"Meeting: {m['filename']}")
                output_lines.append(f"Speaker: {s['name']}")
                output_lines.append(f"Line: {line}")
                
                # 근처 라인들 출력
                idx = s['lines'].index(line)
                start_idx = max(0, idx - 5)
                end_idx = min(len(s['lines']), idx + 6)
                output_lines.append("\nContext:")
                for i in range(start_idx, end_idx):
                    prefix = "--> " if i == idx else "    "
                    line_data = s['lines'][i]
                    output_lines.append(f"{prefix}[Line {i}] Page {line_data['page']}: {line_data['text']}")

with open('scratch/search_result.txt', 'w', encoding='utf-8') as f_out:
    f_out.write("\n".join(output_lines))
print("Saved to scratch/search_result.txt")
