# Run the same panel/worker as open-panel, with bounded crash recovery.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Avval setup.ps1 ni bajaring.' }
& $pythonPath -c "from telegram_agent.config import Settings; Settings.load(); print('Sozlamalar: OK; maxfiy qiymatlar chiqarilmadi.')"
if ($LASTEXITCODE -ne 0) { throw 'Avval sozlash va tekshiruvni yakunlang.' }
$backgroundPythonPath = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $backgroundPythonPath)) { $backgroundPythonPath = $pythonPath }
$action = New-ScheduledTaskAction -Execute $backgroundPythonPath -Argument '-m telegram_agent supervise' -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
try {
    Register-ScheduledTask -TaskName 'TelegramAgent' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'TelegramAgent panel and supervised worker' -Force | Out-Null
    Write-Host 'Task Scheduler avtomatik ishga tushishi sozlandi.'
} catch {
    $agentShortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'TelegramAgent.lnk'
    $agentShortcutShell = New-Object -ComObject WScript.Shell
    $agentShortcut = $agentShortcutShell.CreateShortcut($agentShortcutPath)
    $agentShortcut.TargetPath = $backgroundPythonPath
    $agentShortcut.Arguments = '-m telegram_agent supervise'
    $agentShortcut.WorkingDirectory = $PSScriptRoot
    $agentShortcut.WindowStyle = 7
    $agentShortcut.Save()
    Write-Host 'Task Scheduler yozishga ruxsat bermadi; joriy foydalanuvchi Startup yorlig‘i sozlandi.'
}
Write-Host 'Windows login paytida avtomatik ishga tushish sozlandi. Kompyuter uyquda yoki o''chiq bo''lsa agent ishlamaydi.'
