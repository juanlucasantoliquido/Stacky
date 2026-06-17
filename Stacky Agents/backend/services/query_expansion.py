"""I2.3 — Normalización y expansión de query para retrieval sin FTS5.

Funciones puras, sin deps externas. Usadas de forma OPT-IN: solo cuando
`STACKY_RETRIEVAL_EXPANSION_ENABLED=true`, sobre el QUERY (nunca el corpus).

API pública:
  - `normalize_text(text)` — fold de acentos, lowercase, colapso de espacios.
  - `expand_query(tokens)` — tokens + sinónimos del dominio, deduplicados.

Principio: `_tokenize` global de `services/embeddings.py` NUNCA se muta.
El opt-in se aplica llamando a estas funciones ANTES de pasar el texto al
tokenizer habitual, o expandiendo los tokens resultado del tokenizer.
"""
from __future__ import annotations

import unicodedata


# ---------------------------------------------------------------------------
# Normalización de texto
# ---------------------------------------------------------------------------

_ACCENT_MAP: dict[str, str] = {
    "á": "a", "à": "a", "â": "a", "ä": "a",
    "é": "e", "è": "e", "ê": "e", "ë": "e",
    "í": "i", "ì": "i", "î": "i", "ï": "i",
    "ó": "o", "ò": "o", "ô": "o", "ö": "o",
    "ú": "u", "ù": "u", "û": "u", "ü": "u",
    "ñ": "n",
    # Mayúsculas (por si acaso el texto no fue lowercaseado antes)
    "Á": "a", "À": "a", "Â": "a", "Ä": "a",
    "É": "e", "È": "e", "Ê": "e", "Ë": "e",
    "Í": "i", "Ì": "i", "Î": "i", "Ï": "i",
    "Ó": "o", "Ò": "o", "Ô": "o", "Ö": "o",
    "Ú": "u", "Ù": "u", "Û": "u", "Ü": "u",
    "Ñ": "n",
}

_TRANS = str.maketrans(_ACCENT_MAP)


def normalize_text(text: str) -> str:
    """Fold de acentos, lowercase, colapso de espacios.

    Ejemplo:
        "Facturación ÑOÑO" → "facturacion nono"
    """
    if not text:
        return ""
    # Aplicar mapa de acentos y lowercase
    folded = text.translate(_TRANS).lower()
    # Colapso de whitespace (tabs, newlines, múltiples espacios)
    return " ".join(folded.split())


# ---------------------------------------------------------------------------
# Expansión de query con sinónimos del dominio
# ---------------------------------------------------------------------------

# Diccionario estático de sinónimos del dominio.
# Cada conjunto incluye las formas que el retrieval debe tratar como equivalentes.
# NO requiere LLM ni DB. Normalizado (sin acentos, minúsculas).
_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"factura", "facturacion", "comprobante"}),
    frozenset({"tarea", "task"}),
    frozenset({"error", "falla", "bug"}),
    frozenset({"refactor", "refactoring", "refactorizacion"}),
    frozenset({"migracion", "migration"}),
    frozenset({"integracion", "integration"}),
    frozenset({"reporte", "report", "informe"}),
    frozenset({"usuario", "user"}),
    frozenset({"configuracion", "configuration", "config", "setting"}),
    frozenset({"base", "datos", "database", "db"}),
    frozenset({"prueba", "test", "testing"}),
    frozenset({"deployment", "despliegue", "deploy"}),
    frozenset({"endpoint", "api", "servicio", "service"}),
    frozenset({"cliente", "client"}),
    frozenset({"autenticacion", "authentication", "auth", "login"}),
)

# Índice inverso: token → frozenset de sinónimos
_SYNONYM_INDEX: dict[str, frozenset[str]] = {}
for _group in _SYNONYM_GROUPS:
    for _token in _group:
        _SYNONYM_INDEX[_token] = _group


def expand_query(tokens: list[str]) -> list[str]:
    """Agrega sinónimos/variantes a la lista de tokens del dominio.

    Retorna `tokens + extras` deduplicados, preservando el orden original.
    Los tokens que no tienen sinónimos en el diccionario se conservan tal cual.

    Ejemplo:
        ["factura", "errores"] → ["factura", "errores", "facturacion", "comprobante", "error", "falla", "bug"]
    """
    if not tokens:
        return tokens
    seen: set[str] = set(tokens)
    result = list(tokens)
    for tok in tokens:
        group = _SYNONYM_INDEX.get(tok)
        if group is None:
            continue
        for syn in sorted(group):  # sorted para determinismo
            if syn not in seen:
                result.append(syn)
                seen.add(syn)
    return result
