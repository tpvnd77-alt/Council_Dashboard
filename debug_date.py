#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, sys, os, json
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PDF_DIR = r"C:\Users\hp\bills_council\pdf_22nd"
files = [f for f in os.listdir(PDF_DIR) if f.lower().endswith('.pdf') and '(1)' not in f]

print("=== 날짜 파싱 테스트 (첫 10개) ===")
for fname in sorted(files)[:10]:
    stem = Path(fname).stem
    # 다양한 패턴 시도
    m1 = re.search(r'\((\d{4})\.(\d{2})\.(\d{2})\.?\)', stem)
    m2 = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', stem)
    result1 = f"{m1.group(1)}-{m1.group(2)}-{m1.group(3)}" if m1 else "NONE"
    result2 = f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}" if m2 else "NONE"
    print(f"  파일: ...{stem[-45:]}")
    print(f"    패턴1(괄호): {result1}")
    print(f"    패턴2(자유): {result2}")
    print()

print()
print("=== 현재 meetings.json 날짜 확인 ===")
with open('data/meetings.json', encoding='utf-8') as f:
    db = json.load(f)

none_count = sum(1 for m in db['meetings'] if not m.get('date'))
dated = [m for m in db['meetings'] if m.get('date')]
print(f"날짜 있음: {len(dated)}건 / 없음: {none_count}건")
if dated:
    print("날짜 있는 첫 5건:")
    for m in dated[:5]:
        print(f"  {m['date']} | {m['meeting_type']} | 발언자:{len(m.get('speakers',[]))}명")
