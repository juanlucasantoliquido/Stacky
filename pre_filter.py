"""
pre_filter.py — E-05: Detector de tickets auto-cerrables (pre-filtro sin IA).

Antes de invertir PM+DEV+QA en un ticket, analiza el INC-{id}.md localmente
y detecta casos que no deberían procesarse automáticamente:

  - DUPLICADO:      descripción muy similar a un ticket ya resuelto
  - SIN_INFO:       descripción muy corta, sin pasos de reproducción
  - FUERA_SCOPE:    keywords de otro equipo (infra, servidor, accesos)
  - YA_RESUELTO:    el fix ya existe en el trunk (búsqueda literal)

Cada categoría genera una nota específica en la carpeta del ticket
(PRE_FILTER_RESULT.json) para que el daemon decida si procesar o no.

Uso:
    from pre_filter import pre_filter_ticket, FilterResult
    result = pre_filter_ticket(ticket_folder, ticket_id, tickets_base, workspace_root)
    if result.should_skip:
        # No procesar — ver result.reason y result.category
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("mantis.pre_filter")

# ── Configuración ─────────────────────────────────────────────────────────────

# Keywords que indican que el ticket es de otro equipo
_OUT_OF_SCOPE_KEYWORDS = [
    "infraestructura", "servidor", "server", "deploy", "despliegue", "firewall",
    "red ", "network", "acceso a ", "permisos de ", "usuario de red",
    "vpn", "certificado ssl", "dns", "ip address", "puerto ", "port ",
    "backup", "restaurar base", "restore ", "dba ", "administrador de base",
    "licencia ", "license ", "hardware", "memoria ram", "disco duro",
]

# Mínimo de palabras en la descripción para no ser considerado "sin info"
_MIN_DESCRIPTION_WORDS = 30

# Umbral de similitud para considerar duplicado (0-1)
_DUPLICATE_THRESHOLD = 0.70

# Máximo de tickets del historial a comparar para duplicados
_MAX_HISTORY_TO_CHECK = 100


@dataclass
class FilterResult:
    ticket_id:   str
    should_skip: bool
    category:    str   # "OK" | "DUPLICADO" | "SIN_INFO" | "FUERA_SCOPE" | "YA_RESUELTO"
    reason:      str
    confidence:  float = 1.0
    similar_to:  str   = ""   # ticket_id del posible duplicado

    def to_dict(self) -> dict:
        return asdict(self)


# ── API pública ───────────────────────────────────────────────────────────────

def pre_filter_ticket(ticket_folder: str, ticket_id: str,
                      tickets_base: str, workspace_root: str = "") -> FilterResult:
    """
    Ejecuta todos los filtros sobre el ticket y retorna el resultado.
    Escribe PRE_FILTER_RESULT.json en la carpeta del ticket.
    """
    inc_path = os.path.join(ticket_folder, f"INC-{ticket_id}.md")
    if not os.path.exists(inc_path):
        result = FilterResult(ticket_id=ticket_id, should_skip=False,
                              category="OK", reason="INC no encontrado — no filtrar")
        _write_result(ticket_folder, result)
        return result

    content = Path(inc_path).read_text(encoding="utf-8", errors="replace")

    # Ejecutar filtros en orden de costo (más baratos primero)
    for check_fn in [_check_sin_info, _check_fuera_scope,
                     _check_duplicado, _check_ya_resuelto]:
        try:
            result = check_fn(ticket_id, content, tickets_base, workspace_root)
            if result.should_skip:
                _write_result(ticket_folder, result)
                logger.info("[PRE-FILTER] %s → SKIP (%s): %s",
                            ticket_id, result.category, result.reason[:80])
                return result
        except Exception as e:
            logger.debug("[PRE-FILTER] Error en %s: %s", check_fn.__name__, e)

    result = FilterResult(ticket_id=ticket_id, should_skip=False,
                          category="OK", reason="Pasó todos los filtros")
    _write_result(ticket_folder, result)
    return result


def load_filter_result(ticket_folder: str) -> FilterResult | None:
    """Carga el resultado de filtro previo si existe."""
    path = os.path.join(ticket_folder, "PRE_FILTER_RESULT.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return FilterResult(**data)
    except Exception:
        return None


# ── Filtros individuales ──────────────────────────────────────────────────────

def _check_sin_info(ticket_id: str, content: str,
                    tickets_base: str, workspace_root: str) -> FilterResult:
    """Detecta tickets con descripción insuficiente."""
    # Extraer sección de descripción
    desc = _extract_description(content)
    word_count = len(desc.split())

    if word_count < _MIN_DESCRIPTION_WORDS:
        return FilterResult(
            ticket_id=ticket_id, should_skip=True, category="SIN_INFO",
            reason=(f"Descripción muy corta ({word_count} palabras, mínimo "
                    f"{_MIN_DESCRIPTION_WORDS}). Requiere más información para procesar."),
            confidence=0.9,
        )

    # Verificar que tenga pasos de reproducción o descripción del problema
    has_steps = bool(re.search(
        r'(pasos|steps|reproduce|reproducir|para reproducir|cómo reproducir'
        r'|se produce cuando|ocurre cuando|error al|falla cuando)',
        content, re.IGNORECASE
    ))
    has_expected = bool(re.search(
        r'(esperado|expected|debería|deberia|resultado esperado|comportamiento esperado)',
        content, re.IGNORECASE
    ))

    if word_count < 60 and not has_steps and not has_expected:
        return FilterResult(
            ticket_id=ticket_id, should_skip=True, category="SIN_INFO",
            reason="Ticket sin pasos de reproducción ni resultado esperado. "
                   "No hay suficiente información para análisis.",
            confidence=0.75,
        )

    return FilterResult(ticket_id=ticket_id, should_skip=False,
                        category="OK", reason="Información suficiente")


def _check_fuera_scope(ticket_id: str, content: str,
                       tickets_base: str, workspace_root: str) -> FilterResult:
    """Detecta tickets que corresponden a otro equipo."""
    content_lower = content.lower()
    matched = [kw for kw in _OUT_OF_SCOPE_KEYWORDS if kw in content_lower]

    if len(matched) >= 2:  # al menos 2 keywords para evitar falsos positivos
        return FilterResult(
            ticket_id=ticket_id, should_skip=True, category="FUERA_SCOPE",
            reason=(f"Keywords de infraestructura/administración detectados: "
                    f"{', '.join(matched[:4])}. Posiblemente corresponde a otro equipo."),
            confidence=0.8,
        )
    return FilterResult(ticket_id=ticket_id, should_skip=False,
                        category="OK", reason="Sin keywords fuera de scope")


def _check_duplicado(ticket_id: str, content: str,
                     tickets_base: str, workspace_root: str) -> FilterResult:
    """Busca tickets similares ya resueltos."""
    if not tickets_base or not os.path.isdir(tickets_base):
        return FilterResult(ticket_id=ticket_id, should_skip=False,
                            category="OK", reason="Sin base de tickets para comparar")

    desc_current = _normalize_text(_extract_description(content))
    if len(desc_current) < 20:
        return FilterResult(ticket_id=ticket_id, should_skip=False,
                            category="OK", reason="Descripción muy corta para comparar")

    best_sim    = 0.0
    best_match  = ""
    checked     = 0

    # Buscar en tickets completados (carpeta archivado o tester_completado)
    completed_dirs = []
    for estado in ["archivado", "aceptada", "resuelta"]:
        d = os.path.join(tickets_base, estado)
        if os.path.isdir(d):
            completed_dirs.append(d)
    # También buscar en tickets con TESTER_COMPLETADO.md en asignada
    asignada_dir = os.path.join(tickets_base, "asignada")
    if os.path.isdir(asignada_dir):
        completed_dirs.append(asignada_dir)

    for base_dir in completed_dirs:
        if checked >= _MAX_HISTORY_TO_CHECK:
            break
        try:
            for tid in os.listdir(base_dir):
                if tid == ticket_id or checked >= _MAX_HISTORY_TO_CHECK:
                    continue
                inc_other = os.path.join(base_dir, tid, f"INC-{tid}.md")
                if not os.path.exists(inc_other):
                    continue
                # Solo comparar si tiene TESTER_COMPLETADO.md (fue procesado)
                tester_flag = os.path.join(base_dir, tid, "TESTER_COMPLETADO.md")
                if not os.path.exists(tester_flag):
                    continue
                try:
                    other_content = Path(inc_other).read_text(
                        encoding="utf-8", errors="replace")[:3000]
                    desc_other = _normalize_text(_extract_description(other_content))
                    sim = _jaccard_similarity(desc_current, desc_other)
                    if sim > best_sim:
                        best_sim   = sim
                        best_match = tid
                    checked += 1
                except Exception:
                    pass
        except Exception:
            pass

    if best_sim >= _DUPLICATE_THRESHOLD:
        return FilterResult(
            ticket_id=ticket_id, should_skip=True, category="DUPLICADO",
            reason=(f"Muy similar al ticket #{best_match} ya procesado "
                    f"(similitud: {best_sim:.0%}). Verificar si es duplicado."),
            confidence=best_sim,
            similar_to=best_match,
        )
    return FilterResult(ticket_id=ticket_id, should_skip=False,
                        category="OK", reason=f"Sin duplicados (máx similitud: {best_sim:.0%})")


def _check_ya_resuelto(ticket_id: str, content: str,
                       tickets_base: str, workspace_root: str) -> FilterResult:
    """Detecta si la solución ya existe en el codebase."""
    # Solo aplica si hay workspace y menciona un fix específico
    if not workspace_root or not os.path.isdir(workspace_root):
        return FilterResult(ticket_id=ticket_id, should_skip=False,
                            category="OK", reason="Sin workspace para verificar")

    # Extraer nombres de métodos/clases específicos del ticket
    method_matches = re.findall(
        r'\b((?:Fix|Solve|Resolve|Arreglar|Correg)[A-Z][a-zA-Z]{3,})\b',
        content
    )
    if not method_matches:
        return FilterResult(ticket_id=ticket_id, should_skip=False,
                            category="OK", reason="Sin métodos fix específicos a verificar")

    # Buscar si esos métodos existen en el trunk
    for method in method_matches[:3]:
        for root, dirs, files in os.walk(workspace_root):
            dirs[:] = [d for d in dirs
                       if d not in {"bin", "obj", "node_modules", ".git", ".svn"}]
            for fname in files:
                if not fname.endswith(".cs"):
                    continue
                try:
                    fpath   = os.path.join(root, fname)
                    fcontent = Path(fpath).read_text(encoding="utf-8", errors="replace")
                    if method.lower() in fcontent.lower():
                        rel = os.path.relpath(fpath, workspace_root).replace("\\", "/")
                        return FilterResult(
                            ticket_id=ticket_id, should_skip=True,
                            category="YA_RESUELTO",
                            reason=(f"Método '{method}' encontrado en {rel}. "
                                    f"Posiblemente ya fue resuelto."),
                            confidence=0.6,
                        )
                except Exception:
                    pass

    return FilterResult(ticket_id=ticket_id, should_skip=False,
                        category="OK", reason="Fix no encontrado en codebase")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_description(content: str) -> str:
    """Extrae la sección de descripción del INC."""
    in_desc = False
    desc_lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if re.match(r'^#+\s*(descripción|description|resumen|summary|detalle)',
                    stripped, re.IGNORECASE):
            in_desc = True
            continue
        if in_desc and re.match(r'^#+\s', stripped):
            break
        if in_desc:
            desc_lines.append(stripped)
    if desc_lines:
        return " ".join(desc_lines)
    # Fallback: todo el contenido
    return content


def _normalize_text(text: str) -> set[str]:
    """Tokeniza y normaliza texto para comparación."""
    _STOP = {"el", "la", "los", "las", "un", "una", "de", "en", "y", "a",
             "que", "es", "se", "no", "con", "por", "para", "al", "del",
             "lo", "le", "su", "si", "hay", "pero", "como", "más"}
    tokens = re.findall(r'\b\w{3,}\b', text.lower())
    return {t for t in tokens if t not in _STOP}


def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """Calcula similitud Jaccard entre dos sets de tokens."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union        = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _write_result(ticket_folder: str, result: FilterResult) -> None:
    """Persiste el resultado del filtro en PRE_FILTER_RESULT.json."""
    path = os.path.join(ticket_folder, "PRE_FILTER_RESULT.json")
    try:
        data = result.to_dict()
        data["timestamp"] = datetime.now().isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.debug("Error escribiendo PRE_FILTER_RESULT.json: %s", e)
