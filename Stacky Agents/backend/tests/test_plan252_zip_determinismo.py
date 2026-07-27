"""Plan 252 F3 — zip determinista + gate anti-secreto que FALLA CERRADO. 11 tests.

El bug central del v1: corria `scrub_files` ANTES del gate. `mask_token_values` conoce
7 prefijos; si corre primero BORRA el secreto y el gate no encuentra nada, asi que el
paquete SALE. O sea: fallaba ABIERTO justo para los formatos que sabe reconocer, y
cerrado solo para los que no conoce. Estos tests congelan el orden correcto.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from services import pipeline_capability_frontier as fr
from services import pipeline_handoff_bundle as hb

# literales PARTIDOS a proposito: un token entero en el fuente dispara la
# push-protection de GitHub y bloquea el push del repo.
_GLPAT = "glpat-" + "x" * 20          # lo reconocen egress_policies Y secret_masking
_GHP_CORTO = "ghp_" + "a" * 20        # lo reconoce SOLO secret_masking (egress pide 36)


def _frontera(deploys=True):
    return fr.resolve_frontier({}, pipeline_deploys=deploys)


def _inputs(**kw):
    base = dict(
        pipeline_name="AgendaWeb CI",
        provider="ado",
        yaml_files={"pipelines/ci.yml": "stages: []\n"},
        script_files={"scripts/Deploy-Local.ps1": "Write-Host hola\n"},
        variables=(),
        pipeline_deploys=True,
    )
    base.update(kw)
    return hb.BundleInputs(**base)


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    import runtime_paths

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    yield tmp_path


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_zip_es_byte_identico_en_dos_corridas():
    """KPI-1. Sin teatro: `zip_bytes` no toca el disco, asi que tocarle el mtime a un
    archivo homonimo no probaria nada. Se asserta sobre los 4 campos que un refactor
    puede volver dependientes del entorno."""
    files = hb.build_files(_inputs(), _frontera())
    a, b = hb.zip_bytes(files), hb.zip_bytes(files)
    assert a == b
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()
    for info in zipfile.ZipFile(io.BytesIO(a)).infolist():
        assert info.date_time == (1980, 1, 1, 0, 0, 0), info.filename
        assert info.external_attr == 0o644 << 16, info.filename
        assert info.create_system == 0, info.filename
        assert info.compress_type == zipfile.ZIP_DEFLATED, info.filename


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_masking_que_cambia_algo_tambien_aborta():
    """El scrub es TESTIGO, no filtro: si tuvo algo que hacer, es que al gate se le
    escapo un formato, y eso aborta."""
    entradas = _inputs(script_files={"scripts/x.ps1": "$t = '%s'\n" % _GHP_CORTO})
    files = hb.build_files(entradas, _frontera())
    # el gate NO lo reconoce (egress pide 36 chars despues de ghp_)...
    hb.assert_no_secrets(files)
    # ...pero el enmascarado SI, y por eso el bundle se cae igual
    assert hb.scrub_files(files) != files
    with pytest.raises(hb.HandoffSecretError) as exc:
        hb.build_bundle(entradas, _frontera())
    assert "scripts/x.ps1" in str(exc.value)


def test_el_gate_corre_sobre_el_texto_crudo_no_sobre_el_enmascarado():
    """REGRESION DEL BUG CENTRAL: si el scrub corriera primero, el secreto conocido
    desapareceria y el paquete SALDRIA. Falla cerrado, no abierto."""
    files = {"a.ps1": "$t = '%s'\n" % _GLPAT}
    assert hb.scrub_files(files) != files, "el enmascarado SI lo reconoce"
    with pytest.raises(hb.HandoffSecretError):
        hb.assert_no_secrets(files)               # el gate tambien, sobre el crudo
    # y sobre el YA enmascarado el gate no encontraria nada: por eso el orden importa
    hb.assert_no_secrets(hb.scrub_files(files))


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_bundle_id_es_hash_del_contenido_del_zip():
    _bid, data, manifest = hb.build_bundle(_inputs(), _frontera())
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        empaquetados = {n: zf.read(n).decode("utf-8") for n in zf.namelist()}
    base = {k: v for k, v in empaquetados.items()
            if k not in ("MANIFEST.json", "README.md")}
    assert hb.compute_bundle_id(base) == manifest["bundle_id"]


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_zip_ignora_el_orden_de_insercion():
    files = hb.build_files(_inputs(), _frontera())
    assert hb.zip_bytes(files) == hb.zip_bytes(dict(reversed(list(files.items()))))


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_zip_usa_epoch_fijo():
    data = hb.zip_bytes(hb.build_files(_inputs(), _frontera()))
    for info in zipfile.ZipFile(io.BytesIO(data)).infolist():
        assert info.date_time == (1980, 1, 1, 0, 0, 0)


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_zip_arcnames_con_barra_posix():
    files = {"a\\b\\c.yml": "x: 1\n"}
    with zipfile.ZipFile(io.BytesIO(hb.zip_bytes(files))) as zf:
        for nombre in zf.namelist():
            assert "\\" not in nombre


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_secreto_sembrado_aborta_el_bundle(_data_dir):
    """KPI-2 — y NO deja archivo en disco."""
    entradas = _inputs(script_files={"scripts/x.ps1": "$t = '%s'\n" % _GLPAT})
    with pytest.raises(hb.HandoffSecretError) as exc:
        hb.build_bundle(entradas, _frontera())
    assert "scripts/x.ps1" in str(exc.value)
    assert not list(_data_dir.rglob("*.zip"))


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_secreto_en_el_readme_tambien_aborta():
    """Sembrado en un `format_hint`: se ataja EN EL CONSTRUCTOR, con el campo nombrado."""
    with pytest.raises(hb.HandoffSecretError) as exc:
        hb.HandoffVariable(name="TOKEN_CI", where="w", format_hint=_GLPAT, secret=True)
    assert "format_hint" in str(exc.value)
    assert "TOKEN_CI" in str(exc.value)


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_build_number_de_8_digitos_no_bloquea():
    """La clase `pii` de egress_policies matchea \\b\\d{7,8}\\b: un numero de build la
    dispara. Si el gate mirara el set completo, el paquete seria INCONSTRUIBLE."""
    from services.egress_policies import detect_classes

    texto = "Build 20260726 terminada.\n"
    assert "pii" in detect_classes(texto)
    entradas = _inputs(script_files={"scripts/x.ps1": texto})
    _bid, data, _m = hb.build_bundle(entradas, _frontera())
    assert data


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_palabra_produccion_no_bloquea():
    from services.egress_policies import detect_classes

    texto = "Este pipeline despliega a producción.\n"
    assert "production" in detect_classes(texto)
    entradas = _inputs(script_files={"scripts/x.ps1": texto})
    _bid, data, _m = hb.build_bundle(entradas, _frontera())
    assert data


def test_el_readme_generado_no_se_autobloquea():
    """Centinela: el propio texto que emite este plan tiene que pasar su propio gate.
    Un README de deploy dice 'producción' y trae comandos; si el gate mirara mas que la
    clase `secrets`, la feature no podria producir NI UN paquete."""
    files = hb.build_files(_inputs(), _frontera())
    hb.assert_no_secrets(files)
    assert hb.scrub_files(files) == files


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_bundle_path_rechaza_traversal(_data_dir):
    antes = sorted(p.name for p in _data_dir.iterdir())
    for malo in ("../../etc/passwd", "ABCD", "", "0123456789abcdeg",
                 "0123456789abcde", "0123456789abcdef0", None, 123):
        assert hb.bundle_path(malo) is None, malo
    assert hb.bundle_path("0123456789abcdef") is not None
    assert sorted(p.name for p in _data_dir.iterdir()) == antes


def test_persiste_atomico_y_prune_no_lanza(_data_dir):
    bid, data, manifest = hb.build_bundle(_inputs(), _frontera())
    destino = hb.persist_bundle(bid, data)
    assert destino.is_file()
    assert not list(destino.parent.glob("*.tmp"))
    hb.append_ledger(bid, manifest)
    ledger = _data_dir / "pipeline_handoff" / "bundles.jsonl"
    assert ledger.is_file()
    fila = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert fila["bundle_id"] == bid
    assert "at" in fila, "el timestamp va FUERA del zip"
    assert hb.prune_bundles() >= 0
