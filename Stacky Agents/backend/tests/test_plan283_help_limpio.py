"""Plan 283 F1 (v2/C7) - Las 4 reglas de la ayuda llana, aplicadas SOLO a las 5
keys de este plan.

Por que existe. `tests/test_harness_flags_help.py` ya esta rojo: 4 de sus 8
casos fallan por ~80 flags AJENAS sin entrada en `PLAIN_HELP` y por entradas
ajenas con jerga. Esos 4 rojos son de CONJUNTO: cada uno acumula violaciones de
TODAS las entradas en una lista y assertea `== []`. Cinco entradas nuevas con
jerga prohibida, o sin el `"Si "`, o pasadas de largo, NO suben el conteo de 4:
se suman a la lista del test que YA falla. Un criterio "delta cero en el conteo"
no discrimina. Este archivo si: filtra a lo propio.

Las 4 reglas se copian del test real (`tests/test_harness_flags_help.py`), no se
parafrasean, y se importan de ahi donde se puede para que un cambio de la
denylist ajena rompa aca tambien.

Cabecera obligatoria: DATABASE_URL en memoria ANTES de importar la app (R8).
"""
from __future__ import annotations

import os
import re

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

KEYS_283 = (
    "STACKY_MEETINGS_ENABLED",
    "STACKY_MEETINGS_GRAPH_ENABLED",
    "STACKY_MEETINGS_PUBLISH_ENABLED",
    "STACKY_MEETINGS_GRAPH_TENANT",
    "STACKY_MEETINGS_GRAPH_CLIENT_ID",
)


def _entradas():
    from services.harness_flags_help import PLAIN_HELP

    return {k: PLAIN_HELP[k] for k in KEYS_283 if k in PLAIN_HELP}


def _campos(entry) -> list[str]:
    return [entry.what, entry.on_effect, entry.off_effect, entry.example]


def test_regla_1_cobertura_de_las_5_keys():
    """Regla 1 (`:36-41`) - las 5 tienen entrada."""
    entradas = _entradas()
    faltantes = sorted(set(KEYS_283) - set(entradas))
    assert faltantes == [], f"keys de este plan sin ayuda llana: {faltantes}"
    assert len(entradas) == 5


def test_regla_2_campos_no_vacios_y_acotados():
    """Regla 2 (`:44-53`) - los 4 limites de longitud, y ningun campo vacio."""
    for key, entry in sorted(_entradas().items()):
        assert len(entry.what.strip()) >= 10, f"{key}: what demasiado corto"
        assert len(entry.what) <= 200, f"{key}: what > 200 ({len(entry.what)})"
        assert len(entry.on_effect) <= 240, f"{key}: on_effect > 240 ({len(entry.on_effect)})"
        assert len(entry.off_effect) <= 240, f"{key}: off_effect > 240 ({len(entry.off_effect)})"
        assert len(entry.example) <= 300, f"{key}: example > 300 ({len(entry.example)})"
        for campo in _campos(entry):
            assert campo.strip(), f"{key}: campo vacio"


def test_regla_3_on_off_empiezan_con_si_sin_tilde():
    """Regla 3 (`:56-60`) - literalmente `"Si "`: con espacio y SIN tilde."""
    for key, entry in sorted(_entradas().items()):
        assert entry.on_effect.startswith("Si "), f"{key}: on_effect no empieza con 'Si '"
        assert entry.off_effect.startswith("Si "), f"{key}: off_effect no empieza con 'Si '"
        # El error tipico es "Sí ": lo nombramos para que el mensaje sea util.
        assert not entry.on_effect.startswith("Sí "), f"{key}: on_effect usa 'Sí' con tilde"
        assert not entry.off_effect.startswith("Sí "), f"{key}: off_effect usa 'Sí' con tilde"


def test_regla_4_sin_jerga_ni_keys_ni_referencias_a_fases():
    """Regla 4 (`:63-76`) - denylist con PLURAL, keys SCREAMING_SNAKE y `F<n>`.

    La denylist y los dos regex se IMPORTAN del test ajeno: si alguien la
    endurece, este archivo se entera. Copiarlos a mano seria una foto que
    envejece.
    """
    from tests.test_harness_flags_help import JARGON_DENYLIST, _KEY_RE, _PHASE_RE

    # GUARD POSITIVO, PRIMERO: los detectores detectan de verdad. Sin esto, una
    # denylist vacia o un regex roto harian pasar el test entero por accidente.
    assert len(JARGON_DENYLIST) == 15, f"la denylist ajena cambio: {len(JARGON_DENYLIST)} terminos"
    assert re.search(rf"\b{re.escape('token')}s?\b", "guarda los tokens", re.IGNORECASE)
    assert _KEY_RE.search("mira STACKY_MEETINGS_ENABLED y listo")
    assert _PHASE_RE.search("como dice F4")

    violaciones: list[str] = []
    for key, entry in sorted(_entradas().items()):
        for campo in _campos(entry):
            for termino in JARGON_DENYLIST:
                if re.search(rf"\b{re.escape(termino)}s?\b", campo, re.IGNORECASE):
                    violaciones.append(f"{key}: jerga {termino!r}")
            if _KEY_RE.search(campo):
                violaciones.append(f"{key}: cita una key SCREAMING_SNAKE")
            if _PHASE_RE.search(campo):
                violaciones.append(f"{key}: referencia a fase de plan (F<n>)")
    assert violaciones == [], f"ayuda llana con jerga prohibida: {violaciones}"
