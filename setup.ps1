$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv topilmadi. https://docs.astral.sh/uv/getting-started/installation/ orqali o''rnating.'
}
& uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw 'Kutubxonalarni o''rnatish bajarilmadi.' }
& "$PSScriptRoot\.venv\Scripts\python.exe" -m telegram_agent setup
if ($LASTEXITCODE -ne 0) { throw 'Sozlash yakunlanmadi.' }
