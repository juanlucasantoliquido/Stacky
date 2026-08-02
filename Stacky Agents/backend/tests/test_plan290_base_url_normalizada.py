"""Plan 290 F6 — `base_url` de GitLab se normaliza tambien del lado del servidor.

Hasta este plan la normalizacion vivia SOLO en el cliente
(frontend/src/projects/newProjectGitlabModel.ts:37) y el servidor hacia
`url.rstrip("/")`. Cualquier alta que no pasara por ese formulario dejaba
`https://host/grupo/proyecto` como base y todas las llamadas salian a
`.../grupo/proyecto/api/v4/...` -> 404.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: Tabla de equivalencia CLIENTE <-> SERVIDOR. Mismo input, mismo output.
PARES: list[tuple[str, str]] = [
    ("https://gitlab.com", "https://gitlab.com"),
    ("https://gitlab.com/", "https://gitlab.com"),
    ("https://gitlab.com///", "https://gitlab.com"),
    ("https://gitlab.com/api/v4", "https://gitlab.com"),
    ("https://gitlab.com/api/v4/", "https://gitlab.com"),
    ("https://git.interno/grupo/proyecto", "https://git.interno"),
    ("https://git.interno:8443/grupo/proyecto", "https://git.interno:8443"),
    ("HTTP://GitLab.com/API/V4", "HTTP://GitLab.com"),
    ("", ""),
    # Sin esquema NO se inventa un origen: validateGitlabFields ya lo rechaza.
    ("gitlab.com/grupo", "gitlab.com/grupo"),
]


@pytest.mark.parametrize("entrada,salida", PARES)
def test_normaliza_igual_que_el_cliente(entrada, salida):
    from project_manager import _normalizar_base_url_gitlab

    assert _normalizar_base_url_gitlab(entrada) == salida


def test_la_tabla_del_test_coincide_con_la_del_docstring():
    """Paridad DECLARADA.

    El docstring de `_normalizar_base_url_gitlab` lleva la misma tabla, porque es
    lo que un implementador futuro lee antes de tocar la funcion. Si alguien
    cambia una y no la otra, esto se pone rojo — que es mucho mejor que
    descubrirlo con un 404 en produccion.
    """
    from project_manager import _normalizar_base_url_gitlab

    doc = _normalizar_base_url_gitlab.__doc__ or ""
    del_doc: list[tuple[str, str]] = []
    for linea in doc.splitlines():
        m = re.match(r"\s{4,}(\S*)\s+->\s*(\S*)\s*$", linea)
        if m:
            del_doc.append((m.group(1), m.group(2)))

    assert len(del_doc) == len(PARES), (
        f"el docstring declara {len(del_doc)} pares y el test {len(PARES)}: "
        f"alguien cambio uno y no el otro. Docstring: {del_doc}"
    )
    # El par de git.interno:8443 va abreviado en el docstring para que la tabla
    # entre en el ancho: se compara solo el ORIGEN, que es lo que la funcion
    # devuelve.
    assert [s for _e, s in del_doc] == [s for _e, s in PARES], (
        f"las salidas divergen.\n  docstring: {[s for _e, s in del_doc]}\n"
        f"  test:      {[s for _e, s in PARES]}"
    )
