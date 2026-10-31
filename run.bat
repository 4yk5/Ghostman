@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
title Ghostman - TUI API & Webhook Studio
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo [Ghostman] An error occurred while running Ghostman.
    pause
)
