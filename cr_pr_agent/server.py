"""웹 화면 + JSON API (표준 라이브러리만 사용).

기본은 127.0.0.1 에만 바인딩한다. Decision Log 에는 대외비가 담기므로 공유 서버에 올릴 때는
사내 SSO 프록시 뒤에 두고 CRPR_HOST 를 바꾼다. 분석은 백그라운드 스레드에서 돌고 화면은 STAGE 를 폴링한다.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import export_xlsx, feedback, pipeline, render, scoring, store  # noqa: E402
from agent.config import SETTINGS, Registry, Taxonomy, codebook  # noqa: E402
from agent.ingest import IngestError  # noqa: E402
from agent.llm import get_llm  # noqa: E402

WEB = Path(__file__).resolve().parent / "web"
HOST = os.environ.get("CRPR_HOST", "127.0.0.1")
MAX_UPLOAD = 40 * 1024 * 1024


def _bg(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


def _with_dday(r: dict) -> dict:
    r["D_DAY"] = scoring.d_day(r.get("DUE_DATE")) if r.get("STATUS") != "종결" else None
    return r


def dashboard() -> dict:
    recs = [_with_dday(r) for r in store.list_records()]
    tx = Taxonomy()
    open_recs = [r for r in recs if r["STATUS"] != "종결"]

    def by(key, rows):
        return {k: sum(1 for r in rows if r.get(key) == k) for k in {r.get(key) for r in rows} if k}

    l1 = {}
    for r in recs:
        p = tx.path(r.get("ISSUE_ID") or "")
        if p:
            l1[p["l1"]["name"]] = l1.get(p["l1"]["name"], 0) + 1
    months = {}
    for r in recs:
        m = (r["UPLOAD_DATE"] or "")[:7]
        months[m] = months.get(m, 0) + 1
    decided = [r for r in recs if r.get("FINAL_DECISION")]
    kinds = {k: sum(1 for r in decided if r["FINAL_DECISION"].startswith(k)) for k in ("승인", "수정 채택", "기각")}
    return {
        "total": len(recs), "open": len(open_recs),
        "by_level": by("RISK_LEVEL", open_recs), "by_status": by("STATUS", recs), "by_l1": l1,
        "by_month": dict(sorted(months.items())), "decisions": kinds,
        "adoption_rate": round((kinds["승인"] + kinds["수정 채택"]) / len(decided), 2) if decided else None,
        "alerts": pipeline.alerts(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "CRPR/1.0"

    def log_message(self, fmt, *args):
        if os.environ.get("CRPR_LOG"):
            super().log_message(fmt, *args)

    # ---------------------------------------------------------- 응답 도우미
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode(), "application/json; charset=utf-8")

    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD * 1.4:
            raise ValueError("파일이 너무 큽니다(최대 40MB).")
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw or b"{}")

    def _download(self, data: bytes, name: str, ctype: str):
        self._send(200, data, ctype, {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})

    # ---------------------------------------------------------------- GET
    def do_GET(self):
        try:
            self.route_get(urlparse(self.path))
        except Exception as e:  # noqa: BLE001
            self.json({"error": str(e), "trace": traceback.format_exc()[-800:]}, 500)

    def route_get(self, u):
        p, q = u.path, parse_qs(u.query)
        if p == "/api/status":
            llm = get_llm()
            return self.json({"mode": "offline" if llm.offline else SETTINGS.provider,
                              "heavy_model": SETTINGS.heavy_model, "light_model": SETTINGS.light_model,
                              "fallbacks": getattr(llm, "fallbacks", False), "max_revisions": SETTINGS.max_revisions})
        if p == "/report.css":
            return self._send(200, render.REPORT_CSS.encode(), "text/css; charset=utf-8")
        if p == "/api/codebook":
            return self.json(codebook())
        if p == "/api/dashboard":
            return self.json(dashboard())
        if p == "/api/records":
            return self.json([_with_dday(r) for r in store.list_records()])
        if p == "/api/alerts":
            return self.json(pipeline.alerts())
        if p == "/api/taxonomy":
            tx = Taxonomy()
            rows = [{**i, "label": tx.label(i["issue_id"]), "l3_name": tx.l3[i["l3"]]["name"],
                     "prompt": tx.l3[i["l3"]].get("prompt")} for i in tx.data["issues"]]
            return self.json({"issues": rows, "l3": list(tx.l3.values())})
        if p == "/api/prompts":
            return self.json(Registry().listing())
        if p == "/api/evals":
            return self.json(store.eval_history())
        if p == "/api/feedback":
            since = (q.get("since") or [""])[0]
            stats = feedback.collect(since)
            props = sorted(x.name for x in feedback.PROPOSALS.glob("*.md")) if feedback.PROPOSALS.exists() else []
            return self.json({"stats": stats, "markdown": feedback.report_markdown(stats), "proposals": props})
        if p == "/api/export.xlsx":
            return self._download(export_xlsx.build(), "CR_PR_전략_에이전트_운영_워크북.xlsx",
                                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        m = re.fullmatch(r"/api/records/(DOC-\d{6}-\d{3})(/report\.html|/report\.docx)?", p)
        if m:
            rec = store.get(m.group(1))
            if not rec:
                return self.json({"error": "없는 문서"}, 404)
            if m.group(2) == "/report.html":
                return self._send(200, render.report_html(rec).encode(), "text/html; charset=utf-8")
            if m.group(2) == "/report.docx":
                return self._download(render.report_docx(rec), f"{rec['DOC_ID']}_의사결정보고서.docx",
                                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            rec = _with_dday(rec)
            rec["report_html"] = render.report_html(rec, standalone=False) if rec.get("REPORT_JSON") else ""
            rec["audit"] = store.audit_trail(rec["DOC_ID"])
            rec["label"] = Taxonomy().label(rec.get("ISSUE_ID") or "")
            return self.json(rec)
        # 정적 파일
        name = "index.html" if p in ("/", "") else p.lstrip("/")
        f = (WEB / name).resolve()
        if WEB.resolve() not in f.parents or not f.is_file():
            return self._send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        extra = {}
        if f.name == "index.html":
            extra["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:"
        return self._send(200, f.read_bytes(), ctype, extra)

    # --------------------------------------------------------------- POST
    def do_POST(self):
        try:
            self.route_post(urlparse(self.path).path, self.body())
        except (IngestError, ValueError, KeyError) as e:
            self.json({"error": str(e)}, 400)
        except pipeline.GateRequired as e:
            self.json({"error": str(e)}, 409)
        except Exception as e:  # noqa: BLE001
            self.json({"error": str(e), "trace": traceback.format_exc()[-800:]}, 500)

    def route_post(self, p, b):
        if p == "/api/ingest":
            data = base64.b64decode(b["file_b64"]) if b.get("file_b64") else b""
            if len(data) > MAX_UPLOAD:
                raise ValueError("파일이 너무 큽니다(최대 40MB).")
            doc_id = pipeline.ingest(b.get("filename", ""), data, text=b.get("text", ""),
                                     title=b.get("title", ""), source_type=b.get("source_type", "언론"),
                                     source_ref=b.get("source_ref", ""))
            _bg(pipeline.run, doc_id)
            return self.json({"doc_id": doc_id})
        if p == "/api/inbox":
            return self.json(pipeline.process_inbox())
        if p == "/api/taxonomy/issue":
            return self.json(Taxonomy().add_issue(b["l3"], b["name"].strip()))
        if p == "/api/taxonomy/deprecate":
            Taxonomy().deprecate_issue(b["issue_id"])
            return self.json({"ok": True})
        if p == "/api/feedback/propose":
            stats = feedback.collect(b.get("since", ""))
            return self.json({"proposal": str(feedback.propose(b["prompt_id"], stats).name)})
        if p == "/api/feedback/promote":
            path = feedback.PROPOSALS / Path(b["proposal"]).name
            return self.json(feedback.promote(path, b.get("split", "dev")))
        if p == "/api/evals/run":
            from agent.evals import run_eval
            _bg(run_eval, b.get("split", "dev"))
            return self.json({"started": True})
        m = re.fullmatch(r"/api/records/(DOC-\d{6}-\d{3})/(\w+)", p)
        if not m:
            return self.json({"error": "없는 경로"}, 404)
        doc_id, action = m.groups()
        if not store.get(doc_id):
            return self.json({"error": "없는 문서"}, 404)
        if action == "confirm":
            pipeline.confirm_classification(doc_id, b["issue_id"], b.get("sub_ids", []), b["actor"], b.get("reason", ""))
            _bg(pipeline.run, doc_id)
            return self.json({"ok": True})
        if action == "rerun":
            if b.get("step") == "classify":
                store.update(doc_id, CLASSIFICATION_JSON=None, GATE1_REQUIRED=0)
            store.update(doc_id, STAGE="analyzing")
            _bg(pipeline.run, doc_id)
            return self.json({"ok": True})
        if action == "review":
            return self.json(pipeline.review(doc_id, b["reviewer"], b.get("scores"), b.get("reasons"),
                                             b.get("owners"), b.get("note", "")))
        if action == "decide":
            return self.json(pipeline.decide(doc_id, b["approver"], b["decision"], b.get("reason", ""),
                                             b.get("decision_type", ""), b.get("final_text", ""), b.get("scores")))
        if action == "close":
            pipeline.close(doc_id, b["lessons"], b["actor"])
            return self.json({"ok": True})
        return self.json({"error": "없는 동작"}, 404)


def main(port: int | None = None):
    store.init()
    port = port or SETTINGS.port
    srv = ThreadingHTTPServer((HOST, port), Handler)
    mode = "오프라인 모의 모드" if get_llm().offline else f"{SETTINGS.provider} ({SETTINGS.heavy_model} / {SETTINGS.light_model})"
    print(f"CR·PR 의사결정 에이전트 — http://{HOST}:{port}  [{mode}]")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
