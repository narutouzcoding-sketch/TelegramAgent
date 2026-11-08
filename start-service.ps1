$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$agentBackgroundPython = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $agentBackgroundPython)) { throw 'Avval setup.ps1 orqali Python muhitini tayyorlang.' }
Start-Process -FilePath $agentBackgroundPython -ArgumentList @('-m','telegram_agent','supervise') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden | Out-Null
Write-Host 'Yashirin panel nazoratchisi ishga tushirildi. Holat: http://127.0.0.1:8765/ . Log: data/service.log'
