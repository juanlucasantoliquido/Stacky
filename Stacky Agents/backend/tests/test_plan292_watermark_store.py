"""tests/test_plan292_watermark_store.py — Plan 292 F2.

El store de la marca de agua y la barrera de admision del delta.

R8 — INNEGOCIABLE: `data_dir()` es `backend/data/`, la carpeta donde vive la base
del operador. Los DIECISEIS casos monkeypatchean la ruta a `tmp_path`, y el
primero asserta el aislamiento ANTES de escribir un solo byte.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """El modulo con `data_dir()` apuntando a un temporal, nunca a backend/data/."""
    import services.gitlab_sync_watermark as wm

    monkeypatch.setattr(wm, "data_dir", lambda: tmp_path)
    return wm


# ───────────────────────── lectura tolerante ─────────────────────────


def test_sin_archivo_devuelve_none_y_contador_cero(store, tmp_path):
    # El cinturon de R8: si esto no es cierto, el resto de los casos estarian
    # escribiendo en la instalacion real del operador.
    assert tmp_path.name in str(store._path()), f"el store NO esta aislado: {store._path()}"
    assert not store._path().exists()
    assert store.leer_marca("RIPLEY") == (None, 0)


def test_escribir_y_leer_ida_y_vuelta(store):
    store.escribir_marca("RIPLEY", "2026-08-01T10:00:00Z", 3)
    assert store.leer_marca("RIPLEY") == ("2026-08-01T10:00:00Z", 3)


def test_json_corrupto_degrada_a_none_sin_lanzar(store):
    store._path().write_text("{no es json", encoding="utf-8")
    assert store.leer_marca("RIPLEY") == (None, 0)


def test_marca_que_no_parsea_como_fecha_degrada_a_none(store):
    store._path().write_text(
        json.dumps({"RIPLEY": {"marca": "ayer", "contador": 1}}), encoding="utf-8"
    )
    assert store.leer_marca("RIPLEY") == (None, 0)


def test_contador_no_entero_degrada_a_none(store):
    store._path().write_text(
        json.dumps({"RIPLEY": {"marca": "2026-08-01T10:00:00Z", "contador": "tres"}}),
        encoding="utf-8",
    )
    assert store.leer_marca("RIPLEY") == (None, 0)
    # `isinstance(True, int)` es True en Python: un booleano NO es un contador.
    store._path().write_text(
        json.dumps({"RIPLEY": {"marca": "2026-08-01T10:00:00Z", "contador": True}}),
        encoding="utf-8",
    )
    assert store.leer_marca("RIPLEY") == (None, 0)


def test_json_que_no_es_objeto_degrada_a_none(store):
    store._path().write_text("[1,2,3]", encoding="utf-8")
    assert store.leer_marca("RIPLEY") == (None, 0)


def test_dos_proyectos_no_se_pisan(store):
    store.escribir_marca("RIPLEY", "2026-08-01T10:00:00Z", 1)
    store.escribir_marca("RSPACIFICO", "2026-07-15T08:30:00Z", 7)
    assert store.leer_marca("RIPLEY") == ("2026-08-01T10:00:00Z", 1)
    assert store.leer_marca("RSPACIFICO") == ("2026-07-15T08:30:00Z", 7)


def test_escribir_no_lanza_si_el_directorio_no_existe(tmp_path, monkeypatch):
    import services.gitlab_sync_watermark as wm

    hondo = tmp_path / "no" / "existe" / "todavia"
    monkeypatch.setattr(wm, "data_dir", lambda: hondo)
    assert not hondo.exists()
    wm.escribir_marca("RIPLEY", "2026-08-01T10:00:00Z", 2)   # no debe lanzar
    assert wm.leer_marca("RIPLEY") == ("2026-08-01T10:00:00Z", 2)


# ───────────────────────── marca_maxima ─────────────────────────


def test_marca_maxima_normaliza_z_y_milisegundos(store):
    # El maximo es el segundo; menos los 120 s de solapamiento.
    assert (
        store.marca_maxima(["2026-08-01T10:00:00.000Z", "2026-08-02T09:00:00.500Z"])
        == "2026-08-02T08:58:00Z"
    )


def test_marca_maxima_ignora_vacios_y_basura(store):
    assert store.marca_maxima(["", None, "ayer", "2026-08-01T10:00:00Z"]) == "2026-08-01T09:58:00Z"
    assert store.marca_maxima(["", None, "ayer"]) is None


def test_marca_maxima_de_lista_vacia_es_none(store):
    assert store.marca_maxima([]) is None


# ───────────────────────── R11 — la marca es MONOTONA ─────────────────────────


def test_la_marca_nunca_retrocede(store):
    """R11. En modo COMPLETO `items` son solo los ABIERTOS: si el cambio mas
    reciente del proyecto fue sobre un CERRADO, el max(updated_at) de esa tanda es
    mas viejo que la marca que dejo el ultimo incremental. Escribirlo haria que la
    corrida siguiente pidiera una ventana enorme.

    MITAD DE CONTRASTE: con `escribir_marca` guardando `marca` a secas en vez de
    max(previa, nueva), este caso DEBE fallar.
    """
    store.escribir_marca("RIPLEY", "2026-08-02T10:00:00Z", 1)
    store.escribir_marca("RIPLEY", "2026-08-01T10:00:00Z", 0)
    marca, contador = store.leer_marca("RIPLEY")
    assert marca == "2026-08-02T10:00:00Z", "la marca RETROCEDIO"
    # El contador si se actualiza: es el de la corrida que acaba de pasar.
    assert contador == 0


def test_la_marca_avanza_si_la_nueva_es_mas_nueva(store):
    """El complemento del anterior: sin este caso, el 12 se satisface con un
    `escribir_marca` que nunca escriba nada."""
    store.escribir_marca("RIPLEY", "2026-08-01T10:00:00Z", 1)
    store.escribir_marca("RIPLEY", "2026-08-02T10:00:00Z", 2)
    assert store.leer_marca("RIPLEY") == ("2026-08-02T10:00:00Z", 2)


# ───────────── §3.1-bis — la barrera de admision del delta ─────────────


def test_admitir_del_delta_solo_bloquea_al_cerrado_desconocido(store):
    """Los cuatro cuadrantes de la tabla de §3.1-bis, en modo incremental."""
    ad = store.admitir_del_delta
    abierto = {"state": "opened"}
    cerrado = {"state": "closed"}
    assert ad(abierto, fila_existe=True, modo="incremental") is True
    assert ad(abierto, fila_existe=False, modo="incremental") is True
    # Un cerrado CONOCIDO se admite: es la deteccion de cierre de §3.1.
    assert ad(cerrado, fila_existe=True, modo="incremental") is True
    # Un cerrado DESCONOCIDO se saltea: crear esa fila es inventar historial que
    # el operador nunca tuvo, y nadie la borraria nunca.
    assert ad(cerrado, fila_existe=False, modo="incremental") is False


def test_admitir_del_delta_no_bloquea_nada_en_modo_completo(store):
    """La garantia de que el modo de hoy queda byte-identico."""
    ad = store.admitir_del_delta
    for estado in ("opened", "closed"):
        for existe in (True, False):
            assert ad({"state": estado}, fila_existe=existe, modo="completo") is True


def test_admitir_del_delta_trata_el_estado_ausente_como_abierto(store):
    """`_upsert_ticket_gitlab` cae a "opened" cuando el campo falta
    (gitlab_sync.py:148): la barrera NO puede ser mas estricta que el upsert, o
    saltearia items validos."""
    ad = store.admitir_del_delta
    assert ad({}, fila_existe=False, modo="incremental") is True
    assert ad({"state": ""}, fila_existe=False, modo="incremental") is True
    assert ad({"state": None}, fila_existe=False, modo="incremental") is True
    assert ad({"state": "reopened"}, fila_existe=False, modo="incremental") is True
