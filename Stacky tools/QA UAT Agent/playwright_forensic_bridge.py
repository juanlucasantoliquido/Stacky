"""
playwright_forensic_bridge.py — Puente Python↔Playwright para logging forense.

RESPONSABILIDADES:
  1. Antes del run: preparar env vars y directorio para el logger TypeScript.
  2. Durante el run: uat_test_runner usa CommandRunner (streaming).
  3. Después del run: leer los JSONL escritos por TypeScript y persistirlos
     en el ForensicEventLogger (SQLite + events.jsonl del run).

Env vars que configura antes del run Playwright:
  QA_UAT_FORENSIC_RUN_DIR    → run_dir
  QA_UAT_FORENSIC_RUN_ID     → run_id
  QA_UAT_FORENSIC_TICKET_ID  → ticket_id

Archivos que lee después del run:
  <run_dir>/playwright/actions.jsonl
  <run_dir>/playwright/network.jsonl
  <run_dir>/playwright/console.jsonl
  <run_dir>/playwright/screenshots.jsonl

Uso en qa_uat_pipeline.py:
    from playwright_forensic_bridge import PlaywrightForensicBridge

    bridge = PlaywrightForensicBridge(
        run_dir=run_dir, run_id=run_id, ticket_id=ticket_id,
        forensic_log=log
    )
    env_extra = bridge.get_env_vars()   # pasar al comando npx playwright
    # ... ejecutar playwright con env_extra ...
    bridge.import_playwright_events()  # post-run: importar eventos a ForensicEventLogger
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import logging

_py_logger = logging.getLogger("stacky.qa_uat.playwright_forensic_bridge")


# Máximo de eventos de red por run (para no sobrecargar el store con assets)
_MAX_NETWORK_EVENTS = 200
# Tipos de recursos de red a ignorar (ruido)
_IGNORED_RESOURCE_TYPES = frozenset({"image", "font", "media", "other"})


class PlaywrightForensicBridge:
    """
    Configura y procesa el puente entre Playwright (TypeScript) y ForensicEventLogger (Python).
    """

    def __init__(
        self,
        run_dir: Path,
        run_id: str,
        ticket_id: Any,
        forensic_log: Any = None,  # ForensicEventLogger
        artifact_registry: Any = None,  # ArtifactRegistry
    ) -> None:
        self.run_dir = run_dir
        self.run_id = run_id
        self.ticket_id = ticket_id
        self.forensic_log = forensic_log
        self.artifact_registry = artifact_registry
        self._pw_dir = run_dir / "playwright"

    def get_env_vars(self) -> dict:
        """
        Devuelve dict de env vars a agregar al proceso Playwright.
        El logger TypeScript usa estas vars para saber dónde escribir.
        """
        return {
            "QA_UAT_FORENSIC_RUN_DIR": str(self.run_dir),
            "QA_UAT_FORENSIC_RUN_ID": str(self.run_id),
            "QA_UAT_FORENSIC_TICKET_ID": str(self.ticket_id),
        }

    def prepare(self) -> None:
        """Crear directorio playwright/ antes del run."""
        self._pw_dir.mkdir(parents=True, exist_ok=True)

    def import_playwright_events(self) -> dict:
        """
        Leer los JSONL escritos por Playwright (TypeScript) y emitir
        cada uno como evento en el ForensicEventLogger.

        Devuelve resumen:
          { "actions": int, "network": int, "console": int,
            "screenshots": int, "errors": int }
        """
        summary = {"actions": 0, "network": 0, "console": 0, "screenshots": 0, "errors": 0}

        if not self._pw_dir.exists():
            return summary

        # ── Actions ────────────────────────────────────────────────────────────
        summary["actions"] = self._import_file(
            self._pw_dir / "actions.jsonl",
            self._map_action_event,
        )

        # ── Network ────────────────────────────────────────────────────────────
        summary["network"] = self._import_file(
            self._pw_dir / "network.jsonl",
            self._map_network_event,
            limit=_MAX_NETWORK_EVENTS,
        )

        # ── Console ────────────────────────────────────────────────────────────
        summary["console"] = self._import_file(
            self._pw_dir / "console.jsonl",
            self._map_console_event,
        )

        # ── Screenshots ─────────────────────────────────────────────────────────
        summary["screenshots"] = self._import_screenshots()

        return summary

    # ── Import helpers ─────────────────────────────────────────────────────────

    def _import_file(self, path: Path, mapper: Any, limit: Optional[int] = None) -> int:
        """Leer JSONL y emitir cada evento via mapper. Devuelve count."""
        if not path.exists():
            return 0
        count = 0
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if limit and count >= limit:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        mapper(rec)
                        count += 1
                    except json.JSONDecodeError:
                        pass
                    except Exception as exc:
                        _py_logger.debug("Bridge import error: %s", exc)
        except Exception as exc:
            _py_logger.warning("Bridge: error leyendo %s: %s", path, exc)
        return count

    def _map_action_event(self, rec: dict) -> None:
        """Convertir evento de action.jsonl a ForensicEventLogger."""
        if self.forensic_log is None:
            return
        try:
            cat = rec.get("category", "page_click")
            status = rec.get("status", "completed")
            level = "error" if status == "failed" else "info"
            self.forensic_log.emit(
                source="playwright",
                event_type=rec.get("event_type", f"playwright.action.{status}"),
                category=cat,
                stage="runner",
                action=rec.get("action", "action"),
                status=status,
                level=level,
                message=rec.get("message", f"Playwright {rec.get('action', 'action')} {status}"),
                payload={
                    "scenario_id": rec.get("scenario_id"),
                    "step_id": rec.get("step_id"),
                    "selector": rec.get("selector"),
                    "url_before": rec.get("url_before"),
                    "url_after": rec.get("url_after"),
                    "duration_ms": rec.get("duration_ms"),
                    "error": rec.get("error"),
                    **(rec.get("payload") or {}),
                },
                duration_ms=rec.get("duration_ms"),
                redact_payload=True,  # redactar valores de fill
            )
        except Exception as exc:
            _py_logger.debug("Bridge _map_action_event error: %s", exc)

    def _map_network_event(self, rec: dict) -> None:
        """Convertir evento de network.jsonl a ForensicEventLogger — filtrar ruido."""
        if self.forensic_log is None:
            return
        resource_type = rec.get("resource_type", "")
        if resource_type in _IGNORED_RESOURCE_TYPES:
            return
        # Solo loguear errores y respuestas de API/documento
        status_code = rec.get("status")
        event_kind = rec.get("event_kind", "response")
        is_error = event_kind == "failure" or (status_code and status_code >= 500)

        if not is_error and event_kind != "failure":
            # Solo capturar respuestas de documentos y XHR/fetch (no assets)
            if resource_type not in ("document", "xhr", "fetch", "websocket", ""):
                return

        try:
            level = "error" if is_error else "info"
            self.forensic_log.emit(
                source="browser_network",
                event_type=rec.get("event_type", f"network.{event_kind}"),
                category=rec.get("category", "network_response"),
                stage="runner",
                action=f"network_{event_kind}",
                status="failed" if is_error else "completed",
                level=level,
                message=f"Network {event_kind}: {rec.get('method', '')} {rec.get('url', '')[:100]}",
                payload={
                    "scenario_id": rec.get("scenario_id"),
                    "method": rec.get("method"),
                    "url": rec.get("url"),
                    "status": status_code,
                    "resource_type": resource_type,
                    "failure": rec.get("failure"),
                },
                redact_payload=True,
            )
        except Exception as exc:
            _py_logger.debug("Bridge _map_network_event error: %s", exc)

    def _map_console_event(self, rec: dict) -> None:
        """Convertir evento de console.jsonl a ForensicEventLogger."""
        if self.forensic_log is None:
            return
        is_error = rec.get("is_error", False)
        # Solo capturar errores y warnings — el resto es ruido
        console_type = rec.get("console_type", "log")
        if not is_error and console_type not in ("error", "warning", "warn", "pageerror"):
            return
        try:
            self.forensic_log.emit(
                source="browser_console",
                event_type=rec.get("event_type", "browser.console"),
                category="console_log",
                stage="runner",
                action="console_log",
                status="ok",
                level="error" if is_error else "warning",
                message=rec.get("text", "")[:300],
                payload={
                    "scenario_id": rec.get("scenario_id"),
                    "console_type": console_type,
                    "location": rec.get("location"),
                    "is_error": is_error,
                },
            )
        except Exception as exc:
            _py_logger.debug("Bridge _map_console_event error: %s", exc)

    def _import_screenshots(self) -> int:
        """
        Leer screenshots.jsonl, registrar artifacts con sha256.
        También escanear el directorio playwright/screenshots/ por screenshots
        existentes que no fueron registrados (Playwright los escribe directamente).
        """
        count = 0
        screenshots_jsonl = self._pw_dir / "screenshots.jsonl"

        # Desde JSONL del logger TypeScript
        if screenshots_jsonl.exists():
            try:
                with open(screenshots_jsonl, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                            self._register_screenshot_artifact(
                                path_str=rec.get("screenshot_path", ""),
                                scenario_id=rec.get("scenario_id", ""),
                                reason=rec.get("reason", "step"),
                            )
                            count += 1
                        except Exception:
                            pass
            except Exception as exc:
                _py_logger.warning("Bridge: error leyendo screenshots.jsonl: %s", exc)

        # Escanear directorios de escenarios para screenshots Playwright
        # (los que Playwright escribe por su cuenta en evidence/<ticket>/<sid>/)
        try:
            evidence_parent = self.run_dir.parent  # evidence/<ticket>/
            for scenario_dir in evidence_parent.iterdir():
                if not scenario_dir.is_dir():
                    continue
                for png in scenario_dir.rglob("*.png"):
                    self._register_screenshot_artifact(
                        path_str=str(png),
                        scenario_id=scenario_dir.name,
                        reason="playwright_auto",
                    )
                    count += 1
        except Exception as exc:
            _py_logger.debug("Bridge: error escaneando screenshots: %s", exc)

        return count

    def _register_screenshot_artifact(self, path_str: str, scenario_id: str, reason: str) -> None:
        """Registrar un screenshot como artifact si el archivo existe."""
        if not path_str:
            return
        p = Path(path_str)
        if not p.exists():
            return
        if self.artifact_registry is None:
            return
        try:
            existing = self.artifact_registry.get_by_type("screenshot")
            existing_paths = {a.get("path", "") for a in existing}
            # Normalizar path relativo
            try:
                rel = str(p.relative_to(self.run_dir))
            except ValueError:
                rel = str(p)
            if rel in existing_paths or str(p) in existing_paths:
                return  # ya registrado

            self.artifact_registry.register_file(
                path=p,
                artifact_type="screenshot",
                scenario_id=scenario_id,
                ticket_id=self.ticket_id,
                extra={"reason": reason},
            )
        except Exception as exc:
            _py_logger.debug("Bridge _register_screenshot_artifact error: %s", exc)

    # ── Emit browser lifecycle events ──────────────────────────────────────────

    def emit_browser_launch(self, headed: bool = False) -> Optional[str]:
        """Emitir evento de lanzamiento de browser."""
        if self.forensic_log is None:
            return None
        return self.forensic_log.emit(
            source="playwright",
            event_type="browser.launch",
            category="browser_launch",
            stage="runner",
            action="browser_launch",
            status="completed",
            level="info",
            message=f"Browser lanzado ({'headed' if headed else 'headless'})",
            payload={"headed": headed, "browser": "chromium"},
        )

    def emit_browser_close(self) -> Optional[str]:
        """Emitir evento de cierre de browser."""
        if self.forensic_log is None:
            return None
        return self.forensic_log.emit(
            source="playwright",
            event_type="browser.close",
            category="browser_close",
            stage="runner",
            action="browser_close",
            status="completed",
            level="info",
            message="Browser cerrado",
            payload={},
        )

    def emit_scenario_verdict(
        self, scenario_id: str, verdict: str, duration_ms: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> Optional[str]:
        """Emitir veredicto final de un escenario."""
        if self.forensic_log is None:
            return None
        return self.forensic_log.emit_verdict(
            stage="runner",
            verdict=verdict,
            reason=reason,
            payload={"scenario_id": scenario_id, "duration_ms": duration_ms},
        )
