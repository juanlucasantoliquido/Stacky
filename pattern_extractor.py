"""
pattern_extractor.py — N-06: Auto-documentación de patrones fix.

Después de cada pipeline completado con QA aprobado, extrae el patrón de solución
y lo agrega a la knowledge base del proyecto como "patrón conocido".

Con el tiempo, esto construye una biblioteca de soluciones probadas que se inyecta
en futuros prompts de PM cuando se detecta similitud con un patrón existente.

Uso:
    from pattern_extractor import extract_and_store_pattern, get_relevant_patterns
    extract_and_store_pattern(ticket_folder, ticket_id, project_name)
    patterns = get_relevant_patterns(inc_content, project_name, top_k=3)
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("stacky.pattern_extractor")

# ── Tipos de patrón ───────────────────────────────────────────────────────────
_PATTERN_TYPES = {
    "null_reference":   ["nullreferenceexception", "object reference", "null pointer",
                         "campo nulo", "clienteid null", "valor null"],
    "validation":       ["validación", "validar", "campo requerido", "ridioma",
                         "mensaje al usuario", "error.agregar"],
    "dal_query":        ["dal_", "query oracle", "all_tab_columns", "where clause",
                         "parametrized", "oraclecommand"],
    "performance":      ["rendimiento", "lentitud", "timeout", "índice", "full scan",
                         "query lenta", "explain plan"],
    "ui_webforms":      ["aspx", "codebehind", "postback", "viewstate", "frm",
                         "btn_click", "gridview"],
    "logging":          ["log.error", "log.info", "logging", "trazabilidad"],
    "batch_process":    ["batch", "proceso masivo", "scheduler", "scheduled task"],
    "integration":      ["webservice", "integración", "soap", "rest api", "endpoint"],
}


def extract_and_store_pattern(ticket_folder: str, ticket_id: str,
                               project_name: str) -> bool:
    """
    Extrae el patrón de solución del ticket completado y lo guarda en la KB.
    Retorna True si se extrajo y guardó un patrón útil.
    """
    # Solo procesar tickets con QA aprobado
    tester_path = os.path.join(ticket_folder, "TESTER_COMPLETADO.md")
    if not os.path.exists(tester_path):
        return False

    tester_content = Path(tester_path).read_text(encoding="utf-8", errors="replace")
    if "APROBADO" not in tester_content.upper():
        return False  # No guardar patrones de tickets rechazados/con observaciones

    # Leer fuentes
    inc_content  = _read_safe(ticket_folder, f"INC-{ticket_id}.md",  3000)
    analisis     = _read_safe(ticket_folder, "ANALISIS_TECNICO.md",   2000)
    arq          = _read_safe(ticket_folder, "ARQUITECTURA_SOLUCION.md", 2000)
    dev_done     = _read_safe(ticket_folder, "DEV_COMPLETADO.md",     2000)

    if not inc_content or not analisis:
        return False

    # Determinar tipo de patrón
    combined_lower = (inc_content + analisis + arq).lower()
    pattern_types  = []
    for ptype, keywords in _PATTERN_TYPES.items():
        if sum(1 for kw in keywords if kw in combined_lower) >= 2:
            pattern_types.append(ptype)

    if not pattern_types:
        pattern_types = ["general"]

    # Extraer elementos clave del patrón
    root_cause   = _extract_section(analisis, ["causa raíz", "causa:", "root cause"])
    solution     = _extract_section(arq, ["solución", "cambios", "qué cambiar"])
    files_mod    = _extract_modified_files(dev_done)
    symptoms     = _extract_symptoms(inc_content)

    pattern = {
        "id":            f"{project_name}_{ticket_id}",
        "ticket_id":     ticket_id,
        "project":       project_name,
        "types":         pattern_types,
        "symptoms":      symptoms[:3],
        "root_cause":    root_cause[:300] if root_cause else "",
        "solution":      solution[:400] if solution else "",
        "files_affected": files_mod[:6],
        "created_at":    datetime.now().isoformat(),
        "seen_count":    1,
    }

    return _save_pattern(pattern, project_name)


def get_relevant_patterns(inc_content: str, project_name: str,
                           top_k: int = 3) -> list[dict]:
    """
    Busca patrones relevantes para un nuevo ticket.
    Retorna lista de patrones ordenados por relevancia.
    """
    patterns = _load_patterns(project_name)
    if not patterns:
        return []

    inc_lower = inc_content.lower()
    scored    = []

    for pattern in patterns:
        score = 0
        # Score por síntomas en el INC
        for symptom in pattern.get("symptoms", []):
            if symptom.lower() in inc_lower:
                score += 3
        # Score por tipo de patrón
        for ptype in pattern.get("types", []):
            keywords = _PATTERN_TYPES.get(ptype, [])
            score += sum(1 for kw in keywords if kw in inc_lower)
        # Bonus por frecuencia (patrón visto más veces)
        score += min(pattern.get("seen_count", 1) - 1, 3)

        if score > 0:
            scored.append((score, pattern))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:top_k]]


def format_patterns_section(patterns: list[dict]) -> str:
    """Formatea patrones como sección Markdown para inyectar en prompts."""
    if not patterns:
        return ""

    lines = [
        "",
        "---",
        "",
        "## Patrones de solución conocidos (similares a este ticket)",
        "",
        "_Basado en tickets resueltos anteriormente. Usar como referencia, no como receta exacta._",
        "",
    ]
    for i, p in enumerate(patterns, 1):
        tid     = p.get("ticket_id", "?")
        ptypes  = ", ".join(p.get("types", ["general"]))
        cause   = p.get("root_cause", "")
        sol     = p.get("solution", "")
        files   = p.get("files_affected", [])
        seen    = p.get("seen_count", 1)

        lines += [
            f"### Patrón #{i} — Ticket #{tid} ({ptypes}) — visto {seen}x",
            "",
        ]
        if cause:
            lines += [f"**Causa raíz:** {cause}", ""]
        if sol:
            lines += [f"**Solución aplicada:** {sol}", ""]
        if files:
            lines += [f"**Archivos típicamente afectados:** {', '.join(files[:4])}", ""]
        lines.append("")

    return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_safe(folder: str, fname: str, max_chars: int = 3000) -> str:
    try:
        return Path(os.path.join(folder, fname)).read_text(
            encoding="utf-8", errors="replace")[:max_chars]
    except Exception:
        return ""


def _extract_section(content: str, headers: list[str]) -> str:
    """Extrae el contenido de una sección por nombre de header."""
    for header in headers:
        pattern = re.compile(
            rf'#+\s*{re.escape(header)}.*?\n(.*?)(?=\n#+\s|\Z)',
            re.IGNORECASE | re.DOTALL
        )
        m = pattern.search(content)
        if m:
            text = m.group(1).strip()
            if len(text) > 20:
                return text
    return ""


def _extract_symptoms(inc_content: str) -> list[str]:
    """Extrae síntomas/descripción del error del INC."""
    symptoms = []
    # Buscar frases de error
    for pat in [
        r'(?:error|falla|problema|bug)[:\s]+([^.\n]{20,100})',
        r'(?:se produce|ocurre cuando)[:\s]+([^.\n]{20,100})',
        r'al\s+(?:hacer|ejecutar|guardar|cargar)\s+([^.\n]{10,80})',
    ]:
        matches = re.findall(pat, inc_content, re.IGNORECASE)
        symptoms.extend(m.strip() for m in matches[:2])
    return symptoms[:3]


def _extract_modified_files(dev_content: str) -> list[str]:
    """Extrae archivos modificados del DEV_COMPLETADO."""
    pat   = re.compile(r'[\w/\\]+\.(?:cs|aspx|aspx\.cs|vb|sql)', re.IGNORECASE)
    files = []
    for m in pat.finditer(dev_content):
        f = m.group(0).replace("\\", "/")
        if f not in files and "stacky" not in f.lower():
            files.append(f)
    return files[:6]


def _get_patterns_path(project_name: str) -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    kb   = os.path.join(base, "knowledge", project_name)
    os.makedirs(kb, exist_ok=True)
    return os.path.join(kb, "patterns.json")


def _load_patterns(project_name: str) -> list[dict]:
    path = _get_patterns_path(project_name)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_pattern(pattern: dict, project_name: str) -> bool:
    path     = _get_patterns_path(project_name)
    patterns = _load_patterns(project_name)

    # Verificar si ya existe (mismo ticket_id) → incrementar seen_count
    for i, existing in enumerate(patterns):
        if existing.get("ticket_id") == pattern["ticket_id"]:
            patterns[i]["seen_count"] = existing.get("seen_count", 1) + 1
            _write_patterns(path, patterns)
            return True

    patterns.append(pattern)
    # Mantener máximo 500 patrones (los más recientes)
    if len(patterns) > 500:
        patterns = patterns[-500:]

    _write_patterns(path, patterns)
    logger.info("[PATTERN] Patrón guardado: %s (%s)",
                pattern["ticket_id"], ", ".join(pattern["types"]))
    return True


def _write_patterns(path: str, patterns: list[dict]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(patterns, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("[PATTERN] Error guardando patterns.json: %s", e)
