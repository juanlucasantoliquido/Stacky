"""
live_pair_watcher.py — X-05: Modo Live Pair: Stacky como Copiloto en Tiempo Real.

Monitorea que archivos abre/modifica el developer y, cuando uno de ellos
corresponde a un ticket activo en el pipeline, pushea contexto al panel lateral
del dashboard via Server-Sent Events (SSE).

Flujo:
  1. Watcher de sistema de archivos (watchdog) detecta archivos abiertos/modificados.
  2. Busca en el pipeline state si algun ticket activo referencia ese archivo
     (en ARQUITECTURA_SOLUCION.md o SVN_CHANGES.md).
  3. Si hay match, emite un evento SSE al dashboard con el contexto relevante:
     - Analisis PM del ticket
     - Advertencias de Blast Radius para ese archivo
     - Timeout countdown
     - Patrones conocidos del archivo

Uso:
    from live_pair_watcher import LivePairWatcher
    watcher = LivePairWatcher(project_name, pipeline_state)
    watcher.start()   # thread no bloqueante
    watcher.stop()
"""

import json
import logging
import os
import queue
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("mantis.live_pair")

BASE_DIR = Path(__file__).parent

# Cola de eventos SSE para el endpoint /api/live-pair/events
_event_queue: queue.Queue = queue.Queue(maxsize=100)


def get_event_queue() -> queue.Queue:
    """Retorna la cola global de eventos SSE."""
    return _event_queue


class LivePairWatcher:
    """
    Watcher de archivos que emite contexto Stacky cuando el developer
    edita archivos relacionados con tickets activos.
    """

    def __init__(self, project_name: str, pipeline_state_path: str = None):
        self.project_name = project_name
        self._pipeline_state_path = pipeline_state_path or str(
            BASE_DIR / "pipeline" / "state.json"
        )
        self._config = self._load_config()
        self._workspace_root = Path(
            self._config.get("workspace_root", str(BASE_DIR.parent.parent))
        )
        self._tickets_base = (
            BASE_DIR / "projects" / project_name / "tickets"
        )
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_context: dict = {}   # archivo → ultimo contexto emitido

    # ── API publica ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Inicia el watcher en un thread daemon."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watch_loop, daemon=True, name="live-pair-watcher"
        )
        self._thread.start()
        logger.info("[X-05] Live Pair Watcher iniciado para proyecto %s", self.project_name)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def get_context_for_file(self, file_path: str) -> Optional[dict]:
        """
        Retorna el contexto Stacky relevante para un archivo especifico.
        Busca en tickets activos. Retorna None si no hay match.
        """
        normalized = self._normalize_path(file_path)
        active_tickets = self._get_active_tickets()

        for ticket_id, ticket_info in active_tickets.items():
            relevant_files = ticket_info.get("relevant_files", [])
            if any(self._normalize_path(f) == normalized for f in relevant_files):
                return self._build_context(ticket_id, ticket_info, file_path)
        return None

    # ── Internos ─────────────────────────────────────────────────────────────

    def _watch_loop(self) -> None:
        """Loop principal: detecta cambios en el workspace y emite contexto."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class _Handler(FileSystemEventHandler):
                def __init__(self, outer: "LivePairWatcher"):
                    self._outer = outer

                def on_modified(self, event):
                    if not event.is_directory:
                        self._outer._handle_file_event(event.src_path)

                def on_created(self, event):
                    if not event.is_directory:
                        self._outer._handle_file_event(event.src_path)

            observer = Observer()
            observer.schedule(_Handler(self), str(self._workspace_root), recursive=True)
            observer.start()

            while not self._stop_event.is_set():
                time.sleep(1)

            observer.stop()
            observer.join()

        except ImportError:
            logger.warning("[X-05] watchdog no instalado — usando polling cada 5s")
            self._poll_loop()

    def _poll_loop(self) -> None:
        """Fallback cuando watchdog no esta disponible: polling de archivos recientes."""
        while not self._stop_event.is_set():
            active = self._get_active_tickets()
            for ticket_id, info in active.items():
                for fpath in info.get("relevant_files", []):
                    full = self._workspace_root / fpath
                    if full.exists():
                        mtime = full.stat().st_mtime
                        last  = self._last_context.get(fpath, {}).get("mtime", 0)
                        if mtime > last:
                            ctx = self._build_context(ticket_id, info, str(full))
                            ctx["mtime"] = mtime
                            self._last_context[fpath] = ctx
                            self._emit_event(ctx)
            self._stop_event.wait(5)

    def _handle_file_event(self, file_path: str) -> None:
        """Procesa un evento de sistema de archivos."""
        ext = Path(file_path).suffix.lower()
        if ext not in {".cs", ".aspx", ".vb", ".sql", ".config", ".aspx.cs"}:
            return

        ctx = self.get_context_for_file(file_path)
        if ctx:
            # Evitar spam: no reemitir el mismo contexto en menos de 30s
            key  = ctx.get("ticket_id", "") + "|" + file_path
            last = self._last_context.get(key, {}).get("ts", 0)
            now  = time.time()
            if now - last > 30:
                self._last_context[key] = {"ts": now}
                self._emit_event(ctx)

    def _emit_event(self, ctx: dict) -> None:
        """Coloca el evento en la cola SSE."""
        try:
            _event_queue.put_nowait(ctx)
            logger.debug("[X-05] Evento live pair emitido para ticket %s", ctx.get("ticket_id"))
        except queue.Full:
            pass  # cliente no esta consumiendo — ok

    def _get_active_tickets(self) -> dict:
        """
        Lee el estado del pipeline y retorna tickets activos con sus archivos relevantes.
        """
        result = {}
        try:
            state = json.loads(Path(self._pipeline_state_path).read_text(encoding="utf-8"))
        except Exception:
            state = {}

        for ticket_id, info in state.items():
            stage = info.get("stage", "")
            if stage in ("pm_en_proceso", "dev_en_proceso", "tester_en_proceso",
                         "pm_completado", "dev_completado"):
                # Leer archivos relevantes de ARQUITECTURA_SOLUCION.md y SVN_CHANGES.md
                ticket_folder = self._find_ticket_folder(ticket_id)
                if ticket_folder:
                    files = self._extract_relevant_files(ticket_folder)
                    result[ticket_id] = {
                        **info,
                        "relevant_files": files,
                        "ticket_folder":  str(ticket_folder),
                    }
        return result

    def _find_ticket_folder(self, ticket_id: str) -> Optional[Path]:
        """Busca la carpeta del ticket en cualquier subdirectorio de estado."""
        ticket_num = ticket_id.replace("INC-", "").lstrip("0")
        padded     = ticket_num.zfill(7)
        for estado_dir in self._tickets_base.iterdir() if self._tickets_base.exists() else []:
            candidate = estado_dir / padded
            if candidate.exists():
                return candidate
        return None

    def _extract_relevant_files(self, ticket_folder: Path) -> list:
        """Extrae rutas de archivos mencionadas en ARQUITECTURA_SOLUCION.md y SVN_CHANGES.md."""
        files = set()
        for fname in ("ARQUITECTURA_SOLUCION.md", "SVN_CHANGES.md", "DEV_COMPLETADO.md"):
            fpath = ticket_folder / fname
            if fpath.exists():
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                # Buscar paths relativos con extensiones de codigo
                for match in re.finditer(
                    r"[\w/\\.\-]+\.(?:cs|aspx|vb|sql|config|aspx\.cs)", content
                ):
                    files.add(match.group(0).replace("\\", "/"))
        return list(files)

    def _build_context(self, ticket_id: str, ticket_info: dict, file_path: str) -> dict:
        """Construye el payload de contexto para el panel lateral."""
        ticket_folder = Path(ticket_info.get("ticket_folder", ""))
        stage = ticket_info.get("stage", "")

        # Leer fragmento de ANALISIS_TECNICO
        analisis_snippet = ""
        analisis_file = ticket_folder / "ANALISIS_TECNICO.md"
        if analisis_file.exists():
            text = analisis_file.read_text(encoding="utf-8", errors="ignore")
            analisis_snippet = text[:800] + ("..." if len(text) > 800 else "")

        # Blast radius para este archivo
        blast_warnings = self._get_blast_warnings(file_path, ticket_folder)

        # Timeout countdown
        timeout_info = self._compute_timeout(ticket_info)

        # Patrones conocidos
        patterns = self._get_known_patterns(ticket_id)

        return {
            "type":             "live_pair_context",
            "ticket_id":        ticket_id,
            "stage":            stage,
            "file":             os.path.basename(file_path),
            "file_path":        file_path,
            "analisis_snippet": analisis_snippet,
            "blast_warnings":   blast_warnings,
            "timeout_info":     timeout_info,
            "patterns":         patterns,
            "timestamp":        datetime.now().isoformat(),
        }

    def _get_blast_warnings(self, file_path: str, ticket_folder: Path) -> list:
        """Lee BLAST_RADIUS.md del ticket si existe."""
        warnings = []
        blast_file = ticket_folder / "BLAST_RADIUS.md"
        if blast_file.exists():
            content = blast_file.read_text(encoding="utf-8", errors="ignore")
            fname   = os.path.basename(file_path)
            # Buscar lineas que mencionen el archivo
            for line in content.splitlines():
                if fname in line and any(k in line.upper() for k in ("ALTO", "CRITICO", "HIGH")):
                    warnings.append(line.strip("- #* ").strip())
        return warnings[:3]

    def _compute_timeout(self, ticket_info: dict) -> dict:
        """Calcula cuanto tiempo queda para el timeout de la etapa actual."""
        stage   = ticket_info.get("stage", "")
        started = ticket_info.get("stage_started_at")
        timeout = ticket_info.get("timeout_minutes", 60)

        if not started:
            return {}

        try:
            start_dt  = datetime.fromisoformat(started)
            elapsed   = (datetime.now() - start_dt).total_seconds() / 60
            remaining = max(0, timeout - elapsed)
            return {
                "stage":           stage,
                "elapsed_minutes": round(elapsed, 1),
                "remaining_minutes": round(remaining, 1),
                "timeout_minutes": timeout,
                "is_near": remaining < 10,
            }
        except Exception:
            return {}

    def _get_known_patterns(self, ticket_id: str) -> list:
        """Busca patrones conocidos relevantes de la knowledge base."""
        patterns = []
        try:
            from knowledge_base import KnowledgeBase
            tickets_base = str(self._tickets_base)
            kb  = KnowledgeBase(tickets_base, self.project_name)
            inc_file = self._find_inc_file(ticket_id)
            if inc_file:
                content = inc_file.read_text(encoding="utf-8", errors="ignore")
                results = kb.search(content, k=2)
                for r in results:
                    patterns.append({
                        "ticket_ref": r.get("ticket_id", ""),
                        "summary":    r.get("summary", "")[:120],
                        "similarity": r.get("score", 0),
                    })
        except Exception:
            pass
        return patterns

    def _find_inc_file(self, ticket_id: str) -> Optional[Path]:
        folder = self._find_ticket_folder(ticket_id)
        if folder:
            for f in folder.glob("INC-*.md"):
                return f
        return None

    def _normalize_path(self, path: str) -> str:
        return Path(path).name.lower()

    def _load_config(self) -> dict:
        cfg_path = BASE_DIR / "projects" / self.project_name / "config.json"
        if cfg_path.exists():
            try:
                return json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}
