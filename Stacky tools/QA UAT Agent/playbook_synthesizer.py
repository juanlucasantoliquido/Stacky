"""playbook_synthesizer.py — Playbooks deterministas desde el ui_map (Plan 240 F3b).

POR QUE EXISTE
--------------
El generador exige un playbook por escenario (QA_UAT_REQUIRE_PLAYBOOK=true por
default): sin playbook, TODO escenario se bloquea con MISSING_PLAYBOOK y el runner
nunca corre. Hasta hoy la unica via de crear un playbook era grabar una sesion humana
(session_recorder -> session_to_playbook), es decir: trabajo manual del operador por
cada flujo. Este modulo sintetiza el playbook de forma DETERMINISTA a partir de dos
insumos que YA existen: el ui_map de la pantalla (cache/ui_maps/<pantalla>.json) y,
opcionalmente, los criterios de aceptacion del ticket.

REGLAS DURAS
------------
1. Cero LLM: puro cruce de datos => identico en los 3 runtimes.
2. NUNCA persiste una URL con ?q= (Plan 240 H4): el payload es per-sesion. La
   navegacion se declara por `screen` y el driver la resuelve en vivo.
3. Solo pantallas verificadas como alcanzables por deep-link con sesion valida
   (_DEEPLINKABLE). Para el resto se declara entry por menu, sin inventar URLs.
4. Marca `synthesized: true` y `source_ui_map`: un playbook sintetizado JAMAS se
   confunde con uno grabado de una sesion humana real.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.playbook_synthesizer")

_TOOL_ROOT = Path(__file__).resolve().parent
_UI_MAPS = _TOOL_ROOT / "cache" / "ui_maps"
_PLAYBOOKS = _TOOL_ROOT / "cache" / "playbooks"

_SCHEMA_VERSION = "playbook/1.0"
_TOOL_VERSION = "1.0.0"

# Pantallas verificadas en vivo (2026-07-25) como alcanzables por URL directa con
# sesion valida. Ver Plan 240 §2 "Sano y reusable".
_DEEPLINKABLE = frozenset({
    "FrmAgenda.aspx", "FrmBusqueda.aspx", "FrmDetalleClie.aspx", "FrmAgendaEquipo.aspx",
    "FrmAgendaJudicial.aspx", "FrmBusquedaJudicial.aspx", "FrmGestionFlujos.aspx",
    "Default.aspx", "FrmAsignarLote.aspx", "FrmAdministrador.aspx",
})

_WAIT_MS = 15_000


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return s[:60] or "flujo"


def load_ui_map(screen: str, ui_maps_dir: Optional[Path] = None) -> dict:
    """Lee el ui_map de una pantalla. Devuelve {} si no existe o no parsea."""
    base = ui_maps_dir or _UI_MAPS
    path = base / f"{screen}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def _elements(ui_map: dict) -> list:
    for key in ("elements", "elementos", "items"):
        val = ui_map.get(key)
        if isinstance(val, list):
            return [e for e in val if isinstance(e, dict)]
    return []


def _selector_of(el: dict) -> Optional[str]:
    for key in ("selector_recommended", "selector", "css"):
        val = el.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    eid = el.get("id")
    if isinstance(eid, str) and eid.strip():
        return f"#{eid.strip()}"
    return None


def _shell_selectors(screen: str, ui_maps_dir: Optional[Path] = None) -> set:
    """Selectores presentes en la MAYORIA de las otras pantallas => son de la shell.

    Un ancla de llegada tiene que ser DISCRIMINATIVA: #TimerSession, el menu o el
    boton de logout existen en todas las pantallas, asi que un waitFor sobre ellos
    pasaria en cualquier pagina y convertiria la asercion de llegada en un falso
    positivo (justo la clase de bug que este plan viene a matar).
    """
    base = ui_maps_dir or _UI_MAPS
    counts: dict[str, int] = {}
    others = 0
    try:
        for path in base.glob("*.json"):
            if path.stem == screen:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8")) or {}
            except Exception:  # noqa: BLE001
                continue
            others += 1
            seen = set()
            for el in _elements(data):
                sel = _selector_of(el)
                if sel:
                    seen.add(sel)
            for sel in seen:
                counts[sel] = counts.get(sel, 0) + 1
    except Exception:  # noqa: BLE001
        return set()
    if others < 2:
        return set()
    threshold = max(2, (others + 1) // 2)      # presente en >= la mitad de las otras
    return {sel for sel, n in counts.items() if n >= threshold}


# Controles de shell conocidos: aunque solo hubiera un ui_map, nunca son ancla.
_SHELL_DENY_RE = re.compile(
    r"timersession|logout|salir|menu|navbar|sidebar|footer|header|"
    r"usuario_?log|btncerrar|lblusuario|form1$",
    re.I,
)


# Elementos que NO sirven como ancla de llegada porque solo existen DESPUES de una
# accion (grillas de resultados, paneles de resultado, dialogos): usarlos produce
# SELECTOR_TIMEOUT en la carga inicial — verificado en vivo con FrmBusqueda.aspx.
_LATE_RENDER_RE = re.compile(
    r"__gvc_|grid|resultado|dialog|finsesion|updtimer|coincidencia", re.I
)


def rank_anchor_candidates(ui_map: dict, *, screen: str = "",
                           ui_maps_dir: Optional[Path] = None,
                           limit: int = 8) -> list:
    """Candidatos a ancla, del mejor al peor. Determinista.

    Criterios, en orden de peso: discriminativo (no de la shell) > presente en la
    carga inicial (no late-render) > selector por id > robustez alta > es un control
    de formulario.
    """
    shell = _shell_selectors(screen, ui_maps_dir) if screen else set()
    scored: list[tuple[int, str]] = []
    seen: set = set()
    for el in _elements(ui_map):
        if el.get("is_decorative"):
            continue
        sel = _selector_of(el)
        if not sel or sel in seen:
            continue
        if _SHELL_DENY_RE.search(sel):
            continue
        seen.add(sel)
        score = 0
        if sel not in shell:
            score += 6
        if not _LATE_RENDER_RE.search(sel):
            score += 5            # presente en la carga inicial
        if sel.startswith("#"):
            score += 3
        if str(el.get("robustness") or "").lower() == "high":
            score += 2
        kind = str(el.get("type") or el.get("tag") or "").lower()
        if kind in ("input", "text", "textbox", "select", "button", "submit"):
            score += 2
        scored.append((score, sel))
    scored.sort(key=lambda t: (-t[0], t[1]))
    # Solo candidatos discriminativos y de carga inicial (score >= 11).
    out = [sel for score, sel in scored if score >= 11]
    if not out:
        out = [sel for score, sel in scored if score >= 6]
    return out[:limit]


def pick_anchor(ui_map: dict, *, screen: str = "",
                ui_maps_dir: Optional[Path] = None) -> Optional[str]:
    """Mejor ancla estatica (sin verificar en vivo). None si no hay ninguna honesta."""
    cands = rank_anchor_candidates(ui_map, screen=screen, ui_maps_dir=ui_maps_dir)
    return cands[0] if cands else None


def find_by_tokens(ui_map: dict, tokens: list) -> Optional[str]:
    """Selector cuyo id/label/alias contenga alguno de los tokens (case-insensitive)."""
    if not tokens:
        return None
    low_tokens = [str(t).lower() for t in tokens if str(t).strip()]
    for el in _elements(ui_map):
        hay = " ".join(str(el.get(k) or "") for k in
                       ("id", "label", "alias_semantic", "name", "placeholder")).lower()
        if any(t in hay for t in low_tokens):
            sel = _selector_of(el)
            if sel:
                return sel
    return None


def synthesize(screen: str, *, goal_slug: Optional[str] = None,
               goal_label: Optional[str] = None,
               criteria: Optional[list] = None,
               ui_maps_dir: Optional[Path] = None) -> dict:
    """Construye el dict del playbook. NUNCA lanza.

    Devuelve {"ok": bool, "playbook": dict|None, "error": str|None, "anchor": str|None}
    """
    try:
        ui_map = load_ui_map(screen, ui_maps_dir)
        if not ui_map:
            return {"ok": False, "playbook": None, "anchor": None,
                    "error": f"ui_map_missing:{screen}"}
        anchor = pick_anchor(ui_map, screen=screen, ui_maps_dir=ui_maps_dir)
        if not anchor:
            return {"ok": False, "playbook": None, "anchor": None,
                    "error": f"no_stable_anchor:{screen}"}

        slug = goal_slug or f"verificar_{_slug(screen.replace('.aspx', ''))}"
        label = goal_label or f"verificar pantalla {screen}"

        nav_steps: list = []
        if screen in _DEEPLINKABLE:
            # `goto` por SCREEN (nunca una URL con ?q=): el runner la resuelve.
            nav_steps.append({"action": "goto", "screen": screen})
        else:
            nav_steps.append({"action": "goto", "screen": "FrmAgenda.aspx"})
            nav_steps.append({"action": "menu", "label": screen.replace(".aspx", ""),
                              "_note": "resuelto en vivo desde el menu (Plan 240 H4)"})
        nav_steps.append({"action": "waitFor", "selector": anchor, "timeout_ms": _WAIT_MS})

        action_steps: list = [
            {"action": "waitFor", "selector": anchor, "timeout_ms": _WAIT_MS,
             "_note": "ancla de llegada: prueba que la pantalla cargo"},
        ]
        # Un waitFor extra por criterio cuyo token resuelva a un selector real.
        for crit in (criteria or []):
            if not isinstance(crit, dict):
                continue
            sel = find_by_tokens(ui_map, crit.get("tokens") or [])
            if sel and sel != anchor:
                action_steps.append({
                    "action": "waitFor", "selector": sel, "timeout_ms": _WAIT_MS,
                    "_note": f"elemento del criterio {crit.get('id') or ''}".strip(),
                })

        playbook = {
            "schema_version": _SCHEMA_VERSION,
            "tool_version": _TOOL_VERSION,
            "goal_slug": slug,
            "goal_label": label,
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "session_source": f"synthesized:cache/ui_maps/{screen}.json",
            "synthesized": True,
            "source_ui_map": f"cache/ui_maps/{screen}.json",
            "entry_screen": screen if screen in _DEEPLINKABLE else "FrmAgenda.aspx",
            "target_screen": screen,
            "navigation_path": ["FrmLogin.aspx", screen],
            "navigation_steps": nav_steps,
            "action_steps": action_steps,
            "parameterizable_fields": {},
        }
        return {"ok": True, "playbook": playbook, "anchor": anchor, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.debug("synthesize fallo: %s", exc, exc_info=True)
        return {"ok": False, "playbook": None, "anchor": None,
                "error": f"{type(exc).__name__}: {exc}"}


def _has_q_param(obj) -> bool:
    """True si algun string del playbook contiene un payload ?q= (prohibido, H4)."""
    if isinstance(obj, str):
        return "?q=" in obj
    if isinstance(obj, dict):
        return any(_has_q_param(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_has_q_param(v) for v in obj)
    return False


def write_playbook(playbook: dict, *, playbooks_dir: Optional[Path] = None,
                   overwrite: bool = False) -> dict:
    """Persiste el playbook. Rechaza cualquiera con ?q= (H4). NUNCA lanza."""
    try:
        if _has_q_param(playbook):
            return {"ok": False, "path": None, "error": "playbook_has_q_param"}
        base = playbooks_dir or _PLAYBOOKS
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{playbook.get('goal_slug') or 'flujo'}.json"
        if path.exists() and not overwrite:
            existing = json.loads(path.read_text(encoding="utf-8")) or {}
            # Un playbook GRABADO por un humano jamas se pisa con uno sintetizado.
            if not existing.get("synthesized"):
                return {"ok": False, "path": str(path), "error": "human_playbook_exists"}
        path.write_text(json.dumps(playbook, ensure_ascii=False, indent=1), encoding="utf-8")
        return {"ok": True, "path": str(path), "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "path": None, "error": f"{type(exc).__name__}: {exc}"}


def ensure_playbook_for_screen(screen: str, *, criteria: Optional[list] = None,
                               ui_maps_dir: Optional[Path] = None,
                               playbooks_dir: Optional[Path] = None) -> dict:
    """Sintetiza y persiste el playbook de una pantalla si no hay uno que la cubra."""
    base = playbooks_dir or _PLAYBOOKS
    try:
        for pb_file in base.glob("*.json"):
            try:
                data = json.loads(pb_file.read_text(encoding="utf-8")) or {}
            except Exception:  # noqa: BLE001
                continue
            if data.get("target_screen") == screen:
                return {"ok": True, "path": str(pb_file), "created": False,
                        "synthesized": bool(data.get("synthesized")), "error": None}
    except Exception:  # noqa: BLE001
        pass
    res = synthesize(screen, criteria=criteria, ui_maps_dir=ui_maps_dir)
    if not res.get("ok"):
        return {"ok": False, "path": None, "created": False, "error": res.get("error")}
    wrote = write_playbook(res["playbook"], playbooks_dir=playbooks_dir, overwrite=True)
    return {"ok": bool(wrote.get("ok")), "path": wrote.get("path"), "created": True,
            "synthesized": True, "anchor": res.get("anchor"), "error": wrote.get("error")}


def verify_anchors_live(screens: list, *, ui_maps_dir: Optional[Path] = None,
                        timeout_ms: int = 8000) -> dict:
    """Abre cada pantalla y devuelve el PRIMER candidato a ancla que existe de verdad.

    Adivinar el ancla por el ui_map es fragil: una grilla de resultados existe en el
    mapa pero NO en la carga inicial, y el spec muere con SELECTOR_TIMEOUT (verificado
    en vivo). Esta verificacion cuesta una carga de pagina por pantalla y elimina esa
    clase de falso fallo. Requiere AgendaWeb arriba. NUNCA lanza.

    Retorna {screen: {"anchor": str|None, "checked": [..], "error": str|None}}
    """
    out: dict = {}
    try:
        from playwright.sync_api import sync_playwright
        from environment_preflight import get_agenda_base_url
        from auth_session_factory import _LOGIN_BTN_SEL, _LOGIN_PASS_SEL, _LOGIN_USER_SEL
        import os as _os
    except Exception as exc:  # noqa: BLE001
        return {s: {"anchor": None, "checked": [], "error": f"import: {exc}"} for s in screens}

    base = get_agenda_base_url()
    user = _os.environ.get("AGENDA_WEB_USER", "")
    pwd = _os.environ.get("AGENDA_WEB_PASS", "")
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                ctx = browser.new_context()
                page = ctx.new_page()
                page.goto(base + "FrmLogin.aspx", wait_until="domcontentloaded", timeout=30000)
                page.fill(_LOGIN_USER_SEL, user, timeout=10000)
                page.fill(_LOGIN_PASS_SEL, pwd)
                page.locator(_LOGIN_BTN_SEL).click(no_wait_after=True)
                page.wait_for_url(lambda u: "frmlogin" not in u.lower(), timeout=25000)
                page.wait_for_load_state("domcontentloaded", timeout=15000)

                for screen in screens:
                    ui_map = load_ui_map(screen, ui_maps_dir)
                    cands = rank_anchor_candidates(ui_map, screen=screen,
                                                   ui_maps_dir=ui_maps_dir)
                    entry = {"anchor": None, "checked": cands, "error": None}
                    try:
                        page.goto(base + screen, wait_until="domcontentloaded", timeout=30000)
                        if "frmlogin" in (page.url or "").lower():
                            entry["error"] = "login_redirect"
                            out[screen] = entry
                            continue
                        # VISIBILIDAD, no mera existencia: el spec generado asserta
                        # toBeVisible(), y un UpdatePanel puede existir en el DOM
                        # pero estar oculto hasta que haya resultados => el spec
                        # moria con SELECTOR_TIMEOUT (verificado en vivo).
                        for sel in cands:
                            try:
                                loc = page.locator(sel).first
                                if loc.count() > 0 and loc.is_visible(timeout=1500):
                                    entry["anchor"] = sel
                                    break
                            except Exception:  # noqa: BLE001
                                continue
                        if not entry["anchor"]:
                            entry["error"] = "no_candidate_present"
                    except Exception as exc:  # noqa: BLE001
                        entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
                    out[screen] = entry
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        for s in screens:
            out.setdefault(s, {"anchor": None, "checked": [], "error": str(exc)[:200]})
    return out


def ensure_playbooks_live(screens: list, *, ui_maps_dir: Optional[Path] = None,
                          playbooks_dir: Optional[Path] = None) -> dict:
    """Sintetiza playbooks con el ancla VERIFICADA en vivo. Retorna {screen: result}."""
    verified = verify_anchors_live(screens, ui_maps_dir=ui_maps_dir)
    results: dict = {}
    for screen in screens:
        info = verified.get(screen) or {}
        anchor = info.get("anchor")
        if not anchor:
            results[screen] = {"ok": False, "error": info.get("error") or "no_anchor",
                               "anchor": None}
            continue
        res = synthesize(screen, ui_maps_dir=ui_maps_dir)
        if not res.get("ok"):
            results[screen] = {"ok": False, "error": res.get("error"), "anchor": None}
            continue
        pb = res["playbook"]
        # Reemplazar el ancla adivinada por la VERIFICADA en vivo.
        for step in pb.get("navigation_steps", []):
            if step.get("action") == "waitFor":
                step["selector"] = anchor
        for step in pb.get("action_steps", []):
            if step.get("action") == "waitFor" and "ancla" in str(step.get("_note") or ""):
                step["selector"] = anchor
        pb["anchor_verified_live"] = True
        wrote = write_playbook(pb, playbooks_dir=playbooks_dir, overwrite=True)
        results[screen] = {"ok": bool(wrote.get("ok")), "anchor": anchor,
                           "path": wrote.get("path"), "error": wrote.get("error")}
    return results


# ── Plan 241 F4: pantallas que EXIGEN contexto previo ────────────────────────

# Selector de fila por default, verificado en vivo sobre la agenda personal.
# Selector de fila VERIFICADO EN VIVO el 2026-07-25: la grilla real es
# `#c_GridAgendaAut` (class "aisgridview clickable") y la fila 1 es el header, asi
# que la primera fila de datos es nth-child(2). Clickearla abre el detalle del
# cliente en una PESTANA NUEVA.
DEFAULT_ROW_SELECTOR = "#c_GridAgendaAut tr:nth-child(2)"
DEFAULT_ENTRY_SCREEN = "FrmAgenda.aspx"


def build_context_playbook(screen: str, *, anchor: str,
                           entry_screen: str = DEFAULT_ENTRY_SCREEN,
                           row_selector: Optional[str] = None,
                           goal_slug: Optional[str] = None) -> dict:
    """Playbook de una pantalla que exige contexto. Puro, sin navegador. NUNCA lanza.

    El contexto se gana NAVEGANDO: goto a la pantalla de entrada -> click en la
    primera fila de la grilla -> esperar el ancla de la pantalla de destino.
    JAMAS un goto con ?q= (el payload esta encriptado POR SESION: reconstruirlo es
    imposible y deep-linkearlo sin el redirige a frmLogin.aspx DESTRUYENDO la
    sesion — Plan 240 H4).
    """
    row = row_selector or DEFAULT_ROW_SELECTOR
    slug = goal_slug or f"verificar_{_slug(screen.replace('.aspx', ''))}"
    # El wait de llegada NO puede ser el generico de 15 s: medido en vivo, la
    # pestana del detalle pasa ~25 s en un interstitial "Loading ...". Con 15 s el
    # spec moriria con SELECTOR_TIMEOUT sobre una pantalla que SI llega.
    nav_steps = [
        {"action": "goto", "screen": entry_screen,
         "_note": "pantalla de ENTRADA; el destino no es deep-linkeable"},
        {"action": "click", "selector": row,
         "_note": "gana el contexto de cliente: el href real lleva un payload "
                  "encriptado por sesion, y el detalle abre en una PESTANA NUEVA"},
        {"action": "waitFor", "selector": anchor,
         "timeout_ms": _CONTEXT_ARRIVAL_TIMEOUT_MS,
         "_note": "ancla de llegada a la pantalla con contexto (interstitial ~25 s)"},
    ]
    return {
        "schema_version": _SCHEMA_VERSION,
        "tool_version": _TOOL_VERSION,
        "goal_slug": slug,
        "goal_label": f"verificar pantalla {screen} (con cliente en sesion)",
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "session_source": f"synthesized_with_context:cache/ui_maps/{screen}.json",
        "synthesized": True,
        "requires_context": True,
        "context_note": (
            "Esta pantalla NO se abre por URL: exige un cliente seleccionado. El "
            "enlace real lleva un payload de query encriptado POR SESION que no se "
            "puede reconstruir ni persistir; por eso se navega clickeando."
        ),
        "source_ui_map": f"cache/ui_maps/{screen}.json",
        "entry_screen": entry_screen,
        "target_screen": screen,
        "row_selector": row,
        "navigation_path": ["FrmLogin.aspx", entry_screen, screen],
        "navigation_steps": nav_steps,
        "action_steps": [
            {"action": "waitFor", "selector": anchor,
             "timeout_ms": _CONTEXT_ARRIVAL_TIMEOUT_MS,
             "_note": "ancla de llegada: prueba que la pantalla cargo"},
        ],
        "parameterizable_fields": {},
    }


# MEDIDO EN VIVO (2026-07-25): la pestana del detalle muestra un interstitial
# "Loading http://.../FrmDetalleClie.aspx" y recien navega de verdad a los ~25 s.
# Con el timeout de 20 s el harvest reportaba NAV_WRONG_SCREEN — un diagnostico
# MENTIROSO: la pantalla si llegaba, solo que despues del plazo.
_CONTEXT_ARRIVAL_TIMEOUT_MS = 60_000

# Controles de navegacion presentes en varias pantallas: sirven de ancla solo como
# ULTIMO recurso, porque un waitFor sobre ellos pasaria en cualquier pagina.
_GENERIC_CHROME_RE = re.compile(r"btnback|btnnext|btnprev|btnhome|btnsalir", re.I)


def _harvest_screen_with_context(screen: str, *, entry_screen: str,
                                 row_selector: str,
                                 timeout_ms: int = _CONTEXT_ARRIVAL_TIMEOUT_MS) -> dict:
    """Navega en vivo hasta `screen` con contexto y cosecha el ui_map REAL.

    Requiere AgendaWeb arriba. NUNCA lanza.
    Retorna {"ok", "anchor", "ui_map", "landing_url", "error"}.
    """
    out = {"ok": False, "anchor": None, "ui_map": None, "landing_url": None,
           "error": None}
    try:
        from playwright.sync_api import sync_playwright
        from environment_preflight import get_agenda_base_url
        from auth_session_factory import _LOGIN_BTN_SEL, _LOGIN_PASS_SEL, _LOGIN_USER_SEL
        from ui_map_builder import build_from_live_page
        import os as _os
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"import: {exc}"
        return out

    base = get_agenda_base_url()
    user = _os.environ.get("AGENDA_WEB_USER", "")
    pwd = _os.environ.get("AGENDA_WEB_PASS", "")
    screen_token = screen.replace(".aspx", "").lower()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                ctx = browser.new_context()
                page = ctx.new_page()
                # 1. login
                page.goto(base + "FrmLogin.aspx", wait_until="domcontentloaded",
                          timeout=30000)
                page.fill(_LOGIN_USER_SEL, user, timeout=10000)
                page.fill(_LOGIN_PASS_SEL, pwd)
                page.locator(_LOGIN_BTN_SEL).click(no_wait_after=True)
                page.wait_for_url(lambda u: "frmlogin" not in u.lower(), timeout=25000)
                # 2. pantalla de entrada
                page.goto(base + entry_screen, wait_until="domcontentloaded",
                          timeout=30000)
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                # 3. click en la primera fila (gana el contexto de cliente)
                row = page.locator(row_selector).first
                if row.count() == 0:
                    out["error"] = (
                        f"GRID_EMPTY: la grilla de {entry_screen} no tiene filas con "
                        f"el selector {row_selector!r}: sin un cliente cargado no se "
                        f"puede alcanzar {screen}"
                    )
                    return out
                # VERIFICADO EN VIVO (2026-07-25): la grilla de FrmAgenda abre el
                # detalle en una PESTANA NUEVA (window.open), no navegando la actual.
                # Sin esto, el wait_for_url sobre la pagina original expira siempre y
                # el diagnostico sale como NAV_WRONG_SCREEN, que es MENTIRA.
                _popups: list = []
                ctx.on("page", lambda p: _popups.append(p))
                row.click(no_wait_after=True, timeout=timeout_ms)

                # 4. aterrizaje: en la pestana nueva si la hubo, si no en la actual
                target_page = page
                deadline = time.time() + (timeout_ms / 1000.0)
                while time.time() < deadline:
                    if _popups:
                        target_page = _popups[0]
                        break
                    if screen_token in (page.url or "").lower():
                        break
                    page.wait_for_timeout(250)
                if target_page is not page:
                    try:
                        target_page.wait_for_url(
                            lambda u: screen_token in (u or "").lower(),
                            timeout=timeout_ms)
                    except Exception:  # noqa: BLE001
                        pass
                page = target_page
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                landing = page.url or ""
                out["landing_url"] = landing
                if "frmlogin" in landing.lower():
                    out["error"] = "NAV_SESSION_LOST: la app expulso al login"
                    return out
                if screen_token not in landing.lower():
                    out["error"] = (
                        f"NAV_WRONG_SCREEN: se esperaba {screen} y se aterrizo en {landing}")
                    return out
                # 5. cosechar el ui_map de la PAGINA VIVA (con contexto)
                ui_map = build_from_live_page(page, screen)
                out["ui_map"] = ui_map
                if not (ui_map or {}).get("ok"):
                    out["error"] = f"UI_MAP_EMPTY: {(ui_map or {}).get('error')}"
                    return out
                # 6. ancla por VISIBILIDAD real, no por ranking teorico, y
                #    DISCRIMINATIVA: los controles de paginacion (#btnBack/#btnNext)
                #    existen en varias pantallas, asi que un waitFor sobre ellos
                #    pasaria en cualquier lado — justo el falso positivo que el Plan
                #    241 mata. Se prefiere un candidato propio de la pantalla; los
                #    genericos quedan como ultimo recurso.
                # limit alto a proposito: los primeros candidatos de una pantalla
                # rica son modales OCULTOS, y con el limit por default (8) el unico
                # visible terminaba siendo #btnBack — un ancla no discriminativa.
                _visibles: list = []
                for sel in rank_anchor_candidates(ui_map, screen=screen, limit=30):
                    try:
                        loc = page.locator(sel).first
                        if loc.count() > 0 and loc.is_visible(timeout=1500):
                            _visibles.append(sel)
                            if not _GENERIC_CHROME_RE.search(sel):
                                break
                    except Exception:  # noqa: BLE001
                        continue
                _specific = [s for s in _visibles if not _GENERIC_CHROME_RE.search(s)]
                out["anchor"] = (_specific or _visibles or [None])[0]
                if not out["anchor"]:
                    out["error"] = "no_visible_anchor"
                    return out
                out["ok"] = True
                return out
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"[:250]
        return out


def ensure_playbook_with_context(screen: str, *, entry_screen: str = DEFAULT_ENTRY_SCREEN,
                                 row_selector: Optional[str] = None,
                                 ui_maps_dir: Optional[Path] = None,
                                 playbooks_dir: Optional[Path] = None) -> dict:
    """Sintetiza el playbook de una pantalla que EXIGE contexto previo (Plan 241 F4).

    Por que (Plan 240 H4/E9): FrmDetalleClie.aspx solo se abre con un cliente
    seleccionado, y el enlace real lleva un ?q= ENCRIPTADO POR SESION que NO se
    puede reconstruir. Por eso el contexto se gana NAVEGANDO, no sintetizando URLs:
      1. login  2. goto entry_screen  3. click en la primera fila de la grilla
      4. esperar aterrizaje en `screen`  5. recien AHI cosechar el ui_map real
         (ui_map_builder sobre la pagina viva) y elegir el ancla por VISIBILIDAD.
    El playbook resultante declara navigation_steps con la secuencia de CLICKS
    (jamas un goto con ?q=) y `requires_context: true`.
    Retorna {"ok", "anchor", "ui_map_elements", "path", "error"}. NUNCA lanza.
    """
    row = row_selector or DEFAULT_ROW_SELECTOR
    try:
        harvest = _harvest_screen_with_context(
            screen, entry_screen=entry_screen, row_selector=row)
        if not harvest.get("ok"):
            return {"ok": False, "anchor": None, "ui_map_elements": 0, "path": None,
                    "error": harvest.get("error") or "harvest_failed"}

        ui_map = harvest.get("ui_map") or {}
        # Persistir el ui_map cosechado CON contexto (pisa el de 5.7 KB sin cliente).
        try:
            base_maps = ui_maps_dir or _UI_MAPS
            base_maps.mkdir(parents=True, exist_ok=True)
            (base_maps / f"{screen}.json").write_text(
                json.dumps(ui_map, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("no se pudo persistir el ui_map con contexto: %s", exc)

        playbook = build_context_playbook(
            screen, anchor=harvest["anchor"], entry_screen=entry_screen,
            row_selector=row)
        playbook["anchor_verified_live"] = True
        playbook["query_payload_persisted"] = False   # jamas se persiste (ratchet H4)
        wrote = write_playbook(playbook, playbooks_dir=playbooks_dir, overwrite=True)
        return {
            "ok": bool(wrote.get("ok")),
            "anchor": harvest["anchor"],
            "ui_map_elements": len(ui_map.get("elements") or []),
            "path": wrote.get("path"),
            "error": wrote.get("error"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "anchor": None, "ui_map_elements": 0, "path": None,
                "error": f"{type(exc).__name__}: {exc}"[:250]}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Sintetiza playbooks desde el ui_map (Plan 240)")
    ap.add_argument("--screen", help="Pantalla, ej. FrmBusqueda.aspx")
    ap.add_argument("--screens", nargs="*", help="Varias pantallas (con --verify-live)")
    ap.add_argument("--write", action="store_true", help="Persiste en cache/playbooks/")
    ap.add_argument("--verify-live", action="store_true",
                    help="Verifica el ancla abriendo la pantalla (requiere AgendaWeb arriba)")
    ap.add_argument("--with-context", action="store_true",
                    help="Plan 241 F4: navega con contexto (click en fila) antes de cosechar")
    ap.add_argument("--entry-screen", default=DEFAULT_ENTRY_SCREEN)
    ap.add_argument("--row-selector", default=None)
    args = ap.parse_args()
    if args.with_context:
        print(json.dumps(ensure_playbook_with_context(
            args.screen, entry_screen=args.entry_screen,
            row_selector=args.row_selector), indent=2, ensure_ascii=False))
    elif args.verify_live:
        screens = args.screens or ([args.screen] if args.screen else [])
        print(json.dumps(ensure_playbooks_live(screens), indent=2, ensure_ascii=False))
    elif args.write:
        print(json.dumps(ensure_playbook_for_screen(args.screen), indent=2, ensure_ascii=False))
    else:
        res = synthesize(args.screen)
        print(json.dumps(res, indent=2, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
