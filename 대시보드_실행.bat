@echo off
title 국회 회의록 대시보드(System C) 실행
echo =====================================================================
echo  제22대 국회 과학기술정보방송통신위원회 회의록 대시보드 (System C)
echo =====================================================================
echo.
echo  [안내] 로컬 개발 서버(Port 3000)를 기동합니다...
echo.
cd /d "C:\Users\hp\.gemini\antigravity\scratch\council_dashboard"
start "" "http://localhost:3000/#/keywords?k1=최민희%%20%%26%%20쿠팡%%20%%26%%20해킹"
python dev_server.py
pause
