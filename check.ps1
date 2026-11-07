param([switch]$Online)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$arguments = @('-m', 'telegram_agent', 'doctor')
if ($Online) { $arguments += '--online' }
& "$PSScriptRoot\.venv\Scripts\python.exe" @arguments
exit $LASTEXITCODE
