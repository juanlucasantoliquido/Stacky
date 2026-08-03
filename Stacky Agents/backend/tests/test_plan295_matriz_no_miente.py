"""Plan 295 F2 + F2a -- la matriz deja de mentir, y su guardian admite SIMBOLOS.

F2  (casos 1-4): las DOS entradas de CAPABILITY_MATRIX["gitlab"] que declaraban
    ausente o degradada una capacidad IMPLEMENTADA Y ON desde los planes 276 y 292.
F2a (casos 5-7): el guardian del 218 (`_EVIDENCE_RE`) exigia `archivo.py:DIGITOS`,
    o sea exactamente lo que este plan quiere eliminar. Se AMPLIA para aceptar
    linea O simbolo, sin ceder nada de lo que hoy rechaza.

Los casos 5-7 importan `_EVIDENCE_RE` DESDE tests.test_plan218_capability_matrix,
no lo redefinen: probar una copia del regex en vez del que corre en el gate es el
falso verde clasico.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.provider_capabilities import (  # noqa: E402
    CAPABILITY_MATRIX,
    capability_status,
    supports,
)

_CLAVES = ("tracker.sync.incremental", "tracker.rate_limit.clamp")


# ---------------------------------------------------------------- F2 (1-4) ---
def test_1_gitlab_declara_full_el_sync_incremental():
    """El plan 292 lo implemento y nace ON; la matriz lo declaraba `absent` y el
    panel de Diagnostico se lo mostraba asi al operador."""
    assert capability_status("gitlab", "tracker.sync.incremental") == "full"


def test_2_gitlab_declara_full_el_clamp_de_retry_after():
    """El 276 F9 puso el clamp a 30 s en _resolver_retry_after y la matriz seguia
    declarando la perdida YA RESUELTA."""
    assert capability_status("gitlab", "tracker.rate_limit.clamp") == "full"


def test_3_las_dos_evidencias_nuevas_son_por_simbolo():
    for clave in _CLAVES:
        ev = str(CAPABILITY_MATRIX["gitlab"][clave].get("evidence") or "")
        assert ":" in ev, f"gitlab/{clave}: evidencia sin ancla -> {ev!r}"
        assert re.search(r":\d+$", ev) is None, (
            f"gitlab/{clave}: la evidencia sigue anclada por LINEA ({ev!r}). "
            "Una linea caduca con el primer commit ajeno: anclá por SIMBOLO."
        )


def test_4_supports_la_via_consultiva_dice_true_para_las_dos():
    """supports() es la que usa el codigo de produccion, no capability_status."""
    for clave in _CLAVES:
        assert supports("gitlab", clave) is True, f"gitlab/{clave}"


# --------------------------------------------------------------- F2a (5-7) ---
def _evidence_re():
    from tests.test_plan218_capability_matrix import _EVIDENCE_RE

    return _EVIDENCE_RE


def test_5_el_guardian_del_218_acepta_evidencia_por_simbolo():
    er = _evidence_re()
    assert er.match("services/gitlab_sync.py:sync_gitlab_tickets") is not None
    assert er.match("services/gitlab_client.py:_resolver_retry_after") is not None
    # y la LINEA sigue siendo valida: el ratchet de F4 es descendente, no un corte.
    assert er.match("services/gitlab_client.py:146") is not None


def test_6_el_guardian_sigue_rechazando_vacio_y_archivo_pelado():
    er = _evidence_re()
    assert er.match("") is None
    assert er.match("services/x.py") is None


def test_7_el_guardian_sigue_rechazando_lo_que_no_es_un_simbolo():
    er = _evidence_re()
    assert er.match("services/x.py:no es un simbolo") is None
    assert er.match("services/x.py:") is None
    # Clase.metodo queda fuera a proposito: no se resuelve con un solo getattr,
    # asi que seria un anclaje que el gate de F3 no puede verificar.
    assert er.match("services/x.py:Clase.metodo") is None
