"""자동 구조 검증 + 환각 방지 장치 (XI장 4절, XII장 3절) — LLM 없이 매 건 실시간으로 돈다.

errors   : 고쳐야 배포 가능한 문제 → 수정 루프의 피드백으로 들어간다
warnings : 담당자 검수 때 확인할 문제
metrics  : 품질 지표(⑥ Action 구체성 등)
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .schema import DecisionReport

_NORM = re.compile(r"[\s\"'“”‘’「」『』·,.()\[\]\-–—:;]+")
_NUM = re.compile(r"\d[\d,.]*\s*(?:조|억|만|천|%|퍼센트|원|명|건|MHz|GHz)")
_HEDGE = ("추정", "확인 필요", "과거 사례")
_WEAK = ("검토가 필요", "검토 필요", "추가 검토", "신중한 검토", "지켜볼 필요")


def _n(s: str) -> str:
    return _NORM.sub("", s or "").lower()


def quote_found(quote: str, source_norm: str) -> bool:
    q = _n(quote)
    if not q:
        return False
    if q in source_norm:
        return True
    if len(q) < 12:
        return False
    m = SequenceMatcher(None, source_norm, q, autojunk=False).find_longest_match(0, len(source_norm), 0, len(q))
    return m.size / len(q) >= 0.8


def _numbers(s: str) -> set[str]:
    return {re.sub(r"[\s,]", "", m.group(0)) for m in _NUM.finditer(s or "")}


def _strings(obj, path=""):
    """보고서의 모든 문자열을 (경로, 값) 으로 펼친다."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def validate(report: DecisionReport, source: str, panel: dict, history_text: str = "") -> dict:
    errors, warnings = [], []
    r = report
    src_n = _n(source)

    # ① 한줄 판단
    if not r.one_line_judgment.strip():
        errors.append("① 조직장 한줄 판단이 비어 있다.")
    # ② 핵심 사실 3개 이내 + 원문 인용
    facts = r.key_content.key_facts
    if not facts:
        errors.append("② 핵심 사실이 없다.")
    if len(facts) > 3:
        errors.append(f"② 핵심 사실은 3개 이내여야 한다(현재 {len(facts)}개).")
    for i, f in enumerate(facts):
        if not quote_found(f.quote, src_n):
            errors.append(f"② key_facts[{i}] 의 인용문이 원문에서 확인되지 않는다: 「{f.quote[:60]}」 — 원문 문장을 그대로 인용하라.")
    # ③ 진짜 쟁점
    ri = r.real_issue
    for k, label in (("surface_issue", "표면적 이슈"), ("real_issue", "실제 쟁점"),
                     ("counterpart_intent", "상대방 의도"), ("must_not_miss", "놓치면 안 되는 것")):
        if not getattr(ri, k).strip():
            errors.append(f"③ {label}가 비어 있다.")
    # ⑤ 시나리오 A/B/C
    names = {s.name for s in r.scenarios}
    if names != {"A 선제 대응", "B 방어적 대응", "C 무대응"}:
        errors.append("⑤ 시나리오는 A 선제 대응 / B 방어적 대응 / C 무대응 세 가지가 모두 있어야 한다.")
    # ⑥ Option A/B + 하나의 추천
    keys = sorted(o.key for o in r.decision.options)
    if keys != ["A", "B"]:
        errors.append("⑥ Option A 와 Option B 를 하나씩 제시해야 한다.")
    if any(w in r.decision.recommended_summary for w in _WEAK):
        errors.append("⑥ 추천안이 「검토 필요」로 끝난다 — 하나를 명확히 추천하라.")
    ra = r.decision.rationale
    if not all(x.strip() for x in (ra.pnl, ra.policy, ra.public_opinion, ra.legal, ra.strategy)):
        errors.append("⑥ 추천 이유를 손익·정책·여론·법무·전략 다섯 관점으로 모두 설명하라.")
    # ⑦ 협상 카드
    nc = r.negotiation_cards
    if not (nc.protect and nc.concede and nc.demand):
        errors.append("⑦ 협상 카드의 지킬 것·양보할 것·요구할 것을 모두 채워라.")
    # ⑧ Action Plan D+1/3/7
    whens = [a.when for a in r.action_plan]
    concrete = 0
    for need in ("D+1", "D+3", "D+7"):
        if need not in whens:
            errors.append(f"⑧ Action Plan 에 {need} 행이 없다.")
    for a in r.action_plan:
        filled = all(x.strip() for x in (a.owner, a.task, a.counterpart, a.message))
        if filled:
            concrete += 1
        else:
            errors.append(f"⑧ {a.when} 행의 담당·할 일·대상·메시지 중 빈 칸이 있다.")
        if a.when == "D+7" and not a.decision_needed.strip():
            errors.append("⑧ D+7 행에는 필요한 의사결정을 적어야 한다.")
    # ⑨ PR Stance
    if not r.pr_stance.official_message.strip():
        errors.append("⑨ 공식 메시지가 비어 있다.")
    if not 1 <= len(r.pr_stance.taboo_words) <= 6:
        warnings.append("⑨ 금기어는 2~4개를 권장한다.")
    # ⑩ CEO 예상 질문 6개, 30초(약 200자) 이내
    if len(r.ceo_qa) != 6:
        errors.append(f"⑩ CEO 예상 질문은 정확히 6개여야 한다(현재 {len(r.ceo_qa)}개).")
    for i, qa in enumerate(r.ceo_qa):
        if len(qa.answer) > 220:
            warnings.append(f"⑩ {i+1}번 답변이 30초 분량을 넘는다({len(qa.answer)}자).")

    # 수치 플레이스홀더: 원문·과거 사례에 없는 숫자는 OOO 여야 한다
    allowed = _numbers(source) | _numbers(history_text)
    for path, s in _strings(r.model_dump()):
        for num in _numbers(s) - allowed:
            if any(h in s for h in _HEDGE):
                warnings.append(f"수치 {num} ({path}) — 원문에 없는 수치. 추정 표기는 있으나 출처를 확인하라.")
            else:
                errors.append(f"수치 {num} ({path}) 가 원문에 없다 — 「OOO」로 바꾸고 D+1 액션에 산출 담당을 지정하라.")

    # 리스크 패널 근거 인용 확인 (원문 근거 강제)
    for area, p in (panel or {}).items():
        for e in p.get("evidence", []):
            if e["kind"] == "원문" and e["quote"] and not quote_found(e["quote"], src_n):
                warnings.append(f"리스크 패널 {area} 의 원문 인용이 확인되지 않는다: 「{e['quote'][:50]}」")

    n_actions = max(len(r.action_plan), 1)
    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "action_concreteness": round(concrete / n_actions, 2),
            "facts_quoted": sum(quote_found(f.quote, src_n) for f in facts),
            "facts_total": len(facts),
            "has_recommendation": r.decision.recommended in ("A", "B"),
        },
    }
