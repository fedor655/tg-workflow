@echo off
chcp 65001 >nul
title Rasshifrovka
python "%~dp0_stt.py" %*
echo.
pause
