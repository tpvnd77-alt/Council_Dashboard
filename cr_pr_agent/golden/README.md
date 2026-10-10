# 골든셋 (Golden Set)

조직장이 직접 작성한 「정답 판단」이 붙은 평가용 문서 모음이다. Prompt 개정은 이 골든셋 재평가에서 기존 점수 이상일 때만 배포된다.

- `split: dev` — 튜닝·개정 비교용 (약 70%)
- `split: test` — 최종 평가용 (약 30%). **Prompt 튜닝 피드백에 절대 사용하지 않는다.**
- `provisional: true` — 기대값이 임시값인 사례. 조직장 정답으로 교체 후 이 표시를 지운다.
- `candidates/` — 조직장이 「기각」·「수정 채택」한 운영 건이 자동으로 쌓인다. 정답을 채워 이 폴더 위로 옮기면 골든셋이 된다.

## 사례 파일 형식
```json
{
  "id": "G004-CR1311", "split": "dev",
  "title": "...", "source_type": "정부부처", "text": "원문 전체",
  "expected": {
    "issue_id": "CR-1311",
    "scores": {"SCORE_REG": 4, "SCORE_FIN": 3, "SCORE_PR": 3, "SCORE_LEG": 4}, "opp": 2,
    "key_fact_keywords": [["핵심사실1 키워드", "동의어"], ["핵심사실2"]],
    "recommendation_keywords": ["추천안에 들어가야 할 표현"]
  }
}
```
L3 13종 × 3~5건(총 40~60건)이 목표다. 현재 G001·G002 는 워크북 샘플 2건의 재구성본이다.
