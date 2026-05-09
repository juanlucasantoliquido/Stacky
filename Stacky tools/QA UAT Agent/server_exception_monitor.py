"""
server_exception_monitor.py — Monitor server-side ASP.NET / IIS Express exceptions
during QA UAT test runs.

PROBLEMA
    Playwright ve respuestas HTTP y la consola del browser, pero NO el runtime
    .NET del servidor. Cuando IIS Express crashea (exit code -1) o ASP.NET
    atrapa una SqlException/ArgumentNullException antes de generar la respuesta
    HTTP, el browser muestra un error genérico o nada. El QA no sabe la causa.

QUÉ CAPTURA ESTE TOOL
    Canal 1 — Windows Application Event Log
        ASP.NET 4.x escribe las excepciones no manejadas (las que llegan a
        Application_Error o al módulo HttpRuntime) en el Event Log con
        ProviderName = "ASP.NET 4.0.30319.0".
        Se consulta via PowerShell (sin dependencias extras).

    Canal 2 — IIS Express Failed Request Tracing (opt-in)
        applicationhost.config ya tiene <traceFailedRequestsLogging> configurado
        pero disabled. Si enable_frt=True, este módulo lo habilita al arrancar
        y parsea los archivos XML que IIS genera en TraceLogFiles/.
        IMPORTANTE: requiere reiniciar IIS Express para activarse.

    Canal 3 — Respuesta HTTP del servidor (companion Playwright hook)
        El template Playwright captura el body de respuestas 5xx y extrae el
        stack trace del YSOD HTML. Los resultados llegan via `add_response_body_entry`.

    Canal 4 — request_failed (companion Playwright hook)
        Cuando IIS Express crashea, Playwright emite page.on('requestfailed').
        Los resultados llegan via `add_request_failed_entry`.

    Todos los canales escriben en:
        evidence/<ticket>/<sid>/server_exceptions_<sid>.json

CONTRACT
    Funciones públicas:
        ServerExceptionMonitor(evidence_dir, *, iis_config_path, trace_dir, enable_frt)
        .start()            — registra baseline del Event Log
        .collect()          — lee eventos nuevos y parsea FRT XMLs
        .dump(scenario_id)  — escribe server_exceptions_<sid>.json
        .add_response_body_entry(...)  — agrega captura HTTP del template
        .add_request_failed_entry(...) — agrega captura de crash HTTP del template

CLI
    # Leer eventos recientes sin correr un test:
    python server_exception_monitor.py --dump-recent --since-minutes 5

    # Habilitar FRT en applicationhost.config (solo modifica el XML, no reinicia IIS):
    python server_exception_monitor.py --enable-frt

NOTA DE SEGURIDAD
    Este módulo lee (y opcionalmente modifica) applicationhost.config.
    La modificación de applicationhost.config con --enable-frt requiere que
    IIS Express esté detenido o se reinicie después para aplicar el cambio.
    Nunca se conecta a BD ni envía datos fuera del equipo local.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.server_exception_monitor")

_TOOL_VERSION = "1.0.0"

# IIS Express applicationhost.config default location
_DEFAULT_IIS_CONFIG = Path(
    os.environ.get(
        "STACKY_IIS_CONFIG",
        Path(os.path.expandvars(
            r"%USERPROFILE%\OneDrive - UBIMIA\Documentos\IISExpress\config\applicationhost.config"
        )).as_posix(),
    )
)

_DEFAULT_TRACE_DIR = Path(
    os.environ.get(
        "STACKY_IIS_TRACE_DIR",
        Path(os.path.expandvars(
            r"%USERPROFILE%\OneDrive - UBIMIA\Documentos\IISExpress\TraceLogFiles"
        )).as_posix(),
    )
)

# ASP.NET Event Log provider names (all known variants)
_ASPNET_PROVIDERS = [
    "ASP.NET 4.0.30319.0",
    "ASP.NET 2.0.50727.0",
    "ASP.NET",
    "System.Web",
]

# ThreadAbortException es NORMAL en WebForms (Response.Redirect usa esto internamente).
# Lo excluimos del output para no generar falsos positivos.
_IGNORE_EXCEPTION_TYPES = {
    "System.Threading.ThreadAbortException",
}


# ── Main class ────────────────────────────────────────────────────────────────

class ServerExceptionMonitor:
    """Monitor de excepciones server-side durante un test QA UAT."""

    def __init__(
        self,
        evidence_dir: Path,
        *,
        iis_config_path: Optional[Path] = None,
        trace_dir: Optional[Path] = None,
        enable_frt: bool = False,
    ) -> None:
        self.evidence_dir = Path(evidence_dir)
        self.iis_config_path = iis_config_path or _DEFAULT_IIS_CONFIG
        self.trace_dir = trace_dir or _DEFAULT_TRACE_DIR
        self.enable_frt = enable_frt

        self._baseline_record_id: int = 0
        self._baseline_trace_files: set[str] = set()
        self._entries: list[dict] = []
        self._lock = threading.Lock()
        self._started = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Registra el estado inicial antes del test."""
        self._baseline_record_id = _get_event_log_high_watermark()
        self._baseline_trace_files = _get_trace_file_set(self.trace_dir)
        if self.enable_frt:
            _enable_failed_request_tracing(self.iis_config_path)
        self._started = True
        logger.info(
            "ServerExceptionMonitor started. EventLog baseline record_id=%d, "
            "trace_files_baseline=%d",
            self._baseline_record_id,
            len(self._baseline_trace_files),
        )

    def collect(self) -> list[dict]:
        """Lee todas las excepciones ocurridas desde start()."""
        if not self._started:
            logger.warning("collect() called before start() — no baseline, returning empty")
            return []

        new_entries: list[dict] = []

        # Canal 1: Windows Event Log
        evlog_entries = _read_event_log_since(self._baseline_record_id)
        for e in evlog_entries:
            parsed = _parse_eventlog_entry(e)
            if parsed:
                new_entries.append(parsed)

        # Canal 2: IIS Express Failed Request Tracing (if enabled)
        if self.enable_frt:
            new_trace_files = _get_trace_file_set(self.trace_dir) - self._baseline_trace_files
            for tf in sorted(new_trace_files):
                parsed = _parse_frt_xml(Path(tf))
                if parsed:
                    new_entries.append(parsed)

        with self._lock:
            self._entries.extend(new_entries)

        return list(self._entries)

    def dump(self, scenario_id: str) -> Path:
        """Escribe evidence/<ticket>/<sid>/server_exceptions_<sid>.json."""
        scenario_dir = self.evidence_dir / scenario_id
        scenario_dir.mkdir(parents=True, exist_ok=True)
        out_path = scenario_dir / f"server_exceptions_{scenario_id}.json"
        with self._lock:
            data = list(self._entries)
        out_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("ServerExceptionMonitor dump: %d entries → %s", len(data), out_path)
        return out_path

    # ── Companion hooks (called by Playwright template via Python bridge) ──────

    def add_response_body_entry(
        self,
        *,
        step_index: int,
        status: int,
        url: str,
        body_snippet: str,
        exception_type: Optional[str] = None,
        exception_message: Optional[str] = None,
        stack_trace_snippet: Optional[str] = None,
    ) -> None:
        """Agrega una excepción capturada del body de una respuesta HTTP 5xx."""
        entry = {
            "source": "http_response_body",
            "step_index": step_index,
            "status": status,
            "url": url,
            "body_snippet": body_snippet[:400] if body_snippet else "",
            "exception_type": exception_type,
            "exception_message": exception_message,
            "stack_trace_snippet": stack_trace_snippet[:600] if stack_trace_snippet else None,
            "captured_at": _now_iso(),
        }
        with self._lock:
            self._entries.append(entry)

    def add_request_failed_entry(
        self,
        *,
        step_index: int,
        url: str,
        error_text: str,
    ) -> None:
        """Agrega una falla de request (IIS crash, connection refused, etc.)."""
        entry = {
            "source": "request_failed",
            "step_index": step_index,
            "url": url,
            "error_text": error_text[:300],
            "captured_at": _now_iso(),
        }
        with self._lock:
            self._entries.append(entry)


# ── Windows Event Log ─────────────────────────────────────────────────────────

def _get_event_log_high_watermark() -> int:
    """Devuelve el RecordId del último evento en el Application Event Log."""
    ps = r"""
$rec = Get-WinEvent -LogName Application -MaxEvents 1 -ErrorAction SilentlyContinue
if ($rec) { $rec.RecordId } else { 0 }
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        text = result.stdout.strip()
        return int(text) if text.isdigit() else 0
    except Exception as exc:
        logger.warning("Could not get event log watermark: %s", exc)
        return 0


def _read_event_log_since(record_id: int) -> list[dict]:
    """Lee eventos del Application Event Log más recientes que record_id."""
    if record_id <= 0:
        # Si no hay baseline, solo los últimos 20 eventos de la sesión actual
        where_clause = "Where-Object { $_.LevelDisplayName -ne 'Information' }"
        max_events = "-MaxEvents 20"
    else:
        where_clause = f"Where-Object {{ $_.RecordId -gt {record_id} -and $_.LevelDisplayName -ne 'Information' }}"
        max_events = ""

    ps = f"""
$events = Get-WinEvent -LogName Application {max_events} -ErrorAction SilentlyContinue |
    {where_clause} |
    Select-Object RecordId, TimeCreated, ProviderName, LevelDisplayName, Id, Message
if ($events) {{
    $events | ConvertTo-Json -Depth 2 -Compress
}} else {{
    '[]'
}}
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=20,
        )
        text = (result.stdout or "").strip()
        if not text:
            return []
        parsed = json.loads(text)
        # PowerShell devuelve objeto (no array) cuando hay un solo item
        if isinstance(parsed, dict):
            parsed = [parsed]
        return parsed if isinstance(parsed, list) else []
    except Exception as exc:
        logger.warning("Could not read event log: %s", exc)
        return []


def _parse_eventlog_entry(entry: dict) -> Optional[dict]:
    """Convierte un entry del Event Log al schema interno. None si es ruido."""
    provider = str(entry.get("ProviderName", ""))
    message = str(entry.get("Message", ""))

    # Filtrar por provider ASP.NET / iisexpress
    is_aspnet = any(p.lower() in provider.lower() for p in _ASPNET_PROVIDERS)
    is_iis = "iisexpress" in provider.lower() or "iis express" in provider.lower()
    if not (is_aspnet or is_iis):
        return None

    # Extraer tipo de excepción del mensaje
    exc_type = _extract_exception_type(message)

    # Ignorar ThreadAbortException (normal en WebForms)
    if exc_type in _IGNORE_EXCEPTION_TYPES:
        return None

    # TimeCreated puede ser un dict de PowerShell serialization
    time_created = entry.get("TimeCreated")
    if isinstance(time_created, dict):
        # PowerShell DateTime → "/Date(milliseconds)/"
        val = str(time_created.get("value", time_created.get("Value", "")))
        time_created = val
    else:
        time_created = str(time_created or "")

    return {
        "source": "event_log",
        "record_id": entry.get("RecordId"),
        "time_created": time_created,
        "provider": provider,
        "level": entry.get("LevelDisplayName", ""),
        "event_id": entry.get("Id"),
        "exception_type": exc_type,
        "message": message[:600],
        "captured_at": _now_iso(),
    }


def _extract_exception_type(text: str) -> Optional[str]:
    """Extrae el tipo de excepción de un texto de Event Log o stack trace."""
    if not text:
        return None
    # Patrón: "System.Data.SqlClient.SqlException" etc.
    m = re.search(
        r"\b(System(?:\.\w+)+Exception|Microsoft(?:\.\w+)+Exception)\b",
        text,
    )
    if m:
        return m.group(1)
    # Patrón genérico: "XXXException"
    m2 = re.search(r"\b(\w+Exception)\b", text)
    if m2:
        return m2.group(1)
    return None


# ── IIS Express Failed Request Tracing ───────────────────────────────────────

def _get_trace_file_set(trace_dir: Path) -> set[str]:
    """Devuelve el conjunto de archivos .xml existentes en trace_dir."""
    try:
        if not trace_dir.exists():
            return set()
        return {str(f) for f in trace_dir.rglob("*.xml")}
    except Exception:
        return set()


def _parse_frt_xml(xml_path: Path) -> Optional[dict]:
    """Parsea un archivo XML de Failed Request Tracing y extrae la excepción."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ns = {"freb": "http://schemas.microsoft.com/win/2004/08/events/event"}

        # Buscar el EventData que contiene la excepción
        exception_type = None
        exception_message = None
        status_code = None
        url = None

        # Nodo Request
        for req in root.iter("Request"):
            url = req.get("Url") or req.get("url")
            status_code = req.get("StatusCode") or req.get("failureReason")

        # Buscar EXCEPTION_CAUGHT o MODULE_SET_RESPONSE_ERROR_STATUS
        for event_data in root.iter("EventData"):
            for data in event_data.iter("Data"):
                name = data.get("Name", "")
                val = (data.text or "").strip()
                if name == "ExceptionType":
                    exception_type = val
                elif name == "ExceptionMessage":
                    exception_message = val
                elif name == "StatusCode" and not status_code:
                    status_code = val

        if not exception_type and not exception_message:
            return None
        if exception_type in _IGNORE_EXCEPTION_TYPES:
            return None

        return {
            "source": "frt_xml",
            "xml_file": xml_path.name,
            "url": url,
            "status_code": status_code,
            "exception_type": exception_type,
            "exception_message": (exception_message or "")[:400],
            "captured_at": _now_iso(),
        }
    except Exception as exc:
        logger.warning("Could not parse FRT XML %s: %s", xml_path, exc)
        return None


def _enable_failed_request_tracing(config_path: Path) -> bool:
    """Habilita traceFailedRequestsLogging en applicationhost.config.

    NOTA: IIS Express debe reiniciarse para que el cambio tome efecto.
    Este método hace una modificación mínima y reversible al XML.
    """
    if not config_path.exists():
        logger.warning("IIS config not found: %s", config_path)
        return False
    try:
        content = config_path.read_text(encoding="utf-8")
        if 'enabled="false"' not in content:
            logger.info("FRT already enabled or config format unexpected")
            return True
        # Reemplazar solo la línea de traceFailedRequestsLogging
        updated = re.sub(
            r'(<traceFailedRequestsLogging\s[^>]*?)enabled="false"',
            r'\1enabled="true"',
            content,
        )
        if updated == content:
            logger.info("FRT config not changed (pattern not found)")
            return False
        config_path.write_text(updated, encoding="utf-8")
        logger.info("FRT enabled in %s. Restart IIS Express to apply.", config_path)
        return True
    except Exception as exc:
        logger.error("Could not enable FRT: %s", exc)
        return False


def _disable_failed_request_tracing(config_path: Path) -> bool:
    """Revierte el cambio de enable_failed_request_tracing."""
    if not config_path.exists():
        return False
    try:
        content = config_path.read_text(encoding="utf-8")
        updated = re.sub(
            r'(<traceFailedRequestsLogging\s[^>]*?)enabled="true"',
            r'\1enabled="false"',
            content,
        )
        if updated != content:
            config_path.write_text(updated, encoding="utf-8")
            logger.info("FRT disabled in %s.", config_path)
        return True
    except Exception as exc:
        logger.error("Could not disable FRT: %s", exc)
        return False


# ── HTTP Response body parser (called from Python, fed by Playwright hook) ───

def parse_ysod_body(body: str, url: str = "", status: int = 500) -> dict:
    """Extrae información de excepción de un YSOD HTML o custom error page.

    Devuelve un dict con exception_type, exception_message, stack_trace_snippet.
    Se llama desde el pipeline Python cuando el Playwright template reporta
    un response body de 5xx via add_response_body_entry.
    """
    result: dict = {
        "source": "ysod_body",
        "url": url,
        "status": status,
        "exception_type": None,
        "exception_message": None,
        "stack_trace_snippet": None,
        "body_snippet": body[:400] if body else "",
        "captured_at": _now_iso(),
    }

    if not body:
        return result

    text = body

    # YSOD pattern 1: "Exception Details: System.Data.SqlClient.SqlException: ..."
    m = re.search(
        r"Exception Details:\s*([\w.]+Exception)[:\s]+([^\n\r<]{1,300})",
        text, re.IGNORECASE,
    )
    if m:
        result["exception_type"] = m.group(1)
        result["exception_message"] = m.group(2).strip()

    # YSOD pattern 2: plain exception line at top of error
    if not result["exception_type"]:
        m2 = re.search(
            r"\b(System(?:\.\w+)+Exception|Microsoft(?:\.\w+)+Exception)"
            r"[:\s]+([^\n\r<]{1,300})",
            text,
        )
        if m2:
            result["exception_type"] = m2.group(1)
            result["exception_message"] = m2.group(2).strip()

    # Generic: look for Argentine Spanish error messages
    if not result["exception_type"]:
        m3 = re.search(
            r"(?:Se produjo|Ha ocurrido|ocurrió)\s+(?:una|un)\s+[^<\n]{1,200}",
            text, re.IGNORECASE,
        )
        if m3:
            result["exception_message"] = m3.group(0).strip()

    # Stack trace snippet
    st_match = re.search(
        r"((?:en |at )\s*\w[\w.]+\([^\)]{0,120}\)(?:\s*en\s*[^\n]{0,120})?)",
        text,
    )
    if st_match:
        result["stack_trace_snippet"] = st_match.group(1).strip()[:400]

    return result


# ── Standalone CLI ────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="ServerExceptionMonitor — Captura excepciones ASP.NET/IISExpress"
    )
    parser.add_argument("--dump-recent", action="store_true",
                        help="Mostrar eventos recientes del Event Log")
    parser.add_argument("--since-minutes", type=int, default=5,
                        help="Minutos hacia atrás para --dump-recent (default: 5)")
    parser.add_argument("--enable-frt", action="store_true",
                        help="Habilitar Failed Request Tracing en applicationhost.config")
    parser.add_argument("--disable-frt", action="store_true",
                        help="Deshabilitar Failed Request Tracing")
    parser.add_argument("--iis-config", type=Path, default=None,
                        help="Ruta a applicationhost.config (opcional)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = args.iis_config or _DEFAULT_IIS_CONFIG

    if args.enable_frt:
        ok = _enable_failed_request_tracing(cfg)
        print(f"FRT enable: {'OK' if ok else 'FAILED'} — {cfg}")
        return

    if args.disable_frt:
        ok = _disable_failed_request_tracing(cfg)
        print(f"FRT disable: {'OK' if ok else 'FAILED'} — {cfg}")
        return

    if args.dump_recent:
        # Calcular el record_id de hace N minutos atrás
        # Simplificación: usamos record_id=0 para los últimos 50 eventos de nivel Warning+
        ps = f"""
$cutoff = (Get-Date).AddMinutes(-{args.since_minutes})
$events = Get-WinEvent -LogName Application -ErrorAction SilentlyContinue |
    Where-Object {{ $_.TimeCreated -gt $cutoff -and $_.LevelDisplayName -ne 'Information' }} |
    Select-Object RecordId, TimeCreated, ProviderName, LevelDisplayName, Id, Message
if ($events) {{ $events | ConvertTo-Json -Depth 2 }} else {{ '[]' }}
"""
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=20,
        )
        text = (result.stdout or "").strip()
        try:
            events = json.loads(text)
            if isinstance(events, dict):
                events = [events]
        except Exception:
            events = []

        parsed = []
        for e in events:
            p = _parse_eventlog_entry(e)
            if p:
                parsed.append(p)

        if not parsed:
            print(f"Sin excepciones ASP.NET en los últimos {args.since_minutes} minutos.")
        else:
            print(json.dumps(parsed, ensure_ascii=False, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    _cli()
