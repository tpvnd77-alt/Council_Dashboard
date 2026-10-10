"""지식 계층 — Decision Log(20컬럼 + 확장 컬럼), 점수 조정 이력, 감사 로그.

Phase 2 구성(DB 원천 + 엑셀은 조회용 자동 갱신)을 SQLite 한 파일로 구현한다.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .config import DATA_DIR

DB_PATH = DATA_DIR / "decision_log.db"
_lock = threading.Lock()

# IX장 1절(20컬럼) + 2절(확장 컬럼) + 시스템 운영 컬럼
CORE_COLUMNS = [
    "DOC_ID", "UPLOAD_DATE", "DOC_TITLE", "SOURCE_TYPE", "ISSUE_ID",
    "SCORE_REG", "SCORE_FIN", "SCORE_PR", "SCORE_LEG", "TOTAL_RISK_SCORE", "RISK_LEVEL",
    "EXECUTIVE_SUMMARY", "RISK_DESCRIPTION", "DECISION_POINTS", "TODO_ACTIONS", "PR_STANCE",
    "DUE_DATE", "D_DAY", "STATUS", "DECISION_TYPE",
]
EXT_COLUMNS = [
    "SCORE_OPP", "ISSUE_ID_SUB", "CLASS_CONFIDENCE", "SCENARIOS", "NEGOTIATION_CARDS", "CEO_QA",
    "AGENT_RECOMMENDATION", "FINAL_DECISION", "REVIEWER", "APPROVER", "PROMPT_VERSION", "SOURCE_REF",
]
SYS_COLUMNS = [
    "STAGE", "GATE1_REQUIRED", "NEW_CATEGORY_CANDIDATE", "SOURCE_TEXT", "MASKED",
    "CLASSIFICATION_JSON", "PANEL_JSON", "REPORT_JSON", "CRITIC_JSON", "LOOP_LOG", "VALIDATION_JSON",
    "MODEL_VERSION", "ERROR", "LESSONS", "DECIDED_AT", "UPDATED_AT", "LEAD_SECONDS",
]
ALL_COLUMNS = CORE_COLUMNS + EXT_COLUMNS + SYS_COLUMNS
INT_COLS = {"SCORE_REG", "SCORE_FIN", "SCORE_PR", "SCORE_LEG", "SCORE_OPP", "GATE1_REQUIRED"}
REAL_COLS = {"TOTAL_RISK_SCORE", "CLASS_CONFIDENCE", "LEAD_SECONDS"}

# 파이프라인 단계 (STATUS 와 별개인 내부 진행 상태)
STAGES = ["ingested", "classifying", "gate1", "analyzing", "review", "decision", "decided", "error"]


def _coltype(c):
    if c == "DOC_ID":
        return "TEXT PRIMARY KEY"
    if c in INT_COLS:
        return "INTEGER"
    if c in REAL_COLS:
        return "REAL"
    return "TEXT"


@contextmanager
def conn():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE IF NOT EXISTS decision_log (" +
                  ", ".join(f"{k} {_coltype(k)}" for k in ALL_COLUMNS) + ")")
        have = {r[1] for r in c.execute("PRAGMA table_info(decision_log)")}
        for k in ALL_COLUMNS:  # 컬럼이 늘어나도 기존 DB 를 그대로 쓴다
            if k not in have:
                c.execute(f"ALTER TABLE decision_log ADD COLUMN {k} {_coltype(k)}")
        c.execute("""CREATE TABLE IF NOT EXISTS adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT, l3 TEXT, field TEXT,
            before TEXT, after TEXT, reason TEXT, actor TEXT, role TEXT, at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT, step TEXT, model TEXT,
            prompt_version TEXT, attempt INTEGER, input_chars INTEGER, output TEXT,
            usage TEXT, at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS eval_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, prompt_versions TEXT,
            split TEXT, summary TEXT, detail TEXT)""")


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def new_doc_id(date: dt.date | None = None) -> str:
    date = date or dt.date.today()
    prefix = f"DOC-{date:%y%m%d}-"
    with _lock, conn() as c:
        row = c.execute("SELECT DOC_ID FROM decision_log WHERE DOC_ID LIKE ? ORDER BY DOC_ID DESC LIMIT 1",
                        (prefix + "%",)).fetchone()
        n = int(row[0].rsplit("-", 1)[1]) + 1 if row else 1
        doc_id = f"{prefix}{n:03d}"
        c.execute("INSERT INTO decision_log (DOC_ID, UPLOAD_DATE, STATUS, STAGE, UPDATED_AT) VALUES (?,?,?,?,?)",
                  (doc_id, now(), "신규접수", "ingested", now()))
    return doc_id


def _enc(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


def update(doc_id: str, **fields) -> None:
    bad = set(fields) - set(ALL_COLUMNS)
    if bad:
        raise KeyError(f"없는 컬럼: {bad}")
    fields["UPDATED_AT"] = now()
    keys = list(fields)
    with conn() as c:
        c.execute(f"UPDATE decision_log SET {', '.join(k + '=?' for k in keys)} WHERE DOC_ID=?",
                  [_enc(fields[k]) for k in keys] + [doc_id])


JSON_COLS = {"CLASSIFICATION_JSON", "PANEL_JSON", "REPORT_JSON", "CRITIC_JSON", "LOOP_LOG",
             "VALIDATION_JSON", "MASKED"}


def _row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    for k in JSON_COLS:
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except (TypeError, ValueError):
                pass
    return d


def get(doc_id: str) -> dict | None:
    with conn() as c:
        return _row(c.execute("SELECT * FROM decision_log WHERE DOC_ID=?", (doc_id,)).fetchone())


def list_records(heavy: bool = False, where: str = "", params: tuple = ()) -> list[dict]:
    cols = "*" if heavy else ", ".join(c for c in ALL_COLUMNS if c not in
                                       ("SOURCE_TEXT", "PANEL_JSON", "REPORT_JSON", "CRITIC_JSON",
                                        "LOOP_LOG", "CLASSIFICATION_JSON"))
    with conn() as c:
        rows = c.execute(f"SELECT {cols} FROM decision_log {where} ORDER BY UPLOAD_DATE DESC", params)
        return [_row(r) for r in rows]


def similar_cases(l3_codes: list[str], issue_prefixes: list[str], exclude: str, limit: int = 3) -> list[dict]:
    """같은 L3 의 과거 사례 — 조직장 결정이 끝난 건을 우선한다 (Prompt 조립 User 3)."""
    if not issue_prefixes:
        return []
    like = " OR ".join("ISSUE_ID LIKE ?" for _ in issue_prefixes)
    with conn() as c:
        rows = c.execute(
            f"""SELECT DOC_ID, UPLOAD_DATE, DOC_TITLE, ISSUE_ID, TOTAL_RISK_SCORE, RISK_LEVEL,
                       EXECUTIVE_SUMMARY, AGENT_RECOMMENDATION, FINAL_DECISION, STATUS, LESSONS
                FROM decision_log WHERE ({like}) AND DOC_ID != ? AND REPORT_JSON IS NOT NULL
                ORDER BY (FINAL_DECISION IS NOT NULL) DESC, UPLOAD_DATE DESC LIMIT ?""",
            [p + "%" for p in issue_prefixes] + [exclude, limit])
        return [dict(r) for r in rows]


def open_issues(exclude: str) -> list[dict]:
    """진행 중인 관련 이슈 (Big Deal 탐색용, Prompt 조립 User 4)."""
    with conn() as c:
        rows = c.execute("""SELECT DOC_ID, ISSUE_ID, DOC_TITLE, RISK_LEVEL, STATUS FROM decision_log
                            WHERE STATUS IN ('분석완료','대응중') AND DOC_ID != ?
                            ORDER BY UPLOAD_DATE DESC LIMIT 15""", (exclude,))
        return [dict(r) for r in rows]


def add_adjustment(doc_id: str, l3: str, field: str, before, after, reason: str, actor: str, role: str):
    with conn() as c:
        c.execute("INSERT INTO adjustments (doc_id,l3,field,before,after,reason,actor,role,at) VALUES (?,?,?,?,?,?,?,?,?)",
                  (doc_id, l3, field, str(before), str(after), reason, actor, role, now()))


def adjustments(since: str = "") -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM adjustments WHERE at >= ? ORDER BY at", (since,))]


def audit(doc_id: str, step: str, model: str, prompt_version: str, attempt: int,
          input_chars: int, output, usage: dict | None):
    with conn() as c:
        c.execute("INSERT INTO audit_log (doc_id,step,model,prompt_version,attempt,input_chars,output,usage,at) "
                  "VALUES (?,?,?,?,?,?,?,?,?)",
                  (doc_id, step, model, prompt_version, attempt, input_chars,
                   json.dumps(output, ensure_ascii=False, default=str)[:200000],
                   json.dumps(usage or {}, default=str), now()))


def audit_trail(doc_id: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id, step, model, prompt_version, attempt, input_chars, usage, at FROM audit_log "
            "WHERE doc_id=? ORDER BY id", (doc_id,))]


def save_eval(prompt_versions: dict, split: str, summary: dict, detail: list) -> int:
    with conn() as c:
        cur = c.execute("INSERT INTO eval_runs (at, prompt_versions, split, summary, detail) VALUES (?,?,?,?,?)",
                        (now(), json.dumps(prompt_versions, ensure_ascii=False), split,
                         json.dumps(summary, ensure_ascii=False), json.dumps(detail, ensure_ascii=False)))
        return cur.lastrowid


def eval_history(limit: int = 20) -> list[dict]:
    with conn() as c:
        out = []
        for r in c.execute("SELECT id, at, prompt_versions, split, summary FROM eval_runs ORDER BY id DESC LIMIT ?",
                           (limit,)):
            d = dict(r)
            d["prompt_versions"] = json.loads(d["prompt_versions"])
            d["summary"] = json.loads(d["summary"])
            out.append(d)
        return out


def db_path() -> Path:
    return DB_PATH
