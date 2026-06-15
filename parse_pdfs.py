#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
제22대 국회 과학기술정보방송통신위원회 회의록 PDF 파서 v3
개선사항:
  - 불용어 대폭 강화 (기관명, 법안형식어, 직책어)
  - 발언 내용 요약: 실제 발언 텍스트에서 핵심 내용 추출
  - 발언자 이름 정규화 (직책 접두사 제거)
  - 안건 추출 정확도 향상
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

# === 설정 ===
PDF_DIR    = r"C:\Users\hp\bills_council\pdf_22nd"
OUTPUT_PATH = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\data\meetings.json"
MAX_PAGES  = 20
MAX_WORKERS = 6

# ─── 불용어 (대폭 강화 및 노이즈 직책어/조사/형식어 배제) ───────────────────────────────────────────
STOPWORDS = set([
    # 법안 형식어 및 무의미 단어
    "일부개정법률안","전부개정법률안","일부개정법률","제정법률안","법률안","시행령",
    "대표발의","의안번호","정부제출","위원대표","의원대표","의안","법률","개정안",
    "개정법률안","일부개정","전부개정","법률안등","의안제","법률안은","법률안에",
    "대안","보편적","연번","보고사항","주시기","바랍니다","존경하는","이의",
    # 기관/위원회명 노이즈 배제
    "과학기술정보방송","과학기술정보통신","방송통신위원회","방송통신위원",
    "정보통신방송","과학기술정보","한국방송공사","방송미디어통신위",
    "방송미디어통신심","과학기술원자력","정보통신망","한국교육방송",
    "한국인터넷진흥","방송통신","과학기술","정보통신","방송미디어",
    # 직책/역할어 (키워드에서 완전 제외)
    "위원장","소위원장","수석전문위원","전문위원","부위원장","간사",
    "위원","장관","차관","부장관","처장","청장","원장","이사장","사장","대표이사",
    "후보자","직무대행","장직무대행","후보","대행","비서관","행정관","참고인","증인","진술인",
    "의원","의원은","의원이","의원님","의원들의","한국방송공사사장",
    # 주요 인물명 노이즈 (의원 탭에 별도 표기되므로 키워드에서 완전 배제)
    "최민희","최형두","김현","노종면","이정헌","황정아","박충권","이훈기",
    "이상휘","박정훈","김장겸","이준석","정동영","이해민","최수진","한민수",
    "임명현","이복우","조인철","이주희","김태규","이진숙","유상임","박민",
    "김종철","류희림","안형준","박민규","김우영","권영진","신동욱","김남근",
    "김영배","정일영","유영상","김범섭","김종원","고광헌","박대준",
    "신성범","배경훈","박장범","류제명","강도현","이창윤",
    # 일반 동사/형용사/조사 (있는, 관한, 하는, 하고 등 노이즈 완벽 소거)
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
    # 사용자의 키워드 배제(X) 정밀 피드백 완벽 반영
    "위원님","통신제","통신소위제","정부","특별법 통과","그러니까","보면",
    "해서","말씀을","설치","운영에","방송통신위원회의","부총리겸과학기술",
    "정보통신부장관","년도","의견을","주십시오","기반","생각을","부분에",
    "이사","필요가","해야","신뢰","니다","방통위","년도국감","디지털",
    "방송통신위원장후","보자","말씀해","소위","굉장히","있음",
    "방송통신위원장직","이것은","인사청문회","청문회","번호","국회",
    # 대명사/부사
    "이것","그것","저것","우리가","저희가","우리는","저희는","저희들",
    "거기에","여기에","지금은","현재는","이미","아직","계속","바로",
    "조금","잠깐","잠시","다시","한번","사실","그냥","정말","아마",
    "조금더","좀더","많이","너무","매우","상당히","충분히","대단히",
    # 조사/어미
    "이","가","을","를","은","는","의","에","와","과","도","로","으로",
    "에서","에게","부터","까지","이다","있다","없다","하다","되다",
    "것","수","그","저","좀","그리고","그래서","그러나","그런데",
    "하지만","또한","또는","및","등","즉","따라서","그렇","으며",
    "이며","이고","이나","이라","에도","으로는","으로도","에서는",
    # 시간/숫자 관련
    "년","월","일","시","분","번","제","차","항","호","조","조항",
    "이상","이하","다음","이전","최근","현재","지난","올해","내년",
    "작년","오늘","내일","어제","이번","다음번","지금","때",
    # 기타 일반 명사 불용어
    "문제","부분","경우","상황","내용","사항","방면","측면","정도",
    "관련","대해","대한","통해","위해","때문","생각","말씀",
    "여기","거기","모든","모두","각각","여러","가지",
    "어떤","무슨","누가","왜","언제","어디","예","아니","맞습니다",
    "됩니","있습","없습","였습","이런","그런","저런","같은","다른",
    "제가","저는","그게","이게","우리","저희","하여","통해서","위하여",
    "육성에","하는데","등의","운영","운영에","운영을","운영이","운영은","운영도",
    "하고법안","하는법안","할법안","법안","법안의","법안을","법안이","법안에",
    "통과","상정","검토","의결",
    # 4차 정제 추가
    "대표발","그리","주시","이렇","어떻","이훈","원회상임위원","상임위","의원안",
    "그다음","그다음에","그러","그렇","이러","하지","개의","회의","보고","제출",
    "준수","주시기","어떻게","하기","하게","하고","그리고","공동발의","소관",
    "상임위원회",
    # 7차 보완 신규 추가
    "기존", "아니라", "아니고", "아니면", "아닙니다", "하나", "일부", "대부분", "자리", "선서", "자료제출", "제정법", "현행법",
    "먼저", "얘기", "필요", "시간", "것들", "국민들", "회계연", "회계연도", "연도", "년도", "제도", "보도", "의도", "태도", "부분들",
    "방미통위", "과방위", "방심위", "과기부", "문화체육관광부", "무대행", "직무대행", "위원장님", "간사님", "위원님들",
    "했습니다", "드리겠습니다", "따라", "하면", "있어서", "번째", "하십니까", "하셨습니다",
    # 9차 보완 신규 추가 (일반명사 제외)
    "국민", "근거", "지원",
    # 10차 보완 신규 추가 (의사결정 맥락 무관 고빈도 일반 명사 및 부처명)
    "자료", "사업", "규정", "요구", "사람", "과정", "취지", "이유", "분야", "진흥", "답변", "중요", "절차", "진행", "활용", "본인", "발언", "조사", "안건", "대표", "관리", "의사진행발언", "대한민국", "기재부", "부처", "입장", "발전", "의제", "과학기술정보통신부", "문화체육관광부",
    # 11차 보완 신규 추가 (의제와 무관한 서술형/연결형 멘트 배제)
    "있다고", "들어", "보니까", "관련된", "주신", "되면", "있기", "보시겠습니다",
    # 12차 보완 신규 추가 (회의 진행/절차상 반복어 및 무의미한 서술어 완벽 배제)
    "없으십니까", "가결되었음", "관련되어져서", "마련해", "반대", "심사", "조정", "개회", "통합", "업무", "기관", "기능", "접근",
    "선포", "가결", "부결", "개의선포", "개의하도록", "선언합니다", "의석을정돈해", "의석을", "정돈해", "개의를", "이의가",
    "없으므로", "되었음을", "선포합니다", "의결하고자", "찬성하시는", "반대하시는", "보고해", "보고해주시기", "방지", "보호", "토론",
    # 13차 보완 신규 추가 (사용자 피드백 반영: 일반명사 및 절차어 노이즈 완벽 소거)
    "단계", "보장", "중단", "마이크", "법상", "상황", "의견", "생각", "말씀", "부분", "내용", "사항", "경우",
    # 14차 보완 신규 추가 (단독 일반명사 제외 및 결합구체화 유도)
    "콘텐츠", "컨텐츠", "산업", "체계", "영역", "활동", "플랫폼", "문화", "기준", "기업", "제작",
    # 15차 보완 신규 추가 (의제 무관 고빈도 일반명사 차단)
    "방법", "부담", "역할", "노력", "판단", "기대", "평가", "확보", "대비", "자체", "이전", "이후",
    # 16차 보완 신규 추가 (문맥 분석 기반 무의미어/부사/대명사 소거)
    "주요", "함께", "경험", "차원", "사실", "자체", "진짜", "내지", "이유", "의견", "정도", "대해"
])

# 직책 접두사 패턴 (발언자 이름 정규화용)
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
    """
    발언자 이름 정규화.
    '소위원장 최형두' → '최형두'
    '위원장 최민희'  → '최민희'
    """
    name = TITLE_PREFIXES.sub('', raw_name).strip()
    if len(name) > 8 or re.search(r'[0-9]', name):
        return None
    if not re.match(r'^[가-힣]{2,8}$', name):
        return None
    return name


def get_speaker_titles(full_text, speaker_names):
    """
    본문 텍스트를 검색하여 각 발언자의 국회/정부 직책을 동적으로 매핑합니다.
    """
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
            
        symbol = line[0]
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
                
    return titles


def build_agenda_details(agendas, full_text, meeting_date):
    """
    각 상정 안건에 대해 본문에서 제안일자, 제안자, 제안이유 및 주요 내용을 지능적으로 추출하여 
    풍부한 입법 정보 데이터 오브젝트 배열을 빌드합니다.
    """
    import urllib.parse
    import urllib.request
    import json
    from pathlib import Path
    details = []
    
    # 캐시 파일 위치
    cache_path = Path(r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\data\bill_ids_cache.json")
    cache = {}
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception:
            pass
    
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
            if author_m:
                proposer = "의원 공동발의"
                
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
                    
        # 7자리 의안번호 추출하여 direct billDetailPage.do?billId=PRC_... 링크 빌드
        bill_no_m = re.search(r'\b\d{7}\b', agenda)
        link = "https://likms.assembly.go.kr/bill/main.do"
        if bill_no_m:
            bill_no = bill_no_m.group(0)
            bill_id = cache.get(bill_no)
            if not bill_id:
                # 실시간으로 LIKMS API 쿼리하여 캐시 업데이트
                try:
                    url = f"https://likms.assembly.go.kr/bill/bi/common/findBillDetail.do?billNo={bill_no}"
                    req = urllib.request.Request(
                        url,
                        headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0',
                            'Referer': 'https://likms.assembly.go.kr/bill/main.do'
                        }
                    )
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        res_data = json.loads(resp.read().decode('utf-8', errors='replace'))
                        fetched_id = res_data.get("data", {}).get("billId")
                        if fetched_id:
                            bill_id = fetched_id
                            cache[bill_no] = bill_id
                            # 캐시 파일 갱신
                            cache_path.parent.mkdir(parents=True, exist_ok=True)
                            with open(cache_path, 'w', encoding='utf-8') as f:
                                json.dump(cache, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
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
    """발언자 추출. 페이지 번호를 유지하며 ◯/○ 패턴으로 매칭합니다."""
    speakers = {}
    current_speaker = None
    current_text = []

    TITLE_WORDS = {
        "소위원장", "위원장", "위원", "전문위원", "수석전문위원", "정부위원", 
        "차관", "장관", "부처장", "원장", "처장", "청장", "부장관", "실장", 
        "국장", "과장", "사장", "대행", "진술인", "참고인", "증인", "비서관", "행정관"
    }

    global_line_idx = 0
    for page_num, text in page_texts:
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            global_line_idx += 1
            
            # line starts with ◯ or ○
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
                            prefix_parts.append(w0)
                            prefix_parts.append(w1)
                            if w2 in TITLE_WORDS or w2 in ["의원", "대표"]:
                                prefix_parts.append(w2)
                                
                    if speaker_name:
                        # Normalize speaker name
                        norm = normalize_speaker_name(speaker_name)
                        if norm:
                            if current_speaker and current_text:
                                speakers.setdefault(current_speaker, []).extend(current_text)
                            current_speaker = norm
                            
                            # Reconstruct the exact prefix matched to strip it
                            matched_words_count = len(prefix_parts) - 1 # exclude symbol
                            line_words = line.split()
                            prefix_words = line_words[:matched_words_count]
                            prefix_str = " ".join(prefix_words)
                            
                            idx_prefix = line.find(prefix_str)
                            if idx_prefix != -1:
                                rest = line[idx_prefix + len(prefix_str):].strip()
                            else:
                                rest = line[1:].strip()
                                
                            current_text = [{"text": rest, "page": page_num, "idx": global_line_idx}] if rest else []
                            continue
            
            # If it doesn't start with symbol, or didn't match a speaker_name:
            if current_speaker and line:
                current_text.append({"text": line, "page": page_num, "idx": global_line_idx})

    if current_speaker and current_text:
        speakers.setdefault(current_speaker, []).extend(current_text)

    return speakers


def strip_josa(word):
    """
    한국어 조사 및 어미를 제거하여 명사 원형을 추출 (간이 형태소 분석 모듈)
    """
    josa_suffixes = [
        "위원회는", "위원회에서", "위원회도", "위원회가", "위원회",
        "있다라고", "했다라고", "한다라고", "이다라고", "없다라고", "되다라고",
        "라더군요", "하더군요", "라더라고", "하더라고", "했다며", "한다며", "이라며",
        "것이고요", "것이고", "것이죠", "것이지", "것인가", "것인가요",
        "이라면서", "라면서", "이라서", "이라도", "이라며", "이라",
        "으로서", "에서는", "으로부터", "에서도", "에서", 
        "부터", "까지", "으로", "로써", "님", "들", "도", "나", "며", "든", "만", "뿐", "쯤", "치", "란", "랑",
        "하고", "하며", "하여", "의", "에", "로", "을", "를", "은", "는", "이", "가",
        "과", "와", "는데", "며는", "면서", "해서", "하는", "하다", "한", "할", "한대", "할때", "은데", "ㄴ데",
        "입니다", "합니다", "했습니다", "해야", "하겠다", "하겠습니", "였다", "였다가", "였다는", "한다", "했다",
        "라고", "이고", "고", "라며", "하며", "다며", "하면", "해서", "였다", "였고", "됐다", "됐고", "이다"
    ]
    changed = True
    while changed:
        changed = False
        for j in josa_suffixes:
            if word.endswith(j) and len(word) > len(j):
                word = word[:-len(j)]
                changed = True
                break
    return word


def extract_keywords(text, top_n=20, extra_stopwords=None, meeting_keywords=None, is_speaker=False):
    """
    구체적 법안/인물/사건 결과 매칭 중심 키워드 정제 (치환 및 구체화 v4 완벽 구현)
    """
    local_stopwords = STOPWORDS
    if extra_stopwords:
        local_stopwords = STOPWORDS.union(extra_stopwords)

    specific_laws = []
    
    # 1. 인사청문회 구체화 (누구 인사청문회인지 매칭)
    if "청문회" in text or "인사청문회" in text:
        person = "소관"
        for name in ["이진숙", "유상임", "김홍일", "이동관", "박장범", "임명현"]:
            if name in text:
                person = name
                break
        specific_laws.extend([f"{person} 인사청문회"] * 4)

    # 2. 기본법 구체화 (~기본법 -> ~기본법 통과)
    base_laws = re.findall(r'([가-힣]{2,8}기본법)(?:안|률안)?', text)
    for bl in base_laws:
        if bl not in local_stopwords:
            specific_laws.extend([f"{bl} 통과"] * 3)
    if "기본법" in text and not base_laws:
        # 매칭 안될 경우 우주항공청법이나 인공지능법 등의 맥락에 맞춰 Fallback
        if "인공지능" in text:
            specific_laws.extend(["인공지능기본법 통과"] * 2)
        elif "국정감사" in text:
            specific_laws.extend(["과학기술기본법 통과"] * 2)
            
    # 3. 이용촉진 구체화 (이용촉진 -> ~이용촉진법 통과)
    if "이용촉진" in text or "정보보호" in text:
        if "정보통신망" in text:
            specific_laws.extend(["정보통신망이용촉진법 통과"] * 3)
        else:
            specific_laws.extend(["정보통신이용촉진법 통과"] * 2)

    # 4. 진흥법 구체화 (진흥법 -> ~진흥법 통과)
    promotion_laws = re.findall(r'([가-힣]{2,8}진흥법)(?:안|률안)?', text)
    for pl in promotion_laws:
        if pl not in local_stopwords:
            specific_laws.extend([f"{pl} 통과"] * 3)
            
    # 5. 특별법안 구체화 (특별법안 -> ~특별법안 통과)
    special_laws = re.findall(r'([가-힣]{2,8}특별법(?:안)?)(?:률안)?', text)
    for sl in special_laws:
        if sl not in local_stopwords and "특별법" not in sl:
            specific_laws.extend([f"{sl} 통과"] * 3)
    if "특별법안" in text and not special_laws:
        if "우주항공" in text:
            specific_laws.extend(["우주항공청특별법안 통과"] * 3)

    # 6. 한국교육방송공사 구체화 ("멀 어쨌다는건지")
    if "한국교육방송공사" in text or "EBS" in text:
        if "법" in text or "개정" in text:
            specific_laws.extend(["한국교육방송공사법 통과"] * 3)
        else:
            specific_laws.extend(["EBS 임원진 심사 검토"] * 2)

    # 7. 국회 구체화 ("멀 어쨌다는건지")
    if "국회" in text:
        if "국회법" in text:
            specific_laws.extend(["국회법 개정안 통과"] * 3)
        elif "질의" in text or "보고" in text:
            specific_laws.extend(["국회 상임위 현안질의"] * 2)

    # 8. 방송문화진흥회법 구체화 ("어떻게 되었는지")
    if "방송문화진흥회법" in text or "방문진" in text:
        if "통과" in text or "의결" in text:
            specific_laws.extend(["방송문화진흥회법 통과"] * 4)
        else:
            specific_laws.extend(["방송문화진흥회법 개정안 검토"] * 2)

    # 9. 기존 특정 법안 및 정규식 추출 (최대 길이 25로 상향하여 이름이 긴 법안 잘림 현상 방지)
    law_matches = re.findall(r'([가-힣A-Za-z0-9]{2,25}\s*법(?:안|개정안|률안|폐지안)?)', text)
    for law in law_matches:
        law_clean = re.sub(r'\s+', '', law).strip()
        # 노이즈 정제 ("관한법", "관한" 등 노이즈 완벽 차단)
        if any(sw in law_clean for sw in ["일부개정", "전부개정", "법률안", "의안제", "원회", "관련법", "관한법", "관한법률", "기본법"]):
            continue
        
        # 만약 law_clean이 불용어로 시작하거나 (예: 하고법안) 불용어를 포함하면 제외
        prefix_match = re.search(r'^(.*?)(?:법(?:안|개정안|률안|폐지안)?)$', law_clean)
        if prefix_match:
            prefix = prefix_match.group(1)
            if len(prefix) < 2 or prefix in local_stopwords or any(prefix.startswith(sw) for sw in local_stopwords if len(sw) >= 2):
                continue
                
            # 동사/형용사 어미 Modifiers 및 무의미한 수식어가 붙은 가짜 법안명 차단 (예: '만드는법', '발의한법', '3개의법', '위헌적인법' 등)
            invalid_prefix_endings = (
                "한", "는", "은", "인", "던", "고", "의", "을", "야", "로", "운", "해", "된", "형", "적", "를"
            )
            if any(prefix.endswith(ending) for ending in invalid_prefix_endings):
                continue
                
            # 숫자가 포함된 가짜 법안명 차단 (예: '30일법안', '2건의법' 등)
            if any(char.isdigit() for char in prefix):
                continue

        if "관한" in law_clean or len(law_clean) < 3:
            continue
        # 최대 길이를 20으로 상향하여 정상적인 긴 법안명도 통과/상정 정보가 정상 결합되도록 처리
        if len(law_clean) <= 20:
            if "통과" in text or "의결" in text:
                specific_laws.extend([f"{law_clean} 통과"] * 3)
            elif "상정" in text:
                specific_laws.extend([f"{law_clean} 상정"] * 3)
            else:
                specific_laws.extend([f"{law_clean} 검토"] * 2)

    # 주요 고유이슈 고정 룰셋
    policy_issues = [
        ("인공지능기본법", "인공지능법 통과"),
        ("단말기유통법", "단통법 폐지안"),
        ("단통법", "단통법 폐지안"),
        ("우주항공청", "우주항공청 설립"),
        ("라인야후", "라인야후 사태 대응"),
        ("류희림", "방송통신심의위 이슈"),
        ("연구개발예산", "R&D 예산 삭감"),
        ("티메프", "티메프 사태 조사"),
        ("망이용", "망이용대가법 검토"),
        ("네이버", "네이버 라인야후 사태"),
    ]
    for key, output in policy_issues:
        if key in text:
            specific_laws.extend([output] * 4)

    # 9-2. 단독 일반명사 구체화 (ㅇㅇ콘텐츠, ㅇㅇ산업, ㅇㅇ체계, ㅇㅇ영역, ㅇㅇ활동, ㅇㅇ플랫폼, ㅇㅇ제작, ㅇㅇ문화, ㅇㅇ기업, ㅇㅇ기준)
    concept_patterns = r'([가-힣]{2,10}\s*(?:콘텐츠|컨텐츠|산업|체계|영역|활동|플랫폼|제작|문화|기업|기준))'
    concept_matches = re.findall(concept_patterns, text)
    for cm in concept_matches:
        cm_clean = re.sub(r'\s+', '', cm).strip()
        # 불용어로 시작하지 않는 구체적 결합어에 가중치(3) 부여
        if len(cm_clean) >= 3 and not any(cm_clean.startswith(sw) for sw in local_stopwords if len(sw) >= 2):
            specific_laws.extend([cm_clean] * 3)

    # 10. 일반 단어 카운팅 (정규식을 [가-힣]+ 로 전면 교체하여 단어 잘림/임의 쪼개짐 원천 해결)
    words = re.findall(r'[가-힣]+', text)
    cleaned_words = []
    for w in words:
        # A. 원본 단어가 불용어 세트에 매핑되는지 선행 체크
        if w in local_stopwords:
            continue
            
        # B. 줄바꿈 깨짐 단어 제거 (원회 포함되나 위원회는 아닌 것)
        if "원회" in w and "위원회" not in w:
            continue
            
        # C. 조사/어미 제거 적용
        w_clean = strip_josa(w)
        
        # '과학기술정보통신부제2차관' 등 숫자(2) 앞에서 한글이 잘려 '부제'로 끝나는 접미사 노이즈 처리
        if w_clean.endswith("부제") and len(w_clean) > 3:
            w_clean = w_clean[:-1]
            
        # D. 정제된 단어에 대해 재검사
        if w_clean in local_stopwords:
            continue
            
        if "원회" in w_clean and "위원회" not in w_clean:
            continue

        if len(w_clean) < 2 or len(w_clean) > 10:
            continue

        # E. 구어체 종결 어미가 남아서 동사/형용사형 끝맺음이 남아있는 명사 차단
        if any(w_clean.endswith(ending) for ending in [
            "이고", "라고", "하고", "했다", "한다", "이다", "하며", "라며", "다며", "하면", "해서", "있다", "없다", "였고", "됐고", "인듯", "인것", "이지", "지요",
            "있어요", "없어요", "아니에요", "아닙니다", "이에요", "봅니다", "하네요", "했네요",
            "된다", "맞다", "같다", "같아", "아니냐", "아니라", "그렇"
        ]):
            continue

        # 3자 이상의 단어가 '요'로 끝날 경우 구어체 종결어미일 확률이 매우 높으므로 차단 (예: 있어요, 아니에요, 같아요 등)
        if w_clean.endswith("요") and len(w_clean) >= 3:
            continue
            
        cleaned_words.append(w_clean)

    counter = Counter(specific_laws + cleaned_words)

    # 가중치 및 최소 빈도 필터링 로직 적용
    refined_keywords = []
    if is_speaker and meeting_keywords:
        meeting_kw_words = {kw["word"] for kw in meeting_keywords}
        for word, count in counter.items():
            if word in meeting_kw_words:
                # 회의록 전체 핵심 아젠다와 일치하는 키워드에는 가중치 부여 (우선순위 상승)
                refined_keywords.append((word, count * 2 + 2))
            else:
                # 회의록 핵심 아젠다에 없는 일반 단어는 발언자 수준에서 최소 3회 이상 언급되었을 때만 후보 허용
                if count >= 3:
                    refined_keywords.append((word, count))
    else:
        for word, count in counter.items():
            refined_keywords.append((word, count))
            
    # 정렬
    refined_keywords.sort(key=lambda x: x[1], reverse=True)
    
    # 갯수를 맞추기 위해 억지로 저빈도 노이즈 키워드를 포함하지 않음
    result_kws = []
    for word, score in refined_keywords:
        orig_count = counter[word]
        if is_speaker:
            # 발언자 키워드는 실제 발언 회수가 4회 이상(3회 이하 제외)인 경우만 우선 수집
            if orig_count >= 4:
                result_kws.append({"word": word, "count": orig_count})
        else:
            # 전체 회의록 키워드는 원본 카운트 2 이상인 것 위주로 반영
            if orig_count >= 2:
                result_kws.append({"word": word, "count": orig_count})

    # Adaptive Thresholding: 발언자가 언급한 키워드 개수가 3개 미만인 경우, 
    # 회의록 전체의 핵심 의제(meeting_keywords)와 일치하면서 2~3회 언급된 단어를 지능적으로 구제하여 병합
    if is_speaker and len(result_kws) < 3 and meeting_keywords:
        meeting_kw_words = {kw["word"] for kw in meeting_keywords}
        for word, score in refined_keywords:
            if len(result_kws) >= 3:
                break
            orig_count = counter[word]
            # 이미 포함된 단어는 제외
            if any(k["word"] == word for k in result_kws):
                continue
            # 전체 의제와 연관이 깊고 발언 회수가 2~3회인 경우 구제
            if score > orig_count and orig_count in [2, 3]:
                result_kws.append({"word": word, "count": orig_count})
                
    return result_kws[:top_n]





def extract_agendas(text):
    """의사일정 / 상정 안건 추출 (Fallback 스캔 고도화)"""
    agendas = []
    
    # 1. 기존 블록 매칭 시도
    agenda_block = re.search(
        r'(?:의\s*사\s*일\s*정|상정\s*안건|심사\s*안건)\s*\n(.*?)(?=상정된\s*안건|◯|○|\Z)',
        text, re.DOTALL
    )
    if agenda_block:
        block = agenda_block.group(1)
        items = re.findall(
            r'(?:^|\n)\s*(\d+)\.\s+([가-힣A-Za-z「」『』].{4,80}?)(?=\n\s*\d+\.|\n\n|\Z)',
            block, re.MULTILINE
        )
        for _, item in items[:12]:
            clean = re.sub(r'\s+', ' ', item.strip())
            clean = re.sub(r'[\·\.\s]*$', '', clean)
            if 4 < len(clean) < 100:
                agendas.append(clean)
                
    # 2. 만약 안건을 하나도 못 찾았다면, 본문 전체를 스캔하여 번호 매겨진 법안/의안 목록 파싱 (Fallback)
    if not agendas:
        # 본문 전체에서 "숫자. ~~법률안/개정안/대안/의 건" 유형 탐색
        items = re.findall(
            r'(?:^|\n)\s*(\d+)\.\s+([가-힣A-Za-z0-9\s「」『』\(\)\,\_]{3,80}?(?:법안|률안|개정안|대안|동의안|의 건|보고의 건|계획서|청원안)[^\n]*)',
            text
        )
        for _, item in items[:12]:
            clean = re.sub(r'\s+', ' ', item.strip())
            clean = re.sub(r'[\·\.\s]*$', '', clean)
            if 4 < len(clean) < 100 and not any(clean in a for a in agendas):
                # 개의 선언 및 procedural 멘트 제외
                if not any(noise in clean for noise in ["개의하도록", "선언합니다", "개의를", "의석을", "보고해 주시기"]):
                    agendas.append(clean)
                    
    return list(dict.fromkeys(agendas))[:12]


def convert_to_개조식(sentence):
    """
    일반 평서문 문장을 개조식 종결어미(~함, ~임, ~함에 따라) 형태로 건조하게 변환
    """
    sentence = sentence.strip()
    if not sentence:
        return ""
    
    # 어미 변환 룰셋
    replacements = [
        (r'생각합니다\.?$', '생각함.'),
        (r'판단됩니다\.?$', '판단됨.'),
        (r'보고드립니다\.?$', '보고함.'),
        (r'촉구합니다\.?$', '촉구함.'),
        (r'요구합니다\.?$', '요구함.'),
        (r'지적했습니다\.?$', '지적함.'),
        (r'주장했습니다\.?$', '주장함.'),
        (r'답변했습니다\.?$', '답변함.'),
        (r'설명했습니다\.?$', '설명함.'),
        (r'있습니다\.?$', '있음.'),
        (r'없습니다\.?$', '없음.'),
        (r'합니다\.?$', '함.'),
        (r'습니다\.?$', '음.'),
        (r'됩니다\.?$', '됨.'),
        (r'입니다\.?$', '임.'),
        (r'것으로 보입니다\.?$', '것으로 보임.'),
        (r'것입니다\.?$', '것임.'),
    ]
    
    for pat, rep in replacements:
        sentence = re.sub(pat, rep, sentence)
    
    if not sentence.endswith('.'):
        sentence += '.'
    return sentence


def clean_speech_text(txt):
    if not txt:
        return ""
    # Replace multiple spaces with a single space
    txt = re.sub(r'\s+', ' ', txt)
    # Fix common PDF line break splits
    txt = txt.replace("사실입 니다", "사실입니다").replace("사전 적으로는", "사전적으로는")
    txt = txt.replace("의견이라 는", "의견이라는").replace("의결을 하지 않았기 때문 에", "의결을 하지 않았기 때문에")
    txt = txt.replace("지상파 라 디오", "지상파 라디오").replace("우려하시 는", "우려하시는")
    return txt.strip()


def summarize_question(txt):
    txt = clean_speech_text(txt)
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', txt) if s.strip()]
    if not sentences:
        return "현안에 대해 질의함."

    def clean_filler(s):
        s = re.sub(r'^(어,|음,|그러니까|근데|사실은|제가|저희가|또|그리고|근데,|그게|그게 좀)\s+', '', s)
        s = re.sub(r'^(아니\s+)', '', s)
        return s.strip()

    sentences = [clean_filler(s) for s in sentences]
    sentences = [s for s in sentences if len(s) >= 10]

    if not sentences:
        return "현안에 대해 질의함."

    q_sents = [s for s in sentences if s.endswith('?')]
    if q_sents:
        chosen = q_sents[0]
    else:
        chosen = sentences[-1]

    # Convert question endings to policy report style
    chosen = re.sub(r'의견입니까,?\s*.*?$', '의견인지 질의함.', chosen)
    chosen = re.sub(r'의견입니까[\.\?]*$', '의견인지 질의함.', chosen)
    chosen = re.sub(r'것입니까[\.\?]*$', '것인지 질의함.', chosen)
    chosen = re.sub(r'입니까[\.\?]*$', '인지 질의함.', chosen)
    chosen = re.sub(r'의견이라는 거지요[\.\?]*$', '의견인지 확인을 요구함.', chosen)
    chosen = re.sub(r'거지요[\.\?]*$', '것인지 확인을 요구함.', chosen)
    chosen = re.sub(r'적합합니까[\.\?]*$', '적합한지 질의함.', chosen)
    chosen = re.sub(r'맞습니까[\.\?]*$', '맞는지 질의함.', chosen)
    chosen = re.sub(r'있습니까[\.\?]*$', '있는지 질의함.', chosen)
    chosen = re.sub(r'않습니까[\.\?]*$', '않는지 지적함.', chosen)
    chosen = re.sub(r'생각하십니까[\.\?]*$', '생각하는지 질의함.', chosen)
    chosen = re.sub(r'무엇인가,?\s*.*?$', '무엇인지 의문을 제기함.', chosen)
    chosen = re.sub(r'무엇입니까[\.\?]*$', '무엇인지 질의함.', chosen)
    
    if not any(chosen.endswith(ending) for ending in ['함.', '음.', '임.', '제기함.', '요구함.', '지적함.', '질의함.']):
        if chosen.endswith('있어요.') or chosen.endswith('있습니다.'):
            chosen = re.sub(r'있어요\.?|있습니다\.?$', '있음을 지적함.', chosen)
        elif chosen.endswith('합니다.'):
            chosen = re.sub(r'합니다\.?$', '할 것을 요구함.', chosen)
        elif chosen.endswith('했다.') or chosen.endswith('했습니다.'):
            chosen = re.sub(r'했다\.?|했습니다\.?$', '했음을 지적함.', chosen)
        elif chosen.endswith('있다.'):
            chosen = re.sub(r'있다\.?$', '있음을 지적함.', chosen)
        else:
            chosen = chosen.rstrip('.') + '에 대해 지적함.'

    return chosen


def summarize_answer(txt):
    txt = clean_speech_text(txt)
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', txt) if s.strip()]
    if not sentences:
        return "관련 내용을 답변함."

    def clean_filler(s):
        s = re.sub(r'^(위원님,|어,|음,|저희가|저희는|저희|일단은|일단)\s+', '', s)
        return s.strip()

    sentences = [clean_filler(s) for s in sentences]
    sentences = [s for s in sentences if len(s) >= 12]

    if not sentences:
        return "소관 업무에 대해 답변함."

    decl_sents = [s for s in sentences if any(w in s for w in ["검토", "의결", "계획", "판단", "생각", "설명", "답변", "의견", "사실", "정책"])]
    if decl_sents:
        chosen = decl_sents[0]
    else:
        chosen = sentences[0]

    has_cut_off = False
    if re.search(r'아까 말[\.\?]*$', chosen):
        chosen = re.sub(r'아까 말[\.\?]*$', '의견임을 설명함.', chosen)
        has_cut_off = True
    elif re.search(r'아까 말한.*?$', chosen):
        chosen = re.sub(r'아까 말한.*?$', '의견임을 밝힘.', chosen)
        has_cut_off = True
    elif re.search(r'아까 말씀.*?$', chosen):
        chosen = re.sub(r'아까 말씀.*?$', '답변함.', chosen)
        has_cut_off = True
    elif re.search(r'말\.$', chosen):
        chosen = re.sub(r'말\.$', '답변함.', chosen)
        has_cut_off = True

    if not has_cut_off:
        if chosen.endswith('사실입니다.'):
            chosen = re.sub(r'사실입니다\.?$', '사실이라고 설명함.', chosen)
        elif any(chosen.endswith(ending) for ending in ['임.', '함.', '음.', '밝힘.', '설명함.', '답변함.']):
            pass
        else:
            if chosen.endswith('것입니다.'):
                chosen = re.sub(r'것입니다\.?$', '것이라고 답변함.', chosen)
            elif chosen.endswith('있습니다.'):
                chosen = re.sub(r'있습니다\.?$', '있다고 설명함.', chosen)
            elif chosen.endswith('없습니다.'):
                chosen = re.sub(r'없습니다\.?$', '없다고 답변함.', chosen)
            elif chosen.endswith('합니다.'):
                chosen = re.sub(r'합니다\.?$', '한다고 답변함.', chosen)
            elif chosen.endswith('입니다.'):
                chosen = re.sub(r'입니다\.?$', '이라고 설명함.', chosen)
            elif chosen.endswith('부분임.'):
                chosen = re.sub(r'부분임\.?$', '부분이라고 해명함.', chosen)
            elif chosen.endswith('것이고요.'):
                chosen = re.sub(r'것이고요\.?$', '것이라고 밝힘.', chosen)
            else:
                chosen = chosen.rstrip('.') + '라고 설명함.'

    return chosen


def clean_fact_text(txt):
    if not txt:
        return ""
    txt = re.sub(r'\s+', ' ', txt)
    # Remove leading speech fillers/context markers
    txt = re.sub(r'^(그래서|그리고|하지만|또한|따라서|앞으로|일단)\s+', '', txt)
    txt = re.sub(r'^(저희는|저희가|제가)\s+', '', txt)
    txt = re.sub(r'^[가-힣]{2,4}\s*위원님\s*(?:말씀하신|말씀하신 것의)\s*(?:연장선으로\s*하면|연장선상에서)\s*', '', txt)
    # Clean up trailing numbers/noise
    txt = re.sub(r'\s+\d+\.?$', '', txt)
    return txt.strip()


def summarize_fact(spk, sent, is_member=True):
    cleaned = clean_fact_text(sent)
    if not cleaned:
        return ""
    
    # Apply 개조식 endings
    converted = convert_to_개조식(cleaned)
    role_suffix = " 의원" if is_member else ""
    return f"- **{spk}**{role_suffix}, {converted}"


def extract_speech_summary(speakers_dict, date, title, agendas, keywords, speaker_titles=None):
    """
    국회 대응 CR 전문가 어조의 [상황 보고서(Status Report)] 포맷으로 요약 생성 (개선 v3)
    """
    m_date = date.replace('-', '.') if date else '2026.05.29'
    m_title = title if title else '과학기술정보방송통신위원회 회의'

    # 참석자 정보 조립
    member_list = []
    officer_list = []
    
    COMMISSION_MEMBERS = {
        "최민희", "최형두", "김현", "노종면", "이정헌", "황정아", "박충권", "이훈기", 
        "이상휘", "박정훈", "김장겸", "이준석", "정동영", "이해민", "최수진", "한민수", 
        "조인철", "박민규", "김우영", "신성범", "권영진", "신동욱", "김남근", "김영배", "정일영"
    }
    
    for name in sorted(speakers_dict.keys()):
        if name in ["위원장", "소위원장", "위원장대행", "속기사"]:
            continue
        if len(name) < 2 or len(name) > 4:
            continue
            
        title_val = speaker_titles.get(name, "") if speaker_titles else ""
        if title_val:
            display_name = f"{name}({title_val})"
        else:
            display_name = name
            
        if name in COMMISSION_MEMBERS:
            member_list.append(display_name)
        else:
            officer_list.append(display_name)
            
    attendance_md = ""
    if member_list or officer_list:
        attendance_md = "**참석자:**\n"
        if member_list:
            attendance_md += f"- **위원:** {', '.join(member_list)}\n"
        if officer_list:
            attendance_md += f"- **정부관계자 및 진술인 등:** {', '.join(officer_list)}\n"
        attendance_md += "\n"

    # 1. 핵심 키워드 선정 (볼드용)
    top_kws = [kw["word"] for kw in keywords[:5]]
    bold_kws = []
    for k in top_kws:
        # 공백 제거하여 볼드 처리용 후보군
        bold_kws.append(k.split()[0] if k else '')
    
    # 상시 볼드 대상 (의원명, 부처명)
    always_bold = ["최민희", "최형두", "김현", "노종면", "이정헌", "과기정통부", "방통위", "R&D", "AI", "인공지능", "단통법", "방송법"]
    
    def apply_bold(txt):
        for bk in bold_kws + always_bold:
            if bk and len(bk) >= 2:
                # 무한 볼드 중복 방지를 위한 안전 장치
                txt = re.sub(rf'(?<!\*\*)(?<![가-힣]){re.escape(bk)}(?![가-힣])(?!\*\*)', f'**{bk}**', txt)
        return txt

    # 2. 총평 (Executive Summary) 추출
    full_context = " ".join([" ".join([line["text"] for line in lines]) for lines in speakers_dict.values()])
    summary_sentence = "금일 회의는 주요 현안 법안 상정 및 피질의 기관 정책 모니터링이 집중적으로 이루어짐."
    if agendas:
        summary_sentence = f"금일 회의는 **{agendas[0]}** 등 상정된 주요 현안 의안들에 대한 심사 및 정책 대안 검토가 중점적으로 논의됨."
    elif top_kws:
        if "공청회" in full_context or "인사청문회" in full_context or "청문회" in full_context:
            person = "소관"
            for name in ["이진숙", "유상임", "김홍일", "이동관", "박장범", "임명현"]:
                if name in full_context:
                    person = name
                    break
            if "청문회" in full_context or "인사청문회" in full_context:
                summary_sentence = f"금일 회의는 **{person} 후보자 인사청문회**로서, 후보자의 자격 검증 및 주요 현안에 대한 집중 질의가 진행됨."
            else:
                summary_sentence = f"금일 회의는 **{top_kws[0]}** 관련 주요 법률안 제정을 위한 **공청회**로서, 산업계 및 학계 진술인들의 심도 깊은 의견 청취가 교차함."
        else:
            summary_sentence = f"금일 회의는 **{top_kws[0]}** 및 **{top_kws[1]}** 등 소관 정책 아젠다에 대한 위원회 차원의 현안질의 및 질타가 격렬하게 교차함."

    # 전체 turns 복원 및 idx 오름차순 정렬
    all_lines = []
    for spk, lines in speakers_dict.items():
        for line in lines:
            all_lines.append({
                "speaker": spk,
                "text": line.get("text", ""),
                "page": line.get("page", 1),
                "idx": line.get("idx", 0)
            })
    all_lines.sort(key=lambda x: x["idx"])

    # 연속 턴 병합
    turns = []
    current = None
    for line in all_lines:
        text_clean = line["text"].strip()
        if not text_clean:
            continue
        if not current:
            current = {
                "speaker": line["speaker"],
                "text": text_clean,
                "page": line["page"],
                "idx": line["idx"]
            }
        else:
            if current["speaker"] == line["speaker"]:
                current["text"] += " " + text_clean
            else:
                turns.append(current)
                current = {
                    "speaker": line["speaker"],
                    "text": text_clean,
                    "page": line["page"],
                    "idx": line["idx"]
                }
    if current:
        turns.append(current)

    # 팩트 2~3개 추출
    facts = []
    count = 0
    for turn in turns:
        spk = turn["speaker"]
        if spk in ["위원장", "소위원장", "위원장대행", "속기사"]:
            continue
        q_sents = [s.strip() for s in re.split(r'[.。!?]\s*', turn["text"]) if s.strip()]
        for sent in q_sents:
            if len(sent) >= 35 and any(k in sent for k in top_kws[:3]) and count < 3:
                is_member = spk in COMMISSION_MEMBERS
                fact_str = summarize_fact(spk, sent, is_member)
                if fact_str:
                    facts.append(fact_str)
                    count += 1
                    break

    if not facts:
        facts = [
            "- 주요 상임위 법률안 심사 소위의 법안 검토 및 소관 기관 업무 보고가 진행됨.",
            "- 여야 위원들은 주요 정책 현안에 대한 실효성 및 대정부 질문을 이어감."
        ]

    # 참고사항 동적 구성
    ref_issues = []
    if agendas:
        ref_issues.append(f"상정 안건 {agendas[0]}에 대한 국회 상임위 계류 상황 지속 모니터링 필요.")
    else:
        ref_issues.append("향후 법안심사소위원회 세부 심사 및 소관 부처 대응 조치 모니터링 요망.")

    # Q&A 리스트 구성
    qa_list = []
    qa_count = 0
    MODERATORS = {"위원장", "소위원장", "위원장대행", "속기사"}
    
    # respondents 집합 빌드
    respondents_set = set()
    for k in speakers_dict.keys():
        title_val = speaker_titles.get(k, "") if speaker_titles else ""
        is_officer = any(r in k or r in title_val for r in [
            "장관", "차관", "사장", "원장", "처장", "청장", "방통위", "방송미디어통신위", "국장", "과장", "기획관", "단장", 
            "실장", "본부장", "진술인", "참고인", "증인", "대행", "배경훈", "유상임", "이진숙", "박민", "김태규", "최성희", "류제명"
        ])
        if (is_officer or k not in COMMISSION_MEMBERS) and k not in MODERATORS:
            respondents_set.add(k)

    PROCEDURAL_WORDS = ["성원이 되었으므로", "개회하겠습", "개의하겠습", "개의를 선포", "의사일정", "선포합니다", "의석을 정돈", "보고해 주시기", " 개의하도록", "상정합니다", "의안번호", "개회를 선포"]

    for i in range(len(turns)):
        turn_q = turns[i]
        q_spk = turn_q["speaker"]
        
        # 질의자 자격 조건
        if q_spk in MODERATORS or q_spk in respondents_set or q_spk not in COMMISSION_MEMBERS:
            continue
            
        q_text = turn_q["text"]
        q_sents = [s.strip() for s in re.split(r'[.。!?]\s*', q_text) if s.strip()]
        valid_q_sents = [s for s in q_sents if len(s) >= 30 and not any(pw in s for pw in PROCEDURAL_WORDS)]
        
        if not valid_q_sents:
            continue
            
        # 답변자 검색 (i 뒤 5턴 이내)
        matched_a_turn = None
        for j in range(i + 1, min(i + 6, len(turns))):
            turn_a = turns[j]
            a_spk = turn_a["speaker"]
            
            if a_spk in respondents_set:
                a_text = turn_a["text"]
                a_sents = [s.strip() for s in re.split(r'[.。!?]\s*', a_text) if s.strip()]
                valid_a_sents = [s for s in a_sents if len(s) >= 30 and not any(pw in s for pw in PROCEDURAL_WORDS)]
                
                if valid_a_sents:
                    matched_a_turn = {
                        "speaker": a_spk,
                        "fact": summarize_answer(a_text)
                    }
                    break
                    
        if matched_a_turn:
            a_spk = matched_a_turn["speaker"]
            a_fact = matched_a_turn["fact"]
        else:
            a_spk = "정부 관계자"
            a_fact = "소관 현안에 대해 관계 부처에서 충분한 검토를 거쳐 신속히 조치하겠다고 언급함."
            
        q_fact = summarize_question(q_text)
        issue_name = top_kws[qa_count % len(top_kws)] if top_kws else "정합성 검토"
        if "관한법" in issue_name:
            issue_name = "현안질의"
            
        spk_title = speaker_titles.get(q_spk, "위원") if speaker_titles else "위원"
        if "위원" not in spk_title and q_spk in COMMISSION_MEMBERS:
            spk_title = "위원"
            
        qa_item = (
            f"▲ [{issue_name}]\n"
            f"- [질의 요지] {q_spk} {spk_title}(과방위) | {q_fact}\n"
            f"- | {a_spk} | {a_fact}"
        )
        qa_list.append(qa_item)
        qa_count += 1
        if qa_count >= 5:
            break

    # 4. 문서 최종 조립 (보고서 가이드 완벽 준수)
    report_lines = []
    report_lines.append(f"[{m_date}] {m_title}\n")
    
    if attendance_md:
        report_lines.append(attendance_md)
        
    report_lines.append("1. 총 평 (Executive Summary):")
    report_lines.append(f" ㅇ {convert_to_개조식(summary_sentence)}")
    for f in facts[:3]:
        report_lines.append(f" {f}")
    for r in ref_issues[:1]:
        report_lines.append(f" ※ {r}\n")
        
    report_lines.append("2. 주요 질의 및 답변 (Detailed Q&A):")
    for qa in qa_list:
        report_lines.append(f" {qa}\n")

    full_report = "\n".join(report_lines)
    # 볼드 처리 적용
    return apply_bold(full_report)


# 머릿글/바릿글 노이즈 패턴 정의 (예: 제434회-과학기술정보방송통신소위제3차(2026년4월22일) 11, - 11 - 등)
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
        if not is_noise:
            lines.append(line)
    return "\n".join(lines)


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
                        t = patch_page_text(filepath.name, page_num, t)
                        full_text += t + "\n"
                        page_texts.append((page_num, t))
                except Exception:
                    pass
    except Exception as e:
        result.update({"error": str(e), "text_length": 0,
                       "keywords": [], "speakers": [], "summary": "", "agendas": []})
        return result

    result["text_length"] = len(full_text)

    # 1. 발언자 추출 및 중복 병합
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

    # 2. 고유 안건 및 실효적 키워드 추출
    raw_agendas = extract_agendas(full_text)
    result["agendas"] = build_agenda_details(raw_agendas, full_text, result["date"])
    
    # 발언자 이름을 불용어로 동적 추가하여 키워드 탭에 의원명이 노출되는 것 방지
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

    # 3. 정합성 높은 회의록 제목 조립
    cleanTitle = re.sub(r'^제22대국회\s+과학기술정보방송통신위원회\s+회의록\s+', '', filepath.name.replace('.PDF','').replace('.pdf',''))
    cleanTitle = re.sub(r'^제22대국회\s+', '', cleanTitle)
    title_match = re.match(r'제(\d+)회\((.+?)\)\s+제(\d+)차\s+(.+)', cleanTitle)
    displayTitle = cleanTitle
    if title_match:
        displayTitle = f"제{title_match.group(1)}회({title_match.group(2)}) 제{title_match.group(3)}차 {title_match.group(4)}"

    # 4. CR 상황 보고서 요약 조립
    speaker_titles = get_speaker_titles(full_text, [info['name'] for info in merged.values()])
    
    # 요약용 상세 라인 리스트 구성 (idx, page 데이터 보존)
    text_only_speakers = {}
    for info in merged.values():
        text_only_speakers[info['name']] = info['lines']
        
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


def main():
    pdf_dir = Path(PDF_DIR)
    if not pdf_dir.exists():
        safe_print(f"오류: {PDF_DIR} 없음")
        sys.exit(1)

    all_pdfs = sorted([
        f for f in pdf_dir.iterdir()
        if f.suffix.lower() == '.pdf' and not is_duplicate(f.name)
    ], key=lambda p: p.stat().st_size)

    total = len(all_pdfs)
    safe_print(f"총 {total}개 파싱 시작 (v3 - 발언내용요약 + 이름정규화)")

    meetings, errors, done = [], [], 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_path = {executor.submit(parse_pdf, p): p for p in all_pdfs}
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            done += 1
            try:
                data = future.result()
                meetings.append(data)
                spk_names = [s['name'] for s in data.get('speakers', [])[:3]]
                kw_str = ", ".join(k["word"] for k in data.get("keywords", [])[:3])
                safe_print(f"[{done:3d}/{total}] {data.get('date','?')} | {', '.join(spk_names)} | {kw_str}")
            except Exception as e:
                safe_print(f"[{done:3d}/{total}] ERR {path.name[:40]}: {e}")
                errors.append({"file": path.name, "error": str(e)})

    meetings.sort(key=lambda x: (x.get("date") or "0000-00-00"))

    all_keywords = Counter()
    for m in meetings:
        for kw in m.get("keywords", []):
            all_keywords[kw["word"]] += kw["count"]

    db = {
        "generated_at": datetime.datetime.now().isoformat(),
        "total_count": len(meetings),
        "global_keywords": [{"word": w, "count": c} for w, c in all_keywords.most_common(100)],
        "meetings": meetings,
        "errors": errors,
    }

    output_path = Path(OUTPUT_PATH)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    size_kb = output_path.stat().st_size // 1024
    safe_print(f"\n완료! {len(meetings)}개 / 오류 {len(errors)}개 / {size_kb}KB")


if __name__ == "__main__":
    main()
