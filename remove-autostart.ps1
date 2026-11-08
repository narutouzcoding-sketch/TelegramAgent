$ErrorActionPreference = 'Stop'
if (Get-ScheduledTask -TaskName 'TelegramAgent' -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName 'TelegramAgent' -Confirm:$false
}
Write-Host 'TelegramAgent avtomatik ishga tushishi olib tashlandi.'
$agentShortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'TelegramAgent.lnk'
if (Test-Path -LiteralPath $agentShortcutPath) { Remove-Item -LiteralPath $agentShortcutPath }
