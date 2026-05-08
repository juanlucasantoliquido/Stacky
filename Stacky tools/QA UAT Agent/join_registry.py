"""
join_registry.py — Registro de joins entre tablas RSPACIFICO.

PROPÓSITO
---------
Cuando `precondition_parser.py` detecta que una precondición involucra datos
de múltiples tablas (ej: "el cliente del lote debe tener riesgo A"), necesita
conocer las claves de join para construir una query SQL correcta.

Este módulo provee ese conocimiento de forma persistente y extensible.

FUENTES DE CONOCIMIENTO
------------------------
1. `cache/join_registry.json` — joins descubiertos y verificados manualmente.
   Formato estructurado, versionado, extensible.
2. Fallback estático en código — garantiza funcionamiento sin cache.

CONTRATO (join_registry.json)
------------------------------
  {
    "version": "1.0",
    "updated_at": "2026-05-08T...",
    "joins": [
      {
        "from_table": "RLOTE",
        "from_col": "LOCOD",
        "to_table": "ROBLG",
        "to_col": "OGLOTE",
        "join_type": "INNER",
        "notes": "Lote → Obligaciones. Verified 2026-05-04."
      },
      ...
    ]
  }

API PÚBLICA
-----------
  get_join_path(from_table, to_table) → list[JoinStep] | None
  get_direct_join(t1, t2) → JoinStep | None
  register_join(from_table, from_col, to_table, to_col, notes="") → None
  get_all_joins() → list[JoinStep]
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.join_registry")

_TOOL_VERSION = "1.0.0"

_REGISTRY_PATH = Path(__file__).resolve().parent / "cache" / "join_registry.json"


# ── Tipos ──────────────────────────────────────────────────────────────────────

@dataclass
class JoinStep:
    from_table: str
    from_col: str
    to_table: str
    to_col: str
    join_type: str = "INNER"
    notes: str = ""

    def to_sql_fragment(self, from_alias: str = "", to_alias: str = "") -> str:
        """Genera el fragmento SQL para el JOIN."""
        fa = f"{self.from_table} {from_alias}".strip()
        ta = f"{self.to_table} {to_alias}".strip()
        lhs = f"{from_alias}.{self.from_col}" if from_alias else f"{self.from_table}.{self.from_col}"
        rhs = f"{to_alias}.{self.to_col}" if to_alias else f"{self.to_table}.{self.to_col}"
        return f"{self.join_type} JOIN {self.to_table} {to_alias} ON {lhs} = {rhs}".strip()


# ── Fallback estático — joins confirmados para RSPACIFICO ─────────────────────
# Verificados con db_query_119.py en 2026-05-04:
#   RLOTE.LOCOD → ROBLG.OGLOTE
#   ROBLG.OGCORREDOR, ROBLG.OGCODCLI → joins de obligación
#   RCLIE.CLCOD → identificador de cliente

_STATIC_JOINS: list[JoinStep] = [
    # Lote → Obligaciones
    JoinStep(
        from_table="RLOTE", from_col="LOCOD",
        to_table="ROBLG", to_col="OGLOTE",
        join_type="INNER",
        notes="Lote → Obligaciones. Verificado 2026-05-04.",
    ),
    # Obligaciones → Cliente (via OGCODCLI → CLCOD)
    JoinStep(
        from_table="ROBLG", from_col="OGCODCLI",
        to_table="RCLIE", to_col="CLCOD",
        join_type="INNER",
        notes="Obligaciones → Cliente. Verificado 2026-05-04.",
    ),
    # Lote → Agente (RLOTE a RAGEN — relación directa si existe AGENLOTE)
    JoinStep(
        from_table="RAGEN", from_col="AGLOTE",
        to_table="RLOTE", to_col="LOCOD",
        join_type="INNER",
        notes="Agente → Lote. RAGEN.AGLOTE es el lote ID del agente.",
    ),
    # Motivo de gestión
    JoinStep(
        from_table="RAGEN", from_col="AGPERFIL",
        to_table="RAGMOT", to_col="AGMPERFIL",
        join_type="LEFT",
        notes="Agente → Motivos de gestión permitidos (si RAGMOT tiene AGMPERFIL).",
    ),
]

# Cache en memoria
_REGISTRY_CACHE: Optional[list[JoinStep]] = None


# ── API pública ────────────────────────────────────────────────────────────────

def get_all_joins() -> list[JoinStep]:
    """Retorna todos los joins registrados (cache + estáticos)."""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is None:
        _REGISTRY_CACHE = _load()
    return _REGISTRY_CACHE


def get_direct_join(t1: str, t2: str) -> Optional[JoinStep]:
    """
    Retorna el JoinStep directo entre t1 y t2 (en cualquier dirección).
    Retorna None si no hay join directo registrado.
    """
    t1u, t2u = t1.upper(), t2.upper()
    for j in get_all_joins():
        if (j.from_table.upper() == t1u and j.to_table.upper() == t2u) or \
           (j.from_table.upper() == t2u and j.to_table.upper() == t1u):
            return j
    return None


def get_join_path(from_table: str, to_table: str) -> Optional[list[JoinStep]]:
    """
    Encuentra el camino de joins entre `from_table` y `to_table`.

    Implementa BFS sobre el grafo de joins registrados.
    Retorna la lista de JoinStep en orden, o None si no hay camino.

    Ejemplo:
      get_join_path("RLOTE", "RCLIE")
      → [RLOTE.LOCOD→ROBLG.OGLOTE, ROBLG.OGCODCLI→RCLIE.CLCOD]
    """
    start = from_table.upper()
    end   = to_table.upper()

    if start == end:
        return []

    all_joins = get_all_joins()

    # Construir grafo bidireccional
    graph: dict[str, list[JoinStep]] = {}
    for j in all_joins:
        ft = j.from_table.upper()
        tt = j.to_table.upper()
        graph.setdefault(ft, []).append(j)
        # Añadir inverso (join funciona en ambas direcciones)
        inv = JoinStep(
            from_table=j.to_table, from_col=j.to_col,
            to_table=j.from_table, to_col=j.from_col,
            join_type=j.join_type, notes=f"[inverse] {j.notes}",
        )
        graph.setdefault(tt, []).append(inv)

    # BFS
    from collections import deque
    visited = {start}
    queue: deque = deque([(start, [])])

    while queue:
        current, path = queue.popleft()
        for j in graph.get(current, []):
            next_table = j.to_table.upper()
            new_path = path + [j]
            if next_table == end:
                return new_path
            if next_table not in visited:
                visited.add(next_table)
                queue.append((next_table, new_path))

    return None


def register_join(
    from_table: str,
    from_col: str,
    to_table: str,
    to_col: str,
    join_type: str = "INNER",
    notes: str = "",
) -> None:
    """
    Registra un nuevo join en el cache en memoria y en disco.

    Usado por el learning pipeline cuando se descubre un nuevo join
    (ej: análisis de queries exitosas en el historial).
    """
    global _REGISTRY_CACHE

    new_join = JoinStep(
        from_table=from_table.upper(),
        from_col=from_col.upper(),
        to_table=to_table.upper(),
        to_col=to_col.upper(),
        join_type=join_type.upper(),
        notes=notes,
    )

    joins = get_all_joins()

    # Evitar duplicados exactos
    for existing in joins:
        if (existing.from_table == new_join.from_table and
                existing.from_col == new_join.from_col and
                existing.to_table == new_join.to_table and
                existing.to_col == new_join.to_col):
            logger.debug("join_registry: join already registered: %s.%s → %s.%s",
                         from_table, from_col, to_table, to_col)
            return

    joins.append(new_join)
    _REGISTRY_CACHE = joins
    _write(joins)
    logger.info("join_registry: registered %s.%s → %s.%s", from_table, from_col, to_table, to_col)


# ── Internos ──────────────────────────────────────────────────────────────────

def _load() -> list[JoinStep]:
    """Carga joins desde disco + fallback estático."""
    joins = list(_STATIC_JOINS)  # siempre incluir los estáticos

    if _REGISTRY_PATH.exists():
        try:
            raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
            for entry in raw.get("joins", []):
                j = JoinStep(
                    from_table=entry["from_table"].upper(),
                    from_col=entry["from_col"].upper(),
                    to_table=entry["to_table"].upper(),
                    to_col=entry["to_col"].upper(),
                    join_type=entry.get("join_type", "INNER").upper(),
                    notes=entry.get("notes", ""),
                )
                # Añadir solo si no está duplicado con los estáticos
                if not any(
                    e.from_table == j.from_table and e.from_col == j.from_col and
                    e.to_table == j.to_table and e.to_col == j.to_col
                    for e in joins
                ):
                    joins.append(j)
            logger.debug("join_registry: loaded %d joins from disk", len(joins))
        except Exception as exc:
            logger.warning("join_registry: could not load from disk: %s", exc)

    return joins


def _write(joins: list[JoinStep]) -> None:
    """Persiste los joins en disco (excluyendo los estáticos que ya están en código)."""
    try:
        _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Solo guardar los que no son estáticos (para evitar duplicados en disco)
        static_keys = {
            (j.from_table, j.from_col, j.to_table, j.to_col)
            for j in _STATIC_JOINS
        }
        to_persist = [
            j for j in joins
            if (j.from_table, j.from_col, j.to_table, j.to_col) not in static_keys
        ]
        payload = {
            "version": "1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "joins": [asdict(j) for j in to_persist],
        }
        _REGISTRY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("join_registry: could not write to disk: %s", exc)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="join_registry — joins de tablas RSPACIFICO")
    parser.add_argument("--list", action="store_true", help="Listar todos los joins")
    parser.add_argument("--path", nargs=2, metavar=("FROM", "TO"), help="Buscar camino de joins")
    args = parser.parse_args()

    if args.list:
        for j in get_all_joins():
            print(f"  {j.from_table}.{j.from_col} → {j.to_table}.{j.to_col} ({j.join_type})")
    elif args.path:
        path = get_join_path(args.path[0], args.path[1])
        if path:
            print(f"Path {args.path[0]} → {args.path[1]} ({len(path)} steps):")
            for s in path:
                print(f"  {s.from_table}.{s.from_col} → {s.to_table}.{s.to_col}")
        else:
            print(f"No join path found between {args.path[0]} and {args.path[1]}")
    else:
        parser.print_help()
