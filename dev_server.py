import os
import json
import re
import urllib.parse
import datetime
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

# Fix terminal encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

PORT = 3000
LOCAL_JSON_PATH = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\data\meetings.json"

# Load .env file manually if exists
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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

DB_URL = os.environ.get("SUPABASE_DB_URL")
HAS_POSTGRES = False
CONN_URL = ""

if DB_URL:
    try:
        import psycopg2
        # Clean query parameters for psycopg2/libpq compatibility
        CONN_URL = DB_URL.split("?")[0] if "?" in DB_URL else DB_URL
        # Try a quick dry connection to confirm availability
        conn = psycopg2.connect(CONN_URL, connect_timeout=3)
        conn.close()
        HAS_POSTGRES = True
        print("[dev_server.py] Successfully connected to Supabase PostgreSQL Database!")
    except Exception as e:
        print(f"[dev_server.py] PostgreSQL DB URL detected but connection failed: {e}")
        print("FALLING BACK TO LOCAL JSON MODE.")

# --- [Word boundary matching logic matching JS] ---
def match_keyword_py(text, kw):
    if not text or not kw: return False
    text = text.lower()
    kw = kw.lower()
    is_english = bool(re.match(r'^[a-z0-9_-]+$', kw))
    if is_english:
        return bool(re.search(rf"\b{re.escape(kw)}\b", text))
    return kw in text

def sanitize_text(txt):
    if not txt: return ''
    cleaned = re.sub(r'\d+\s+제\d+회\s*-\s*[가-힣\s\(\)]+?\(\d{4}년\s*\d{1,2}월\s*\d{1,2}일\)', '', txt)
    cleaned = re.sub(r'^\d+\s+제\d+회-.*?$', '', cleaned, flags=re.MULTILINE)
    return cleaned.strip()

def get_speaker_merged_turns_py(lines, speaker_name):
    if not lines: return []
    merged = []
    current = None
    
    for idx, line in enumerate(lines):
        # line can be a dict (JSON fallback) or a tuple (PostgreSQL)
        if isinstance(line, dict):
            content = line.get("text", "")
            page = line.get("page", 1)
        else:
            content = line[0]
            page = line[1]
            
        cleaned_text = sanitize_text(content)
        if not cleaned_text: continue
        
        if not current:
            current = {
                "name": speaker_name,
                "text": cleaned_text,
                "page": page,
                "lineIdxs": [idx]
            }
        else:
            last_idx = current["lineIdxs"][-1]
            if idx == last_idx + 1 and page == current["page"]:
                current["text"] += " " + cleaned_text
                current["lineIdxs"].append(idx)
            else:
                merged.append(current)
                current = {
                    "name": speaker_name,
                    "text": cleaned_text,
                    "page": page,
                    "lineIdxs": [idx]
                }
    if current:
        merged.append(current)
    return merged

def merge_db_rows_to_turns(rows):
    # Group by meeting and speaker
    groups = {}
    for r in rows:
        # r: (filename, date, summary, session_num, session_type, order_num, meeting_type, year, speaker_name, content, page)
        key = f"{r[0]}||{r[8]}"
        if key not in groups:
            groups[key] = {
                "filename": r[0],
                "date": r[1],
                "summary": r[2],
                "session_num": r[3],
                "session_type": r[4],
                "order_num": r[5],
                "meeting_type": r[6],
                "year": r[7],
                "speaker_name": r[8],
                "lines": []
            }
        groups[key]["lines"].append((r[9], r[10])) # (content, page)

    turn_matches = []
    for key, g in groups.items():
        turns = get_speaker_merged_turns_py(g["lines"], g["speaker_name"])
        for turn in turns:
            turn_matches.append({
                "filename": g["filename"],
                "date": g["date"],
                "summary": g["summary"],
                "session_num": g["session_num"],
                "session_type": g["session_type"],
                "order_num": g["order_num"],
                "meeting_type": g["meeting_type"],
                "year": g["year"],
                "speaker": turn["name"],
                "content": turn["text"],
                "page": turn["page"]
            })
    return turn_matches

class SystemCDevServer(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        pathname = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # Route to root mapping
        if pathname == '/':
            pathname = '/index.html'

        # API routing
        if pathname.startswith('/api/'):
            self.handle_api(pathname, query)
        else:
            self.handle_static(pathname)

    def handle_static(self, pathname):
        clean_path = pathname.lstrip('/')
        file_path = os.path.join(os.getcwd(), clean_path)

        if os.path.exists(file_path) and os.path.isfile(file_path):
            content_type = 'text/html; charset=utf-8'
            if file_path.endswith('.js'):
                content_type = 'application/javascript; charset=utf-8'
            elif file_path.endswith('.css'):
                content_type = 'text/css; charset=utf-8'
            elif file_path.endswith('.json'):
                content_type = 'application/json; charset=utf-8'

            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.end_headers()
            with open(file_path, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b"Static File Not Found")

    def handle_api(self, pathname, query):
        try:
            self._handle_api_impl(pathname, query)
        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                encoded_err = json.dumps({"success": False, "error": str(e)}, ensure_ascii=False).encode('utf-8')
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(encoded_err)))
                self.end_headers()
                self.wfile.write(encoded_err)
            except Exception:
                pass

    def _handle_api_impl(self, pathname, query):
        api_name = pathname[5:] # e.g. "meetings" or "search"
        response_data = {}

        if HAS_POSTGRES:
            import psycopg2
            conn = psycopg2.connect(CONN_URL)
            try:
                if api_name == 'meetings':
                    filename = query.get('filename', [''])[0]
                    if filename:
                        # Fetch specific meeting details
                        with conn.cursor() as cur:
                            cur.execute("""
                                SELECT meeting_id, filename, date, session_num, session_type, order_num, meeting_type, year, text_length, summary
                                FROM meetings
                                WHERE filename = %s;
                            """, (filename,))
                            m_row = cur.fetchone()
                            if not m_row:
                                response_data = {"success": False, "message": "Meeting not found"}
                            else:
                                meeting_id = m_row[0]
                                
                                # Fetch agendas
                                cur.execute("SELECT title, proposer, proposal_date, summary, link FROM agendas WHERE meeting_id = %s ORDER BY agenda_id ASC;", (meeting_id,))
                                agendas = [{"title": r[0], "proposer": r[1], "proposal_date": r[2], "summary": r[3], "link": r[4]} for r in cur.fetchall()]
                                
                                # Fetch speeches
                                cur.execute("SELECT speaker_name, content, page, speech_count FROM speeches WHERE meeting_id = %s ORDER BY speech_id ASC;", (meeting_id,))
                                speeches = cur.fetchall()
                                
                                # Fetch keywords
                                cur.execute("SELECT speaker_name, word, count FROM keywords WHERE meeting_id = %s ORDER BY count DESC;", (meeting_id,))
                                keywords = cur.fetchall()
                                
                                # Group speeches
                                speakers_map = {}
                                for s_row in speeches:
                                    name = s_row[0]
                                    if name not in speakers_map:
                                        speakers_map[name] = {
                                            "name": name,
                                            "speech_count": s_row[3],
                                            "lines": [],
                                            "keywords": []
                                        }
                                    speakers_map[name]["lines"].append({
                                        "text": s_row[1],
                                        "page": s_row[2]
                                    })
                                    
                                meeting_keywords = []
                                for k_row in keywords:
                                    spk_name = k_row[0]
                                    word = k_row[1]
                                    count = k_row[2]
                                    if spk_name is None:
                                        meeting_keywords.append({"word": word, "count": count})
                                    elif spk_name in speakers_map:
                                        speakers_map[spk_name]["keywords"].append({"word": word, "count": count})
                                        
                                response_data = {
                                    "success": True,
                                    "meeting": {
                                        "filename": m_row[1],
                                        "date": m_row[2],
                                        "session_num": m_row[3],
                                        "session_type": m_row[4],
                                        "order_num": m_row[5],
                                        "meeting_type": m_row[6],
                                        "year": m_row[7],
                                        "text_length": m_row[8],
                                        "summary": m_row[9],
                                        "agendas": agendas,
                                        "speakers": list(speakers_map.values()),
                                        "keywords": meeting_keywords
                                    }
                                }
                    else:
                        # Fetch list
                        limit = int(query.get('limit', [1000])[0])
                        offset = int(query.get('offset', [0])[0])
                        sort_by = query.get('sortBy', ['date'])[0]
                        sort_order = query.get('sortOrder', ['desc'])[0]
                        
                        order_clause = 'm.date DESC'
                        if sort_by == 'session':
                            order_clause = f"m.session_num {sort_order}, m.order_num {sort_order}"
                        elif sort_by == 'speakers':
                            order_clause = f"speaker_count {sort_order}"
                        else:
                            order_clause = f"m.date {sort_order}"
                            
                        with conn.cursor() as cur:
                            cur.execute(f"""
                                SELECT m.meeting_id, m.filename, m.date, m.session_num, m.session_type, m.order_num, m.meeting_type, m.year, m.text_length, m.summary,
                                       (SELECT COUNT(DISTINCT s.speaker_name) FROM speeches s WHERE s.meeting_id = m.meeting_id) as speaker_count,
                                       (SELECT COUNT(*) FROM agendas a WHERE a.meeting_id = m.meeting_id) as agenda_count
                                FROM meetings m
                                ORDER BY {order_clause}
                                LIMIT %s OFFSET %s;
                            """, (limit, offset))
                            meetings_rows = cur.fetchall()
                            meeting_ids = [r[0] for r in meetings_rows]
                            
                            cur.execute("SELECT COUNT(*) FROM meetings;")
                            total_count = cur.fetchone()[0]
                            
                            cur.execute("""
                                SELECT word, SUM(count) as total_count
                                FROM keywords
                                WHERE speaker_name IS NULL
                                GROUP BY word
                                ORDER BY total_count DESC
                                LIMIT 100;
                            """)
                            global_keywords = [{"word": r[0], "count": int(r[1])} for r in cur.fetchall()]
                            
                            agendas_map = {}
                            keywords_map = {}
                            speakers_map = {}
                            
                            if meeting_ids:
                                cur.execute("""
                                    SELECT meeting_id, title
                                    FROM agendas
                                    WHERE meeting_id = ANY(%s)
                                    ORDER BY agenda_id ASC;
                                """, (meeting_ids,))
                                for a_row in cur.fetchall():
                                    if a_row[0] not in agendas_map: agendas_map[a_row[0]] = []
                                    agendas_map[a_row[0]].append(a_row[1])
                                    
                                cur.execute("""
                                    SELECT meeting_id, word, count
                                    FROM keywords
                                    WHERE meeting_id = ANY(%s) AND speaker_name IS NULL
                                    ORDER BY count DESC;
                                """, (meeting_ids,))
                                for k_row in cur.fetchall():
                                    if k_row[0] not in keywords_map: keywords_map[k_row[0]] = []
                                    if len(keywords_map[k_row[0]]) < 10:
                                        keywords_map[k_row[0]].append({"word": k_row[1], "count": k_row[2]})
                                        
                                cur.execute("""
                                    SELECT s.meeting_id, s.speaker_name, COUNT(*) as cnt
                                    FROM speeches s
                                    WHERE s.meeting_id = ANY(%s)
                                    GROUP BY s.meeting_id, s.speaker_name
                                    ORDER BY cnt DESC;
                                """, (meeting_ids,))
                                for s_row in cur.fetchall():
                                    if s_row[0] not in speakers_map: speakers_map[s_row[0]] = []
                                    speakers_map[s_row[0]].append({"name": s_row[1], "speech_count": s_row[2]})
                                    
                            meetings = []
                            for r in meetings_rows:
                                m_id = r[0]
                                meetings.append({
                                    "filename": r[1],
                                    "date": r[2],
                                    "session_num": r[3],
                                    "session_type": r[4],
                                    "order_num": r[5],
                                    "meeting_type": r[6],
                                    "year": r[7],
                                    "text_length": r[8],
                                    "summary": r[9],
                                    "speaker_count": r[10],
                                    "agenda_count": r[11],
                                    "agendas": agendas_map.get(m_id, []),
                                    "keywords": keywords_map.get(m_id, []),
                                    "speakers": speakers_map.get(m_id, [])
                                })
                                
                            response_data = {
                                "success": True,
                                "total_count": total_count,
                                "generated_at": datetime.datetime.now().isoformat(),
                                "global_keywords": global_keywords,
                                "meetings": meetings
                            }

                elif api_name == 'search':
                    q_param = query.get('q', [''])[0]
                    speaker_param = query.get('speaker', [''])[0]
                    matched_meetings = []
                    
                    with conn.cursor() as cur:
                        if speaker_param.strip():
                            cur.execute("""
                                SELECT m.filename, m.date, m.summary, m.session_num, m.session_type, m.order_num, m.meeting_type, m.year,
                                       s.speaker_name, s.content, s.page
                                FROM speeches s
                                JOIN meetings m ON s.meeting_id = m.meeting_id
                                WHERE s.speaker_name ILIKE %s
                                ORDER BY m.meeting_id ASC, s.speaker_name ASC, s.page ASC, s.speech_id ASC;
                            """, (f"%{speaker_param.strip()}%",))
                            all_turns = merge_db_rows_to_turns(cur.fetchall())
                            
                            meetings_map = {}
                            for turn in all_turns:
                                key = turn["filename"]
                                if key not in meetings_map:
                                    meetings_map[key] = {
                                        "filename": turn["filename"],
                                        "date": turn["date"],
                                        "summary": turn["summary"],
                                        "session_num": turn["session_num"],
                                        "session_type": turn["session_type"],
                                        "order_num": turn["order_num"],
                                        "meeting_type": turn["meeting_type"],
                                        "year": turn["year"],
                                        "matched_speeches": []
                                    }
                                meetings_map[key]["matched_speeches"].append({
                                    "speaker": turn["speaker"],
                                    "content": turn["content"],
                                    "page": turn["page"]
                                })
                            matched_meetings = list(meetings_map.values())
                            
                        elif q_param.strip():
                            if '&' in q_param:
                                parts = [p.strip() for p in q_param.split('&')]
                                speaker = parts[0]
                                keyword_groups = parts[1:]
                                
                                or_kws = []
                                for g in keyword_groups:
                                    or_kws.extend([k.strip() for k in g.split(',') if k.strip()])
                                    
                                like_clauses = " OR ".join(["s2.content ILIKE %s"] * len(or_kws))
                                params = [f"%{speaker}%"] + [f"%{k}%" for k in or_kws]
                                
                                cur.execute(f"""
                                    SELECT m.filename, m.date, m.summary, m.session_num, m.session_type, m.order_num, m.meeting_type, m.year,
                                           s.speaker_name, s.content, s.page
                                    FROM speeches s
                                    JOIN meetings m ON s.meeting_id = m.meeting_id
                                    WHERE (s.meeting_id, s.speaker_name, s.page) IN (
                                        SELECT DISTINCT s2.meeting_id, s2.speaker_name, s2.page
                                        FROM speeches s2
                                        WHERE s2.speaker_name ILIKE %s AND ({like_clauses})
                                    )
                                    ORDER BY m.meeting_id ASC, s.speaker_name ASC, s.page ASC, s.speech_id ASC;
                                """, params)
                                all_turns = merge_db_rows_to_turns(cur.fetchall())
                                
                                # Filter turns for AND matching and word boundary in python
                                meetings_map = {}
                                for turn in all_turns:
                                    match_all = True
                                    for group in keyword_groups:
                                        kws = [k.strip() for k in group.split(',') if k.strip()]
                                        if not any(match_keyword_py(turn["content"], kw) for kw in kws):
                                            match_all = False
                                            break
                                    if match_all:
                                        key = turn["filename"]
                                        if key not in meetings_map:
                                            meetings_map[key] = {
                                                "filename": turn["filename"],
                                                "date": turn["date"],
                                                "summary": turn["summary"],
                                                "session_num": turn["session_num"],
                                                "session_type": turn["session_type"],
                                                "order_num": turn["order_num"],
                                                "meeting_type": turn["meeting_type"],
                                                "year": turn["year"],
                                                "matched_speeches": []
                                            }
                                        meetings_map[key]["matched_speeches"].append({
                                            "speaker": turn["speaker"],
                                            "content": turn["content"],
                                            "page": turn["page"]
                                        })
                                matched_meetings = list(meetings_map.values())
                            else:
                                or_kws = [k.strip() for k in q_param.split(',') if k.strip()]
                                like_clauses = " OR ".join(["s2.content ILIKE %s"] * len(or_kws))
                                params = [f"%{k}%" for k in or_kws]
                                
                                cur.execute(f"""
                                    SELECT m.filename, m.date, m.summary, m.session_num, m.session_type, m.order_num, m.meeting_type, m.year,
                                           s.speaker_name, s.content, s.page
                                    FROM speeches s
                                    JOIN meetings m ON s.meeting_id = m.meeting_id
                                    WHERE (s.meeting_id, s.speaker_name, s.page) IN (
                                        SELECT DISTINCT s2.meeting_id, s2.speaker_name, s2.page
                                        FROM speeches s2
                                        WHERE {like_clauses}
                                    )
                                    ORDER BY m.meeting_id ASC, s.speaker_name ASC, s.page ASC, s.speech_id ASC;
                                """, params)
                                all_turns = merge_db_rows_to_turns(cur.fetchall())
                                
                                meetings_map = {}
                                for turn in all_turns:
                                    if any(match_keyword_py(turn["content"], kw) for kw in or_kws):
                                        key = turn["filename"]
                                        if key not in meetings_map:
                                            meetings_map[key] = {
                                                "filename": turn["filename"],
                                                "date": turn["date"],
                                                "summary": turn["summary"],
                                                "session_num": turn["session_num"],
                                                "session_type": turn["session_type"],
                                                "order_num": turn["order_num"],
                                                "meeting_type": turn["meeting_type"],
                                                "year": turn["year"],
                                                "matched_speeches": []
                                            }
                                        meetings_map[key]["matched_speeches"].append({
                                            "speaker": turn["speaker"],
                                            "content": turn["content"],
                                            "page": turn["page"]
                                        })
                                matched_meetings = list(meetings_map.values())
                                
                    response_data = {"success": True, "matched_meetings": matched_meetings}

                elif api_name == 'speakers':
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT speaker_name, COUNT(*) as speech_cnt
                            FROM speeches
                            GROUP BY speaker_name
                            ORDER BY speech_cnt DESC;
                        """)
                        speakers_rows = cur.fetchall()
                        
                        cur.execute("""
                            SELECT speaker_name, word, count
                            FROM keywords
                            WHERE speaker_name IS NOT NULL
                            ORDER BY speaker_name, count DESC;
                        """)
                        keywords_rows = cur.fetchall()
                        
                        keywords_map = {}
                        for k_row in keywords_rows:
                            spk = k_row[0]
                            if spk not in keywords_map: keywords_map[spk] = []
                            if len(keywords_map[spk]) < 10:
                                keywords_map[spk].append({"word": k_row[1], "count": k_row[2]})
                                
                        speakers = []
                        for s_row in speakers_rows:
                            speakers.append({
                                "name": s_row[0],
                                "speech_count": s_row[1],
                                "keywords": keywords_map.get(s_row[0], [])
                            })
                        response_data = {"success": True, "speakers": speakers}

                elif api_name == 'calendar':
                    with conn.cursor() as cur:
                        cur.execute("SELECT date, filename, meeting_type FROM meetings;")
                        events = [{"date": r[0], "title": r[1], "meeting_type": r[2]} for r in cur.fetchall()]
                        response_data = {"success": True, "events": events}

            finally:
                conn.close()

        else:
            # ============================================================
            # Local JSON Fallback Mode (Fallback when SUPABASE_DB_URL not set)
            # ============================================================
            if not os.path.exists(LOCAL_JSON_PATH):
                encoded_err = json.dumps({"success": False, "message": "meetings.json not found"}).encode('utf-8')
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(encoded_err)))
                self.end_headers()
                self.wfile.write(encoded_err)
                return

            with open(LOCAL_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if api_name == 'meetings':
                filename = query.get('filename', [''])[0]
                if filename:
                    meeting = next((m for m in data.get("meetings", []) if m.get("filename") == filename), None)
                    if meeting:
                        response_data = {"success": True, "meeting": meeting}
                    else:
                        response_data = {"success": False, "message": "Meeting not found"}
                else:
                    limit = int(query.get('limit', [1000])[0])
                    offset = int(query.get('offset', [0])[0])
                    sort_by = query.get('sortBy', ['date'])[0]
                    sort_order = query.get('sortOrder', ['desc'])[0]

                    meetings = []
                    for m in data.get("meetings", []):
                        meetings.append({
                            "filename": m.get("filename"),
                            "date": m.get("date"),
                            "session_num": m.get("session_num"),
                            "session_type": m.get("session_type"),
                            "order_num": m.get("order_num"),
                            "meeting_type": m.get("meeting_type"),
                            "year": m.get("year"),
                            "text_length": m.get("text_length"),
                            "summary": m.get("summary"),
                            "speaker_count": len(m.get("speakers", [])),
                            "agenda_count": len(m.get("agendas", [])),
                            "agendas": m.get("agendas", []),
                            "keywords": m.get("keywords", []),
                            "speakers": [{"name": s.get("name"), "speech_count": s.get("speech_count")} for s in m.get("speakers", [])]
                        })

                    reverse = (sort_order == 'desc')
                    if sort_by == 'session':
                        meetings.sort(key=lambda x: (x.get("session_num") or 0, x.get("order_num") or 0), reverse=reverse)
                    elif sort_by == 'speakers':
                        meetings.sort(key=lambda x: x.get("speaker_count") or 0, reverse=reverse)
                    else:
                        meetings.sort(key=lambda x: x.get("date") or '', reverse=reverse)

                    sliced = meetings[offset:offset+limit]
                    response_data = {
                        "success": True,
                        "total_count": len(meetings),
                        "generated_at": data.get("generated_at"),
                        "global_keywords": data.get("global_keywords", []),
                        "meetings": sliced
                    }

            elif api_name == 'search':
                q_param = query.get('q', [''])[0]
                speaker_param = query.get('speaker', [''])[0]
                matched_meetings = []

                if speaker_param.strip():
                    clean_speaker = speaker_param.strip().lower()
                    for m in data.get("meetings", []):
                        matched_speeches = []
                        for spk in m.get("speakers", []):
                            if clean_speaker in spk.get("name", "").lower():
                                turns = get_speaker_merged_turns_py(spk.get("lines", []), spk.get("name"))
                                for turn in turns:
                                    matched_speeches.append({
                                        "speaker": turn["name"],
                                        "content": turn["text"],
                                        "page": turn["page"]
                                    })
                        if matched_speeches:
                            matched_meetings.append({
                                "filename": m.get("filename"),
                                "date": m.get("date"),
                                "summary": m.get("summary"),
                                "session_num": m.get("session_num"),
                                "session_type": m.get("session_type"),
                                "order_num": m.get("order_num"),
                                "meeting_type": m.get("meeting_type"),
                                "year": m.get("year"),
                                "matched_speeches": matched_speeches
                            })
                elif q_param.strip():
                    if '&' in q_param:
                        parts = [p.strip() for p in q_param.split('&')]
                        speaker = parts[0]
                        keyword_groups = parts[1:]

                        for m in data.get("meetings", []):
                            matched_speeches = []
                            for spk in m.get("speakers", []):
                                if speaker.lower() in spk.get("name", "").lower():
                                    turns = get_speaker_merged_turns_py(spk.get("lines", []), spk.get("name"))
                                    for turn in turns:
                                        match_all = True
                                        for group in keyword_groups:
                                            or_kws = [k.strip() for k in group.split(',') if k.strip()]
                                            if not any(match_keyword_py(turn["text"], kw) for kw in or_kws):
                                                match_all = False
                                                break
                                        if match_all:
                                            matched_speeches.append({
                                                "speaker": turn["name"],
                                                "content": turn["text"],
                                                "page": turn["page"]
                                            })
                            if matched_speeches:
                                matched_meetings.append({
                                    "filename": m.get("filename"),
                                    "date": m.get("date"),
                                    "summary": m.get("summary"),
                                    "session_num": m.get("session_num"),
                                    "session_type": m.get("session_type"),
                                    "order_num": m.get("order_num"),
                                    "meeting_type": m.get("meeting_type"),
                                    "year": m.get("year"),
                                    "matched_speeches": matched_speeches
                                })
                    else:
                        or_kws = [k.strip() for k in q_param.split(',') if k.strip()]
                        for m in data.get("meetings", []):
                            matched_speeches = []
                            for spk in m.get("speakers", []):
                                turns = get_speaker_merged_turns_py(spk.get("lines", []), spk.get("name"))
                                for turn in turns:
                                    if any(match_keyword_py(turn["text"], kw) for kw in or_kws):
                                        matched_speeches.append({
                                            "speaker": turn["name"],
                                            "content": turn["text"],
                                            "page": turn["page"]
                                        })
                            if matched_speeches:
                                matched_meetings.append({
                                    "filename": m.get("filename"),
                                    "date": m.get("date"),
                                    "summary": m.get("summary"),
                                    "session_num": m.get("session_num"),
                                    "session_type": m.get("session_type"),
                                    "order_num": m.get("order_num"),
                                    "meeting_type": m.get("meeting_type"),
                                    "year": m.get("year"),
                                    "matched_speeches": matched_speeches
                                })

                response_data = {"success": True, "matched_meetings": matched_meetings}

            elif api_name == 'speakers':
                speakers_map = {}
                for m in data.get("meetings", []):
                    for spk in m.get("speakers", []):
                        name = spk.get("name")
                        if name not in speakers_map:
                            speakers_map[name] = {"name": name, "speech_count": 0, "keywords_counts": {}}
                        speakers_map[name]["speech_count"] += spk.get("speech_count", 0)
                        for kw in spk.get("keywords", []):
                            speakers_map[name]["keywords_counts"][kw.get("word")] = speakers_map[name]["keywords_counts"].get(kw.get("word"), 0) + kw.get("count", 0)

                speakers = []
                for spk in speakers_map.values():
                    kws = [{"word": k, "count": c} for k, c in spk["keywords_counts"].items()]
                    kws.sort(key=lambda x: x["count"], reverse=True)
                    speakers.append({
                        "name": spk["name"],
                        "speech_count": spk["speech_count"],
                        "keywords": kws[:10]
                    })
                speakers.sort(key=lambda x: x["speech_count"], reverse=True)
                response_data = {"success": True, "speakers": speakers}

            elif api_name == 'calendar':
                events = []
                for m in data.get("meetings", []):
                    events.append({
                        "date": m.get("date"),
                        "title": m.get("filename"),
                        "meeting_type": m.get("meeting_type")
                    })
                response_data = {"success": True, "events": events}

        encoded_data = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded_data)))
        self.end_headers()
        self.wfile.write(encoded_data)

def run(server_class=HTTPServer, handler_class=SystemCDevServer):
    server_address = ('', PORT)
    httpd = server_class(server_address, handler_class)
    print(f"\n[System C Python Dev Server] Running at http://localhost:{PORT}")
    if HAS_POSTGRES:
        print(f"Connected dynamically to Supabase Database.")
    else:
        print(f"Reading local JSON fallback database from: {LOCAL_JSON_PATH}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    print("\nServer stopped.")

if __name__ == '__main__':
    run()
