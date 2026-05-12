Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONPATH = "$(Get-Location)\src"

$py = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $py = "py" }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $py = "python" }
elseif (Test-Path ".venv\Scripts\python.exe") { $py = ".venv\Scripts\python.exe" }
else { Write-Host "[ERRO] Python nao encontrado." -ForegroundColor Red; Read-Host; exit 1 }

Write-Host "Iniciando RPA PBSeg em http://localhost:5000 ..." -ForegroundColor Cyan
& $py -m rpa_corretora.webapp
