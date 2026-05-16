"""
auth_session_factory.py — Stage P0: genera y valida el storage_state de Playwright.

Responsabilidad única: antes de que corra cualquier spec, asegurar que existe un
storage_state.json válido con una sesión autenticada en AgendaWeb.

Flujo:
  1. Verificar que las credenciales existen en el entorno (nunca en repo).
  2. Si existe un storage_state válido y vigente (TTL configurable, default 30 min),
     reutilizarlo (fast-path).
  3. Si no existe o está vencido/inválido: hacer login programático con Playwright
     (chromium, headless), guardar el storage_state en dos lugares:
       - .auth/agenda.json            (usado por playwright.config.ts en todos los specs)
       - evidence/{ticket}/{run}/auth/storage_state.json  (artefacto de evidencia)
  4. Emitir evento auth_session en execution.jsonl con todos los campos requeridos.

Modos:
  - normal  : genera sesión real si hace falta
  - dry-run : solo valida que credenciales y selectores de login están configurados;
              NO abre browser, NO genera sesión real.
  - verify-only : igual que dry-run (alias)

Contrato de salida:
  {
    "ok": true | false,
    "verdict": "OK" | "BLOCKED",
    "category": "ENV" | null,
    "reason": "AUTH_OK" | "AUTH_NOT_AVAILABLE" | "AUTH_EXPIRED" |
              "AUTH_CREDENTIALS_INVALID" | "MISSING_CREDENTIALS" |
              "AUTH_LOGIN_TIMEOUT" | "AUTH_SELECTOR_MISSING",
    "stage": "auth_session",
    "storage_state_path": "<path>",
    "evidence_path": "<path>",
    "session_fingerprint": "<hex16>",
    "ttl_s": 1800,
    "session_age_s": <float> | null,
    "elapsed_ms": <int>,
    "dry_run": true | false,
    "human_action_required": "<str>" | null
  }

Evento execution.jsonl:
  {
    "event": "auth_session",
    "verdict": "OK",
    "reason": "AUTH_OK",
    "session_fingerprint": "<hex16>",
    "storage_state_path": ".auth/agenda.json",
    "ttl_s": 1800,
    "session_age_s": 120,
    "elapsed_ms": 8500,
    "dry_run": false,
    "reused": true
  }

Seguridad:
  - Las credenciales se leen SOLO de variables de entorno o keyring.
  - El storage_state nunca se commitea (ver .gitignore de .auth/).
  - Los permisos del archivo se restringen a 0o600.
  - No se loguean contraseñas — solo fingerprint derivado de (user, base_url).

CLI:
    python auth_session_factory.py [--mode dry-run] [--ticket 122] [--run-id <id>]
                                   [--evidence-dir <path>] [--verbose]
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import stat
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.auth_session")

# ── Constantes ─────────────────────────────────────────────────────────────────

_TOOL_ROOT = Path(__file__).parent
_AUTH_DIR = _TOOL_ROOT / ".auth"
_AUTH_FILE = _AUTH_DIR / "agenda.json"
_FINGERPRINT_FILE = _AUTH_DIR / "agenda.fingerprint.json"

# TTL de la sesión (segundos). Configurable vía QA_UAT_AUTH_TTL_S.
_DEFAULT_TTL_S: int = 1800  # 30 minutos

# Selectores del login form en FrmLogin.aspx (AIS WebForms)
_LOGIN_USER_SEL = "#c_abfUsuario"
_LOGIN_PASS_SEL = "#c_abfContrasena"
_LOGIN_BTN_SEL = "#c_btnOk"
_POST_LOGIN_URL_RE = r"FrmAgenda|FrmMain"

# Timeout de login real (ms)
_LOGIN_NAVIGATE_TIMEOUT_MS = 30_000
_LOGIN_FILL_TIMEOUT_MS = 10_000
_LOGIN_WAIT_URL_TIMEOUT_MS = 25_000
_LOGIN_LOAD_STATE_TIMEOUT_MS = 15_000

_TOOL_VERSION = "1.0.0"


# ── Resultado ──────────────────────────────────────────────────────────────────

@dataclass
class AuthSessionResult:
    ok: bool
    verdict: str               # "OK" | "BLOCKED"
    category: Optional[str]    # "ENV" | None
    reason: str                # ver contrato de salida
    stage: str = "auth_session"
    storage_state_path: Optional[str] = None
    evidence_path: Optional[str] = None
    session_fingerprint: Optional[str] = None
    ttl_s: int = _DEFAULT_TTL_S
    session_age_s: Optional[float] = None
    elapsed_ms: int = 0
    dry_run: bool = False
    reused: bool = False
    human_action_required: Optional[str] = None
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_event(self) -> dict:
        """Forma compacta para emission en execution.jsonl."""
        return {
            "event": "auth_session",
            "verdict": self.verdict,
            "category": self.category,
            "reason": self.reason,
            "storage_state_path": self.storage_state_path,
            "session_fingerprint": self.session_fingerprint,
            "ttl_s": self.ttl_s,
            "session_age_s": self.session_age_s,
            "elapsed_ms": self.elapsed_ms,
            "dry_run": self.dry_run,
            "reused": self.reused,
            "evidence_path": self.evidence_path,
        }


# ── Helpers de credenciales ───────────────────────────────────────────────────

def _read_credentials(config: Optional[dict] = None) -> tuple[str, str, str, str]:
    """Devuelve (base_url, user, password, missing_vars).

    missing_vars es string vacío si todas las vars están presentes.
    Las credenciales se leen EXCLUSIVAMENTE de env vars o del dict config
    pasado por tests — nunca de archivos hardcodeados.
    """
    cfg = config or {}
    try:
        from environment_preflight import get_agenda_base_url
        base_url = cfg.get("base_url") or get_agenda_base_url()
    except ImportError:
        base_url = (
            cfg.get("base_url")
            or os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
            .rstrip("/") + "/"
        )

    user = (cfg.get("user") or os.environ.get("AGENDA_WEB_USER", "")).strip()
    password = (cfg.get("pass") or os.environ.get("AGENDA_WEB_PASS", "")).strip()

    missing: list[str] = []
    if not user:
        missing.append("AGENDA_WEB_USER")
    if not password:
        missing.append("AGENDA_WEB_PASS")

    return base_url, user, password, ", ".join(missing)


def _credential_fingerprint(user: str, base_url: str) -> str:
    """SHA-256 sobre (user|base_url), primeros 16 hex. Nunca incluye password."""
    return hashlib.sha256(f"{user}|{base_url}".encode()).hexdigest()[:16]


# ── TTL y validez del storage_state existente ────────────────────────────────

def _load_existing_state(auth_file: Path, fingerprint: str, ttl_s: int) -> dict:
    """Verifica si el storage_state existente es reutilizable.

    Retorna {"ok": bool, "reason": str, "age_s": float|None, "data": dict|None}
    """
    if not auth_file.is_file():
        return {"ok": False, "reason": "AUTH_FILE_MISSING", "age_s": None, "data": None}

    # Verificar fingerprint
    if _FINGERPRINT_FILE.is_file():
        try:
            stored = json.loads(_FINGERPRINT_FILE.read_text(encoding="utf-8"))
            if stored.get("fingerprint") != fingerprint:
                return {
                    "ok": False,
                    "reason": "AUTH_FINGERPRINT_MISMATCH",
                    "age_s": None,
                    "data": None,
                }
        except Exception:
            return {"ok": False, "reason": "AUTH_FINGERPRINT_CORRUPT", "age_s": None, "data": None}
    else:
        # Sin fingerprint — invalidar por seguridad
        return {"ok": False, "reason": "AUTH_FINGERPRINT_MISSING", "age_s": None, "data": None}

    # Verificar TTL
    try:
        age_s = time.time() - auth_file.stat().st_mtime
        if age_s > ttl_s:
            return {"ok": False, "reason": "AUTH_EXPIRED", "age_s": age_s, "data": None}
    except OSError:
        return {"ok": False, "reason": "AUTH_FILE_STAT_ERROR", "age_s": None, "data": None}

    # Verificar contenido mínimo (cookies)
    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
        if not data.get("cookies"):
            return {"ok": False, "reason": "AUTH_NO_COOKIES", "age_s": age_s, "data": None}
        return {"ok": True, "reason": "AUTH_VALID", "age_s": age_s, "data": data}
    except Exception as exc:
        return {"ok": False, "reason": f"AUTH_FILE_PARSE_ERROR", "age_s": None, "data": None}


# ── Login programático con Playwright ─────────────────────────────────────────

def _do_playwright_login(
    base_url: str,
    user: str,
    password: str,
    auth_file: Path,
    fingerprint: str,
) -> dict:
    """Realiza el login programático via Playwright (headless chromium).

    Guarda el storage_state en auth_file y escribe el fingerprint.
    Retorna {"ok": bool, "reason": str, "error": str|None}
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "ok": False,
            "reason": "AUTH_NOT_AVAILABLE",
            "error": "playwright no está instalado — pip install playwright && playwright install chromium",
        }

    _AUTH_DIR.mkdir(parents=True, exist_ok=True)

    login_url = base_url.rstrip("/") + "/FrmLogin.aspx"
    logger.info("[auth_session_factory] Iniciando login headless en %s", login_url)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()

                page.goto(login_url, wait_until="domcontentloaded", timeout=_LOGIN_NAVIGATE_TIMEOUT_MS)
                page.fill(_LOGIN_USER_SEL, user, timeout=_LOGIN_FILL_TIMEOUT_MS)
                page.fill(_LOGIN_PASS_SEL, password)
                page.locator(_LOGIN_BTN_SEL).click(no_wait_after=True)

                login_succeeded = False
                try:
                    page.wait_for_url(_POST_LOGIN_URL_RE, timeout=_LOGIN_WAIT_URL_TIMEOUT_MS)
                    page.wait_for_load_state("domcontentloaded", timeout=_LOGIN_LOAD_STATE_TIMEOUT_MS)
                    login_succeeded = "frmlogin" not in page.url.lower()
                except Exception:
                    login_succeeded = False

                if not login_succeeded:
                    return {
                        "ok": False,
                        "reason": "AUTH_CREDENTIALS_INVALID",
                        "error": (
                            f"Login falló — sigue en {page.url}. "
                            "Verificar AGENDA_WEB_USER / AGENDA_WEB_PASS."
                        ),
                    }

                # Guardar storage_state
                context.storage_state(path=str(auth_file))

                # Restringir permisos del archivo (solo propietario puede leer/escribir)
                try:
                    auth_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
                except OSError:
                    pass  # Windows puede no soportar esto — no es fatal

                # Guardar fingerprint
                _FINGERPRINT_FILE.write_text(
                    json.dumps({
                        "fingerprint": fingerprint,
                        "user": user,
                        "base_url": base_url,
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "tool_version": _TOOL_VERSION,
                    }, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                logger.info("[auth_session_factory] Login OK — storage_state guardado en %s", auth_file)
                return {"ok": True, "reason": "AUTH_LOGIN_OK", "error": None}

            finally:
                browser.close()

    except Exception as exc:
        err_str = str(exc)
        # Clasificar error
        if "timeout" in err_str.lower():
            reason = "AUTH_LOGIN_TIMEOUT"
        elif "net::ERR" in err_str or "Connection refused" in err_str.lower():
            reason = "AUTH_NOT_AVAILABLE"
        else:
            reason = "AUTH_CREDENTIALS_INVALID"
        return {"ok": False, "reason": reason, "error": err_str}


# ── Copia del storage_state a evidence/ ───────────────────────────────────────

def _copy_to_evidence(
    auth_file: Path,
    evidence_dir: Optional[Path],
    ticket_id: Optional[int],
    run_id: Optional[str],
) -> Optional[str]:
    """Copia el storage_state a evidence/{ticket}/{run}/auth/storage_state.json.

    Retorna la ruta destino o None si no se puede copiar.
    El storage_state en evidence/ es artefacto de auditoría — mismos permisos
    restrictivos que el original.
    """
    if evidence_dir is None:
        if ticket_id and run_id:
            evidence_dir = _TOOL_ROOT / "evidence" / str(ticket_id) / run_id
        else:
            return None

    dest_dir = evidence_dir / "auth"
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "storage_state.json"
        import shutil
        shutil.copy2(str(auth_file), str(dest))
        try:
            dest.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        return str(dest)
    except Exception as exc:
        logger.warning("[auth_session_factory] No se pudo copiar storage_state a evidence: %s", exc)
        return None


# ── Dry-run: solo verifica configuración ──────────────────────────────────────

def _dry_run_verify(base_url: str, user: str, fingerprint: str) -> AuthSessionResult:
    """Verifica que credenciales y selectores estén configurados sin abrir browser."""
    checks = []

    # Check: credenciales presentes (ya validadas antes de llegar aquí)
    checks.append({"check": "credentials", "ok": True})

    # Check: selectores de login documentados (no abrimos browser, solo los reportamos)
    checks.append({
        "check": "login_selectors",
        "ok": True,
        "selectors": {
            "user": _LOGIN_USER_SEL,
            "pass": _LOGIN_PASS_SEL,
            "submit": _LOGIN_BTN_SEL,
            "post_login_url_re": _POST_LOGIN_URL_RE,
        },
    })

    # Check: archivo de auth actual (estado informativo)
    auth_exists = _AUTH_FILE.is_file()
    checks.append({"check": "auth_file_exists", "ok": auth_exists, "path": str(_AUTH_FILE)})

    return AuthSessionResult(
        ok=True,
        verdict="OK",
        category=None,
        reason="DRY_RUN_VERIFIED",
        storage_state_path=str(_AUTH_FILE) if auth_exists else None,
        session_fingerprint=fingerprint,
        dry_run=True,
        message=(
            f"dry-run: credenciales configuradas, selectores documentados. "
            f"Auth file {'existe' if auth_exists else 'NO existe'}."
        ),
    )


# ── Punto de entrada principal ─────────────────────────────────────────────────

def run_auth_session(
    mode: str = "normal",
    ticket_id: Optional[int] = None,
    run_id: Optional[str] = None,
    evidence_dir: Optional[Path] = None,
    config: Optional[dict] = None,
    exec_log=None,
) -> AuthSessionResult:
    """Ejecuta el stage auth_session y retorna AuthSessionResult.

    Parámetros
    ----------
    mode : str
        "normal"      — genera sesión real si hace falta.
        "dry-run" / "verify-only" — solo valida configuración, no abre browser.
    ticket_id : int, optional
        ID del ticket QA UAT (para rutas de evidencia).
    run_id : str, optional
        ID del run actual (para rutas de evidencia).
    evidence_dir : Path, optional
        Directorio raíz del run actual en evidence/.
    config : dict, optional
        Sobreescrituras de configuración (base_url, user, pass) — usado en tests.
    exec_log : ExecutionLogger, optional
        Logger activo para emitir el evento auth_session.

    Retorna
    -------
    AuthSessionResult con todos los campos del contrato de salida.
    """
    started = time.time()
    is_dry_run = mode in ("dry-run", "verify-only", "dry_run")
    ttl_s = int(os.environ.get("QA_UAT_AUTH_TTL_S", str(_DEFAULT_TTL_S)))

    # ── 1. Leer credenciales ─────────────────────────────────────────────────
    base_url, user, password, missing_vars = _read_credentials(config)

    if missing_vars:
        result = AuthSessionResult(
            ok=False,
            verdict="BLOCKED",
            category="ENV",
            reason="MISSING_CREDENTIALS",
            elapsed_ms=int((time.time() - started) * 1000),
            dry_run=is_dry_run,
            human_action_required=(
                f"Configurar las variables de entorno: {missing_vars}. "
                "Ejemplo: set AGENDA_WEB_USER=usuario && set AGENDA_WEB_PASS=clave"
            ),
            message=f"Credenciales faltantes: {missing_vars}",
        )
        _emit_event(exec_log, result)
        return result

    fingerprint = _credential_fingerprint(user, base_url)

    # ── 2. Modo dry-run ──────────────────────────────────────────────────────
    if is_dry_run:
        result = _dry_run_verify(base_url, user, fingerprint)
        result.elapsed_ms = int((time.time() - started) * 1000)
        _emit_event(exec_log, result)
        return result

    # ── 3. Intentar reutilizar sesión existente ──────────────────────────────
    existing = _load_existing_state(_AUTH_FILE, fingerprint, ttl_s)
    if existing["ok"]:
        age_s = existing.get("age_s")
        evid_path = _copy_to_evidence(_AUTH_FILE, evidence_dir, ticket_id, run_id)
        result = AuthSessionResult(
            ok=True,
            verdict="OK",
            category=None,
            reason="AUTH_OK",
            storage_state_path=str(_AUTH_FILE),
            evidence_path=evid_path,
            session_fingerprint=fingerprint,
            ttl_s=ttl_s,
            session_age_s=age_s,
            elapsed_ms=int((time.time() - started) * 1000),
            dry_run=False,
            reused=True,
            message=f"Sesión reutilizada ({int(age_s or 0)}s de antigüedad, TTL={ttl_s}s)",
        )
        _emit_event(exec_log, result)
        return result

    # ── 4. Limpiar estado inválido si existe ─────────────────────────────────
    _invalidate_auth_files()

    # ── 5. Login programático ─────────────────────────────────────────────────
    logger.info(
        "[auth_session_factory] Generando nueva sesión (reason=%s)", existing["reason"]
    )
    login_result = _do_playwright_login(base_url, user, password, _AUTH_FILE, fingerprint)

    if not login_result["ok"]:
        reason = login_result.get("reason", "AUTH_NOT_AVAILABLE")
        human_actions = {
            "MISSING_CREDENTIALS": (
                "Configurar AGENDA_WEB_USER y AGENDA_WEB_PASS en el entorno."
            ),
            "AUTH_CREDENTIALS_INVALID": (
                "Verificar AGENDA_WEB_USER y AGENDA_WEB_PASS — el login falló. "
                "Intentar login manual en FrmLogin.aspx para confirmar."
            ),
            "AUTH_NOT_AVAILABLE": (
                "AgendaWeb no responde durante el login. "
                "Verificar que la aplicación está corriendo (environment_preflight debería haber bloqueado antes)."
            ),
            "AUTH_LOGIN_TIMEOUT": (
                "Timeout durante el login programático. "
                "La aplicación puede estar iniciando lentamente. Reintentá en ~30s."
            ),
        }
        result = AuthSessionResult(
            ok=False,
            verdict="BLOCKED",
            category="ENV",
            reason=reason,
            elapsed_ms=int((time.time() - started) * 1000),
            dry_run=False,
            session_fingerprint=fingerprint,
            human_action_required=human_actions.get(reason, f"Investigar el error de auth: {login_result.get('error')}"),
            message=login_result.get("error", reason),
        )
        _emit_event(exec_log, result)
        return result

    # ── 6. Copiar a evidence/ y retornar OK ──────────────────────────────────
    evid_path = _copy_to_evidence(_AUTH_FILE, evidence_dir, ticket_id, run_id)
    new_age = time.time() - _AUTH_FILE.stat().st_mtime

    result = AuthSessionResult(
        ok=True,
        verdict="OK",
        category=None,
        reason="AUTH_OK",
        storage_state_path=str(_AUTH_FILE),
        evidence_path=evid_path,
        session_fingerprint=fingerprint,
        ttl_s=ttl_s,
        session_age_s=new_age,
        elapsed_ms=int((time.time() - started) * 1000),
        dry_run=False,
        reused=False,
        message="Nueva sesión generada exitosamente",
    )
    _emit_event(exec_log, result)
    return result


# ── Helpers internos ──────────────────────────────────────────────────────────

def _invalidate_auth_files() -> None:
    """Elimina auth file y fingerprint si existen."""
    for f in (_AUTH_FILE, _FINGERPRINT_FILE):
        try:
            if f.is_file():
                f.unlink()
        except OSError:
            pass


def _emit_event(exec_log, result: AuthSessionResult) -> None:
    """Emite el evento auth_session al ExecutionLogger si está disponible."""
    if exec_log is None:
        return
    try:
        exec_log.event("auth_session", result.to_event())
    except Exception as exc:
        logger.debug("[auth_session_factory] No se pudo emitir evento auth_session: %s", exc)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    p = argparse.ArgumentParser(
        description="auth_session_factory — genera o valida la sesión de Playwright"
    )
    p.add_argument(
        "--mode",
        default="normal",
        choices=["normal", "dry-run", "verify-only"],
        help="Modo de operación (default: normal)",
    )
    p.add_argument("--ticket", type=int, default=None, help="ID del ticket QA UAT")
    p.add_argument("--run-id", default=None, dest="run_id", help="ID del run activo")
    p.add_argument(
        "--evidence-dir", default=None, dest="evidence_dir",
        help="Directorio raíz del run en evidence/",
    )
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG, stream=sys.stderr,
            format="%(levelname)s %(name)s: %(message)s",
        )

    result = run_auth_session(
        mode=args.mode,
        ticket_id=args.ticket,
        run_id=args.run_id,
        evidence_dir=Path(args.evidence_dir) if args.evidence_dir else None,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
