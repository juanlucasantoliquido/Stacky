"""Saneado de las filas duplicadas que dejó el publicador de épica en un proyecto GitLab.

QUÉ ARREGLA. `_persist_epic_ticket` (api/tickets.py:7100) escribía la fila local de
la épica SIN `tracker_type`, así que quedaba con el default de columna
`"azure_devops"` (models.py:49) aun dentro de un proyecto GitLab. El sync de GitLab
busca por la terna `(stacky_project_name, 'gitlab', external_id)`
(services/gitlab_sync.py:162-170) y por lo tanto NUNCA la encontraba: daba de alta
una SEGUNDA fila del MISMO issue. El grafo dibuja dos nodos porque indexa por
`(tracker, ado_id)` (api/tickets.py:646-655).

FRONTERA DURA — CERO ESCRITURAS EN GITLAB. Esta herramienta toca EXCLUSIVAMENTE la
base local. Los issues duplicados que existan de verdad en GitLab se REPORTAN por
`iid` para que el operador los cierre a mano; el script no los cierra, no los borra
y no los edita. No abre una sola conexión al tracker.

DRY-RUN POR DEFECTO. Sin `--aplicar` la base se abre en `mode=ro` (read-only a nivel
de SQLite, no por disciplina) y no se escribe un byte. Con `--aplicar` se saca un
backup ANTES de tocar nada, con la API de backup de sqlite3 (consistente con WAL).

BORRAR vs FUSIONAR. Seis tablas cuelgan de `tickets.id` y sólo UNA declara
`ON DELETE CASCADE`, así que borrar una fila con hijos deja huérfanos o revienta por
FK. Por eso: sin hijos ⇒ borrar; con hijos ⇒ FUSIONAR (re-apuntar los hijos a la
fila buena y recién ahí borrar la fantasma).

Uso:
    python scripts/sanear_duplicados_gitlab.py                    # dry-run (default)
    python scripts/sanear_duplicados_gitlab.py --db <ruta>        # otra base
    python scripts/sanear_duplicados_gitlab.py --proyecto RIPLEY  # acotar
    python scripts/sanear_duplicados_gitlab.py --aplicar          # ESCRIBE (con backup)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import sqlite3
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Las 6 tablas que DECLARAN una FK a tickets.id, verificadas con
# `pragma foreign_key_list` sobre la base viva (no copiadas de models.py, que
# declara sólo 4: `agent_html_publish` y `ticket_status_events` no están ahí).
#
# ¡PERO ESTA LISTA NO ALCANZA! Hay tablas que apuntan a `tickets.id` por una
# columna `ticket_id` SIN declarar la FK, y el pragma no las ve: medido sobre la
# base viva, `system_logs` tenía 7 filas colgando de la fila fantasma. Con
# `PRAGMA foreign_keys = 0` (el default de sqlite3) el DELETE pasa igual y las
# deja HUÉRFANAS EN SILENCIO. Por eso las hijas se DESCUBREN en runtime por la
# columna (`_tablas_hijas`) y esta tupla queda sólo como control cruzado.
TABLAS_CON_FK_DECLARADA = (
    "agent_executions",
    "agent_html_publish",
    "pack_runs",
    "pipeline_runs",
    "ticket_state_history",
    "ticket_status_events",
)


def _tablas_hijas(con: sqlite3.Connection) -> tuple[str, ...]:
    """TODA tabla con columna `ticket_id`, declare FK o no.

    Descubrir por COLUMNA y no por `pragma foreign_key_list` es la diferencia
    entre re-apuntar a los hijos y dejarlos huérfanos sin un solo error.
    """
    fuera: list[str] = []
    for (tabla,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name <> 'tickets'"
    ):
        try:
            columnas = [c[1] for c in con.execute(f"pragma table_info('{tabla}')")]
        except sqlite3.OperationalError:
            continue
        if "ticket_id" in columnas:
            fuera.append(tabla)
    return tuple(sorted(fuera))

TRACKER = "gitlab"


def ruta_base_por_defecto() -> Path:
    """La MISMA que abre el runtime: config.DATABASE_URL → runtime_paths.data_dir()."""
    try:
        from runtime_paths import data_dir

        return data_dir() / "stacky_agents.db"
    except Exception:  # noqa: BLE001 — el script tiene que servir sin el entorno
        return _BACKEND / "data" / "stacky_agents.db"


def _normalizar_titulo(t: str | None) -> str:
    return re.sub(r"\s+", " ", (t or "")).strip().lower()


def _conectar(ruta: Path, *, escritura: bool) -> sqlite3.Connection:
    if escritura:
        con = sqlite3.connect(str(ruta))
    else:
        # mode=ro: es SQLite quien rechaza la escritura, no la buena voluntad.
        con = sqlite3.connect(f"file:{ruta.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _backup(ruta: Path) -> Path:
    """Copia consistente ANTES de escribir. Usa la API de backup de sqlite3 y no
    `shutil.copy`: con WAL activo (db.py:103-111) copiar el archivo suelto puede
    dejar afuera el contenido del -wal."""
    destino_dir = ruta.parent / "backups"
    destino_dir.mkdir(parents=True, exist_ok=True)
    sello = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = destino_dir / f"stacky_agents-presaneado-{sello}.db"
    origen = sqlite3.connect(f"file:{ruta.as_posix()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(destino))
        try:
            origen.backup(dst)
        finally:
            dst.close()
    finally:
        origen.close()
    return destino


# ── análisis (solo lectura) ───────────────────────────────────────────────────

def _proyectos_gitlab(con: sqlite3.Connection, proyecto: str | None) -> list[str]:
    sql = ("SELECT DISTINCT stacky_project_name FROM tickets "
           "WHERE tracker_type = ? AND stacky_project_name IS NOT NULL")
    args: list = [TRACKER]
    if proyecto:
        sql += " AND stacky_project_name = ?"
        args.append(proyecto)
    return [r[0] for r in con.execute(sql, args)]


def _hijos_de(con: sqlite3.Connection, ticket_id: int) -> dict[str, int]:
    fuera = {}
    for tabla in _tablas_hijas(con):
        try:
            n = con.execute(
                f"SELECT COUNT(*) FROM {tabla} WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()[0]
        except sqlite3.OperationalError:
            continue           # la tabla no existe en esta versión de la base
        if n:
            fuera[tabla] = n
    return fuera


def analizar(con: sqlite3.Connection, proyecto: str | None = None) -> dict:
    """Devuelve el diagnóstico completo SIN tocar nada."""
    informe: dict = {"proyectos": [], "pares_locales": [], "fantasmas_sin_par": [],
                     "sentinelas": [], "duplicados_en_gitlab": [], "sellos_estringados": []}

    for proy in _proyectos_gitlab(con, proyecto):
        informe["proyectos"].append(proy)
        filas = list(con.execute(
            "SELECT id, ado_id, external_id, tracker_type, title, work_item_type, "
            "       ado_url, created_at, stacky_status "
            "FROM tickets WHERE stacky_project_name = ?", (proy,)))

        buenas = [f for f in filas if (f["tracker_type"] or "") == TRACKER]
        fantasmas = [f for f in filas if (f["tracker_type"] or "") != TRACKER]

        por_external = {f["external_id"]: f for f in buenas if f["external_id"] is not None}
        por_titulo: dict[str, list] = {}
        for f in buenas:
            por_titulo.setdefault(_normalizar_titulo(f["title"]), []).append(f)

        # (1) fantasmas: filas no-GitLab dentro de un proyecto GitLab.
        for f in fantasmas:
            buena = por_external.get(f["external_id"])
            criterio = "external_id" if buena is not None else None
            if buena is None:
                candidatas = por_titulo.get(_normalizar_titulo(f["title"]), [])
                if len(candidatas) == 1:
                    buena, criterio = candidatas[0], "titulo"
            registro = {
                "proyecto": proy,
                "fantasma": dict(f),
                "hijos": _hijos_de(con, f["id"]),
            }
            if buena is None:
                # Los `ado_id` NEGATIVOS son SENTINELAS por diseño (los tickets
                # sintéticos con los que Stacky corre agentes sin ticket real).
                # No son residuo del bug y meterlos con los fantasmas hace que el
                # operador vea 3 problemas donde hay 1.
                destino = ("sentinelas" if (f["ado_id"] or 0) < 0
                           else "fantasmas_sin_par")
                informe[destino].append(registro)
                continue
            registro["buena"] = dict(buena)
            registro["criterio"] = criterio
            registro["accion"] = "fusionar" if registro["hijos"] else "borrar"
            informe["pares_locales"].append(registro)

        # (2) duplicados REALES en GitLab: dos issues distintos, mismo título.
        #     SOLO REPORTE — el operador los cierra a mano.
        for titulo, grupo in por_titulo.items():
            if titulo and len(grupo) > 1:
                informe["duplicados_en_gitlab"].append({
                    "proyecto": proy,
                    "titulo": grupo[0]["title"],
                    "iids": sorted(g["ado_id"] for g in grupo),
                    "external_ids": sorted(g["external_id"] for g in grupo
                                           if g["external_id"] is not None),
                    "urls": [g["ado_url"] for g in grupo],
                })

        # (3) rastro del OTRO defecto: el sello `epic_ado_id` guardado como STRING.
        #     Con el sello estringado el guard del modal no lo reconocía y el
        #     frontend republicaba ⇒ una épica de más EN GITLAB que puede todavía no
        #     estar sincronizada acá. No se toca nada: es una pista para el operador.
        try:
            filas_sello = con.execute(
                "SELECT e.id, e.status, e.metadata_json FROM agent_executions e "
                "JOIN tickets t ON t.id = e.ticket_id "
                "WHERE t.stacky_project_name = ? AND e.metadata_json LIKE '%epic_ado_id%'",
                (proy,))
            for fila in filas_sello:
                import json as _json
                try:
                    md = _json.loads(fila["metadata_json"] or "{}")
                except Exception:  # noqa: BLE001
                    continue
                for clave in ("epic_ado_id", "issue_ado_id"):
                    if isinstance(md.get(clave), str):
                        informe["sellos_estringados"].append({
                            "proyecto": proy, "execution_id": fila["id"],
                            "status": fila["status"], "clave": clave,
                            "valor": md[clave],
                        })
        except sqlite3.OperationalError:
            pass

    return informe


# ── aplicación (solo con --aplicar) ───────────────────────────────────────────

def aplicar(con: sqlite3.Connection, informe: dict) -> dict:
    """Fusiona/borra las filas fantasma emparejadas. NO toca `fantasmas_sin_par`."""
    hechos = {"fusionadas": 0, "borradas": 0, "hijos_reapuntados": 0}
    cur = con.cursor()
    hijas = _tablas_hijas(con)
    for par in informe["pares_locales"]:
        viejo, nuevo = par["fantasma"]["id"], par["buena"]["id"]
        # Se re-apunta contra las tablas DESCUBIERTAS ahora, no contra la lista
        # que trae el informe: si el informe se calculó con una foto vieja, la
        # diferencia son huérfanos.
        for tabla in hijas:
            n = cur.execute(
                f"UPDATE {tabla} SET ticket_id = ? WHERE ticket_id = ?", (nuevo, viejo)
            ).rowcount
            hechos["hijos_reapuntados"] += max(n, 0)
        # POST-CONDICIÓN ANTES DE BORRAR. `PRAGMA foreign_keys` es 0 por defecto:
        # si quedara un hijo colgando, el DELETE pasaría igual y lo dejaría
        # huérfano SIN un solo error. Se aborta la transacción entera.
        for tabla in hijas:
            quedan = cur.execute(
                f"SELECT COUNT(*) FROM {tabla} WHERE ticket_id = ?", (viejo,)
            ).fetchone()[0]
            if quedan:
                con.rollback()
                raise RuntimeError(
                    f"ABORTADO sin escribir: quedan {quedan} fila(s) en {tabla} "
                    f"apuntando al ticket {viejo}. Borrarlo las dejaría huérfanas."
                )
        cur.execute("DELETE FROM tickets WHERE id = ?", (viejo,))
        if par["accion"] == "fusionar":
            hechos["fusionadas"] += 1
        else:
            hechos["borradas"] += 1
    con.commit()
    return hechos


# ── reporte ───────────────────────────────────────────────────────────────────

def imprimir(informe: dict, *, ruta: Path, aplicado: bool) -> None:
    # La consola de Windows es cp1252: sin esto, el primer título con acento (o la
    # flecha del reporte) mata el script con UnicodeEncodeError DESPUÉS de haber
    # impreso medio informe — el operador se queda con un reporte truncado y con
    # cara de crash.
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — si no se puede, seguimos igual
            pass
    p = print
    p("=" * 78)
    p(f"SANEADO DE DUPLICADOS GITLAB — {'APLICADO' if aplicado else 'DRY-RUN (no se tocó nada)'}")
    p(f"base: {ruta}")
    p(f"proyectos GitLab analizados: {', '.join(informe['proyectos']) or '(ninguno)'}")
    p("=" * 78)

    p(f"\n[1] PARES LOCALES (mismo issue, dos filas) — {len(informe['pares_locales'])}")
    for r in informe["pares_locales"]:
        f, b = r["fantasma"], r["buena"]
        p(f"  · {r['proyecto']} | criterio={r['criterio']} | accion={r['accion'].upper()}")
        p(f"      fantasma  id={f['id']:>6} tracker={f['tracker_type']!r:>15} "
          f"ado_id={f['ado_id']} external_id={f['external_id']} wit={f['work_item_type']}")
        p(f"      buena     id={b['id']:>6} tracker={b['tracker_type']!r:>15} "
          f"ado_id={b['ado_id']} external_id={b['external_id']} wit={b['work_item_type']}")
        p(f"      titulo    {f['title']!r}")
        if r["hijos"]:
            p(f"      hijos     {r['hijos']}  → se RE-APUNTAN a id={b['id']} antes de borrar")

    p(f"\n[2] FANTASMAS SIN PAR (no se tocan, solo reporte) — {len(informe['fantasmas_sin_par'])}")
    for r in informe["fantasmas_sin_par"]:
        f = r["fantasma"]
        p(f"  · {r['proyecto']} | id={f['id']} tracker={f['tracker_type']!r} "
          f"ado_id={f['ado_id']} external_id={f['external_id']} hijos={r['hijos'] or '{}'}")
        p(f"      titulo {f['title']!r}")

    p(f"\n[2b] SENTINELAS (ado_id negativo — POR DISEÑO, ignorar) — "
      f"{len(informe['sentinelas'])}")
    for r in informe["sentinelas"]:
        f = r["fantasma"]
        p(f"  · {r['proyecto']} | id={f['id']} ado_id={f['ado_id']} titulo={f['title']!r}")

    p(f"\n[3] DUPLICADOS EN GITLAB — SOLO REPORTE, CERRALOS A MANO — "
      f"{len(informe['duplicados_en_gitlab'])}")
    for r in informe["duplicados_en_gitlab"]:
        p(f"  · {r['proyecto']} | iids={r['iids']} | titulo={r['titulo']!r}")
        for u in r["urls"]:
            p(f"      {u}")

    p(f"\n[4] SELLOS ESTRINGADOS (rastro de la doble publicación en el tracker) — "
      f"{len(informe['sellos_estringados'])}")
    if informe["sellos_estringados"]:
        p("     Con el sello como string el guard del modal no lo reconocía y el")
        p("     frontend republicaba. Revisá EN GITLAB si esos iid tienen gemelo:")
    for r in informe["sellos_estringados"]:
        p(f"  · {r['proyecto']} | execution_id={r['execution_id']} status={r['status']} "
          f"{r['clave']}={r['valor']!r} (str)")
    p("")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=None, help="ruta a la base (default: la del runtime)")
    ap.add_argument("--proyecto", default=None, help="acotar a un proyecto Stacky")
    ap.add_argument("--aplicar", action="store_true",
                    help="ESCRIBE en la base local (saca backup antes). Sin esto: dry-run.")
    args = ap.parse_args(argv)

    ruta = Path(args.db).expanduser() if args.db else ruta_base_por_defecto()
    if not ruta.exists():
        print(f"ERROR: no existe la base {ruta}", file=sys.stderr)
        return 2

    con = _conectar(ruta, escritura=False)
    try:
        informe = analizar(con, args.proyecto)
    finally:
        con.close()

    if not args.aplicar:
        imprimir(informe, ruta=ruta, aplicado=False)
        total = len(informe["pares_locales"])
        print(f"DRY-RUN: {total} par(es) se fusionarían/borrarían. "
              f"Para aplicar: --aplicar (saca backup solo).")
        return 0

    if not informe["pares_locales"]:
        print("No hay pares para sanear; no se escribe nada.")
        return 0

    destino = _backup(ruta)
    print(f"backup: {destino}")
    con = _conectar(ruta, escritura=True)
    try:
        hechos = aplicar(con, informe)
    finally:
        con.close()
    imprimir(informe, ruta=ruta, aplicado=True)
    print(f"APLICADO: {hechos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
