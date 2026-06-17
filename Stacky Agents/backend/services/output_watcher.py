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
    últimos 30s (o done-marker explícito).
    Acción: **auto-crea** las Tasks hijas en ADO (self-HTTP idempotente a
    create-child-task) — NO depende de una AgentExecution running, así que
    cubre también agentes corridos fuera del tracking de Stacky. Luego cierra
    la execution trackeada si existe (sin publish: los Epics no llevan
    comment.html). Re-deshabilitable con STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS=false.

Idempotencia:
  - Modo B: dedup DB-level por (execution_id, html_sha256) en agent_html_publish.
  - Modo A: dedup en memoria + check TicketStatusEvent con changed_by que
    contenga 'output_watcher_mode_a'.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
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
COMMENT_META_FILENAME = "comment.meta.json"
PENDING_TASK_FILENAME = "pending-task.json"
# Señal de finalización determinista (Fase P3): el agente la escribe como último
# paso. Su presencia dispara el cierre inmediato del Modo A sin esperar el
# debounce heurístico de mtime (que queda como fallback si el agente no la
# escribe). Ver _find_done_marker.
DONE_MARKER_FILENAME = ".stacky-done.json"

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
        # `outputs_dir` se resuelve **lazy** (ver property abajo) cuando no se
        # pasa override explícito. Resolverlo acá, en __init__, lo congelaba al
        # valor de arranque del proceso — y en deploy el watcher arranca ANTES
        # de que haya proyecto activo, así que repo_root() caía al fallback
        # parents[4] (que en el .exe empaquetado dentro del repo apunta a
        # <repo>/Tools/Stacky en vez de <repo>) y el watcher quedaba poleando
        # un directorio inexistente para siempre. Resolver en cada scan permite
        # tomar el workspace_root del proyecto cuando se activa y seguir
        # cambios de proyecto en runtime.
        self._outputs_dir_override = outputs_dir
        self._last_scanned_dir: Path | None = None
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

    @property
    def outputs_dir(self) -> Path:
        """Directorio `Agentes/outputs` a vigilar.

        Si se construyó con un override explícito (tests, diag) lo respeta;
        si no, lo resuelve en cada acceso vía `_outputs_dir()` para reflejar el
        proyecto activo aunque éste se haya seteado después del arranque.
        """
        if self._outputs_dir_override is not None:
            return self._outputs_dir_override
        return _outputs_dir()

    @property
    def _alt_epic_base(self) -> Path | None:
        """Base alternativa `<repo>/output/tickets` donde el agente a veces
        co-loca el pending-task.json. Derivada del repo_root (o del override,
        que es `<repo>/Agentes/outputs` → subimos dos niveles)."""
        base = self.outputs_dir
        try:
            repo = base.parent.parent
        except Exception:
            return None
        return repo / "output" / "tickets"

    # — Lifecycle —

    def start(self) -> threading.Thread:
        if self._thread is not None and self._thread.is_alive():
            return self._thread
        self._stop.clear()

        def _loop() -> None:
            logger.info(
                "output watcher started (dir=%s interval=%.1fs, dir resuelto dinámicamente por scan)",
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
        outputs_dir = self.outputs_dir  # resuelto lazy: snapshot por scan
        # Log cuando cambia el dir vigilado (p.ej. al activarse un proyecto
        # luego del arranque). Clave para diagnosticar runs huérfanos.
        if outputs_dir != self._last_scanned_dir:
            logger.info("output_watcher: dir vigilado → %s (existe=%s)", outputs_dir, outputs_dir.exists())
            self._last_scanned_dir = outputs_dir
        # NO retornar temprano si el dir canónico no existe: el agente funcional
        # a veces sólo escribe el pending-task.json en la base alternativa
        # `<repo>/output/tickets/epic-{id}/` y nunca crea `Agentes/outputs`. El
        # `return` temprano de antes dejaba el Modo A (auto-create) muerto en ese
        # caso (causa raíz del "termina la task y queda atascada": el watcher
        # nunca escaneaba la base alternativa). Escaneamos la canónica sólo si
        # existe y SIEMPRE intentamos la alternativa más abajo.
        if outputs_dir.exists():
            for entry in outputs_dir.iterdir():
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

        # Base alternativa: el agente funcional a veces co-loca el
        # pending-task.json en `<repo>/output/tickets/epic-{id}/` junto al
        # análisis y el plan, en vez de la canónica `Agentes/outputs/epic-{id}/`.
        # Escaneamos también esa base para Modo A (auto-create + cierre). Modo B
        # (comentarios) vive sólo en la canónica.
        alt_base = self._alt_epic_base
        if alt_base is not None and alt_base.exists() and alt_base != outputs_dir:
            for entry in alt_base.iterdir():
                if not entry.is_dir() or not entry.name.startswith("epic-"):
                    continue
                epic_part = entry.name[5:]
                if not epic_part.isdigit():
                    continue
                try:
                    self._process_mode_a(
                        epic_ado_id=int(epic_part), epic_dir=entry, round_result=round_result
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("output_watcher: error procesando alt %s: %s", entry, exc)
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

        # Leer comment.meta.json (si existe) para extraer target_ado_state. Esto
        # permite que el watcher aplique el state change cuando recupera un run
        # huérfano que el agente no PATCHeó (ver S1 del roadmap).
        meta_target_state = _read_target_state_from_meta(ado_dir)

        logger.info(
            "output_watcher mode_b: %s exec=%d ADO-%s sha=%s target_state=%s",
            action, execution_id, ado_id, sha256[:8], meta_target_state or "(none)",
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
            target_ado_state=meta_target_state,
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
        # Recolectar pending-task.json del Epic (en subcarpetas RF y, por las
        # dudas, directamente bajo el epic dir).
        pending_files = list(epic_dir.glob(PENDING_TASK_FILENAME)) + list(
            epic_dir.glob("*/" + PENDING_TASK_FILENAME)
        )
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

        age_seconds = (datetime.utcnow() - max_mtime_dt).total_seconds()

        # Señal determinista (P3): si el agente escribió el done-marker, cerramos
        # de inmediato — declaró que terminó. Sin marker, caemos al debounce
        # heurístico por estabilidad de mtime (fallback).
        done_marker = _find_done_marker(epic_dir)
        if done_marker is not None:
            logger.info(
                "output_watcher mode_a: done-marker detectado (%s) — cierre inmediato (sin esperar debounce)",
                done_marker,
            )
        elif age_seconds < self.stable_delay_a:
            logger.debug(
                "output_watcher mode_a: epic-%s estable hace %.0fs (< %.0fs) y sin done-marker — esperando",
                epic_ado_id, age_seconds, self.stable_delay_a,
            )
            return

        # Cache: si ya procesamos este max_mtime_ns para este epic, skip
        prev_mtime = self._seen_a.get(str(epic_dir))
        if prev_mtime == max_mtime_ns:
            return

        trigger_desc = (
            "done-marker explícito"
            if done_marker is not None
            else f"estables hace {int(age_seconds)}s (debounce)"
        )
        pending_count = len(pending_files)
        effective_epic_ado_id, epic_resolution = _resolve_effective_epic_ado_id(
            source_epic_ado_id=epic_ado_id,
            epic_dir=epic_dir,
            pending_files=pending_files,
            max_mtime_dt=max_mtime_dt,
        )
        if effective_epic_ado_id != epic_ado_id:
            logger.warning(
                "output_watcher mode_a: corrigiendo epic dir mal nombrado "
                "source_epic=%s effective_ado=%s reason=%s path=%s",
                epic_ado_id,
                effective_epic_ado_id,
                epic_resolution.get("reason"),
                epic_dir,
            )

        # ── Auto-create Tasks en ADO (Fase W5 + W6) ───────────────────────────
        # IMPORTANTE: la auto-creación NO depende de que exista una
        # AgentExecution "running". El agente puede haber corrido fuera del
        # tracking de Stacky (Copilot directo) o su execution puede haberse
        # cerrado ya. Igual auto-creamos las Tasks desde los pending-task.json
        # estables: el endpoint create-child-task es idempotente (marca el
        # archivo como consumed), así que esto es seguro y la vista
        # "Desatascador" queda sólo como fallback manual puntual.
        #
        # Si STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS == "false", el helper
        # devuelve todo como skipped (gate del operador re-habilitable).
        project_name = _project_name_for_epic(effective_epic_ado_id)
        auto_create_summary = _auto_create_pending_tasks(
            epic_ado_id=effective_epic_ado_id,
            pending_files=pending_files,
            project_name=project_name,
            source_epic_ado_id=epic_ado_id if effective_epic_ado_id != epic_ado_id else None,
            source_epic_dir=str(epic_dir) if effective_epic_ado_id != epic_ado_id else None,
        )
        if auto_create_summary["created"] > 0 or auto_create_summary["errors"] > 0:
            logger.info(
                "output_watcher mode_a: auto-create resumen — created=%d skipped=%d errors=%d",
                auto_create_summary["created"],
                auto_create_summary["skipped"],
                auto_create_summary["errors"],
            )

        # La auto-creación es best-effort y NUNCA bloquea el cierre del run. Si
        # hubo errores transitorios (Flask no listo, ADO 5xx) y además no hay
        # execution que cerrar, dejamos el mtime sin cachear para reintentar.
        auto_create_had_errors = auto_create_summary["errors"] > 0

        # ── Cerrar la execution trackeada (si la hay) ─────────────────────────
        # El cierre del run sí requiere una AgentExecution running. Si no hay
        # (agente fuera de tracking), las Tasks ya quedaron creadas arriba y no
        # hay nada que cerrar.
        with session_scope() as session:
            ticket = session.query(Ticket).filter(Ticket.ado_id == effective_epic_ado_id).first()
            if ticket is None:
                logger.debug("output_watcher mode_a: ADO-%s no existe en DB", effective_epic_ado_id)
                if not auto_create_had_errors:
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
                    "output_watcher mode_a: epic-%s sin execution running — "
                    "Tasks auto-creadas, nada que cerrar",
                    effective_epic_ado_id,
                )
                # Reintentar el auto-create en el próximo scan si hubo errores.
                if not auto_create_had_errors:
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
                    running_exec.id, effective_epic_ado_id, already_event.id,
                )
                if not auto_create_had_errors:
                    self._seen_a[str(epic_dir)] = max_mtime_ns
                round_result.mode_a_skipped += 1
                return

            execution_id = running_exec.id
            agent_type = running_exec.agent_type

        logger.info(
            "output_watcher mode_a: cerrando exec=%d epic-%s (pending_tasks=%d, disparador=%s)",
            execution_id, effective_epic_ado_id, pending_count, trigger_desc,
        )
        result = close_execution_with_publish(
            execution_id=execution_id,
            triggered_by="output_watcher_mode_a",
            final_status="completed",
            html_output_path=None,  # explícito: no hay HTML para publicar en modo A
            user=MODE_A_CHANGED_BY_PREFIX,
            reason=(
                f"output_watcher mode_a: epic-{effective_epic_ado_id} análisis completado "
                f"({pending_count} pending-task.json, {trigger_desc})"
            ),
            completion_source="output_watcher",
            agent_type_hint=agent_type,
            auto_publish=False,  # explícito: Epics no llevan comment.html
        )

        if not auto_create_had_errors:
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


def _find_done_marker(epic_dir: Path) -> Path | None:
    """Busca el done-marker explícito (`.stacky-done.json`) del Modo A.

    El agente lo escribe como último paso para declarar que terminó (Fase P3).
    Se acepta tanto a nivel del epic (`epic-<id>/.stacky-done.json`) como por RF
    (`epic-<id>/<RF>/.stacky-done.json`).

    Devuelve el Path del primer marker válido (JSON dict que NO declare un estado
    no-terminal como `running`/`in_progress`/`pending`); None si no hay ninguno o
    todos son inválidos. Defensivo: un marker malformado se ignora (cae al
    fallback por debounce), nunca rompe el scan.
    """
    candidates = [epic_dir / DONE_MARKER_FILENAME]
    candidates.extend(sorted(epic_dir.glob("*/" + DONE_MARKER_FILENAME)))
    for marker in candidates:
        if not marker.is_file():
            continue
        try:
            import json as _json
            data = _json.loads(marker.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("output_watcher mode_a: done-marker inválido en %s: %s", marker, exc)
            continue
        if not isinstance(data, dict):
            continue
        status = str(data.get("status", "")).strip().lower()
        if status in {"running", "in_progress", "in-progress", "pending"}:
            # Marker prematuro/no-terminal: no dispara cierre.
            continue
        return marker
    return None


def _read_target_state_from_meta(ado_dir: Path) -> str | None:
    """Lee `comment.meta.json` para extraer el target_ado_state que el agente
    quiere aplicar tras el publish.

    Defensivo:
      - Si el archivo no existe → None (sin state change).
      - Si está malformado / no es JSON → None + log debug.
      - Si está OK pero no tiene `target_ado_state` → None.
      - Si tiene un valor string no vacío → lo retorna.
    """
    meta = ado_dir / COMMENT_META_FILENAME
    if not meta.is_file():
        return None
    try:
        import json as _json
        data = _json.loads(meta.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("output_watcher: comment.meta.json inválido en %s: %s", meta, exc)
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("target_ado_state")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _ep_label_matches_title(title: str | None, ep_label: int) -> bool:
    if not title:
        return False
    return re.match(
        rf"^\s*ep\s*[-#:]?\s*0*{re.escape(str(int(ep_label)))}(?=\D|$)",
        str(title),
        re.IGNORECASE,
    ) is not None


def _intake_valid_ado_ids(epic_ado_id: int, source_epic_ado_id: int | None) -> list[int]:
    """V1.3 — ids ADO reales conocidos para el contexto de la regla anti-ordinal.

    Incluye el epic destino y el epic origen (si difiere). Vacío ⇒ la regla
    anti-ordinal hace skip (no inventa). No consulta toda la DB: el set mínimo
    confiable es el epic involucrado en este intake.
    """
    ids: list[int] = []
    try:
        ids.append(int(epic_ado_id))
    except (TypeError, ValueError):
        pass
    if source_epic_ado_id is not None:
        try:
            sid = int(source_epic_ado_id)
            if sid not in ids:
                ids.append(sid)
        except (TypeError, ValueError):
            pass
    return ids


def _read_pending_payload(pt_file: Path) -> dict | None:
    try:
        data = json.loads(pt_file.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _declared_parent_ado_id(payload: dict | None) -> int | None:
    if not payload:
        return None
    for key in ("epic_ado_id", "parent_id", "parent_ado_id"):
        value = payload.get(key)
        if value is None or not str(value).strip().isdigit():
            continue
        return int(str(value).strip())
    return None


def _exact_ticket_exists(ado_id: int) -> bool:
    try:
        with session_scope() as session:
            return session.query(Ticket.id).filter(Ticket.ado_id == int(ado_id)).first() is not None
    except Exception:  # noqa: BLE001
        logger.debug("output_watcher mode_a: no se pudo consultar ticket ADO-%s", ado_id, exc_info=True)
        return False


def _resolve_effective_epic_ado_id(
    *,
    source_epic_ado_id: int,
    epic_dir: Path,
    pending_files: list[Path],
    max_mtime_dt: datetime,
) -> tuple[int, dict]:
    """Resuelve el ADO real cuando la carpeta usa la etiqueta humana EP-<n>.

    Evidencia ADO-241: el agente escribio `epic-26` porque el titulo del Epic
    era `EP-26 - ...`. El System.Id real era 241. El watcher no debe crear contra
    26 si la BD local o la ejecucion activa identifican 241.
    """
    if _exact_ticket_exists(source_epic_ado_id):
        return source_epic_ado_id, {"reason": "exact_ticket_exists"}

    for pt in pending_files:
        declared = _declared_parent_ado_id(_read_pending_payload(pt))
        if declared and declared != source_epic_ado_id:
            return declared, {"reason": "declared_parent_id", "pending_task_path": str(pt)}

    try:
        with session_scope() as session:
            from sqlalchemy import func

            titled_matches = [
                t.ado_id
                for t in session.query(Ticket)
                .filter(func.lower(Ticket.work_item_type) == "epic")
                .all()
                if _ep_label_matches_title(t.title, source_epic_ado_id)
            ]
            if len(set(titled_matches)) == 1:
                return int(titled_matches[0]), {
                    "reason": "ticket_title_ep_label",
                    "source_epic_dir": str(epic_dir),
                }

            lower_bound = max_mtime_dt - timedelta(minutes=20)
            upper_bound = max_mtime_dt + timedelta(minutes=5)
            candidates = []
            rows = (
                session.query(AgentExecution, Ticket)
                .join(Ticket, Ticket.id == AgentExecution.ticket_id)
                .filter(AgentExecution.agent_type == "functional")
                .all()
            )
            for execution, ticket in rows:
                if (ticket.work_item_type or "").strip().lower() != "epic":
                    continue
                started = execution.started_at
                completed = execution.completed_at
                if started and started > upper_bound:
                    continue
                if completed and completed < lower_bound:
                    continue
                if started and started <= upper_bound:
                    candidates.append((ticket.ado_id, execution.id, execution.status))
            unique = {ado_id for ado_id, _, _ in candidates if ado_id != source_epic_ado_id}
            if len(unique) == 1:
                ado_id = int(next(iter(unique)))
                exec_ids = [eid for cand_ado, eid, _ in candidates if cand_ado == ado_id]
                return ado_id, {
                    "reason": "agent_execution_time_window",
                    "execution_ids": exec_ids,
                    "source_epic_dir": str(epic_dir),
                }
    except Exception:  # noqa: BLE001
        logger.debug("output_watcher mode_a: resolucion de epic efectivo fallo", exc_info=True)

    return source_epic_ado_id, {"reason": "source_epic_dir"}


# Cuarentena de pending-task.json con fallo ESTRUCTURAL (JSON corrupto o rechazo
# terminal 4xx del endpoint). Evita el loop de reintentos cada 3s (incidente
# epic-28/RF-028, 2026-06-05: 1239 reintentos en 1h): logueamos el error UNA vez
# por (path, mtime) y lo contamos como `skipped` —no `error`— para no bloquear el
# cacheo del mtime del epic dir. Si el operador corrige el archivo (cambia el
# mtime), se reprocesa. Key: str(path) → st_mtime_ns.
_SEEN_TERMINAL_PENDING: dict[str, int] = {}

# HTTP que indican un fallo ESTRUCTURAL del pending-task.json (no transitorio):
# reintentar idéntico no ayuda hasta que el operador corrija el archivo/carpeta
# (padre inexistente, jerarquía no soportada, schema/epic_id inválido). Los 5xx y
# errores de conexión NO están acá: esos sí se reintentan.
_TERMINAL_CREATE_HTTP = {400, 404, 409, 422}
_TERMINAL_CREATE_ERRORS = {
    "ADO_CHILD_TASK_VERIFICATION_FAILED",
    "ADO_HIERARCHY_NOT_SUPPORTED",
    "ADO_PARENT_NOT_FOUND",
    "PENDING_TASK_EPIC_MISMATCH",
    "PENDING_TASK_FILE_NOT_FOUND",
    "PENDING_TASK_PARSE_ERROR",
    "PENDING_TASK_SCHEMA_INVALID",
    "PENDING_TASK_STATUS_INVALID",
}


def _quarantine_pending_once(pt_file: Path, reason: str) -> bool:
    """Loguea UNA vez (por path+mtime) un pending-task.json con fallo terminal y
    lo registra en la cuarentena. Devuelve True si logueó (primera vez para este
    contenido), False si ya estaba en cuarentena."""
    key = str(pt_file)
    try:
        mtime_ns = pt_file.stat().st_mtime_ns
    except OSError:
        mtime_ns = -1
    if _SEEN_TERMINAL_PENDING.get(key) == mtime_ns:
        return False  # ya logueado para este contenido
    _SEEN_TERMINAL_PENDING[key] = mtime_ns
    logger.error(
        "output_watcher mode_a: pending-task con fallo terminal (se omite hasta "
        "corregir el archivo/carpeta) en %s: %s",
        pt_file, reason,
    )
    return True


def _pending_is_quarantined(pt_file: Path) -> bool:
    key = str(pt_file)
    if key not in _SEEN_TERMINAL_PENDING:
        return False
    try:
        mtime_ns = pt_file.stat().st_mtime_ns
    except OSError:
        mtime_ns = -1
    return _SEEN_TERMINAL_PENDING.get(key) == mtime_ns


def _validate_pending_task_strict(payload: dict, *, epic_ado_id: int) -> list[str]:
    """R1.2 — Validacion estructural minima del pending-task antes del POST.

    Comprueba: campos requeridos presentes, tipos correctos, coherencia
    ordinal (rf_id) vs parent ADO id. Solo valida ESTRUCTURA, no contenido.

    Retorna lista de errores (vacia = valido).
    """
    errors: list[str] = []
    required_str = ("title",)
    for field in required_str:
        if not payload.get(field) or not isinstance(payload[field], str):
            errors.append(f"campo requerido ausente o invalido: '{field}'")

    # rf_id: debe ser str o int, no None/vacio
    rf_id = payload.get("rf_id")
    if rf_id is None or rf_id == "":
        errors.append("campo requerido ausente: 'rf_id'")

    # parent_ado_id coherencia ordinal: si esta presente, debe coincidir con epic_ado_id
    # (regla anti-ordinal del plan 28 R1.2).
    parent_id = payload.get("parent_ado_id") or payload.get("epic_ado_id")
    if parent_id is not None:
        try:
            if int(parent_id) != int(epic_ado_id):
                errors.append(
                    f"parent_ado_id={parent_id} no coincide con epic_ado_id={epic_ado_id} "
                    "(mismatch ordinal vs ADO id)"
                )
        except (TypeError, ValueError):
            errors.append(f"parent_ado_id={parent_id!r} no es un entero valido")

    return errors


def _terminal_create_failure(status_code: int, error_code: str | None) -> bool:
    if status_code in _TERMINAL_CREATE_HTTP:
        return True
    return bool(error_code and error_code in _TERMINAL_CREATE_ERRORS)


def _project_name_for_epic(epic_ado_id: int) -> str | None:
    """Devuelve el proyecto Stacky/tracker conocido para enviar al self-HTTP."""
    try:
        with session_scope() as session:
            ticket = session.query(Ticket).filter(Ticket.ado_id == epic_ado_id).first()
            if ticket is None:
                return None
            return (ticket.stacky_project_name or ticket.project or "").strip() or None
    except Exception:  # noqa: BLE001
        logger.debug("output_watcher mode_a: no se pudo resolver proyecto para ADO-%s", epic_ado_id, exc_info=True)
        return None


def _auto_create_pending_tasks(
    *,
    epic_ado_id: int,
    pending_files: list[Path],
    project_name: str | None = None,
    source_epic_ado_id: int | None = None,
    source_epic_dir: str | None = None,
) -> dict:
    """Para cada pending-task.json no consumido, llama al endpoint
    `/api/tickets/by-ado/{epic}/create-child-task` vía self-HTTP.

    Idempotente: el endpoint mismo skipea archivos con status=consumed.

    Distingue fallos TRANSITORIOS (5xx, conexión → cuenta como `errors`, se
    reintenta en el próximo scan) de fallos ESTRUCTURALES (JSON inválido, 4xx →
    cuarentena vía `_quarantine_pending_once`, cuenta como `skipped` para no
    reintentar cada 3s).

    Retorna {created, skipped, errors}.
    """
    import json as _json
    import requests as _req

    if os.getenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true").lower() == "false":
        return {"created": 0, "skipped": len(pending_files), "errors": 0}

    try:
        from config import config as _config
        port = _config.PORT
    except Exception:
        port = int(os.getenv("PORT", "5050"))

    base_url = f"http://127.0.0.1:{port}/api/tickets/by-ado/{epic_ado_id}/create-child-task"

    created = 0
    skipped = 0
    errors = 0

    for pt_file in pending_files:
        if _pending_is_quarantined(pt_file):
            skipped += 1
            continue

        # V1.3 — Intake universal (flag-gated). Si ON, todo output file-based
        # pasa por validate_and_normalize ANTES de encolarse: reparación
        # determinista + schema + regla anti-ordinal. Si falla → cuarentena con
        # errores legibles (nunca llega inválido a ADO). Si OFF → path actual.
        if os.getenv("STACKY_ARTIFACT_INTAKE_ENABLED", "false").lower() in ("1", "true", "yes", "on"):
            try:
                from services import artifact_intake
                raw_text = pt_file.read_text(encoding="utf-8")
            except OSError as exc:
                _quarantine_pending_once(pt_file, f"no legible: {exc}")
                skipped += 1
                continue
            # status=consumed: no re-validar, ya procesado.
            try:
                _peek = _json.loads(raw_text)
            except Exception:
                _peek = None
            if isinstance(_peek, dict) and (
                _peek.get("status") == "consumed" or "consumed_at" in _peek
            ):
                skipped += 1
                continue
            ctx = {"valid_ado_ids": _intake_valid_ado_ids(epic_ado_id, source_epic_ado_id)}
            result = artifact_intake.validate_and_normalize(
                raw=raw_text, kind="pending_task_json", ticket_context=ctx,
            )
            if not result.ok:
                _quarantine_pending_once(
                    pt_file,
                    "intake rechazó el artefacto: " + "; ".join(result.errors),
                )
                skipped += 1
                continue
            if result.repaired and isinstance(result.normalized, dict):
                # Reescribir el archivo con el JSON normalizado para que el
                # endpoint downstream consuma una versión válida.
                try:
                    pt_file.write_text(
                        _json.dumps(result.normalized, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    logger.info(
                        "output_watcher intake: reparado %s (%s)",
                        pt_file.name, ", ".join(result.repairs),
                    )
                except OSError:
                    logger.warning("intake: no se pudo reescribir %s", pt_file, exc_info=True)
            pt_payload = result.normalized if isinstance(result.normalized, dict) else _peek or {}
        else:
            try:
                pt_payload = _json.loads(pt_file.read_text(encoding="utf-8"))
            except (OSError, _json.JSONDecodeError) as exc:
                _quarantine_pending_once(pt_file, f"JSON inválido/no legible: {exc}")
                skipped += 1
                continue

        if pt_payload.get("status") == "consumed" or "consumed_at" in pt_payload:
            skipped += 1
            continue

        rf_id = pt_payload.get("rf_id", "?")

        # R1.2 — Validacion estructural always-on (independiente del flag V1.3).
        # Gate minimo: campos requeridos, tipos, coherencia ordinal vs parent ADO id.
        # Si el flag STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED=false → no-op.
        _strict_ok = True
        if os.getenv("STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED", "false").lower() in (
            "1", "true", "yes", "on"
        ):
            _validation_errors = _validate_pending_task_strict(
                pt_payload, epic_ado_id=epic_ado_id
            )
            if _validation_errors:
                _quarantine_pending_once(
                    pt_file,
                    "R1.2 validacion estricta: " + "; ".join(_validation_errors),
                )
                logger.warning(
                    "output_watcher R1.2: pending-task rf=%s rechazado: %s",
                    rf_id, _validation_errors,
                )
                # Emitir telemetria en el log como contador de cuarentena.
                logger.info(
                    "output_watcher R1.2 telemetria: cuarentena_strict epic=%s rf=%s errors=%d",
                    epic_ado_id, rf_id, len(_validation_errors),
                )
                skipped += 1
                _strict_ok = False
        if not _strict_ok:
            continue

        pt_rel = _rel_to_repo(pt_file)
        body = {
            "pending_task_path": pt_rel,
            "operator_reason": (
                f"output_watcher auto-create: pending-task estable detectado para "
                f"epic-{epic_ado_id}/{rf_id}"
            ),
            "completion_source": "output_watcher_auto",
        }
        if source_epic_ado_id is not None and int(source_epic_ado_id) != int(epic_ado_id):
            body["source_epic_ado_id"] = int(source_epic_ado_id)
            body["source_epic_dir"] = source_epic_dir
            body["allow_epic_id_mismatch"] = True
        if project_name:
            body["project"] = project_name
        try:
            resp = _req.post(base_url, json=body, timeout=60)
        except _req.exceptions.ConnectionError as exc:
            # El Flask todavía no acepta conexiones (raro: el watcher corre
            # dentro del mismo proceso). Logueamos y dejamos para el próximo round.
            logger.warning(
                "output_watcher mode_a: auto-create connection error para rf=%s: %s",
                rf_id, exc,
            )
            errors += 1
            continue
        except _req.exceptions.RequestException as exc:
            logger.warning(
                "output_watcher mode_a: auto-create request falló para rf=%s: %s",
                rf_id, exc,
            )
            errors += 1
            continue

        try:
            payload = resp.json()
        except ValueError:
            payload = {}

        if resp.status_code == 200 and payload.get("ok") is not False:
            task_ado_id = payload.get("task_ado_id")
            if payload.get("idempotent"):
                skipped += 1
                logger.info(
                    "output_watcher mode_a: auto-create rf=%s ya estaba consumido (task_id=%s)",
                    rf_id, task_ado_id,
                )
            elif task_ado_id:
                created += 1
                logger.info(
                    "output_watcher mode_a: auto-create rf=%s → task_ado_id=%s",
                    rf_id, task_ado_id,
                )
            else:
                logger.warning(
                    "output_watcher mode_a: auto-create rf=%s devolvió 200 sin task_ado_id: %s",
                    rf_id, payload,
                )
                errors += 1
        else:
            err_code = payload.get("error") if isinstance(payload, dict) else None
            err_msg = (
                (payload.get("message") or err_code)
                if isinstance(payload, dict)
                else None
            ) or resp.text[:200]
            if _terminal_create_failure(resp.status_code, err_code):
                _quarantine_pending_once(pt_file, f"HTTP {resp.status_code}: {err_msg}")
                skipped += 1
                continue
            errors += 1
            logger.warning(
                "output_watcher mode_a: auto-create rf=%s falló (HTTP %d): %s",
                rf_id, resp.status_code, err_msg,
            )

    return {"created": created, "skipped": skipped, "errors": errors}


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
