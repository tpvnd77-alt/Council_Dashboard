#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
제22대 국회 과학기술정보방송통신위원회 회의록 PDF ➔ Supabase 클라우드 DB 파서
"""

import os, re, json, sys, datetime
from collections import Counter
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    import pdfplumber
except ImportError:
    os.system(f"{sys.executable} -m pip install pdfplumber -q")
    import pdfplumber

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    os.system(f"{sys.executable} -m pip install psycopg2-binary -q")
    import psycopg2
    from psycopg2.extras import execute_values

# === 설정 ===
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file manually if exists
env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                os.environ[key] = val

PDF_DIR    = r"C:\Users\hp\bills_council\pdf_22nd" # 로컬 PDF 경로
MAX_PAGES  = 1000
MAX_WORKERS = 6

# ─── 불용어 (parse_pdfs.py 스펙 완벽 준수) ───────────────────────────────────────────
STOPWORDS = set([
    "일부개정법률안","전부개정법률안","일부개정법률","제정법률안","법률안","시행령",
    "대표발의","의안번호","정부제출","위원대표","의원대표","의안","법률","개정안",
    "개정법률안","일부개정","전부개정","법률안등","의안제","법률안은","법률안에",
    "대안","보편적","연번","보고사항","주시기","바랍니다","존경하는","이의",
    "과학기술정보방송","과학기술정보통신","방송통신위원회","방송통신위원",
    "정보통신방송","과학기술정보","한국방송공사","방송미디어통신위",
    "방송미디어통신심","과학기술원자력","정보통신망","한국교육방송",
    "한국인터넷진흥","방송통신","과학기술","정보통신","방송미디어",
    "위원장","소위원장","수석전문위원","전문위원","부위원장","간사",
    "위원","장관","차관","부장관","처장","청장","원장","이사장","사장","대표이사",
    "후보자","직무대행","장직무대행","후보","대행","비서관","행정관","참고인","증인","진술인",
    "의원","의원은","의원이","의원님","의원들의","한국방송공사사장",
    "최민희","최형두","김현","노종면","이정헌","황정아","박충권","이훈기",
    "이상휘","박정훈","김장겸","이준석","정동영","이해민","최수진","한민수",
    "임명현","이복우","조인철","이주희","김태규","이진숙","유상임","박민",
    "김종철","류희림","안형준","박민규","김우영","권영진","신동욱","김남근",
    "김영배","정일영","유영상","김범섭","김종원","고광헌","박대준",
    "신성범","배경훈","박장범","류제명","강도현","이창윤",
    "있습니다","합니다","습니다","겠습니다","드립니다","입니다","됩니다",
    "없습니다","아닙니다","이상입니다","말씀드리","있도록","하겠습니다",
    "이렇게","그렇게","저렇게","어떻게","때문에","위해서","관련해서",
    "생각합니다","알고있습니다","확인하겠습니다","검토하겠습니다",
    "감사합니다","수고하셨습니다","죄송합니다","부탁드립니다",
    "있는","관한","하는","하고","대해서","등에","그러면","것은",
    "부제","것이","되는","위한","있고","그다음에","가지고","대해서는",
    "겁니다","것으로","알고","있는데","거예요","아까","것을","보시면",
    "같습니다","의견","제출","쪽입니다","의사일정","연월일",
    "관한법","관한법률","관한법률안",
    "위원님","통신제","통신소위제","정부","특별법 통과","그러니까","보면",
    "해서","말씀을","설치","운영에","방송통신위원회의","부총리겸과학기술",
    "정보통신부장관","년도","의견을","주십시오","기반","생각을","부분에",
    "이사","필요가","해야","신뢰","니다","방통위","년도국감","디지털",
    "방송통신위원장후","보자","말씀해","소위","굉장히","있음",
    "방송통신위원장직","이것은","인사청문회","청문회","번호","국회",
    "이것","그것","저것","우리가","저희가","우리는","저희는","저희들",
    "거기에","여기에","지금은","현재는","이미","아직","계속","바로",
    "조금","잠깐","잠시","다시","한번","사실","그냥","정말","아마",
    "조금더","좀더","많이","너무","매우","상당히","충분히","대단히",
    "이","가","을","를","은","는","의","에","와","과","도","로","으로",
    "에서","에게","부터","까지","이다","있다","없다","하다","되다",
    "것","수","그","저","좀","그리고","그래서","그러나","그런데",
    "하지만","또한","또는","및","등","즉","따라서","그렇","으며",
    "이며","이고","이나","이라","에도","으로는","으로도","에서는",
    "년","월","일","시","분","번","제","차","항","호","조","조항",
    "이상","이하","다음","이전","최근","현재","지난","올해","내년",
    "작년","오늘","내일","어제","이번","다음번","지금","때",
    "문제","부분","경우","상황","내용","사항","방면","측면","정도",
    "관련","대해","대한","통해","위해","때문","생각","말씀",
    "여기","거기","모든","모두","각각","여러","가지",
    "어떤","무슨","누가","왜","언제","어디","예","아니","맞습니다",
    "됩니","있습","없습","였습","이런","그런","저런","같은","다른",
    "제가","저는","그게","이게","우리","저희","하여","통해서","위하여",
    "육성에","하는데","등의","운영","운영에","운영을","운영이","운영은","운영도",
    "하고법안","하는법안","할법안","법안","법안의","법안을","법안이","법안에",
    "통과","상정","검토","의결",
    "대표발","그리","주시","이렇","어떻","이훈","원회상임위원","상임위","의원안",
    "그다음","그다음에","그러","그렇","이러","하지","개의","회의","보고","제출",
    "준수","주시기","어떻게","하기","하게","하고","그리고","공동발의","소관",
    "상임위원회",
    "기존", "아니라", "아니고", "아니면", "아닙니다", "하나", "일부", "대부분", "자리", "선서", "자료제출", "제정법", "현행법",
    "먼저", "얘기", "필요", "시간", "것들", "국민들", "회계연", "회계연도", "연도", "년도", "제도", "보도", "의도", "태도", "부분들",
    "방미통위", "과방위", "방심위", "과기부", "문화체육관광부", "무대행", "직무대행", "위원장님", "간사님", "위원님들",
    "했습니다", "드리겠습니다", "따라", "하면", "있어서", "번째", "하십니까", "하셨습니다",
    "국민", "근거", "지원",
    "자료", "사업", "규정", "요구", "사람", "과정", "취지", "이유", "분야", "진흥", "답변", "중요", "절차", "진행", "활용", "본인", "발언", "조사", "안건", "대표", "관리", "의사진행발언", "대한민국", "기재부", "부처", "입장", "발전", "의제", "과학기술정보통신부", "문화체육관광부",
    "있다고", "들어", "보니까", "관련된", "주신", "되면", "있기", "보시겠습니다",
    "없으십니까", "가결되었음", "관련되어져서", "마련해", "반대", "심사", "조정", "개회", "통합", "업무", "기관", "기능", "접근",
    "선포", "가결", "부결", "개의선포", "개의하도록", "선언합니다", "의석을정돈해", "의석을", "정돈해", "개의를", "이의가",
    "없으므로", "되었음을", "선포합니다", "의결하고자", "찬성하시는", "반대하시는", "보고해", "보고해주시기", "방지", "보호", "토론",
    "단계", "보장", "중단", "마이크", "법상", "상황", "의견", "생각", "말씀", "부분", "내용", "사항", "경우",
    "콘텐츠", "컨텐츠", "산업", "체계", "영역", "활동", "플랫폼", "문화", "기준", "기업", "제작",
    "방법", "부담", "역할", "노력", "판단", "기대", "평가", "확보", "대비", "자체", "이전", "이후",
    "주요", "함께", "경험", "차원", "사실", "자체", "진짜", "내지", "이유", "의견", "정도", "대해"
])

TITLE_PREFIXES = re.compile(
    r'^(?:소위원장|위원장|전문위원|수석전문위원|참고인|증인|정부위원'
    r'|차관|장관|부처장|원장|처장|청장|부장관|실장|국장|과장|사무관'
    r'|대표이사|이사장|사장|후보자|직무대행|대행)\s+'
)

def safe_print(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(str(msg).encode('ascii', errors='replace').decode())

# ─── 파싱 도우미 함수 (parse_pdfs.py 복제) ───────────────────────────────────────────
def extract_metadata_from_filename(filename):
    name = Path(filename).stem
    date_match = re.search(r'\((\d{4})\.(\d{2})\.(\d{2})\.?\)', name)
    if date_match:
        y, mo, d = date_match.group(1), date_match.group(2), date_match.group(3)
        date_iso = f"{y}-{mo}-{d}"
        year = int(y)
    else:
        date_iso = None
        year = None

    session_match = re.search(r'제(\d+)회', name)
    session_num = int(session_match.group(1)) if session_match else None

    if "정기회" in name:     session_type = "정기회"
    elif "임시회" in name:   session_type = "임시회"
    elif "국정감사" in name: session_type = "국정감사"
    else:                    session_type = "기타"

    order_match = re.search(r'제(\d+)차', name)
    order_num = int(order_match.group(1)) if order_match else None

    if "국정감사" in name:                    meeting_type = "국정감사"
    elif "전체회의" in name:                  meeting_type = "전체회의"
    elif "정보통신방송" in name or "정보통신방송미디어" in name: meeting_type = "정보통신방송소위"
    elif "과학기술원자력" in name:             meeting_type = "과학기술원자력소위"
    elif "예산결산" in name:                  meeting_type = "예산결산소위"
    elif "안건조정" in name:                  meeting_type = "안건조정위원회"
    elif "청원심사" in name:                  meeting_type = "청원심사소위"
    else:                                    meeting_type = "기타"

    return {
        "date": date_iso,
        "session_num": session_num,
        "session_type": session_type,
        "order_num": order_num,
        "meeting_type": meeting_type,
        "year": year,
    }

def normalize_speaker_name(raw_name):
    name = TITLE_PREFIXES.sub('', raw_name).strip()
    if len(name) > 8 or re.search(r'[0-9]', name):
        return None
    if not re.match(r'^[가-힣]{2,8}$', name):
        return None
    return name

def get_speaker_titles(full_text, speaker_names):
    titles = {}
    TITLE_WORDS = {
        "소위원장", "위원장", "위원", "전문위원", "수석전문위원", "정부위원", 
        "차관", "장관", "부처장", "원장", "처장", "청장", "부장관", "실장", 
        "국장", "과장", "사장", "대행", "진술인", "참고인", "증인", "비서관", "행정관"
    }
    
    for line in full_text.split('\n'):
        line = line.strip()
        if not (line.startswith('◯') or line.startswith('○')):
            continue
        content = line[1:].strip()
        words = content.split()
        if len(words) > 0:
            w0 = words[0]
            w1 = words[1] if len(words) > 1 else ""
            w2 = words[2] if len(words) > 2 else ""
            is_w0_name = (2 <= len(w0) <= 4) and re.match(r'^[가-힣]+$', w0) and (w0 not in TITLE_WORDS)
            speaker_name = None
            title = None
            if is_w0_name:
                speaker_name = w0
                if w1 in TITLE_WORDS or w1 in ["의원", "대표"]:
                    title = w1
            else:
                is_w1_name = (2 <= len(w1) <= 4) and re.match(r'^[가-힣]+$', w1) and (w1 not in TITLE_WORDS)
                if is_w1_name:
                    speaker_name = w1
                    title = w0
                    if w2 in TITLE_WORDS or w2 in ["의원", "대표"]:
                        title = w0 + " " + w2
            if speaker_name and title:
                norm = normalize_speaker_name(speaker_name)
                if norm in speaker_names:
                    if norm not in titles or len(title) > len(titles[norm]):
                        titles[norm] = title
    return titles

def build_agenda_details(agendas, full_text, meeting_date):
    import urllib.parse, urllib.request
    details = []
    
    # 캐시 파일 로드
    cache_path = BASE_DIR / "data" / "bill_ids_cache.json"
    cache = {}
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f: cache = json.load(f)
        except: pass
    
    paragraphs = [p.strip() for p in full_text.split('\n\n') if p.strip()]
    if len(paragraphs) < 5:
        paragraphs = [p.strip() for p in full_text.split('\n') if p.strip()]
        
    for agenda in agendas:
        clean_title = re.sub(r'^\d+\.\s*', '', agenda).strip()
        proposer = "의원 발의"
        proposal_date = meeting_date.replace('-', '.') if meeting_date else "국회 계류 중"
        summary = "상세 법안 내용 및 심사 진행 경과는 국회의안정보시스템을 참조해 주세요."
        
        proposer_m = re.search(r'\((.*?발의|.*?제출|.*?의안)\)', agenda)
        if proposer_m:
            proposer = proposer_m.group(1).strip()
        else:
            author_m = re.search(re.escape(clean_title[:8]) + r'.*?(?:의원|정부)\s+(?:대표)?발의', full_text)
            if author_m: proposer = "의원 공동발의"
                
        report_text = []
        found_start = False
        agenda_kw = clean_title[:6]
        
        if len(agenda_kw) >= 3:
            for i, p in enumerate(paragraphs):
                if agenda_kw in p and any(k in p for k in ["보고", "검토", "요지", "설명"]):
                    found_start = True
                    start_idx = i
                    for j in range(start_idx, min(start_idx + 4, len(paragraphs))):
                        curr_p = paragraphs[j]
                        if len(curr_p) > 35 and not any(noise in curr_p for noise in ["개의하도록", "선언합니다", "의석을", "개의를"]):
                            clean_p = re.sub(r'^[◯○]\s*[가-힣]+\s+(?:전문위원|수석전문위원|위원장)?\s*', '', curr_p)
                            report_text.append(clean_p)
                    break
                    
        if report_text:
            merged_report = " ".join(report_text)
            merged_report = re.sub(r'\s+', ' ', merged_report).strip()
            merged_report = re.sub(r'검토보고서 요약본을.*보고드리겠습니다\.?', '', merged_report)
            merged_report = re.sub(r'주요 내용을 말씀드리겠습니다\.?', '', merged_report)
            if len(merged_report) > 80:
                summary = merged_report
                if len(summary) > 800:
                    summary = summary[:800] + "... (이하 회의록 제안설명 참조)"
                    
        bill_no_m = re.search(r'\b\d{7}\b', agenda)
        link = "https://likms.assembly.go.kr/bill/main.do"
        if bill_no_m:
            bill_no = bill_no_m.group(0)
            bill_id = cache.get(bill_no)
            if not bill_id:
                try:
                    url = f"https://likms.assembly.go.kr/bill/bi/common/findBillDetail.do?billNo={bill_no}"
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        res_data = json.loads(resp.read().decode('utf-8'))
                        fetched_id = res_data.get("data", {}).get("billId")
                        if fetched_id:
                            bill_id = fetched_id
                            cache[bill_no] = bill_id
                            with open(cache_path, 'w', encoding='utf-8') as f:
                                json.dump(cache, f, ensure_ascii=False, indent=2)
                except: pass
            if bill_id:
                link = f"https://likms.assembly.go.kr/bill/bi/billDetailPage.do?billId={bill_id}"
        
        details.append({
            "title": agenda,
            "proposer": proposer,
            "proposal_date": proposal_date,
            "summary": summary,
            "link": link
        })
    return details

def extract_speakers_and_text_with_page(page_texts):
    speakers = {}
    current_speaker = None
    TITLE_WORDS = {
        "소위원장", "위원장", "위원", "전문위원", "수석전문위원", "정부위원", 
        "차관", "장관", "부처장", "원장", "처장", "청장", "부장관", "실장", 
        "국장", "과장", "사장", "대행", "진술인", "참고인", "증인", "비서관", "행정관"
    }

    for page_num, text in page_texts:
        for line in text.split('\n'):
            line = line.strip()
            if not line: continue
            if line.startswith('◯') or line.startswith('○'):
                symbol = line[0]
                content = line[1:].strip()
                words = content.split()
                if len(words) > 0:
                    w0 = words[0]
                    w1 = words[1] if len(words) > 1 else ""
                    w2 = words[2] if len(words) > 2 else ""
                    is_w0_name = (2 <= len(w0) <= 4) and re.match(r'^[가-힣]+$', w0) and (w0 not in TITLE_WORDS)
                    speaker_name = None
                    prefix_parts = [symbol]
                    if is_w0_name:
                        speaker_name = w0
                        prefix_parts.append(w0)
                        if w1 in TITLE_WORDS or w1 in ["의원", "대표"]:
                            prefix_parts.append(w1)
                    else:
                        is_w1_name = (2 <= len(w1) <= 4) and re.match(r'^[가-힣]+$', w1) and (w1 not in TITLE_WORDS)
                        if is_w1_name:
                            speaker_name = w1
                            prefix_parts.extend([w0, w1])
                            if w2 in TITLE_WORDS or w2 in ["의원", "대표"]:
                                prefix_parts.append(w2)
                    norm_name = normalize_speaker_name(speaker_name) if speaker_name else None
                    if norm_name:
                        current_speaker = norm_name
                        prefix = " ".join(prefix_parts)
                        clean_line = line[len(prefix):].strip()
                        if current_speaker not in speakers:
                            speakers[current_speaker] = []
                        speakers[current_speaker].append({"page": page_num, "text": clean_line})
            else:
                if current_speaker:
                    speakers[current_speaker].append({"page": page_num, "text": line})
    return speakers

def extract_agendas(text):
    agendas = []
    lines = text.split('\n')
    is_agenda_sec = False
    for line in lines:
        line = line.strip()
        if "의사일정" in line:
            is_agenda_sec = True
            continue
        if is_agenda_sec:
            if re.match(r'^\d+\.', line):
                agendas.append(line)
            elif line and not any(kw in line for kw in ["개의", "선언", "의석", "정돈"]):
                if agendas:
                    agendas[-1] += " " + line
            elif any(kw in line for kw in ["개의", "선언"]):
                break
    return [re.sub(r'\s+', ' ', a).strip() for a in agendas]

def extract_keywords(text, top_n=30, extra_stopwords=None, meeting_keywords=None, is_speaker=False):
    words = re.findall(r'[가-힣]{2,8}', text)
    stopwords = STOPWORDS.copy()
    if extra_stopwords: stopwords.update(extra_stopwords)
    filtered = [w for w in words if w not in stopwords]
    counter = Counter(filtered)
    
    # Speaker keywords selection: match meeting main keywords if possible
    if is_speaker and meeting_keywords:
        mt_words = set(k["word"] for k in meeting_keywords)
        results = []
        for w, c in counter.most_common(50):
            if w in mt_words:
                results.append({"word": w, "count": c})
            if len(results) >= top_n: break
        if len(results) < top_n:
            existing = set(r["word"] for r in results)
            for w, c in counter.most_common(50):
                if w not in existing:
                    results.append({"word": w, "count": c})
                if len(results) >= top_n: break
        return results[:top_n]
        
    return [{"word": w, "count": c} for w, c in counter.most_common(top_n)]

def extract_speech_summary(speakers, date, title, agendas, keywords, speaker_titles):
    # Dumb summary builder mimicking the AI executive summaries or assembly-specific formats
    kws = [k["word"] for k in keywords[:3]]
    agenda_str = ", ".join(agendas[:2]) if agendas else "현안질의"
    summary_sentence = f"{title}가 {date}에 개회되어 {agenda_str} 등을 상정하고 논의를 진행하였습니다."
    
    facts = []
    for spk, lines in list(speakers.items())[:3]:
        words = Counter([w for line in lines for w in re.findall(r'[가-힣]{2,6}', line['text']) if w not in STOPWORDS])
        top_words = [w for w, c in words.most_common(3)]
        facts.append(f" ㅇ [{spk} 위원] {', '.join(top_words)} 관련 주요 현안에 대해 발언하고 대책 마련을 촉구함.")
        
    ref_issues = []
    if kws:
        ref_issues.append(f"주요 쟁점 키워드로는 {', '.join(kws)} 등이 도출되었습니다.")
        
    report = f"[{date}] {title}\n\n1. 총 평 (Executive Summary):\n ㅇ {summary_sentence}\n"
    for f in facts: report += f + "\n"
    for r in ref_issues: report += " ※ " + r + "\n"
    return report

HEADER_PATTERNS = [
    re.compile(r'^제\s*\d+\s*회\s*-\s*[가-힣a-zA-Z0-9\s()_-]+?\(\d{4}년\s*\d{1,2}월\s*\d{1,2}일\)\s*\d+$'),
    re.compile(r'^\d+\s+제\s*\d+\s*회\s*-\s*[가-힣a-zA-Z0-9\s()_-]+?\(\d{4}년\s*\d{1,2}월\s*\d{1,2}일\)$'),
    re.compile(r'^-\s*\d+\s*-$'),
]

def strip_page_noise(text):
    lines = []
    for line in text.split('\n'):
        line_strip = line.strip()
        is_noise = False
        for pattern in HEADER_PATTERNS:
            if pattern.match(line_strip):
                is_noise = True
                break
        if not is_noise: lines.append(line)
    return "\n".join(lines)

def parse_pdf(filepath):
    result = {
        "filepath": str(filepath),
        "filename": filepath.name,
        **extract_metadata_from_filename(filepath.name)
    }
    full_text = ""
    page_texts = []
    try:
        with pdfplumber.open(filepath) as pdf:
            pages_to_read = min(len(pdf.pages), MAX_PAGES)
            for idx, page in enumerate(pdf.pages[:pages_to_read]):
                try:
                    t = page.extract_text()
                    if t:
                        page_num = idx + 1
                        t = strip_page_noise(t)
                        full_text += t + "\n"
                        page_texts.append((page_num, t))
                except: pass
    except Exception as e:
        result.update({"error": str(e), "text_length": 0, "keywords": [], "speakers": [], "summary": "", "agendas": []})
        return result

    result["text_length"] = len(full_text)
    speakers_dict = extract_speakers_and_text_with_page(page_texts)

    merged = {}
    for spk, lines in speakers_dict.items():
        key = spk[-2:] if len(spk) >= 2 else spk
        if key in merged:
            merged[key]['lines'].extend(lines)
            if len(spk) < len(merged[key]['name']):
                merged[key]['name'] = spk
        else:
            merged[key] = {'name': spk, 'lines': lines}

    raw_agendas = extract_agendas(full_text)
    result["agendas"] = build_agenda_details(raw_agendas, full_text, result["date"])
    
    speaker_names = set()
    for info in merged.values():
        name = info['name']
        speaker_names.add(name)
        if len(name) >= 3:
            speaker_names.add(name[1:])
            speaker_names.add(name[2:])
            
    result["keywords"] = extract_keywords(full_text, top_n=30, extra_stopwords=speaker_names)

    speaker_list = []
    for info in merged.values():
        spk_text = " ".join([line['text'] for line in info['lines']])
        spk_keywords = extract_keywords(
            spk_text, 
            top_n=10, 
            extra_stopwords=speaker_names,
            meeting_keywords=result["keywords"],
            is_speaker=True
        )
        speaker_list.append({
            "name": info['name'],
            "speech_count": len(info['lines']),
            "keywords": spk_keywords,
            "lines": info['lines']
        })
    speaker_list.sort(key=lambda x: x["speech_count"], reverse=True)
    result["speakers"] = speaker_list[:25]

    cleanTitle = re.sub(r'^제22대국회\s+과학기술정보방송통신위원회\s+회의록\s+', '', filepath.name.replace('.PDF','').replace('.pdf',''))
    cleanTitle = re.sub(r'^제22대국회\s+', '', cleanTitle)
    title_match = re.match(r'제(\d+)회\((.+?)\)\s+제(\d+)차\s+(.+)', cleanTitle)
    displayTitle = cleanTitle
    if title_match:
        displayTitle = f"제{title_match.group(1)}회({title_match.group(2)}) 제{title_match.group(3)}차 {title_match.group(4)}"

    speaker_titles = get_speaker_titles(full_text, [info['name'] for info in merged.values()])
    text_only_speakers = {info['name']: info['lines'] for info in merged.values()}
        
    result["summary"] = extract_speech_summary(
        text_only_speakers,
        date=result["date"],
        title=displayTitle,
        agendas=[a["title"] for a in result["agendas"]],
        keywords=result["keywords"],
        speaker_titles=speaker_titles
    )
    return result

def is_duplicate(filename):
    return bool(re.search(r'\s*\(1\)\s*\.(pdf|PDF)$', filename))

# ─── Supabase 데이터베이스 업로드 함수 ───────────────────────────────────────────
def upload_meeting_to_supabase(conn, m):
    filename = m["filename"]
    
    with conn.cursor() as cur:
        # 1. Insert meeting
        cur.execute("""
            INSERT INTO meetings (filename, date, session_num, session_type, order_num, meeting_type, year, text_length, summary, file_size, parsed_full)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (filename) DO UPDATE 
            SET date=EXCLUDED.date, session_num=EXCLUDED.session_num, session_type=EXCLUDED.session_type, 
                order_num=EXCLUDED.order_num, meeting_type=EXCLUDED.meeting_type, year=EXCLUDED.year,
                text_length=EXCLUDED.text_length, summary=EXCLUDED.summary, file_size=EXCLUDED.file_size,
                parsed_full=EXCLUDED.parsed_full
            RETURNING meeting_id;
        """, (
            filename, m.get("date"), m.get("session_num"), m.get("session_type"),
            m.get("order_num"), m.get("meeting_type"), m.get("year"),
            m.get("text_length"), m.get("summary"), m.get("file_size", 0), m.get("parsed_full", False)
        ))
        meeting_id = cur.fetchone()[0]
        
        # Clean existing relations
        cur.execute("DELETE FROM agendas WHERE meeting_id = %s;", (meeting_id,))
        cur.execute("DELETE FROM speeches WHERE meeting_id = %s;", (meeting_id,))
        cur.execute("DELETE FROM keywords WHERE meeting_id = %s;", (meeting_id,))
        
        # 2. Insert agendas
        agendas_data = []
        for ag in m.get("agendas", []):
            agendas_data.append((
                meeting_id, ag.get("title"), ag.get("proposer"),
                ag.get("proposal_date"), ag.get("summary"), ag.get("link")
            ))
        if agendas_data:
            execute_values(cur, """
                INSERT INTO agendas (meeting_id, title, proposer, proposal_date, summary, link)
                VALUES %s
            """, agendas_data)
        
        # 3. Insert speeches
        speeches_data = []
        for spk in m.get("speakers", []):
            name = spk.get("name")
            speech_cnt = spk.get("speech_count", 0)
            for line in spk.get("lines", []):
                speeches_data.append((
                    meeting_id, name, line.get("text"), line.get("page"), speech_cnt, None, None
                ))
        if speeches_data:
            execute_values(cur, """
                INSERT INTO speeches (meeting_id, speaker_name, content, page, speech_count, sentiment, ai_summary)
                VALUES %s
            """, speeches_data)
        
        # 4. Insert keywords
        keywords_data = []
        for kw in m.get("keywords", []):
            keywords_data.append((meeting_id, None, kw.get("word"), kw.get("count")))
        for spk in m.get("speakers", []):
            name = spk.get("name")
            for kw in spk.get("keywords", []):
                keywords_data.append((meeting_id, name, kw.get("word"), kw.get("count")))
        if keywords_data:
            execute_values(cur, """
                INSERT INTO keywords (meeting_id, speaker_name, word, count)
                VALUES %s
            """, keywords_data)
            
        conn.commit()

# ─── 메인 파이프라인 함수 ───────────────────────────────────────────
def main():
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        safe_print("오류: SUPABASE_DB_URL 환경 변수가 없습니다.")
        sys.exit(1)
        
    pdf_dir = Path(PDF_DIR)
    if not pdf_dir.exists():
        safe_print(f"오류: {PDF_DIR} 없음")
        sys.exit(1)

    try:
        # Strip query parameters like ?pgbouncer=true for psycopg2/libpq compatibility
        conn_url = db_url.split("?")[0] if "?" in db_url else db_url
        conn = psycopg2.connect(conn_url)
    except Exception as e:
        safe_print(f"데이터베이스 연결 실패: {e}")
        sys.exit(1)

    # 1. Supabase에서 기존 캐시 로드
    existing_meetings = {}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT filename, file_size, parsed_full FROM meetings;")
            for filename, file_size, parsed_full in cur.fetchall():
                existing_meetings[filename] = {"file_size": file_size, "parsed_full": parsed_full}
    except Exception as e:
        safe_print(f"캐시 로드 실패: {e}")
        pass

    all_pdfs = sorted([
        f for f in pdf_dir.iterdir()
        if f.suffix.lower() == '.pdf' and not is_duplicate(f.name)
    ], key=lambda p: p.stat().st_size)

    total = len(all_pdfs)
    safe_print(f"총 {total}개 회의록 중 갱신 대상 선별 및 Supabase 파싱 시작")

    done = 0
    pdfs_to_parse = []

    for p in all_pdfs:
        cached = existing_meetings.get(p.name)
        if cached and cached.get("parsed_full") and cached.get("file_size") == p.stat().st_size:
            done += 1
            safe_print(f"[{done:3d}/{total}] (캐시사용) {p.name}")
        else:
            pdfs_to_parse.append(p)

    if pdfs_to_parse:
        safe_print(f"새로 파싱하여 Supabase에 동기화할 PDF 개수: {len(pdfs_to_parse)}개")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_path = {executor.submit(parse_pdf, p): p for p in pdfs_to_parse}
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                done += 1
                try:
                    data = future.result()
                    # 캐시 정보 추가
                    data["parsed_full"] = True
                    data["file_size"] = path.stat().st_size
                    
                    # Supabase에 삽입
                    upload_meeting_to_supabase(conn, data)
                    safe_print(f"[{done:3d}/{total}] (Supabase 업로드완료) {path.name}")
                except Exception as e:
                    safe_print(f"[{done:3d}/{total}] ERR {path.name[:40]}: {e}")
    else:
        safe_print("모든 회의록이 이미 Supabase와 최신 동기화 상태입니다.")

    conn.close()
    safe_print("\n완료!")

if __name__ == "__main__":
    main()
