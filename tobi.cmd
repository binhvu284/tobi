@echo off
setlocal
REM Tobi launcher (Windows) - mirrors the Codespace `tobi` bash script.
REM   tobi            full system (main.py start)
REM   tobi test       connection test
REM   tobi terminal   local interactive chat
REM   tobi status / bot / api / research / execute / ceo
cd /d "%~dp0"
set "TOBI_PY=%~dp0venv\Scripts\python.exe"
call :check_python
if not errorlevel 1 goto run

REM The shared D-drive environment is the working fallback when the checkout venv is stale.
set "TOBI_PY=%~dp0..\.python\venv\Scripts\python.exe"
call :check_python
if not errorlevel 1 goto run

echo [tobi] no working Python environment was found.
echo [tobi] checked "%~dp0venv" and "%~dp0..\.python\venv".
exit /b 1

:run
if "%~1"=="" (
  "%TOBI_PY%" main.py start
) else (
  "%TOBI_PY%" main.py %*
)
exit /b %errorlevel%

:check_python
if not exist "%TOBI_PY%" exit /b 1
"%TOBI_PY%" --version >nul 2>&1
exit /b %errorlevel%
