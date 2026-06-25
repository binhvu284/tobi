@echo off
setlocal
REM Tobi launcher (Windows) - mirrors the Codespace `tobi` bash script.
REM   tobi            full system (main.py start)
REM   tobi test       connection test
REM   tobi terminal   local interactive chat
REM   tobi status / bot / api / research / execute / ceo
cd /d "%~dp0"
set "TOBI_PY=%~dp0venv\Scripts\python.exe"
if not exist "%TOBI_PY%" (
  echo [tobi] venv not found at "%~dp0venv"
  echo [tobi] create it first with: python -m venv venv
  exit /b 1
)
if "%~1"=="" (
  "%TOBI_PY%" main.py start
) else (
  "%TOBI_PY%" main.py %*
)
