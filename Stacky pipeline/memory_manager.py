"""
memory_manager.py — G-06: Memoria Persistente de Agentes por Codebase.

Permite a los agentes recordar hechos sobre el proyecto que descubren
durante el análisis de tickets:
  - Convenciones de código del proyecto (naming, patterns DAL/BLL)
  - Módulos frágiles o con historial de bugs
  - Desarrolladores responsables de cada área
  - Gotchas y anti-patterns encontrados

Los hechos se persisten en knowledge/{project}/agent_memory.json.
Se inyectan como contexto en los prompts PM y DEV.

Uso:
    from memory_manager import AgentMemory
    mem = AgentMemory(project_name)
    mem.add_fact("convention", "DAL usa OracleCommand, nunca LINQ")
    mem.add_fact("fragile_module", "FrmReportesPago — historial de bugs de concurrencia")
    section = mem.format_memory_section()
"""

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("stacky.memory")

# Categorías de memoria
_CATEGORIES = {
    "convention":      "Convenciones del codebase",
    "fragile_module":  "Módulos con historial de bugs",
    "pattern":         "Patrones de solución validados",
    "gotcha":          "Gotchas y anti-patterns",
    "owner":           "Responsables por área/módulo",
    "dependency":      "Dependencias críticas entre módulos",
    "config":          "Configuraciones importantes",
    "performance":     "Puntos críticos de rendimiento",
}

_MAX_FACTS_PER_CATEGORY = 30
_MAX_TOTAL_FACTS = 200


class AgentMemory:
    """
    Memoria persistente de hechos sobre el proyecto para los agentes Stacky.
    Thread-safe con RLock.
    """

    def __init__(self, project_name: str):
        self._project = project_name
        self._lock    = threading.RLock()
        self._path    = self._get_memory_path()
        self._data    = self._load()

    # ── API pública ───────────────────────────────────────────────────────

    def add_fact(self, category: str, fact: str, source: str = "",
                 confidence: float = 1.0) -> bool:
        """
        Agrega un hecho a la memoria. Retorna True si fue agregado (no duplicado).
        category: clave de _CATEGORIES
        fact: descripción del hecho (max 200 chars)
        source: ticket_id u origen del hecho
        confidence: 0.0-1.0
        """
        if not fact or len(fact.strip()) < 10:
            return False

        fact = fact.strip()[:200]
        with self._lock:
            facts = self._data.setdefault("facts", {}).setdefault(category, [])

            # Verificar duplicado aproximado (texto muy similar)
            for existing in facts:
                if self._similar(existing["fact"], fact):
                    # Actualizar confianza y source si la nueva es más confiable
                    if confidence > existing.get("confidence", 1.0):
                        existing["confidence"] = confidence
                        existing["updated_at"] = datetime.now().isoformat()
                        if source:
                            existing.setdefault("sources", [])
                            if source not in existing["sources"]:
                                existing["sources"].append(source)
                        self._save()
                    return False  # No duplicar

            # Limit por categoría
            if len(facts) >= _MAX_FACTS_PER_CATEGORY:
                # Remover el más antiguo
                facts.sort(key=lambda x: x.get("added_at", ""))
                facts.pop(0)

            facts.append({
                "fact":       fact,
                "category":   category,
                "confidence": confidence,
                "sources":    [source] if source else [],
                "added_at":   datetime.now().isoformat(),
                "use_count":  0,
            })

            # Mantener límite total
            total = sum(len(v) for v in self._data["facts"].values())
            if total > _MAX_TOTAL_FACTS:
                self._prune()

            self._save()
            logger.debug("[MEMORY] Hecho agregado: [%s] %s", category, fact[:60])
            return True

    def get_facts(self, category: str = "", min_confidence: float = 0.5) -> list[dict]:
        """Retorna hechos filtrados por categoría y confianza mínima."""
        with self._lock:
            all_facts = self._data.get("facts", {})
            if category:
                facts = all_facts.get(category, [])
            else:
                facts = [f for cat_facts in all_facts.values()
                         for f in cat_facts]
            return [f for f in facts if f.get("confidence", 1.0) >= min_confidence]

    def extract_facts_from_ticket(self, ticket_folder: str, ticket_id: str) -> int:
        """
        Extrae automáticamente hechos de un ticket completado y los agrega a la memoria.
        Retorna la cantidad de hechos nuevos agregados.
        """
        added = 0

        # Leer documentos del ticket
        for fname, category, patterns in [
            ("ANALISIS_TECNICO.md",     "gotcha",         _GOTCHA_PATTERNS),
            ("ARQUITECTURA_SOLUCION.md", "convention",    _CONVENTION_PATTERNS),
            ("DEV_COMPLETADO.md",        "fragile_module", _FRAGILE_PATTERNS),
        ]:
            fpath = os.path.join(ticket_folder, fname)
            if not os.path.exists(fpath):
                continue
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                for pat, confidence in patterns:
                    for m in pat.finditer(content):
                        fact = m.group(0).strip()
                        if len(fact) >= 15:
                            if self.add_fact(category, fact, source=ticket_id,
                                             confidence=confidence):
                                added += 1
            except Exception:
                pass

        if added:
            logger.info("[MEMORY] %d hecho(s) extraídos del ticket #%s", added, ticket_id)
        return added

    def format_memory_section(self, categories: list[str] | None = None,
                               max_facts: int = 15) -> str:
        """
        Formatea la memoria como sección Markdown para inyectar en prompts.
        categories: lista de categorías a incluir (None = todas).
        """
        with self._lock:
            all_facts = self._data.get("facts", {})

        if not any(all_facts.values()):
            return ""

        cats_to_show = categories or list(_CATEGORIES.keys())
        lines = [
            "",
            "---",
            "",
            f"## Memoria del Proyecto — {self._project}",
            "",
            "_Hechos aprendidos de tickets anteriores. Tener en cuenta al analizar._",
            "",
        ]

        count = 0
        for cat in cats_to_show:
            facts = all_facts.get(cat, [])
            if not facts:
                continue
            label = _CATEGORIES.get(cat, cat)
            lines.append(f"### {label}")
            lines.append("")
            for f in sorted(facts, key=lambda x: -x.get("confidence", 1.0))[:5]:
                if count >= max_facts:
                    break
                conf_icon = "✅" if f.get("confidence", 1.0) >= 0.8 else "⚠️"
                lines.append(f"- {conf_icon} {f['fact']}")
                count += 1
            lines.append("")
            if count >= max_facts:
                break

        return "\n".join(lines)

    def invalidate_fact(self, fact_text: str) -> bool:
        """Reduce la confianza de un hecho (marcarlo como dudoso)."""
        with self._lock:
            for cat_facts in self._data.get("facts", {}).values():
                for f in cat_facts:
                    if self._similar(f["fact"], fact_text):
                        f["confidence"] = max(0.0, f.get("confidence", 1.0) - 0.3)
                        f["updated_at"] = datetime.now().isoformat()
                        self._save()
                        return True
        return False

    def get_stats(self) -> dict:
        """Retorna estadísticas de la memoria."""
        with self._lock:
            facts = self._data.get("facts", {})
            return {
                "project":     self._project,
                "total_facts": sum(len(v) for v in facts.values()),
                "by_category": {k: len(v) for k, v in facts.items() if v},
                "last_updated": self._data.get("last_updated", ""),
            }

    # ── Internals ─────────────────────────────────────────────────────────

    @staticmethod
    def _similar(a: str, b: str, threshold: float = 0.7) -> bool:
        """Similitud simple por tokens comunes."""
        tokens_a = set(a.lower().split())
        tokens_b = set(b.lower().split())
        if not tokens_a or not tokens_b:
            return False
        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)
        return (intersection / union) >= threshold if union > 0 else False

    def _prune(self) -> None:
        """Elimina los hechos con menor confianza cuando se supera el límite."""
        all_facts: list[tuple] = []
        for cat, facts in self._data.get("facts", {}).items():
            for i, f in enumerate(facts):
                all_facts.append((f.get("confidence", 1.0), cat, i))
        all_facts.sort()
        # Eliminar los 20 de menor confianza
        to_remove: dict[str, set] = {}
        for _, cat, i in all_facts[:20]:
            to_remove.setdefault(cat, set()).add(i)
        for cat, indices in to_remove.items():
            self._data["facts"][cat] = [
                f for i, f in enumerate(self._data["facts"][cat])
                if i not in indices
            ]

    def _get_memory_path(self) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        kb   = os.path.join(base, "knowledge", self._project)
        os.makedirs(kb, exist_ok=True)
        return os.path.join(kb, "agent_memory.json")

    def _load(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"facts": {}, "project": self._project}
        except Exception as e:
            logger.warning("[MEMORY] Error cargando memory: %s", e)
            return {"facts": {}, "project": self._project}

    def _save(self) -> None:
        self._data["last_updated"] = datetime.now().isoformat()
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("[MEMORY] Error guardando memory: %s", e)


# ── Patrones de extracción automática ─────────────────────────────────────────
import re as _re

_GOTCHA_PATTERNS = [
    (_re.compile(r'(?:cuidado|precaución|atención|ojo con|problema conocido)[:\s]+([^.\n]{20,150})',
                 _re.IGNORECASE), 0.8),
    (_re.compile(r'(?:no usar|evitar|nunca)[:\s]+([^.\n]{15,120})',
                 _re.IGNORECASE), 0.9),
    (_re.compile(r'causa raíz[:\s]+([^.\n]{20,150})',
                 _re.IGNORECASE), 0.85),
]

_CONVENTION_PATTERNS = [
    (_re.compile(r'(?:convención|patrón|estándar|standard)[:\s]+([^.\n]{20,120})',
                 _re.IGNORECASE), 0.75),
    (_re.compile(r'(?:siempre usar|se usa|se utiliza|el proyecto usa)[:\s]+([^.\n]{15,100})',
                 _re.IGNORECASE), 0.7),
]

_FRAGILE_PATTERNS = [
    (_re.compile(r'(?:módulo frágil|código legacy|deuda técnica|alto riesgo)[:\s]+([^.\n]{10,100})',
                 _re.IGNORECASE), 0.8),
    (_re.compile(r'(Frm\w+ (?:tiene|presenta|contiene)[^.\n]{10,80})',
                 _re.IGNORECASE), 0.65),
]


# ── Singleton por proyecto ────────────────────────────────────────────────────

_memory_instances: dict[str, AgentMemory] = {}
_memory_lock = threading.Lock()


def get_agent_memory(project_name: str) -> AgentMemory:
    """Retorna (y cachea) una instancia de AgentMemory por proyecto."""
    with _memory_lock:
        if project_name not in _memory_instances:
            _memory_instances[project_name] = AgentMemory(project_name)
        return _memory_instances[project_name]
