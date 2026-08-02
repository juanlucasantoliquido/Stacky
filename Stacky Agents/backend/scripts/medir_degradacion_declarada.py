"""Plan 290 F8.2 — mide el KPI K1: que porcentaje de las corridas que PODIAN
declarar una degradacion, la declararon.

    K1 = (ejecuciones con metadata["capability_degraded"] no vacio)
         / (ejecuciones de proyectos NO-ADO, con metadata["ado_context"]
            presente, iniciadas despues del commit de F2)

El denominador NO es "todas las ejecuciones". No hay forma de saber, a
posteriori, si una ejecucion ATRAVESO el guard: sin el filtro, el denominador
incluye corridas que nunca podian declarar y el KPI baja por construccion. El
`ado_context` del Plan 289 es la prueba de que esa corrida paso por
`enrich_blocks`, que es exactamente el camino que F2 instrumenta.

Meta: >= 95 %. No 100 %: una corrida que muere entre el enriquecimiento y el
commit de la fila es un hueco real y honesto, no un defecto a perseguir.

SOLO LECTURA. Nunca escribe en la base del operador.

    ⚠️ El motor corre en WAL (db.py:42-49), asi que las escrituras recientes
    viven en el sidecar `-wal` y NO en el `.db`. Copiar solo el `.db` da una foto
    INCONSISTENTE: medir sobre esa copia hace que el arranque falle con
    `IntegrityError: UNIQUE constraint failed: tickets.stacky_project_name,
    tickets.tracker_type, tickets.external_id`, y la metrica que sale de ahi no
    es "aproximada": es FALSA. Por eso este script usa `VACUUM INTO`, que produce
    una foto consistente en un solo archivo sin tocar el origen.

Uso:
    python scripts/medir_degradacion_declarada.py [--desde 2026-08-02]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

CLAVE_DEGRADACION = "capability_degraded"
CLAVE_CONTEXTO = "ado_context"


def _ruta_base() -> Path:
    from runtime_paths import data_dir

    return data_dir() / "stacky_agents.db"


def _foto_consistente(origen: Path, destino: Path) -> None:
    """`VACUUM INTO`: una foto consistente en UN archivo, sin tocar el origen.

    Se abre en modo `ro` por URI para que ni siquiera exista la posibilidad de
    escribir en la base viva del operador.
    """
    if destino.exists():
        destino.unlink()
    con = sqlite3.connect(f"file:{origen}?mode=ro", uri=True)
    try:
        con.execute("VACUUM INTO ?", (str(destino),))
    finally:
        con.close()


def _es_no_ado(nombre: str | None) -> bool:
    from services.project_context import tracker_is_azure_devops

    return not tracker_is_azure_devops(nombre)


def medir(desde: str | None = None) -> dict:
    origen = _ruta_base()
    if not origen.exists():
        return {"error": f"no existe la base: {origen}"}

    with tempfile.TemporaryDirectory(prefix="plan290_") as tmp:
        copia = Path(tmp) / "foto.db"
        _foto_consistente(origen, copia)

        con = sqlite3.connect(f"file:{copia}?mode=ro", uri=True)
        try:
            sql = (
                "SELECT e.id, e.metadata_json, t.stacky_project_name "
                "FROM agent_executions e LEFT JOIN tickets t ON t.id = e.ticket_id"
            )
            params: tuple = ()
            if desde:
                sql += " WHERE e.started_at >= ?"
                params = (desde,)
            filas = con.execute(sql, params).fetchall()
        finally:
            con.close()

    candidatas = 0
    declaradas = 0
    for _id, md_json, proyecto in filas:
        try:
            md = json.loads(md_json) if md_json else {}
        except (TypeError, ValueError):
            continue
        if not isinstance(md, dict):
            continue
        # El denominador: paso por enrich_blocks (ado_context) Y es no-ADO.
        if CLAVE_CONTEXTO not in md:
            continue
        if not _es_no_ado(proyecto):
            continue
        candidatas += 1
        if md.get(CLAVE_DEGRADACION):
            declaradas += 1

    pct = (declaradas / candidatas * 100.0) if candidatas else 0.0
    return {
        "base": str(origen),
        "desde": desde,
        "ejecuciones_totales": len(filas),
        "candidatas": candidatas,
        "declaradas": declaradas,
        "porcentaje": round(pct, 1),
        "meta": 95.0,
        "cumple": candidatas > 0 and pct >= 95.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="KPI K1 del Plan 290 (solo lectura)")
    ap.add_argument(
        "--desde",
        default=None,
        help="ISO date; solo ejecuciones iniciadas desde esa fecha (el commit de F2)",
    )
    args = ap.parse_args()

    r = medir(args.desde)
    if "error" in r:
        print(r["error"])
        return 1
    print(f"base:                {r['base']}")
    print(f"desde:               {r['desde'] or '(sin filtro)'}")
    print(f"ejecuciones leidas:  {r['ejecuciones_totales']}")
    print(f"candidatas:          {r['candidatas']}  (no-ADO y con ado_context)")
    print(f"declaradas:          {r['declaradas']}")
    print(f"K1 = declaradas / candidatas = {r['porcentaje']} %   (meta >= {r['meta']} %)")
    if r["candidatas"] == 0:
        print()
        print("Sin candidatas todavia: no hay corridas no-ADO posteriores al despliegue")
        print("de F2. El KPI no es 0 %, es NO MEDIBLE aun. Volve a correrlo despues de")
        print("la primera corrida sobre un proyecto GitLab.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
