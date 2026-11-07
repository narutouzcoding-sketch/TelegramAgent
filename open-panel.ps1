param([switch]$Lan, [int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$panelAddress = "http://127.0.0.1:$Port"
$panelReady = $false
try {
    $panelSession = Invoke-RestMethod -Uri "$panelAddress/api/session" -TimeoutSec 2
    $panelReady = $null -ne $panelSession.PSObject.Properties['authenticated']
} catch { }
if (-not $panelReady) {
    $panelPython = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
    if (-not (Test-Path -LiteralPath $panelPython)) { throw 'Avval loyiha Python muhiti o''rnatilishi kerak.' }
    $panelData = Join-Path $PSScriptRoot 'data'
    New-Item -ItemType Directory -Path $panelData -Force | Out-Null
    $panelBind = '127.0.0.1'
    if ($Lan) { $panelBind = '0.0.0.0' }
    $panelArguments = @('-m', 'telegram_agent', 'panel', '--host', $panelBind, '--port', "$Port")
    $panelProcess = Start-Process -FilePath $panelPython -ArgumentList $panelArguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $panelData 'panel.stdout.log') -RedirectStandardError (Join-Path $panelData 'panel.stderr.log')
    for ($panelAttempt = 0; $panelAttempt -lt 30; $panelAttempt++) {
        Start-Sleep -Milliseconds 300
        try {
            $panelSession = Invoke-RestMethod -Uri "$panelAddress/api/session" -TimeoutSec 1
            $panelReady = $null -ne $panelSession.PSObject.Properties['authenticated']
        } catch { }
        if ($panelReady -or $panelProcess.HasExited) { break }
    }
    if (-not $panelReady) { throw 'Panel ochilmadi. Eski agent ishlayotgan bo''lsa Ctrl+C bilan to''xtating. Tafsilot: data/panel.stderr.log' }
}
Start-Process $panelAddress
Write-Host 'Panel ochildi. Parol: data/panel-password.txt. Terminalni yopishingiz mumkin.'
