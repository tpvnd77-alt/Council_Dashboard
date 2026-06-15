#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pdfplumber
import sys
import os

# 가장 작은 PDF로 테스트
PDF_DIR = r"C:\Users\hp\bills_council\pdf_22nd"

files = [f for f in os.listdir(PDF_DIR) if f.lower().endswith('.pdf') and '(1)' not in f]
files.sort(key=lambda f: os.path.getsize(os.path.join(PDF_DIR, f)))

print(f"가장 작은 파일 5개:")
for f in files[:5]:
    size = os.path.getsize(os.path.join(PDF_DIR, f))
    print(f"  {f[:60]} ({size//1024} KB)")

# 가장 작은 파일로 테스트
test_file = os.path.join(PDF_DIR, files[0])
print(f"\n테스트 파일: {files[0]}")

try:
    with pdfplumber.open(test_file) as pdf:
        print(f"페이지 수: {len(pdf.pages)}")
        for i, page in enumerate(pdf.pages[:3]):
            text = page.extract_text()
            if text:
                print(f"페이지 {i+1} ({len(text)}자): {text[:150]}")
            else:
                print(f"페이지 {i+1}: 텍스트 없음")
    print("\n파싱 성공!")
except Exception as e:
    print(f"오류: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
