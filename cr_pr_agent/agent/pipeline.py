"""오케스트레이터 — 5단계 파이프라인과 두 개의 사람 게이트, 품질 루프.

  Step 1 ingest      → DOC_ID 발번, 추출·마스킹             (STATUS 신규접수)
  Step 2 classify    → 신뢰도 < 0.7 또는 신규 분류 후보면 ── 게이트 1 (담당자 분류 확정)
  Step 3 risk panel  → 4대 리스크 + 기회 sub-agent 병렬, 점수는 시스템 수식
  Step 4 synthesize  → 생성 ⟲ [결정론 검증 → critic sub-agent → 피드백 수정] 최대 N회
  Step 5 deliver     → Decision Log 기록, 담당자 검수(점수 조정)  (STATUS 분석완료)
                     ── 게이트 2 (조직장 승인/수정 채택/기각)      (STATUS 대응중/종결)

각 단계 결과는 DB 에 저장되므로 실패하면 그 단계부터 다시 돌린다.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import time
import traceback
from pathlib import Path

from . import render, scoring, store, subagents
from .config import ROOT, SETTINGS, Registry, Taxonomy, codebook
from .ingest import IngestError, extract, mask_pii, normalize
from .llm import LLMError, get_llm
from .schema import DecisionReport
from .validate import validate

INBOX = ROOT / "inbox"
GOLDEN_CANDIDATES = ROOT / "golden" / "candidates"


class GateRequired(Exception):
    pass


# ------------------------------------------------------------------ Step 1
def ingest(filename: str = "", data: bytes = b"", *, text: str = "", title: str = "",
           source_type: str = "언론", source_ref: str = "") -> str:
    cb = codebook()
    if source_type not in cb["source_types"]:
        raise IngestError(f"출처유형은 {cb['source_types']} 중 하나여야 합니다.")
    if source_type == "사내보고서" and not SETTINGS.allow_internal_docs and not get_llm().offline:
        raise IngestError("사내보고서의 외부 API 전송이 정책상 차단되어 있습니다(CRPR_ALLOW_INTERNAL=0).")
    warnings, pages = [], 0
    if data:
        ex = extract(filename, data)
        body, warnings, pages = ex.text, ex.warnings, ex.pages
    else:
        body = normalize(text)
    if not body.strip():
        raise IngestError("본문이 비어 있습니다.")
    masked = {}
    if SETTINGS.mask_pii:
        body, masked = mask_pii(body)
    title = title.strip() or (Path(filename).stem if filename else body.splitlines()[0][:80])
    store.init()
    doc_id = store.new_doc_id()
    store.update(doc_id, DOC_TITLE=title, SOURCE_TYPE=source_type, SOURCE_TEXT=body,
                 SOURCE_REF=source_ref or filename, MASKED={"counts": masked, "warnings": warnings, "pages": pages})
    return doc_id


# ------------------------------------------------------------- 공통 문맥
def _context(rec: dict) -> dict:
    tx = Taxonomy()
    ctx = {
        "doc_id": rec["DOC_ID"], "title": rec["DOC_TITLE"], "source_type": rec["SOURCE_TYPE"],
        "upload_date": (rec["UPLOAD_DATE"] or "")[:10], "text": rec["SOURCE_TEXT"], "taxonomy": tx,
    }
    cl = rec.get("CLASSIFICATION_JSON")
    if isinstance(cl, dict) and rec.get("ISSUE_ID"):
        cl = {**cl, "primary_issue_id": rec["ISSUE_ID"],
              "sub_issue_ids": [x for x in (rec.get("ISSUE_ID_SUB") or "").split(",") if x]}
        ctx["classification"] = cl
        path = tx.path(rec["ISSUE_ID"])
        ctx["l3_code"] = path["l3"]["code"] if path else ""
        ctx["l3_prompt_id"] = path["l3"].get("prompt", "GEN-0000") if path else "GEN-0000"
        # 같은 L3 의 과거 사례 (ISSUE_ID 마지막 자리를 뗀 접두어 = 같은 L3)
        prefix = rec["ISSUE_ID"][:-1] if path else ""
        ctx["similar"] = store.similar_cases([ctx["l3_code"]], [prefix] if prefix else [], rec["DOC_ID"])
        ctx["open_issues"] = store.open_issues(rec["DOC_ID"])
    return ctx


def _audit(doc_id: str, calls: list, attempt: int = 0):
    for step, res, tag in calls:
        store.audit(doc_id, step, res.model, tag, attempt, 0, res.obj.model_dump(), res.usage)


def _retry(fn, *a, tries: int = 2, **kw):
    """해당 단계만 재시도 (구조화 출력 파싱 실패 등)."""
    last = None
    for _ in range(tries):
        try:
            return fn(*a, **kw)
        except LLMError as e:
            last = e
            if "인증" in str(e) or "거절" in str(e):
                break
    raise last


# ------------------------------------------------------------------ Step 2
def classify(doc_id: str) -> dict:
    rec = store.get(doc_id)
    store.update(doc_id, STAGE="classifying", ERROR=None)
    ctx = _context(rec)
    cl, calls = _retry(subagents.classify, ctx, Registry())
    _audit(doc_id, calls)
    thr = codebook()["classification_confidence_threshold"]
    gate = cl["confidence"] < thr or bool(cl.get("new_category_candidate"))
    store.update(doc_id, CLASSIFICATION_JSON=cl, ISSUE_ID=cl["primary_issue_id"],
                 ISSUE_ID_SUB=",".join(cl["sub_issue_ids"]), CLASS_CONFIDENCE=cl["confidence"],
                 NEW_CATEGORY_CANDIDATE=cl.get("new_category_candidate") or None,
                 GATE1_REQUIRED=int(gate), STAGE="gate1" if gate else "analyzing")
    return cl


def confirm_classification(doc_id: str, issue_id: str, sub_ids: list[str], actor: str, reason: str = "") -> None:
    """게이트 1 — 담당자 분류 확정. 바뀐 경우 조정 이력에 남긴다(분류 정확도 지표)."""
    tx = Taxonomy()
    if issue_id not in tx.issues:
        raise ValueError(f"없는 ISSUE_ID: {issue_id}")
    rec = store.get(doc_id)
    if rec["ISSUE_ID"] != issue_id:
        store.add_adjustment(doc_id, tx.issues[issue_id]["l3"], "ISSUE_ID", rec["ISSUE_ID"], issue_id,
                             reason or "분류 수정", actor, "담당자")
    store.update(doc_id, ISSUE_ID=issue_id, ISSUE_ID_SUB=",".join(s for s in sub_ids if s in tx.issues)[:30],
                 GATE1_REQUIRED=0, REVIEWER=actor, STAGE="analyzing")


# --------------------------------------------------------------- Step 3~4
def analyze(doc_id: str) -> dict:
    rec = store.get(doc_id)
    if rec["STAGE"] == "gate1" or rec.get("GATE1_REQUIRED"):
        raise GateRequired("게이트 1: 담당자 분류 확정이 필요합니다.")
    t0 = time.time()
    reg = Registry()
    ctx = _context(rec)
    store.update(doc_id, STAGE="analyzing", ERROR=None)

    # Step 3 — 리스크 패널 (sub-agent 5개 병렬) + 시스템 수식
    panel, calls = _retry(subagents.risk_panel, ctx, reg)
    _audit(doc_id, calls)
    ctx["panel"] = panel
    scores = {k: panel[k]["score"] for k in scoring.AREAS}
    opp = panel["SCORE_OPP"]["score"]
    upload = dt.date.fromisoformat(ctx["upload_date"]) if ctx["upload_date"] else dt.date.today()
    ev = scoring.evaluate(scores, opp, upload)
    store.update(doc_id, PANEL_JSON=panel, SCORE_OPP=opp, TOTAL_RISK_SCORE=ev["TOTAL_RISK_SCORE"],
                 RISK_LEVEL=ev["RISK_LEVEL"], DECISION_TYPE=ev["DECISION_TYPE"], DUE_DATE=ev["DUE_DATE"], **scores)

    # Step 4 — 품질 루프: 생성 → 결정론 검증 → critic → 피드백 수정
    report, check, critic, loop_log, converged = quality_loop(
        ctx, reg, on_calls=lambda calls, attempt: _audit(doc_id, calls, attempt))

    fields = render.decision_log_fields(report, panel, Taxonomy())
    store.update(doc_id, REPORT_JSON=report.model_dump(), VALIDATION_JSON=check,
                 CRITIC_JSON=critic.model_dump() if critic else None,
                 LOOP_LOG={"converged": converged, "attempts": loop_log},
                 PROMPT_VERSION=reg.version_tag(ctx["l3_prompt_id"]),
                 MODEL_VERSION=f"heavy={SETTINGS.heavy_model};light={SETTINGS.light_model}"
                 + (";offline" if get_llm().offline else ""),
                 STAGE="review", LEAD_SECONDS=round(time.time() - t0, 1), **fields)
    return {"converged": converged, "attempts": len(loop_log), **ev}


def quality_loop(ctx: dict, reg: Registry, max_revisions: int | None = None, on_calls=None):
    """생성 ⟲ 검증 루프. 결정론 검증(싸다)을 먼저 통과해야 critic sub-agent(비싸다)를 부른다.
    실패 내용은 다음 생성의 피드백으로 들어가고, 한도를 넘기면 마지막 초안을 검수 대기로 넘긴다."""
    max_revisions = SETTINGS.max_revisions if max_revisions is None else max_revisions
    history_text = subagents.history_block(ctx)
    feedback, loop_log, report, check, critic = None, [], None, None, None
    for attempt in range(max_revisions + 1):
        critic = None
        report, calls = _retry(subagents.synthesize, ctx, reg, feedback)
        if on_calls:
            on_calls(calls, attempt)
        check = validate(report, ctx["text"], ctx["panel"], history_text)
        entry = {"attempt": attempt, "validator_errors": check["errors"], "critic": None}
        loop_log.append(entry)
        if not check["passed"]:
            feedback = check["errors"]
            continue
        critic, calls = _retry(subagents.critique, ctx, reg, report)
        if on_calls:
            on_calls(calls, attempt)
        entry["critic"] = critic.model_dump()
        if critic.passed:
            break
        feedback = [f"[{i.type}] {i.field}: {i.problem} → {i.fix_hint}" for i in critic.issues]
    converged = bool(check["passed"] and critic and critic.passed)
    return report, check, critic, loop_log, converged


def run(doc_id: str) -> str:
    """접수된 문서를 가능한 데까지 진행한다. 게이트에서 멈추면 그 단계를 돌려준다."""
    try:
        rec = store.get(doc_id)
        if not rec.get("CLASSIFICATION_JSON"):
            classify(doc_id)
            rec = store.get(doc_id)
        if rec["STAGE"] == "gate1":
            return "gate1"
        if not rec.get("REPORT_JSON") or rec["STAGE"] in ("analyzing", "error"):
            analyze(doc_id)
        return store.get(doc_id)["STAGE"]
    except GateRequired:
        return "gate1"
    except Exception as e:  # 단계 상태를 남기고 재실행할 수 있게 한다
        store.update(doc_id, STAGE="error", ERROR=f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}")
        return "error"


# ------------------------------------------------------- Step 5 검수·게이트 2
def review(doc_id: str, reviewer: str, scores: dict | None = None, reasons: dict | None = None,
           owners: dict | None = None, note: str = "") -> dict:
    """담당자 검수 — 점수 조정(전·후 값과 사유 저장), Action 담당자 실명 지정."""
    rec = store.get(doc_id)
    if not rec.get("REPORT_JSON"):
        raise ValueError("분석 결과가 없습니다.")
    tx = Taxonomy()
    l3 = tx.issues.get(rec["ISSUE_ID"], {}).get("l3", "")
    upd = {}
    for k, v in (scores or {}).items():
        if k not in list(scoring.AREAS) + ["SCORE_OPP"]:
            continue
        v = max(1, min(5, int(v)))
        if v != rec[k]:
            store.add_adjustment(doc_id, l3, k, rec[k], v, (reasons or {}).get(k, ""), reviewer, "담당자")
            upd[k] = v
    merged = {k: upd.get(k, rec[k]) for k in list(scoring.AREAS) + ["SCORE_OPP"]}
    ev = scoring.evaluate({k: merged[k] for k in scoring.AREAS}, merged["SCORE_OPP"],
                          dt.date.fromisoformat(rec["UPLOAD_DATE"][:10]))
    report = DecisionReport.model_validate(rec["REPORT_JSON"])
    for a in report.action_plan:
        if owners and owners.get(a.when):
            a.owner = owners[a.when]
    fields = render.decision_log_fields(report, rec["PANEL_JSON"], tx)
    store.update(doc_id, **upd, TOTAL_RISK_SCORE=ev["TOTAL_RISK_SCORE"], RISK_LEVEL=ev["RISK_LEVEL"],
                 DECISION_TYPE=ev["DECISION_TYPE"], REPORT_JSON=report.model_dump(), REVIEWER=reviewer,
                 STATUS="분석완료", STAGE="decision",
                 LESSONS=(rec.get("LESSONS") or "") + (f"[검수] {note}\n" if note else ""), **fields)
    return ev


def decide(doc_id: str, approver: str, decision: str, reason: str, decision_type: str = "",
           final_text: str = "", scores: dict | None = None) -> dict:
    """게이트 2 — 조직장 판단. 이 기록이 채택률·골든셋·피드백 루프의 원천이다."""
    cb = codebook()
    if decision not in cb["final_decisions"]:
        raise ValueError(f"결정은 {cb['final_decisions']} 중 하나")
    rec = store.get(doc_id)
    if rec["STATUS"] != "분석완료":
        raise ValueError("담당자 검수(분석완료) 후에 조직장 판단을 기록할 수 있습니다.")
    if scores:  # 조직장 최종 점수 확정
        tx = Taxonomy()
        l3 = tx.issues.get(rec["ISSUE_ID"], {}).get("l3", "")
        for k, v in scores.items():
            v = max(1, min(5, int(v)))
            if k in rec and v != rec[k]:
                store.add_adjustment(doc_id, l3, k, rec[k], v, reason, approver, "조직장")
                store.update(doc_id, **{k: v})
        rec = store.get(doc_id)
        ev = scoring.evaluate({k: rec[k] for k in scoring.AREAS}, rec["SCORE_OPP"],
                              dt.date.fromisoformat(rec["UPLOAD_DATE"][:10]))
        store.update(doc_id, TOTAL_RISK_SCORE=ev["TOTAL_RISK_SCORE"], RISK_LEVEL=ev["RISK_LEVEL"])
    dtype = decision_type or rec["DECISION_TYPE"]
    if dtype not in cb["report_levels"]:
        raise ValueError("보고 Level 이 올바르지 않습니다.")
    if dtype != rec["DECISION_TYPE"]:
        store.add_adjustment(doc_id, "", "DECISION_TYPE", rec["DECISION_TYPE"], dtype, reason, approver, "조직장")
    final = f"{decision}: {final_text or rec['AGENT_RECOMMENDATION']}" + (f" (사유: {reason})" if reason else "")
    status = "종결" if decision == "기각" else "대응중"
    store.update(doc_id, FINAL_DECISION=final, APPROVER=approver, DECISION_TYPE=dtype, STATUS=status,
                 STAGE="decided", DECIDED_AT=store.now())
    if decision != "승인":  # 기각·수정 채택 건은 골든셋 후보 (XII장 2절)
        GOLDEN_CANDIDATES.mkdir(parents=True, exist_ok=True)
        rec = store.get(doc_id)
        with open(GOLDEN_CANDIDATES / f"{doc_id}.json", "w", encoding="utf-8") as f:
            json.dump({k: rec[k] for k in ("DOC_ID", "DOC_TITLE", "SOURCE_TYPE", "ISSUE_ID", "SCORE_REG",
                                           "SCORE_FIN", "SCORE_PR", "SCORE_LEG", "SCORE_OPP", "SOURCE_TEXT",
                                           "AGENT_RECOMMENDATION", "FINAL_DECISION")},
                      f, ensure_ascii=False, indent=1)
    return {"status": status, "distribution": cb["distribution"][dtype]}


def close(doc_id: str, lessons: str, actor: str) -> None:
    rec = store.get(doc_id)
    store.update(doc_id, STATUS="종결", LESSONS=(rec.get("LESSONS") or "") + f"[종결·교훈 {actor}] {lessons}\n")


# ------------------------------------------------------------ 운영 루프
def process_inbox() -> list[dict]:
    """inbox/ 에 떨어진 파일을 자동 접수·분석한다. 파일명 '[출처유형] 제목.pdf' 를 해석한다."""
    import re

    out = []
    done = INBOX / "processed"
    done.mkdir(parents=True, exist_ok=True)
    for p in sorted(INBOX.iterdir()):
        if not p.is_file() or p.name.startswith(".") or p.name.lower() == "readme.md":
            continue
        m = re.match(r"^\[(정부부처|국회|경쟁사|언론|사내보고서)\]\s*(.+)$", p.stem)
        source, title = (m.group(1), m.group(2)) if m else ("언론", p.stem)
        try:
            doc_id = ingest(p.name, p.read_bytes(), title=title, source_type=source, source_ref=str(p.name))
            stage = run(doc_id)
            out.append({"file": p.name, "doc_id": doc_id, "stage": stage})
        except (IngestError, ValueError) as e:
            out.append({"file": p.name, "error": str(e)})
        shutil.move(str(p), done / f"{dt.datetime.now():%Y%m%d%H%M%S}_{p.name}")
    return out


def alerts(today: dt.date | None = None) -> list[dict]:
    """D-Day 알림 대상 (기한 3일 전·당일·경과) + 게이트 대기 건."""
    today = today or dt.date.today()
    days = codebook()["dday_alert_days"]
    out = []
    for r in store.list_records():
        if r["STATUS"] == "종결":
            continue
        dd = scoring.d_day(r.get("DUE_DATE"), today)
        reasons = []
        if dd is not None and (dd in days or dd < 0):
            reasons.append("기한 경과" if dd < 0 else f"D-{dd}" if dd else "D-Day")
        if r.get("STAGE") == "gate1":
            reasons.append("게이트1 분류 확정 대기")
        if r.get("STATUS") == "분석완료" and not r.get("FINAL_DECISION"):
            reasons.append("게이트2 조직장 판단 대기")
        if r.get("STAGE") == "review":
            reasons.append("담당자 검수 대기")
        if r.get("STAGE") == "error":
            reasons.append("처리 오류 — 재실행 필요")
        if reasons:
            out.append({"DOC_ID": r["DOC_ID"], "DOC_TITLE": r["DOC_TITLE"], "RISK_LEVEL": r.get("RISK_LEVEL"),
                        "DUE_DATE": r.get("DUE_DATE"), "D_DAY": dd, "reasons": reasons})
    return sorted(out, key=lambda x: (x["D_DAY"] if x["D_DAY"] is not None else 999))
