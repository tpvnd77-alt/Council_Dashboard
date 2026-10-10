"""CR·PR 의사결정 에이전트 CLI.

  python cli.py serve                         웹 화면 (기본 http://localhost:8787)
  python cli.py analyze 문서.pdf --source 정부부처 [--title ...]
  python cli.py confirm DOC-.. CR-1111 --actor 홍길동      게이트 1
  python cli.py daily                          inbox 처리 + D-Day 알림 + 워크북 갱신 (일일 루프)
  python cli.py alerts                         알림 대상만 출력
  python cli.py export [out.xlsx]              운영 워크북 갱신
  python cli.py eval [--split dev|test|all]    골든셋 평가
  python cli.py feedback [--since 2026-09-01] [--propose]   월간 피드백 루프
  python cli.py promote prompts/proposals/X@1.1.md          골든셋 게이트 통과 시 배포
  python cli.py status                         모드·모델·건수
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent import export_xlsx, feedback, pipeline, store  # noqa: E402
from agent.config import DATA_DIR, SETTINGS  # noqa: E402
from agent.llm import get_llm  # noqa: E402


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def cmd_analyze(a):
    p = Path(a.file)
    doc_id = pipeline.ingest(p.name, p.read_bytes(), title=a.title or "", source_type=a.source, source_ref=str(p))
    stage = pipeline.run(doc_id)
    rec = store.get(doc_id)
    res = {"doc_id": doc_id, "stage": stage, "issue_id": rec.get("ISSUE_ID"),
           "confidence": rec.get("CLASS_CONFIDENCE"), "risk": rec.get("TOTAL_RISK_SCORE"),
           "level": rec.get("RISK_LEVEL"), "report_level": rec.get("DECISION_TYPE"),
           "recommendation": rec.get("AGENT_RECOMMENDATION"), "error": rec.get("ERROR")}
    if stage == "gate1":
        res["next"] = f"python cli.py confirm {doc_id} <ISSUE_ID> --actor <담당자>"
    out(res)


def cmd_confirm(a):
    pipeline.confirm_classification(a.doc_id, a.issue_id, a.sub or [], a.actor, a.reason or "")
    out({"doc_id": a.doc_id, "stage": pipeline.run(a.doc_id)})


def cmd_rerun(a):
    rec = store.get(a.doc_id)
    if a.step == "classify":
        store.update(a.doc_id, CLASSIFICATION_JSON=None)
    store.update(a.doc_id, STAGE="analyzing" if rec.get("ISSUE_ID") and a.step != "classify" else "ingested")
    out({"doc_id": a.doc_id, "stage": pipeline.run(a.doc_id)})


def cmd_export(a):
    path = Path(a.out or DATA_DIR / "CR_PR_전략_에이전트_운영_워크북.xlsx")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(export_xlsx.build())
    print(path)


def cmd_daily(a):
    """일일 운영 루프 — 스케줄러(작업 스케줄러/cron/Claude /loop)가 부른다."""
    res = {"inbox": pipeline.process_inbox(), "alerts": pipeline.alerts()}
    path = DATA_DIR / "CR_PR_전략_에이전트_운영_워크북.xlsx"
    path.write_bytes(export_xlsx.build())
    res["workbook"] = str(path)
    out(res)


def cmd_eval(a):
    from agent.evals import run_eval
    r = run_eval(a.split, prompt_id=a.prompt)
    out({"summary": r["summary"], "cases": [{k: d[k] for k in ("id", "predicted_issue", "scores", "score")}
                                            for d in r["detail"]]})


def cmd_feedback(a):
    since = a.since or (dt.date.today().replace(day=1) - dt.timedelta(days=1)).replace(day=1).isoformat()
    stats = feedback.collect(since, a.until or "")
    path = feedback.save_report(stats)
    res = {"report": str(path), "adoption_rate": stats["adoption_rate"], "targets": stats["targets"],
           "revise_master": stats["revise_master"]}
    if a.propose:
        res["proposals"] = [str(feedback.propose(pid, stats)) for pid in sorted({t["prompt_id"] for t in stats["targets"]})]
    out(res)


def cmd_promote(a):
    out(feedback.promote(a.proposal, a.split, a.force))


def cmd_status(a):
    llm = get_llm()
    recs = store.list_records()
    out({"mode": "offline(모의)" if llm.offline else SETTINGS.provider,
         "heavy_model": SETTINGS.heavy_model, "light_model": SETTINGS.light_model,
         "db": str(store.db_path()), "records": len(recs),
         "by_status": {s: sum(r["STATUS"] == s for r in recs) for s in ("신규접수", "분석완료", "대응중", "종결")}})


def cmd_serve(a):
    import server
    server.main(a.port)


def main(argv=None):
    ap = argparse.ArgumentParser(description="CR·PR 의사결정 에이전트")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("analyze"); p.add_argument("file"); p.add_argument("--source", default="언론"); p.add_argument("--title")
    p.set_defaults(fn=cmd_analyze)
    p = sp.add_parser("confirm"); p.add_argument("doc_id"); p.add_argument("issue_id"); p.add_argument("--sub", nargs="*")
    p.add_argument("--actor", required=True); p.add_argument("--reason"); p.set_defaults(fn=cmd_confirm)
    p = sp.add_parser("rerun"); p.add_argument("doc_id"); p.add_argument("--step", choices=["classify", "analyze"], default="analyze")
    p.set_defaults(fn=cmd_rerun)
    p = sp.add_parser("export"); p.add_argument("out", nargs="?"); p.set_defaults(fn=cmd_export)
    sp.add_parser("daily").set_defaults(fn=cmd_daily)
    sp.add_parser("alerts").set_defaults(fn=lambda a: out(pipeline.alerts()))
    p = sp.add_parser("eval"); p.add_argument("--split", default="all"); p.add_argument("--prompt"); p.set_defaults(fn=cmd_eval)
    p = sp.add_parser("feedback"); p.add_argument("--since"); p.add_argument("--until"); p.add_argument("--propose", action="store_true")
    p.set_defaults(fn=cmd_feedback)
    p = sp.add_parser("promote"); p.add_argument("proposal"); p.add_argument("--split", default="dev")
    p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_promote)
    sp.add_parser("status").set_defaults(fn=cmd_status)
    p = sp.add_parser("serve"); p.add_argument("--port", type=int, default=SETTINGS.port); p.set_defaults(fn=cmd_serve)
    a = ap.parse_args(argv)
    store.init()
    a.fn(a)


if __name__ == "__main__":
    main()
