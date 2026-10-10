---
name: crpr-new-l3-prompt
description: CR·PR 의사결정 에이전트에 새 L3 소분류 전문 Prompt 를 추가한다(예: 2230 기업평판, 3110 투자·재무, 4120 산업 Trend 처럼 아직 범용 GEN-0000 을 쓰는 L3, 또는 새로 신설한 L3). 템플릿 작성 → 분류체계 연결 → 골든셋 2건 이상 검증까지 한 번에 진행.
---
# 신규 L3 전문 Prompt 추가

작업 디렉터리: `cr_pr_agent/`. 참고 예시: `prompts/l3/CR-1610.md`.

1. 대상 L3 코드와 이름을 확인한다(`config/taxonomy.json` 의 l3). 새 L3 신설이면 코드 규칙(십 단위, L2 하위)을 지키고 사용자 확인을 받은 뒤 l3 배열에 추가한다. 기존 코드는 삭제하지 않는다.
2. 사용자(도메인 전문가)에게 분석 관점과 이 유형에서 조직장이 늘 묻는 질문을 받는다. 받지 못한 부분은 Master Prompt 의 판단 프레임에서 끌어오되 초안임을 표시한다.
3. `prompts/l3/<접두어>-<L3코드>.md` 를 템플릿대로 만든다:
   ```
   ---
   id: PR-2230
   name: 기업평판(CEO PI)
   version: 1.0
   applies_to: [2230]
   owner: 운영자 + 담당 전문가
   ---
   ## 분석 관점   이 이슈를 「…」로 분석하라.
   ## 집중 질문   5~7개
   ## 핵심 판단   「~이 아니라 ~를 판단하라」
   ## 최종 출력 형식   선택지 집합 또는 최적 조합 중 하나를 추천
   ```
4. `config/taxonomy.json` 해당 l3 의 `prompt` 를 새 ID 로 바꾸고, 필요하면 `keywords` 를 보강한다.
5. 골든셋: 이 L3 의 사례가 dev 2건 이상인지 확인한다. 부족하면 **crpr-golden-curator** sub-agent 로 후보를 만들고, 정답 값은 사용자에게 받는다.
6. 검증: `python cli.py eval --split dev --prompt <새 ID>` 와 `python -m unittest discover -s tests`. 범용 Prompt(GEN-0000) 대비 점수가 낮으면 배포하지 말고 결과를 보고한다.
7. 결과(새 파일, 바꾼 config, 평가 점수)를 보고한다.
