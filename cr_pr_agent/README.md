# 조직장 관점 CR·PR 의사결정 에이전트

정부·국회·언론·경쟁사·사내 문서를 받아 **Document → 조직장 관점 해석 → Risk/Opportunity → Scenario → Decision → Action** 으로 바꾸고,
원페이지 의사결정 보고서와 D+1/3/7 실행 계획, Decision Log 를 만든다. 「CR·PR 의사결정 에이전트 구축 종합 기획서 v1.0」의 구현이다.

## 빠른 시작
```bash
cd cr_pr_agent
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # 없으면 오프라인 모의 모드(규칙 기반)로 화면·흐름을 시험할 수 있다
python cli.py serve                 # http://localhost:8787   (Windows: 실행.bat)
```
CLI 만으로도 쓸 수 있다: `python cli.py analyze 공문.pdf --source 정부부처` (전체 명령은 `python cli.py -h`).

## 처리 흐름
| 단계 | 하는 일 | 구현 |
|---|---|---|
| Step 1 수집·정규화 | PDF·HWPX·HWP·DOCX·HTML·TXT 추출(표 구조 유지), 개인정보 마스킹, DOC_ID 발번 | `agent/ingest.py` |
| Step 2 분류 | 키워드 규칙 + **분류 sub-agent** 앙상블 → ISSUE_ID·부 코드·신뢰도·근거 | `subagents.classify` |
| 🧑 게이트 1 | 신뢰도 < 0.7 또는 신규 분류 후보 → 담당자 분류 확정 | 웹 화면 / `cli.py confirm` |
| Step 3 리스크 | **리스크 패널 sub-agent 4종(규제·여론·재무·법무) + 기회 1종 병렬**, 근거는 원문 인용 또는 「추정」. 합산·등급·보고 Level 은 시스템 수식 | `subagents.risk_panel`, `scoring.py` |
| Step 4 의사결정 | Master + Format + L3 Prompt 조립 → **합성 sub-agent** 가 10단계 JSON 생성 ⟲ **품질 루프** | `pipeline.quality_loop` |
| Step 5 전달 | Decision Log 기록, 원페이지 보고서(HTML/Word), 운영 워크북(엑셀) | `render.py`, `export_xlsx.py` |
| 🧑 담당자 검수 | 점수 보정(전·후 값과 사유 저장), Action 담당 실명 지정 | 웹 화면 |
| 🧑 게이트 2 | 조직장 승인 / 수정 채택 / 기각 + 사유, 보고 Level 확정 → 배포 대상 안내 | 웹 화면 |

## 루프 엔지니어링 — 세 겹의 루프
1. **건별 품질 루프 (초 단위)** — 생성 → 결정론 검증(10단계 누락, 핵심 사실 원문 인용 대조, 원문에 없는 수치, D+1/3/7 구체성) → 통과하면 **critic sub-agent** 가 환각·추정 미표기·약한 추천을 점검 → 지적 사항을 피드백으로 다시 생성. 최대 `CRPR_MAX_REVISIONS`(기본 2)회, 미수렴이면 남은 문제를 표시해 검수로 넘긴다.
2. **일일 운영 루프** — `python cli.py daily`: `inbox/` 문서 자동 접수·분석, D-Day(3일 전·당일·경과)·게이트 대기 알림, 운영 워크북 갱신. Windows 작업 스케줄러(`crpr_daily.bat`) 또는 Claude Code `/loop 1d /crpr-daily-ops`.
3. **월간 학습 루프** — `python cli.py feedback --propose`: 조정 이력에서 L3 별 점수 편향(평균 ±0.75 이상)·기각률(30% 이상)을 찾아 개정 대상을 정하고, **prompt tuner sub-agent** 가 개정안을 `prompts/proposals/` 에 쓴다. `python cli.py promote <개정안>` 은 골든셋 dev 재평가에서 **기존 점수 이상·환각 증가 없음·사례 2건 이상**일 때만 배포하고 구버전을 `prompts/archive/` 로 옮긴다. 기각·수정 채택 건은 `golden/candidates/` 에 자동으로 쌓여 골든셋 후보가 된다.

## 서브 에이전트와 스킬
**서비스 안의 sub-agent** (각자 고정 프롬프트 + 강제 출력 스키마, `prompts/subagents/`)

| sub-agent | 모델 | 역할 |
|---|---|---|
| classifier | light (`claude-sonnet-5-5`) | 분류·신뢰도·근거 |
| risk panel ×4, opportunity | light | 영역별 1~5점 + 원문 근거, 병렬 실행 |
| synthesizer | heavy (`claude-opus-5-5`) | 10단계 판단 |
| critic | heavy | 원문 대조 검증 |
| prompt tuner | heavy | 피드백 기반 Prompt 개정안 |

**Claude Code 운영 도구** (저장소 루트 `.claude/`)

| 종류 | 이름 | 쓰임 |
|---|---|---|
| 스킬 | `/crpr-analyze` | 문서 하나 분석, 게이트 1 안내 |
| 스킬 | `/crpr-daily-ops` | 일일 루프 실행·요약 (`/loop 1d /crpr-daily-ops`) |
| 스킬 | `/crpr-monthly-feedback` | 월간 루프: 집계 → tuner sub-agent 병렬 → 골든셋 게이트 → 보고 |
| 스킬 | `/crpr-new-l3-prompt` | 새 L3 전문 Prompt 추가(템플릿 → 분류 연결 → 골든셋 검증) |
| sub-agent | `crpr-prompt-tuner` | L3/Master 개정안 작성 후 promote 게이트 실행 |
| sub-agent | `crpr-golden-curator` | 골든셋 커버리지 점검, 후보 → 사례 전환(정답은 사람에게 받음) |
| sub-agent | `crpr-taxonomy-curator` | 분기 분류체계 검토·제안 |
| sub-agent | `crpr-report-reviewer` | 보고서 6대 기준 블라인드 채점 |

## 지식 계층 (판단 기준은 전부 파일)
- `config/taxonomy.json` — 02_Taxonomy_Master (4계층, 23개 세분류, L3 → 전문 Prompt 매핑, 키워드). 세분류 추가·폐기는 웹 화면에서.
- `config/codebook.json` — 05_Code_Book (가중치 35/25/25/15, 등급 80/60/40, 기회 상향 규칙, 보고 Level 별 배포)
- `prompts/master.md`(Layer 1) · `prompts/output_format.md`(Layer 3) · `prompts/l3/*.md`(Layer 2, 16종) · `prompts/subagents/*.md`
- `data/decision_log.db` — Decision Log 20컬럼 + 확장 컬럼, 조정 이력, 감사 로그(모든 호출의 모델·Prompt 버전·토큰), 평가 이력
- `golden/` — 골든셋 (README 참고)

## 부록 A 정합성 정비 반영
리스크 척도 5=치명 표준(워크북 샘플 79점·35점 재현, 테스트로 고정) · 4단계 영문 등급 + 1~4등급 병기 · 1420/1430 L1=1000 정정 · Prompt 코드 1120→1130, 2310→2220 정정 · 통일 명칭 · 1400/2200 중분류 공통 Prompt · 확장 컬럼(SCORE_OPP, CEO_QA 등) · D_DAY=DUE_DATE−오늘 수식 · 종합 점수 엑셀 수식이 코드북 가중치 참조.
신규 Prompt 는 1120 가계통신비, 4110 국회/입법동향(부록 A 우선순위 1)을 추가했고, 아직 전문 Prompt 가 없는 3110·3120·4120·4130 은 범용 `GEN-0000` 을 쓴다(`/crpr-new-l3-prompt` 로 확장).

## 설정 (환경 변수)
| 변수 | 기본 | 설명 |
|---|---|---|
| `CRPR_PROVIDER` | anthropic | anthropic / bedrock(`AWS_REGION`) / vertex(`VERTEX_PROJECT_ID`) / offline |
| `CRPR_HEAVY_MODEL`, `CRPR_LIGHT_MODEL` | claude-opus-5-5, claude-sonnet-5-5 | 판단·합성 / 분류·패널 |
| `CRPR_HEAVY_EFFORT`, `CRPR_LIGHT_EFFORT` | high, medium | 모델 effort |
| `CRPR_FALLBACKS` | 1 | Claude API 에서 안전 분류기 거절 시 서버측 대체 모델 재실행(`fallbacks: "default"`) |
| `CRPR_MAX_REVISIONS` | 2 | 품질 루프 최대 수정 횟수 |
| `CRPR_ALLOW_INTERNAL` | 1 | 0 이면 사내보고서 외부 API 전송 차단(정보보호 협의 결과로 설정) |
| `CRPR_MASK_PII` | 1 | 주민번호·전화·이메일·계좌 마스킹 |
| `CRPR_HOST`, `CRPR_PORT` | 127.0.0.1, 8787 | 웹 서버. 공유 시 사내 SSO 프록시 뒤에 둘 것 |
| `CRPR_DATA_DIR` | ./data | DB·리포트·워크북 위치 |

## 구현하지 않은 것 (기획서 중 이번 범위에서 제외)
- 메일·공문함·국회 시스템 연동, 언론·SNS 실시간 수집(Phase 2~3) → 대신 `inbox/` 폴더 자동 처리
- 스캔본 OCR, 과거 사례 벡터 인덱스(같은 L3 최근·결정 완료 건 3개로 대체), Batch API 야간 일괄 분류
- 메일/메신저 알림 발송(알림 대상은 대시보드·`daily` 출력으로 제공), 행 단위 권한 관리(로컬 바인딩 + 외부 SSO 전제)
- 추진 일정·R&R·KPI 목표치는 운영 문서 영역이라 코드 대신 대시보드·피드백 리포트의 목표 표시로 반영

## 테스트
`python -m unittest discover -s tests` — API 키 없이 오프라인으로 돈다(점수 산식, 추출·마스킹, 검증기, 품질 루프 수정, 게이트, 피드백 집계, 엑셀, API 요청 형태).
