"""
execution_logger.py — Logger estructurado central para el QA UAT Agent.

Escribe un archivo JSON Lines (execution.jsonl) en el directorio de evidencia
de cada sesión. Cada línea es un evento JSON con timestamp, tipo y payload.

DISEÑO
------
- Un `ExecutionLogger` por sesión (run_id). Se obtiene via `get_logger()`.
- Thread-safe: escritura serializada via threading.Lock.
- Nunca lanza excepciones al exterior — los errores de escritura se silencian.
- Soporta context manager para garantizar `session_end` aunque ocurra error.

EVENTOS REGISTRADOS
-------------------
session_start       inicio de pipeline con todos los parámetros de entrada
session_end         fin de pipeline con resultado y elapsed total
stage_start         comienzo de una stage (reader, ui_map, compiler, etc.)
stage_end           fin de stage con resultado OK/FAIL y duration_ms
stage_error         error fatal en una stage con stack trace
playwright_run_start inicio de ejecución de un spec.ts
playwright_run_end   fin de ejecución de spec.ts con status y duration_ms
playwright_line      cada línea de stdout de Playwright (DEBUG only)
playwright_assertion assertion failure con expected/received
playwright_timeout   timeout de un spec
llm_call            llamada a LLM con modelo, backend, primeros 200 chars del prompt
llm_response        respuesta LLM con duration_ms, tokens estimados, primeros 200 chars
llm_error           error de LLM con razón
screenshot          screenshot capturado (path relativo)
error               cualquier error/exception con stack trace
info                mensaje informativo genérico

FORMATO DE CADA EVENTO
-----------------------
{
  "ts":        "2026-05-06T12:00:00.123456Z",   // UTC ISO 8601
  "session_id": "freeform-20260506-120000",
  "seq":        42,                              // secuencia dentro de la sesión
  "event":      "stage_end",
  "stage":      "runner",                        // cuando aplica
  "scenario_id": "P01",                          // cuando aplica
  "ok":         true,
  "duration_ms": 4321,
  "data":       { ... }                          // payload específico del evento
}

USO
---
    from execution_logger import get_logger, ExecutionLogger

    # Obtener logger para la sesión actual
    log = get_logger("freeform-20260506-120000", evidence_dir=Path("evidence/freeform-..."))

    log.session_start({"intent": "...", "headed": True})

    with log.stage("reader"):
        result = reader_run(...)

    log.session_end({"verdict": "PASS", "elapsed_s": 12.3})

    # Como context manager (garantiza session_end)
    with ExecutionLogger("freeform-...", evidence_dir=Path("...")) as log:
        ...
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

_py_logger = logging.getLogger("stacky.qa_uat.execution_logger")

# Máximo de chars guardados de texto libre (stdout crudo, prompts) por evento.
# Guardar más sobrecarga el JSONL sin valor adicional para debugging.
_MAX_TEXT_CHARS = 8_000
# Máximo de chars guardados de un stack trace completo.
_MAX_STACK_CHARS = 4_000

# Registry global de loggers activos (session_id → ExecutionLogger).
# Permite que módulos sin acceso al objeto recuperen el logger de la sesión actual.
_registry: dict[str, "ExecutionLogger"] = {}
_registry_lock = threading.Lock()


# ── Public API ────────────────────────────────────────────────────────────────

def get_logger(
    session_id: str,
    evidence_dir: Optional[Path] = None,
) -> "ExecutionLogger":
    """
    Obtener o crear el ExecutionLogger para `session_id`.

    Si ya existe en el registry se devuelve el mismo objeto (singleton por sesión).
    Si se pasa `evidence_dir`, se usa como directorio de salida.
    Si no se pasa, se usa evidence/<session_id>/ relativo al directorio de este módulo.
    """
    with _registry_lock:
        if session_id in _registry:
            return _registry[session_id]
        if evidence_dir is None:
            evidence_dir = Path(__file__).parent / "evidence" / session_id
        log = ExecutionLogger(session_id, evidence_dir=evidence_dir)
        _registry[session_id] = log
        return log


def get_active_logger() -> Optional["ExecutionLogger"]:
    """Devuelve el logger más recientemente creado, si existe. Útil desde módulos anidados."""
    with _registry_lock:
        if not _registry:
            return None
        # El último registrado es el más reciente
        return list(_registry.values())[-1]


def close_logger(session_id: str) -> None:
    """Eliminar el logger del registry (libera el file handle)."""
    with _registry_lock:
        log = _registry.pop(session_id, None)
    if log is not None:
        log.close()


# ── Core class ────────────────────────────────────────────────────────────────

class ExecutionLogger:
    """Logger estructurado por sesión. Thread-safe. Nunca lanza al exterior."""

    def __init__(self, session_id: str, evidence_dir: Path) -> None:
        self.session_id = session_id
        self.evidence_dir = evidence_dir
        self._lock = threading.Lock()
        self._seq = 0
        self._fh: Optional[Any] = None  # file handle
        self._closed = False
        self._open()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _open(self) -> None:
        """Abrir (o crear) el archivo de log JSONL."""
        try:
            self.evidence_dir.mkdir(parents=True, exist_ok=True)
            log_path = self.evidence_dir / "execution.jsonl"
            self._fh = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: WPS515
            _py_logger.debug("ExecutionLogger opened: %s", log_path)
        except Exception as exc:  # noqa: BLE001
            _py_logger.warning("ExecutionLogger: cannot open log file: %s", exc)
            self._fh = None

    def close(self) -> None:
        """Cerrar el file handle. Idempotente."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._fh is not None:
                try:
                    self._fh.flush()
                    self._fh.close()
                except Exception:  # noqa: BLE001
                    pass
                self._fh = None

    def __enter__(self) -> "ExecutionLogger":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self.error(
                "session_fatal_error",
                exc=exc_val,
                detail="Unhandled exception in session context manager",
            )
        self.close()

    # ── Write ──────────────────────────────────────────────────────────────────

    def _write(self, event: str, data: dict, **kwargs: Any) -> None:
        """Escribir un evento JSON Lines. Silencioso ante errores."""
        with self._lock:
            self._seq += 1
            seq = self._seq

        record: dict = {
            "ts": _utcnow(),
            "session_id": self.session_id,
            "seq": seq,
            "event": event,
        }
        # Campos opcionales de primer nivel
        for field in ("stage", "scenario_id", "ok", "duration_ms"):
            if field in kwargs:
                record[field] = kwargs[field]
        record["data"] = data

        try:
            line = json.dumps(record, ensure_ascii=False, default=str)
        except Exception as exc:  # noqa: BLE001
            line = json.dumps(
                {"ts": _utcnow(), "session_id": self.session_id, "seq": seq,
                 "event": "_serialize_error", "data": {"error": str(exc)}},
                ensure_ascii=False,
            )

        with self._lock:
            if self._fh is not None and not self._closed:
                try:
                    self._fh.write(line + "\n")
                    self._fh.flush()
                except Exception:  # noqa: BLE001
                    pass

    # ── High-level event methods ───────────────────────────────────────────────

    def session_start(self, params: dict) -> None:
        self._write("session_start", {
            "params": _sanitize(params),
            "pid": os.getpid(),
            "python": sys.version.split()[0],
            "cwd": os.getcwd(),
        })

    def session_end(self, result: dict) -> None:
        self._write("session_end", {
            "ok": result.get("ok"),
            "verdict": result.get("verdict"),
            "elapsed_s": result.get("elapsed_s"),
            "stages_summary": _stages_summary(result.get("stages", {})),
        }, ok=result.get("ok"))

    def stage_start(self, stage: str, params: Optional[dict] = None) -> None:
        self._write("stage_start", {"params": _sanitize(params or {})}, stage=stage)

    def stage_end(
        self,
        stage: str,
        ok: bool,
        duration_ms: int,
        result_summary: Optional[dict] = None,
    ) -> None:
        self._write(
            "stage_end",
            {"result_summary": result_summary or {}},
            stage=stage,
            ok=ok,
            duration_ms=duration_ms,
        )

    def stage_error(self, stage: str, exc: Optional[Exception], message: str = "") -> None:
        self._write(
            "stage_error",
            {
                "message": message,
                "exception": type(exc).__name__ if exc else None,
                "stack": _safe_stack(exc),
            },
            stage=stage,
            ok=False,
        )

    @contextmanager
    def stage(
        self, stage_name: str, params: Optional[dict] = None
    ) -> Generator[None, None, None]:
        """Context manager que envuelve una stage y registra start/end/error."""
        import time as _time
        t0 = _time.time()
        self.stage_start(stage_name, params)
        try:
            yield
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((_time.time() - t0) * 1000)
            self.stage_error(stage_name, exc, str(exc))
            self.stage_end(stage_name, ok=False, duration_ms=duration_ms)
            raise
        else:
            duration_ms = int((_time.time() - t0) * 1000)
            self.stage_end(stage_name, ok=True, duration_ms=duration_ms)

    # ── Playwright events ──────────────────────────────────────────────────────

    def playwright_run_start(
        self,
        scenario_id: str,
        spec_file: str,
        headed: bool,
        timeout_ms: int,
    ) -> None:
        self._write(
            "playwright_run_start",
            {"spec_file": spec_file, "headed": headed, "timeout_ms": timeout_ms},
            scenario_id=scenario_id,
        )

    def playwright_run_end(
        self,
        scenario_id: str,
        status: str,
        duration_ms: int,
        return_code: int,
        assertion_failures: Optional[list] = None,
        reason: Optional[str] = None,
    ) -> None:
        self._write(
            "playwright_run_end",
            {
                "status": status,
                "return_code": return_code,
                "assertion_failures": assertion_failures or [],
                "reason": reason,
            },
            scenario_id=scenario_id,
            ok=(status == "pass"),
            duration_ms=duration_ms,
        )

    def playwright_line(self, scenario_id: str, line: str) -> None:
        """Log de cada línea de stdout de Playwright. Solo si nivel DEBUG activo."""
        if not _py_logger.isEnabledFor(logging.DEBUG):
            return
        self._write(
            "playwright_line",
            {"line": line.rstrip()[:500]},
            scenario_id=scenario_id,
        )

    def playwright_assertion(
        self,
        scenario_id: str,
        expected: str,
        received: str,
        message: str = "",
    ) -> None:
        self._write(
            "playwright_assertion",
            {
                "message": message[:_MAX_TEXT_CHARS],
                "expected": expected[:500],
                "received": received[:500],
            },
            scenario_id=scenario_id,
            ok=False,
        )

    def playwright_timeout(self, scenario_id: str, timeout_ms: int) -> None:
        self._write(
            "playwright_timeout",
            {"timeout_ms": timeout_ms},
            scenario_id=scenario_id,
            ok=False,
        )

    # ── LLM events ────────────────────────────────────────────────────────────

    def llm_call(
        self,
        model: str,
        backend: str,
        system_preview: str,
        user_preview: str,
        max_tokens: int,
        call_site: str = "",
    ) -> None:
        self._write(
            "llm_call",
            {
                "model": model,
                "backend": backend,
                "max_tokens": max_tokens,
                "call_site": call_site,
                "system_preview": _redact(system_preview)[:_MAX_TEXT_CHARS],
                "user_preview": _redact(user_preview)[:_MAX_TEXT_CHARS],
            },
        )

    def llm_response(
        self,
        model: str,
        backend: str,
        duration_ms: int,
        text_preview: str,
        estimated_tokens: Optional[int] = None,
    ) -> None:
        self._write(
            "llm_response",
            {
                "model": model,
                "backend": backend,
                "duration_ms": duration_ms,
                "estimated_tokens": estimated_tokens,
                "text_preview": text_preview[:_MAX_TEXT_CHARS],
            },
            ok=True,
            duration_ms=duration_ms,
        )

    def llm_error(self, model: str, backend: str, error: str) -> None:
        self._write(
            "llm_error",
            {"model": model, "backend": backend, "error": error[:1000]},
            ok=False,
        )

    # ── Generic ───────────────────────────────────────────────────────────────

    def screenshot(
        self,
        path: str,
        scenario_id: Optional[str] = None,
        label: str = "",
    ) -> None:
        kw: dict = {}
        if scenario_id:
            kw["scenario_id"] = scenario_id
        self._write("screenshot", {"path": path, "label": label}, **kw)

    def info(self, message: str, **extra: Any) -> None:
        self._write("info", {"message": message, **{k: str(v) for k, v in extra.items()}})

    def error(
        self,
        code: str,
        exc: Optional[Exception] = None,
        detail: str = "",
        stage: Optional[str] = None,
        scenario_id: Optional[str] = None,
    ) -> None:
        kw: dict = {"ok": False}
        if stage:
            kw["stage"] = stage
        if scenario_id:
            kw["scenario_id"] = scenario_id
        self._write(
            "error",
            {
                "code": code,
                "detail": detail,
                "exception": type(exc).__name__ if exc else None,
                "stack": _safe_stack(exc),
            },
            **kw,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


_REDACT_PATTERNS = (
    "password", "pass", "token", "secret", "credential",
    "AGENDA_WEB_PASS", "GH_TOKEN", "GITHUB_TOKEN", "COPILOT_TOKEN",
)


def _redact(text: str) -> str:
    """Reemplaza valores de variables sensibles por [REDACTED]."""
    import re
    for pattern in _REDACT_PATTERNS:
        text = re.sub(
            rf"({re.escape(pattern)}\s*[=:]\s*)([^\s\"']+)",
            r"\1[REDACTED]",
            text,
            flags=re.IGNORECASE,
        )
    return text


def _sanitize(params: dict) -> dict:
    """Eliminar/redactar claves sensibles de un dict de parámetros."""
    safe = {}
    for k, v in params.items():
        if any(p in k.lower() for p in ("password", "pass", "token", "secret", "credential")):
            safe[k] = "[REDACTED]"
        else:
            safe[k] = v
    return safe


def _safe_stack(exc: Optional[Exception]) -> str:
    if exc is None:
        return ""
    try:
        return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[
            :_MAX_STACK_CHARS
        ]
    except Exception:  # noqa: BLE001
        return repr(exc)[:500]


def _stages_summary(stages: dict) -> dict:
    """Resumen compacto de stages para session_end."""
    return {
        name: {
            "ok": info.get("ok"),
            "skipped": info.get("skipped", False),
        }
        for name, info in stages.items()
    }
