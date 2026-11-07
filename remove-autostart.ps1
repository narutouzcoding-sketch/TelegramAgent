$ErrorActionPreference = 'Stop'
if (Get-ScheduledTask -TaskName 'TelegramAgent' -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName 'TelegramAgent' -Confirm:$false
}
Write-Host 'TelegramAgent avtomatik ishga tushishi olib tashlandi.'
