$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& uv sync --frozen --group dev
if ($LASTEXITCODE -ne 0) { throw 'Test kutubxonalari o''rnatilmadi.' }
& "$PSScriptRoot\.venv\Scripts\ruff.exe" check telegram_agent tests
if ($LASTEXITCODE -ne 0) { throw 'Kod tekshiruvi bajarilmadi.' }
& "$PSScriptRoot\.venv\Scripts\python.exe" -m pytest -q
exit $LASTEXITCODE
