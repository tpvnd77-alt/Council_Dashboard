@echo off
REM 제22대 국회 회의록 대시보드 - 자동 업데이트 및 클라우드 자동 배포 스크립트
REM 매일 새벽 1시에 Windows 작업 스케줄러에 의해 실행됩니다.

SET SCRIPT_DIR=C:\Users\hp\.gemini\antigravity\scratch\council_dashboard
SET LOG_FILE=%SCRIPT_DIR%\data\update_log.txt
SET PYTHON=python

REM Git 실행 경로 설정 (절대경로 우선, 없으면 PATH의 git 사용)
SET GIT="C:\Program Files\Git\cmd\git.exe"
IF NOT EXIST %GIT% SET GIT=git

echo [%DATE% %TIME%] 업데이트 시작 >> "%LOG_FILE%"

cd /d "%SCRIPT_DIR%"

REM 0. 텔레그램 봇 다운로드 폴더로부터 신규 PDF 동기화
xcopy /d /y "C:\Users\hp\.gemini\antigravity\scratch\telegram_bot_dashboard\bots\bills_council\pdf_22nd\*.pdf" "C:\Users\hp\bills_council\pdf_22nd\" >> "%LOG_FILE%" 2>&1

REM 0b. 국정감사 회의록 확인. 봇이 긁는 과방위 페이지에는 국정감사가
REM     올라오지 않아 국회회의록시스템에서 따로 받는다. 갓 끝난 국감은
REM     '임시회의록' 으로 먼저 올라오고 몇 달 뒤 정식본으로 바뀌는데,
REM     그때 알아서 갈아끼우고 관리자 채팅으로 한 줄 알린다.
REM     이 단계가 실패해도 배포를 막지 않는다 - PARSE_RC 는 아래 parse_pdfs 것만 본다.
%PYTHON% -X utf8 "C:\Users\hp\.gemini\antigravity\scratch\telegram_bot_dashboard\bots\bills_council\collect_audit.py" >> "%LOG_FILE%" 2>&1

REM 1. Build local JSON for Github Pages (this is what the dashboard reads)
%PYTHON% -X utf8 "%SCRIPT_DIR%\parse_pdfs.py" >> "%LOG_FILE%" 2>&1
SET PARSE_RC=%ERRORLEVEL%

REM 2. Supabase sync removed 2026-10-02. The project no longer exists: its
REM    <ref>.supabase.co is NXDOMAIN on public resolvers and both poolers
REM    answer "tenant/user not found". Last good sync was 2026-09-26.
REM    Nothing live depended on it - the published dashboard reads only
REM    data/meetings.json, and the Vercel API in api/ was never deployed.
REM    scripts/parse_to_supabase.py is left in place, just not run. To bring
REM    it back: put a working SUPABASE_DB_URL in .env and restore this step.

REM 3. Deploy.
IF %PARSE_RC% EQU 0 (
    echo [%DATE% %TIME%] parse_pdfs OK - deploying >> "%LOG_FILE%"
    %GIT% add data/index.json data/meetings pdf/ >> "%LOG_FILE%" 2>&1
    REM The legacy single meetings.json was dropped 2026-11-19: it had grown to
    REM 95MB against GitHub per-file limit of 100MB, and the site reads
    REM data/index.json plus data/meetings/ instead.
    %GIT% commit -m "Auto database and PDF update: %DATE% %TIME%" >> "%LOG_FILE%" 2>&1
    %GIT% push origin main >> "%LOG_FILE%" 2>&1
    IF ERRORLEVEL 1 (
        echo [%DATE% %TIME%] DEPLOY FAILED - git push returned an error >> "%LOG_FILE%"
    ) ELSE (
        echo [%DATE% %TIME%] DEPLOY OK >> "%LOG_FILE%"
    )
) ELSE (
    echo [%DATE% %TIME%] DEPLOY SKIPPED - parse_pdfs failed rc=%PARSE_RC% >> "%LOG_FILE%"
)



echo ---------------------------------------- >> "%LOG_FILE%"

