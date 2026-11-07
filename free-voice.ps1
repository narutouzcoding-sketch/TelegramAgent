param([switch]$EnableCalls)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$arguments = @('-m', 'telegram_agent', 'free-voice-check')
if ($EnableCalls) { $arguments += '--enable-voice' }
& "$PSScriptRoot\.venv\Scripts\python.exe" @arguments
exit $LASTEXITCODE
