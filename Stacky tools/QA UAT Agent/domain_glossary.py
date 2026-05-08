"""
domain_glossary.py — Glosario funcional → columnas DB para RSPACIFICO.

PROBLEMA RESUELTO
-----------------
`precondition_parser.py` necesita mapear términos funcionales del lenguaje
del analista QA ("el corredor del cliente", "riesgo de entrada", "lote activo")
a columnas reales de la BD (ROBLG.OGCORREDOR, RCLIE.CLRIESGOENT, RLOTE.LOESTADO).

Sin este glosario, el parser dependería 100% del LLM para resolver cada término,
lo cual es lento, costoso y no determinístico.

ESTRATEGIA: CAPAS DE RESOLUCIÓN
---------------------------------
1. Schema token match (schema_explorer.find_column) — si el término aparece
   literalmente en un nombre de columna → match directo. Sin LLM.
2. Glossary match (este módulo) — términos funcionales mapeados a columnas.
   Cubiertos aquí: ~80% de los casos del dominio RSPACIFICO.
3. LLM fallback — solo para términos no cubiertos por 1 ni 2.

CONTRATO (domain_glossary.json — extensible)
---------------------------------------------
  {
    "version": "1.0",
    "updated_at": "...",
    "entries": [
      {
        "term": "corredor",
        "aliases": ["corredor principal", "agente corredor", "cod corredor"],
        "mappings": [
          {"table": "ROBLG", "column": "OGCORREDOR", "polarity": "value"},
          {"table": "RCLIE", "column": "CLCORREDOR", "polarity": "value"}
        ],
        "description": "Código de corredor asignado a la obligación/cliente"
      }
    ]
  }

POLARITY
--------
  "value"   → el término busca el valor de esta columna (SELECT OGCORREDOR FROM ...)
  "flag"    → el término indica un flag booleano/estado (IS NOT NULL, = 'S', etc.)
  "exists"  → el término indica existencia de registro (COUNT > 0)
  "range"   → el término indica un rango (BETWEEN, >=, <=)

API PÚBLICA
-----------
  lookup(term) → list[GlossaryMapping]
  lookup_with_polarity(term, polarity) → list[GlossaryMapping]
  register_term(term, table, column, polarity, aliases, description) → None
  get_all_terms() → list[str]
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.domain_glossary")

_TOOL_VERSION = "1.0.0"

_GLOSSARY_PATH = Path(__file__).resolve().parent / "cache" / "domain_glossary.json"


# ── Tipos ──────────────────────────────────────────────────────────────────────

@dataclass
class GlossaryMapping:
    table: str
    column: str
    polarity: str = "value"  # value | flag | exists | range
    condition: str = ""      # condición adicional (ej: "LOESTADO = 'A'")
    priority: int = 0        # menor = más relevante


@dataclass
class GlossaryEntry:
    term: str
    aliases: list[str] = field(default_factory=list)
    mappings: list[GlossaryMapping] = field(default_factory=list)
    description: str = ""


# ── Glosario estático (fallback — siempre disponible) ─────────────────────────
# Términos confirmados para el dominio RSPACIFICO / Agenda Web
# Columnas verificadas con db_query_119.py en 2026-05-04

_STATIC_GLOSSARY: list[GlossaryEntry] = [

    # ── CORREDOR ──────────────────────────────────────────────────────────────
    GlossaryEntry(
        term="corredor",
        aliases=["corredor principal", "agente corredor", "cod corredor",
                 "código corredor", "corredor asignado", "corredores"],
        mappings=[
            GlossaryMapping(table="ROBLG", column="OGCORREDOR", polarity="value", priority=0),
            GlossaryMapping(table="RCLIE", column="CLCORREDOR", polarity="value", priority=1),
        ],
        description="Código de corredor asignado a la obligación o cliente",
    ),

    # ── RIESGO ────────────────────────────────────────────────────────────────
    GlossaryEntry(
        term="riesgo",
        aliases=["riesgo de entrada", "riesgo ent", "riesgo ingreso",
                 "nivel de riesgo", "clasificación de riesgo", "riesgos"],
        mappings=[
            # Columna confirmada: RCLIE.CLRIESGOENT (NOT CLRIESGOSIS)
            GlossaryMapping(table="RCLIE", column="CLRIESGOENT", polarity="value", priority=0),
        ],
        description="Riesgo de entrada del cliente (RCLIE.CLRIESGOENT)",
    ),

    # ── LOTE ──────────────────────────────────────────────────────────────────
    GlossaryEntry(
        term="lote",
        aliases=["id lote", "código lote", "cod lote", "lote activo",
                 "lote asignado", "lotes"],
        mappings=[
            # Columna confirmada: RLOTE.LOCOD (NOT IDLOTE)
            GlossaryMapping(table="RLOTE", column="LOCOD", polarity="value", priority=0),
            GlossaryMapping(table="ROBLG", column="OGLOTE", polarity="value", priority=1),
            GlossaryMapping(table="RAGEN", column="AGLOTE", polarity="value", priority=2),
        ],
        description="Identificador de lote (RLOTE.LOCOD)",
    ),

    # ── CLIENTE ───────────────────────────────────────────────────────────────
    GlossaryEntry(
        term="cliente",
        aliases=["id cliente", "código cliente", "cod cliente",
                 "rut cliente", "rut", "deudor"],
        mappings=[
            GlossaryMapping(table="RCLIE", column="CLCOD", polarity="value", priority=0),
        ],
        description="Identificador de cliente (RCLIE.CLCOD)",
    ),

    GlossaryEntry(
        term="nombre cliente",
        aliases=["nombre deudor", "apellido cliente", "nombre completo"],
        mappings=[
            GlossaryMapping(table="RCLIE", column="CLNOMBRE", polarity="value", priority=0),
        ],
        description="Nombre del cliente",
    ),

    # ── OBLIGACIÓN ────────────────────────────────────────────────────────────
    GlossaryEntry(
        term="obligacion",
        aliases=["obligación", "id obligacion", "cod obligacion",
                 "número obligacion", "numero obligacion"],
        mappings=[
            GlossaryMapping(table="ROBLG", column="OGCORREDOR", polarity="exists", priority=0),
        ],
        description="Obligación del cliente en un lote",
    ),

    # ── AGENTE ────────────────────────────────────────────────────────────────
    GlossaryEntry(
        term="agente",
        aliases=["id agente", "perfil agente", "agente asignado",
                 "código agente", "cod agente"],
        mappings=[
            GlossaryMapping(table="RAGEN", column="AGPERFIL", polarity="value", priority=0),
        ],
        description="Perfil/ID del agente en RAGEN",
    ),

    # ── ESTADO LOTE ───────────────────────────────────────────────────────────
    GlossaryEntry(
        term="lote activo",
        aliases=["lote en estado activo", "lote activado", "lotes activos"],
        mappings=[
            GlossaryMapping(
                table="RLOTE", column="LOESTADO",
                polarity="flag", condition="LOESTADO = 'A'", priority=0,
            ),
        ],
        description="Lote con estado activo (RLOTE.LOESTADO = 'A')",
    ),

    # ── SISTEMA ───────────────────────────────────────────────────────────────
    GlossaryEntry(
        term="sistema",
        aliases=["id sistema", "cod sistema", "código sistema"],
        mappings=[
            GlossaryMapping(table="RASIST", column="SISSISTEMA", polarity="value", priority=0),
        ],
        description="Código de sistema en RASIST",
    ),

    # ── MOTIVO ────────────────────────────────────────────────────────────────
    GlossaryEntry(
        term="motivo",
        aliases=["motivo gestion", "motivo de gestión", "id motivo",
                 "cod motivo", "código motivo"],
        mappings=[
            GlossaryMapping(table="RAGMOT", column="AGMMOTIVO", polarity="value", priority=0),
        ],
        description="Motivo de gestión en RAGMOT",
    ),

    # ── CALIDAD ───────────────────────────────────────────────────────────────
    GlossaryEntry(
        term="calidad",
        aliases=["calidad gestion", "calidad de gestión", "id calidad",
                 "cod calidad", "código calidad"],
        mappings=[
            GlossaryMapping(table="RAGCAL", column="AGCCALIDAD", polarity="value", priority=0),
        ],
        description="Calidad de gestión en RAGCAL",
    ),

    # ── IDIOMA / RIDIOMA ──────────────────────────────────────────────────────
    GlossaryEntry(
        term="idioma",
        aliases=["ridioma", "idtexto", "id texto", "texto idioma",
                 "texto de pantalla"],
        mappings=[
            GlossaryMapping(table="RIDIOMA", column="IDTEXTO", polarity="value", priority=0),
            GlossaryMapping(table="RIDIOMA", column="IDIDIOMA", polarity="value", priority=1),
        ],
        description="Texto de UI en RIDIOMA (IDTEXTO = código de texto)",
    ),
]

# Cache en memoria
_GLOSSARY_CACHE: Optional[list[GlossaryEntry]] = None


# ── API pública ────────────────────────────────────────────────────────────────

def lookup(term: str) -> list[GlossaryMapping]:
    """
    Busca un término funcional en el glosario.

    Retorna lista de GlossaryMapping ordenada por priority (menor = mejor).
    Vacío si el término no está en el glosario.

    Búsqueda: normaliza, busca en term exacto, luego en aliases.
    """
    term_norm = _normalize(term)
    entries = _get_entries()

    for entry in entries:
        if _normalize(entry.term) == term_norm:
            return sorted(entry.mappings, key=lambda m: m.priority)

    # Buscar en aliases
    for entry in entries:
        if any(_normalize(a) == term_norm for a in entry.aliases):
            return sorted(entry.mappings, key=lambda m: m.priority)

    # Búsqueda parcial (el término contiene el término del glosario o viceversa)
    partial_matches = []
    for entry in entries:
        entry_norm = _normalize(entry.term)
        if entry_norm in term_norm or term_norm in entry_norm:
            for m in entry.mappings:
                partial_matches.append((m.priority + 10, m))  # penalidad por match parcial
        for alias in entry.aliases:
            alias_norm = _normalize(alias)
            if alias_norm in term_norm or term_norm in alias_norm:
                for m in entry.mappings:
                    partial_matches.append((m.priority + 5, m))

    if partial_matches:
        partial_matches.sort(key=lambda x: x[0])
        # Deduplicar por (table, column)
        seen = set()
        result = []
        for _, m in partial_matches:
            key = (m.table, m.column)
            if key not in seen:
                seen.add(key)
                result.append(m)
        return result

    return []


def lookup_with_polarity(term: str, polarity: str) -> list[GlossaryMapping]:
    """Filtra los mappings de un término por polarity."""
    return [m for m in lookup(term) if m.polarity == polarity]


def get_all_terms() -> list[str]:
    """Retorna lista de todos los términos del glosario (terms + aliases)."""
    terms = []
    for entry in _get_entries():
        terms.append(entry.term)
        terms.extend(entry.aliases)
    return terms


def register_term(
    term: str,
    table: str,
    column: str,
    polarity: str = "value",
    aliases: Optional[list[str]] = None,
    description: str = "",
    condition: str = "",
) -> None:
    """
    Registra un nuevo término en el glosario (cache + disco).

    Usado por el learning pipeline cuando el LLM resuelve un término nuevo
    y queremos evitar llamadas LLM en el futuro para el mismo término.
    """
    global _GLOSSARY_CACHE
    entries = _get_entries()

    new_mapping = GlossaryMapping(
        table=table.upper(), column=column.upper(),
        polarity=polarity, condition=condition,
    )

    # Buscar si el término ya existe
    for entry in entries:
        if _normalize(entry.term) == _normalize(term):
            # Añadir mapping si no existe
            existing_keys = {(m.table, m.column) for m in entry.mappings}
            if (new_mapping.table, new_mapping.column) not in existing_keys:
                entry.mappings.append(new_mapping)
                _GLOSSARY_CACHE = entries
                _write(entries)
                logger.info("domain_glossary: added mapping %s.%s to term '%s'",
                            table, column, term)
            return

    # Crear nueva entrada
    new_entry = GlossaryEntry(
        term=term.lower(),
        aliases=aliases or [],
        mappings=[new_mapping],
        description=description,
    )
    entries.append(new_entry)
    _GLOSSARY_CACHE = entries
    _write(entries)
    logger.info("domain_glossary: registered new term '%s' → %s.%s", term, table, column)


# ── Internos ──────────────────────────────────────────────────────────────────

def _get_entries() -> list[GlossaryEntry]:
    global _GLOSSARY_CACHE
    if _GLOSSARY_CACHE is None:
        _GLOSSARY_CACHE = _load()
    return _GLOSSARY_CACHE


def _load() -> list[GlossaryEntry]:
    entries = list(_STATIC_GLOSSARY)

    if _GLOSSARY_PATH.exists():
        try:
            raw = json.loads(_GLOSSARY_PATH.read_text(encoding="utf-8"))
            static_terms = {_normalize(e.term) for e in _STATIC_GLOSSARY}
            for item in raw.get("entries", []):
                term_norm = _normalize(item.get("term", ""))
                if term_norm in static_terms:
                    continue  # no sobreescribir estáticos con disco
                mappings = [
                    GlossaryMapping(
                        table=m["table"].upper(),
                        column=m["column"].upper(),
                        polarity=m.get("polarity", "value"),
                        condition=m.get("condition", ""),
                        priority=m.get("priority", 0),
                    )
                    for m in item.get("mappings", [])
                ]
                entries.append(GlossaryEntry(
                    term=item["term"],
                    aliases=item.get("aliases", []),
                    mappings=mappings,
                    description=item.get("description", ""),
                ))
            logger.debug("domain_glossary: loaded %d entries total", len(entries))
        except Exception as exc:
            logger.warning("domain_glossary: could not load from disk: %s", exc)

    return entries


def _write(entries: list[GlossaryEntry]) -> None:
    try:
        _GLOSSARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        static_terms = {_normalize(e.term) for e in _STATIC_GLOSSARY}
        to_persist = [
            {
                "term": e.term,
                "aliases": e.aliases,
                "description": e.description,
                "mappings": [asdict(m) for m in e.mappings],
            }
            for e in entries
            if _normalize(e.term) not in static_terms
        ]
        payload = {
            "version": "1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entries": to_persist,
        }
        _GLOSSARY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("domain_glossary: could not write to disk: %s", exc)


def _normalize(text: str) -> str:
    """Normaliza para comparación: minúsculas, sin tildes, sin espacios extra."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text.lower().strip())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="domain_glossary — glosario funcional → columnas DB")
    parser.add_argument("--lookup", metavar="TERMINO", help="Buscar término en el glosario")
    parser.add_argument("--list", action="store_true", help="Listar todos los términos")
    args = parser.parse_args()

    if args.lookup:
        mappings = lookup(args.lookup)
        if mappings:
            print(f"'{args.lookup}' → {len(mappings)} mapping(s):")
            for m in mappings:
                print(f"  {m.table}.{m.column} ({m.polarity})"
                      + (f" | condition: {m.condition}" if m.condition else ""))
        else:
            print(f"Término '{args.lookup}' no encontrado en el glosario")
    elif args.list:
        for e in _get_entries():
            print(f"  {e.term}: {', '.join(f'{m.table}.{m.column}' for m in e.mappings)}")
    else:
        parser.print_help()
