"""tests/test_mg_historial.py — parser del HISTORIAL de Mantis (fecha real de
cierre + resolución vigente).

## Por qué estos tests usan una FIXTURE REAL y no un fake

`tests/fixtures/mg/mantis_view_history_sample.html` es HTML **capturado de la
instancia real** (`view.php?id=20636`, 2026-07-29) y anonimizado: la estructura
es la verdadera, byte a byte. Eso es deliberado, por dos precedentes de este
mismo repo:

1. Los regex de `_parse_bugnotes_html` y `_parse_relationships_html` se
   escribieron **dos veces contra estructuras inventadas** y devolvían 0 filas
   contra el servidor real.
2. El bug de las fechas (`_build_authorship_block` leía claves que ningún adapter
   producía) estuvo oculto porque el fake del test **inventaba la clave**: el test
   pasaba en verde mientras la migración perdía el dato.

## Qué habilita este parser

- **`date_closed`**: la fecha REAL de cierre. Antes se aproximaba con
  `last_modified`, que cambia con cualquier edición posterior al cierre. Alimenta
  el bloque de metadata y el `UPDATE` de `closed_at` en base.
- **`resolution`**: el campo que distingue un ticket **corregido** de uno
  **rechazado** (duplicado / no se corregirá / no se requieren cambios). No se
  migraba en absoluto.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.migrar_mantis_gitlab.adapters.scraping_adapter import (
    _extraer_fecha_cierre,
    _extraer_resolucion,
    _parse_history_html,
    _parse_issue_detail_html,
    _parse_total_declarado,
)
from tools.migrar_mantis_gitlab.mapping.date_map import mantis_date_to_iso

_FIXTURES = Path(__file__).parent / "fixtures" / "mg"


def _fixture_historial() -> str:
    return (_FIXTURES / "mantis_view_history_sample.html").read_text(encoding="utf-8")


# ── Parseo contra el HTML REAL ─────────────────────────────────────────────


def test_parsea_las_11_filas_del_historial_real():
    filas = _parse_history_html(_fixture_historial())
    assert len(filas) == 11
    # La cabecera usa <th>, no <td class="small-caption">: no debe colarse.
    assert all(f["campo"] != "campo" for f in filas)


def test_las_filas_traen_fecha_usuario_campo_y_transicion():
    filas = _parse_history_html(_fixture_historial())
    estados = [f for f in filas if f["campo"] == "estado"]
    assert len(estados) == 5
    # Orden cronológico ascendente, tal como lo emite Mantis.
    assert (estados[0]["desde"], estados[0]["hasta"]) == ("nueva", "aceptada")
    assert (estados[-1]["desde"], estados[-1]["hasta"]) == ("resuelta", "cerrada")
    assert estados[-1]["fecha"] == "05/03/2025 11:38"


def test_la_flecha_de_mantis_se_parte_en_desde_y_hasta():
    """Mantis emite `&gt;` en `=&gt;`; `_strip_tags` lo desescapa a `=>`. Si el
    split falla, `desde` queda vacío y el estado destino contiene toda la cadena
    — y la detección de cierre deja de funcionar."""
    filas = _parse_history_html(_fixture_historial())
    resumen = [f for f in filas if f["campo"] == "resumen"][0]
    assert resumen["desde"].startswith("[DXXXX]")
    assert resumen["hasta"].startswith("[D20636]")
    assert "=>" not in resumen["hasta"]


def test_una_fila_sin_flecha_no_rompe():
    """"Nueva Incidencia" no tiene transición: `desde` vacío, sin excepción."""
    filas = _parse_history_html(_fixture_historial())
    nueva = [f for f in filas if f["campo"] == "nueva incidencia"][0]
    assert nueva["desde"] == ""


def test_el_campo_se_normaliza_sin_acentos():
    """"Resolución" tiene tilde; el código compara contra `resolucion`."""
    filas = _parse_history_html(_fixture_historial())
    assert any(f["campo"] == "resolucion" for f in filas)


def test_html_sin_historial_devuelve_lista_vacia():
    assert _parse_history_html("<html><body>sin historial</body></html>") == []
    assert _parse_history_html("") == []


# ── Fecha REAL de cierre ───────────────────────────────────────────────────


def test_fecha_de_cierre_real_del_ticket_20636():
    filas = _parse_history_html(_fixture_historial())
    assert _extraer_fecha_cierre(filas) == "05/03/2025 11:38"
    assert mantis_date_to_iso("05/03/2025 11:38", "-03:00") == "2025-03-05T11:38:00-03:00"


def test_toma_el_ULTIMO_cierre_no_el_primero():
    """Un ticket resuelto y después cerrado tiene dos transiciones de cierre. La
    vigente es la última — usar la primera daría la fecha de la resolución, no la
    del cierre."""
    filas = [
        {"campo": "estado", "fecha": "01/01/2025 10:00", "desde": "confirmada", "hasta": "resuelta"},
        {"campo": "estado", "fecha": "02/02/2025 11:00", "desde": "resuelta", "hasta": "cerrada"},
    ]
    assert _extraer_fecha_cierre(filas) == "02/02/2025 11:00"


def test_un_ticket_reabierto_no_tiene_fecha_de_cierre_vigente():
    """Si después del cierre hay una transición a un estado ABIERTO, el ticket
    está reabierto: devolver la vieja fecha de cierre sería mentir."""
    filas = [
        {"campo": "estado", "fecha": "01/01/2025 10:00", "desde": "confirmada", "hasta": "cerrada"},
        {"campo": "estado", "fecha": "05/01/2025 09:00", "desde": "cerrada", "hasta": "se necesitan mas datos"},
    ]
    assert _extraer_fecha_cierre(filas) is None


def test_reabierto_y_vuelto_a_cerrar_devuelve_el_segundo_cierre():
    filas = [
        {"campo": "estado", "fecha": "01/01/2025 10:00", "desde": "confirmada", "hasta": "cerrada"},
        {"campo": "estado", "fecha": "05/01/2025 09:00", "desde": "cerrada", "hasta": "asignada"},
        {"campo": "estado", "fecha": "09/03/2025 16:20", "desde": "asignada", "hasta": "cerrada"},
    ]
    assert _extraer_fecha_cierre(filas) == "09/03/2025 16:20"


def test_ticket_que_nunca_se_cerro_devuelve_none():
    filas = [
        {"campo": "estado", "fecha": "01/01/2025 10:00", "desde": "nueva", "hasta": "asignada"},
    ]
    assert _extraer_fecha_cierre(filas) is None


def test_estado_destino_desconocido_se_ignora_sin_romper():
    """Un estado personalizado de la instancia no está en la tabla de alias: se
    ignora esa fila en vez de adivinar si es un cierre."""
    filas = [
        {"campo": "estado", "fecha": "01/01/2025 10:00", "desde": "nueva", "hasta": "en revision interna"},
    ]
    assert _extraer_fecha_cierre(filas) is None


@pytest.mark.parametrize("visible,es_cierre", [
    ("resuelta", True), ("cerrada", True), ("resolved", True), ("closed", True),
    ("nueva", False), ("asignada", False), ("confirmada", False), ("aceptada", False),
])
def test_alias_de_estado_en_es_y_en(visible, es_cierre):
    filas = [{"campo": "estado", "fecha": "01/01/2025 10:00", "desde": "x", "hasta": visible}]
    assert (_extraer_fecha_cierre(filas) is not None) is es_cierre


# ── Resolución vigente ─────────────────────────────────────────────────────


def test_resolucion_del_ticket_real_es_fixed():
    filas = _parse_history_html(_fixture_historial())
    assert _extraer_resolucion(filas) == "fixed"


@pytest.mark.parametrize("visible,canonico", [
    ("corregida", "fixed"),
    ("duplicada", "duplicate"),
    ("no se corregira", "wont-fix"),
    ("no se requieren cambios", "no-change-required"),
    ("no se puede reproducir", "unable-to-duplicate"),
    ("suspendida", "suspended"),
    ("reabierta", "reopened"),
    ("abierta", "open"),
    ("won't fix", "wont-fix"),
    ("duplicate", "duplicate"),
])
def test_alias_de_resolucion(visible, canonico):
    filas = [{"campo": "resolucion", "fecha": "01/01/2025 10:00", "desde": "abierta", "hasta": visible}]
    assert _extraer_resolucion(filas) == canonico


def test_resolucion_toma_la_ultima_transicion():
    filas = [
        {"campo": "resolucion", "fecha": "01/01/2025 10:00", "desde": "abierta", "hasta": "corregida"},
        {"campo": "resolucion", "fecha": "02/01/2025 10:00", "desde": "corregida", "hasta": "reabierta"},
    ]
    assert _extraer_resolucion(filas) == "reopened"


def test_sin_filas_de_resolucion_devuelve_none():
    filas = [{"campo": "estado", "fecha": "01/01/2025 10:00", "desde": "nueva", "hasta": "cerrada"}]
    assert _extraer_resolucion(filas) is None


# ── Integración en el detalle del issue ────────────────────────────────────


def test_el_detalle_expone_date_closed_y_resolution():
    d = _parse_issue_detail_html(_fixture_historial(), 20636)
    assert d["date_closed"] == "05/03/2025 11:38"
    assert d["resolution"] == "fixed"
    assert len(d["history"]) == 11


def test_detalle_sin_historial_deja_los_campos_en_none():
    d = _parse_issue_detail_html("<html><body>vacio</body></html>", 1)
    assert d["date_closed"] is None
    assert d["resolution"] is None
    assert d["history"] == []


# ── El label de resolución llega al payload ────────────────────────────────


def _field_mapping_minimo() -> dict:
    return {
        "status": {
            "closed": {"gitlab_state": "closed", "label": "status::closed"},
            "_unmapped_fallback": {"gitlab_state": "opened", "label": "status::sin_mapear"},
        },
        "severity": {"label_prefix": "severity::"},
        "category": {"label_prefix": "category::"},
        "tags": {"label_prefix": "tag::"},
        "version": {},
        "custom_fields": {"mode": "metadata_block"},
    }


def test_el_payload_lleva_el_label_de_resolucion():
    from tools.migrar_mantis_gitlab.migrator_mg_core import _build_payload

    p = _build_payload(
        {"id": 20636, "summary": "t", "status": "closed", "resolution": "wont-fix"},
        _field_mapping_minimo(), {}, [],
    )
    assert "mantis-resolution::wont-fix" in p["labels"]


def test_resolucion_open_no_genera_label():
    """`open` es el default de Mantis para todo ticket sin resolver: etiquetarlo
    sería ruido en cada issue abierto."""
    from tools.migrar_mantis_gitlab.migrator_mg_core import _build_payload

    p = _build_payload(
        {"id": 1, "summary": "t", "status": "closed", "resolution": "open"},
        _field_mapping_minimo(), {}, [],
    )
    assert not any(l.startswith("mantis-resolution::") for l in p["labels"])


def test_la_metadata_cita_la_fecha_REAL_de_cierre_y_la_resolucion():
    from tools.migrar_mantis_gitlab.migrator_mg_core import _build_authorship_block

    bloque = _build_authorship_block({
        "reporter": "Alguien", "status": "closed",
        "date_submitted": "25/03/2024 15:59",
        "last_modified": "20/06/2025 08:00",
        "date_closed": "05/03/2025 11:38",
        "resolution": "fixed",
    })
    assert "05/03/2025 11:38" in bloque
    assert "fecha real, del historial de Mantis" in bloque
    assert "Resolución en Mantis:** fixed" in bloque
    # La aproximación NO debe aparecer cuando hay fecha real.
    assert "APROXIMACIÓN" not in bloque


def test_la_metadata_marca_la_aproximacion_cuando_no_hay_fecha_real():
    from tools.migrar_mantis_gitlab.migrator_mg_core import _build_authorship_block

    bloque = _build_authorship_block({
        "reporter": "Alguien", "status": "closed",
        "last_modified": "20/06/2025 08:00",
    })
    assert "APROXIMACIÓN" in bloque
    assert "20/06/2025 08:00" in bloque


# ── Total declarado: el número real de la instancia ────────────────────────


def test_total_declarado_con_el_texto_real_de_la_instancia():
    """Texto REAL: "Visualizando incidencias 1 - 500 / 1008". La primera versión
    del regex exigía que el número siguiera inmediatamente a la palabra clave y
    devolvía `None`, dejando el gate de conteo desactivado en silencio."""
    assert _parse_total_declarado("Visualizando incidencias 1 - 500 / 1008") == 1008
    assert _parse_total_declarado("Viewing issues 1 - 50 / 583") == 583
    assert _parse_total_declarado("Mostrando 1 - 50 / 52") == 52
