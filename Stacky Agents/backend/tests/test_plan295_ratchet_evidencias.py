"""Plan 295 F4 — RATCHET de evidencias: los anclajes por LÍNEA solo bajan.

POR QUÉ. Una evidencia "archivo:123" caduca con el primer commit ajeno al archivo.
Este plan encontró una CADUCA en producción: tracker.items.list de GitLab apuntaba
a gitlab_provider.py:155, que cae dentro de _normalize_issue (:145), cuando
fetch_open_items está en :324. La evidencia mandaba a leer la función equivocada.

RATCHET, NO CORTE A CERO. Al escribir este plan había 104 evidencias por línea
(ADO 50 + GitLab 54). Exigir cero pondría 104 entradas en rojo de golpe -- rojo de
fábrica masivo, que este plan prohíbe. El tope solo puede BAJAR.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.provider_capabilities import CAPABILITY_MATRIX  # noqa: E402

# MEDIDO al implementar este plan (baseline F0 = 104; F2 convierte 1 por línea y
# F4 convierte 8 => 95). Este número SOLO PUEDE BAJAR: si tu cambio lo sube, estás
# agregando un anclaje que va a caducar. Anclá por SÍMBOLO.
_TOPE_EVIDENCIAS_POR_LINEA = 95

_POR_LINEA = re.compile(r"\.(py|ts|tsx|ps1|sh):\d+\s*$")


def _evidencias_por_linea() -> list[str]:
    fuera = []
    for proveedor, entradas in CAPABILITY_MATRIX.items():
        for clave, entrada in entradas.items():
            ev = str(entrada.get("evidence") or "")
            if ev and _POR_LINEA.search(ev):
                fuera.append(f"{proveedor}/{clave} -> {ev}")
    return sorted(fuera)


def test_hay_evidencias_para_medir():
    """Si el regex deja de matchear (cambio de formato), _evidencias_por_linea()
    devolvería [] y el ratchet pasaría EN FALSO para siempre. Este lo tapa:
    la matriz TIENE evidencias, así que el conjunto no puede ser vacío por diseño."""
    con_evidencia = [
        1
        for entradas in CAPABILITY_MATRIX.values()
        for e in entradas.values()
        if e.get("evidence")
    ]
    assert len(con_evidencia) >= 90, f"solo {len(con_evidencia)} entradas con evidencia"


def test_ratchet_evidencias_por_simbolo():
    fuera = _evidencias_por_linea()
    assert len(fuera) <= _TOPE_EVIDENCIAS_POR_LINEA, (
        f"{len(fuera)} evidencias ancladas por LÍNEA (tope {_TOPE_EVIDENCIAS_POR_LINEA}). "
        "Un anclaje por línea caduca con el primer commit ajeno. Anclá por SÍMBOLO "
        "('archivo.py:nombre_de_funcion') y BAJÁ el tope en el mismo commit.\n"
        + "\n".join(fuera[:15])
    )


def test_las_convertidas_por_este_plan_no_volvieron_a_linea():
    """ASSERT DE PRESENCIA del valor correcto (G7): el ratchet por sí solo permitiría
    convertir 8 cualesquiera. Estas 4 son las que este plan corrigió a propósito
    porque su anclaje era DEMOSTRABLEMENTE equivocado."""
    esperadas = {
        ("gitlab", "tracker.items.list"): "fetch_open_items",
        ("gitlab", "tracker.items.get"): "get_item",
        ("gitlab", "tracker.auth.html_redirect"): "_validar_base_url",
        ("gitlab", "tracker.rate_limit.clamp"): "_resolver_retry_after",
    }
    for (proveedor, clave), simbolo in esperadas.items():
        ev = str(CAPABILITY_MATRIX[proveedor][clave].get("evidence") or "")
        assert ev.endswith(f":{simbolo}"), f"{proveedor}/{clave} evidencia={ev!r}"


def test_los_webhooks_no_apuntan_al_emisor_saliente():
    """services/webhooks.py es el EMISOR de webhooks salientes de Stacky (fire/_sign).
    Citarlo como evidencia de events.webhook.inbound/verify manda al lector a leer
    código que no tiene nada que ver. Una capacidad absent puede ir sin evidencia."""
    for clave in ("events.webhook.inbound", "events.webhook.verify"):
        ev = str(CAPABILITY_MATRIX["gitlab"][clave].get("evidence") or "")
        assert "webhooks.py" not in ev, f"gitlab/{clave} sigue citando el emisor: {ev!r}"
