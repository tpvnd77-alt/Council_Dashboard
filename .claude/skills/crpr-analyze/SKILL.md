---
name: crpr-analyze
description: 정부·국회·언론·경쟁사·사내 문서 하나를 CR·PR 의사결정 에이전트로 분석해 조직장 관점 한줄 판단·추천안·Action Plan 을 받는다. 사용자가 공문·기사·법안·국감 자료 파일이나 본문을 주며 "분석해 줘", "조직장 보고서 만들어 줘", "어떻게 대응할지" 를 물을 때 사용.
---
# 문서 분석 (Step 1~5)

작업 디렉터리: `cr_pr_agent/`

1. 출처유형을 정한다: 정부부처 / 국회 / 경쟁사 / 언론 / 사내보고서. 불분명하면 사용자에게 묻는다.
   - 본문만 받았으면 scratchpad 에 `.txt` 로 저장한다.
2. 실행: `python cli.py analyze <파일> --source <출처유형> --title "<제목>"`
3. 결과의 `stage` 에 따라:
   - `gate1` — 분류 신뢰도 부족. `CLASSIFICATION_JSON` 의 후보·근거를 사용자에게 보여 주고, 사용자가 고른 ISSUE_ID 로
     `python cli.py confirm <DOC_ID> <ISSUE_ID> --actor <사용자> --reason "<사유>"` 를 실행한다. ISSUE_ID 를 대신 고르지 않는다(게이트 1은 사람 몫).
   - `review` — 완료. 아래 4로.
   - `error` — `ERROR` 를 읽고 원인(자격 증명, 형식, 네트워크)을 설명한 뒤 `python cli.py rerun <DOC_ID>` 로 해당 단계만 다시 돌린다.
4. 사용자에게 돌려줄 것: 리스크 등급·종합 점수·기회 점수, 조직장 한줄 판단, ★추천안, D+1 액션, 품질 루프 수렴 여부(미수렴이면 남은 문제).
   전체 보고서는 웹 화면(`python cli.py serve` → `#/doc/<DOC_ID>`) 또는 `/api/records/<DOC_ID>/report.html` 로 안내한다.
5. 검수(점수 조정)와 조직장 판단(게이트 2)은 사람이 웹 화면에서 한다. 대신 기록하지 않는다.

`status` 가 오프라인 모의 모드면 결과가 규칙 기반 모의 분석이라는 점을 반드시 함께 알린다.
