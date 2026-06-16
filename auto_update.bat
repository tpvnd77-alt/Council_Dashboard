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

REM PDF 파싱 실행
%PYTHON% -X utf8 "%SCRIPT_DIR%\parse_pdfs.py" >> "%LOG_FILE%" 2>&1

IF %ERRORLEVEL% EQU 0 (
    echo [%DATE% %TIME%] 업데이트 성공 -> 클라우드 업로드 시작 >> "%LOG_FILE%"
    
    REM Git 배포 자동화 실행
    %GIT% add data/meetings.json pdf/ >> "%LOG_FILE%" 2>&1
    %GIT% commit -m "Auto database and PDF update: %DATE% %TIME%" >> "%LOG_FILE%" 2>&1
    %GIT% push origin main >> "%LOG_FILE%" 2>&1
    
    echo [%DATE% %TIME%] 클라우드 업로드 성공 >> "%LOG_FILE%"
) ELSE (
    echo [%DATE% %TIME%] 업데이트 실패 (오류코드: %ERRORLEVEL%) >> "%LOG_FILE%"
)

echo ---------------------------------------- >> "%LOG_FILE%"
