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


def main() -> None:
    ap = argparse.ArgumentParser(description="Guard del runtime de navegador (Plan 240 F0)")
    ap.add_argument("--report", action="store_true", help="Imprime el JSON del guard")
    ap.add_argument("--probe", action="store_true",
                    help="Lanza y cierra chromium headless (chequeo autoritativo)")
    args = ap.parse_args()
    res = check_browser_runtime(probe_launch=args.probe)
    if args.report or args.probe or True:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    sys.exit(0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
