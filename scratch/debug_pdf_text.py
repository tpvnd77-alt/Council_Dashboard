import pdfplumber
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

filepath = r"C:\Users\hp\bills_council\pdf_22nd\제22대국회 제434회(임시회) 제3차 과학기술정보방송통신위원회(정보통신방송미디어법안심사소위원회) (2026.04.22.) (2).pdf"

with pdfplumber.open(filepath) as pdf:
    print(f"총 페이지 수: {len(pdf.pages)}")
    # 첫 4페이지 텍스트 출력
    for i, page in enumerate(pdf.pages[:4]):
        print(f"=== PAGE {i+1} ===")
        text = page.extract_text()
        print(text)
        print("-" * 50)
