import pdfplumber
import sys

sys.stdout.reconfigure(encoding='utf-8')

pdf_path = r"C:\Users\hp\bills_council\pdf_22nd\제22대국회 제434회(임시회) 제3차 과학기술정보방송통신위원회(정보통신방송미디어법안심사소위원회) (2026.04.22.).pdf"

print(f"Reading Page 12 of PDF: {pdf_path}")
with pdfplumber.open(pdf_path) as pdf:
    # Page index is 0-indexed, so page 12 is index 11
    if len(pdf.pages) >= 12:
        page_text = pdf.pages[11].extract_text()
        print("--- Page 12 Text ---")
        print(page_text)
    else:
        print(f"PDF only has {len(pdf.pages)} pages.")
