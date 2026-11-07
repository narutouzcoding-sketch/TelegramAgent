param([switch]$Lan, [int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$panelBind = '127.0.0.1'
if ($Lan) { $panelBind = '0.0.0.0' }
& "$PSScriptRoot\.venv\Scripts\python.exe" -m telegram_agent panel --host $panelBind --port $Port
exit $LASTEXITCODE
