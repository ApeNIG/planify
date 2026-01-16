# Set console to UTF-8 mode
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
chcp 65001 | Out-Null

$env:OPENAI_API_KEY = [System.Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'User')
$env:GEMINI_API_KEY = [System.Environment]::GetEnvironmentVariable('GEMINI_API_KEY', 'User')

Write-Host "OPENAI_API_KEY loaded: $($env:OPENAI_API_KEY.Substring(0,20))..."
Write-Host "GEMINI_API_KEY loaded: $($env:GEMINI_API_KEY.Substring(0,20))..."

cd C:\Users\sibag\Desktop\BUILD\planify
poetry run planify "Add email notifications for invoice reminders" --repo "C:\Users\sibag\Desktop\BUILD\crm\apps\web" --config "C:\Users\sibag\Desktop\BUILD\crm\apps\web\planify.yaml" --no-interactive --max-rounds 1
