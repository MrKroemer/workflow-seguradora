# ============================================================
#  RPA PBSeg - Preparacao Completa do Ambiente Windows
#  Execute UMA vez em maquina nova ou apos atualizar o projeto.
#  Uso: clique duplo em preparar_ambiente.bat
# ============================================================

param()
$ErrorActionPreference = "Continue"
$ProgressPreference    = "SilentlyContinue"

$ROOT     = Split-Path $PSScriptRoot -Parent
$OUTPUTS  = "$ROOT\outputs"
$ARQUIVOS = "$ROOT\arquivos"
$VENV     = "$ROOT\.venv"
$ENV_FILE = "$ROOT\.env"
$ENV_EX   = "$ROOT\.env.example"
$CONFIG   = "$ROOT\config"

Set-Location $ROOT
New-Item -ItemType Directory -Force -Path $OUTPUTS | Out-Null
$LOG = "$OUTPUTS\setup_log.txt"

# ── helpers ──────────────────────────────────────────────────────
function log($m)  { "$(Get-Date -f 'yyyy-MM-dd HH:mm:ss') $m" | Add-Content $LOG -Encoding UTF8 }
function ok($m)   { Write-Host "     [OK] $m" -ForegroundColor Green;  log "[OK] $m"     }
function warn($m) { Write-Host "     [!!] $m" -ForegroundColor Yellow; log "[AVISO] $m"  }
function err($m)  { Write-Host "     [XX] $m" -ForegroundColor Red;    log "[ERRO] $m"   }
function step($n,$t,$title) {
    Write-Host ""
    Write-Host "  ── PASSO $n/$t — $title" -ForegroundColor Cyan
    log "PASSO $n/$t: $title"
}

# ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   RPA PBSeg - Preparacao Completa do Ambiente"              -ForegroundColor Cyan
Write-Host "   $(Get-Date -f 'dd/MM/yyyy HH:mm:ss')"                    -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   Raiz : $ROOT"
Write-Host "   Log  : $LOG"
log "=== INICIO DO SETUP ==="

# ─────────────────────────────────────────────────────────────────
# PASSO 1 — Python 3.11+
# ─────────────────────────────────────────────────────────────────
step 1 9 "Python 3.11+"

$PY     = $null
$pyArgs = @()
$pyVer  = $null

if     (Get-Command py     -EA SilentlyContinue) { $PY = "py";     $pyArgs = @("-3"); $pyVer = (py -3 --version 2>&1).ToString() }
elseif (Get-Command python  -EA SilentlyContinue) { $PY = "python";                   $pyVer = (python --version 2>&1).ToString() }
elseif (Get-Command python3 -EA SilentlyContinue) { $PY = "python3";                  $pyVer = (python3 --version 2>&1).ToString() }
else {
    warn "Python nao encontrado. Tentando instalar via winget..."
    if (Get-Command winget -EA SilentlyContinue) {
        winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -eq 0) {
            $env:PATH = [Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [Environment]::GetEnvironmentVariable("PATH","User")
            $PY = "py"; $pyArgs = @("-3")
            ok "Python 3.12 instalado via winget."
        } else {
            err "Falha ao instalar Python automaticamente."
            err "Acesse https://python.org/downloads e instale Python 3.11+."
            err "Marque 'Add Python to PATH' durante a instalacao."
            Read-Host "Pressione Enter para sair"; exit 1
        }
    } else {
        err "winget nao disponivel. Instale Python 3.11+ em: https://python.org/downloads"
        Read-Host "Pressione Enter para sair"; exit 1
    }
}

if ($pyVer -match "Python (\d+)\.(\d+)") {
    $maj = [int]$Matches[1]; $min = [int]$Matches[2]
    if ($maj -lt 3 -or ($maj -eq 3 -and $min -lt 11)) {
        err "Python $maj.$min encontrado — necessario 3.11+."
        Read-Host "Pressione Enter para sair"; exit 1
    }
    ok "Python $maj.$min  ($pyVer)"
}

# ─────────────────────────────────────────────────────────────────
# PASSO 2 — Ambiente virtual .venv
# ─────────────────────────────────────────────────────────────────
step 2 9 "Ambiente virtual (.venv)"

$venvPy = "$VENV\Scripts\python.exe"

if (Test-Path $venvPy) {
    ok ".venv ja existe."
} else {
    Write-Host "     Criando .venv ..."
    & $PY @pyArgs -m venv $VENV
    if ($LASTEXITCODE -ne 0) { err "Falha ao criar .venv"; Read-Host "Enter para sair"; exit 1 }
    ok ".venv criado."
}

Write-Host "     Atualizando pip..."
& $venvPy -m pip install --upgrade pip --quiet
ok "pip atualizado."

# ─────────────────────────────────────────────────────────────────
# PASSO 3 — Dependencias Python
# ─────────────────────────────────────────────────────────────────
step 3 9 "Dependencias Python"

$pkgs = @("openpyxl","flask","playwright","pywinauto","pypdf")
Write-Host "     Instalando: $($pkgs -join ', ')..."
& $venvPy -m pip install --quiet @pkgs
if ($LASTEXITCODE -ne 0) {
    err "Falha ao instalar dependencias. Verifique conexao e tente novamente."
    Read-Host "Enter para sair"; exit 1
}
foreach ($p in $pkgs) {
    $r = & $venvPy -c "import $p; print('ok')" 2>&1
    if ($r -eq "ok") { ok "  $p" } else { warn "  $p — pode ter problema" }
}

# ─────────────────────────────────────────────────────────────────
# PASSO 4 — Playwright Chromium
# ─────────────────────────────────────────────────────────────────
step 4 9 "Navegador Playwright (Chromium)"

Write-Host "     Instalando Chromium (pode levar alguns minutos)..."
& $venvPy -m playwright install chromium
if ($LASTEXITCODE -eq 0) { ok "Chromium instalado." }
else { warn "Falha no Chromium. Execute manualmente: .venv\Scripts\python.exe -m playwright install chromium" }

# ─────────────────────────────────────────────────────────────────
# PASSO 5 — Arquivo .env
# ─────────────────────────────────────────────────────────────────
step 5 9 "Arquivo de configuracao (.env)"

if (-not (Test-Path $ENV_FILE)) {
    if (Test-Path $ENV_EX) {
        Copy-Item $ENV_EX $ENV_FILE
        ok ".env criado a partir de .env.example"
    } else {
        @"
RPA_STRICT_PRODUCTION=0
MICROSOFT_TODO_REQUIRE_DESKTOP=0
SEGFY_WEB_ENABLED=1
MICROSOFT_TODO_DESKTOP_ENABLED=1
"@ | Set-Content $ENV_FILE -Encoding UTF8
        ok ".env minimo criado."
    }
    warn "ATENCAO: Preencha suas credenciais em: $ENV_FILE"
    $r = Read-Host "     Deseja abrir o .env agora para editar? (S/N)"
    if ($r -imatch "^s") {
        Start-Process notepad $ENV_FILE
        Read-Host "     Edite e salve o .env. Pressione Enter para continuar"
    }
} else {
    ok ".env ja existe."
}

$envLines = Get-Content $ENV_FILE -Encoding UTF8 -EA SilentlyContinue
@{
    "GOOGLE_CLIENT_ID"         = "Google Calendar"
    "GMAIL_IMAP_USER"          = "Gmail IMAP"
    "MICROSOFT_TODO_CLIENT_ID" = "Microsoft To Do"
    "SEGFY_USER"               = "Segfy"
}.GetEnumerator() | ForEach-Object {
    $v = $envLines | Where-Object { $_ -match "^$($_.Key)=(.+)" }
    $val = if ($v) { ($v -split "=",2)[1].Trim() } else { "" }
    if ($val) { ok "  $($_.Value) configurado" }
    else      { warn "  $($_.Value) nao configurado — edite .env: $($_.Key)=" }
}

# ─────────────────────────────────────────────────────────────────
# PASSO 6 — Pastas + settings.json
# ─────────────────────────────────────────────────────────────────
step 6 9 "Estrutura de pastas e configuracoes"

foreach ($d in @($OUTPUTS,$ARQUIVOS,"$ROOT\web",$CONFIG)) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
    ok "Pasta: $(Split-Path $d -Leaf)"
}

$settingsPath = "$CONFIG\settings.json"
if (-not (Test-Path $settingsPath)) {
    @'
{
  "timezone": "America/Fortaleza",
  "files": {
    "seguros_pbseg_xlsx":        "arquivos/SEGUROS PBSEG.xlsx",
    "acompanhamento_2026_xlsx":  "arquivos/ACOMPANHAMENTO 2026.xlsx",
    "fluxo_caixa_xlsx":          "arquivos/FLUXO DE CAIXA.xlsx",
    "senhas_pdf":                "arquivos/SENHAS.pdf"
  },
  "renewal": {
    "internal_days": 30,
    "new_days": 15,
    "reminder_days": [7, 1],
    "holidays": []
  },
  "insurers": {
    "Yelum":        "https://novomeuespacocorretor.yelumseguros.com.br/dashboard",
    "Porto Seguro": "https://corretor.portoseguro.com.br",
    "Mapfre":       "https://negocios.mapfre.com.br/tela-principal",
    "Bradesco":     "https://wwwn.bradescoseguros.com.br",
    "Allianz":      "https://www.allianznet.com.br",
    "Suhai":        "https://suhaiseguradoracotacao.com.br/login",
    "Tokio Marine": "https://www.tokiomarine.com.br/corretores",
    "HDI":          "https://www.hdi.com.br/hdidigital",
    "Azul":         "https://www.azulseguros.com.br/area-restrita",
    "Justos":       "https://corretores.justos.com.br/entrar"
  },
  "insurer_domains": [
    "yelum","portoseguro","mapfre","bradesco",
    "allianz","suhai","tokiomarine","hdi","azulseguros","justos"
  ]
}
'@ | Set-Content $settingsPath -Encoding UTF8
    ok "config\settings.json criado."
} else {
    ok "config\settings.json ja existe."
}

foreach ($p in @("SEGUROS PBSEG.xlsx","ACOMPANHAMENTO 2026.xlsx","FLUXO DE CAIXA.xlsx")) {
    if (Test-Path "$ARQUIVOS\$p") { ok "Planilha: $p" }
    else { warn "Planilha ausente: arquivos\$p" }
}

# ─────────────────────────────────────────────────────────────────
# PASSO 7 — Banco de dados SQLite
# ─────────────────────────────────────────────────────────────────
step 7 9 "Banco de dados operacional (SQLite)"

$tmpPy = "$OUTPUTS\_setup_db.py"
@"
import sys, os
sys.path.insert(0, r'$ROOT\src')
os.chdir(r'$ROOT')
try:
    from rpa_corretora.core import OperationalDatabase
    db = OperationalDatabase(r'$OUTPUTS\rpa_corretora.db')
    n  = db.conn.execute('SELECT COUNT(*) FROM policies').fetchone()[0]
    print(f'Banco OK — apolices: {n}')
    db.close()
except Exception as e:
    print(f'Aviso: {e}')
"@ | Set-Content $tmpPy -Encoding UTF8
$env:PYTHONPATH = "$ROOT\src"
$r = & $venvPy $tmpPy 2>&1
Remove-Item $tmpPy -Force -EA SilentlyContinue
ok $r

# ─────────────────────────────────────────────────────────────────
# PASSO 8 — Chrome CDP (Segfy)
# ─────────────────────────────────────────────────────────────────
step 8 9 "Chrome com CDP (Segfy)"

$chromePaths = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chromeExe = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chromeExe) {
    try { $chromeExe = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" -EA Stop)."(default)" } catch {}
}

if ($chromeExe) {
    ok "Chrome: $chromeExe"
    $desktop  = [Environment]::GetFolderPath("Desktop")
    $ws       = New-Object -ComObject WScript.Shell
    $sc       = $ws.CreateShortcut("$desktop\Chrome PBSeg.lnk")
    $sc.TargetPath      = $chromeExe
    $sc.Arguments       = '--remote-debugging-port=9222 --profile-directory="Profile 1" --restore-last-session'
    $sc.WorkingDirectory = Split-Path $chromeExe
    $sc.Description     = "Chrome com debug remoto para RPA PBSeg"
    $sc.IconLocation    = "$chromeExe,0"
    $sc.Save()
    ok "Atalho 'Chrome PBSeg' criado na area de trabalho."
    warn "IMPORTANTE: Sempre abra o Segfy pelo atalho 'Chrome PBSeg'."
} else {
    warn "Chrome nao encontrado. Instale em: https://google.com/chrome"
}

# ─────────────────────────────────────────────────────────────────
# PASSO 9 — Atalhos na area de trabalho
# ─────────────────────────────────────────────────────────────────
step 9 9 "Atalhos na area de trabalho"

$desktop = [Environment]::GetFolderPath("Desktop")
$ws      = New-Object -ComObject WScript.Shell

@(
    @{ Nome="RPA PBSeg - Painel";            Bat="abrir_painel.bat";       Desc="Painel web em http://localhost:5000" },
    @{ Nome="RPA PBSeg - Executar";          Bat="executar_rpa.bat";       Desc="Ciclo diario completo do RPA" },
    @{ Nome="RPA PBSeg - Configurar Chrome"; Bat="configurar_chrome.bat";  Desc="Configura Chrome CDP para Segfy"  }
) | ForEach-Object {
    $bat = "$ROOT\scripts\$($_.Bat)"
    if (Test-Path $bat) {
        $sc = $ws.CreateShortcut("$desktop\$($_.Nome).lnk")
        $sc.TargetPath       = $bat
        $sc.WorkingDirectory = $ROOT
        $sc.Description      = $_.Desc
        $sc.Save()
        ok "Atalho: $($_.Nome)"
    } else {
        warn "Script nao encontrado: $($_.Bat)"
    }
}

# ─────────────────────────────────────────────────────────────────
# VALIDACAO FINAL
# ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ── VALIDACAO FINAL — modulos principais" -ForegroundColor Cyan

$tmpVal = "$OUTPUTS\_setup_val.py"
@"
import sys, os
sys.path.insert(0, r'$ROOT\src')
os.chdir(r'$ROOT')
erros = []
for mod, nome in [
    ('openpyxl',              'openpyxl'),
    ('flask',                 'flask'),
    ('playwright',            'playwright'),
    ('rpa_corretora.config',  'configuracao'),
    ('rpa_corretora.core',    'banco de dados'),
    ('rpa_corretora.webapp',  'servidor web'),
    ('rpa_corretora.main',    'modulo principal'),
]:
    try:
        __import__(mod)
        print(f'     [OK] {nome}')
    except Exception as e:
        print(f'     [XX] {nome}: {e}')
        erros.append(nome)
if erros:
    print(f'\n     {len(erros)} modulo(s) com problema — veja acima.')
    raise SystemExit(1)
else:
    print(f'\n     Todos os modulos OK.')
"@ | Set-Content $tmpVal -Encoding UTF8
& $venvPy $tmpVal
$valOK = $LASTEXITCODE -eq 0
Remove-Item $tmpVal -Force -EA SilentlyContinue

# ─────────────────────────────────────────────────────────────────
# RELATORIO FINAL
# ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   SETUP CONCLUIDO — $(Get-Date -f 'dd/MM/yyyy HH:mm:ss')"  -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "   PROXIMOS PASSOS:" -ForegroundColor White
Write-Host ""
Write-Host "   1. Preencha credenciais no .env:" -ForegroundColor White
Write-Host "         $ENV_FILE" -ForegroundColor Gray
Write-Host ""
Write-Host "   2. Coloque as planilhas em arquivos\:" -ForegroundColor White
Write-Host "         SEGUROS PBSEG.xlsx  |  ACOMPANHAMENTO 2026.xlsx  |  FLUXO DE CAIXA.xlsx" -ForegroundColor Gray
Write-Host ""
Write-Host "   3. Para o Segfy — abra o Chrome pelo atalho 'Chrome PBSeg'" -ForegroundColor White
Write-Host "         Faca login no Segfy, depois execute o RPA" -ForegroundColor Gray
Write-Host ""
Write-Host "   4. Inicie o painel:" -ForegroundColor White
Write-Host "         Atalho 'RPA PBSeg - Painel'  ou  scripts\abrir_painel.bat" -ForegroundColor Gray
Write-Host "         Acesse: http://localhost:5000" -ForegroundColor Gray
Write-Host ""
Write-Host "   5. (Opcional) IA local do agente: scripts\setup_ollama.bat" -ForegroundColor White
Write-Host ""
Write-Host "   Log completo: $LOG" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

log "=== SETUP CONCLUIDO ==="
Read-Host "Pressione Enter para fechar"
