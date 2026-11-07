param([string]$Model = 'qwen3:4b-instruct')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$localOllama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
if (-not (Test-Path -LiteralPath $localOllama)) {
    throw 'Avval rasmiy Ollama o''rnating: winget install --id Ollama.Ollama --exact --scope user'
}
try { $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 2 }
catch { Start-Process -FilePath $localOllama -ArgumentList 'serve' -WindowStyle Hidden }
& "$PSScriptRoot\.venv\Scripts\python.exe" -m telegram_agent.local_model_setup $Model
if ($LASTEXITCODE -ne 0) { throw 'Mahalliy model yuklanmadi. Internetni tekshiring.' }
& "$PSScriptRoot\.venv\Scripts\python.exe" -m telegram_agent configure
Write-Host 'Mahalliy AI tayyor. .env: LOCAL_AI_FALLBACK=true, LOCAL_AI_MODEL model nomi. Agentni paneldan qayta yoqing.'
