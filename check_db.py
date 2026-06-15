#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, json
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('data/meetings.json', encoding='utf-8') as f:
    db = json.load(f)

print(f"총 회의록: {db['total_count']}건")
print(f"전체 키워드: {len(db['global_keywords'])}개")
print(f"오류: {len(db['errors'])}건")
print()
print("=== TOP 15 키워드 ===")
for k in db['global_keywords'][:15]:
    print(f"  {k['word']}: {k['count']}회")
print()
print("=== 첫 5개 회의록 ===")
for m in db['meetings'][:5]:
    spk = len(m.get('speakers', []))
    kws = [k['word'] for k in m.get('keywords', [])[:4]]
    print(f"  [{m['date']}] {m['meeting_type']} | 발언자:{spk}명 | KW:{kws}")
print()
print("=== 회의 유형별 통계 ===")
types = Counter(m['meeting_type'] for m in db['meetings'])
for t, c in types.most_common():
    print(f"  {t}: {c}건")
print()
print("=== 연도별 통계 ===")
years = Counter(m['year'] for m in db['meetings'] if m.get('year'))
for y, c in sorted(years.items()):
    print(f"  {y}년: {c}건")

# 발언자 샘플
print()
print("=== 발언자 상위 10명 (전체 합산) ===")
spk_map = Counter()
for m in db['meetings']:
    for s in m.get('speakers', []):
        spk_map[s['name']] += s['speech_count']
for name, cnt in spk_map.most_common(10):
    print(f"  {name}: {cnt}회")
