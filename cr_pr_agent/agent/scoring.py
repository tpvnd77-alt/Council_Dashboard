"""Step 3 리스크 스코어링 — LLM 이 아니라 시스템 수식으로 계산한다 (재현성).

TOTAL_RISK_SCORE = (0.35×REG + 0.25×PR + 0.25×FIN + 0.15×LEG) ÷ 5 × 100
가중치·등급 구간·보고 Level 은 코드북에서 읽는다.
"""
from __future__ import annotations

import datetime as dt

from .config import codebook

AREAS = {
    "SCORE_REG": ("규제", "규제·인가·제재 영향도 — 인가 조건·제재 수위·향후 규제 선례가 되는가"),
    "SCORE_PR": ("여론", "언론 비판·불매·이미지 타격 — 지배적 언론 프레임, 소비자 후생 프레임에 갇히는가"),
    "SCORE_FIN": ("재무", "CapEx·매출·과징금 영향 — ARPU·가입자·투자비·과징금 규모"),
    "SCORE_LEG": ("법무", "위법성 및 소송 패소 가능성 — 조사·처분·소송 단계별 방어 가능성"),
}


def total_score(scores: dict, cb: dict | None = None) -> float:
    cb = cb or codebook()
    w = cb["weights"]
    s = sum(w[k] * int(scores[k]) for k in w)
    return round(s / 5 * 100, 1)


def risk_level(total: float, cb: dict | None = None) -> dict:
    cb = cb or codebook()
    for lv in sorted(cb["levels"], key=lambda x: -x["min"]):
        if total >= lv["min"]:
            return lv
    return cb["levels"][-1]


def report_level(level: str, opp: int, cb: dict | None = None) -> str:
    """VII장 5절 매트릭스: 기회 점수 ≥ 4 이면 기본 보고 Level 을 한 단계 상향."""
    cb = cb or codebook()
    order = cb["report_levels"]  # 높은 Level 부터
    base = next(lv["report"] for lv in cb["levels"] if lv["level"] == level)
    idx = order.index(base)
    if opp >= cb["opportunity_uplift_threshold"] and idx > 0:
        idx -= 1
    return order[idx]


def matrix_note(level: str, opp: int) -> str:
    hi = level in ("CRITICAL", "HIGH")
    if opp >= 4:
        return "빅딜 사안 — 조직장 직접, CEO 보고 검토" if hi else (
            "임원 전결로 상향 — 선제 대응" if level == "MEDIUM" else "임원 전결로 상향 — 제도 설계 참여")
    if opp == 3:
        return "방어 + 거래 카드 탐색" if hi else (
            "부서 간 조율" if level == "MEDIUM" else "단순 모니터링 + 기회 메모")
    return "방어 집중 사안 — 기본 Level 유지" if hi else (
        "부서 간 조율" if level == "MEDIUM" else "단순 모니터링")


def evaluate(scores: dict, opp: int, upload_date: dt.date | None = None) -> dict:
    cb = codebook()
    total = total_score(scores, cb)
    lv = risk_level(total, cb)
    upload_date = upload_date or dt.date.today()
    return {
        "TOTAL_RISK_SCORE": total,
        "RISK_LEVEL": lv["level"],
        "RISK_GRADE": lv["grade"],
        "DECISION_TYPE": report_level(lv["level"], opp, cb),
        "MATRIX_NOTE": matrix_note(lv["level"], opp),
        "PRINCIPLE": lv["principle"],
        "DUE_DATE": (upload_date + dt.timedelta(days=lv["due_days"])).isoformat(),
    }


def d_day(due_date: str | None, today: dt.date | None = None) -> int | None:
    """D_DAY = DUE_DATE − 오늘 (부록 A #10). 음수면 기한 경과."""
    if not due_date:
        return None
    today = today or dt.date.today()
    return (dt.date.fromisoformat(due_date[:10]) - today).days
