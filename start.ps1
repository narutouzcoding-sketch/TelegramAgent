$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Avval setup.ps1 ni bajaring.' }
& $pythonPath -m telegram_agent run
exit $LASTEXITCODE
