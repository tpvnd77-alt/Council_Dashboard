"""오프라인 모의 LLM — API 자격 증명 없이 파이프라인·화면·테스트를 돌리기 위한 규칙 기반 대역.

판단 품질은 실제 모델과 비교할 수 없으며, 모든 산출물에 「[오프라인 모의 분석]」이 붙는다.
원문 문장만 인용하고 수치를 만들지 않으므로 검증 루프를 통과한다.
"""
from __future__ import annotations

import re
import time

from . import schema as S
from .llm import CallResult

_SENT = re.compile(r"(?<=[.!?。다])\s+|\n+")

AREA_WORDS = {
    "SCORE_REG": ["의무", "규제", "제재", "인가", "법안", "개정", "고시", "시행", "의무화", "도입", "검토"],
    "SCORE_PR": ["비판", "여론", "소비자", "국민", "언론", "보도", "불만", "논란", "부담"],
    "SCORE_FIN": ["매출", "요금", "ARPU", "투자", "과징금", "비용", "감소", "손실", "인하", "억", "조원"],
    "SCORE_LEG": ["위법", "소송", "항소", "처분", "고발", "판결", "담합", "위반"],
    "SCORE_OPP": ["진흥", "지원", "세액공제", "허용", "기회", "투자", "육성", "특별법", "확대", "성과"],
}
TAG = "[오프라인 모의 분석] "


def sentences(text: str) -> list[str]:
    out = []
    for s in _SENT.split(text):
        s = s.strip(" -·•\t")
        if 15 <= len(s) <= 200 and not s.startswith("[p.") and "|" not in s:
            out.append(s)
    return out


def _rank(text: str, words: list[str]) -> list[str]:
    ss = sentences(text)
    return sorted(ss, key=lambda s: -sum(w in s for w in words))


class OfflineLLM:
    offline = True

    def run(self, task, role, system, user, schema, ctx=None, max_tokens=0) -> CallResult:
        ctx = ctx or {}
        t0 = time.time()
        fn = getattr(self, "_" + task.split(":")[0])
        obj = fn(ctx)
        return CallResult(obj=schema.model_validate(obj.model_dump()), model="offline-mock",
                          usage={}, seconds=round(time.time() - t0, 3))

    # ---------------------------------------------------------- tasks
    def _classify(self, ctx):
        kw = ctx.get("keyword_candidates") or []
        tx = ctx["taxonomy"]
        if kw:
            top = kw[0]
            conf = min(0.95, 0.55 + 0.1 * top["score"])
            ev = [s for s in sentences(ctx["text"]) if any(h in s for h in top["hits"])][:2]
            return S.Classification(primary_issue_id=top["issue_id"],
                                    sub_issue_ids=[k["issue_id"] for k in kw[1:3] if k["score"] >= 3],
                                    confidence=round(conf, 2), evidence=ev, new_category_candidate="")
        return S.Classification(primary_issue_id=tx.active_issues()[0]["issue_id"], sub_issue_ids=[],
                                confidence=0.3, evidence=[], new_category_candidate="미분류 — 담당자 확인 필요")

    def _panel(self, ctx):
        area = ctx["area"]
        words = AREA_WORDS[area]
        text = ctx["text"]
        hits = sum(text.count(w) for w in words)
        score = 1 if hits == 0 else 2 if hits <= 2 else 3 if hits <= 5 else 4 if hits <= 9 else 5
        top = [s for s in _rank(text, words) if any(w in s for w in words)][:2]
        ev = [S.Evidence(kind="원문", quote=s, reasoning="관련 표현 출현") for s in top] or \
             [S.Evidence(kind="추정", quote="", reasoning="원문에 직접 근거 없음 — 확인 필요")]
        summary = f"{TAG}관련 표현 {hits}회 출현 기준 {score}점 (확인 필요)"
        if area == "SCORE_OPP":
            return S.OpportunityScore(score=score, summary=summary, evidence=ev, big_deal_candidates=[])
        return S.AreaScore(score=score, summary=summary, evidence=ev, needed_data=["영향 금액 OOO — 재무 담당 산출"])

    def _synthesize(self, ctx):
        text = ctx["text"]
        facts = _rank(text, sum(AREA_WORDS.values(), []))[:3] or [text.strip()[:120]]
        title = ctx["title"]
        cp = {"정부부처": "소관 부처 담당 과장", "국회": "소관 상임위 의원실 보좌관", "경쟁사": "업계 협의체",
              "언론": "출입기자", "사내보고서": "관련 임원"}.get(ctx["source_type"], "관계 기관")
        return S.DecisionReport(
            one_line_judgment=f"{TAG}「{title}」은(는) 리스크 패널 결과에 따라 조직장 확인이 필요한 사안이다(확인 필요).",
            key_content=S.KeyContent(
                key_facts=[S.KeyFact(fact=f[:120], quote=f) for f in facts],
                core_change="확인 필요 — 원문의 핵심 변화를 담당자가 보완",
                company_impact=["추정: 규제·재무 영향은 리스크 패널 점수 참조", "확인 필요: 매출 영향 OOO"]),
            real_issue=S.RealIssue(surface_issue=f"{title}",
                                   real_issue="추정: 규제 선례화 여부가 실제 쟁점일 가능성",
                                   counterpart_intent="확인 필요: 상대방의 공식 입장과 실제 의도 구분 필요",
                                   must_not_miss="추정: 경쟁사 선제 대응 시 프레임 고착"),
            opportunity_note="추정: 제도 설계 참여 시 협상 지렛대 확보 가능(확인 필요)",
            scenarios=[S.Scenario(name="A 선제 대응", effect="추정: 프레임 선점", side_effect="추정: 비용 선부담"),
                       S.Scenario(name="B 방어적 대응", effect="추정: 비용 최소화", side_effect="추정: 수세적 프레임"),
                       S.Scenario(name="C 무대응", effect="추정: 단기 비용 없음",
                                  side_effect="추정: 무대응 비용 OOO — 경쟁사·정부 프레임에 갇힘")],
            decision=S.Decision(
                options=[S.Option(key="A", title="조건부 선제 대응", description="추정: 대안을 먼저 제시",
                                  pros=["프레임 선점"], cons=["비용 선부담"]),
                         S.Option(key="B", title="방어적 관망", description="추정: 업계 공동 대응",
                                  pros=["비용 최소화"], cons=["수세적 프레임"])],
                recommended="A", recommended_summary="조건부 선제 대응으로 대안을 먼저 제시한다(추정).",
                why_now="추정: 결정 전 의견 수렴 단계에서 영향력이 가장 크다",
                gain="추정: 협상 주도권", cost_to_accept="추정: 비용 OOO",
                rationale=S.Rationale(pnl="추정: 손익 영향 OOO", policy="추정: 정책 설계 참여",
                                      public_opinion="추정: 긍정 프레임", legal="추정: 법적 리스크 낮음",
                                      strategy="추정: 협상 지렛대 확보")),
            negotiation_cards=S.NegotiationCards(protect=["핵심 수익 구조(확인 필요)"], concede=["적용 시기 조정(추정)"],
                                                 demand=["단계적 시행(추정)"], big_deal=["진행 중 이슈와 연계 검토(추정)"]),
            action_plan=[S.ActionItem(when="D+1", owner="CR 담당", task="영향 금액 OOO 산출 요청", counterpart="내부 재무팀",
                                      message="영향 시뮬레이션 요청", decision_needed=""),
                         S.ActionItem(when="D+3", owner="CR 팀장", task="비공식 의견 청취", counterpart=cp,
                                      message="당사 대안 방향 설명", decision_needed=""),
                         S.ActionItem(when="D+7", owner="조직장", task="대응 방향 확정", counterpart="담당 임원",
                                      message="추천안 보고", decision_needed="Option A/B 확정")],
            pr_stance=S.PRStance(official_message="관련 내용을 면밀히 검토하고 있습니다.",
                                 emphasize=["국민 편익", "책임 있는 대응"], taboo_words=["수익성 악화", "과도한 개입"]),
            ceo_qa=[S.QA(question=q, answer="확인 필요 — 담당자 보완 예정입니다.") for q in
                    ["그래서 어떻게 하자는 건가?", "무대응하면 무엇을 잃나?", "경쟁사는 어떻게 움직이나?",
                     "정부와 거래 가능한 것은?", "비용은 얼마인가?", "언제까지 결정해야 하나?"]],
            assumptions=["오프라인 모의 분석 — 모든 판단은 확인 필요"],
            missing_numbers=["영향 금액 OOO — 재무 담당"],
        )

    def _critic(self, ctx):
        return S.CriticReport(passed=True, issues=[])

    def _prompt_tuner(self, ctx):
        return S.PromptRevision(diagnosis=f"{TAG}통계 기반 자동 개정은 실제 모델에서만 수행됩니다.",
                                revised_prompt_markdown=ctx.get("prompt", ""), change_summary=[])
