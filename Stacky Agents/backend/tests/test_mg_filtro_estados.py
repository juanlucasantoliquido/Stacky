"""tests/test_mg_filtro_estados.py — gate anti-extracción-truncada (bug #2).

## Qué bug blindan estos tests

En la migración de Ripley (Mantis 310 → GitLab 127) el filtro de estados de
Mantis se creyó aplicado y no lo estaba: `view_all_set.php?type=1` es un "set"
PARCIAL — los campos que no se envían conservan el filtro GUARDADO de la cuenta,
y el default de Mantis oculta los cerrados. Resultado: de 52 issues migrados,
**1 en estado `resolved` y CERO en `closed`**, y 8 tickets que por evidencia
independiente se sabían resueltos quedaron afuera. La migración se dio por
completa.

Lo grave no fue el filtro: fue que **nada miró el resultado**. El síntoma era
trivialmente detectable. Estos tests aseguran que ese mismo fallo, si vuelve,
**aborte la corrida** en vez de producir una migración parcial silenciosa.

Los tests del PARSEO no requieren credenciales de Mantis; los del filtro end-to-end
sí, y quedan como validación manual documentada en
`30_HOMOLOGACION_MANTIS_GITLAB.md`.
"""
from __future__ import annotations

import pytest

from tools.migrar_mantis_gitlab.adapters.scraping_adapter import (
    MantisScrapingPaginationError,
    _parse_total_declarado,
    _verificar_cobertura_de_estados,
)


# ── Total declarado por Mantis ─────────────────────────────────────────────


@pytest.mark.parametrize("html,esperado", [
    ('<div class="links">Mostrando 1 - 50 / 583</div>', 583),
    ("Viewing 1 - 50 / 583", 583),
    ("Visualizando 51 - 100 / 583", 583),
    # Con tags de por medio (el parser normaliza antes de buscar).
    ("<span>Mostrando</span> <b>1 - 50</b> / <b>52</b>", 52),
    # Sin el texto: None, y el gate de conteo se saltea (no invento un total).
    ("<table id='buglist'></table>", None),
    ("", None),
])
def test_parse_total_declarado(html, esperado):
    assert _parse_total_declarado(html) == esperado


# ── Gate 1: conteo contra el total declarado ───────────────────────────────


def test_aborta_si_se_extrajo_menos_de_lo_que_mantis_declara():
    """Éste es el requisito del operador —validar contra un conteo real de
    Mantis— hecho automático: no depende de que alguien se acuerde de mirarlo."""
    issues = [{"id": i, "status": "new"} for i in range(52)]
    with pytest.raises(MantisScrapingPaginationError) as exc:
        _verificar_cobertura_de_estados(
            issues, project_id=310, include_resolved_closed=True, total_declarado=583
        )
    assert "583" in str(exc.value) and "52" in str(exc.value)


def test_no_aborta_si_el_conteo_coincide():
    issues = [{"id": i, "status": "closed"} for i in range(52)]
    _verificar_cobertura_de_estados(
        issues, project_id=310, include_resolved_closed=True, total_declarado=52
    )


def test_sin_total_declarado_el_gate_de_conteo_se_saltea():
    """Si Mantis no imprimió el total, no se inventa uno: sólo queda el gate de
    cobertura de estados."""
    issues = [{"id": 1, "status": "resolved"}]
    _verificar_cobertura_de_estados(
        issues, project_id=310, include_resolved_closed=True, total_declarado=None
    )


# ── Gate 2: cobertura de estados (el que atrapa el bug #2) ─────────────────


def test_aborta_si_no_vino_ningun_resuelto_ni_cerrado():
    """La firma EXACTA del bug de Ripley: 52 issues, ninguno cerrado."""
    issues = (
        [{"id": i, "status": "confirmed"} for i in range(17)]
        + [{"id": 100 + i, "status": "feedback"} for i in range(16)]
        + [{"id": 200 + i, "status": "new"} for i in range(12)]
        + [{"id": 300 + i, "status": "assigned"} for i in range(5)]
        + [{"id": 400, "status": "acknowledged"}]
    )
    with pytest.raises(MantisScrapingPaginationError) as exc:
        _verificar_cobertura_de_estados(
            issues, project_id=310, include_resolved_closed=True, total_declarado=None
        )
    mensaje = str(exc.value)
    assert "include_resolved_closed=True" in mensaje
    # El error tiene que ser accionable: decir qué encontró y cómo salir.
    assert "resolved" in mensaje and "closed" in mensaje
    assert "include_resolved_closed=False" in mensaje


def test_un_solo_resuelto_ya_satisface_la_cobertura():
    """Con `resolved` presente el filtro claramente no los oculta. Que haya UNO
    solo es sospechoso pero no es prueba de fallo: para eso está el gate de
    conteo."""
    issues = [{"id": 1, "status": "confirmed"}, {"id": 2, "status": "resolved"}]
    _verificar_cobertura_de_estados(
        issues, project_id=310, include_resolved_closed=True, total_declarado=None
    )


def test_solo_cerrados_tambien_satisface():
    issues = [{"id": 1, "status": "closed"}]
    _verificar_cobertura_de_estados(
        issues, project_id=310, include_resolved_closed=True, total_declarado=None
    )


def test_con_include_resolved_closed_false_no_se_exige_cobertura():
    """Decisión explícita del operador de migrar sólo lo abierto: se respeta."""
    issues = [{"id": 1, "status": "new"}]
    _verificar_cobertura_de_estados(
        issues, project_id=310, include_resolved_closed=False, total_declarado=None
    )


def test_proyecto_vacio_no_aborta():
    """Cero issues no es evidencia de filtro roto — puede ser un proyecto vacío."""
    _verificar_cobertura_de_estados(
        [], project_id=999, include_resolved_closed=True, total_declarado=None
    )


def test_estado_en_mayusculas_o_con_espacios_cuenta_igual():
    """El estado viene del ID de la clase CSS y debería llegar normalizado, pero
    el gate no se puede caer por un espacio: un falso positivo acá ABORTA una
    migración legítima."""
    issues = [{"id": 1, "status": " Resolved "}]
    _verificar_cobertura_de_estados(
        issues, project_id=310, include_resolved_closed=True, total_declarado=None
    )
