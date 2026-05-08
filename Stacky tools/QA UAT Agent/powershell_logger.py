"""
powershell_logger.py — Logger de PowerShell con transcript forense para QA UAT Agent.

Cuando QA UAT Agent ejecuta comandos PowerShell:
  1. Activa Start-Transcript en un archivo temporal.
  2. Ejecuta el bloque de comandos.
  3. Para el transcript.
  4. Lee y parsea el transcript.
  5. Persiste eventos por línea relevante.
  6. Redacta secretos.

Archivos de salida:
  <run_dir>/powershell/
  ├── transcript.log          → transcript crudo redactado
  └── transcript.jsonl        → líneas relevantes como eventos

Uso:
    from powershell_logger import PowerShellLogger

    ps_log = PowerShellLogger(run_dir=run_dir, forensic_log=log, stage="publisher")
    result = ps_log.run_script(
        script="Get-Date; Write-Host 'hello'",
        label="check_date",
        timeout_s=30,
    )
    # result: { "ok": bool, "stdout": str, "stderr": str, "duration_ms": int,
    #           "transcript_path": str, "event_ids": {...} }
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from redactor import redact_text

import logging

_py_logger = logging.getLogger("stacky.qa_uat.powershell_logger")

# ── Detectar PowerShell disponible ────────────────────────────────────────────

def _find_powershell() -> Optional[str]:
    """Encontrar el ejecutable de PowerShell disponible."""
    for exe in ("pwsh", "powershell"):
        if shutil.which(exe):
            return exe
    return None


_POWERSHELL_EXE = _find_powershell()


def is_powershell_available() -> bool:
    """Verificar si PowerShell está disponible en el sistema."""
    return _POWERSHELL_EXE is not None


# ── Patrones de transcript ─────────────────────────────────────────────────────

# Líneas de transcript a ignorar (ruido del transcript)
_TRANSCRIPT_IGNORE_RE = re.compile(
    r"^(Windows PowerShell|PowerShell|Copyright|Transcript|====|PSVersion|PS\s*>|$)",
    re.IGNORECASE,
)

# Patrones de error/warning en PowerShell
_PS_ERROR_RE = re.compile(r"^\s*(At line:\d+|Error|Exception|WARNING):", re.IGNORECASE)
_PS_WARNING_RE = re.compile(r"^WARNING:", re.IGNORECASE)


class PowerShellLogger:
    """
    Ejecuta bloques de PowerShell con transcript forense.

    Si PowerShell no está disponible, retorna BLOCKED sin crash.
    """

    def __init__(
        self,
        run_dir: Path,
        stage: str,
        forensic_log: Any = None,
        run_id: str = "",
        ticket_id: Any = "",
    ) -> None:
        self.run_dir = run_dir
        self.stage = stage
        self.forensic_log = forensic_log
        self.run_id = run_id
        self.ticket_id = ticket_id
        self._ps_dir = run_dir / "powershell"
        self._ps_dir.mkdir(parents=True, exist_ok=True)
        self._transcript_jsonl = self._ps_dir / "transcript.jsonl"
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def run_script(
        self,
        script: str,
        *,
        label: str = "",
        timeout_s: float = 60.0,
        cwd: Optional[Path] = None,
        env_override: Optional[dict] = None,
        stage: Optional[str] = None,
    ) -> dict:
        """
        Ejecutar un script PowerShell con transcript y logging forense.

        Si PowerShell no está disponible, retorna blocked sin lanzar excepción.
        Los secretos en stdout/stderr son redactados automáticamente.
        """
        effective_stage = stage or self.stage

        if not _POWERSHELL_EXE:
            msg = "PowerShell no disponible en este sistema"
            _py_logger.warning(msg)
            if self.forensic_log:
                self.forensic_log.emit_warning(effective_stage, msg)
            return {
                "ok": False,
                "reason": "POWERSHELL_NOT_AVAILABLE",
                "stdout": "",
                "stderr": msg,
                "duration_ms": 0,
                "transcript_path": None,
                "event_ids": {},
            }

        # Usar CommandRunner internamente para capturar el proceso
        from command_runner import CommandRunner
        runner = CommandRunner(
            run_dir=self.run_dir,
            stage=effective_stage,
            forensic_log=self.forensic_log,
            run_id=self.run_id,
            ticket_id=self.ticket_id,
        )

        # Crear archivo de transcript temporal
        transcript_log = self._ps_dir / f"transcript_{self._next_seq():03d}.log"

        # Construir script con transcript activado
        wrapped_script = f"""
$transcriptPath = '{str(transcript_log).replace("'", "''")}'
Start-Transcript -Path $transcriptPath -Append -Force | Out-Null
try {{
{script}
}} finally {{
    Stop-Transcript | Out-Null
}}
""".strip()

        import os
        env = {**os.environ}
        if env_override:
            env.update(env_override)

        # Ejecutar PowerShell
        result = runner.run_logged(
            cmd=[_POWERSHELL_EXE, "-NoProfile", "-NonInteractive", "-Command", wrapped_script],
            label=label or "powershell_script",
            cwd=cwd,
            timeout_s=timeout_s,
            capture_output=True,
            stage=effective_stage,
        )

        # Parsear y persistir transcript si existe
        transcript_content = ""
        if transcript_log.exists():
            try:
                raw = transcript_log.read_text(encoding="utf-8", errors="replace")
                # Redactar secretos en el transcript
                transcript_safe, _ = redact_text(raw)
                transcript_content = transcript_safe
                # Sobrescribir con versión redactada
                transcript_log.write_text(transcript_safe, encoding="utf-8")
                # Append a transcript.log consolidado
                consolidated = self._ps_dir / "transcript.log"
                with open(consolidated, "a", encoding="utf-8") as f:
                    f.write(f"\n\n=== {label or 'script'} at {datetime.now(timezone.utc).isoformat()} ===\n")
                    f.write(transcript_safe)
                # Parsear líneas relevantes a eventos
                self._parse_transcript_to_events(
                    transcript_safe,
                    label=label,
                    stage=effective_stage,
                )
            except Exception as exc:
                _py_logger.warning("Error leyendo transcript: %s", exc)

        result["transcript_path"] = str(transcript_log) if transcript_log.exists() else None
        result["transcript_lines"] = transcript_content.count("\n") if transcript_content else 0

        return result

    def _parse_transcript_to_events(self, transcript: str, label: str, stage: str) -> None:
        """
        Parsear transcript de PowerShell y convertir líneas relevantes en eventos JSONL.
        """
        if not transcript.strip():
            return

        lines = transcript.splitlines()
        events_written = 0

        for line in lines:
            stripped = line.strip()
            if not stripped or _TRANSCRIPT_IGNORE_RE.match(stripped):
                continue

            level = "info"
            if _PS_ERROR_RE.match(stripped):
                level = "error"
            elif _PS_WARNING_RE.match(stripped):
                level = "warning"

            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "source": "powershell",
                "stage": stage,
                "label": label,
                "level": level,
                "line": stripped[:500],
            }

            try:
                with open(self._transcript_jsonl, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                events_written += 1
            except Exception:
                pass

            # Emitir evento forense para líneas de error/warning
            if level in ("error", "warning") and self.forensic_log:
                try:
                    self.forensic_log.emit(
                        source="powershell",
                        event_type=f"powershell.{level}",
                        category="error" if level == "error" else "warning",
                        stage=stage,
                        action="powershell_line",
                        status="ok",
                        level=level,
                        message=stripped[:300],
                        payload={"label": label, "line": stripped[:500]},
                    )
                except Exception:
                    pass
