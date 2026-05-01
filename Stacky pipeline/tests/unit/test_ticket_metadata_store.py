"""Tests unitarios de ticket_metadata_store."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Aisla el store en un tmp_path por test y resetea el singleton."""
    import ticket_metadata_store as tms

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tms, "_DATA_DIR", data_dir)
    monkeypatch.setattr(tms, "_STORE_PATH", data_dir / "ticket_metadata.json")
    monkeypatch.setattr(tms, "_LOCK_PATH", data_dir / "ticket_metadata.json.lock")
    tms.reset_singleton_for_tests()
    yield
    tms.reset_singleton_for_tests()


class TestBasicCrud:
    def test_get_retorna_none_cuando_no_existe(self):
        from ticket_metadata_store import get_store
        assert get_store().get("nope") is None

    def test_set_color_persiste_y_se_lee(self):
        from ticket_metadata_store import get_store
        store = get_store()
        store.set_color("27698", "#ABcdef")   # se normaliza a lowercase
        meta = store.get("27698")
        assert meta is not None
        assert meta.color is not None
        assert meta.color.hex == "#abcdef"

    def test_clear_color_deja_color_none(self):
        from ticket_metadata_store import get_store
        store = get_store()
        store.set_color("t1", "#112233")
        store.clear_color("t1")
        assert store.get("t1").color is None

    def test_get_all_devuelve_todos(self):
        from ticket_metadata_store import get_store
        store = get_store()
        store.set_color("a", "#000000")
        store.set_color("b", "#ffffff")
        all_ = store.get_all()
        assert set(all_.keys()) == {"a", "b"}


class TestAtomicWrites:
    def test_archivo_escrito_es_json_valido(self, tmp_path):
        import ticket_metadata_store as tms
        from ticket_metadata_store import get_store
        get_store().set_color("27698", "#aabbcc")
        raw = json.loads(tms._STORE_PATH.read_text(encoding="utf-8"))
        assert raw["version"] == 1
        assert raw["tickets"]["27698"]["color"]["hex"] == "#aabbcc"

    def test_no_deja_archivo_tmp_residual(self, tmp_path):
        import ticket_metadata_store as tms
        from ticket_metadata_store import get_store
        get_store().set_color("x", "#abcdef")
        tmp_files = list(tms._DATA_DIR.glob("*.tmp"))
        assert tmp_files == []


class TestUserTags:
    def test_tags_se_normalizan_lowercase_y_dedup(self):
        from ticket_metadata_store import get_store
        store = get_store()
        store.set_user_tags("t1", ["BUG", "bug", "  Frontend ", "frontend"])
        tags = store.get("t1").user_tags.tags
        assert tags == ["bug", "frontend"]

    def test_tag_invalido_lanza_error(self):
        from ticket_metadata_store import get_store
        from ticket_metadata_store import TicketMetadataError
        with pytest.raises(TicketMetadataError):
            get_store().set_user_tags("t1", ["tag con espacio"])

    def test_tag_con_tildes_y_ñ_valido(self):
        from ticket_metadata_store import get_store
        store = get_store()
        store.set_user_tags("t1", ["año-crítico", "niño"])
        assert set(store.get("t1").user_tags.tags) == {"año-crítico", "niño"}

    def test_add_user_tag_respeta_limite(self):
        from ticket_metadata_store import get_store, TicketMetadataError
        store = get_store()
        store.set_user_tags("t1", [f"tag{i}" for i in range(20)])
        with pytest.raises(TicketMetadataError):
            store.add_user_tag("t1", "overflow")

    def test_remove_user_tag_elimina_y_persiste(self):
        from ticket_metadata_store import get_store
        store = get_store()
        store.set_user_tags("t1", ["alpha", "beta", "gamma"])
        store.remove_user_tag("t1", "BETA")    # case-insensitive
        assert store.get("t1").user_tags.tags == ["alpha", "gamma"]


class TestInvalidColor:
    @pytest.mark.parametrize("bad", ["red", "#abc", "#12345", "rgb(1,2,3)", "#gggggg", ""])
    def test_color_invalido_rechazado(self, bad):
        from ticket_metadata_store import get_store, TicketMetadataError
        with pytest.raises(TicketMetadataError):
            get_store().set_color("t1", bad)


class TestCorruption:
    def test_json_corrupto_se_mueve_a_bak_y_arranca_vacio(self, tmp_path):
        import ticket_metadata_store as tms
        tms._STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tms._STORE_PATH.write_text("{ esto no es json", encoding="utf-8")
        store = tms.get_store()
        assert store.get_all() == {}
        baks = list(tms._DATA_DIR.glob("*.bak.*"))
        assert len(baks) == 1

    def test_schema_invalido_se_mueve_a_bak(self, tmp_path):
        import ticket_metadata_store as tms
        tms._STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tms._STORE_PATH.write_text(
            json.dumps({"version": 1, "tickets": {"t1": {"color": {"hex": "nope"}}}}),
            encoding="utf-8",
        )
        store = tms.get_store()
        assert store.get_all() == {}
        assert len(list(tms._DATA_DIR.glob("*.bak.*"))) == 1


class TestMigrationV0:
    def test_dict_plano_se_migra(self, tmp_path):
        import ticket_metadata_store as tms
        tms._STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # formato v0 defensivo: dict plano ticket → metadata, sin clave "version"
        tms._STORE_PATH.write_text(
            json.dumps({"27698": {"ticket_id": "27698",
                                  "color": {"hex": "#aabbcc"},
                                  "user_tags": {"tags": ["bug"]}}}),
            encoding="utf-8",
        )
        meta = tms.get_store().get("27698")
        assert meta is not None and meta.color.hex == "#aabbcc"


class TestBulkUpdate:
    def test_bulk_update_atomico_multiples_tickets(self):
        from ticket_metadata_store import get_store
        store = get_store()
        store.bulk_update({
            "a": {"color": "#111111", "user_tags": ["bug"]},
            "b": {"color": "#222222"},
            "c": {"user_tags": ["frontend", "urgente"]},
        })
        assert store.get("a").color.hex == "#111111"
        assert store.get("a").user_tags.tags == ["bug"]
        assert store.get("b").color.hex == "#222222"
        assert store.get("c").color is None
        assert set(store.get("c").user_tags.tags) == {"frontend", "urgente"}

    def test_bulk_update_error_es_all_or_nothing(self):
        from ticket_metadata_store import get_store, TicketMetadataError
        store = get_store()
        store.set_color("a", "#111111")
        with pytest.raises(TicketMetadataError):
            store.bulk_update({
                "a": {"color": "#222222"},
                "b": {"color": "not-hex"},
            })
        # "a" debe conservar su color original (rollback)
        assert store.get("a").color.hex == "#111111"
        assert store.get("b") is None

    def test_bulk_update_color_none_borra(self):
        from ticket_metadata_store import get_store
        store = get_store()
        store.set_color("a", "#112233")
        store.bulk_update({"a": {"color": None}})
        assert store.get("a").color is None


class TestMtimeCache:
    def test_segunda_lectura_sin_cambios_usa_cache(self, monkeypatch):
        import ticket_metadata_store as tms
        store = tms.get_store()
        store.set_color("t1", "#aabbcc")

        calls = {"n": 0}
        original_read = Path.read_text
        def spy_read(self, *a, **kw):
            if self == tms._STORE_PATH:
                calls["n"] += 1
            return original_read(self, *a, **kw)
        monkeypatch.setattr(Path, "read_text", spy_read)

        for _ in range(5):
            store.get("t1")
        assert calls["n"] == 0   # 0 re-lecturas del disco: todo desde cache

    def test_cambio_en_disco_invalida_cache(self):
        import ticket_metadata_store as tms
        store = tms.get_store()
        store.set_color("t1", "#aabbcc")
        # escritura externa simulada
        raw = json.loads(tms._STORE_PATH.read_text(encoding="utf-8"))
        raw["tickets"]["t1"]["color"]["hex"] = "#ddeeff"
        tms._STORE_PATH.write_text(json.dumps(raw), encoding="utf-8")
        # forzar mtime distinto
        st = tms._STORE_PATH.stat()
        os.utime(tms._STORE_PATH, (st.st_atime, st.st_mtime + 2))
        assert store.get("t1").color.hex == "#ddeeff"


class TestConcurrency:
    def test_lecturas_concurrentes_no_rompen(self):
        from ticket_metadata_store import get_store
        store = get_store()
        store.set_color("t1", "#abcdef")
        errors: list = []

        def reader():
            try:
                for _ in range(50):
                    m = store.get("t1")
                    assert m.color.hex == "#abcdef"
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []

    def test_escrituras_concurrentes_serializan(self):
        from ticket_metadata_store import get_store
        store = get_store()
        errors: list = []

        def writer(i: int):
            try:
                store.set_color(f"t{i}", "#112233")
                store.add_user_tag(f"t{i}", f"tag{i}")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert len(store.get_all()) == 10
