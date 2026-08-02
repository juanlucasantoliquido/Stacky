"""Plan 290 F9 [ADICION ARQUITECTO] — la deuda de los ocho sitios deja de ser prosa.

Este plan instrumenta 2 de los 8 guards del Plan 281 F7. Los otros 6 quedan
fuera de scope CON MOTIVO — pero un motivo escrito en un .md tiene un final
conocido en este repo: nadie vuelve a leerlo. Y hay un agravante: el dia que
alguien agregue un noveno guard, no existe nada que lo obligue a decidir si
declara o no. Nace mudo, como nacieron estos ocho.

Un .md no es un mecanismo. Un test si.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Se arma por partes A PROPOSITO: si el censo se ampliara alguna vez a `tests/`,
# un literal completo en este archivo se cazaria a si mismo y el test contaria
# un sitio fantasma (censo circular).
MARCA = "Plan 281 " + "F7 sitio"

#: Directorios del backend que el censo NO mira. `tests/` queda afuera porque los
#: tests HABLAN de los sitios sin ser sitios.
EXCLUIDOS = {"tests", "scripts", ".venv", "venv", "node_modules", "__pycache__"}


def _relativa(ruta: Path) -> str:
    """Ruta relativa al backend con `/`, NUNCA `archivo:linea`: los ocho anclajes
    de §2.1 ya se movieron una vez y se van a volver a mover; el archivo, no."""
    return ruta.relative_to(BACKEND).as_posix()


def _censar_sitios() -> list[str]:
    """Archivos del backend que contienen al menos un guard del Plan 281 F7."""
    vistos: list[str] = []
    for ruta in sorted(BACKEND.rglob("*.py")):
        partes = set(ruta.relative_to(BACKEND).parts)
        if partes & EXCLUIDOS:
            continue
        try:
            texto = ruta.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover — defensa
            continue
        if MARCA in texto:
            vistos.append(_relativa(ruta))
    return vistos


def _contar_guards() -> int:
    """Cuantos guards hay en total (un archivo puede tener mas de uno)."""
    total = 0
    for rel in _censar_sitios():
        total += (BACKEND / rel).read_text(encoding="utf-8").count(MARCA)
    return total


def _declara(archivo: str) -> bool:
    """¿Ese archivo llama de verdad a `capability_degradation.declarar(...)`?

    Por AST y no por subcadena: una mencion en un docstring o un comentario no es
    una llamada. Se aceptan las dos formas de invocacion (`modulo.declarar(...)` y
    `declarar(...)` importado suelto) para que el gate no dependa del estilo de
    import de quien instrumente el noveno sitio.
    """
    arbol = ast.parse((BACKEND / archivo).read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        f = nodo.func
        if getattr(f, "attr", None) == "declarar" or getattr(f, "id", None) == "declarar":
            return True
    return False


def test_todo_sitio_281_esta_instrumentado_o_declarado_como_deuda():
    from services.capability_degradation import SITIOS_SIN_DECLARAR

    sitios = _censar_sitios()
    # Sin esto, un censo roto (renombre de la marca, `rglob` que no encuentra
    # nada) daria VERDE por lista vacia: el fallo clasico del censo por subcadena.
    assert len(sitios) >= 5, (
        f"el censo solo vio {len(sitios)} archivos con guards: el parser se rompio"
    )
    assert _contar_guards() >= 8, (
        f"el censo solo vio {_contar_guards()} guards y el Plan 281 F7 dejo 8: "
        "el parser se rompio"
    )

    sin_clasificar = [
        s for s in sitios if not _declara(s) and s not in SITIOS_SIN_DECLARAR
    ]
    assert sin_clasificar == [], (
        f"sitios de degradacion sin clasificar: {sin_clasificar}. "
        "O instrumentalos con capability_degradation.declarar(), o agregalos a "
        "SITIOS_SIN_DECLARAR con su motivo."
    )


def test_los_dos_instrumentados_declaran_de_verdad():
    """Sentinela de PRESENCIA, no de ausencia.

    Si alguien borra la llamada de F2 o de F3, el test de arriba seguiria VERDE:
    el archivo caeria en "no declara" y bastaria moverlo a SITIOS_SIN_DECLARAR
    para cerrar la prosa. Este lo impide.
    """
    from services.capability_degradation import SITIOS_SIN_DECLARAR

    assert _declara("services/business_preflight.py")
    assert _declara("services/self_review.py")
    assert "services/business_preflight.py" not in SITIOS_SIN_DECLARAR
    assert "services/self_review.py" not in SITIOS_SIN_DECLARAR
    # Y los 6 que quedaron fuera tienen motivo ESCRITO, no una entrada vacia.
    assert all(str(v).strip() for v in SITIOS_SIN_DECLARAR.values()), (
        f"hay entradas de SITIOS_SIN_DECLARAR sin motivo: {SITIOS_SIN_DECLARAR}"
    )
