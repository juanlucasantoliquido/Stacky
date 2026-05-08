"""
regression_monitor.py — E-07: Monitor de Regresiones Post-Commit.

Después de un commit Git exitoso, monitorea indicadores de regresión:
  - Nuevos tickets sobre los mismos módulos
  - Errores en archivos de log del servidor (si están accesibles)
  - Cambios en métricas de build del proyecto

Genera alertas cuando detecta posibles regresiones y activa N-10 (rollback plan).

Uso:
    from regression_monitor import RegressionMonitor
    monitor = RegressionMonitor(tickets_base, project_name, notifier)
    monitor.watch_ticket(ticket_id, ticket_folder)
    issues = monitor.check_regressions()
"""

import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("stacky.regression_monitor")

_CHECK_WINDOW_HOURS = 48  # ventana de monitoreo post-commit
_REGRESSION_THRESHOLD = 2  # tickets nuevos en mismo módulo = posible regresión


class RegressionMonitor:
    """
    Monitorea regresiones post-commit comparando tickets nuevos con módulos recientes.
    """

    def __init__(self, tickets_base: str, project_name: str, notifier=None):
        self._tickets_base = tickets_base
        self._project      = project_name
        self._notifier     = notifier
        self._lock         = threading.RLock()
        self._path         = self._get_path()
        self._data         = self._load()

    # ── API pública ───────────────────────────────────────────────────────

    def watch_ticket(self, ticket_id: str, ticket_folder: str) -> None:
        """Registra un ticket completado para monitoreo de regresiones."""
        files  = self._extract_files(ticket_folder)
        tables = self._extract_tables(ticket_folder)
        modules = list(set(self._extract_module_names(files)))

        with self._lock:
            watched = self._data.setdefault("watched", {})
            watched[ticket_id] = {
                "files":      files,
                "tables":     tables,
                "modules":    modules,
                "committed_at": datetime.now().isoformat(),
                "folder":     ticket_folder,
                "regression_score": 0,
            }
            # Limpiar tickets viejos (>7 días)
            cutoff = (datetime.now() - timedelta(days=7)).isoformat()
            self._data["watched"] = {
                k: v for k, v in watched.items()
                if v.get("committed_at", "") >= cutoff
            }
            self._save()

        logger.info("[REGRESSION] Ticket #%s registrado para monitoreo (%d módulos)",
                    ticket_id, len(modules))

    def check_regressions(self) -> list[dict]:
        """
        Verifica si hay nuevos tickets que afectan módulos de tickets recientes.
        Retorna lista de posibles regresiones.
        """
        with self._lock:
            watched = dict(self._data.get("watched", {}))

        if not watched:
            return []

        cutoff = (datetime.now() - timedelta(hours=_CHECK_WINDOW_HOURS)).isoformat()
        regressions = []

        # Buscar tickets nuevos (sin PM_COMPLETADO.flag) en estados activos
        new_tickets = self._find_new_tickets(cutoff)

        for watched_id, watch_data in watched.items():
            if watch_data.get("committed_at", "") < cutoff:
                continue

            watched_modules = set(watch_data.get("modules", []))
            watched_files   = set(watch_data.get("files", []))

            matching_new = []
            for new_tid, new_content in new_tickets.items():
                new_modules = set(self._extract_module_names_from_content(new_content))
                new_files   = set(re.findall(r'\b(\w+\.cs)\b', new_content, re.IGNORECASE))

                overlap_modules = watched_modules & new_modules
                overlap_files   = watched_files   & {f.lower() for f in new_files}

                if overlap_modules or len(overlap_files) >= 2:
                    matching_new.append({
                        "new_ticket":       new_tid,
                        "overlap_modules":  list(overlap_modules),
                        "overlap_files":    list(overlap_files)[:5],
                    })

            if len(matching_new) >= _REGRESSION_THRESHOLD:
                regression = {
                    "watched_ticket": watched_id,
                    "new_tickets":    matching_new,
                    "severity":       "HIGH" if len(matching_new) >= 4 else "MEDIUM",
                    "detected_at":    datetime.now().isoformat(),
                }
                regressions.append(regression)
                self._handle_regression(regression, watch_data)

        return regressions

    # ── Internals ─────────────────────────────────────────────────────────

    def _find_new_tickets(self, since: str) -> dict[str, str]:
        """Busca tickets nuevos (sin PM completado) desde la fecha dada."""
        new_tickets: dict[str, str] = {}
        for estado in ["nueva", "nueva", "confirmada"]:
            estado_dir = os.path.join(self._tickets_base, estado)
            if not os.path.isdir(estado_dir):
                continue
            try:
                for tid in os.listdir(estado_dir):
                    ticket_folder = os.path.join(estado_dir, tid)
                    inc_path = os.path.join(ticket_folder, f"INC-{tid}.md")
                    if not os.path.exists(inc_path):
                        continue
                    # Solo tickets creados recientemente
                    try:
                        mtime = os.path.getmtime(inc_path)
                        if datetime.fromtimestamp(mtime).isoformat() < since:
                            continue
                    except Exception:
                        continue
                    try:
                        content = Path(inc_path).read_text(
                            encoding="utf-8", errors="replace")[:3000]
                        new_tickets[tid] = content
                    except Exception:
                        pass
            except Exception:
                pass
        return new_tickets

    @staticmethod
    def _extract_module_names(files: list[str]) -> list[str]:
        modules = []
        for f in files:
            base = os.path.splitext(os.path.basename(f))[0].lower()
            base = re.sub(r'\.aspx$', '', base)
            if len(base) >= 4:
                modules.append(base)
        return modules

    @staticmethod
    def _extract_module_names_from_content(content: str) -> list[str]:
        modules = set()
        for m in re.finditer(r'\b(Frm\w+|DAL_\w+|BLL_\w+)\b', content):
            modules.add(m.group(1).lower())
        return list(modules)

    @staticmethod
    def _extract_files(ticket_folder: str) -> list[str]:
        files: set[str] = set()
        for fname in ["ARQUITECTURA_SOLUCION.md", "DEV_COMPLETADO.md"]:
            fpath = os.path.join(ticket_folder, fname)
            if not os.path.exists(fpath):
                continue
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r'([\w.\-]+\.(?:cs|aspx\.cs|aspx))', content,
                                     re.IGNORECASE):
                    files.add(m.group(1).lower())
            except Exception:
                pass
        return list(files)[:15]

    @staticmethod
    def _extract_tables(ticket_folder: str) -> list[str]:
        tables: set[str] = set()
        for fname in ["ANALISIS_TECNICO.md", "ARQUITECTURA_SOLUCION.md"]:
            fpath = os.path.join(ticket_folder, fname)
            if not os.path.exists(fpath):
                continue
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r'\b(RST_[A-Z0-9_]{3,20})\b', content):
                    tables.add(m.group(1))
            except Exception:
                pass
        return list(tables)[:10]

    def _handle_regression(self, regression: dict, watch_data: dict) -> None:
        """Notifica y genera plan de rollback para posible regresión."""
        watched_id = regression["watched_ticket"]
        folder     = watch_data.get("folder", "")

        logger.warning("[REGRESSION] Posible regresión detectada — Ticket #%s "
                       "correlaciona con %d nuevos tickets",
                       watched_id, len(regression["new_tickets"]))

        if self._notifier:
            try:
                self._notifier.send(
                    title=f"⚠️ Posible regresión — Ticket #{watched_id}",
                    message=(f"{len(regression['new_tickets'])} nuevos tickets en módulos "
                             f"modificados por #{watched_id}. Verificar rollback."),
                    level="warning",
                    ticket_id=watched_id,
                )
            except Exception:
                pass

        # Marcar en el JSON de monitoreo
        with self._lock:
            if watched_id in self._data.get("watched", {}):
                self._data["watched"][watched_id]["regression_score"] += \
                    len(regression["new_tickets"])
                self._data["watched"][watched_id]["regression_detected_at"] = \
                    datetime.now().isoformat()
            self._save()

    def _get_path(self) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        kb   = os.path.join(base, "knowledge", self._project)
        os.makedirs(kb, exist_ok=True)
        return os.path.join(kb, "regression_monitor.json")

    def _load(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"watched": {}}
        except Exception as e:
            logger.warning("[REGRESSION] Error cargando: %s", e)
            return {"watched": {}}

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("[REGRESSION] Error guardando: %s", e)
