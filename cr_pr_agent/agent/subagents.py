"""Sub-agent 정의 — 각자 좁은 역할 하나, 고정된 시스템 프롬프트, 강제된 출력 스키마를 가진다.

  classifier      (light) Step 2  ISSUE_ID·신뢰도·근거 — 키워드 규칙·과거 사례와 앙상블
  risk panel ×4   (light) Step 3  규제/여론/재무/법무 각 1~5 + 근거, 병렬 실행
  opportunity     (light) Step 3  전략적 기회 1~5 (리스크와 별도 축)
  synthesizer     (heavy) Step 4  Master + Format + L3 Prompt 조립 → 10단계 판단
  critic          (heavy) 검증   원문 대조 환각·추정 표기·추천/액션 구체성 점검
  prompt tuner    (heavy) 피드백 루프  조정 이력 → L3 Prompt 개정안
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from . import schema as S
from .config import Registry, Taxonomy, codebook
from .llm import get_llm, dumps
from .scoring import AREAS

USER_ORDER_NOTE = "아래는 이번 문서에 대한 입력이다. 원문만 사실의 근거로 삼는다."


# ------------------------------------------------------------ 입력 조립
def meta_block(ctx: dict) -> str:
    lines = [f"[문서 메타데이터]",
             f"DOC_ID: {ctx['doc_id']}", f"출처유형: {ctx['source_type']}",
             f"문서제목: {ctx['title']}", f"접수일: {ctx['upload_date']}"]
    if ctx.get("classification"):
        tx: Taxonomy = ctx["taxonomy"]
        cl = ctx["classification"]
        lines.append(f"주 코드: {tx.label(cl['primary_issue_id'])}")
        if cl.get("sub_issue_ids"):
            lines.append("부 코드: " + ", ".join(tx.label(x) for x in cl["sub_issue_ids"]))
    return "\n".join(lines)


def source_block(ctx: dict) -> str:
    return f"[원문 — 인용 근거로 사용]\n<document>\n{ctx['text']}\n</document>"


def history_block(ctx: dict) -> str:
    cases = ctx.get("similar") or []
    if not cases:
        return "[과거 유사 사안 — 같은 L3]\n없음"
    rows = []
    for c in cases:
        rows.append(f"- (과거 사례) {c['DOC_ID']} {c['ISSUE_ID']} 「{c['DOC_TITLE']}」 "
                    f"{c.get('RISK_LEVEL') or ''} {c.get('TOTAL_RISK_SCORE') or ''}점\n"
                    f"  요약: {(c.get('EXECUTIVE_SUMMARY') or '')[:300]}\n"
                    f"  에이전트 추천: {(c.get('AGENT_RECOMMENDATION') or '')[:200]}\n"
                    f"  조직장 결정: {c.get('FINAL_DECISION') or '미결정'} / 교훈: {c.get('LESSONS') or '-'}")
    return "[과거 유사 사안 — 같은 L3, 최대 3건. 인용 시 「과거 사례」라고 명시]\n" + "\n".join(rows)


def open_issues_block(ctx: dict) -> str:
    items = ctx.get("open_issues") or []
    if not items:
        return "[진행 중인 관련 이슈 — Big Deal 탐색용]\n없음"
    return "[진행 중인 관련 이슈 — Big Deal 탐색용]\n" + "\n".join(
        f"- {i['ISSUE_ID']} 「{i['DOC_TITLE']}」 {i.get('RISK_LEVEL') or ''} {i['STATUS']}" for i in items)


# ------------------------------------------------------------ Step 2 분류
_WORD = re.compile(r"[가-힣A-Za-z0-9]+")


def keyword_candidates(text: str, tx: Taxonomy, top: int = 3) -> list[dict]:
    """규칙 엔진: L3 키워드 출현 수 + 세분류 이슈명 단어 겹침."""
    low = text.lower()
    scored = []
    for issue in tx.active_issues():
        l3 = tx.l3[issue["l3"]]
        hits = [k for k in l3.get("keywords", []) if k.lower() in low]
        name_tokens = [w for w in _WORD.findall(issue["name"]) if len(w) >= 2]
        name_hits = sum(1 for w in name_tokens if w.lower() in low)
        score = len(hits) * 2 + name_hits
        if score:
            scored.append({"issue_id": issue["issue_id"], "score": score, "hits": hits})
    scored.sort(key=lambda x: -x["score"])
    return scored[:top]


def classify(ctx: dict, reg: Registry) -> tuple[dict, list]:
    tx: Taxonomy = ctx["taxonomy"]
    kw = keyword_candidates(ctx["text"], tx)
    ctx["keyword_candidates"] = kw
    prompt = reg.sub["classifier"]
    user = [meta_block({**ctx, "classification": None}),
            "[키워드 규칙 엔진 후보]\n" + (dumps(kw) if kw else "없음"),
            source_block(ctx)]
    res = get_llm().run("classify", "light", [prompt.body, "[Taxonomy Master]\n" + tx.master_table()],
                        user, S.Classification, ctx)
    cl = res.obj.model_dump()

    # 앙상블: LLM 판단을 주로 쓰되 규칙 엔진과의 일치 여부로 신뢰도를 보정
    if cl["primary_issue_id"] not in tx.issues:
        cl["new_category_candidate"] = cl["new_category_candidate"] or cl["primary_issue_id"]
        cl["primary_issue_id"] = kw[0]["issue_id"] if kw else tx.active_issues()[0]["issue_id"]
        cl["confidence"] = min(cl["confidence"], 0.5)
    conf = max(0.0, min(1.0, float(cl["confidence"])))
    if kw:
        same_l3 = tx.issues[kw[0]["issue_id"]]["l3"] == tx.issues[cl["primary_issue_id"]]["l3"]
        conf = conf + 0.05 if same_l3 else conf - 0.1
    cl["confidence"] = round(max(0.0, min(1.0, conf)), 2)
    cl["sub_issue_ids"] = [x for x in cl["sub_issue_ids"] if x in tx.issues and x != cl["primary_issue_id"]][:2]
    cl["keyword_candidates"] = kw
    return cl, [("classify", res, prompt.tag)]


# ------------------------------------------------------------ Step 3 패널
def _scale_text(scale: dict) -> str:
    return "\n".join(f"{k} = {v}" for k, v in sorted(scale.items(), key=lambda x: -int(x[0])))


def risk_panel(ctx: dict, reg: Registry) -> tuple[dict, list]:
    cb = codebook()
    llm = get_llm()
    base = reg.sub["risk_panel"]
    user = [meta_block(ctx), open_issues_block(ctx), history_block(ctx), source_block(ctx)]

    def one(area):
        name, desc = AREAS[area]
        sys = base.body.format(area_name=name, area_desc=desc, scale=_scale_text(cb["score_scale"]))
        return area, llm.run(f"panel:{area}", "light", [sys], user, S.AreaScore, {**ctx, "area": area}), base.tag

    def opp():
        p = reg.sub["opportunity_panel"]
        sys = p.body.format(scale=_scale_text(cb["opportunity_scale"]))
        return "SCORE_OPP", llm.run("panel:SCORE_OPP", "light", [sys], user, S.OpportunityScore,
                                    {**ctx, "area": "SCORE_OPP"}), p.tag

    jobs = [lambda a=a: one(a) for a in AREAS] + [opp]
    with ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(lambda f: f(), jobs))
    panel, calls = {}, []
    for area, res, tag in results:
        d = res.obj.model_dump()
        d["score"] = S.clamp_score(d["score"])
        panel[area] = d
        calls.append((f"panel:{area}", res, tag))
    return panel, calls


def panel_block(panel: dict) -> str:
    rows = ["[리스크 패널 결과 — 점수는 확정값이므로 바꾸지 말 것. 근거를 판단에 활용]"]
    for k in list(AREAS) + ["SCORE_OPP"]:
        p = panel[k]
        name = AREAS[k][0] if k in AREAS else "전략적 기회"
        rows.append(f"- {name}({k}) {p['score']}점: {p['summary']}")
        for e in p["evidence"][:3]:
            rows.append(f"    · [{e['kind']}] {e['quote'] or e['reasoning']}")
    return "\n".join(rows)


# ------------------------------------------------------------ Step 4 합성
def synthesize(ctx: dict, reg: Registry, feedback: list[str] | None = None) -> tuple[S.DecisionReport, list]:
    l3 = reg.l3_prompt(ctx["l3_prompt_id"])
    system = [reg.master.body, reg.format.body, l3.body]  # 고정 → L3별 고정 순서 (캐시 효율)
    user = [meta_block(ctx), panel_block(ctx["panel"]), source_block(ctx),
            history_block(ctx), open_issues_block(ctx)]
    if feedback:
        user.append("[검수 피드백 — 아래 문제를 모두 고쳐 10단계 전체를 다시 작성하라]\n" +
                    "\n".join(f"- {f}" for f in feedback))
    res = get_llm().run("synthesize", "heavy", system, user, S.DecisionReport, ctx, max_tokens=64000)
    return res.obj, [("synthesize", res, reg.version_tag(ctx["l3_prompt_id"]))]


# ------------------------------------------------------------ 검증 critic
def critique(ctx: dict, reg: Registry, report: S.DecisionReport) -> tuple[S.CriticReport, list]:
    p = reg.sub["critic"]
    user = [source_block(ctx), history_block(ctx),
            "[검증 대상 초안]\n" + report.model_dump_json(indent=1)]
    res = get_llm().run("critic", "heavy", [p.body], user, S.CriticReport, {**ctx, "report": report})
    return res.obj, [("critic", res, p.tag)]


# ------------------------------------------------------------ 피드백 루프
def propose_revision(prompt_body: str, stats: dict, samples: list[dict], master: str) -> S.PromptRevision:
    system = [master,
              "너는 위 Master Prompt 를 쓰는 에이전트의 L3 전문 Prompt 를 개정하는 Prompt 엔지니어다. "
              "구조(분석 관점 / 집중 질문 5~7개 / 핵심 판단 / 최종 출력 형식)는 유지한다. "
              "조정 이력에서 보이는 체계적 편향만 고치고, 근거 없는 확장은 하지 않는다."]
    user = ["[현재 L3 Prompt]\n" + prompt_body,
            "[월간 조정·결정 통계]\n" + dumps(stats),
            "[조직장·담당자 수정 사례]\n" + dumps(samples)]
    return get_llm().run("prompt_tuner", "heavy", system, user, S.PromptRevision, {"prompt": prompt_body}).obj
