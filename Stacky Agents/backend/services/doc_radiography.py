"""Plan 284 — Radiografía documental: cobertura módulo↔nota sobre el grafo del 109/268.

Es una LECTURA DERIVADA del grafo que ya existe: no construye un grafo paralelo,
no persiste nada, no llama al LLM.
"""
from __future__ import annotations


def compute_coverage(graph: dict, workspace_root: str | None) -> dict:
    """Cobertura documental. PURA respecto del grafo: NO reconstruye nada.

    Forma GARANTIZADA (las 7 claves siempre presentes):
      {"enabled": bool, "modules_total": int, "modules_covered": int,
       "coverage_ratio": float, "uncovered": [str], "orphan_notes": [str],
       "by_doc_class": {clase: int}}

    Nunca lanza: ante error devuelve la forma con enabled=True y ceros.
    """
    from config import config as _cfg
    vacio = {"enabled": False, "modules_total": 0, "modules_covered": 0,
             "coverage_ratio": 0.0, "uncovered": [], "orphan_notes": [],
             "by_doc_class": {}}
    if not bool(getattr(_cfg, "STACKY_DOCS_RADIOGRAPHY_ENABLED", False)):
        return vacio
    try:
        g = graph or {}
        salud = g.get("doc_health") or {}
        uncovered = list(salud.get("uncovered_modules") or [])
        nodos = g.get("nodes") or []

        # ── OJO: el total NO sale de doc_health ──────────────────────────
        # uncovered_modules es SOLO la lista de los NO cubiertos: no trae el
        # total, y además viene vacía en 3 de las 4 ramas de
        # classify_doc_health (SIN_DOCS, FORMATO_NO_OBSIDIAN, SANA) y en el
        # except. De ahí no se puede derivar un ratio. El total sale de los
        # nodos de código del grafo.
        modulos = {str(n.get("path") or "") for n in nodos
                   if str(n.get("kind") or "") in ("code", "module", "missing")}
        modulos.discard("")
        total = len(modulos) or len(uncovered)
        cubiertos = max(total - len(uncovered), 0)
        ratio = 1.0 if total == 0 else cubiertos / total

        notas = [str(n.get("path") or "") for n in nodos
                 if str(n.get("kind") or "") == "note"]
        from services import doc_taxonomy
        return {"enabled": True, "modules_total": total,
                "modules_covered": cubiertos, "coverage_ratio": ratio,
                "uncovered": uncovered,
                "orphan_notes": list(g.get("orphans") or []),
                "by_doc_class": doc_taxonomy.summarize_classes(notas)}
    except Exception:
        return dict(vacio, enabled=True)


def compute_coverage_delta(actual: dict, previo: dict | None) -> dict:
    """Plan 284 A2 — variación de cobertura respecto del run anterior.

    Forma GARANTIZADA: {"has_previous": bool, "ratio_delta": float,
                        "modules_closed": [str], "modules_opened": [str]}
    - modules_closed: módulos que estaban sin cubrir y ahora sí lo están.
    - modules_opened: módulos que aparecieron sin cubrir (regresión o código nuevo).
    Nunca lanza.

    Es lo que convierte al Documentador de foto en instrumento: un ratio
    absoluto ("cobertura 68%") no se interpreta sin memoria; la derivada sí.
    """
    vacio = {"has_previous": False, "ratio_delta": 0.0,
             "modules_closed": [], "modules_opened": []}
    try:
        if not previo or not previo.get("enabled"):
            return vacio
        ant = set(previo.get("uncovered") or [])
        act = set((actual or {}).get("uncovered") or [])
        return {
            "has_previous": True,
            "ratio_delta": float((actual or {}).get("coverage_ratio", 0.0))
                           - float(previo.get("coverage_ratio", 0.0)),
            "modules_closed": sorted(ant - act),
            "modules_opened": sorted(act - ant),
        }
    except Exception:
        return vacio
