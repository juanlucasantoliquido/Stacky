"""
precondition_parser.py — Parser universal de precondiciones funcionales → condiciones SQL.

PROBLEMA RESUELTO
-----------------
Las precondiciones de los escenarios QA vienen en lenguaje funcional libre:
  - "El cliente debe tener corredor asignado (código 1)"
  - "El lote debe estar activo"
  - "Existe obligación con riesgo de entrada = 'A'"
  - "RIDIOMA 9296 aplicado"

Para verificar estas precondiciones en BD, el pipeline necesita:
  1. Identificar QUÉ tabla y columna verificar.
  2. QUÉ valor/condición esperar.
  3. CÓMO construir la query SQL segura.

Sin este parser, `data_resolver.py` usaba FIELD_HINTS estáticos con nombres
de columna incorrectos → queries que fallaban silenciosamente.

ARQUITECTURA DE 3 CAPAS
-----------------------
  Capa 1: Schema token match (schema_explorer.find_column)
    → El término contiene literalmente un fragmento de nombre de columna.
    → Ejemplo: "corredor" → schema_explorer.find_column("corredor")
               → ROBLG.OGCORREDOR, RCLIE.CLCORREDOR
    → Sin LLM. Determinístico. Rápido.

  Capa 2: Domain glossary match (domain_glossary.lookup)
    → El término está en el glosario funcional del dominio.
    → Ejemplo: "riesgo de entrada" → RCLIE.CLRIESGOENT
    → Sin LLM. Determinístico. Cubre ~80% de los casos.

  Capa 3: LLM fallback (solo cuando capas 1+2 no resuelven)
    → Llamada a gpt-4o-mini con schema + glosario como contexto.
    → El resultado se guarda en resolution_cache para evitar re-llamadas.
    → Solo para términos genuinamente ambiguos.

CONTRATO DE SALIDA (ParsedCondition)
--------------------------------------
  {
    "term": "corredor",
    "source": "glossary",           # schema | glossary | llm | manual
    "table": "ROBLG",
    "column": "OGCORREDOR",
    "operator": "=",
    "value": "1",                   # None si no se extrae valor del texto
    "condition": "OGCORREDOR IS NOT NULL",  # condición completa para SQL
    "confidence": 0.95,
    "polarity": "value",
    "join_path": [...]              # JoinStep list si requiere JOIN
  }

OUTPUT FILES (emitidos por uat_precondition_checker.py)
---------------------------------------------------------
  evidence/<ticket>/<run_id>/resolved_values.json  — valores resueltos para uso en specs
  evidence/<ticket>/<run_id>/precondition_gap.json — precondiciones no resueltas
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.precondition_parser")

_TOOL_VERSION = "1.0.0"

# Regex para extraer RIDIOMA IDs
_RIDIOMA_RE = re.compile(r'(?:RIDIOMA|IDTEXTO)[=\s]+(\d+(?:[-,]\d+)*)', re.IGNORECASE)

# Regex para extraer valores literales entre comillas o numéricos
_VALUE_RE = re.compile(r"""[=:]\s*['"]?([A-Za-z0-9_\-\.]+)['"]?""")
_NUMERIC_RE = re.compile(r'\b(\d{1,10})\b')


# ── Tipos ──────────────────────────────────────────────────────────────────────

@dataclass
class ParsedCondition:
    """Condición SQL lista para ser ejecutada por sql_builder.py."""
    term: str                       # término funcional original
    source: str                     # "schema" | "glossary" | "llm" | "ridioma" | "manual"
    table: str                      # tabla SQL
    column: str                     # columna SQL
    operator: str = "IS NOT NULL"   # operador SQL (=, IS NOT NULL, >, etc.)
    value: Optional[str] = None     # valor si el operador es = o similar
    condition: str = ""             # condición SQL completa (para override)
    confidence: float = 1.0         # 0..1
    polarity: str = "value"         # value | flag | exists | range
    join_path: list = field(default_factory=list)  # list[dict] de join steps

    def to_dict(self) -> dict:
        return asdict(self)

    def to_sql_condition(self) -> str:
        """Retorna la condición SQL como string."""
        if self.condition:
            return self.condition
        if self.operator.upper() in ("IS NOT NULL", "IS NULL"):
            return f"{self.table}.{self.column} {self.operator}"
        if self.value is not None:
            return f"{self.table}.{self.column} {self.operator} '{self.value}'"
        return f"{self.table}.{self.column} IS NOT NULL"


@dataclass
class ParseResult:
    """Resultado del parser para una precondición completa."""
    original: str                              # texto original
    conditions: list[ParsedCondition]          # condiciones resueltas
    ridioma_ids: list[int]                     # IDs de RIDIOMA encontrados
    unresolved: list[str]                      # términos no resueltos
    parse_method: str                          # "full_resolved" | "partial" | "ridioma_only" | "unresolved"

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "conditions": [c.to_dict() for c in self.conditions],
            "ridioma_ids": self.ridioma_ids,
            "unresolved": self.unresolved,
            "parse_method": self.parse_method,
        }


# ── Parser principal ──────────────────────────────────────────────────────────

def parse(
    precondition_text: str,
    connection=None,
    use_llm: bool = True,
) -> ParseResult:
    """
    Parsea una precondición funcional a condiciones SQL estructuradas.

    Ejecuta las 3 capas en orden:
      1. RIDIOMA check (si el texto menciona RIDIOMA/IDTEXTO)
      2. Schema token match
      3. Domain glossary match
      4. LLM fallback (solo si use_llm=True y capas 1-3 no resuelven)

    Args:
      precondition_text: Texto de la precondición en lenguaje funcional.
      connection: Conexión DB opcional para schema discovery.
      use_llm: Si True, llama al LLM cuando las capas 1-3 no resuelven.

    Returns:
      ParseResult con conditions, ridioma_ids y unresolved.
    """
    text = precondition_text.strip()
    conditions: list[ParsedCondition] = []
    unresolved: list[str] = []

    # ── Capa 0: RIDIOMA check ──────────────────────────────────────────────────
    ridioma_ids = _extract_ridioma_ids(text)
    if ridioma_ids:
        for rid in ridioma_ids:
            conditions.append(ParsedCondition(
                term=f"RIDIOMA IDTEXTO={rid}",
                source="ridioma",
                table="RIDIOMA",
                column="IDTEXTO",
                operator="=",
                value=str(rid),
                condition=f"RIDIOMA.IDTEXTO = {rid}",
                confidence=1.0,
                polarity="value",
            ))
        return ParseResult(
            original=text,
            conditions=conditions,
            ridioma_ids=ridioma_ids,
            unresolved=[],
            parse_method="ridioma_only",
        )

    # ── Capa 1: Schema token match ────────────────────────────────────────────
    schema_conditions = _try_schema_match(text, connection=connection)
    if schema_conditions:
        return ParseResult(
            original=text,
            conditions=schema_conditions,
            ridioma_ids=[],
            unresolved=[],
            parse_method="schema",
        )

    # ── Capa 2: Domain glossary match ──────────────────────────────────────────
    glossary_conditions = _try_glossary_match(text)
    if glossary_conditions:
        return ParseResult(
            original=text,
            conditions=glossary_conditions,
            ridioma_ids=[],
            unresolved=[],
            parse_method="glossary",
        )

    # ── Capa 3: LLM fallback ──────────────────────────────────────────────────
    if use_llm:
        llm_conditions = _try_llm_match(text, connection=connection)
        if llm_conditions:
            return ParseResult(
                original=text,
                conditions=llm_conditions,
                ridioma_ids=[],
                unresolved=[],
                parse_method="llm",
            )

    # No resuelto
    unresolved.append(text)
    return ParseResult(
        original=text,
        conditions=[],
        ridioma_ids=[],
        unresolved=unresolved,
        parse_method="unresolved",
    )


def parse_all(
    preconditions: list[str],
    connection=None,
    use_llm: bool = True,
) -> list[ParseResult]:
    """
    Parsea una lista de precondiciones.
    Retorna una ParseResult por cada precondición.
    """
    results = []
    for prec in preconditions:
        if not prec or not prec.strip():
            continue
        result = parse(prec, connection=connection, use_llm=use_llm)
        results.append(result)
        if result.parse_method != "unresolved":
            logger.debug(
                "precondition_parser: '%s...' → %s (%d conditions)",
                prec[:50], result.parse_method, len(result.conditions),
            )
        else:
            logger.info("precondition_parser: unresolved: '%s...'", prec[:80])
    return results


def emit_resolved_values(
    parse_results: list[ParseResult],
    scenario_id: str,
    out_path: Path,
) -> dict:
    """
    Emite `resolved_values.json` con los valores resueltos para uso en specs.

    Formato:
    {
      "scenario_id": "P04",
      "resolved": {
        "CORREDOR": {"table": "ROBLG", "column": "OGCORREDOR", "sql_condition": "..."},
        "RIESGO": {"table": "RCLIE", "column": "CLRIESGOENT", "sql_condition": "..."},
      },
      "unresolved": ["texto que no se pudo resolver"],
      "ridioma_ids": [9296, 9297]
    }
    """
    resolved: dict = {}
    all_unresolved: list[str] = []
    all_ridioma_ids: list[int] = []

    for r in parse_results:
        all_unresolved.extend(r.unresolved)
        all_ridioma_ids.extend(r.ridioma_ids)
        for cond in r.conditions:
            if cond.source == "ridioma":
                continue
            key = f"{cond.table}_{cond.column}"
            resolved[key] = {
                "term": cond.term,
                "table": cond.table,
                "column": cond.column,
                "sql_condition": cond.to_sql_condition(),
                "source": cond.source,
                "confidence": cond.confidence,
            }

    payload = {
        "scenario_id": scenario_id,
        "resolved": resolved,
        "unresolved": all_unresolved,
        "ridioma_ids": sorted(set(all_ridioma_ids)),
    }

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("precondition_parser: resolved_values.json → %s", out_path)
    except Exception as exc:
        logger.warning("precondition_parser: could not write resolved_values.json: %s", exc)

    return payload


def emit_precondition_gap(
    parse_results: list[ParseResult],
    scenario_id: str,
    out_path: Path,
) -> dict:
    """
    Emite `precondition_gap.json` con las precondiciones no resueltas.

    Este archivo permite al operador identificar qué datos faltan
    y resolverlos manualmente antes de ejecutar los tests.
    """
    gaps = []
    for r in parse_results:
        for u in r.unresolved:
            gaps.append({
                "original": u,
                "suggestion": (
                    "Verificar si existe en el dominio glossary. "
                    "Usar `python domain_glossary.py --lookup \"<término>\"` para buscar."
                ),
            })

    payload = {
        "scenario_id": scenario_id,
        "gap_count": len(gaps),
        "gaps": gaps,
    }

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("precondition_parser: precondition_gap.json → %s (%d gaps)", out_path, len(gaps))
    except Exception as exc:
        logger.warning("precondition_parser: could not write precondition_gap.json: %s", exc)

    return payload


# ── Capas de resolución ───────────────────────────────────────────────────────

def _try_schema_match(text: str, connection=None) -> list[ParsedCondition]:
    """Capa 1: busca tokens del texto en nombres de columnas del schema."""
    try:
        from schema_explorer import find_column
    except ImportError:
        return []

    conditions = []
    text_lower = text.lower()

    # Extraer tokens del texto (palabras de 4+ letras)
    tokens = re.findall(r'\b([a-záéíóúñüa-z]{4,})\b', text_lower)
    seen_cols: set = set()

    for token in tokens:
        matches = find_column(token, connection=connection, max_results=3)
        for (table, col) in matches:
            key = (table, col)
            if key in seen_cols:
                continue
            seen_cols.add(key)
            value = _extract_value_from_text(text)
            conditions.append(ParsedCondition(
                term=token,
                source="schema",
                table=table,
                column=col,
                operator="=" if value else "IS NOT NULL",
                value=value,
                confidence=0.7,
                polarity="value",
            ))

    return conditions


def _try_glossary_match(text: str) -> list[ParsedCondition]:
    """Capa 2: busca el texto en el glosario funcional del dominio."""
    try:
        from domain_glossary import lookup
        from join_registry import get_join_path
    except ImportError:
        return []

    conditions = []

    # Probar el texto completo primero
    mappings = lookup(text)
    if not mappings:
        # Probar tokens del texto
        tokens = _extract_meaningful_tokens(text)
        for token in tokens:
            mappings = lookup(token)
            if mappings:
                break

    if not mappings:
        return []

    value = _extract_value_from_text(text)
    for m in mappings[:2]:  # máximo 2 mappings por precondición
        # Si hay condición explícita en el glossary, usarla
        if m.condition:
            conditions.append(ParsedCondition(
                term=text[:80],
                source="glossary",
                table=m.table,
                column=m.column,
                operator="custom",
                value=value,
                condition=m.condition,
                confidence=0.9,
                polarity=m.polarity,
            ))
        else:
            conditions.append(ParsedCondition(
                term=text[:80],
                source="glossary",
                table=m.table,
                column=m.column,
                operator="=" if value else "IS NOT NULL",
                value=value,
                confidence=0.9,
                polarity=m.polarity,
            ))

    return conditions


def _try_llm_match(text: str, connection=None) -> list[ParsedCondition]:
    """
    Capa 3: llama al LLM con contexto de schema + glosario.

    Solo se invoca cuando las capas 1 y 2 fallan.
    Usa resolution_cache para evitar llamadas repetidas.
    """
    try:
        from resolution_cache import get_cached, set_cached
    except ImportError:
        get_cached = set_cached = None  # type: ignore

    # Check cache primero
    if get_cached is not None:
        cached = get_cached(text)
        if cached:
            logger.debug("precondition_parser: LLM cache hit for '%s...'", text[:40])
            return [
                ParsedCondition(
                    term=c["term"], source="llm",
                    table=c["table"], column=c["column"],
                    operator=c.get("operator", "IS NOT NULL"),
                    value=c.get("value"),
                    confidence=c.get("confidence", 0.6),
                )
                for c in cached
            ]

    # Preparar contexto para el LLM
    try:
        from schema_explorer import get_tables, get_columns
        from domain_glossary import get_all_terms
        tables = get_tables(connection=connection)[:30]
        schema_snippet = {t: get_columns(t)[:10] for t in tables[:20]}
        glossary_terms = get_all_terms()[:30]
    except Exception:
        schema_snippet = {}
        glossary_terms = []

    system_prompt = """You are a SQL expert for the RSPACIFICO database (SQL Server, read-only user RSPACIFICOREAD).
Given a functional precondition in Spanish, identify the DB table and column to check.
Respond ONLY with valid JSON array:
[{"table": "TABLE", "column": "COLUMN", "operator": "IS NOT NULL|=|>|<", "value": null_or_string, "confidence": 0.0_to_1.0}]
Rules:
- Only use tables and columns from the schema provided.
- Prefer specific columns over generic ones.
- If you cannot resolve, return [].
- Never guess table/column names — only use what's in the schema."""

    user_msg = f"""Schema (partial):
{json.dumps(schema_snippet, indent=2)[:2000]}

Known domain terms:
{', '.join(glossary_terms[:20])}

Precondition to parse:
"{text}"

Respond with JSON only."""

    try:
        import openai
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
            max_tokens=300,
        )
        raw = response.choices[0].message.content or "[]"
        # Strip markdown fences if present
        raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`")
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []

        conditions = []
        for item in parsed:
            if not item.get("table") or not item.get("column"):
                continue
            conditions.append(ParsedCondition(
                term=text[:80],
                source="llm",
                table=item["table"].upper(),
                column=item["column"].upper(),
                operator=item.get("operator", "IS NOT NULL"),
                value=item.get("value"),
                confidence=float(item.get("confidence", 0.6)),
            ))

        # Guardar en cache
        if conditions and set_cached is not None:
            set_cached(text, [c.to_dict() for c in conditions])

        return conditions

    except Exception as exc:
        logger.warning("precondition_parser: LLM fallback failed: %s", exc)
        return []


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_ridioma_ids(text: str) -> list[int]:
    """Extrae IDs de RIDIOMA de un texto de precondición."""
    ids: list[int] = []
    for match in _RIDIOMA_RE.finditer(text):
        raw = match.group(1)
        # Puede ser "9296,9297" o "9296-9298"
        if "-" in raw:
            parts = raw.split("-")
            if len(parts) == 2:
                try:
                    start, end = int(parts[0]), int(parts[1])
                    ids.extend(range(start, end + 1))
                except ValueError:
                    pass
        else:
            for part in raw.split(","):
                try:
                    ids.append(int(part.strip()))
                except ValueError:
                    pass
    return sorted(set(ids))


def _extract_value_from_text(text: str) -> Optional[str]:
    """
    Intenta extraer un valor literal de un texto de precondición.
    Busca patrones como: = 'A', = 1, código 1, valor "activo"
    """
    # Buscar valor entre comillas
    quoted = re.findall(r"""[=:]\s*['"]([^'"]{1,50})['"]""", text)
    if quoted:
        return quoted[0]

    # Buscar "= número"
    eq_num = re.findall(r'[=:]\s*(\d{1,10})\b', text)
    if eq_num:
        return eq_num[0]

    # Buscar "corredor N" / "código N" / "tipo N"
    labeled = re.findall(r'(?:corredor|código|tipo|id|valor)\s+(\d{1,10})\b', text, re.IGNORECASE)
    if labeled:
        return labeled[0]

    return None


def _extract_meaningful_tokens(text: str) -> list[str]:
    """Extrae tokens significativos del texto para búsqueda en glosario."""
    import unicodedata

    def normalize(t):
        nfkd = unicodedata.normalize("NFKD", t.lower())
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    stop_words = {
        "debe", "tener", "tiene", "estar", "este", "ser", "para",
        "como", "que", "con", "del", "los", "las", "una", "uno",
        "aplicado", "asignado", "existe", "existir", "verificar",
    }

    tokens = re.findall(r'\b([a-záéíóúñ]{4,})\b', normalize(text))
    return [t for t in tokens if t not in stop_words]
