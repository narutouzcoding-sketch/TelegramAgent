param([switch]$SelfTest, [switch]$Speech)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$arguments = @('-m', 'telegram_agent', 'sandbox')
if ($SelfTest) { $arguments += '--self-test' }
if ($Speech) { $arguments += '--speech' }
& "$PSScriptRoot\.venv\Scripts\python.exe" @arguments
exit $LASTEXITCODE
