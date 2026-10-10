---
name: crpr-monthly-feedback
description: CR·PR 의사결정 에이전트의 월간 피드백 루프 — 조직장·담당자 수정 이력을 집계해 점수 편향·채택률·분류 정확도를 점검하고, 편향이 몰린 L3 Prompt 를 sub-agent 로 개정한 뒤 골든셋 게이트를 통과한 것만 배포한다. 월초 정기 점검이나 "Prompt 개선", "채택률 점검" 요청에 사용.
---
# 월간 피드백 루프

작업 디렉터리: `cr_pr_agent/`. 정기 실행 예: 매월 1일 `/crpr-monthly-feedback`.

1. 집계: `python cli.py feedback --since <지난달 1일>` → `data/feedback/feedback_YYYY-MM.md` 를 읽는다.
2. KPI 를 목표와 함께 표로 보고한다: 채택률(70%), 분류 정확도 L3(90%), 점수 ±1 일치도(85%), 초안 생성 시간(30분), 환각(0건).
3. `targets` 가 비어 있으면 여기서 끝낸다(개정 없음도 정상 결과).
4. 개정 대상마다 **crpr-prompt-tuner** sub-agent 를 하나씩 띄운다(서로 다른 Prompt 면 병렬). 각 sub-agent 에 Prompt ID 와 사유를 넘긴다.
   - `revise_master` 가 true 면 Master 개정은 sub-agent 에 맡기지 말고 사용자(조직장 승인 사항)에게 진단과 함께 제안만 한다.
5. 게이트 결과를 모은다. 배포가 보류된 이유가 "골든셋 2건 미만"이면 **crpr-golden-curator** sub-agent 로 해당 L3 의 골든셋 공백을 점검하게 하고, 필요한 정답 질문 목록을 사용자에게 전달한다.
6. 분기 첫 달이면 **crpr-taxonomy-curator** sub-agent 로 분류체계 검토도 함께 돌린다.
7. 최종 보고: KPI 표, 배포된 개정(baseline → candidate 점수), 보류된 개정과 이유, 사람에게 필요한 결정.

배포 후 1개월 뒤 채택률을 다시 보는 것이 변경 절차의 마지막 단계다 — 다음 달 실행에서 지난달 배포한 Prompt 의 채택률 변화를 함께 보고한다(Decision Log 의 PROMPT_VERSION 으로 구분).
