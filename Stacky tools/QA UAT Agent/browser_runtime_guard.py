"""browser_runtime_guard.py — Guard veraz del runtime de navegador (Plan 240 F0).

REGLA DURA: la presencia del binding se prueba SIEMPRE con un import real de
playwright.sync_api, JAMAS con importlib.util.find_spec("playwright").
Motivo (H1): este tool tiene un directorio propio llamado "playwright/" (specs TS).
Con el tool en sys.path, find_spec("playwright") devuelve un ModuleSpec de
namespace package apuntando a ESE directorio => reporta "instalado" cuando no lo esta.
El fallo real recien aparece en `from playwright.sync_api import ...`.

C12: pw.chromium.executable_path devuelve el Chrome HEADED, pero launch(headless=True)
usa el HEADLESS SHELL, que es OTRO ejecutable. Un stat solo del primero da OK
mientras el launch falla. browser_ok exige que existan LOS DOS.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_TOOL_ROOT = Path(__file__).resolve().parent
_PIP_HINT = 'pip install "playwright>=1.44.0" && python -m playwright install chromium'
_INSTALL_HINT = "python -m playwright install chromium"

# Keys FIJAS del contrato de salida (10).
_CONTRACT_KEYS = (
    "ok", "binding_ok", "browser_ok", "code", "binding_version",
    "executable_path", "headless_shell_path", "shadowed_by", "remediation", "detail",
)


def _detect_shadowing() -> str | None:
    """Devuelve la ruta del directorio que enmascara al paquete, o None.

    No importa nada: solo mira el filesystem y sys.path.
    """
    seen: set[str] = set()
    for entry in [str(_TOOL_ROOT)] + list(sys.path):
        if not entry or entry in seen:
            continue
        seen.add(entry)
        try:
            cand = Path(entry) / "playwright"
            if cand.is_dir() and not (cand / "__init__.py").is_file():
                return str(cand)
        except Exception:  # noqa: BLE001 - path invalido en sys.path
            continue
    return None


def _headless_shell_path(executable_path: str) -> str | None:
    """Deriva la ruta del headless shell desde la del Chrome headed (C12).

    Devuelve None si el patron no matchea (otra plataforma / otro layout).
    """
    if not executable_path:
        return None
    p = str(executable_path)
    if not re.search(r"chromium-\d+", p):
        return None
    out = re.sub(r"chromium-(\d+)", r"chromium_headless_shell-\1", p)
    out = out.replace("chrome-win64", "chrome-headless-shell-win64")
    out = out.replace("chrome-linux", "chrome-headless-shell-linux")
    out = out.replace("chrome-mac", "chrome-headless-shell-mac")
    name = Path(out).name
    if name == "chrome.exe":
        out = str(Path(out).with_name("chrome-headless-shell.exe"))
    elif name == "chrome":
        out = str(Path(out).with_name("chrome-headless-shell"))
    else:
        return None
    return out


def _fail(code: str, *, binding_ok: bool, detail: str, remediation: str,
          shadowed: str | None, version: str | None = None,
          exe: str | None = None, shell: str | None = None) -> dict:
    return {
        "ok": False, "binding_ok": binding_ok, "browser_ok": False if binding_ok else None,
        "code": code, "binding_version": version, "executable_path": exe,
        "headless_shell_path": shell, "shadowed_by": shadowed,
        "remediation": remediation, "detail": detail,
    }


def check_browser_runtime(probe_launch: bool = False) -> dict:
    """Chequea binding + browser. NUNCA lanza. Nunca abre red.

    probe_launch=False: heuristico (stat de AMBOS ejecutables, C12).
    probe_launch=True: lanza y cierra chromium headless — unico chequeo autoritativo.
    """
    shadowed = _detect_shadowing()
    try:
        from playwright.sync_api import sync_playwright  # import REAL, no find_spec
    except Exception as exc:  # noqa: BLE001
        code = "PLAYWRIGHT_SHADOWED_BY_TOOL_DIR" if shadowed else "BROWSER_RUNTIME_MISSING"
        return _fail(code, binding_ok=False, detail=f"{type(exc).__name__}: {exc}",
                     remediation=_PIP_HINT, shadowed=shadowed)

    version = None
    try:
        import playwright as _pw
        version = getattr(_pw, "__version__", None)
    except Exception:  # noqa: BLE001
        pass

    exe: str | None = None
    shell: str | None = None
    try:
        with sync_playwright() as pw:
            exe = pw.chromium.executable_path
            shell = _headless_shell_path(exe or "")
            exe_ok = bool(exe) and Path(exe).is_file()
            # C12: si la ruta derivada no matchea el layout conocido, no la exigimos.
            shell_ok = True if shell is None else Path(shell).is_file()
            browser_ok = exe_ok and shell_ok
            if probe_launch and browser_ok:
                browser = pw.chromium.launch(headless=True)
                try:
                    browser_ok = True
                finally:
                    browser.close()
            elif probe_launch and not browser_ok:
                pass  # ya sabemos que falta algo; no intentamos lanzar
    except Exception as exc:  # noqa: BLE001
        return _fail("BROWSER_RUNTIME_MISSING", binding_ok=True,
                     detail=f"{type(exc).__name__}: {exc}",
                     remediation=_INSTALL_HINT, shadowed=shadowed,
                     version=version, exe=exe, shell=shell)

    if not browser_ok:
        missing = exe if not (exe and Path(exe).is_file()) else shell
        return _fail("BROWSER_RUNTIME_MISSING", binding_ok=True,
                     detail=f"ejecutable de navegador no encontrado: {missing}",
                     remediation=_INSTALL_HINT, shadowed=shadowed,
                     version=version, exe=exe, shell=shell)

    return {
        "ok": True, "binding_ok": True, "browser_ok": True, "code": "",
        "binding_version": version, "executable_path": exe,
        "headless_shell_path": shell, "shadowed_by": shadowed,
        "remediation": "", "detail": "",
    }


# ── Plan 241 F6: deriva de versiones Node <-> Python ─────────────────────────

_NODE_HINT = "npm --prefix \"<QA UAT Agent>\" install @playwright/test@<version> && npx playwright install chromium"
_PY_HINT = 'pip install "playwright==<version>" && python -m playwright install chromium'
_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")


def _node_playwright_version() -> str | None:
    """Version de @playwright/test declarada en node_modules. NUNCA lanza, sin red."""
    for rel in ("node_modules/@playwright/test/package.json",
                "node_modules/playwright/package.json",
                "node_modules/playwright-core/package.json"):
        try:
            p = _TOOL_ROOT / rel
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                v = str(data.get("version") or "").strip()
                if v:
                    return v
        except Exception:  # noqa: BLE001
            continue
    return None


def _python_playwright_version() -> str | None:
    """Version del binding Python. NUNCA lanza."""
    try:
        import playwright as _pw
        v = getattr(_pw, "__version__", None)
        return str(v).strip() if v else None
    except Exception:  # noqa: BLE001
        return None


def check_node_browser_drift(node_version: str | None = None,
                             python_version: str | None = None) -> dict:
    """Compara la version de Playwright de Node con la del binding Python.

    POR QUE (Plan 241 F6). El runner corre los specs con `npx playwright test`
    (Node) pero los guards y las sondas usan el binding Python. Si las versiones
    divergen, cada uno exige una REVISION DE NAVEGADOR DISTINTA: el guard de
    Python reporta "browser OK" y el globalSetup de Node muere con
    "Executable doesn't exist at ...chromium_headless_shell-<otra revision>".
    Ese fue exactamente el diagnostico mentiroso de la corrida del Plan 240.

    Retorna {"ok", "code", "node_version", "python_version", "remediation", "detail"}.
    NUNCA lanza. Sin red.
    """
    try:
        nv = node_version if node_version is not None else _node_playwright_version()
        pv = python_version if python_version is not None else _python_playwright_version()
        if not nv or not pv:
            return {
                "ok": True, "code": "", "node_version": nv, "python_version": pv,
                "remediation": [],
                "detail": ("no se pudo determinar alguna de las dos versiones: "
                           f"node={nv!r} python={pv!r} (sin veredicto de deriva)"),
            }
        nm = _VERSION_RE.search(str(nv))
        pm = _VERSION_RE.search(str(pv))
        n_norm = nm.group(1) if nm else str(nv).strip()
        p_norm = pm.group(1) if pm else str(pv).strip()
        if n_norm == p_norm:
            return {
                "ok": True, "code": "", "node_version": nv, "python_version": pv,
                "remediation": [],
                "detail": f"Node y Python alineados en Playwright {n_norm}",
            }
        return {
            "ok": False,
            "code": "BROWSER_VERSION_DRIFT",
            "node_version": nv,
            "python_version": pv,
            # Las DOS remediaciones: el operador elige a cual lado alinear.
            "remediation": [
                _NODE_HINT.replace("<version>", p_norm),
                _PY_HINT.replace("<version>", n_norm),
            ],
            "detail": (
                f"deriva de versiones: Node usa Playwright {n_norm} y el binding Python "
                f"{p_norm}. Cada uno exige una revision de navegador distinta, asi que el "
                "guard de Python puede decir OK mientras el globalSetup de Node muere con "
                "'Executable doesn't exist'."
            ),
        }
    except Exception as exc:  # noqa: BLE001 — NUNCA lanza
        return {"ok": True, "code": "", "node_version": None, "python_version": None,
                "remediation": [], "detail": f"drift_check_error:{type(exc).__name__}: {exc}"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Guard del runtime de navegador (Plan 240 F0)")
    ap.add_argument("--report", action="store_true", help="Imprime el JSON del guard")
    ap.add_argument("--probe", action="store_true",
                    help="Lanza y cierra chromium headless (chequeo autoritativo)")
    ap.add_argument("--drift", action="store_true",
                    help="Reporta la deriva de versiones Node<->Python (Plan 241 F6)")
    args = ap.parse_args()
    if args.drift:
        print(json.dumps(check_node_browser_drift(), indent=2, ensure_ascii=False))
        sys.exit(0)
    res = check_browser_runtime(probe_launch=args.probe)
    if args.report or args.probe or True:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    sys.exit(0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
