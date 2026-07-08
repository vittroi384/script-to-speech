@echo off
chcp 65001 >nul
title 대본 음성 변환기 (무료)
echo edge-tts 설치/업데이트 확인 중 (처음 한 번은 시간이 걸려요)...
py -m pip install -U edge-tts 2>nul || python -m pip install -U edge-tts
echo.
echo 프로그램을 실행합니다...
py "%~dp0edge_tts_gui.py" 2>nul || python "%~dp0edge_tts_gui.py"
if errorlevel 1 pause
