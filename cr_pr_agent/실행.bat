@echo off
chcp 65001 > nul
cd /d "%~dp0"
rem API 키: set ANTHROPIC_API_KEY=... (없으면 오프라인 모의 모드)
start "" http://localhost:8787
python cli.py serve
