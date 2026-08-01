"""Plan 282 F0 — censos ejecutables del estado ANTES del arreglo.

REGLA DE LA CASA: un censo por subcadena da por cubierta la ruta larga y un censo
circular grepea su propia lista. Aca se BARRE EL DIRECTORIO y se cuenta por AST /
por referencia, nunca por `grep -c` sobre un closure.
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _constructores_directos() -> list[str]:
    """K3: modulos de services/ que llaman GitLabTrackerProvider(...) DIRECTO.

    Se excluye services/tracker_provider.py — ESE es el que tiene derecho
    (per-project y legacy; ambos pasan ca_bundle).

    ALCANCE DECLARADO: el glob es NO recursivo sobre services/. Fuera del censo,
    a proposito: tools/migrar_mantis_gitlab/destination_writer.py (el migrador
    tiene su propio eje) y los constructores de tests. Un censo que barriera todo
    el backend mezclaria deuda ajena.
    """
    ofensores: list[str] = []
    for py in sorted((BACKEND / "services").glob("*.py")):
        if py.name == "tracker_provider.py":
            continue
        arbol = ast.parse(py.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Name)
                and nodo.func.id == "GitLabTrackerProvider"
            ):
                ofensores.append(f"{py.name}:{nodo.lineno}")
    return ofensores


def test_f0_censo_constructores_gitlab_que_bypassean_la_fabrica():
    """ANTES del arreglo: exactamente 4 (gitlab_ci_logs, gitlab_ci_provider,
    gitlab_preflight, gitlab_variables). DESPUES de F2: 0.
    """
    ofensores = _constructores_directos()
    # F0 (rojo esperado): assert len(ofensores) == 4
    # F2 (verde):
    assert ofensores == [], f"bypassean la fabrica: {ofensores}"


def test_f0_el_publicador_de_comentarios_es_ado_only():
    """K1: hoy services/ado_publisher.py resuelve el cliente sin preguntar el
    tracker, y por eso muere en project_context (`no usa Azure DevOps`) en todo
    proyecto GitLab.

    GUARDA ANTI-FALSO-VERDE: el detector se prueba PRIMERO contra un fuente
    sintetico que si tiene el ruteo, y contra otro que no. Un assert de ausencia
    que nunca vio un positivo no prueba nada.
    """
    con_ruteo = "def p():\n    pub = resolve_comment_publisher(ticket)\n"
    sin_ruteo = "def p():\n    client = _client_for_ticket_project(x)\n"
    assert _rutea_por_tracker(con_ruteo), "el detector da falso negativo: test invalido"
    assert not _rutea_por_tracker(sin_ruteo), "el detector no detecta: test invalido"

    texto = (BACKEND / "services" / "ado_publisher.py").read_text(encoding="utf-8")
    # F0 (rojo esperado): assert not _rutea_por_tracker(texto)
    # F1 (verde):
    assert _rutea_por_tracker(texto), "ado_publisher no consulta el router de tracker"


def _rutea_por_tracker(fuente: str) -> bool:
    """True si el fuente REFERENCIA resolve_comment_publisher.

    Se censa por REFERENCIA (ast.Name/ast.Attribute), no por ast.Call con
    func.id: si manana la llamada se hace por alias o por atributo de modulo,
    un censo de llamadas daria CERO y premiaria el bug.
    """
    arbol = ast.parse(fuente)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name) and nodo.id == "resolve_comment_publisher":
            return True
        if isinstance(nodo, ast.Attribute) and nodo.attr == "resolve_comment_publisher":
            return True
    return False
