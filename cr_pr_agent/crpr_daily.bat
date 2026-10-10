@echo off
chcp 65001 > nul
cd /d "%~dp0"
rem Windows 작업 스케줄러에 매일 08:30 등록: inbox 처리 + D-Day 알림 + 워크북 갱신
python cli.py daily >> data\daily_log.txt 2>&1
