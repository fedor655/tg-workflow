@echo off
chcp 65001 >nul
title Vygruzka Telegram
python "%~dp0_выгрузка_тг.py"
echo.
pause
