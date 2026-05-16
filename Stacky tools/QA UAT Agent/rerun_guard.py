"""
rerun_guard.py — Stage 0: gate contra reruns repetidos sin cambio de ambiente.

Responsabilidad única: antes de cualquier otro stage del pipeline, detectar si
el run actual es un rerun de un run reciente que terminó BLOCKED/ENV/* sin que
nada haya cambiado en el ambiente. Si lo detecta, bloquear con un mensaje
accionable que indica exactamente qué resolver.

Motivación:
  Se observaron 17 runs del ticket 122 en 93 minutos, todos dry-run, todos
  terminando en BLOCKED/ENV (MISSING_CREDENTIALS, AUTH_NOT_AVAILABLE,
  LOGIN_PAGE_TIMEOUT). Cada run gasta ~68s y produce artefactos que no aportan
  información nueva. El operador relanzaba sin esperar resolución del bloqueo.

Diseño:
  - Lee evidence/{ticket}/latest_run_result.json (enriquecido por el pipeline
    al finalizar cada run — ver qa_uat_pipeline._write_run_index_enriched).
  - Si latest no existe o tiene formato inválido → OK (compatibilidad hacia atrás).
  - Cooldown activo si: elapsed < TTL AND verdict == BLOCKED AND category IN
    ENV_CATEGORIES AND deployment_fingerprint no cambió.
  - Override: --force-rerun siempre permite (loguea forced=True).

Categorías que activan cooldown (bloqueos ENV transitorios):
  ENV_COOLDOWN_CATEGORIES = {"ENV"}
  Solo se bloquea si el verdict fue BLOCKED/ENV. FAIL funcional (APP) siempre
  permite reruns inmediatos (es un bug real del producto, no del ambiente).

Contrato de salida (RerunGuardResult):
  {
    "ok": true | false,
    "verdict": "OK" | "BLOCKED" | "OK_OVERRIDE",
    "category": "OPS" | null,
    "reason": "FIRST_RUN" | "TTL_EXPIRED" | "VERDICT_NOT_ENV" |
              "FINGERPRINT_CHANGED" | "FORCED_RERUN" | "NO_LATEST_RESULT" |
              "PREVIOUS_RUN_SAME_VERDICT",
    "stage": "rerun_guard",
    "cooldown_active": false | true,
    "cooldown_remaining_s": 0 | <int>,
    "previous_run_id": "<str>" | null,
    "previous_verdict": "<str>" | null,
    "previous_reason": "<str>" | null,
    "previous_finished_at": "<iso8601>" | null,
    "forced": false | true,
    "elapsed_ms": <int>,
    "human_action_required": "<str>" | null,
    "message": "<str>"
  }

Evento execution.jsonl:
  {
    "event": "rerun_guard",
    "verdict": "OK",
    "reason": "FIRST_RUN",
    "cooldown_active": false,
    "cooldown_remaining_s": 0,
    "previous_run_id": null,
    "forced": false,
    "elapsed_ms": 2
  }

Compatibilidad hacia atrás:
  Si latest_run_result.json no existe o tiene formato antiguo (solo run_id +
  artifact_root, sin verdict/finished_at), el gate asume OK sin bloquear.
  Esto garantiza que tickets que nunca corrieron antes no se vean afectados.

CLI:
    python rerun_guard.py --ticket 122 --check
        → JSON del resultado sin modificar estado

    python rerun_guard.py --ticket 122 --reset --confirm
        → Elimina latest_run_result.json (uso debug, NO para producción)

Dependencias: solo stdlib (json, pathlib, datetime, argparse, time).
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.rerun_guard")

# ── Constantes ─────────────────────────────────────────────────────────────────

_TOOL_ROOT = Path(__file__).parent

# TTL de cooldown en segundos (default 10 minutos). Configurable vía env var.
_DEFAULT_COOLDOWN_TTL_S: int = 600

# Nombre del archivo de resultado del último run (escrito por el pipeline al finalizar).
# Separado de latest.json (que solo apunta al run_id) para no romper el índice existente.
_LATEST_RESULT_FILENAME = "latest_run_result.json"

# Categorías que activan el cooldown. Solo ENV: bloqueos transitorios del ambiente.
# APP (fallo funcional real) y PIP (problema de pipeline) permiten reruns inmediatos.
_COOLDOWN_CATEGORIES: frozenset[str] = frozenset({"ENV"})

# Reasons de bloqueo que activan cooldown. Si hay una ENV/OK (improbable) no bloqueamos.
_COOLDOWN_VERDICTS: frozenset[str] = frozenset({"BLOCKED"})

# Texto de ayuda por reason de bloqueo previo
_HUMAN_HINTS: dict[str, str] = {
    "MISSING_CREDENTIALS": (
        "Configurar las variables de entorno AGENDA_WEB_USER y AGENDA_WEB_PASS "
        "antes de relanzar. Ejemplo: "
        "set AGENDA_WEB_USER=mi_usuario && set AGENDA_WEB_PASS=mi_clave"
    ),
    "AUTH_NOT_AVAILABLE": (
        "AgendaWeb no responde. Verificar que el servidor está corriendo "
        "en http://localhost:35017/AgendaWeb/ antes de relanzar."
    ),
    "AUTH_LOGIN_TIMEOUT": (
        "El login programático superó el timeout. "
        "La aplicación puede estar iniciando lentamente. "
        "Esperá ~30 segundos y verificá que AgendaWeb responde antes de relanzar."
    ),
    "AUTH_CREDENTIALS_INVALID": (
        "Las credenciales son inválidas — el login falló. "
        "Verificar AGENDA_WEB_USER / AGENDA_WEB_PASS contra FrmLogin.aspx."
    ),
    "PREFLIGHT_ERROR": (
        "El preflight de ambiente falló. "
        "Verificar que AgendaWeb está corriendo y accesible antes de relanzar."
    ),
    "DEPLOYMENT_MISMATCH": (
        "El build activo no coincide con el esperado. "
        "Desplegar el build correcto o actualizar QA_UAT_EXPECTED_BUILD_ID."
    ),
    "BUILD_UNVERIFIABLE": (
        "No se puede verificar el build activo. "
        "Desplegar un build verificable o configurar policy=soft."
    ),
}

_TOOL_VERSION = "1.0.0"


# ── Resultado ──────────────────────────────────────────────────────────────────

@dataclass
class RerunGuardResult:
    ok: bool
    verdict: str                        # "OK" | "BLOCKED" | "OK_OVERRIDE"
    category: Optional[str]            # "OPS" si bloquea, None si permite
    reason: str                         # ver contrato de salida
    stage: str = "rerun_guard"
    cooldown_active: bool = False
    cooldown_remaining_s: int = 0
    previous_run_id: Optional[str] = None
    previous_verdict: Optional[str] = None
    previous_reason: Optional[str] = None
    previous_finished_at: Optional[str] = None
    forced: bool = False
    elapsed_ms: int = 0
    human_action_required: Optional[str] = None
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_event(self) -> dict:
        """Forma compacta para emission en execution.jsonl."""
        return {
            "event": "rerun_guard",
            "verdict": self.verdict,
            "category": self.category,
            "reason": self.reason,
            "cooldown_active": self.cooldown_active,
            "cooldown_remaining_s": self.cooldown_remaining_s,
            "previous_run_id": self.previous_run_id,
            "previous_verdict": self.previous_verdict,
            "previous_reason": self.previous_reason,
            "forced": self.forced,
            "elapsed_ms": self.elapsed_ms,
        }


# ── Helpers de lectura de estado previo ───────────────────────────────────────

def _read_latest_result(ticket_id: int, evidence_root: Optional[Path] = None) -> dict:
    """Lee latest_run_result.json del directorio del ticket.

    Retorna el dict del archivo, o {} si no existe / es inválido / formato antiguo.
    Nunca lanza excepciones — la ausencia de latest siempre resulta en OK.
    """
    root = evidence_root or (_TOOL_ROOT / "evidence")
    result_path = root / str(ticket_id) / _LATEST_RESULT_FILENAME
    if not result_path.is_file():
        return {}
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        # Formato mínimo para que sea útil: necesita verdict y finished_at
        if "verdict" not in data or "finished_at" not in data:
            return {}
        return data
    except Exception as exc:
        logger.debug("[rerun_guard] No se pudo leer %s: %s", result_path, exc)
        return {}


def _parse_iso8601(s: str) -> Optional[datetime.datetime]:
    """Parsea una cadena ISO 8601 UTC a datetime. Retorna None si falla."""
    if not s:
        return None
    try:
        # Python 3.7+ soporta fromisoformat pero no 'Z' como sufijo hasta 3.11
        s_clean = s.replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(s_clean)
    except Exception:
        return None


def _elapsed_since(finished_at_str: str) -> Optional[float]:
    """Retorna segundos transcurridos desde finished_at_str hasta ahora (UTC).

    Retorna None si el string no se puede parsear.
    """
    dt = _parse_iso8601(finished_at_str)
    if dt is None:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    # Asegurar que dt sea tz-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    delta = (now - dt).total_seconds()
    return max(delta, 0.0)  # nunca negativo por skew de reloj


def _get_cooldown_ttl_s() -> int:
    """Lee QA_UAT_RERUN_COOLDOWN_S del entorno, con default 600."""
    import os
    raw = os.environ.get("QA_UAT_RERUN_COOLDOWN_S", "").strip()
    try:
        val = int(raw)
        return val if val > 0 else _DEFAULT_COOLDOWN_TTL_S
    except (ValueError, TypeError):
        return _DEFAULT_COOLDOWN_TTL_S


def _build_human_action(
    previous_reason: Optional[str],
    previous_run_id: Optional[str],
    cooldown_remaining_s: int,
    cooldown_ttl_s: int,
) -> str:
    """Construye el mensaje accionable completo para el operador."""
    hint = _HUMAN_HINTS.get(previous_reason or "", "Investigar el bloqueo previo antes de relanzar.")
    minutes_remaining = cooldown_remaining_s // 60
    seconds_remaining = cooldown_remaining_s % 60

    if minutes_remaining > 0:
        time_str = f"{minutes_remaining}m {seconds_remaining}s"
    else:
        time_str = f"{seconds_remaining}s"

    lines = [
        f"El run anterior ({previous_run_id or 'desconocido'}) terminó en el mismo bloqueo "
        f"hace menos de {cooldown_ttl_s // 60} min.",
        f"Tiempo restante del cooldown: {time_str}.",
        hint,
        "Para forzar el rerun de todas formas: agregar --force-rerun al comando.",
    ]
    return " | ".join(lines)


# ── Lógica principal ──────────────────────────────────────────────────────────

def run_rerun_guard(
    ticket_id: int,
    force_rerun: bool = False,
    current_fingerprint: Optional[str] = None,
    evidence_root: Optional[Path] = None,
    exec_log=None,
) -> RerunGuardResult:
    """Ejecuta el gate de rerun y retorna RerunGuardResult.

    Parámetros
    ----------
    ticket_id : int
        ID del ticket QA UAT.
    force_rerun : bool
        Si True, siempre permite (loguea forced=True).
    current_fingerprint : str, optional
        Fingerprint del build actual (hash del deployment). Si difiere del
        previo, se permite el rerun aunque esté en cooldown.
    evidence_root : Path, optional
        Directorio raíz de evidence/ (para tests — sobreescribe el default).
    exec_log : ExecutionLogger, optional
        Logger activo para emitir el evento rerun_guard en execution.jsonl.

    Retorna
    -------
    RerunGuardResult con todos los campos del contrato de salida.
    """
    started = time.time()
    cooldown_ttl_s = _get_cooldown_ttl_s()

    def _ok_result(reason: str, forced: bool = False, **kwargs) -> RerunGuardResult:
        verdict = "OK_OVERRIDE" if forced else "OK"
        r = RerunGuardResult(
            ok=True,
            verdict=verdict,
            category=None,
            reason=reason,
            forced=forced,
            elapsed_ms=int((time.time() - started) * 1000),
            **kwargs,
        )
        _emit_event(exec_log, r)
        return r

    def _blocked_result(
        previous_run_id: str,
        previous_verdict: str,
        previous_reason: str,
        previous_finished_at: str,
        cooldown_remaining_s: int,
    ) -> RerunGuardResult:
        human_action = _build_human_action(
            previous_reason, previous_run_id, cooldown_remaining_s, cooldown_ttl_s
        )
        r = RerunGuardResult(
            ok=False,
            verdict="BLOCKED",
            category="OPS",
            reason="PREVIOUS_RUN_SAME_VERDICT",
            cooldown_active=True,
            cooldown_remaining_s=cooldown_remaining_s,
            previous_run_id=previous_run_id,
            previous_verdict=previous_verdict,
            previous_reason=previous_reason,
            previous_finished_at=previous_finished_at,
            forced=False,
            elapsed_ms=int((time.time() - started) * 1000),
            human_action_required=human_action,
            message=(
                f"Cooldown activo: el run {previous_run_id!r} terminó en "
                f"BLOCKED/ENV/{previous_reason} hace menos de "
                f"{cooldown_ttl_s // 60} min y nada cambió en el ambiente."
            ),
        )
        _emit_event(exec_log, r)
        return r

    # ── 1. Override: --force-rerun ─────────────────────────────────────────────
    if force_rerun:
        logger.info("[rerun_guard] --force-rerun activo — gate omitido (forced=True)")
        return _ok_result("FORCED_RERUN", forced=True)

    # ── 2. Leer resultado del último run ───────────────────────────────────────
    latest = _read_latest_result(ticket_id, evidence_root)
    if not latest:
        # No hay registro previo o formato inválido — primer run o ticket nuevo
        return _ok_result("FIRST_RUN" if not latest else "NO_LATEST_RESULT")

    # ── 3. Verificar que el run previo terminó en BLOCKED/ENV ─────────────────
    prev_verdict = latest.get("verdict", "")
    prev_category = latest.get("category", "")
    prev_reason = latest.get("reason", "")
    prev_run_id = latest.get("run_id", "unknown")
    prev_finished_at = latest.get("finished_at", "")
    prev_fingerprint = latest.get("deployment_fingerprint")

    if prev_verdict not in _COOLDOWN_VERDICTS or prev_category not in _COOLDOWN_CATEGORIES:
        # El run previo fue PASS, FAIL funcional (APP), o PIP → rerun siempre OK
        logger.debug(
            "[rerun_guard] run previo %r: verdict=%s/category=%s → no activa cooldown",
            prev_run_id, prev_verdict, prev_category,
        )
        return _ok_result(
            "VERDICT_NOT_ENV",
            previous_run_id=prev_run_id,
            previous_verdict=prev_verdict,
            previous_reason=prev_reason,
            previous_finished_at=prev_finished_at,
        )

    # ── 4. Verificar TTL del cooldown ─────────────────────────────────────────
    elapsed_s = _elapsed_since(prev_finished_at)
    if elapsed_s is None:
        # No se puede parsear la fecha — dar beneficio de la duda → OK
        logger.debug("[rerun_guard] No se pudo parsear finished_at=%r — OK por defecto", prev_finished_at)
        return _ok_result(
            "NO_LATEST_RESULT",
            previous_run_id=prev_run_id,
            previous_verdict=prev_verdict,
            previous_reason=prev_reason,
        )

    if elapsed_s >= cooldown_ttl_s:
        # TTL expirado → permitir
        logger.info(
            "[rerun_guard] TTL expirado para %r (%.0fs >= %ss) → OK",
            prev_run_id, elapsed_s, cooldown_ttl_s,
        )
        return _ok_result(
            "TTL_EXPIRED",
            previous_run_id=prev_run_id,
            previous_verdict=prev_verdict,
            previous_reason=prev_reason,
            previous_finished_at=prev_finished_at,
        )

    # ── 5. Verificar cambio de fingerprint ────────────────────────────────────
    if (
        current_fingerprint is not None
        and prev_fingerprint is not None
        and current_fingerprint != prev_fingerprint
        and prev_fingerprint != "NO_EXPECTED_BUILD_DEFINED"
    ):
        logger.info(
            "[rerun_guard] Fingerprint cambió (%r → %r) → OK",
            prev_fingerprint, current_fingerprint,
        )
        return _ok_result(
            "FINGERPRINT_CHANGED",
            previous_run_id=prev_run_id,
            previous_verdict=prev_verdict,
            previous_reason=prev_reason,
            previous_finished_at=prev_finished_at,
        )

    # ── 6. Cooldown activo — BLOQUEAR ─────────────────────────────────────────
    cooldown_remaining_s = max(0, int(cooldown_ttl_s - elapsed_s))
    logger.warning(
        "[rerun_guard] BLOCKED: run previo %r en BLOCKED/ENV/%s hace %.0fs, "
        "cooldown restante: %ds",
        prev_run_id, prev_reason, elapsed_s, cooldown_remaining_s,
    )
    return _blocked_result(
        previous_run_id=prev_run_id,
        previous_verdict=prev_verdict,
        previous_reason=prev_reason,
        previous_finished_at=prev_finished_at,
        cooldown_remaining_s=cooldown_remaining_s,
    )


# ── Escritura del resultado del run en latest_run_result.json ─────────────────

def write_run_result(
    ticket_id: int,
    run_id: str,
    verdict: str,
    category: Optional[str],
    reason: Optional[str],
    finished_at: Optional[str] = None,
    deployment_fingerprint: Optional[str] = None,
    evidence_root: Optional[Path] = None,
) -> None:
    """Escribe (o sobreescribe) latest_run_result.json para el ticket.

    Llamado por el pipeline al finalizar cada run, independientemente del
    resultado. Si falla la escritura, se loguea un warning pero no se propaga
    (el pipeline no debe fallar por un error de indexado).

    Parámetros
    ----------
    ticket_id : int
    run_id : str
    verdict : str          "OK" | "BLOCKED" | "PASS" | "FAIL" | "MIXED"
    category : str | None  "ENV" | "APP" | "PIP" | etc.
    reason : str | None    Razón del bloqueo/fallo.
    finished_at : str      ISO 8601 UTC (default: ahora).
    deployment_fingerprint : str | None
        Hash o ID del build activo al momento del run.
    evidence_root : Path | None
        Sobreescritura para tests.
    """
    root = evidence_root or (_TOOL_ROOT / "evidence")
    ticket_dir = root / str(ticket_id)
    result_path = ticket_dir / _LATEST_RESULT_FILENAME

    if finished_at is None:
        finished_at = (
            datetime.datetime.now(datetime.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    data = {
        "run_id": run_id,
        "verdict": verdict,
        "category": category,
        "reason": reason,
        "finished_at": finished_at,
        "deployment_fingerprint": deployment_fingerprint,
        "tool_version": _TOOL_VERSION,
    }

    try:
        ticket_dir.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug("[rerun_guard] latest_run_result.json actualizado: %s", result_path)
    except Exception as exc:
        logger.warning("[rerun_guard] No se pudo escribir %s: %s", result_path, exc)


# ── Helpers internos ──────────────────────────────────────────────────────────

def _emit_event(exec_log, result: RerunGuardResult) -> None:
    """Emite el evento rerun_guard al ExecutionLogger si está disponible."""
    if exec_log is None:
        return
    try:
        exec_log.event("rerun_guard", result.to_event())
    except Exception as exc:
        logger.debug("[rerun_guard] No se pudo emitir evento rerun_guard: %s", exc)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description=(
            "rerun_guard — gate contra reruns repetidos sin cambio de ambiente. "
            "Reporta si el pipeline permitiría o bloquearía un nuevo run para el ticket."
        )
    )
    p.add_argument("--ticket", type=int, required=True, help="ID del ticket QA UAT")
    p.add_argument(
        "--check",
        action="store_true",
        help="Reporta el veredicto sin modificar estado (read-only)",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Elimina latest_run_result.json (uso debug/desarrollo, "
            "NO para producción). Requiere --confirm."
        ),
    )
    p.add_argument(
        "--confirm",
        action="store_true",
        help="Confirma operaciones destructivas (requerido por --reset).",
    )
    p.add_argument(
        "--force-rerun",
        action="store_true",
        dest="force_rerun",
        help="Simula --force-rerun (permite aunque haya cooldown activo).",
    )
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG, stream=sys.stderr,
            format="%(levelname)s %(name)s: %(message)s",
        )
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    if args.reset:
        if not args.confirm:
            sys.stderr.write(
                "error: --reset requiere --confirm para evitar borrados accidentales.\n"
                "Uso: python rerun_guard.py --ticket <N> --reset --confirm\n"
            )
            sys.exit(1)
        result_path = _TOOL_ROOT / "evidence" / str(args.ticket) / _LATEST_RESULT_FILENAME
        if result_path.is_file():
            result_path.unlink()
            print(json.dumps(
                {"ok": True, "action": "reset", "deleted": str(result_path)},
                ensure_ascii=False, indent=2,
            ))
        else:
            print(json.dumps(
                {"ok": True, "action": "reset", "deleted": None, "message": "El archivo no existía"},
                ensure_ascii=False, indent=2,
            ))
        sys.exit(0)

    if args.check or True:  # --check es el único modo útil además de --reset
        result = run_rerun_guard(
            ticket_id=args.ticket,
            force_rerun=args.force_rerun,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
