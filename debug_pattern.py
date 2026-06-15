#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""회의록 텍스트 샘플 확인 - 발언자 패턴 및 날짜 파악"""
import sys, os, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import pdfplumber
from pathlib import Path

PDF_DIR = r"C:\Users\hp\bills_council\pdf_22nd"
files = sorted(Path(PDF_DIR).iterdir(), key=lambda p: p.stat().st_size)
# 중간 크기 파일 선택
mid = len(files) // 2
test_file = files[mid]
print(f"테스트 파일: {test_file.name}")
print(f"파일명 파싱 테스트:")

# 날짜 패턴 확인
name = test_file.stem
print(f"  stem: {name}")
date_match = re.search(r'\((\d{4}\.\d{2}\.\d{2})\)', name)
print(f"  날짜 매치: {date_match.group(1) if date_match else 'NONE'}")

# 텍스트 추출
with pdfplumber.open(test_file) as pdf:
    text = ""
    for page in pdf.pages[:5]:
        t = page.extract_text()
        if t:
            text += t + "\n"

print(f"\n=== 전체 텍스트 앞 2000자 ===")
print(text[:2000])

print(f"\n=== 발언자 패턴 탐색 ===")
lines = text.split('\n')
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith('○') or stripped.startswith('◯') or '○' in stripped[:3]:
        print(f"  [{i:3d}] repr: {repr(stripped[:80])}")
