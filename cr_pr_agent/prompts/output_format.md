---
id: FORMAT
version: 1.0
layer: 3
owner: 운영자
---
# 최종 출력 Format (10단계) — JSON 스키마로 강제된다

모든 필드를 빠짐없이 채운다. 각 항목의 의도는 다음과 같다.

① one_line_judgment — 「이 사안은 ○○ 때문에 지금 조직장이 직접 챙겨야 하는(또는 모니터링으로 충분한) 사안이다」 형식의 1문장.
② key_content — key_facts: 회사에 실제로 영향을 주는 사실 3개 이내(각 사실에 원문 근거 인용 quote 필수), core_change: 핵심 변화, company_impact: 매출·ARPU·가입자·CapEx·규제·평판 관점 영향(우선순위 순).
③ real_issue — surface_issue(표면적 이슈) / real_issue(실제 쟁점) / counterpart_intent(정부·국회·경쟁사·언론의 공식 입장 vs 실제 의도) / must_not_miss(놓치면 안 되는 것).
④ Risk/Opportunity — 점수는 별도 리스크 패널이 산출하므로 여기서는 쓰지 않는다. opportunity_note 에 전략적 기회의 내용만 서술.
⑤ scenarios — A 선제 대응 / B 방어적 대응 / C 무대응 각각 effect(효과)와 side_effect(부작용). C의 부작용에는 무대응의 비용을 적는다.
⑥ decision — options: Option A, Option B (각 title, description, pros, cons), recommended: "A" 또는 "B" (반드시 하나), why_now, gain, cost_to_accept, rationale: 손익·정책·여론·법무·전략 관점 각 1문장.
⑦ negotiation_cards — protect(지켜야 할 것) / concede(양보 가능한 것) / demand(요구할 것) / big_deal(다른 정책·사업과 묶을 수 있는 것).
⑧ action_plan — D+1, D+3, D+7 세 행. 각 행: owner(담당 역할), task(할 일), counterpart(만날 사람·기관, 없으면 「내부」), message(전달·요구할 메시지), decision_needed(필요한 의사결정, D+7 필수).
⑨ pr_stance — official_message(공식 메시지 1문장), emphasize(강조할 메시지 2~3개), taboo_words(금기어 2~4개).
⑩ ceo_qa — CEO 예상 질문 정확히 6개, 각 answer는 30초 이내(약 150자 이내).

또한 assumptions 에는 본문에서 「추정」·「확인 필요」로 표시한 항목을 모아 적고, missing_numbers 에는 「OOO」로 둔 수치와 산출 담당을 적는다.
