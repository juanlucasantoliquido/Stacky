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


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Sintetiza playbooks desde el ui_map (Plan 240)")
    ap.add_argument("--screen", help="Pantalla, ej. FrmBusqueda.aspx")
    ap.add_argument("--screens", nargs="*", help="Varias pantallas (con --verify-live)")
    ap.add_argument("--write", action="store_true", help="Persiste en cache/playbooks/")
    ap.add_argument("--verify-live", action="store_true",
                    help="Verifica el ancla abriendo la pantalla (requiere AgendaWeb arriba)")
    args = ap.parse_args()
    if args.verify_live:
        screens = args.screens or ([args.screen] if args.screen else [])
        print(json.dumps(ensure_playbooks_live(screens), indent=2, ensure_ascii=False))
    elif args.write:
        print(json.dumps(ensure_playbook_for_screen(args.screen), indent=2, ensure_ascii=False))
    else:
        res = synthesize(args.screen)
        print(json.dumps(res, indent=2, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
