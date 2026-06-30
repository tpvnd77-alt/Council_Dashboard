import os
import sys
import json

# Auto-install psycopg2-binary if not installed
try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("Installing psycopg2-binary for database connection...")
    os.system(f"{sys.executable} -m pip install psycopg2-binary -q")
    import psycopg2
    from psycopg2.extras import execute_values

def get_db_connection():
    # Read connection string from environment variable
    # format: postgresql://postgres:password@db.xxx.supabase.co:5432/postgres
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("\n[오류] SUPABASE_DB_URL 환경 변수가 설정되지 않았습니다.")
        print("예시: set SUPABASE_DB_URL=postgresql://postgres:password@db.xxxxxx.supabase.co:5432/postgres")
        db_url = input("연결할 Supabase PostgreSQL URI를 입력해 주세요: ").strip()
        if not db_url:
            sys.exit(1)
    
    try:
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        print(f"데이터베이스 연결 실패: {e}")
        sys.exit(1)

def create_tables(conn):
    print("테이블 생성 중...")
    with conn.cursor() as cur:
        # Create meetings table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS meetings (
                meeting_id SERIAL PRIMARY KEY,
                filename VARCHAR(255) UNIQUE,
                date VARCHAR(10),
                session_num INTEGER,
                session_type VARCHAR(50),
                order_num INTEGER,
                meeting_type VARCHAR(50),
                year INTEGER,
                text_length INTEGER,
                summary TEXT,
                file_size INTEGER DEFAULT 0,
                parsed_full BOOLEAN DEFAULT FALSE
            );
        """)
        
        # Create agendas table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agendas (
                agenda_id SERIAL PRIMARY KEY,
                meeting_id INTEGER REFERENCES meetings(meeting_id) ON DELETE CASCADE,
                title TEXT,
                proposer VARCHAR(255),
                proposal_date VARCHAR(20),
                summary TEXT,
                link TEXT
            );
        """)
        
        # Create speeches table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS speeches (
                speech_id SERIAL PRIMARY KEY,
                meeting_id INTEGER REFERENCES meetings(meeting_id) ON DELETE CASCADE,
                speaker_name VARCHAR(100),
                content TEXT,
                page INTEGER,
                speech_count INTEGER,
                sentiment VARCHAR(20),
                ai_summary TEXT
            );
        """)
        
        # Create keywords table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS keywords (
                keyword_id SERIAL PRIMARY KEY,
                meeting_id INTEGER REFERENCES meetings(meeting_id) ON DELETE CASCADE,
                speaker_name VARCHAR(100) DEFAULT NULL,
                word VARCHAR(100),
                count INTEGER
            );
        """)
        
        # Create index for fast keyword searches (Full Text Search optimization)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_speeches_speaker ON speeches(speaker_name);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_speeches_meeting_id ON speeches(meeting_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_keywords_word ON keywords(word);")
        
        conn.commit()
    print("테이블 및 인덱스 생성 완료.")

def migrate():
    # Look for meetings.json
    json_path = r"C:\Users\hp\.gemini\antigravity\scratch\council_dashboard\data\meetings.json"
    if not os.path.exists(json_path):
        print(f"[오류] 원본 JSON 데이터베이스를 찾을 수 없습니다: {json_path}")
        return
        
    print(f"JSON 데이터 로딩 중: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        db_data = json.load(f)
        
    meetings = db_data.get("meetings", [])
    print(f"총 {len(meetings)}개 회의록 마이그레이션 시작...")
    
    conn = get_db_connection()
    create_tables(conn)
    
    try:
        for idx, m in enumerate(meetings, 1):
            filename = m.get("filename")
            print(f"[{idx}/{len(meetings)}] {filename} 처리 중...")
            
            with conn.cursor() as cur:
                # Insert meeting and get meeting_id
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
                
                # Delete existing related data to ensure clean overwrite
                cur.execute("DELETE FROM agendas WHERE meeting_id = %s;", (meeting_id,))
                cur.execute("DELETE FROM speeches WHERE meeting_id = %s;", (meeting_id,))
                cur.execute("DELETE FROM keywords WHERE meeting_id = %s;", (meeting_id,))
                
                # Insert agendas
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
                
                # Insert speeches and speech lines
                speeches_data = []
                for spk in m.get("speakers", []):
                    name = spk.get("name")
                    speech_cnt = spk.get("speech_count", 0)
                    # Note: meetings.json speaker object might not have sentiment/ai_summary, 
                    # but individual turns are stored in 'lines'
                    for line in spk.get("lines", []):
                        speeches_data.append((
                            meeting_id, name, line.get("text"), line.get("page"), speech_cnt, None, None
                        ))
                if speeches_data:
                    execute_values(cur, """
                        INSERT INTO speeches (meeting_id, speaker_name, content, page, speech_count, sentiment, ai_summary)
                        VALUES %s
                    """, speeches_data)
                
                # Insert keywords
                keywords_data = []
                # 1. Meeting level keywords
                for kw in m.get("keywords", []):
                    keywords_data.append((meeting_id, None, kw.get("word"), kw.get("count")))
                # 2. Speaker level keywords
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
                
        print("\n[성공] 모든 마이그레이션이 성공적으로 완수되었습니다!")
    except Exception as e:
        conn.rollback()
        print(f"\n[오류] 마이그레이션 중 오류 발생: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
