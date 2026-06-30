import os
import re
import time
import sys
from pathlib import Path

# Fix terminal encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load .env file manually if exists
env_path = os.path.join(os.path.dirname(BASE_DIR), ".env")
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

# Auto-install dependencies
try:
    import pdfplumber
except ImportError:
    os.system(f"{sys.executable} -m pip install pdfplumber -q")
    import pdfplumber

try:
    import fitz  # PyMuPDF
except ImportError:
    os.system(f"{sys.executable} -m pip install pymupdf -q")
    import fitz

try:
    from google import genai
except ImportError:
    os.system(f"{sys.executable} -m pip install google-genai -q")
    from google import genai

try:
    from telegram import Update
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
except ImportError:
    os.system(f"{sys.executable} -m pip install python-telegram-bot -q")
    from telegram import Update
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- [1. 설정 및 API 키] ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PDF_DIR = os.path.join(BASE_DIR, "pdf_22nd")

if not os.path.exists(PDF_DIR):
    os.makedirs(PDF_DIR)

client = genai.Client(api_key=GEMINI_API_KEY)

# --- [2. 데이터베이스 어댑터 (SQLite & PostgreSQL 듀얼 모드)] ---
class DatabaseAdapter:
    def __init__(self):
        self.db_url = os.environ.get("SUPABASE_DB_URL")
        self.is_postgres = bool(self.db_url)
        
        if self.is_postgres:
            import psycopg2
            # Strip query parameters like ?pgbouncer=true for psycopg2/libpq compatibility
            conn_url = self.db_url.split("?")[0] if "?" in self.db_url else self.db_url
            self.conn = psycopg2.connect(conn_url)
            self.p = "%s"  # Placeholder
            self.like_op = "ILIKE"
            self.meeting_table = "meetings"
            self.title_col = "filename"
        else:
            import sqlite3
            self.conn = sqlite3.connect(os.path.join(BASE_DIR, 'assembly_master.db'))
            self.p = "?"
            self.like_op = "LIKE"
            self.meeting_table = "meeting_info"
            self.title_col = "title"

    def cursor(self):
        return self.conn.cursor()

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

# --- [3. 영문 약어 단어 경계(\b) 매칭 유틸리티] ---
def match_keyword_py(text, kw):
    if not text or not kw:
        return False
    text = text.lower()
    kw = kw.lower()
    is_english_acronym = bool(re.match(r'^[a-z0-9_-]+$', kw))
    if is_english_acronym:
        escaped = re.escape(kw)
        pattern = rf"\b{escaped}\b"
        return bool(re.search(pattern, text))
    else:
        return kw in text

# --- [4. PDF 텍스트 추출 헬퍼] ---
def extract_text_safe(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:1000]:  # 최대 1000페이지
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"PDF 텍스트 추출 중 에러: {e}")
    return text

# --- [5. 텔레그램 메시지 핸들러] ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id=chat_id, text="과방위 회의록 정밀 검색 봇 (클라우드 DB 동기화 버전) 가동 중입니다.")

async def check_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db = DatabaseAdapter()
    c = db.cursor()
    
    c.execute(f"SELECT COUNT(*) FROM {db.meeting_table}")
    m_cnt = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM speeches")
    s_cnt = c.fetchone()[0]
    
    c.execute(f"SELECT date, {db.title_col} FROM {db.meeting_table} ORDER BY date DESC LIMIT 5")
    rows = c.fetchall()
    
    msg = f"📊 [클라우드 DB 상태] 현황: 회의록 {m_cnt}개, 분석 발언 {s_cnt}건\n\n[최근 회의록 데이터]\n"
    for d, t in rows:
        msg += f"📅 날짜: [{d}] | 제목: {t[:15]}...\n"
        
    await context.bot.send_message(chat_id=chat_id, text=msg)
    db.close()

async def get_speakers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db = DatabaseAdapter()
    c = db.cursor()
    c.execute("SELECT speaker_name, COUNT(*) as cnt FROM speeches GROUP BY speaker_name ORDER BY cnt DESC LIMIT 20")
    rows = c.fetchall()
    db.close()
    
    msg = "👤 **대시보드 상위 발언자 목록**\n\n"
    for name, cnt in rows:
        msg += f"- {name} ({cnt}건)\n"
    msg += "\n💡 위 이름을 참고해서 `이름` 또는 `이름 & 키워드`를 입력해 보세요!"
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')

async def search_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    keyword = " ".join(context.args)
    if not keyword:
        await context.bot.send_message(chat_id=chat_id, text="검색어를 입력하세요. (예: /search 전기통신사업법)")
        return
        
    db = DatabaseAdapter()
    c = db.cursor()
    c.execute(f"SELECT speaker_name, ai_summary, content FROM speeches WHERE content {db.like_op} {db.p} ORDER BY speech_id DESC", (f"%{keyword}%",))
    all_rows = c.fetchall()
    db.close()
    
    filtered_rows = []
    for speaker_name, ai_summary, content in all_rows:
        if match_keyword_py(content, keyword):
            filtered_rows.append((speaker_name, ai_summary or content[:100]))
            
    rows = filtered_rows[:5]
    if not rows:
        await context.bot.send_message(chat_id=chat_id, text=f"'{keyword}' 관련 발언을 찾을 수 없습니다.")
        return
        
    msg = f"🔍 **'{keyword}' 관련 최신 발언 요약 (최대 5건)**\n\n"
    for name, summary in rows:
        msg += f"👤 **{name}**: {summary}\n\n"
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')

async def get_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    
    if text.startswith('/'):
        if any(text.startswith(cmd) for cmd in ['/check', '/reparse', '/speakers', '/fixdb', '/addlocal', '/start', '/cleanup']):
            return
        text = re.sub(r'^/report\s*', '', text).lstrip('/') 

    raw_query = text.strip()
    if not raw_query: return

    is_all = raw_query.endswith("전체")
    query = raw_query[:-2].strip() if is_all else raw_query

    db = DatabaseAdapter()
    c = db.cursor()

    async def send_extracted_pdf(pdf_path, speeches_info, meeting_type, clean_date):
        if not pdf_path or not os.path.exists(pdf_path): return
        try:
            doc = fitz.open(pdf_path)
            target_pages = set()
            for speaker_name, content in speeches_info:
                clean_content_search = re.sub(r'\s+', '', content[:20]) 
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    page_text = re.sub(r'\s+', '', page.get_text())
                    if clean_content_search in page_text:
                        target_pages.add(page_num)
                        if page_num + 1 < len(doc): target_pages.add(page_num + 1)
                        name_instances = page.search_for(speaker_name)
                        for inst in name_instances:
                            annot = page.add_highlight_annot(inst)
                            annot.update()
                        break
                        
            short_date = f"{clean_date[2:4]}년{clean_date[5:7]}월{clean_date[8:10]}일" if len(clean_date) >= 10 else clean_date
            if not target_pages: 
                doc.close()
                await context.bot.send_document(
                    chat_id=chat_id, document=open(pdf_path, 'rb'), filename=f"{meeting_type}({short_date})_원본.pdf",
                    caption=f"📎 (텍스트 좌표 매칭에 실패하여 원본 파일을 전송합니다.)", read_timeout=120, write_timeout=120
                )
                return
                
            doc.select(sorted(list(target_pages)))
            temp_pdf_name = f"{meeting_type}({short_date})_발췌본.pdf"
            doc.save(temp_pdf_name)
            doc.close()
            
            await context.bot.send_document(
                chat_id=chat_id, document=open(temp_pdf_name, 'rb'), 
                caption=f"📎 해당 발언자 이름에 노란색 형광펜이 칠해진 문서입니다.", read_timeout=120, write_timeout=120
            )
            os.remove(temp_pdf_name)
        except Exception as e:
            print("PDF 분할/하이라이트 에러:", e)

    # 1️⃣ [이름 & AND/OR 다중 혼합 검색]
    if "&" in query:
        parts = [x.strip() for x in query.split("&")]
        speaker = parts[0]
        keyword_groups = parts[1:]
        
        where_clauses = ["s.speaker_name LIKE %s" if db.is_postgres else "s.speaker_name LIKE ?"]
        params = [f"%{speaker}%"]
        
        for group in keyword_groups:
            or_kws = [k.strip() for k in group.split(",") if k.strip()]
            if or_kws:
                placeholder_clause = f"s.content {db.like_op} {db.p}"
                clause = "(" + " OR ".join([placeholder_clause] * len(or_kws)) + ")"
                where_clauses.append(clause)
                params.extend([f"%{k}%" for k in or_kws])
                
        where_str = " AND ".join(where_clauses)
        
        c.execute(f"""
            SELECT m.{db.title_col}, m.date, {"m.pdf_path" if not db.is_postgres else "m.filename as pdf_path"}, s.content 
            FROM speeches s 
            JOIN {db.meeting_table} m ON s.meeting_id = m.meeting_id 
            WHERE {where_str}
            ORDER BY m.date DESC, s.speech_id ASC
        """, params)
        all_rows = c.fetchall()
        
        # Filter in Python
        filtered_rows = []
        for row in all_rows:
            title, date, pdf, content = row
            match_all = True
            for group in keyword_groups:
                or_kws = [k.strip() for k in group.split(",") if k.strip()]
                if not any(match_keyword_py(content, kw) for kw in or_kws):
                    match_all = False
                    break
            if match_all:
                pdf_path = pdf if not db.is_postgres else os.path.join(PDF_DIR, pdf)
                filtered_rows.append((title, date, pdf_path, content))
                
        rows = filtered_rows if is_all else filtered_rows[:5]
        keyword_str = " & ".join(keyword_groups)
        
        if not rows:
            await context.bot.send_message(chat_id=chat_id, text=f"'{speaker}'의 '{keyword_str}' 관련 발언 기록을 찾을 수 없습니다.")
            db.close()
            return

        if is_all:
            await context.bot.send_message(chat_id=chat_id, text=f"📥 '{speaker}'의 전체 검색 결과({len(rows)}건)를 파일로 정리 중입니다...")
            txt_content = f"[{speaker} '{keyword_str}' 관련 전체 발언 원문]\n" + "=" * 50 + "\n\n"
            for title, date, pdf, content in rows:
                txt_content += f"■ [{date}] {title}\n - {content.strip()}\n\n"
            filename = f"{speaker}_혼합검색_전체발언.txt"
            with open(filename, 'w', encoding='utf-8') as f: f.write(txt_content)
            await context.bot.send_document(chat_id=chat_id, document=open(filename, 'rb'), caption=f"📄 전체 발언입니다.", read_timeout=120, write_timeout=120)
            os.remove(filename)
            db.close()
            return
            
        await context.bot.send_message(chat_id=chat_id, text=f"🔍 '{speaker}'의 '{keyword_str}' 관련 발언을 정밀 요약 중입니다...")
        
        meetings_dict = {}
        for title, date, pdf_path, content in rows:
            clean_date = date
            try: parts = date.split('-'); clean_date = f"{parts[0]}-{int(parts[1])}-{int(parts[2])}"
            except: pass
            meeting_type = "전체회의"
            sub_match = re.search(r'([가-힣]+소위원회)', title)
            if sub_match: meeting_type = sub_match.group(1)
            meeting_header = f"[{meeting_type}({clean_date})]"
            
            if meeting_header not in meetings_dict: 
                meetings_dict[meeting_header] = {"speeches": [], "pdf_paths": set(), "meeting_type": meeting_type, "clean_date": clean_date}
            meetings_dict[meeting_header]["speeches"].append((speaker, content))
            if pdf_path and os.path.exists(pdf_path):
                meetings_dict[meeting_header]["pdf_paths"].add(pdf_path)
            
        res = f"[{speaker} '{keyword_str}' 관련 발언 리포트]\n\n"
        for meeting_header, data in meetings_dict.items():
            res += f"{meeting_header}\n"
            for idx, (spk, content) in enumerate(data["speeches"], 1):
                clean_content = re.sub(r'^(위원|위원장|의원|소위원장|장관|차관|증인|참고인|진술인|후보자|실장|국장|과장|본부장|직무대행|정부위원)\s*', '', content.strip()).strip()
                prompt = f"다음 회의록 발언을 마크다운 기호 없이 '{keyword_str}' 맥락을 중심으로 3~5문장 요약해 주세요(과거형 종결어미 사용):\n{clean_content}"
                try: summary = (await client.aio.models.generate_content(model='gemini-2.5-pro', contents=prompt)).text.replace("*", "").strip()
                except: summary = "AI 요약 중 오류 발생"
                res += f" {idx}. {summary}\n"
            res += "\n"
        await context.bot.send_message(chat_id=chat_id, text=res.strip())
        
        for meeting_header, data in meetings_dict.items():
            if data["pdf_paths"]:
                await send_extracted_pdf(list(data["pdf_paths"])[0], data["speeches"], data["meeting_type"], data["clean_date"])
        db.close()
        return

    # 4️⃣ [의안 및 키워드 나열 검색 (OR 검색)]
    else:
        or_kws = [k.strip() for k in query.split(",") if k.strip()]
        if not or_kws: return
        
        guide_msg = ""
        if len(or_kws) > 1 and re.match(r"^[가-힣]{2,4}$", or_kws[0]):
            guide_msg = (
                f"💡 [스마트 검색 팁]\n혹시 '{or_kws[0]}' 의원의 발언을 찾으시나요?\n"
                f"👉 추천 검색어: {or_kws[0]} & {', '.join(or_kws[1:])}\n--------------------------------------------------\n\n"
            )

        placeholder_clause = f"s.content {db.like_op} {db.p}"
        where_str = " OR ".join([placeholder_clause] * len(or_kws))
        params = [f"%{k}%" for k in or_kws]
        
        c.execute(f"""
            SELECT m.date, m.{db.title_col}, {"m.pdf_path" if not db.is_postgres else "m.filename as pdf_path"}, s.speaker_name, s.content 
            FROM speeches s 
            JOIN {db.meeting_table} m ON s.meeting_id = m.meeting_id 
            WHERE {where_str}
            ORDER BY m.date DESC
        """, params)
        all_rows = c.fetchall()
        
        # Filter in Python
        filtered_rows = []
        for row in all_rows:
            date, title, pdf, speaker_name, content = row
            if any(match_keyword_py(content, k) for k in or_kws):
                pdf_path = pdf if not db.is_postgres else os.path.join(PDF_DIR, pdf)
                filtered_rows.append((date, title, pdf_path, speaker_name, content))
                
        rows = filtered_rows if is_all else filtered_rows[:15]
        keyword_str = ", ".join(or_kws)
        
        if not rows:
            await context.bot.send_message(chat_id=chat_id, text=guide_msg + f"'{keyword_str}' 관련 논의 기록을 찾을 수 없습니다.")
            db.close()
            return
            
        if is_all:
            await context.bot.send_message(chat_id=chat_id, text=f"📥 '{keyword_str}' 관련 전체 논의 기록({len(rows)}건)을 원문 파일로 정리 중입니다...")
            txt_content = guide_msg + f"🔍 ['{keyword_str}' 논의 히스토리 전체 원문]\n" + "=" * 50 + "\n\n"
            for date, title, pdf_path, speaker, content in rows:
                txt_content += f"■ [{date}] {title}\n [{speaker}] {content.strip()}\n\n"
            filename = f"키워드검색_논의히스토리_전체.txt"
            with open(filename, 'w', encoding='utf-8') as f: f.write(txt_content)
            await context.bot.send_document(chat_id=chat_id, document=open(filename, 'rb'), caption=f"📄 '{keyword_str}' 전체 기록", read_timeout=120, write_timeout=120)
            os.remove(filename)
            db.close()
            return
            
        await context.bot.send_message(chat_id=chat_id, text=guide_msg + f"🔍 '{keyword_str}' 관련 발언을 정밀 요약 중입니다...")
        
        history = {}
        for date, title, pdf_path, speaker, content in rows:
            clean_date = date
            try: parts = date.split('-'); clean_date = f"{parts[0]}-{int(parts[1])}-{int(parts[2])}"
            except: pass
            meeting_type = "전체회의"
            sub_match = re.search(r'([가-힣]+소위원회)', title)
            if sub_match: meeting_type = sub_match.group(1)
            meeting_header = f"[{meeting_type}({clean_date})]"
            
            key = (meeting_header, meeting_type, clean_date, pdf_path)
            if key not in history: history[key] = []
            history[key].append((speaker, content))
            
        res = f"['{keyword_str}' 논의 히스토리]\n\n"
        for (meeting_header, meeting_type, clean_date, pdf_path), speeches in history.items():
            res += f"{meeting_header}\n"
            for idx, (speaker, content) in enumerate(speeches[:5], 1):
                clean_content = re.sub(r'^(위원|위원장|의원|소위원장|장관|차관|증인|참고인|진술인|후보자|실장|국장|과장|본부장|직무대행|정부위원)\s*', '', content.strip()).strip()
                prompt = f"다음 회의록 발언을 '{keyword_str}' 맥락을 중심으로 3~5문장 요약해 주세요(과거형 종결어미 사용):\n{clean_content}"
                try: summary = (await client.aio.models.generate_content(model='gemini-2.5-pro', contents=prompt)).text.replace("*", "").strip()
                except: summary = "AI 요약 중 오류 발생"
                res += f" {idx}. [{speaker}] {summary}\n"
            res += "\n"
        await context.bot.send_message(chat_id=chat_id, text=res.replace("*", ""))
        
        for (meeting_header, meeting_type, clean_date, pdf_path), speeches in history.items():
            if pdf_path and os.path.exists(pdf_path):
                await send_extracted_pdf(pdf_path, speeches, meeting_type, clean_date)
        db.close()

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).read_timeout(60).write_timeout(60).connect_timeout(60).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_db))
    app.add_handler(CommandHandler("speakers", get_speakers))
    app.add_handler(CommandHandler("search", search_keyword))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_report))
    
    print("🚀 Supabase 연동형 텔레그램 봇 가동 시작...")
    app.run_polling()

if __name__ == '__main__':
    main()
