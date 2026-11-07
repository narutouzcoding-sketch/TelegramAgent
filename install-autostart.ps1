# Optional: run only after setup and a successful real call.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Avval setup.ps1 ni bajaring.' }
& $pythonPath -m telegram_agent doctor
if ($LASTEXITCODE -ne 0) { throw 'Avval sozlash va tekshiruvni yakunlang.' }
$backgroundPythonPath = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $backgroundPythonPath)) { $backgroundPythonPath = $pythonPath }
$action = New-ScheduledTaskAction -Execute $backgroundPythonPath -Argument '-m telegram_agent run' -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'TelegramAgent' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Personal Telegram AI voice assistant' -Force | Out-Null
Write-Host 'Windows login paytida avtomatik ishga tushish sozlandi. Kompyuter uyquda yoki o''chiq bo''lsa agent ishlamaydi.'
