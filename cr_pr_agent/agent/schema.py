"""구조화 출력 스키마 — LLM 응답을 이 모델로 강제하고 검증한다.

필드 이름은 Prompt 의 Layer 3(output_format.md) 과 1:1 로 맞춘다.
점수(1~5)처럼 범위가 있는 값은 스키마에 제약을 넣지 않고 coerce 단계에서
잘라낸다. 구조화 출력이 지원하지 않는 제약이 섞여도 호출이 깨지지 않게 하기 위해서다.
"""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


# ---------- Step 2 : 분류 sub-agent ----------
class Classification(BaseModel):
    primary_issue_id: str = Field(description="주 코드 ISSUE_ID, 예: CR-1111")
    sub_issue_ids: List[str] = Field(description="부 코드 최대 2개")
    confidence: float = Field(description="0~1")
    evidence: List[str] = Field(description="원문 인용 최대 2개")
    new_category_candidate: str = Field(description="신규 분류 후보명, 없으면 빈 문자열")


# ---------- Step 3 : 리스크/기회 패널 sub-agent ----------
class Evidence(BaseModel):
    kind: Literal["원문", "추정"]
    quote: str = Field(description="원문 문장 그대로. 추정이면 빈 문자열")
    reasoning: str


class AreaScore(BaseModel):
    score: int = Field(description="1~5 정수")
    summary: str = Field(description="1~2문장 판단")
    evidence: List[Evidence]
    needed_data: List[str] = Field(description="점수 확정에 필요한 미확보 수치·자료")


class OpportunityScore(BaseModel):
    score: int = Field(description="1~5 정수")
    summary: str
    evidence: List[Evidence]
    big_deal_candidates: List[str] = Field(description="묶어서 협상 가능한 진행 중 ISSUE_ID")


# ---------- Step 4 : 의사결정 합성 (10단계) ----------
class KeyFact(BaseModel):
    fact: str
    quote: str = Field(description="근거가 된 원문 문장 그대로")


class KeyContent(BaseModel):
    key_facts: List[KeyFact] = Field(description="3개 이내")
    core_change: str
    company_impact: List[str] = Field(description="우선순위 순")


class RealIssue(BaseModel):
    surface_issue: str
    real_issue: str
    counterpart_intent: str
    must_not_miss: str


class Scenario(BaseModel):
    name: Literal["A 선제 대응", "B 방어적 대응", "C 무대응"]
    effect: str
    side_effect: str


class Option(BaseModel):
    key: Literal["A", "B"]
    title: str
    description: str
    pros: List[str]
    cons: List[str]


class Rationale(BaseModel):
    pnl: str = Field(description="손익")
    policy: str = Field(description="정책")
    public_opinion: str = Field(description="여론")
    legal: str = Field(description="법무")
    strategy: str = Field(description="전략")


class Decision(BaseModel):
    options: List[Option]
    recommended: Literal["A", "B"]
    recommended_summary: str = Field(description="추천안 한 문장")
    why_now: str
    gain: str
    cost_to_accept: str
    rationale: Rationale


class NegotiationCards(BaseModel):
    protect: List[str]
    concede: List[str]
    demand: List[str]
    big_deal: List[str]


class ActionItem(BaseModel):
    when: Literal["D+1", "D+3", "D+7"]
    owner: str
    task: str
    counterpart: str
    message: str
    decision_needed: str


class PRStance(BaseModel):
    official_message: str
    emphasize: List[str]
    taboo_words: List[str]


class QA(BaseModel):
    question: str
    answer: str


class DecisionReport(BaseModel):
    one_line_judgment: str
    key_content: KeyContent
    real_issue: RealIssue
    opportunity_note: str
    scenarios: List[Scenario]
    decision: Decision
    negotiation_cards: NegotiationCards
    action_plan: List[ActionItem]
    pr_stance: PRStance
    ceo_qa: List[QA]
    assumptions: List[str]
    missing_numbers: List[str]


# ---------- 검증 critic sub-agent ----------
class CriticIssue(BaseModel):
    field: str
    type: Literal["hallucination", "unmarked_inference", "invented_number",
                  "weak_decision", "vague_action", "intent_missing"]
    problem: str
    fix_hint: str


class CriticReport(BaseModel):
    passed: bool
    issues: List[CriticIssue]


# ---------- 피드백 루프: Prompt 개정 제안 ----------
class PromptRevision(BaseModel):
    diagnosis: str = Field(description="수정 패턴에서 읽히는 체계적 편향")
    revised_prompt_markdown: str = Field(description="frontmatter 를 제외한 개정 Prompt 본문 전체")
    change_summary: List[str]


def clamp_score(v) -> int:
    try:
        v = int(round(float(v)))
    except (TypeError, ValueError):
        return 3
    return max(1, min(5, v))
