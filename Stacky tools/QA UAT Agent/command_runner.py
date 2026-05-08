"""
command_runner.py — Wrapper forense de comandos subprocess para QA UAT Agent.

PRINCIPIO: Ningún módulo de QA UAT Agent debe llamar subprocess.run,
           subprocess.Popen u os.system directamente.
           Todo comando externo debe pasar por CommandRunner.run_logged().

Registra por cada comando:
  - command.started (intent)
  - command.stdout (cada línea, con redacción)
  - command.stderr (cada línea, con redacción)
  - command.completed | command.failed

Produce archivos físicos en:
  <run_dir>/command_logs/
  ├── 0001_command.json   → metadata + env redactado
  ├── 0001_stdout.log     → stdout crudo (redactado)
  └── 0001_stderr.log     → stderr crudo (redactado)

Thread-safe. Nunca silencia errores del comando — solo los registra.

Uso:
    from command_runner import CommandRunner

    runner = CommandRunner(run_dir=Path("evidence/70/uat-70-..."),
                           forensic_log=log,  # ForensicEventLogger
                           stage="publisher")

    result = runner.run_logged(
        cmd=["python", "ado.py", "comment", "70", "--text", "foo"],
        label="ado_add_comment",
        cwd=Path("../ADO Manager"),
        timeout_s=30,
        capture_output=True,
    )
    # result: { "ok": bool, "returncode": int, "stdout": str, "stderr": str,
    #           "duration_ms": int, "command_id": str, "event_ids": {...} }
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence, Union

from redactor import redact_env, redact_text

import logging

_py_logger = logging.getLogger("stacky.qa_uat.command_runner")

# Máximo de chars de stdout/stderr guardados en el evento (el log físico guarda todo)
_MAX_INLINE_CHARS = 2_000
# Cuántas líneas máximas guardamos en eventos de stdout/stderr individuales
_MAX_LINE_EVENTS = 500


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class CommandRunner:
    """
    Ejecuta comandos externos con logging forense completo.

    Cada instancia es configurada para un stage y run específicos.
    Es reutilizable (puede ejecutar múltiples comandos).
    """

    def __init__(
        self,
        run_dir: Path,
        stage: str,
        forensic_log: Any = None,   # ForensicEventLogger opcional
        run_id: str = "",
        ticket_id: Any = "",
    ) -> None:
        self.run_dir = run_dir
        self.stage = stage
        self.forensic_log = forensic_log
        self.run_id = run_id
        self.ticket_id = ticket_id
        self._lock = threading.Lock()
        self._cmd_counter = 0
        self._logs_dir = run_dir / "command_logs"
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        self._load_existing_counter()

    def _load_existing_counter(self) -> None:
        """Detectar el mayor índice existente para continuar la numeración."""
        max_n = 0
        for f in self._logs_dir.glob("*_command.json"):
            try:
                n = int(f.stem.split("_")[0])
                if n > max_n:
                    max_n = n
            except (ValueError, IndexError):
                pass
        self._cmd_counter = max_n

    def _next_cmd_id(self) -> tuple[int, str]:
        with self._lock:
            self._cmd_counter += 1
            n = self._cmd_counter
        return n, f"cmd_{n:04d}"

    # ── run_logged ─────────────────────────────────────────────────────────────

    def run_logged(
        self,
        cmd: Union[str, Sequence[str]],
        *,
        label: str = "",
        cwd: Optional[Path] = None,
        env_override: Optional[dict] = None,
        timeout_s: float = 60.0,
        capture_output: bool = True,
        shell: bool = False,
        encoding: str = "utf-8",
        stage: Optional[str] = None,
        log_stdout_lines: bool = True,
        log_stderr_lines: bool = True,
    ) -> dict:
        """
        Ejecutar un comando externo con logging forense completo.

        Parámetros:
          cmd            — lista de args o string (si shell=True)
          label          — nombre semántico para logs (ej: "ado_add_comment")
          cwd            — directorio de trabajo
          env_override   — vars de entorno adicionales (se mezclan con os.environ)
          timeout_s      — timeout en segundos
          capture_output — si True, captura stdout/stderr; si False, los deja en consola
          shell          — si True, ejecuta con shell (evitar cuando sea posible)
          encoding       — encoding para stdout/stderr
          stage          — stage override (por defecto usa self.stage)
          log_stdout_lines — si True, emite eventos por línea de stdout
          log_stderr_lines — si True, emite eventos por línea de stderr

        Devuelve:
          {
            "ok": bool,
            "returncode": int,
            "stdout": str,
            "stderr": str,
            "duration_ms": int,
            "command_id": str,    // "cmd_0001"
            "cmd_seq": int,
            "label": str,
            "event_ids": {
              "started": str,
              "completed_or_failed": str
            }
          }
        """
        effective_stage = stage or self.stage
        seq_n, cmd_id = self._next_cmd_id()

        # Construir env
        base_env = {**os.environ}
        if env_override:
            base_env.update(env_override)
        env_redacted, redacted_keys = redact_env(base_env)

        # Serializar comando para logs (nunca exponer env completo)
        cmd_list = [cmd] if isinstance(cmd, str) else list(cmd)
        cmd_str = " ".join(str(c) for c in cmd_list)

        # Redactar args por si acaso contienen secretos
        cmd_str_safe, _ = redact_text(cmd_str)

        # Metadata del comando
        cmd_meta = {
            "command_id": cmd_id,
            "seq": seq_n,
            "label": label,
            "cmd": cmd_str_safe,
            "cwd": str(cwd or Path.cwd()),
            "shell": shell,
            "timeout_s": timeout_s,
            "run_id": self.run_id,
            "stage": effective_stage,
            "env_redacted_keys": redacted_keys,
            "started_at": _utcnow(),
        }

        # Escribir metadata antes de ejecutar
        cmd_meta_path = self._logs_dir / f"{seq_n:04d}_command.json"
        cmd_meta_path.write_text(
            json.dumps(cmd_meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # ── Emitir command.started ─────────────────────────────────────────────
        started_eid = self._emit_started(
            cmd_id=cmd_id,
            cmd_str=cmd_str_safe,
            label=label,
            cwd=str(cwd or ""),
            stage=effective_stage,
            env_keys=list(env_redacted.keys()),
        )

        t0 = time.monotonic()
        stdout_text = ""
        stderr_text = ""
        returncode = -1
        ok = False
        error_message: Optional[str] = None

        try:
            if capture_output:
                proc = subprocess.run(
                    cmd if shell else cmd_list,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding=encoding,
                    errors="replace",
                    timeout=timeout_s,
                    cwd=str(cwd) if cwd else None,
                    env=base_env,
                    shell=shell,
                )
                stdout_text = proc.stdout or ""
                stderr_text = proc.stderr or ""
                returncode = proc.returncode
            else:
                proc = subprocess.run(
                    cmd if shell else cmd_list,
                    text=True,
                    encoding=encoding,
                    errors="replace",
                    timeout=timeout_s,
                    cwd=str(cwd) if cwd else None,
                    env=base_env,
                    shell=shell,
                )
                returncode = proc.returncode

            ok = (returncode == 0)

        except subprocess.TimeoutExpired as exc:
            error_message = f"Timeout después de {timeout_s}s"
            returncode = -1
            stdout_text = (exc.stdout or b"").decode(encoding, "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr_text = (exc.stderr or b"").decode(encoding, "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        except FileNotFoundError as exc:
            error_message = f"Ejecutable no encontrado: {exc}"
            returncode = -1
        except Exception as exc:
            error_message = f"Error al ejecutar comando: {exc}"
            returncode = -1

        duration_ms = int((time.monotonic() - t0) * 1000)

        # ── Redactar stdout/stderr ─────────────────────────────────────────────
        stdout_safe, _ = redact_text(stdout_text)
        stderr_safe, _ = redact_text(stderr_text)

        # ── Persistir stdout/stderr en archivos físicos ────────────────────────
        stdout_path = self._logs_dir / f"{seq_n:04d}_stdout.log"
        stderr_path = self._logs_dir / f"{seq_n:04d}_stderr.log"
        stdout_path.write_text(stdout_safe, encoding="utf-8")
        stderr_path.write_text(stderr_safe, encoding="utf-8")

        # ── Actualizar metadata con resultado ──────────────────────────────────
        cmd_meta.update({
            "returncode": returncode,
            "duration_ms": duration_ms,
            "ok": ok,
            "stdout_bytes": len(stdout_text.encode("utf-8")),
            "stderr_bytes": len(stderr_text.encode("utf-8")),
            "stdout_lines": stdout_text.count("\n"),
            "stderr_lines": stderr_text.count("\n"),
            "error": error_message,
            "finished_at": _utcnow(),
        })
        cmd_meta_path.write_text(
            json.dumps(cmd_meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # ── Emitir eventos de stdout/stderr (línea a línea, máx _MAX_LINE_EVENTS) ──
        if log_stdout_lines and stdout_safe.strip():
            self._emit_output_lines(
                lines=stdout_safe.splitlines(),
                event_type="command.stdout",
                category="command_stdout",
                stage=effective_stage,
                cmd_id=cmd_id,
                label=label,
                parent_eid=started_eid,
            )

        if log_stderr_lines and stderr_safe.strip():
            self._emit_output_lines(
                lines=stderr_safe.splitlines(),
                event_type="command.stderr",
                category="command_stderr",
                stage=effective_stage,
                cmd_id=cmd_id,
                label=label,
                parent_eid=started_eid,
            )

        # ── Emitir command.completed | command.failed ─────────────────────────
        completed_eid = self._emit_finished(
            cmd_id=cmd_id,
            label=label,
            ok=ok,
            returncode=returncode,
            duration_ms=duration_ms,
            stdout_preview=stdout_safe[:_MAX_INLINE_CHARS],
            stderr_preview=stderr_safe[:_MAX_INLINE_CHARS],
            error=error_message,
            stage=effective_stage,
            causation_event_id=started_eid,
        )

        return {
            "ok": ok,
            "returncode": returncode,
            "stdout": stdout_safe,
            "stderr": stderr_safe,
            "duration_ms": duration_ms,
            "command_id": cmd_id,
            "cmd_seq": seq_n,
            "label": label,
            "error": error_message,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "event_ids": {
                "started": started_eid,
                "completed_or_failed": completed_eid,
            },
        }

    # ── Streaming Popen wrapper ────────────────────────────────────────────────

    def run_streaming(
        self,
        cmd: Union[str, Sequence[str]],
        *,
        label: str = "",
        cwd: Optional[Path] = None,
        env_override: Optional[dict] = None,
        timeout_s: float = 300.0,
        shell: bool = False,
        encoding: str = "utf-8",
        stage: Optional[str] = None,
        on_stdout_line: Optional[Any] = None,   # callback(line: str) opcional
    ) -> dict:
        """
        Ejecutar un comando con streaming de stdout en tiempo real.
        Útil para Playwright y procesos de larga duración.

        Cada línea se registra como evento command.stdout y se pasa a on_stdout_line.
        """
        effective_stage = stage or self.stage
        seq_n, cmd_id = self._next_cmd_id()

        base_env = {**os.environ}
        if env_override:
            base_env.update(env_override)
        env_redacted, redacted_keys = redact_env(base_env)

        cmd_list = [cmd] if isinstance(cmd, str) else list(cmd)
        cmd_str = " ".join(str(c) for c in cmd_list)
        cmd_str_safe, _ = redact_text(cmd_str)

        cmd_meta = {
            "command_id": cmd_id,
            "seq": seq_n,
            "label": label,
            "cmd": cmd_str_safe,
            "cwd": str(cwd or Path.cwd()),
            "shell": shell,
            "timeout_s": timeout_s,
            "run_id": self.run_id,
            "stage": effective_stage,
            "streaming": True,
            "env_redacted_keys": redacted_keys,
            "started_at": _utcnow(),
        }
        cmd_meta_path = self._logs_dir / f"{seq_n:04d}_command.json"
        cmd_meta_path.write_text(
            json.dumps(cmd_meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        started_eid = self._emit_started(
            cmd_id=cmd_id,
            cmd_str=cmd_str_safe,
            label=label,
            cwd=str(cwd or ""),
            stage=effective_stage,
            env_keys=list(env_redacted.keys()),
        )

        stdout_path = self._logs_dir / f"{seq_n:04d}_stdout.log"
        stderr_path = self._logs_dir / f"{seq_n:04d}_stderr.log"

        t0 = time.monotonic()
        captured_lines: list[str] = []
        returncode = -1
        error_message: Optional[str] = None
        line_count = 0

        try:
            proc = subprocess.Popen(
                cmd if shell else cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding=encoding,
                errors="replace",
                bufsize=1,
                cwd=str(cwd) if cwd else None,
                env=base_env,
                shell=shell,
            )

            with open(stdout_path, "a", encoding="utf-8") as stdout_fh, \
                 open(stderr_path, "a", encoding="utf-8") as stderr_fh:

                # Leer stdout línea a línea
                assert proc.stdout is not None
                for raw_line in proc.stdout:
                    line_safe, _ = redact_text(raw_line)
                    stdout_fh.write(line_safe)
                    captured_lines.append(line_safe)
                    line_count += 1

                    if on_stdout_line:
                        try:
                            on_stdout_line(line_safe.rstrip("\n"))
                        except Exception:
                            pass

                    # Emitir evento por línea (solo primeras _MAX_LINE_EVENTS)
                    if line_count <= _MAX_LINE_EVENTS and self.forensic_log:
                        self._emit_line_event(
                            line=line_safe.rstrip("\n"),
                            event_type="command.stdout",
                            category="command_stdout",
                            stage=effective_stage,
                            cmd_id=cmd_id,
                            parent_eid=started_eid,
                        )

                # Leer stderr
                if proc.stderr:
                    stderr_text = proc.stderr.read()
                    stderr_safe, _ = redact_text(stderr_text)
                    stderr_fh.write(stderr_safe)

            proc.wait(timeout=timeout_s)
            returncode = proc.returncode if proc.returncode is not None else -1

        except subprocess.TimeoutExpired:
            error_message = f"Timeout después de {timeout_s}s"
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
            returncode = -1
        except FileNotFoundError as exc:
            error_message = f"Ejecutable no encontrado: {exc}"
        except Exception as exc:
            error_message = f"Error streaming: {exc}"

        duration_ms = int((time.monotonic() - t0) * 1000)
        ok = (returncode == 0)
        stdout_text = "".join(captured_lines)

        cmd_meta.update({
            "returncode": returncode,
            "duration_ms": duration_ms,
            "ok": ok,
            "stdout_lines": line_count,
            "error": error_message,
            "finished_at": _utcnow(),
        })
        cmd_meta_path.write_text(
            json.dumps(cmd_meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        completed_eid = self._emit_finished(
            cmd_id=cmd_id,
            label=label,
            ok=ok,
            returncode=returncode,
            duration_ms=duration_ms,
            stdout_preview=stdout_text[:_MAX_INLINE_CHARS],
            stderr_preview="",
            error=error_message,
            stage=effective_stage,
            causation_event_id=started_eid,
        )

        return {
            "ok": ok,
            "returncode": returncode,
            "stdout": stdout_text,
            "stderr": "",
            "duration_ms": duration_ms,
            "command_id": cmd_id,
            "cmd_seq": seq_n,
            "label": label,
            "error": error_message,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "event_ids": {
                "started": started_eid,
                "completed_or_failed": completed_eid,
            },
        }

    # ── Emit helpers ──────────────────────────────────────────────────────────

    def _emit_started(self, cmd_id: str, cmd_str: str, label: str,
                       cwd: str, stage: str, env_keys: list) -> Optional[str]:
        if self.forensic_log is None:
            return None
        try:
            return self.forensic_log.emit(
                source="subprocess",
                event_type="command.started",
                category="command_started",
                stage=stage,
                action=label or "command",
                status="started",
                level="info",
                message=f"Comando iniciado: {label or cmd_str[:80]}",
                payload={
                    "command_id": cmd_id,
                    "cmd": cmd_str[:500],
                    "cwd": cwd,
                    "env_keys": env_keys[:30],
                    "label": label,
                },
            )
        except Exception:
            return None

    def _emit_finished(self, cmd_id: str, label: str, ok: bool, returncode: int,
                        duration_ms: int, stdout_preview: str, stderr_preview: str,
                        error: Optional[str], stage: str,
                        causation_event_id: Optional[str]) -> Optional[str]:
        if self.forensic_log is None:
            return None
        try:
            return self.forensic_log.emit(
                source="subprocess",
                event_type="command.completed" if ok else "command.failed",
                category="command_completed" if ok else "command_stderr",
                stage=stage,
                action=label or "command",
                status="completed" if ok else "failed",
                level="info" if ok else "error",
                message=f"Comando {'completado' if ok else 'falló'}: {label} (rc={returncode})",
                payload={
                    "command_id": cmd_id,
                    "returncode": returncode,
                    "duration_ms": duration_ms,
                    "stdout_preview": stdout_preview[:500],
                    "stderr_preview": stderr_preview[:500],
                    "error": error,
                    "ok": ok,
                },
                duration_ms=duration_ms,
                causation_event_id=causation_event_id,
            )
        except Exception:
            return None

    def _emit_output_lines(self, lines: list[str], event_type: str, category: str,
                            stage: str, cmd_id: str, label: str,
                            parent_eid: Optional[str]) -> None:
        if self.forensic_log is None:
            return
        for i, line in enumerate(lines[:_MAX_LINE_EVENTS]):
            if not line.strip():
                continue
            self._emit_line_event(
                line=line,
                event_type=event_type,
                category=category,
                stage=stage,
                cmd_id=cmd_id,
                parent_eid=parent_eid,
            )

    def _emit_line_event(self, line: str, event_type: str, category: str,
                          stage: str, cmd_id: str, parent_eid: Optional[str]) -> None:
        if self.forensic_log is None:
            return
        try:
            self.forensic_log.emit(
                source="subprocess",
                event_type=event_type,
                category=category,
                stage=stage,
                action=f"{category}_line",
                status="ok",
                level="debug",
                message=line[:200],
                payload={"command_id": cmd_id, "line": line[:500]},
                parent_event_id=parent_eid,
            )
        except Exception:
            pass
