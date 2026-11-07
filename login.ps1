$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" -m telegram_agent login
if ($LASTEXITCODE -ne 0) { throw 'Telegram login yakunlanmadi. Yuqoridagi xabarni tekshiring.' }
