# PROMPT — RPA PBSeg / workflow-seguradora
## GigaFlops Tecnologia — Entrega: sexta-feira

---

## CONTEXTO

Automação operacional completa para a corretora PBSeg (Danielly Rodrigues).
Repositório: `https://github.com/MrKroemer/workflow-seguradora`
Stack: Python 3.11+, Playwright, Flask, tkinter, SQLite.
O `.env` está 100% funcional — não alterar variáveis existentes.

---

## GARGALO 1 — GUI fecha quando o botão "Agente IA" é clicado

**Arquivo:** `src/rpa_corretora/gui.py`

**Causa exata:** Os métodos `_toggle_agent`, `_build_agent_panel`, `_agent_add_message`, `_agent_on_send`, `_agent_quick`, `_agent_show_status`, `_agent_show_alerts`, `_agent_ask_llm`, `_open_agent`, `_refresh_news`, `_fetch_news` e `_display_news` estão definidos **depois de `if __name__ == "__main__":`**, fora da classe `RPAApp`. Ao clicar no botão Agente, Python lança `AttributeError: 'RPAApp' object has no attribute '_toggle_agent'`, que mata o processo tkinter silenciosamente.

**O que fazer:** Mover todos esses métodos para dentro da classe `RPAApp`, antes do método `run(self)`. A estrutura correta do arquivo:

```python
class RPAApp:
    def __init__(self): ...
    def _setup_styles(self): ...
    def _build_ui(self): ...
    def _build_execution_tab(self): ...
    def _build_status_tab(self): ...
    def _build_news_tab(self): ...
    def _build_tools_tab(self): ...
    def _start_execution(self): ...
    def _start_dryrun(self): ...
    def _run_rpa(self, dry_run): ...
    def _execute_process(self, cmd, env): ...
    def _process_line(self, line): ...
    def _execution_finished(self, exit_code): ...
    def _stop_execution(self): ...
    def _log(self, text): ...
    def _reset_stages(self): ...
    def _update_stage(self, key, icon, color): ...
    def _load_status(self): ...
    def _open_dashboard(self): ...
    def _open_dashboard_basic(self): ...
    def _open_database(self): ...
    def _open_outputs(self): ...
    def _configure_chrome(self): ...
    def _open_last_report(self): ...
    def _open_segfy(self): ...
    def _open_calendar(self): ...
    # --- MOVER ESTES PARA DENTRO DA CLASSE ---
    def _toggle_agent(self): ...
    def _build_agent_panel(self): ...
    def _agent_add_message(self, text, is_user=False): ...
    def _agent_on_send(self, event=None): ...
    def _agent_quick(self, action): ...
    def _agent_show_status(self): ...
    def _agent_show_alerts(self): ...
    def _agent_ask_llm(self, question): ...
    def _open_agent(self): ...
    def _refresh_news(self): ...
    def _fetch_news(self): ...
    def _display_news(self, results): ...
    # -----------------------------------------
    def run(self): ...

def main():
    app = RPAApp()
    app.run()

if __name__ == "__main__":
    main()
```

Após mover, adicionar global exception handler logo no início do `main()`:

```python
def main() -> None:
    import traceback
    def _crash_handler(exc_type, exc_val, exc_tb):
        from pathlib import Path
        from datetime import datetime
        msg = ''.join(traceback.format_exception(exc_type, exc_val, exc_tb))
        Path("outputs").mkdir(exist_ok=True)
        with open("outputs/gui_crash.log", "a") as f:
            f.write(f"\n[{datetime.now()}]\n{msg}\n")
    sys.excepthook = _crash_handler

    app = RPAApp()
    app.run()
```

---

## GARGALO 2 — Chrome abre sem o perfil da Danielly (portais das seguradoras)

**Arquivo:** `src/rpa_corretora/integrations/insurer_portal_wave1.py` (e `wave2.py`)

**Causa exata:** O método `_launch_browser` nos portais usa `playwright.chromium.launch(channel="msedge", headless=self.headless)` — abre um browser isolado, sem perfil, sem sessão salva. O Segfy já resolve isso via CDP (`segfy_web_gateway.py`), mas os portais não — pedindo login toda vez e quebrando a automação.

**O que fazer:** Substituir o `_launch_browser` na classe base `SingleInsurerPortalGateway` (ou equivalente) para usar o mesmo padrão CDP do Segfy:

```python
def _launch_browser(self, playwright: "Playwright"):
    import subprocess, time, shutil
    from pathlib import Path

    cdp_port = int((os.getenv("PORTAL_CHROME_CDP_PORT") or os.getenv("SEGFY_CHROME_CDP_PORT") or "9223").strip())
    cdp_url = f"http://localhost:{cdp_port}"

    # 1. Tenta conectar ao Chrome já aberto com CDP
    if self._cdp_disponivel(cdp_port):
        b = playwright.chromium.connect_over_cdp(cdp_url, timeout=5000)
        b._rpa_persistent = True
        return b

    # 2. Abre Chrome com perfil da Danielly + porta CDP
    user_data_dir = (os.getenv("SEGFY_CHROME_USER_DATA_DIR") or "").strip()
    if not user_data_dir:
        user_data_dir = str(Path(os.getenv("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data")

    profile_dir = (os.getenv("SEGFY_CHROME_PROFILE_DIR") or "Default").strip()

    chrome_exe = None
    for c in [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]:
        if Path(c).exists():
            chrome_exe = c
            break

    if not chrome_exe:
        # fallback para Chromium bundled do Playwright
        return playwright.chromium.launch(headless=self.headless)

    subprocess.Popen([
        chrome_exe,
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={user_data_dir}",
        f"--profile-directory={profile_dir}",
        "--restore-last-session",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(15):
        time.sleep(1)
        if self._cdp_disponivel(cdp_port):
            b = playwright.chromium.connect_over_cdp(cdp_url, timeout=5000)
            b._rpa_persistent = True
            return b

    # fallback final
    return playwright.chromium.launch(headless=self.headless)

@staticmethod
def _cdp_disponivel(port: int) -> bool:
    try:
        from urllib.request import urlopen
        urlopen(f"http://localhost:{port}/json/version", timeout=2)
        return True
    except Exception:
        return False
```

**Atenção:** Usar porta `9223` para os portais (diferente da `9222` do Segfy) para evitar conflito de instâncias CDP. Adicionar ao `.env`:
```
PORTAL_CHROME_CDP_PORT=9223
```

**Para os portais fecharem a aba certa ao terminar:** quando `_rpa_persistent = True`, não chamar `browser.close()` — apenas fechar a aba (`page.close()`). Verificar cada `finally: browser.close()` nos portais e proteger:
```python
finally:
    if not getattr(browser, "_rpa_persistent", False):
        browser.close()
    else:
        try:
            page.close()
        except Exception:
            pass
```

---

## GARGALO 3 — Segfy não navega / trava após login

**Arquivo:** `src/rpa_corretora/integrations/segfy_web_gateway.py`

**Causa exata (três pontos específicos):**

**3a. `wait_for_timeout` fixo após `_navigate_to_section`**

`_navigate_to_section` clica no menu e aguarda `page.wait_for_timeout(1200)` — tempo insuficiente para o Angular carregar a rota e renderizar a tabela. Resultado: o código tenta preencher formulários em tela errada.

Substituir nos métodos `_sync_policies_on_page`, `_sync_followups_on_page`, `_sync_cashflow_on_page`:

```python
# ANTES
self._navigate_to_section(page, ["Segurados", "Clientes", ...])
# ...código continua imediatamente

# DEPOIS
navigated = self._navigate_to_section(page, ["Segurados", "Clientes", ...])
if not navigated:
    self._capture_debug_snapshot(page=page, label="nav_fail_segurados")
    print("[Segfy] Não conseguiu navegar para Segurados. Abortando sync.")
    return 0
# Aguarda a tabela ou botão "Novo" aparecer — sinal que a rota carregou
try:
    page.wait_for_selector(
        "button:has-text('Novo'), button:has-text('Adicionar'), table",
        timeout=12_000
    )
except Exception:
    self._capture_debug_snapshot(page=page, label="nav_timeout_segurados")
    return 0
self._dismiss_segfy_overlays(page)
```

Aplicar o mesmo padrão em todas as navegações dentro dos métodos `_sync_*_on_page` e `_register_*_on_page`.

**3b. `_dismiss_segfy_overlays` não é chamado antes de cada ação crítica**

O modal de "Instalar extensão" pode reaparecer a qualquer momento. Chamar `_dismiss_segfy_overlays(page)` no início de cada método `_sync_*_on_page`, além de já ser chamado no `_login`.

**3c. O `_run_web_session` abre e fecha uma instância CDP por chamada**

O `sync_policies`, `sync_followups`, `sync_cashflow` são chamados em sequência no orchestrator, e cada um abre seu próprio `with sync_playwright()`. No modo CDP persistente isso pode causar conflito de contexto. Consolidar as três chamadas em uma única sessão web:

No `orchestrator.py`, no bloco de Segfy (linha ~`segfy_sync_policies = int(sync_policies_func(policies) or 0)`), verificar se o gateway tem um método de sessão única. Se não tiver, criar:

```python
# Em segfy_web_gateway.py — adicionar método:
def sync_all(self, *, policies, followups, cashflow_entries) -> dict:
    """Executa sync_policies + sync_followups + sync_cashflow em uma única sessão."""
    if not self._can_automate():
        return {"policies": 0, "followups": 0, "cashflow": 0}

    def _action(page):
        p = self._sync_policies_on_page(page, policies) if policies else 0
        f = self._sync_followups_on_page(page, followups) if followups else 0
        c = self._sync_cashflow_on_page(page, cashflow_entries) if cashflow_entries else 0
        return {"policies": p, "followups": f, "cashflow": c}

    return self._run_web_session(_action) or {"policies": 0, "followups": 0, "cashflow": 0}
```

E no `orchestrator.py`, substituir as três chamadas separadas por uma única chamada a `sync_all`.

---

## GARGALO 4 — Visual de baixo impacto

**Arquivo:** `web/index.html` (servido pelo Flask em `webapp.py`)

**O que fazer:** Reescrever o arquivo completo com o seguinte design system:

**Tipografia e paleta:**
```css
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

:root {
  --bg:     #07090f;
  --bg1:    #0d1117;
  --bg2:    #131920;
  --bg3:    #1a2235;
  --border: #1e2d45;
  --cyan:   #00c8d4;
  --green:  #00e676;
  --amber:  #ffb300;
  --red:    #ff4444;
  --purple: #8b5cf6;
  --text:   #c9d8ef;
  --muted:  #4a6080;
  --bright: #e8f4ff;
  --mono:   'JetBrains Mono', monospace;
  --sans:   'Plus Jakarta Sans', system-ui, sans-serif;
}
```

**Layout:** `display: grid; grid-template-columns: 220px 1fr 320px; grid-template-rows: 56px 1fr 28px; height: 100vh`
- Coluna esquerda: sidebar com KPI cards + etapas do ciclo
- Centro: abas (Execução / Status / Ferramentas)
- Direita: painel do agente sempre visível
- Topo: topbar com logo + botões de ação
- Rodapé: barra de status 28px

**KPI cards na sidebar:** número em 28px JetBrains Mono bold, cor semântica, label 8px uppercase. Borda esquerda 2px colorida indica estado.

**Etapas do ciclo:** ícone 28×28px em box com fundo tintado, nome 11px, status 9px mono à direita. Borda esquerda muda de cor: cinza=idle, âmbar=running, verde=ok, vermelho=erro.

**Log:** fundo `#0d1117`, JetBrains Mono 10.5px, linhas coloridas:
- Verde → linhas com "ok", "sucesso", "concluído"
- Âmbar → "aviso", "warning", "skipped"  
- Vermelho → "erro", "falha", "exception"
- Ciano → timestamps e info geral
- Cinza escuro → mensagens secundárias

**Agente:** header com badge roxo, bolhas de chat distintas (usuário em ciano, bot em bg2), quick actions como pills, input com `border: 1px solid var(--border)` que acende em ciano no focus.

**Efeito sutil de terminal:**
```css
body::before {
  content: '';
  position: fixed; inset: 0;
  background: repeating-linear-gradient(
    0deg, transparent, transparent 2px,
    rgba(0,200,212,.01) 2px, rgba(0,200,212,.01) 4px
  );
  pointer-events: none; z-index: 9999;
}
```

**Status bar inferior:** `height: 28px; font: 9px var(--mono)` — exibir: último ciclo, próximo horário, total de alertas. Atualizar via SSE junto com o log.

**A API SSE e todos os endpoints do `webapp.py` não mudam** — apenas o HTML/CSS/JS do frontend.

---

## REGRAS — NÃO NEGOCIÁVEIS

1. **Zero regressão.** Nenhuma integração já funcionando para de funcionar.
2. **Portais**: se um portal falhar, logar e continuar. O ciclo nunca aborta por falha de portal individual — o `CascadingInsurerPortalGateway` já faz isso, não quebrar.
3. **`.env` intocável** — adicionar novas variáveis somente com valor padrão seguro.
4. **`SEGFY_WEB_HEADLESS=0` e `YELUM_PORTAL_WEB_HEADLESS=0`** durante debug, reverter antes do commit.
5. **`outputs/segfy_debug/`** — após qualquer execução falha do Segfy, checar screenshots e HTML gerados pelo `_capture_debug_snapshot` antes de ajustar seletores.

---

## CHECKLIST DE ENTREGA

- [ ] Botão "Agente IA" abre o painel sem fechar a janela
- [ ] Chrome abre com perfil da Danielly — já logado nos portais
- [ ] Segfy: `sync_followups` registra pelo menos 1 acompanhamento
- [ ] Porto Seguro: extrai prêmio e comissão de pelo menos 1 apólice
- [ ] WhatsApp: mensagem de teste enviada
- [ ] Gmail IMAP: e-mails lidos e classificados
- [ ] Google Calendar: compromissos do dia lidos
- [ ] Relatório JSON + PDF gerado em `outputs/` ao fim do ciclo
- [ ] `web/index.html` com visual descrito acima, sem quebrar SSE
- [ ] GUI estável por 5 minutos de execução contínua
- [ ] `--dry-run` sem exceções não tratadas

---

## ORDEM DE EXECUÇÃO

**Agora (impacto imediato, risco zero):**
1. Mover os métodos do agente para dentro da classe `RPAApp` em `gui.py` — resolve Gargalo 1
2. Definir `SEGFY_CHROME_USER_DATA_DIR`, `SEGFY_CHROME_PROFILE_DIR`, `PORTAL_CHROME_CDP_PORT` no `.env`

**Depois:**
3. Substituir `_launch_browser` nos portais — resolve Gargalo 2
4. Adicionar `wait_for_selector` e `_dismiss_segfy_overlays` nas navegações do Segfy — resolve Gargalo 3
5. Criar `sync_all` no Segfy e consolidar chamadas no orchestrator

**Por último:**
6. Reescrever `web/index.html` — resolve Gargalo 4
7. Validar checklist completo

---

*GigaFlops Tecnologia — RPA PBSeg — Entrega sexta-feira*
