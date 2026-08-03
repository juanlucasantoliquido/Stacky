"""tests/test_saneado_duplicados_gitlab.py — gates de la herramienta de saneado.

`scripts/sanear_duplicados_gitlab.py` BORRA filas de la base del operador. Los dos
gates que importan son de seguridad, no de features:

  - el dry-run (comportamiento por DEFECTO) no escribe un solo byte;
  - `--aplicar` re-apunta los hijos ANTES de borrar y saca backup solo.

Seis tablas cuelgan de `tickets.id` y sólo `ticket_state_history` declara
`ON DELETE CASCADE`: borrar sin re-apuntar deja ejecuciones huérfanas. El caso 04
se corre CONTRA ese defecto.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import scripts.sanear_duplicados_gitlab as san  # noqa: E402


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


@pytest.fixture()
def base(tmp_path, monkeypatch):
    """Una sqlite con el esquema REAL (models.Base), no uno inventado a mano."""
    ruta = tmp_path / "saneado.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{ruta.as_posix()}")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from db import Base
    import models  # noqa: F401 — su import es el que registra las tablas

    motor = create_engine(f"sqlite:///{ruta.as_posix()}", future=True)
    Base.metadata.create_all(motor)
    Sesion = sessionmaker(bind=motor, future=True)

    from models import AgentExecution, Ticket

    with Sesion() as s:
        # El par: MISMO issue de GitLab, dos filas. La fantasma nació sin
        # tracker_type ⇒ default "azure_devops" (models.py:49).
        fantasma = Ticket(ado_id=1115, external_id=1115, project="RIPLEY",
                          stacky_project_name="RIPLEY", tracker_type="azure_devops",
                          title="Épica X", work_item_type="Epic")
        buena = Ticket(ado_id=1115, external_id=1115, project="grupo/ripley",
                       stacky_project_name="RIPLEY", tracker_type="gitlab",
                       title="Épica X", work_item_type="Epic")
        # Sentinela: ado_id negativo, por diseño. NO es residuo del bug.
        sentinela = Ticket(ado_id=-1, external_id=-1, project="RIPLEY",
                           stacky_project_name="RIPLEY", tracker_type="azure_devops",
                           title="[Stacky] Brief Pool")
        # Proyecto ADO de verdad: la herramienta ni lo mira.
        ajeno = Ticket(ado_id=5000, external_id=5000, project="ProyADO",
                       stacky_project_name="ProyADO", tracker_type="azure_devops",
                       title="Épica X", work_item_type="Epic")
        s.add_all([fantasma, buena, sentinela, ajeno])
        s.flush()
        ids = {"fantasma": fantasma.id, "buena": buena.id,
               "sentinela": sentinela.id, "ajeno": ajeno.id}
        # Un hijo colgado de la fantasma: obliga a FUSIONAR, no a borrar.
        ejecucion = AgentExecution(ticket_id=fantasma.id, agent_type="business",
                                   status="completed", started_by="t@t")
        ejecucion.input_context = []          # NOT NULL en el esquema real
        s.add(ejecucion)
        # HIJO SIN FK DECLARADA. `SystemLog.ticket_id` es un `mapped_column(Integer)`
        # PELADO (models.py:455): apunta a `tickets.id` pero NO declara ForeignKey,
        # así que `pragma foreign_key_list` NO LO VE. Medido en la base viva: 7 de
        # estas filas colgaban de la fila fantasma y el saneado las habría dejado
        # huérfanas SIN UN SOLO ERROR (`PRAGMA foreign_keys` es 0 por defecto).
        from models import SystemLog
        s.add(SystemLog(level="INFO", source="test", action="fixture",
                        ticket_id=fantasma.id))
        s.commit()
    motor.dispose()

    class _B:
        def __init__(self):
            self.ruta = ruta
            self.ids = ids
            self.Sesion = sessionmaker(
                bind=create_engine(f"sqlite:///{ruta.as_posix()}", future=True),
                future=True)

    return _B()


def _informe(base):
    con = san._conectar(base.ruta, escritura=False)
    try:
        return san.analizar(con)
    finally:
        con.close()


def test_01_detecta_el_par_por_external_id(base):
    inf = _informe(base)
    assert len(inf["pares_locales"]) == 1, inf["pares_locales"]
    par = inf["pares_locales"][0]
    assert par["criterio"] == "external_id"
    assert par["fantasma"]["id"] == base.ids["fantasma"]
    assert par["buena"]["id"] == base.ids["buena"]
    assert par["accion"] == "fusionar", "tiene hijos: borrar dejaría una ejecución huérfana"


def test_02_los_sentinelas_no_se_reportan_como_fantasmas(base):
    inf = _informe(base)
    assert [r["fantasma"]["id"] for r in inf["sentinelas"]] == [base.ids["sentinela"]]
    assert inf["fantasmas_sin_par"] == []


def test_03_un_proyecto_ado_no_entra_en_el_informe(base):
    inf = _informe(base)
    assert inf["proyectos"] == ["RIPLEY"], "se metió un proyecto que no es GitLab"
    tocados = [r["fantasma"]["id"] for r in
               inf["pares_locales"] + inf["fantasmas_sin_par"] + inf["sentinelas"]]
    assert base.ids["ajeno"] not in tocados


def test_04_el_dry_run_NO_escribe_un_solo_byte(base):
    # GUARDA PRIMERO: sin esto, una herramienta que no detecta NADA pasaría este
    # test por accidente (no escribe porque no tiene nada que escribir).
    assert _informe(base)["pares_locales"], "el fixture no tiene nada que sanear"

    antes = _sha(base.ruta)
    codigo = san.main(["--db", str(base.ruta)])          # sin --aplicar
    assert codigo == 0
    assert _sha(base.ruta) == antes, "el dry-run modificó la base del operador"


def test_08_reapunta_al_hijo_SIN_FK_DECLARADA(base):
    """El censo por `pragma foreign_key_list` NO alcanza.

    Se corre CONTRA el defecto: si las tablas hijas se descubren por FK declarada
    (o peor, por una lista hardcodeada), `system_logs` queda afuera, el DELETE pasa
    igual —`PRAGMA foreign_keys` es 0— y la fila queda apuntando a un id que ya no
    existe. Sin este test, el saneado "funciona" mientras corrompe.
    """
    from models import SystemLog

    # GUARDA: que el fixture de verdad tenga el hijo sin FK. Sin esto el test
    # pasaría por accidente si alguien saca la fila del fixture.
    with base.Sesion() as s:
        assert s.query(SystemLog).filter_by(ticket_id=base.ids["fantasma"]).count() == 1

    # Y que la herramienta lo VEA antes de aplicar: si no lo cuenta, no lo re-apunta.
    hijos = _informe(base)["pares_locales"][0]["hijos"]
    assert "system_logs" in hijos, (
        f"la herramienta no ve al hijo sin FK declarada: {hijos}. "
        f"Está censando por `pragma foreign_key_list` en vez de por columna."
    )

    assert san.main(["--db", str(base.ruta), "--aplicar"]) == 0

    with base.Sesion() as s:
        assert s.query(SystemLog).filter_by(ticket_id=base.ids["fantasma"]).count() == 0, (
            "quedó un system_log apuntando a la fila BORRADA: huérfano mudo"
        )
        assert s.query(SystemLog).filter_by(ticket_id=base.ids["buena"]).count() == 1


def test_05_aplicar_reapunta_los_hijos_y_no_deja_huerfanos(base):
    from models import AgentExecution, Ticket

    codigo = san.main(["--db", str(base.ruta), "--aplicar"])
    assert codigo == 0

    with base.Sesion() as s:
        assert s.get(Ticket, base.ids["fantasma"]) is None, "la fila fantasma sigue"
        assert s.get(Ticket, base.ids["buena"]) is not None, "se borró la fila BUENA"
        ejecs = s.query(AgentExecution).all()
        assert len(ejecs) == 1
        assert ejecs[0].ticket_id == base.ids["buena"], (
            f"la ejecución quedó apuntando a {ejecs[0].ticket_id} (huérfana): "
            f"se borró la fila antes de re-apuntar los hijos"
        )


def test_06_aplicar_deja_backup_antes_de_tocar(base):
    san.main(["--db", str(base.ruta), "--aplicar"])
    backups = list((base.ruta.parent / "backups").glob("stacky_agents-presaneado-*.db"))
    assert len(backups) == 1, f"no se sacó backup antes de escribir: {backups}"
    assert backups[0].stat().st_size > 0


def test_07_segunda_corrida_es_idempotente(base):
    san.main(["--db", str(base.ruta), "--aplicar"])
    inf = _informe(base)
    assert inf["pares_locales"] == [], "quedaron pares después de sanear"
