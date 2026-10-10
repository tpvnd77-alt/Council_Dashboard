"""피드백 루프 (VII장 6절, XII장 4절) — 운영 데이터로 Prompt 를 고치는 바깥 루프.

  1. collect()  : 기간 내 조정 이력·조직장 결정을 집계 (점수 편향, 채택률, 분류 정확도)
  2. targets    : 편향이 특정 L3 에 몰리면 그 L3 Prompt, 전반적이면 Master 를 개정 대상으로 지정
  3. propose()  : prompt tuner sub-agent 가 개정안 작성 → prompts/proposals/ (배포 아님)
  4. promote()  : 골든셋 dev 재평가에서 기존 점수 이상일 때만 prompts/ 로 반영, 구버전은 archive/
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

from . import store, subagents
from .config import DATA_DIR, PROMPT_DIR, Registry, Taxonomy, parse_prompt
from .scoring import AREAS

PROPOSALS = PROMPT_DIR / "proposals"
ARCHIVE = PROMPT_DIR / "archive"
REPORTS = DATA_DIR / "feedback"
BIAS_THRESHOLD = 0.75
REJECT_THRESHOLD = 0.3


def collect(since: str = "", until: str = "") -> dict:
    until = until or "9999"
    tx = Taxonomy()
    recs = [r for r in store.list_records() if since <= (r["UPLOAD_DATE"] or "") < until]
    adj = [a for a in store.adjustments(since) if a["at"] < until]

    # 문서·필드별 최초 값(에이전트) → 최종 값(사람)
    first, last = {}, {}
    for a in adj:
        key = (a["doc_id"], a["field"])
        first.setdefault(key, a["before"])
        last[key] = a["after"]

    l3_of = {r["DOC_ID"]: tx.issues.get(r.get("ISSUE_ID") or "", {}).get("l3", "") for r in recs}
    bias = defaultdict(lambda: defaultdict(list))
    reclass = []
    for (doc, field), before in first.items():
        if doc not in l3_of:
            continue
        if field in AREAS or field == "SCORE_OPP":
            try:
                bias[l3_of[doc]][field].append(int(last[(doc, field)]) - int(before))
            except ValueError:
                pass
        elif field == "ISSUE_ID":
            reclass.append({"doc": doc, "from": before, "to": last[(doc, field)]})

    decided = [r for r in recs if r.get("FINAL_DECISION")]
    kinds = {"승인": 0, "수정 채택": 0, "기각": 0}
    per_l3 = defaultdict(lambda: {"n": 0, "기각": 0, "수정 채택": 0, "승인": 0})
    for r in decided:
        k = r["FINAL_DECISION"].split(":")[0]
        if k in kinds:
            kinds[k] += 1
            per_l3[l3_of[r["DOC_ID"]]][k] += 1
            per_l3[l3_of[r["DOC_ID"]]]["n"] += 1

    analysed = [r for r in recs if r.get("TOTAL_RISK_SCORE") is not None]
    reclass_l3 = sum(1 for x in reclass if tx.issues.get(x["from"], {}).get("l3") != tx.issues.get(x["to"], {}).get("l3"))
    within = []  # 사람 확정값과 ±1 이내 비율 (조정되지 않은 값은 일치로 본다)
    for r in analysed:
        for f in AREAS:
            k = (r["DOC_ID"], f)
            within.append(abs(int(last[k]) - int(first[k])) <= 1 if k in first else True)

    bias_summary = {l3: {f: {"n": len(v), "mean": round(sum(v) / len(v), 2)} for f, v in fs.items()}
                    for l3, fs in bias.items()}
    targets = []
    for l3, fs in bias_summary.items():
        for f, b in fs.items():
            if b["n"] >= 2 and abs(b["mean"]) >= BIAS_THRESHOLD:
                targets.append({"l3": l3, "reason": f"{f} 평균 조정 {b['mean']:+.2f} (n={b['n']})"})
    for l3, c in per_l3.items():
        if c["n"] >= 2 and c["기각"] / c["n"] >= REJECT_THRESHOLD:
            targets.append({"l3": l3, "reason": f"기각률 {c['기각']}/{c['n']}"})
    for t in targets:
        t["prompt_id"] = tx.l3.get(t["l3"], {}).get("prompt", "GEN-0000")
    master_flag = len({t["prompt_id"] for t in targets}) >= 3

    n_dec = max(len(decided), 1)
    return {
        "period": {"since": since, "until": until if until != "9999" else ""},
        "documents": len(recs), "analysed": len(analysed), "decided": len(decided),
        "adoption_rate": round((kinds["승인"] + kinds["수정 채택"]) / n_dec, 2) if decided else None,
        "decisions": kinds,
        "classification_accuracy_l3": round(1 - reclass_l3 / max(len(analysed), 1), 2) if analysed else None,
        "score_within1": round(sum(within) / len(within), 2) if within else None,
        "avg_lead_seconds": round(sum(r["LEAD_SECONDS"] or 0 for r in analysed) / len(analysed), 1) if analysed else None,
        "closed": sum(1 for r in recs if r["STATUS"] == "종결"),
        "bias": bias_summary, "per_l3_decisions": dict(per_l3), "reclassified": reclass,
        "targets": targets, "revise_master": master_flag,
    }


def report_markdown(stats: dict) -> str:
    lines = [f"# 월간 피드백 리포트 ({stats['period']['since'] or '전체'} ~ {stats['period']['until'] or '현재'})", "",
             f"- 문서 {stats['documents']}건 / 분석 {stats['analysed']}건 / 조직장 결정 {stats['decided']}건 / 종결 {stats['closed']}건",
             f"- 추천안 채택률(승인+수정 채택): {stats['adoption_rate']}  — 목표 0.70",
             f"- 분류 정확도(L3): {stats['classification_accuracy_l3']}  — 목표 0.90",
             f"- 리스크 점수 ±1 일치도: {stats['score_within1']}  — 목표 0.85",
             f"- 평균 초안 생성 시간(초): {stats['avg_lead_seconds']}  — 목표 1800 이내", "",
             "## 점수 편향 (사람 최종값 − 에이전트 값)"]
    for l3, fs in stats["bias"].items():
        lines.append(f"- L3 {l3}: " + ", ".join(f"{f} {b['mean']:+.2f}(n={b['n']})" for f, b in fs.items()))
    lines += ["", "## 개정 대상"]
    lines += [f"- {t['prompt_id']} (L3 {t['l3']}): {t['reason']}" for t in stats["targets"]] or ["- 없음"]
    if stats["revise_master"]:
        lines.append("- 편향이 3개 이상 Prompt 에 걸쳐 있음 → Master Prompt 개정 검토")
    return "\n".join(lines) + "\n"


def save_report(stats: dict) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    p = REPORTS / f"feedback_{dt.date.today():%Y-%m}.md"
    p.write_text(report_markdown(stats), encoding="utf-8")
    (REPORTS / f"feedback_{dt.date.today():%Y-%m}.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def _bump(version: str) -> str:
    major, _, minor = version.partition(".")
    return f"{major}.{int(minor or 0) + 1}"


def propose(prompt_id: str, stats: dict) -> Path:
    """개정안 작성 — 운영 중인 Prompt 는 건드리지 않는다."""
    reg = Registry()
    cur = reg.l3_prompt(prompt_id) if prompt_id != "MASTER" else reg.master
    tx = Taxonomy()
    l3s = [c for c, x in tx.l3.items() if x.get("prompt") == prompt_id]
    samples = []
    for r in store.list_records():
        if tx.issues.get(r.get("ISSUE_ID") or "", {}).get("l3") in l3s and r.get("FINAL_DECISION"):
            samples.append({"title": r["DOC_TITLE"], "agent": r.get("AGENT_RECOMMENDATION"),
                            "final": r["FINAL_DECISION"], "lessons": r.get("LESSONS")})
    rev = subagents.propose_revision(cur.body, {"bias": {k: stats["bias"].get(k) for k in l3s},
                                                "targets": stats["targets"]}, samples[:10], reg.master.body)
    PROPOSALS.mkdir(parents=True, exist_ok=True)
    ver = _bump(cur.version)
    meta = dict(cur.meta, version=ver, status="proposed", base=cur.tag,
                created=dt.date.today().isoformat())
    head = "\n".join(f"{k}: {v}" for k, v in meta.items())
    notes = "\n".join(f"<!-- change: {c} -->" for c in rev.change_summary)
    p = PROPOSALS / f"{prompt_id}@{ver}.md"
    p.write_text(f"---\n{head}\n---\n<!-- diagnosis: {rev.diagnosis} -->\n{notes}\n"
                 f"{rev.revised_prompt_markdown.strip()}\n", encoding="utf-8")
    return p


def promote(proposal: str | Path, split: str = "dev", force: bool = False) -> dict:
    """골든셋 게이트: 개정안 점수 ≥ 현재 점수일 때만 배포한다."""
    from .evals import run_eval

    proposal = Path(proposal)
    doc = parse_prompt(proposal)
    pid = doc.id
    base = run_eval(split, save=True, prompt_id=pid)["summary"]
    cand = run_eval(split, overrides={pid: str(proposal)}, save=True, prompt_id=pid)["summary"]
    enough = cand["n"] >= 2  # 골든셋 2건 이상으로 검증 (VI장 3절)
    ok = force or (enough and cand["score"] >= base["score"] and cand["hallucinations"] <= base["hallucinations"])
    result = {"prompt_id": pid, "baseline": base, "candidate": cand, "promoted": ok,
              "note": "" if enough else f"{pid} 에 해당하는 골든셋 {split} 사례가 2건 미만이라 배포할 수 없습니다."}
    if ok:
        target = PROMPT_DIR / "master.md" if pid == "MASTER" else PROMPT_DIR / "l3" / f"{pid}.md"
        ARCHIVE.mkdir(parents=True, exist_ok=True)
        old = parse_prompt(target)
        shutil.copy(target, ARCHIVE / f"{pid}@{old.version}.md")
        text = proposal.read_text(encoding="utf-8")
        text = re.sub(r"^status: proposed$", f"status: active\npromoted: {dt.date.today()}", text, flags=re.M)
        target.write_text(text, encoding="utf-8")
        proposal.unlink()
    return result
