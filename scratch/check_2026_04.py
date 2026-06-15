import json
with open('data/meetings.json', encoding='utf-8') as f:
    db = json.load(f)

apr_meetings = [m for m in db['meetings'] if m.get('date') and '2026-04' in m['date']]
print(f"2026년 4월 회의록 개수: {len(apr_meetings)}개")

for m in apr_meetings:
    print(f"[{m['date']}] {m['filename']}")
    print(f"  - Agendas: {m.get('agendas', [])}")
    print(f"  - Speakers count: {len(m.get('speakers', []))}")
    print(f"  - Text Length: {m.get('text_length', 0)}")
    print(f"  - Summary (first 250 chars):\n{m.get('summary', '')[:250]}")
    print("="*60)
