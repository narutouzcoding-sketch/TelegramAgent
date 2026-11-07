$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" -m telegram_agent.owner_contacts
if ($LASTEXITCODE -ne 0) { throw 'Kontaktlar sinxronlanmadi. Yuqoridagi xabarni tekshiring.' }
