"""production_readiness_gate.py — Q-09: Gate post-QA antes de marcar Resolved en ADO."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("stacky.readiness_gate")


@dataclass
class ReadinessReport:
    ready: bool
    blockers: list[str] = field(default_factory=list)
    check_results: dict[str, bool | None] = field(default_factory=dict)


# Palabras clave que indican valores hardcodeados problemáticos en DEV_COMPLETADO.md
_HARDCODE_NEGATIVE_KEYWORDS = ("hardcoded", "hardcodeado", "valor fijo")

# Patrones de performance / N/A aceptables en TESTER_COMPLETADO.md
_PERF_KEYWORDS = ("performance", "rendimiento", "n/a")

# Patrones MySQL/Postgres que rompen T-SQL
_TSQL_INCOMPATIBLE = [
    (re.compile(r"\bLIMIT\s+\d", re.IGNORECASE),           "LIMIT (MySQL/Postgres)"),
    (re.compile(r"\bAUTO_INCREMENT\b", re.IGNORECASE),     "AUTO_INCREMENT (MySQL)"),
    (re.compile(r"\bTEXT\s*\(", re.IGNORECASE),            "TEXT(...) (MySQL)"),
    (re.compile(r"\bSERIAL\b", re.IGNORECASE),             "SERIAL (Postgres)"),
    (re.compile(r"::\w+"),                                 ":: cast (Postgres)"),
]


class ProductionReadinessGate:
    CHECKS = {
        "has_rollback_script":  "ROLLBACK_SCRIPT.sql existe y no está vacío",
        "no_hardcoded_values":  "DEV_COMPLETADO.md no menciona valores hardcodeados",
        "performance_noted":    "TESTER_COMPLETADO.md menciona análisis de performance o N/A explícito",
        "migration_compatible": "Scripts SQL son compatibles con SQL Server (T-SQL válido)",
        "ado_child_tasks_done": "Todas las child tasks en ADO están en estado Done",
    }

    def evaluate(self, ticket_folder: str, work_item_id: int) -> ReadinessReport:
        results: dict[str, bool | None] = {}
        for check_id in self.CHECKS:
            check_fn = getattr(self, f"_check_{check_id}", None)
            if check_fn is None:
                results[check_id] = None
                continue
            try:
                results[check_id] = check_fn(ticket_folder, work_item_id)
            except Exception as e:
                logger.warning("[READINESS] Check %s falló: %s", check_id, e)
                results[check_id] = None

        blockers = [desc for cid, desc in self.CHECKS.items()
                    if results.get(cid) is False]
        ready = not blockers
        logger.info("[READINESS] ticket=%s ready=%s blockers=%d",
                    work_item_id, ready, len(blockers))
        return ReadinessReport(ready=ready, blockers=blockers, check_results=results)

    # ── Checks individuales ──────────────────────────────────────────────────

    def _check_has_rollback_script(self, ticket_folder: str, _wid: int) -> bool:
        base = Path(ticket_folder)
        if not base.is_dir():
            return False
        # ticket_folder + 1 nivel recursivo
        candidates = [base / "ROLLBACK_SCRIPT.sql"]
        try:
            for sub in base.iterdir():
                if sub.is_dir():
                    candidates.append(sub / "ROLLBACK_SCRIPT.sql")
        except OSError:
            pass
        for p in candidates:
            if p.is_file():
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if content.strip():
                    return True
        return False

    def _check_no_hardcoded_values(self, ticket_folder: str, _wid: int) -> bool:
        dev_md = Path(ticket_folder) / "DEV_COMPLETADO.md"
        if not dev_md.is_file():
            # Si no existe, no tenemos evidencia de riesgo — no bloquea.
            return True
        try:
            body = dev_md.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            return True
        # Escanear línea por línea para distinguir entre menciones de riesgo
        # ("valor hardcodeado en X") y negaciones explícitas ("cero hardcodeados",
        # "sin valores hardcodeados", "no hay hardcoded ...").
        negation_prefixes = ("cero ", "sin ", "no hay ", "no existe", "no contiene",
                             "ningún ", "ningun ", "ninguna ", "0 ")
        for line in body.splitlines():
            stripped = line.strip().lstrip("-*#> []x ").strip()
            for kw in _HARDCODE_NEGATIVE_KEYWORDS:
                if kw not in stripped:
                    continue
                if any(neg in stripped for neg in negation_prefixes):
                    continue
                logger.info("[READINESS] Hardcode flag detectado en DEV_COMPLETADO.md: %s", kw)
                return False
        return True

    def _check_performance_noted(self, ticket_folder: str, _wid: int) -> bool:
        tester_md = Path(ticket_folder) / "TESTER_COMPLETADO.md"
        if not tester_md.is_file():
            return False
        try:
            body = tester_md.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            return False
        return any(kw in body for kw in _PERF_KEYWORDS)

    def _check_migration_compatible(self, ticket_folder: str, _wid: int) -> bool:
        base = Path(ticket_folder)
        if not base.is_dir():
            return True
        for sql_path in base.rglob("*.sql"):
            try:
                body = sql_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for pattern, label in _TSQL_INCOMPATIBLE:
                if pattern.search(body):
                    logger.info("[READINESS] SQL incompatible en %s: %s",
                                sql_path.name, label)
                    return False
        return True

    def _check_ado_child_tasks_done(self, _ticket_folder: str, work_item_id: int) -> bool | None:
        try:
            from issue_provider import get_provider
        except Exception as e:
            logger.debug("[READINESS] issue_provider no disponible: %s", e)
            return None
        try:
            from project_manager import get_active_project
            project = get_active_project()
        except Exception:
            project = None
        try:
            provider = get_provider(project)
        except Exception as e:
            logger.debug("[READINESS] get_provider falló: %s", e)
            return None

        # Intentar API específica de children si existe
        fetch_children = getattr(provider, "fetch_child_tickets", None)
        if callable(fetch_children):
            try:
                children = fetch_children(str(work_item_id)) or []
            except Exception as e:
                logger.debug("[READINESS] fetch_child_tickets falló: %s", e)
                return None
            if not children:
                return True
            for c in children:
                st = (getattr(c, "state_raw", "") or "").strip().lower()
                if st not in ("done", "closed", "completed", "resolved"):
                    return False
            return True

        # Fallback: usar detail + relaciones
        fetch_detail = getattr(provider, "fetch_ticket_detail", None)
        if not callable(fetch_detail):
            return None
        try:
            detail = fetch_detail(str(work_item_id))
        except Exception as e:
            logger.debug("[READINESS] fetch_ticket_detail falló: %s", e)
            return None

        raw = getattr(getattr(detail, "ticket", None), "raw", None) or {}
        relations = raw.get("relations") or []
        child_ids: list[str] = []
        for rel in relations:
            rel_type = (rel.get("rel") or "").lower()
            if "forward" in rel_type or "hierarchy-forward" in rel_type:
                url = rel.get("url") or ""
                m = re.search(r"/workItems/(\d+)", url, re.IGNORECASE)
                if m:
                    child_ids.append(m.group(1))
        if not child_ids:
            return True

        for cid in child_ids:
            try:
                child_detail = fetch_detail(cid)
            except Exception:
                return None
            st = (getattr(getattr(child_detail, "ticket", None), "state_raw", "")
                  or "").strip().lower()
            if st not in ("done", "closed", "completed", "resolved"):
                return False
        return True
