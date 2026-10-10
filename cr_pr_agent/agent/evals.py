"""골든셋 평가 (XII장) — Prompt 개정의 배포 게이트.

golden/*.json 의 각 사례를 Decision Log 를 건드리지 않고 파이프라인(분류→패널→품질 루프)에
통과시켜 조직장 정답 판단과 비교한다. split 은 dev(튜닝용 70%) / test(최종 평가용 30%).
test 사례는 Prompt 튜닝 피드백에 절대 쓰지 않는다.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import scoring, store, subagents
from .config import ROOT, Registry, Taxonomy, parse_prompt
from .pipeline import quality_loop

GOLDEN_DIR = ROOT / "golden"

# 종합 점수 가중치 — 6대 평가 기준 중 자동 측정 가능한 것
WEIGHTS = {"l3_match": 0.15, "score_within1": 0.2, "key_fact_recall": 0.2, "complete": 0.15,
           "action_concreteness": 0.1, "recommendation_match": 0.1, "no_hallucination": 0.1}


def load_cases(split: str = "all") -> list[dict]:
    cases = []
    for p in sorted(GOLDEN_DIR.glob("*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        c["_file"] = p.name
        if split == "all" or c.get("split") == split:
            cases.append(c)
    return cases


def registry_with(overrides: dict[str, str] | None) -> Registry:
    """overrides = {prompt_id: 개정안 파일 경로} — 개정안을 끼운 Registry."""
    reg = Registry()
    for pid, path in (overrides or {}).items():
        doc = parse_prompt(Path(path))
        doc.id = pid
        if pid == "MASTER":
            reg.master = doc
        else:
            reg.l3[pid] = doc
    return reg


def run_case(case: dict, reg: Registry, max_revisions: int = 1) -> dict:
    tx = Taxonomy()
    ctx = {"doc_id": f"GOLD-{case['id']}", "title": case["title"], "source_type": case["source_type"],
           "upload_date": case.get("upload_date", ""), "text": case["text"], "taxonomy": tx,
           "similar": [], "open_issues": []}
    cl, _ = subagents.classify(ctx, reg)
    exp = case["expected"]
    # 평가에서는 분류 오류가 뒤 단계 평가를 오염시키지 않도록 정답 코드로 이어서 진행 (게이트 1 재현)
    ctx["classification"] = {**cl, "primary_issue_id": exp["issue_id"]}
    path = tx.path(exp["issue_id"])
    ctx["l3_prompt_id"] = path["l3"].get("prompt", "GEN-0000")
    panel, _ = subagents.risk_panel(ctx, reg)
    ctx["panel"] = panel
    report, check, critic, loop_log, converged = quality_loop(ctx, reg, max_revisions=max_revisions)

    got = {k: panel[k]["score"] for k in scoring.AREAS}
    within = [abs(got[k] - exp["scores"][k]) <= 1 for k in scoring.AREAS]
    facts_text = " ".join(f.fact + " " + f.quote for f in report.key_content.key_facts)
    kf = exp.get("key_fact_keywords", [])
    recall = sum(any(w in facts_text for w in group) for group in kf) / len(kf) if kf else 1.0
    rec_text = report.decision.recommended_summary + " " + " ".join(
        o.title + o.description for o in report.decision.options if o.key == report.decision.recommended)
    rk = exp.get("recommendation_keywords", [])
    rec_match = (any(w in rec_text for w in rk)) if rk else True
    halluc = sum(1 for e in check["errors"] if e.startswith("수치")) + (
        sum(1 for i in critic.issues if i.type in ("hallucination", "invented_number")) if critic else 0)
    m = {
        "l3_match": tx.issues.get(cl["primary_issue_id"], {}).get("l3") == path["l3"]["code"],
        "score_within1": sum(within) / 4,
        "key_fact_recall": round(recall, 2),
        "complete": check["passed"],
        "action_concreteness": check["metrics"]["action_concreteness"],
        "recommendation_match": rec_match,
        "no_hallucination": halluc == 0,
    }
    total = sum(WEIGHTS[k] * float(v) for k, v in m.items())
    return {"id": case["id"], "split": case.get("split"), "predicted_issue": cl["primary_issue_id"],
            "scores": got, "expected_scores": exp["scores"],
            "total_risk": scoring.total_score(got), "expected_total": scoring.total_score(exp["scores"]),
            "metrics": m, "score": round(total, 3), "attempts": len(loop_log), "converged": converged,
            "hallucination_flags": halluc}


def run_eval(split: str = "all", overrides: dict | None = None, save: bool = True,
             prompt_id: str | None = None) -> dict:
    """prompt_id 를 주면 그 L3 Prompt 가 적용되는 사례만 돌린다 (개정 비교 비용 절감)."""
    reg = registry_with(overrides)
    cases = load_cases(split)
    if prompt_id and prompt_id != "MASTER":
        tx = Taxonomy()
        cases = [c for c in cases
                 if tx.path(c["expected"]["issue_id"])["l3"].get("prompt", "GEN-0000") == prompt_id]
    detail = [run_case(c, reg) for c in cases]
    n = max(len(detail), 1)
    summary = {"n": len(detail), "score": round(sum(d["score"] for d in detail) / n, 3)}
    for k in WEIGHTS:
        summary[k] = round(sum(float(d["metrics"][k]) for d in detail) / n, 3)
    summary["hallucinations"] = sum(d["hallucination_flags"] for d in detail)
    versions = {"master": reg.master.tag, "format": reg.format.tag,
                "l3": {k: v.tag for k, v in reg.l3.items()}, "overrides": overrides or {}}
    if save:
        store.init()
        store.save_eval(versions, split, summary, detail)
    return {"summary": summary, "detail": detail, "versions": versions}
