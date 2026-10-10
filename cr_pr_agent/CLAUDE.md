# cr_pr_agent — 작업 규칙

조직장 관점 CR·PR 의사결정 에이전트. 구조와 실행법은 README.md.

- 판단 기준은 코드가 아니라 파일에 있다: `config/taxonomy.json`, `config/codebook.json`, `prompts/`. 기준을 바꾸는 작업이면 코드보다 이 파일들을 먼저 본다.
- 종합 점수·등급·보고 Level 은 `agent/scoring.py` 수식으로만 계산한다. LLM 이 점수를 합산하게 만들지 않는다.
- 운영 중인 `prompts/l3/*.md`, `prompts/master.md` 를 직접 고치지 않는다. 개정은 `prompts/proposals/` → `python cli.py promote` 골든셋 게이트를 거친다(crpr-prompt-tuner).
- 골든셋 `split: test` 내용을 Prompt 에 넣지 않는다. 골든셋 정답 값을 지어내지 않는다.
- 분류 코드는 삭제하지 않고 deprecated 로만 바꾼다.
- 게이트 1(분류 확정)·게이트 2(조직장 판단)는 사람이 한다. 에이전트가 대신 기록하지 않는다.
- 변경 후: `python -m unittest discover -s tests` (오프라인, API 키 불필요).
