"""
copilot_bridge.py — Automatización de UI para interactuar con Copilot Chat en VS Code.

Estrategia (en orden de prioridad):

1. VS Code Bridge HTTP (localhost:5051) — PREFERIDO
   La micro-extensión RIPLEY Bridge expone un servidor HTTP dentro de VS Code.
   El invoke se hace vía POST /invoke — no hay UI automation, no hay timing,
   no hay problema de foco de ventana. 100% confiable.

2. UI Automation fallback (pywinauto + pyautogui) — FALLBACK
   Si la extensión no está instalada o el puerto 5051 no responde,
   se usa automatización de UI como backup.

Para instalar la extensión (una sola vez):
    cd tools/vscode-bridge
    npm install
    npx tsc -p ./
    npx vsce package --no-dependencies
    code --install-extension ripley-vscode-bridge-1.0.0.vsix

Dependencias para el fallback:
    pip install pywinauto pyautogui pyperclip
"""

import os
import time
import logging
import threading
from pathlib import Path

# Carpeta donde VS Code guarda los archivos .agent.md del usuario
VSCODE_PROMPTS_DIR = Path(os.environ.get('APPDATA', '')) / 'Code' / 'User' / 'prompts'
# Carpeta de proyectos del mantis_scraper
PROJECTS_DIR = Path(__file__).parent / 'projects'

# Lock global que serializa TODA la sección de UI automation.
# Evita que dos hilos simultáneos (p.ej. PM + QA) interleaven focus/paste/enter
# sobre la misma ventana de VS Code, enviando prompts al lugar equivocado.
_ui_lock = threading.Lock()

# Puerto de la micro-extensión HTTP bridge
BRIDGE_PORT = 5051
BRIDGE_URL  = f"http://127.0.0.1:{BRIDGE_PORT}"

logger = logging.getLogger(__name__)


def _check_deps():
    """Verifica que las dependencias de UI automation estén instaladas."""
    try:
        import pyperclip  # noqa: F401
        import pyautogui  # noqa: F401
        import pywinauto  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            f"Dependencia de UI automation faltante: {e}\n"
            "Ejecutar: pip install pywinauto pyautogui pyperclip"
        ) from e

# Tiempos de espera (ajustar según velocidad de la máquina)
DELAY_AFTER_FOCUS    = 1.5   # segundos post-foco (más tiempo para que Windows lo procese)
DELAY_AFTER_OPEN_CHAT = 2.5  # segundos esperando que abra el chat
DELAY_AFTER_PASTE    = 0.5   # segundos post-paste antes de Enter
DELAY_AFTER_CLEAR    = 1.0   # segundos post-clear

# Retry
MAX_RETRIES = 3
RETRY_DELAY = 2.0


def _should_start_new_conversation(agent_name: str = None,
                                   new_conversation: bool = False) -> bool:
    """Determina si el envío debe arrancar en una conversación nueva."""
    if new_conversation:
        return True
    normalized = (agent_name or '').strip().lower()
    return normalized.startswith('pm')


def _get_project_prompt(project_name: str, agent_name: str) -> str:
    """
    Busca el prompt de proyecto para el agente dado.
    Hace un reverse lookup en config.json: agents[role] == agent_name -> carga prompts/{role}.md
    """
    config_file = PROJECTS_DIR / project_name / 'config.json'
    if not config_file.exists():
        return ''
    try:
        import json
        cfg    = json.loads(config_file.read_text(encoding='utf-8'))
        agents = cfg.get('agents', {})
        role   = next((k for k, v in agents.items() if v == agent_name), None)
        if role:
            prompt_file = PROJECTS_DIR / project_name / 'prompts' / f'{role}.md'
            if prompt_file.exists():
                text = prompt_file.read_text(encoding='utf-8-sig')
                if text.startswith('---'):
                    end = text.find('\n---', 3)
                    if end != -1:
                        text = text[end + 4:].lstrip('\n')
                logger.info("Prompt de proyecto '%s' / rol '%s' cargado (%d chars)",
                            project_name, role, len(text))
                return text
    except Exception as e:
        logger.warning("Error leyendo prompt de proyecto '%s': %s", project_name, e)
    return ''


def load_agent_base(agent_name: str, project_name: str = None) -> str:
    """
    Carga el prompt base para un agente.

    Orden de prioridad:
    1. Si project_name: busca en projects/{project_name}/prompts/{role}.md
    2. Fallback: archivo {agent_name}.agent.md en la carpeta de prompts de VS Code

    Retorna "" si no se encuentra nada.
    """
    if project_name:
        proj_prompt = _get_project_prompt(project_name, agent_name)
        if proj_prompt:
            return proj_prompt
        logger.debug("Sin prompt de proyecto para '%s'/'%s' — usando VS Code agent",
                     project_name, agent_name)

    agent_file = VSCODE_PROMPTS_DIR / f"{agent_name}.agent.md"
    if not agent_file.exists():
        logger.warning("Archivo de agente no encontrado: %s", agent_file)
        return ''
    try:
        text = agent_file.read_text(encoding='utf-8-sig')
        if text.startswith('---'):
            end_idx = text.find('\n---', 3)
            if end_idx != -1:
                text = text[end_idx + 4:].lstrip('\n')
        logger.info("Base de agente '%s' cargada (%d chars) desde %s",
                    agent_name, len(text), agent_file)
        return text
    except Exception as e:
        logger.error("Error leyendo base de agente '%s': %s", agent_name, e)
        return ''


def _find_vscode_window():
    """
    Busca la ventana de VS Code. Retorna el objeto o None.
    Nota: el escaneo UIA de todas las ventanas cuesta ~400-600ms.
    Usar _get_vscode_context() para obtener (win, edits) en una sola pasada
    cuando se necesita tanto la ventana como los controles.
    """
    import pywinauto
    desktop = pywinauto.Desktop(backend="uia")
    for w in desktop.windows():
        title = w.window_text() or ""
        if "Visual Studio Code" in title:
            return w
    return None


def _get_vscode_context():
    """
    Busca la ventana de VS Code y recupera sus controles Edit en una sola
    pasada UIA (~400ms vs ~1200ms si se llama _find_vscode_window 3 veces).
    Retorna (window, edits_list) o (None, []).
    """
    import pywinauto
    desktop = pywinauto.Desktop(backend="uia")
    for w in desktop.windows():
        if "Visual Studio Code" not in (w.window_text() or ""):
            continue
        try:
            edits = w.descendants(control_type="Edit")
        except Exception:
            edits = []
        return w, edits
    return None, []


def _set_foreground(hwnd: int) -> None:
    """Fuerza hwnd al primer plano usando thread attachment (bypass restricción Windows)."""
    import ctypes
    user32   = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    fg_hwnd  = user32.GetForegroundWindow()
    fg_tid   = user32.GetWindowThreadProcessId(fg_hwnd, None)
    our_tid  = kernel32.GetCurrentThreadId()
    if fg_tid and fg_tid != our_tid:
        user32.AttachThreadInput(our_tid, fg_tid, True)
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    if fg_tid and fg_tid != our_tid:
        user32.AttachThreadInput(our_tid, fg_tid, False)


def _ensure_foreground(win=None) -> bool:
    """
    Solo asegura que la ventana de VS Code esté en primer plano.
    Acepta la ventana ya encontrada para evitar re-escanear el desktop.
    """
    import ctypes
    user32 = ctypes.windll.user32
    if win is None:
        win = _find_vscode_window()
    if not win:
        return False
    try:
        hwnd = win.handle
        if user32.GetForegroundWindow() == hwnd:
            return True
        _set_foreground(hwnd)
        time.sleep(0.3)
        return True
    except Exception as e:
        logger.warning("_ensure_foreground: %s", e)
        return False


def focus_vscode() -> bool:
    """
    Enfoca la ventana de VS Code y la trae al primer plano visualmente.
    Retorna (success, window) para que el caller pueda reusar la ventana.
    """
    import ctypes
    user32 = ctypes.windll.user32

    for attempt in range(MAX_RETRIES):
        try:
            win = _find_vscode_window()
            if win:
                hwnd = win.handle
                user32.ShowWindow(hwnd, 9)   # SW_RESTORE = 9
                time.sleep(0.3)
                _set_foreground(hwnd)
                time.sleep(DELAY_AFTER_FOCUS)
                logger.debug("VS Code enfocado correctamente")
                return True
        except Exception as e:
            logger.warning("Intento %d de enfocar VS Code: %s", attempt + 1, e)
        time.sleep(RETRY_DELAY)

    logger.error("No se pudo enfocar VS Code después de %d intentos", MAX_RETRIES)
    return False


def open_copilot_chat(win=None, edits=None) -> tuple[bool, list]:
    """
    Abre Copilot Chat (Ctrl+Alt+I) y garantiza que el input tenga el foco.
    Acepta (win, edits) ya obtenidos para no re-escanear el desktop.
    Retorna (success, edits) donde edits es la lista de controles Edit actualizada.
    """
    import pyautogui

    for attempt in range(MAX_RETRIES):
        try:
            pyautogui.hotkey('ctrl', 'alt', 'i')
            time.sleep(DELAY_AFTER_OPEN_CHAT)

            # Obtener controles Edit (re-usar ventana si ya la tenemos)
            if win is None:
                win, edits = _get_vscode_context()
            elif not edits:
                try:
                    edits = win.descendants(control_type="Edit")
                except Exception:
                    _, edits = _get_vscode_context()

            if edits:
                try:
                    edits[-1].click_input()
                    time.sleep(0.4)
                    logger.debug("Click en chat input via UIA (edit[-1])")
                except Exception as click_err:
                    logger.debug("UIA click no disponible: %s", click_err)

            logger.debug("Copilot Chat abierto (intento %d)", attempt + 1)
            return True, edits or []
        except Exception as e:
            logger.warning("Intento %d de abrir chat: %s", attempt + 1, e)
        time.sleep(RETRY_DELAY)

    logger.error("No se pudo abrir Copilot Chat")
    return False, []


def clear_chat() -> None:
    """Intenta limpiar el historial del chat."""
    import pyautogui
    try:
        pyautogui.hotkey('ctrl', 'l')
        time.sleep(DELAY_AFTER_CLEAR)
        logger.debug("Chat limpiado")
    except Exception as e:
        logger.warning("No se pudo limpiar chat: %s", e)


def start_new_chat(win=None) -> bool:
    """Intenta arrancar una conversación nueva desde la UI de VS Code."""
    import pyautogui
    import pyperclip

    command_candidates = [
        'Chat: New Chat',
        'Chat: Nuevo chat',
        'Chat: Novo chat',
        'Copilot Chat: New Chat',
    ]

    for command_text in command_candidates:
        try:
            _ensure_foreground(win)
            pyautogui.press('f1')
            time.sleep(0.8)
            pyautogui.hotkey('ctrl', 'a')
            pyautogui.press('backspace')
            pyperclip.copy(command_text)
            time.sleep(0.2)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.5)
            pyautogui.press('enter')
            time.sleep(DELAY_AFTER_CLEAR + 0.5)
            logger.debug("Nuevo chat solicitado via command palette: %s", command_text)
            return True
        except Exception as e:
            logger.debug("No se pudo solicitar nuevo chat con '%s': %s", command_text, e)

    logger.warning("No se pudo abrir una conversación nueva via UI automation")
    return False


def send_prompt(prompt: str, win=None, edits=None) -> bool:
    """
    Envía el prompt al chat de Copilot.
    Acepta (win, edits) ya obtenidos para evitar re-escanear el desktop.
    Retorna True si el prompt fue enviado correctamente.
    """
    import pyautogui
    import pyperclip

    for attempt in range(MAX_RETRIES):
        try:
            pyperclip.copy(prompt)
            time.sleep(0.2)

            _ensure_foreground(win)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(DELAY_AFTER_PASTE)

            # Verificar via UIA que el último Edit tiene contenido
            pasted_ok = False
            if edits:
                try:
                    val = edits[-1].get_value()
                    if val and len(val.strip()) > 10:
                        pasted_ok = True
                        logger.debug("Paste verificado via UIA (%d chars)", len(val))
                except Exception:
                    pasted_ok = True   # UIA no disponible — asumir OK
            else:
                pasted_ok = True

            if not pasted_ok and attempt < MAX_RETRIES - 1:
                logger.warning("Paste no detectado (intento %d) — reabriendo chat", attempt + 1)
                pyautogui.hotkey('ctrl', 'z')
                time.sleep(0.3)
                _, edits = open_copilot_chat(win=win, edits=None)
                continue

            pyautogui.press('enter')
            logger.info("Prompt enviado (%d chars, intento %d)", len(prompt), attempt + 1)
            return True

        except Exception as e:
            logger.error("Error enviando prompt (intento %d): %s", attempt + 1, e)
        time.sleep(RETRY_DELAY)

    logger.error("No se pudo enviar el prompt después de %d intentos", MAX_RETRIES)
    return False


def _ensure_vscode_workspace(workspace_root: str, max_wait: int = 5) -> bool:
    """
    Garantiza que VS Code esté abierto con el workspace correcto Y que el bridge
    esté activo antes de proceder.

    Pasos:
    1. Ejecuta `code <workspace_root>`.
       - Si VS Code ya tiene ese workspace → lo enfoca (sin abrir instancia nueva).
       - Si no estaba abierto → lo abre con el workspace correcto.
    2. Espera polling hasta max_wait segundos a que el bridge responda en :5051.

    Retorna True si el bridge está disponible al final.
    """
    import subprocess

    # code.cmd es el wrapper correcto en Windows (maneja el PATH de extensiones)
    code_cmd = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Programs", "Microsoft VS Code", "bin", "code.cmd"
    )
    if not os.path.exists(code_cmd):
        code_cmd = "code"  # fallback: confiar en el PATH

    try:
        # shell=True necesario para .cmd en Windows sin consola visible
        subprocess.Popen(
            f'"{code_cmd}" "{workspace_root}"',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("[Bridge] VS Code abierto/enfocado con workspace: %s", workspace_root)
    except Exception as e:
        logger.warning("[Bridge] No se pudo abrir VS Code via CLI: %s", e)

    # Esperar a que el bridge responda (máx max_wait segundos)
    deadline = time.time() + max_wait
    attempt  = 0
    while time.time() < deadline:
        if _bridge_health():
            logger.info("[Bridge] Bridge HTTP activo (intento %d, %.1fs)", attempt + 1,
                        time.time() - (deadline - max_wait))
            return True
        attempt += 1
        time.sleep(1.5)

    print(f"[Bridge] Bridge HTTP (:{BRIDGE_PORT}) no disponible — se usará UI automation", flush=True)
    logger.warning("[Bridge] Bridge HTTP no disponible después de %ds — usando fallback UI", max_wait)
    return False


def _try_bridge(prompt: str, agent_name: str = None, workspace_root: str = None,
                new_conversation: bool = False) -> bool:
    """
    Intenta invocar el agente vía la micro-extensión HTTP (localhost:5051).

    Si workspace_root está especificado:
    - Llama primero a _ensure_vscode_workspace() para garantizar que VS Code
      tiene el workspace correcto abierto y el bridge está activo.
    - Si no se puede garantizar, retorna False (el caller usará UI automation).

    Retorna True si la extensión respondió ok=True.
    Retorna False en cualquier otro caso (caller usa fallback de UI automation).
    """
    import urllib.request
    import json as _json

    # Si se conoce el workspace, garantizarlo antes de invocar
    if workspace_root:
        if not _ensure_vscode_workspace(workspace_root):
            return False
    else:
        # Sin workspace conocido: intentar directamente si el bridge ya está activo
        if not _bridge_health():
            logger.debug("[Bridge HTTP] Puerto %d no disponible — usando fallback UI", BRIDGE_PORT)
            return False

    try:
        payload = _json.dumps({
            "prompt":         prompt,
            "agent":          agent_name or "",
            "workspace_root": workspace_root or "",
            "new_conversation": bool(new_conversation),
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{BRIDGE_URL}/invoke",
            data    = payload,
            headers = {"Content-Type": "application/json"},
            method  = "POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
            if body.get("ok"):
                logger.info(
                    "[Bridge HTTP] Prompt enviado vía extensión — agente: %s, chars: %d",
                    agent_name or "(sin agente)", body.get("chars", 0)
                )
                return True
            else:
                logger.warning("[Bridge HTTP] Extensión respondió ok=False: %s", body.get("error"))
                return False
    except OSError:
        logger.debug("[Bridge HTTP] Puerto %d no disponible — usando fallback UI", BRIDGE_PORT)
        return False
    except Exception as e:
        logger.warning("[Bridge HTTP] Error inesperado: %s — usando fallback UI", e)
        return False


def _bridge_health() -> bool:
    """Retorna True si la extensión está activa y respondiendo."""
    try:
        import urllib.request
        import json as _json
        req = urllib.request.Request(f"{BRIDGE_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
            return bool(body.get("ok"))
    except Exception:
        return False


def _try_bridge_with_retry(prompt: str, agent_name: str = None,
                           workspace_root: str = None,
                           new_conversation: bool = False,
                           retries: int = 3, delay: float = 5.0) -> bool:
    """
    Intenta el bridge HTTP con reintentos para dar tiempo a que VS Code
    cargue la extensión si recién fue abierto.
    Retorna True al primer intento exitoso.
    """
    for attempt in range(1, retries + 1):
        if _try_bridge(prompt, agent_name, workspace_root=workspace_root,
                       new_conversation=new_conversation):
            return True
        if attempt < retries:
            logger.debug("[Bridge HTTP] Intento %d/%d fallido — esperando %.0fs...",
                         attempt, retries, delay)
            time.sleep(delay)
    return False


def invoke_agent(prompt: str, agent_name: str = None, project_name: str = None,
                 workspace_root: str = None, allow_ui_fallback: bool = False,
                 new_conversation: bool = False) -> bool:
    """
    Secuencia completa: construye el prompt final y lo envía al agente.

    Estrategia:
    1. VS Code Bridge HTTP (localhost:5051) — ÚNICO MÉTODO SOPORTADO.
       - Abre VS Code con el workspace correcto si no está abierto.
       - Espera al bridge HTTP y luego invoca vía POST /invoke.
       - Sin UI automation, sin problemas de foco. 100% confiable.
    2. UI Automation — DESHABILITADO. allow_ui_fallback=False por defecto.
       No se usa UI automation en ningún contexto (dashboard, daemon, pipeline).

    Args:
        workspace_root:    Ruta al workspace. Si se provee, garantiza que VS Code
                           abre con ese workspace antes de invocar.
        allow_ui_fallback: Si False, retorna False sin intentar UI automation
                           cuando el bridge no está disponible.
    """
    final_prompt = prompt
    if agent_name:
        base = load_agent_base(agent_name, project_name=project_name)
        mention = f"@{agent_name}\n"
        if base:
            final_prompt = (
                f"{mention}"
                f"{base}\n\n"
                f"{'='*60}\n"
                f"## TAREA ACTUAL\n"
                f"{'='*60}\n\n"
                f"{prompt}"
            )
            logger.info("Prompt combinado con base de agente '%s' (total %d chars, con @mention)",
                        agent_name, len(final_prompt))
        else:
            final_prompt = f"{mention}{prompt}"
            logger.warning(
                "No se encontró base para '%s' — enviando solo el prompt de tarea (con @mention).",
                agent_name
            )

    # ── Intento 1: Bridge HTTP (con reintentos y apertura garantizada) ────────
    # Si el bridge claramente no está activo, skip directo a UI automation
    if _bridge_health():
        if _try_bridge_with_retry(final_prompt, agent_name, workspace_root=workspace_root,
                                  new_conversation=new_conversation,
                                  retries=2, delay=3.0):
            return True
        print("[Bridge] HTTP bridge activo pero falló al enviar — probando UI automation", flush=True)
    else:
        print(f"[Bridge] Puerto {BRIDGE_PORT} no disponible — yendo directo a UI automation", flush=True)

    # ── Intento 2: UI Automation fallback ─────────────────────────────────────
    if not allow_ui_fallback:
        print("[Bridge] UI fallback desactivado — invoke fallido", flush=True)
        logger.warning("[Bridge HTTP] No disponible y UI fallback desactivado — retornando False")
        return False

    print(f"[UI] Iniciando UI automation → agente: {agent_name or '(sin agente)'}", flush=True)
    logger.info("Bridge HTTP no disponible — usando UI automation (fallback)")
    _check_deps()

    # Serializar: solo un hilo puede hacer UI automation a la vez.
    # Tiempo máximo de espera: 10 min (ningún agente debería tardar más).
    print(f"[UI] Esperando _ui_lock (agente: {agent_name or '?'})...", flush=True)
    acquired = _ui_lock.acquire(timeout=600)
    if not acquired:
        logger.error("[UI] No se pudo adquirir _ui_lock en 10 min — abortando")
        print("[UI] ERROR: timeout esperando turno de UI — abortando", flush=True)
        return False
    try:
        print(f"[UI] _ui_lock adquirido — agente: {agent_name or '?'}", flush=True)
        # Una sola búsqueda de ventana; se comparte con open_copilot_chat y send_prompt
        print("[UI] Buscando ventana de VS Code...", flush=True)
        if not focus_vscode():
            print("[UI] ERROR: No se encontró ventana de VS Code", flush=True)
            return False
        print("[UI] VS Code encontrado — abriendo Copilot Chat...", flush=True)
        win, edits = _get_vscode_context()
        ok, edits  = open_copilot_chat(win=win, edits=edits)
        if not ok:
            print("[UI] ERROR: No se pudo abrir Copilot Chat", flush=True)
            return False

        if _should_start_new_conversation(agent_name, new_conversation=new_conversation):
            if start_new_chat(win=win):
                ok, edits = open_copilot_chat(win=win, edits=None)
                if not ok:
                    print("[UI] ERROR: No se pudo reabrir Copilot Chat tras crear conversación nueva", flush=True)
                    return False
            else:
                logger.warning("Fallo creando conversación nueva; limpiando chat actual como fallback")
                clear_chat()
        else:
            clear_chat()

        time.sleep(1.2)
        print(f"[UI] Enviando prompt ({len(final_prompt)} chars)...", flush=True)
        result = send_prompt(final_prompt, win=win, edits=edits)
        print(f"[UI] Prompt {'enviado OK' if result else 'FALLÓ'}", flush=True)
        return result
    finally:
        _ui_lock.release()
        print(f"[UI] _ui_lock liberado — agente: {agent_name or '?'}", flush=True)

