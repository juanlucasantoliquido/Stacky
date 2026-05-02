"""
Tests para allocators.ridioma_allocator — T6 RIDIOMA Allocator.

Cobertura: lectura de master, next_id, dedupe, dry-run, apply, error paths,
formato de inserts, comentario de trazabilidad.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from allocators.ridioma_allocator import allocate, RidiomaEntry, _extract_max_id, _encode_descripcion


# ── Fixtures ──────────────────────────────────────────────────────────────────


SAMPLE_SQL = """\
insert into RIDIOMA (IDIDIOMA, IDTEXTO, IDDESCRIPCION) values ('ESP',1000,'Aceptar');
insert into RIDIOMA (IDIDIOMA, IDTEXTO, IDDESCRIPCION) values ('ENG',1000,'Accept');
insert into RIDIOMA (IDIDIOMA, IDTEXTO, IDDESCRIPCION) values ('POR',1000,'Aceitar');
-- ADO-57 | 2026-04-25 | Header columna Prima
insert into RIDIOMA (IDIDIOMA, IDTEXTO, IDDESCRIPCION) values ('ESP',9294,'Prima');
insert into RIDIOMA (IDIDIOMA, IDTEXTO, IDDESCRIPCION) values ('ENG',9294,'Premium');
insert into RIDIOMA (IDIDIOMA, IDTEXTO, IDDESCRIPCION) values ('POR',9294,'Pr' + char(234) + 'mio');
-- ADO-70 | 2026-04-28 | Mensaje lista vacía
insert into RIDIOMA (IDIDIOMA, IDTEXTO, IDDESCRIPCION) values ('ESP',9296,'No hay lotes agendados');
insert into RIDIOMA (IDIDIOMA, IDTEXTO, IDDESCRIPCION) values ('ENG',9296,'No scheduled batches');
insert into RIDIOMA (IDIDIOMA, IDTEXTO, IDDESCRIPCION) values ('POR',9296,'N' + char(227) + 'o existem lotes');
"""


@pytest.fixture()
def master_file(tmp_path):
    """Crea un archivo maestro temporal con contenido de muestra."""
    f = tmp_path / "600804 - Inserts RIDIOMA.sql"
    f.write_text(SAMPLE_SQL, encoding="utf-8")
    return str(f)


# ── _extract_max_id ───────────────────────────────────────────────────────────


def test_extract_max_id_correct():
    max_id = _extract_max_id(SAMPLE_SQL)
    assert max_id == 9296


def test_extract_max_id_empty():
    assert _extract_max_id("") == 0


def test_extract_max_id_no_inserts():
    assert _extract_max_id("-- solo comentarios\n-- nada más") == 0


# ── allocate dry-run ──────────────────────────────────────────────────────────


def test_allocate_dry_run_returns_next_id(master_file):
    entry = allocate(
        ado_id=99,
        fecha="2026-05-02",
        textos={"ESP": "Nuevo mensaje", "ENG": "New message", "POR": "Nova mensagem"},
        contexto_uso="Validación en Test",
        master_path=master_file,
        apply=False,
    )
    assert entry.idtexto == 9297
    assert entry.applied is False
    assert entry.already_existed is False


def test_allocate_dry_run_does_not_modify_file(master_file):
    original = open(master_file, encoding="utf-8").read()
    allocate(
        ado_id=99,
        fecha="2026-05-02",
        textos={"ESP": "Nuevo mensaje"},
        contexto_uso="Test dry run",
        master_path=master_file,
        apply=False,
    )
    after = open(master_file, encoding="utf-8").read()
    assert original == after


def test_allocate_sql_inserts_format(master_file):
    entry = allocate(
        ado_id=99,
        fecha="2026-05-02",
        textos={"ESP": "Fecha inválida", "ENG": "Invalid date", "POR": "Data inválida"},
        contexto_uso="Validación GuardarConvenio",
        master_path=master_file,
        apply=False,
    )
    assert "-- ADO-99 | 2026-05-02 | Validación GuardarConvenio" in entry.sql_inserts
    assert f"insert into RIDIOMA" in entry.sql_inserts
    assert "ESP" in entry.sql_inserts
    assert "ENG" in entry.sql_inserts
    assert "POR" in entry.sql_inserts


def test_allocate_code_const(master_file):
    entry = allocate(
        ado_id=99,
        fecha="2026-05-02",
        textos={"ESP": "Texto"},
        contexto_uso="Test const",
        master_path=master_file,
        apply=False,
    )
    assert entry.code_const == "public const int m9297 = 9297;"


# ── allocate apply ────────────────────────────────────────────────────────────


def test_allocate_apply_modifies_file(master_file):
    entry = allocate(
        ado_id=100,
        fecha="2026-05-02",
        textos={"ESP": "Mensaje aplicado", "ENG": "Applied message"},
        contexto_uso="Test apply",
        master_path=master_file,
        apply=True,
    )
    assert entry.applied is True
    assert entry.idtexto == 9297

    content = open(master_file, encoding="utf-8").read()
    assert "insert into RIDIOMA" in content
    assert "9297" in content
    assert "ADO-100" in content


def test_allocate_apply_increments_correctly(master_file):
    entry1 = allocate(
        ado_id=101,
        fecha="2026-05-02",
        textos={"ESP": "Primer mensaje"},
        contexto_uso="Primer",
        master_path=master_file,
        apply=True,
    )
    entry2 = allocate(
        ado_id=102,
        fecha="2026-05-02",
        textos={"ESP": "Segundo mensaje"},
        contexto_uso="Segundo",
        master_path=master_file,
        apply=True,
    )
    assert entry2.idtexto == entry1.idtexto + 1


# ── Idempotencia (dedupe) ────────────────────────────────────────────────────


def test_allocate_idempotent_same_text(master_file):
    """Si el texto ESP ya existe en el maestro, no duplica."""
    # "No hay lotes agendados" ya existe en SAMPLE_SQL con IDTEXTO=9296
    entry = allocate(
        ado_id=70,
        fecha="2026-04-28",
        textos={"ESP": "No hay lotes agendados"},
        contexto_uso="Test dedupe",
        master_path=master_file,
        apply=False,
    )
    assert entry.already_existed is True
    assert entry.existing_idtexto == 9296
    assert entry.idtexto == 9296


# ── Error paths ───────────────────────────────────────────────────────────────


def test_allocate_file_not_found():
    with pytest.raises(FileNotFoundError):
        allocate(
            ado_id=1,
            fecha="2026-05-02",
            textos={"ESP": "X"},
            contexto_uso="Test",
            master_path="/no/existe/600804.sql",
            apply=False,
        )


def test_allocate_empty_textos(master_file):
    with pytest.raises(ValueError, match="vacío"):
        allocate(
            ado_id=1,
            fecha="2026-05-02",
            textos={},
            contexto_uso="Test",
            master_path=master_file,
            apply=False,
        )


def test_allocate_missing_esp(master_file):
    with pytest.raises(ValueError, match="ESP"):
        allocate(
            ado_id=1,
            fecha="2026-05-02",
            textos={"ENG": "Only English"},
            contexto_uso="Test",
            master_path=master_file,
            apply=False,
        )


# ── _encode_descripcion ───────────────────────────────────────────────────────


def test_encode_ascii_only():
    assert _encode_descripcion("Aceptar") == "'Aceptar'"


def test_encode_with_special_char():
    # ñ = char(241)
    encoded = _encode_descripcion("Contraseña")
    assert "char(241)" in encoded
    assert "Contrase" in encoded


def test_encode_empty():
    assert _encode_descripcion("") == "''"
