"""tests/test_mg_dates.py — fidelidad de fechas Mantis → GitLab.

Blinda `tools/migrar_mantis_gitlab/mapping/date_map.py` y el cableado de fechas
en el payload/notas/estado.

Contexto del bug que estos tests previenen (medido en Ripley, proyecto GitLab
127): las 52 issues migradas quedaron con `created_at` = fecha de la migración y
**sin ninguna fecha de Mantis ni en el bloque de metadata**, porque
`_build_authorship_block` leía `date_submitted`/`last_modified` y NINGÚN adapter
producía esas claves.

El riesgo más caro que se cubre acá es el de día/mes invertido: `10/01/2026` es
10 de enero (formato es_ES de MantisBT). Interpretarlo como 1 de octubre desplaza
la fecha casi 9 meses **sin que nada falle**.
"""
from __future__ import annotations

import pytest

from tools.migrar_mantis_gitlab.mapping.date_map import (
    extraer_fecha_nota,
    extraer_fechas_issue,
    mantis_date_to_iso,
)


# ── Formatos reales observados en soporte.ais-int.net ───────────────────────


@pytest.mark.parametrize("crudo,esperado", [
    # detalle de ticket: dd/mm/yyyy HH:MM
    ("10/01/2026 09:15", "2026-01-10T09:15:00"),
    # listado: dd/mm/yy (año de 2 dígitos, sin hora)
    ("10/01/26", "2026-01-10T00:00:00"),
    # bugnote
    ("13/01/2026 10:00", "2026-01-13T10:00:00"),
    # con segundos
    ("13/01/2026 10:00:45", "2026-01-13T10:00:45"),
    # separador con guion
    ("13-01-2026 10:00", "2026-01-13T10:00:00"),
    # ISO del adapter de API REST: pasa derecho
    ("2026-01-13T10:00:00Z", "2026-01-13T10:00:00Z"),
    ("2026-01-13 10:00", "2026-01-13T10:00:00"),
])
def test_formatos_reales_de_mantis(crudo, esperado):
    assert mantis_date_to_iso(crudo) == esperado


def test_dia_primero_no_mes_primero():
    """El test más importante del archivo: 10/01 es 10 de ENERO, no 1 de octubre.
    Si esto se rompe, las fechas se desplazan meses sin que nada falle."""
    assert mantis_date_to_iso("10/01/2026 09:15").startswith("2026-01-10")
    # Un valor que sólo es válido con día primero: no existe el mes 25.
    assert mantis_date_to_iso("25/12/2025 18:30") == "2025-12-25T18:30:00"


def test_ano_de_dos_digitos_no_cae_en_1900_para_fechas_actuales():
    assert mantis_date_to_iso("05/03/26") == "2026-03-05T00:00:00"
    assert mantis_date_to_iso("05/03/99") == "1999-03-05T00:00:00"


# ── Nunca inventar ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("basura", [
    None, "", "   ", "sin fecha", "hace 3 días", "0000-00-00",
    "32/01/2026", "10/13/2026 09:15", "2026-02-30",
])
def test_valores_no_interpretables_devuelven_none(basura):
    """`None` es la respuesta correcta: el caller omite el campo y la fecha real
    igual sobrevive en el bloque de metadata. Sustituirla por `now()` sería
    inventar un dato."""
    assert mantis_date_to_iso(basura) is None


# ── Zona horaria ───────────────────────────────────────────────────────────


def test_tz_offset_se_agrega_cuando_se_declara():
    assert mantis_date_to_iso("10/01/2026 09:15", "-04:00") == "2026-01-10T09:15:00-04:00"
    # Formato compacto también válido, se normaliza.
    assert mantis_date_to_iso("10/01/2026 09:15", "-0400") == "2026-01-10T09:15:00-04:00"
    assert mantis_date_to_iso("10/01/2026 09:15", "Z") == "2026-01-10T09:15:00Z"


def test_sin_tz_offset_no_se_inventa_ninguno():
    """Sin offset declarado NO se agrega uno: GitLab lo tomará como UTC y eso
    queda declarado en el reporte, en vez de fingir un TZ que no conocemos."""
    assert mantis_date_to_iso("10/01/2026 09:15") == "2026-01-10T09:15:00"


def test_offset_propio_del_valor_gana_sobre_el_declarado():
    """Si el origen YA declaró su offset (adapter de API REST), ése es más fiel
    que el del config."""
    assert mantis_date_to_iso("2026-01-13T10:00:00+02:00", "-04:00") == "2026-01-13T10:00:00+02:00"


def test_tz_offset_invalido_falla_ruidoso():
    with pytest.raises(ValueError):
        mantis_date_to_iso("10/01/2026 09:15", "America/Santiago")


# ── Extractores tolerantes a las claves de AMBOS adapters ──────────────────


def test_extraer_fechas_issue_con_claves_del_scraping():
    r = extraer_fechas_issue({
        "date_submitted": "10/01/2026 09:15",
        "last_modified": "15/02/2026 17:40",
    })
    assert r["created_at_iso"] == "2026-01-10T09:15:00"
    assert r["updated_at_iso"] == "2026-02-15T17:40:00"
    # El texto crudo se preserva para el bloque de metadata.
    assert r["created_at_raw"] == "10/01/2026 09:15"


def test_extraer_fechas_issue_con_claves_de_la_api_rest():
    r = extraer_fechas_issue({
        "created_at": "2026-01-10T09:15:00Z",
        "updated_at": "2026-02-15T17:40:00Z",
    })
    assert r["created_at_iso"] == "2026-01-10T09:15:00Z"
    assert r["updated_at_iso"] == "2026-02-15T17:40:00Z"


def test_extraer_fechas_issue_sin_fechas_no_explota():
    r = extraer_fechas_issue({"id": 1, "status": "new"})
    assert r["created_at_iso"] is None and r["updated_at_iso"] is None
    assert r["created_at_raw"] == "" and r["updated_at_raw"] == ""


def test_extraer_fecha_nota_acepta_date_y_created_at():
    """`date` es la clave del scraping y `created_at` la de la API REST. Antes
    sólo se leía `date`, así que por la vía API las notas perdían la fecha."""
    assert extraer_fecha_nota({"date": "13/01/2026 10:00"}) == "2026-01-13T10:00:00"
    assert extraer_fecha_nota({"created_at": "2026-01-13T10:00:00Z"}) == "2026-01-13T10:00:00Z"
    assert extraer_fecha_nota({"date": ""}) is None


# ── Cableado en el core: payload y metadata ────────────────────────────────


def _field_mapping_minimo() -> dict:
    return {
        "status": {
            "new": {"gitlab_state": "opened", "label": "status::new"},
            "resolved": {"gitlab_state": "closed", "label": "status::resolved"},
            "_unmapped_fallback": {"gitlab_state": "opened", "label": "status::sin_mapear"},
        },
        "severity": {"label_prefix": "severity::"},
        "category": {"label_prefix": "category::"},
        "tags": {"label_prefix": "tag::"},
        "version": {},
        "custom_fields": {"mode": "metadata_block"},
    }


def test_payload_lleva_created_at_iso_cuando_mantis_dio_la_fecha():
    from tools.migrar_mantis_gitlab.migrator_mg_core import _build_payload

    warnings: list[str] = []
    p = _build_payload(
        {"id": 42, "summary": "t", "status": "new", "date_submitted": "10/01/2026 09:15"},
        _field_mapping_minimo(), {}, warnings,
    )
    assert p["created_at"] == "2026-01-10T09:15:00"
    assert warnings == []


def test_payload_sin_created_at_y_con_advertencia_si_la_fecha_es_ilegible():
    from tools.migrar_mantis_gitlab.migrator_mg_core import _build_payload

    warnings: list[str] = []
    p = _build_payload(
        {"id": 42, "summary": "t", "status": "new", "date_submitted": "el martes pasado"},
        _field_mapping_minimo(), {}, warnings,
    )
    assert "created_at" not in p
    assert any("fecha de creación" in w for w in warnings)


def test_payload_sin_fecha_no_genera_advertencia_ni_campo():
    from tools.migrar_mantis_gitlab.migrator_mg_core import _build_payload

    warnings: list[str] = []
    p = _build_payload(
        {"id": 42, "summary": "t", "status": "new"}, _field_mapping_minimo(), {}, warnings
    )
    assert "created_at" not in p
    assert warnings == []


def test_metadata_declara_la_fecha_de_cierre_para_tickets_cerrados():
    """`closed_at` NO es seteable por la API v4, así que el issue va a mostrar la
    fecha de la migración. La metadata tiene que decirlo explícitamente para que
    nadie lea esa fecha como un dato real."""
    from tools.migrar_mantis_gitlab.migrator_mg_core import _build_authorship_block

    bloque = _build_authorship_block({
        "reporter": "Alguien",
        "status": "resolved",
        "date_submitted": "10/01/2026 09:15",
        "last_modified": "15/02/2026 17:40",
    })
    assert "Cerrado en Mantis" in bloque
    assert "15/02/2026 17:40" in bloque
    assert "closed_at" in bloque
    # El texto CRUDO de Mantis, no el ISO: es el dato humano del origen.
    assert "Fecha de creación (Mantis):** 10/01/2026 09:15" in bloque


def test_metadata_no_habla_de_cierre_en_un_ticket_abierto():
    from tools.migrar_mantis_gitlab.migrator_mg_core import _build_authorship_block

    bloque = _build_authorship_block({"reporter": "Alguien", "status": "confirmed"})
    assert "Cerrado en Mantis" not in bloque


# ── Cableado en la pasada de estados ───────────────────────────────────────


def test_state_change_lleva_updated_at_iso_y_la_fecha_cruda():
    from tools.migrar_mantis_gitlab.migrator_mg_states import plan_state_changes

    r = plan_state_changes(
        [{"id": 101, "status": "resolved", "last_modified": "15/02/2026 17:40"}],
        _field_mapping_minimo()["status"],
        {"101": "1"},
        {"1": "opened"},
        tz_offset="-04:00",
    )
    assert len(r.changes) == 1
    assert r.changes[0].updated_at_iso == "2026-02-15T17:40:00-04:00"
    assert r.changes[0].mantis_date_raw == "15/02/2026 17:40"


def test_apply_state_manda_updated_at_al_writer_y_lo_cita_en_la_nota():
    from tools.migrar_mantis_gitlab.migrator_mg_states import (
        apply_state_changes,
        plan_state_changes,
    )
    from tests.test_mg_states import _StateWriter

    r = plan_state_changes(
        [{"id": 101, "status": "resolved", "last_modified": "15/02/2026 17:40"}],
        _field_mapping_minimo()["status"], {"101": "1"}, {"1": "opened"},
    )
    writer = _StateWriter()
    apply_state_changes(r, writer, mantis_project_id="310")

    assert writer.state_calls == [("1", "closed")]
    assert writer.updated_at_calls == ["2026-02-15T17:40:00"]
    cuerpo = writer.comments[0][1]
    assert "15/02/2026 17:40" in cuerpo
    # Sin `date_closed` del historial, la nota TIENE que declarar que es una
    # aproximación: presentar `last_modified` como fecha de cierre sería mentir.
    assert "APROXIMACIÓN" in cuerpo


def test_con_date_closed_del_historial_la_nota_dice_que_es_la_fecha_REAL():
    from tools.migrar_mantis_gitlab.migrator_mg_states import (
        apply_state_changes,
        plan_state_changes,
    )
    from tests.test_mg_states import _StateWriter

    r = plan_state_changes(
        [{
            # `resolved` y no `closed` porque el `_field_mapping_minimo` de este
            # archivo sólo mapea `new`/`resolved`; con `closed` caería al
            # `_unmapped_fallback` (opened) y no habría cambio de estado.
            "id": 101, "status": "resolved",
            "last_modified": "20/06/2026 08:00",   # posterior al cierre: NO es la fecha de cierre
            "date_closed": "15/02/2026 17:40",     # la real, del historial
        }],
        _field_mapping_minimo()["status"], {"101": "1"}, {"1": "opened"},
    )
    assert r.changes[0].fecha_cierre_es_real is True
    assert r.changes[0].mantis_date_raw == "15/02/2026 17:40"

    writer = _StateWriter()
    apply_state_changes(r, writer, mantis_project_id="310")
    cuerpo = writer.comments[0][1]
    assert "15/02/2026 17:40" in cuerpo
    assert "fecha real, tomada del historial" in cuerpo
    assert "APROXIMACIÓN" not in cuerpo
    # `updated_at` sigue siendo `last_modified` (es el campo de GitLab que
    # corresponde), no la fecha de cierre.
    assert writer.updated_at_calls == ["2026-06-20T08:00:00"]


# ── El adapter ya no descarta las fechas ───────────────────────────────────


def test_el_parser_del_detalle_conserva_date_submitted():
    """Antes el dato estaba en memoria (`by_class["date-submitted"]`) y el bucle
    que armaba el dict lo descartaba porque no estaba en `_LABEL_ALIASES`."""
    from tools.migrar_mantis_gitlab.adapters.scraping_adapter import (
        _parse_issue_detail_html,
    )

    html = """
    <table class="bug-description-table">
      <tr><th class="bug-date-submitted category">Enviado</th>
          <td class="bug-date-submitted">10/01/2026 09:15</td></tr>
      <tr><th class="bug-last-modified category">Actualizado</th>
          <td class="bug-last-modified">15/02/2026 17:40</td></tr>
      <tr><td class="bug-summary">0000042: Un titulo</td></tr>
      <tr><td class="bug-status"><i class="status-80-fg"></i><span>resuelta</span></td></tr>
    </table>
    """
    d = _parse_issue_detail_html(html, 42)
    assert d["date_submitted"] == "10/01/2026 09:15"
    assert d["last_modified"] == "15/02/2026 17:40"
    # No se rompió lo que ya funcionaba.
    assert d["summary"] == "Un titulo"
    assert d["status"] == "resolved"


def test_el_parser_del_listado_conserva_last_modified():
    from tools.migrar_mantis_gitlab.adapters.scraping_adapter import (
        _parse_issue_list_html,
    )

    html = """
    <table id="buglist"><tbody>
      <tr>
        <td class="column-id"><a href="view.php?id=42">0000042</a></td>
        <td class="column-summary"><a href="view.php?id=42">Un titulo</a></td>
        <td class="column-status"><i class="status-80-fg"></i><span>resuelta</span></td>
        <td class="column-last-modified">10/01/26</td>
      </tr>
    </tbody></table>
    """
    filas = _parse_issue_list_html(html, 310)
    assert len(filas) == 1
    assert filas[0]["last_modified"] == "10/01/26"
    assert filas[0]["status"] == "resolved"


def test_el_parser_no_confunde_el_th_con_el_td():
    """El `<th>` de la etiqueta comparte la clase CSS con el `<td>` del valor.
    Si el parser tomara el `<th>`, la fecha sería la palabra "Enviado"."""
    from tools.migrar_mantis_gitlab.adapters.scraping_adapter import (
        _parse_issue_detail_html,
    )

    html = (
        '<tr><th class="bug-date-submitted category">Enviado</th>'
        '<td class="bug-date-submitted">10/01/2026 09:15</td></tr>'
    )
    d = _parse_issue_detail_html(html, 42)
    assert d["date_submitted"] == "10/01/2026 09:15"
    assert mantis_date_to_iso(d["date_submitted"]) == "2026-01-10T09:15:00"
