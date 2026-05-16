"""Output watcher — cierra ejecuciones VSCode huérfanas detectando artifacts en disco.

El flujo `/api/agents/open-chat` arranca un agente en VSCode Copilot Chat. La
AgentExecution queda en `running` y debería cerrarse cuando el agente PATCHea
`/api/tickets/by-ado/{ado_id}/stacky-status`. Si el agente no llega al paso
final (no ejecuta el snippet, lo hace y falla, etc.), el run queda colgado.

Este watcher actúa como **fallback** del PATCH: polea `Agentes/outputs/` y
cierra runs cuando detecta los artifacts que el agente debería haber escrito.

Cubre dos casuísticas:

  Modo B — comentario en ADO
    Disparador: `Agentes/outputs/{ado_id}/comment.html` aparece (mtime
    posterior al started_at de la execution + estable hace ≥ 2s + SHA no
    publicado antes).
    Acción: close_execution_with_publish(completed) + auto-publish ADO.

  Modo A — análisis de Epic
    Disparador: `Agentes/outputs/epic-{ado_id}/{RF}/pending-task.json` con
    contenidos del Epic (analisis + plan + pending) sin escrituras en los
    últimos 30s.
    Acción: close_execution_with_publish(completed) **sin** publish (Epics
    no llevan comment.html). NO crea Tasks en ADO (gate del operador).

Idempotencia:
  - Modo B: dedup DB-level por (execution_id, html_sha256) en agent_html_publish.
  - Modo A: dedup en memoria + check TicketStatusEvent con changed_by que
    contenga 'output_watcher_mode_a'.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from db import session_scope
from models import AgentExecution, Ticket
from services.agent_completion_internal import close_execution_with_publish
from services.agent_html_output import repo_root
from services.ticket_status import TicketStatusEvent

logger = logging.getLogger("stacky.output_watcher")

COMMENT_HTML_FILENAME = "comment.html"
PENDING_TASK_FILENAME = "pending-task.json"

# Defaults (configurables vía env)
DEFAULT_POLL_INTERVAL_SECONDS = 3.0
DEFAULT_STABLE_DELAY_B_SECONDS = 2.0
DEFAULT_STABLE_DELAY_A_SECONDS = 30.0
DEFAULT_STARTED_AT_GRACE_SECONDS = 5.0

MODE_A_CHANGED_BY_PREFIX = "system:output_watcher:mode_a"


@dataclass
class ScanStats:
    scans: int = 0
    mode_b_closes: int = 0
    mode_b_skipped: int = 0
    mode_a_closes: int = 0
    mode_a_skipped: int = 0
    errors: int = 0

    def as_dict(self) -> dict:
        return {
            "scans": self.scans,
            "mode_b_closes": self.mode_b_closes,
            "mode_b_skipped": self.mode_b_skipped,
            "mode_a_closes": self.mode_a_closes,
            "mode_a_skipped": self.mode_a_skipped,
            "errors": self.errors,
        }


@dataclass
class _ScanRoundResult:
    mode_b_closes: int = 0
    mode_b_skipped: int = 0
    mode_a_closes: int = 0
    mode_a_skipped: int = 0


def _outputs_dir() -> Path:
    return repo_root() / "Agentes" / "outputs"


def _default_poll_interval() -> float:
    return float(os.getenv("STACKY_OUTPUT_WATCHER_INTERVAL_SECONDS", str(DEFAULT_POLL_INTERVAL_SECONDS)))


def _default_stable_delay_b() -> float:
    return float(os.getenv("STACKY_OUTPUT_WATCHER_STABLE_DELAY_B", str(DEFAULT_STABLE_DELAY_B_SECONDS)))


def _default_stable_delay_a() -> float:
    return float(os.getenv("STACKY_OUTPUT_WATCHER_STABLE_DELAY_A", str(DEFAULT_STABLE_DELAY_A_SECONDS)))


# ── Watcher ───────────────────────────────────────────────────────────────────


class AdoOutputWatcher:
    """Polling watcher de Agentes/outputs/ que cierra runs huérfanos."""

    def __init__(
        self,
        outputs_dir: Path | None = None,
        *,
        poll_interval: float | None = None,
        stable_delay_b: float | None = None,
        stable_delay_a: float | None = None,
    ) -> None:
        self.outputs_dir = outputs_dir if outputs_dir is not None else _outputs_dir()
        self.poll_interval = poll_interval if poll_interval is not None else _default_poll_interval()
        self.stable_delay_b = stable_delay_b if stable_delay_b is not None else _default_stable_delay_b()
        self.stable_delay_a = stable_delay_a if stable_delay_a is not None else _default_stable_delay_a()
        self.stats = ScanStats()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # cache (path, mtime_ns) ya procesados para evitar re-stat de archivos sin cambio
        self._seen_b: dict[str, tuple[int, str]] = {}  # path -> (mtime_ns, sha256)
        # cache (epic_dir, last_max_mtime_ns) — para Modo A
        self._seen_a: dict[str, int] = {}

    # — Lifecycle —

    def start(self) -> threading.Thread:
        if self._thread is not None and self._thread.is_alive():
            return self._thread
        self._stop.clear()

        def _loop() -> None:
            logger.info(
                "output watcher started (dir=%s interval=%.1fs)",
                self.outputs_dir, self.poll_interval,
            )
            while not self._stop.wait(timeout=self.poll_interval):
                try:
                    self.scan_once()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("output watcher scan failed: %s", exc)
                    self.stats.errors += 1
            logger.info("output watcher stopped")

        self._thread = threading.Thread(target=_loop, daemon=True, name="stacky-output-watcher")
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self._stop.clear()

    # — Scan público —

    def scan_once(self) -> dict:
        """Una pasada manual. Retorna dict con counts del round."""
        self.stats.scans += 1
        round_result = _ScanRoundResult()
        if not self.outputs_dir.exists():
            return round_result.__dict__

        for entry in self.outputs_dir.iterdir():
            if not entry.is_dir():
                continue
            name = entry.name
            try:
                if name.startswith("epic-"):
                    epic_part = name[5:]
                    if not epic_part.isdigit():
                        continue
                    self._process_mode_a(epic_ado_id=int(epic_part), epic_dir=entry, round_result=round_result)
                elif name.isdigit():
                    self._process_mode_b(ado_id=int(name), ado_dir=entry, round_result=round_result)
            except Exception as exc:  # noqa: BLE001
                logger.exception("output_watcher: error procesando %s: %s", entry, exc)
                self.stats.errors += 1

        self.stats.mode_b_closes += round_result.mode_b_closes
        self.stats.mode_b_skipped += round_result.mode_b_skipped
        self.stats.mode_a_closes += round_result.mode_a_closes
        self.stats.mode_a_skipped += round_result.mode_a_skipped
        return round_result.__dict__

    # — Modo B —

    def _process_mode_b(self, *, ado_id: int, ado_dir: Path, round_result: _ScanRoundResult) -> None:
        comment = ado_dir / COMMENT_HTML_FILENAME
        if not comment.is_file():
            return
        try:
            stat = comment.stat()
        except OSError:
            return
        key = str(comment)
        prev = self._seen_b.get(key)
        if prev and prev[0] == stat.st_mtime_ns:
            return  # sin cambios

        # Debounce: si el archivo se modificó hace muy poco, esperar próximo round
        age_seconds = (datetime.utcnow() - datetime.utcfromtimestamp(stat.st_mtime)).total_seconds()
        if age_seconds < self.stable_delay_b:
            return

        try:
            content = comment.read_bytes()
        except OSError:
            return
        sha256 = hashlib.sha256(content).hexdigest()

        # Si el SHA es el mismo que ya cacheamos antes, marcamos seen sin re-actuar.
        if prev and prev[1] == sha256:
            self._seen_b[key] = (stat.st_mtime_ns, sha256)
            return

        # ── Consultar DB ──────────────────────────────────────────────────────
        with session_scope() as session:
            ticket = session.query(Ticket).filter(Ticket.ado_id == ado_id).first()
            if ticket is None:
                logger.debug("output_watcher mode_b: ticket ADO-%s no existe en DB", ado_id)
                self._seen_b[key] = (stat.st_mtime_ns, sha256)
                round_result.mode_b_skipped += 1
                return
            ticket_id = ticket.id

            # ¿Ya hay publish con este SHA exacto? Dedup DB-level.
            already_published = _find_publish_by_sha(session, ticket_id=ticket_id, sha256=sha256)
            if already_published is not None and already_published.status == "ok":
                logger.debug(
                    "output_watcher mode_b: ADO-%s sha=%s ya publicado en row %d — skip",
                    ado_id, sha256[:8], already_published.id,
                )
                self._seen_b[key] = (stat.st_mtime_ns, sha256)
                round_result.mode_b_skipped += 1
                return

            # Tomar la LATEST execution (running o terminal). El publish puede
            # disparar aunque la execution esté cerrada — esto cubre el race
            # Modo A → Modo B cuando un Epic produce ambos artifacts y Modo A
            # cerró antes. El dedup SHA en agent_html_publish evita doble-publish.
            latest_exec = (
                session.query(AgentExecution)
                .filter(AgentExecution.ticket_id == ticket_id)
                .order_by(AgentExecution.id.desc())
                .first()
            )
            if latest_exec is None:
                logger.debug(
                    "output_watcher mode_b: comment.html para ADO-%s pero no hay execution registrada",
                    ado_id,
                )
                self._seen_b[key] = (stat.st_mtime_ns, sha256)
                round_result.mode_b_skipped += 1
                return

            # El archivo debe ser de esta execution (mtime ≥ started_at - margen)
            cutoff = latest_exec.started_at - timedelta(seconds=DEFAULT_STARTED_AT_GRACE_SECONDS)
            if datetime.utcfromtimestamp(stat.st_mtime) < cutoff:
                logger.debug(
                    "output_watcher mode_b: comment.html para ADO-%s es más viejo que la execution %d — skip",
                    ado_id, latest_exec.id,
                )
                self._seen_b[key] = (stat.st_mtime_ns, sha256)
                round_result.mode_b_skipped += 1
                return

            execution_id = latest_exec.id
            agent_type = latest_exec.agent_type
            is_running = latest_exec.status == "running"

        # ── Cerrar y publicar (afuera del session_scope para no anidar) ───────
        try:
            html_rel = _rel_to_repo(comment)
        except Exception:
            html_rel = str(comment)

        if is_running:
            action = "cerrando+publicando"
            triggered = "output_watcher_mode_b"
        else:
            action = "solo publicando (execution ya terminal)"
            triggered = "output_watcher_mode_b_late"
        logger.info(
            "output_watcher mode_b: %s exec=%d ADO-%s sha=%s",
            action, execution_id, ado_id, sha256[:8],
        )
        result = close_execution_with_publish(
            execution_id=execution_id,
            triggered_by=triggered,
            final_status="completed",
            html_output_path=html_rel,
            user="system:output_watcher",
            reason=f"output_watcher mode_b: comment.html detectado para ADO-{ado_id} sha={sha256[:8]}",
            completion_source="output_watcher",
            agent_type_hint=agent_type,
        )

        self._seen_b[key] = (stat.st_mtime_ns, sha256)
        # Cuenta como close si transicionamos estado; cuenta como publish-only
        # cuando ya estaba terminal pero publicamos igual.
        publish_ok = result.publish.get("ok") is True
        if result.ok and (not result.already_terminal or publish_ok):
            round_result.mode_b_closes += 1
        else:
            round_result.mode_b_skipped += 1

    # — Modo A —

    def _process_mode_a(self, *, epic_ado_id: int, epic_dir: Path, round_result: _ScanRoundResult) -> None:
        # Recolectar pending-task.json del Epic.
        pending_files = list(epic_dir.glob("*/" + PENDING_TASK_FILENAME))
        if not pending_files:
            return

        # max_mtime entre los pending-task.json (y archivos adyacentes)
        all_files: list[Path] = list(pending_files)
        for rf_dir in epic_dir.iterdir():
            if rf_dir.is_dir():
                for sibling in ("analisis-funcional.md", "plan-de-pruebas.md"):
                    p = rf_dir / sibling
                    if p.is_file():
                        all_files.append(p)

        max_mtime_ns = 0
        max_mtime_dt: datetime | None = None
        for f in all_files:
            try:
                stat = f.stat()
            except OSError:
                continue
            if stat.st_mtime_ns > max_mtime_ns:
                max_mtime_ns = stat.st_mtime_ns
                max_mtime_dt = datetime.utcfromtimestamp(stat.st_mtime)
        if max_mtime_dt is None:
            return

        # Debounce: si algún archivo se modificó hace menos de stable_delay_a, esperar
        age_seconds = (datetime.utcnow() - max_mtime_dt).total_seconds()
        if age_seconds < self.stable_delay_a:
            logger.debug(
                "output_watcher mode_a: epic-%s estable hace %.0fs (< %.0fs) — esperando",
                epic_ado_id, age_seconds, self.stable_delay_a,
            )
            return

        # Cache: si ya procesamos este max_mtime_ns para este epic, skip
        prev_mtime = self._seen_a.get(str(epic_dir))
        if prev_mtime == max_mtime_ns:
            return

        # ── Consultar DB ──────────────────────────────────────────────────────
        with session_scope() as session:
            ticket = session.query(Ticket).filter(Ticket.ado_id == epic_ado_id).first()
            if ticket is None:
                logger.debug("output_watcher mode_a: ADO-%s no existe en DB", epic_ado_id)
                self._seen_a[str(epic_dir)] = max_mtime_ns
                round_result.mode_a_skipped += 1
                return
            ticket_id = ticket.id

            running_exec = (
                session.query(AgentExecution)
                .filter(
                    AgentExecution.ticket_id == ticket_id,
                    AgentExecution.status == "running",
                )
                .order_by(AgentExecution.started_at.desc())
                .first()
            )
            if running_exec is None:
                logger.debug(
                    "output_watcher mode_a: epic-%s sin execution running — skip",
                    epic_ado_id,
                )
                self._seen_a[str(epic_dir)] = max_mtime_ns
                round_result.mode_a_skipped += 1
                return

            # Dedup: ya cerramos esta execution con mode_a antes? Buscamos
            # por el patrón del reason — on_execution_end hardcodea changed_by="system"
            # así que no podemos distinguir por ahí.
            already_event = (
                session.query(TicketStatusEvent)
                .filter(
                    TicketStatusEvent.execution_id == running_exec.id,
                    TicketStatusEvent.reason.like("%output_watcher mode_a%"),
                )
                .first()
            )
            if already_event is not None:
                logger.debug(
                    "output_watcher mode_a: exec=%d epic-%s ya tiene close event (id=%d) — skip",
                    running_exec.id, epic_ado_id, already_event.id,
                )
                self._seen_a[str(epic_dir)] = max_mtime_ns
                round_result.mode_a_skipped += 1
                return

            execution_id = running_exec.id
            agent_type = running_exec.agent_type
            pending_count = len(pending_files)

        # ── Cerrar (sin publish, sin crear tasks) ─────────────────────────────
        logger.info(
            "output_watcher mode_a: cerrando exec=%d epic-%s (pending_tasks=%d, stable=%.0fs)",
            execution_id, epic_ado_id, pending_count, age_seconds,
        )
        result = close_execution_with_publish(
            execution_id=execution_id,
            triggered_by="output_watcher_mode_a",
            final_status="completed",
            html_output_path=None,  # explícito: no hay HTML para publicar en modo A
            user=MODE_A_CHANGED_BY_PREFIX,
            reason=(
                f"output_watcher mode_a: epic-{epic_ado_id} análisis completado "
                f"({pending_count} pending-task.json estables hace {int(age_seconds)}s)"
            ),
            completion_source="output_watcher",
            agent_type_hint=agent_type,
            auto_publish=False,  # explícito: Epics no llevan comment.html
        )

        self._seen_a[str(epic_dir)] = max_mtime_ns
        if result.ok and not result.already_terminal:
            round_result.mode_a_closes += 1
        else:
            round_result.mode_a_skipped += 1


# ── Helpers ──────────────────────────────────────────────────────────────────


def _find_publish_by_sha(session, *, ticket_id: int, sha256: str):
    """Busca en agent_html_publish una row reciente con el mismo SHA y ticket_id.

    Import local de AgentHtmlPublish para evitar acoplar el watcher al módulo
    ado_publisher en el path de import top-level.
    """
    try:
        from services.ado_publisher import AgentHtmlPublish
    except ImportError:
        return None
    return (
        session.query(AgentHtmlPublish)
        .filter(
            AgentHtmlPublish.ticket_id == ticket_id,
            AgentHtmlPublish.html_sha256 == sha256,
        )
        .order_by(AgentHtmlPublish.id.desc())
        .first()
    )


def _rel_to_repo(path: Path) -> str:
    try:
        return str(path.relative_to(repo_root())).replace("\\", "/")
    except ValueError:
        return str(path)


# ── Singleton global ──────────────────────────────────────────────────────────


_GLOBAL_LOCK = threading.Lock()
_GLOBAL_WATCHER: AdoOutputWatcher | None = None


def start_output_watcher(
    outputs_dir: Path | None = None,
    *,
    poll_interval: float | None = None,
) -> AdoOutputWatcher:
    """Arranca (o retorna) el watcher singleton. Idempotente."""
    global _GLOBAL_WATCHER
    with _GLOBAL_LOCK:
        if _GLOBAL_WATCHER is not None and _GLOBAL_WATCHER._thread and _GLOBAL_WATCHER._thread.is_alive():
            return _GLOBAL_WATCHER
        watcher = AdoOutputWatcher(outputs_dir=outputs_dir, poll_interval=poll_interval)
        watcher.start()
        _GLOBAL_WATCHER = watcher
        return watcher


def stop_output_watcher() -> None:
    global _GLOBAL_WATCHER
    with _GLOBAL_LOCK:
        watcher = _GLOBAL_WATCHER
        _GLOBAL_WATCHER = None
    if watcher is not None:
        watcher.stop()


def get_output_watcher() -> AdoOutputWatcher | None:
    """Retorna el singleton si está activo (para diag endpoints)."""
    with _GLOBAL_LOCK:
        return _GLOBAL_WATCHER
