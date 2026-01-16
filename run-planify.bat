@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo           PLANIFY - AI Planning Tool
echo ============================================
echo.

REM Load API keys from User environment variables
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v OPENAI_API_KEY 2^>nul') do set "OPENAI_API_KEY=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v GEMINI_API_KEY 2^>nul') do set "GEMINI_API_KEY=%%b"

if not defined OPENAI_API_KEY (
    echo ERROR: OPENAI_API_KEY not found in user environment variables
    pause
    exit /b 1
)

echo API Key loaded: %OPENAI_API_KEY:~0,20%...
echo.

REM Default values
set "DEFAULT_REPO=C:\Users\sibag\Desktop\BUILD\crm\apps\web"
set "DEFAULT_CONFIG=C:\Users\sibag\Desktop\BUILD\crm\apps\web\planify.yaml"

REM Prompt for task
echo Enter your planning task (or press Enter for default):
echo Default: "Add email notifications for invoice reminders"
echo.
set /p TASK="Task: "

if "%TASK%"=="" set "TASK=Add email notifications for invoice reminders"

echo.
echo Running Planify with:
echo   Task: %TASK%
echo   Repo: %DEFAULT_REPO%
echo.

cd /d C:\Users\sibag\Desktop\BUILD\planify
poetry run planify "%TASK%" --repo "%DEFAULT_REPO%" --config "%DEFAULT_CONFIG%" --no-interactive --max-rounds 1

echo.
echo ============================================
echo Done! Check .planify-session folder for results.
echo ============================================
pause
