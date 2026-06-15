@echo off
title 국회 회의록 분석 대시보드 서버 실행기
echo ===================================================
echo 국회 회의록 분석 대시보드 로컬 서버를 가동합니다.
echo ===================================================
echo.

cd /d "C:\Users\hp\.gemini\antigravity\scratch\council_dashboard"

netstat -ano | findstr :8765 > nul
if %errorlevel% equ 0 (
    echo [정보] 포트 8765가 이미 사용 중입니다. 대시보드가 구동 중일 수 있습니다.
) else (
    echo [정보] 대시보드 웹 서버를 시작합니다 (포트 8765)...
    set PYTHON_EXE=python
    if exist "C:\Users\hp\AppData\Local\Python\pythoncore-3.14-64\python.exe" (
        set PYTHON_EXE="C:\Users\hp\AppData\Local\Python\pythoncore-3.14-64\python.exe"
    )
    start /b "" %PYTHON_EXE% -m http.server 8765
    timeout /t 2 > nul
)

echo [정보] 웹 브라우저를 통해 대시보드에 접속합니다...
explorer "http://localhost:8765"

echo.
echo [안내] 이 창을 닫아도 서버는 백그라운드에서 계속 동작합니다.
echo        서버를 완전히 종료하려면 작업 관리자에서 python 프로세스를 종료해 주세요.
echo.
timeout /t 5
