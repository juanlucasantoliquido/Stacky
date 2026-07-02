"""Plan 56 — Gate de Regresión: Golden Positivo + Golden Negativo.

Funciones PURAS (F0) y IO (F1). Sin LLM, sin red (salvo JSON local), sin reloj.
Determinismo total: las funciones de derivación y evaluación son idempotentes.

Modelo de datos
---------------
- Golden(NamedTuple): unidad mínima de expectativa (negativa o positiva).
- derive_negative_golden: nota de rechazo → Golden negativo.
- derive_positive_golden: HTML aprobado → Golden positivo.
- evaluate_regression: HTML candidato + goldens → lista de defectos.

Persistencia (F1)
-----------------
- save_golden / load_goldens: JSON en backend/harness/goldens/<key>.json.
  Versionado en repo para auditoría; sin BD.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger("stacky.regression_goldens")

# Directorio de almacenamiento relativo al paquete harness/
_GOLDENS_DIR = Path(__file__).parent / "goldens"


# ── Modelo ───────────────────────────────────────────────────────────────────

class Golden(NamedTuple):
    kind: str               # "negative" | "positive"
    check: str              # "absent_substring" | "present_heading"
    value: str              # patrón: substring normalizado o heading canónico
    project: str | None
    agent_type: str
    work_item_type: str     # "Epic" | "Issue"
    confidence_band: str | None = None  # "high" si positivo condicional


# ── F0 — Derivadores puros ────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase + colapsar whitespace."""
    return re.sub(r"\s+", " ", text.lower()).strip()


_TAG_RE = re.compile(r"<[^>]+>")


def _normalize_html_text(html: str) -> str:
    """Plan 81 F0b — quita tags HTML y luego normaliza (matching tag-agnóstico)."""
    return _normalize(_TAG_RE.sub(" ", html or ""))


def derive_negative_golden(
    *,
    rejection_note: str,
    project: str | None,
    agent_type: str,
    work_item_type: str,
) -> Golden | None:
    """PURA. Nota de rechazo → Golden negativo (absent_substring).

    Heurística: el substring normalizado de la nota NO debe reaparecer en el
    próximo output. Nota vacía → None.

    LIMITE documentado: si la nota varía en redacción, no detecta regresión.
    Mitigación: modo warning (no bloqueante) por defecto.
    """
    value = _normalize(rejection_note)
    if not value:
        return None
    return Golden(
        kind="negative",
        check="absent_substring",
        value=value,
        project=project,
        agent_type=agent_type,
        work_item_type=work_item_type,
        confidence_band=None,
    )


_NEG_FROM_EDIT_MIN_LEN = 15  # Plan 81 — snippet normalizado más corto no es señal confiable
_NEG_FROM_EDIT_MAX = 5       # Plan 81 — cap por edición (anti-envenenamiento del catálogo)


def derive_negative_goldens_from_removed(
    *,
    removed_snippets: list,
    edited_text: str,
    project: str | None,
    agent_type: str,
    work_item_type: str,
) -> list:
    """PURA. Plan 81 — snippets borrados por el humano → goldens negativos (absent_substring).

    Guards deterministas, en orden:
      1. snippet normalizado (_normalize) con len < _NEG_FROM_EDIT_MIN_LEN → skip.
      2. snippet aún presente (como substring) en edited_text normalizado → skip
         (fue re-formateo/merge de frases, NO un borrado de contenido).
      3. dedup por valor normalizado dentro de la misma edición.
      4. cap _NEG_FROM_EDIT_MAX, preservando el orden de aparición.
    Lista vacía / None / todo filtrado → []. Nunca lanza.
    """
    edited_norm = _normalize(edited_text or "")
    out: list = []
    seen: set = set()
    for s in (removed_snippets or []):
        v = _normalize(str(s))
        if len(v) < _NEG_FROM_EDIT_MIN_LEN:
            continue
        if v in seen:
            continue
        if v in edited_norm:
            continue
        g = derive_negative_golden(
            rejection_note=str(s),
            project=project,
            agent_type=agent_type,
            work_item_type=work_item_type,
        )
        if g is None:
            continue
        seen.add(v)
        out.append(g)
        if len(out) >= _NEG_FROM_EDIT_MAX:
            break
    return out


def _extract_first_rf_heading(clean_html: str) -> str | None:
    """Extrae el primer heading h2 que parezca un bloque RF (contiene RF-)."""
    pattern = re.compile(r"<h2[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
    for m in pattern.finditer(clean_html):
        text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if re.search(r"RF-\d+", text, re.IGNORECASE):
            return _normalize(text)
    return None


def derive_positive_golden(
    *,
    clean_html: str,
    project: str | None,
    agent_type: str,
    work_item_type: str,
    confidence: float | None = None,
) -> Golden | None:
    """PURA. HTML aprobado → Golden positivo (present_heading).

    Extrae el primer heading RF como marcador estructural mínimo.
    HTML sin marcador RF → None (no hay estructura que proteger).
    confidence >= 0.75 → confidence_band='high' (positivo condicional de alta confianza).
    """
    heading = _extract_first_rf_heading(clean_html)
    if not heading:
        return None
    band: str | None = None
    if confidence is not None and confidence >= 0.75:
        band = "high"
    return Golden(
        kind="positive",
        check="present_heading",
        value=heading,
        project=project,
        agent_type=agent_type,
        work_item_type=work_item_type,
        confidence_band=band,
    )


def evaluate_regression(
    *,
    clean_html: str,
    goldens: list[Golden],
    process_catalog: list | None = None,
    current_confidence: float | None = None,
) -> list[str]:
    """PURA. Devuelve códigos de defecto de regresión.

    - "regression_negative:<value>" si golden negativo REAPARECE en el HTML.
    - "regression_positive_missing:<value>" si golden positivo FALTA en el HTML.

    Selectividad:
    - golden.confidence_band == None: siempre se evalúa.
    - golden.confidence_band == "high": solo si current_confidence >= 0.75.

    Sin goldens → [] (NO-OP).
    """
    if not goldens:
        return []

    html_norm = _normalize(clean_html)
    text_norm = _normalize_html_text(clean_html)  # Plan 81 F0b
    defects: list[str] = []

    for g in goldens:
        # Aplicar filtro de banda de confidence
        if g.confidence_band == "high":
            if current_confidence is None or current_confidence < 0.75:
                continue  # skip: confidence actual no alcanza la banda

        if g.kind == "negative" and g.check == "absent_substring":
            # Defecto: el substring rechazado reaparece
            # Plan 81 F0b: comparar contra texto sin tags inline (los removed_snippets
            # vienen de texto plano; sin esto una épica con <strong>Mul2Bane</strong> escapa).
            if g.value in text_norm:
                defects.append(f"regression_negative:{g.value}")

        elif g.kind == "positive" and g.check == "present_heading":
            # Defecto: el heading esperado no está
            if g.value not in html_norm:
                defects.append(f"regression_positive_missing:{g.value}")

    return defects


# ── F1 — Persistencia (JSON versionado en repo) ───────────────────────────────

def _golden_key(g: Golden) -> tuple:
    """Clave de dedup: (kind, check, value)."""
    return (g.kind, g.check, g.value)


def _store_path(*, project: str | None, agent_type: str, work_item_type: str) -> Path:
    """Ruta del JSON de goldens para (project, agent_type, work_item_type)."""
    proj_slug = (project or "global").replace("/", "_").replace("\\", "_")
    fname = f"{proj_slug}__{agent_type}__{work_item_type}.json"
    return _GOLDENS_DIR / fname


def save_golden(g: Golden) -> None:
    """Persiste golden idempotente (no duplica por (kind, check, value)).

    Crea el directorio goldens/ si no existe.
    """
    _GOLDENS_DIR.mkdir(parents=True, exist_ok=True)
    path = _store_path(project=g.project, agent_type=g.agent_type, work_item_type=g.work_item_type)

    existing = load_goldens(project=g.project, agent_type=g.agent_type, work_item_type=g.work_item_type)
    existing_keys = {_golden_key(e) for e in existing}

    if _golden_key(g) in existing_keys:
        return  # ya existe — no duplicar

    existing.append(g)
    raw = [list(e) for e in existing]  # NamedTuple → list para JSON
    try:
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        logger.warning("save_golden: no se pudo escribir %s", path, exc_info=True)


def load_goldens(*, project: str | None, agent_type: str, work_item_type: str) -> list[Golden]:
    """Carga goldens del JSON. [] si archivo inexistente o JSON corrupto (no lanza)."""
    path = _store_path(project=project, agent_type=agent_type, work_item_type=work_item_type)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [Golden(*entry) for entry in raw]
    except Exception:  # noqa: BLE001
        logger.warning("load_goldens: JSON corrupto en %s, devuelve []", path)
        return []
