param([string]$InterfaceAlias='Wi-Fi')
$ErrorActionPreference='Stop'
$rootPath=Split-Path -Parent $PSScriptRoot
$statusPath=Join-Path $rootPath 'data\phone-network-status.json'
try {
    $existingRule=Get-NetFirewallRule -Name 'TelegramAgent-WiFi-8765' -ErrorAction SilentlyContinue
    if($existingRule){
        Set-NetFirewallRule -Name 'TelegramAgent-WiFi-8765' -Enabled True -Action Allow -Direction Inbound -Profile Any -InterfaceAlias $InterfaceAlias -Protocol TCP -LocalPort 8765 -RemoteAddress LocalSubnet | Out-Null
    } else {
        New-NetFirewallRule -Name 'TelegramAgent-WiFi-8765' -DisplayName 'TelegramAgent local Wi-Fi panel' -Description 'User-requested phone access on the same Wi-Fi subnet, TCP 8765.' -Direction Inbound -Action Allow -Enabled True -Profile Any -InterfaceAlias $InterfaceAlias -Protocol TCP -LocalPort 8765 -RemoteAddress LocalSubnet | Out-Null
    }
    @{ok=$true;port=8765;interface=$InterfaceAlias;remote='LocalSubnet'} | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8
} catch {
    @{ok=$false;error=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8
    throw
}
