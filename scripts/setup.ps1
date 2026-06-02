Write-Host ""
Write-Host "=== RPA PBSeg - Setup Completo ===" -ForegroundColor Cyan
Write-Host ""

Set-Location (Split-Path $PSScriptRoot -Parent)
$root = Get-Location

# Detecta Python
$py = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $py = "py -3"
    Write-Host "[OK] Python: py -3" -ForegroundColor Green
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $py = "python"
    Write-Host "[OK] Python: python" -ForegroundColor Green
} elseif (Test-Path ".venv\Scripts\python.exe") {
    $py = ".venv\Scripts\python.exe"
    Write-Host "[OK] Python: .venv" -ForegroundColor Green
} else {
    Write-Host "[ERRO] Python nao encontrado. Instale em python.org" -ForegroundColor Red
    Read-Host "Pressione Enter"
    exit 1
}

Write-Host ""
Write-Host "[1/4] Instalando dependencias..." -ForegroundColor Yellow
Invoke-Expression "$py -m pip install --upgrade pip"
Invoke-Expression "$py -m pip install openpyxl flask playwright pywinauto pypdf"

Write-Host ""
Write-Host "[2/4] Instalando Chromium para Playwright..." -ForegroundColor Yellow
Invoke-Expression "$py -m playwright install chromium"

Write-Host ""
Write-Host "[3/4] Criando pastas..." -ForegroundColor Yellow
if (-not (Test-Path "outputs")) { New-Item -ItemType Directory -Path "outputs" | Out-Null }
if (-not (Test-Path "web")) { New-Item -ItemType Directory -Path "web" | Out-Null }
Write-Host "[OK] Pastas prontas." -ForegroundColor Green

Write-Host ""
Write-Host "[4/4] Validando..." -ForegroundColor Yellow
$env:PYTHONPATH = "$root\src"
Invoke-Expression "$py -c `"import openpyxl; print('[OK] openpyxl')`""
Invoke-Expression "$py -c `"import flask; print('[OK] flask')`""
Invoke-Expression "$py -c `"import playwright; print('[OK] playwright')`""

Write-Host ""
Write-Host "=== CONCLUIDO ===" -ForegroundColor Green
Write-Host ""
Write-Host "Para usar: scripts\abrir_painel.bat (duplo-clique pelo Explorer)"
Write-Host "Ou no PowerShell: scripts\iniciar.ps1"
Write-Host ""
Read-Host "Pressione Enter para fechar"
