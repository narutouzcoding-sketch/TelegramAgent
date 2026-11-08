param([switch]$AcceptanceOnly, [switch]$Browser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$qaPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $qaPython)) { throw 'Avval setup.ps1 orqali muhitni tayyorlang.' }
if ($Browser) {
    Write-Host 'Alohida sinov paneli: http://127.0.0.1:8766'
    Write-Host 'Sinov paroli: Qa-Sinov-2026! | Haqiqiy Telegram va AI ulanmaydi.'
    & $qaPython tests\serve_qa_panel.py
    if ($LASTEXITCODE -ne 0) { throw 'Sinov paneli ishga tushmadi.' }
    exit 0
}
New-Item -ItemType Directory -Path data -Force | Out-Null
$qaArgs = @('-m','pytest','-q','-W','error::RuntimeWarning','--junitxml=data/qa-results.xml')
if ($AcceptanceOnly) { $qaArgs += 'tests/test_acceptance.py' }
& $qaPython @qaArgs
if ($LASTEXITCODE -ne 0) { throw 'Testlarda xato topildi. data/qa-results.xml ni ko''ring.' }
& "$PSScriptRoot\.venv\Scripts\ruff.exe" check .
if ($LASTEXITCODE -ne 0) { throw 'Ruff tekshiruvida xato.' }
Write-Host 'QA tugadi. Hisobot: data/qa-results.xml. Haqiqiy akkauntga qo''ng''iroq qilinmadi.'
