import re
import sys
import pdfplumber

sys.stdout.reconfigure(encoding='utf-8')

# Import functions from parse_pdfs
sys.path.append(".")
from parse_pdfs import extract_speakers_and_text_with_page

pdf_path = r"C:\Users\hp\bills_council\pdf_22nd\제22대국회 제434회(임시회) 제3차 과학기술정보방송통신위원회(정보통신방송미디어법안심사소위원회) (2026.04.22.).pdf"

def patch_page_text(filename, page_num, text):
    if "2026.04.22" in filename and page_num == 12:
        # 1. 노종면 -> 최성희
        if "그렇지 않습니까? 맞고요. 그게 맞고요. 다만" in text:
            text = text.replace(
                "그렇지 않습니까? 맞고요. 그게 맞고요. 다만",
                "그렇지 않습니까?\n◯문화체육관광부콘텐츠미디어산업관 최성희 맞고요. 그게 맞고요. 다만"
            )
        # 2. 최성희 -> 노종면
        if "이렇게 크게 구별된다고 저는 봐요.\n그러면 질문을" in text:
            text = text.replace(
                "이렇게 크게 구별된다고 저는 봐요.\n그러면 질문을",
                "이렇게 크게 구별된다고 저는 봐요.\n◯노종면 위원 그러면 질문을"
            )
        # 3. 노종면 -> 최성희
        if "의문들이 생기는 거예요.\n그러면 결과적으로 중복될" in text:
            text = text.replace(
                "의문들이 생기는 거예요.\n그러면 결과적으로 중복될",
                "의문들이 생기는 거예요.\n◯문화체육관광부콘텐츠미디어산업관 최성희 그러면 결과적으로 중복될"
            )
    return text

print("Parsing Page 12 with patch...")
page_texts = []
with pdfplumber.open(pdf_path) as pdf:
    p_num = 12
    t = pdf.pages[p_num - 1].extract_text()
    patched_t = patch_page_text(pdf_path, p_num, t)
    page_texts.append((p_num, patched_t))

speakers_dict = extract_speakers_and_text_with_page(page_texts)

# Let's inspect the results
print("\nDetected Speakers on Page 12:")
for spk, lines in speakers_dict.items():
    print(f"\n--- Speaker: {spk} ({len(lines)} lines) ---")
    for line in lines:
        print(f"  Page {line['page']}: {line['text']}")
