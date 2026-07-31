#!/usr/bin/env bash
# smoke_plan277_jerarquia.sh — Plan 277 F8: EL GATE DE CIERRE (paridad POSIX).
#
# Mismo contrato y MISMOS codigos de salida que smoke_plan277_jerarquia.ps1. Existen
# los dos porque los dos ratchets del repo divergen y el .ps1 es el que corre en la
# maquina del operador; este es el que corre en un runner Linux.
#
# Uso:
#   ./scripts/smoke_plan277_jerarquia.sh --project RIPLEY --base-url http://localhost:5000
#   echo $?
#
# PENDIENTE: LA CORRIDA EN VIVO ES DEL OPERADOR. Al implementar F8 (2026-07-31) no
# habia backend levantado ni token; se verifico la SINTAXIS (`bash -n` aca, y
# `compile()` sobre el programa de Python de mas abajo), no el comportamiento. Y sobre
# la base real (solo lectura) se midio que las 2 columnas de F4 YA existen (el paso 2
# no dara exit 7) pero que hay 0 tickets clasificados localmente: hoy este gate sale
# **exit 5** hasta que el operador clasifique al menos una epica desde la pantalla.
#
# CODIGOS DE SALIDA:
#   0 todo bien | 2 flags | 7 columnas en la BD REAL | 3 sync != 200
#   4 respuesta no serializable | 5 epics == 0 | 6 se perdio o se duplico un ticket
#   8 no se pudo hablar con el backend / falta el interprete
set -u

PROJECT=""
BASE_URL="http://localhost:5000"

while [ $# -gt 0 ]; do
  case "$1" in
    --project|-Project) PROJECT="${2:-}"; shift 2 ;;
    --base-url|-BaseUrl) BASE_URL="${2:-}"; shift 2 ;;
    -h|--help)
      echo "uso: $0 --project <nombre> [--base-url http://localhost:5000]"; exit 0 ;;
    *) echo "argumento desconocido: $1" >&2; exit 8 ;;
  esac
done

if [ -z "$PROJECT" ]; then
  echo "falta --project" >&2
  exit 8
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

PY=""
for cand in "$BACKEND_DIR/.venv/bin/python" "$BACKEND_DIR/venv/bin/python" \
            "$BACKEND_DIR/.venv/Scripts/python.exe" "$BACKEND_DIR/venv/Scripts/python.exe"; do
  if [ -x "$cand" ]; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1; then PY="$(command -v python3)"; fi
fi
if [ -z "$PY" ]; then
  echo "FALLO (8): no se encontro un interprete de Python." >&2
  exit 8
fi

export SMOKE277_PROJECT="$PROJECT"
export SMOKE277_BASE_URL="$BASE_URL"

# TODO el gate vive en un solo programa de Python: las 8 comprobaciones comparten el
# mismo estado (el total de la BD del paso 2 es el que compara el paso 7), y partirlas
# en llamadas sueltas obligaria a serializar ese estado entre procesos sin ganar nada.
# `bash -n` valida este envoltorio; el programa de adentro se valida con `py_compile`.
cd "$BACKEND_DIR" || exit 8
"$PY" - <<'PYCODE'
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

PROYECTO = os.environ["SMOKE277_PROJECT"]
BASE = os.environ["SMOKE277_BASE_URL"].rstrip("/")
KS = [
    "STACKY_GITLAB_HIERARCHY_CONTRACT_ENABLED",
    "STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED",
    "STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED",
    "STACKY_GITLAB_SYNC_PARENTS_ENABLED",
]


def fallar(codigo, texto):
    print("FALLO (%d): %s" % (codigo, texto))
    sys.exit(codigo)


def pedir(metodo, url, cuerpo=None):
    datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
    req = urllib.request.Request(url, data=datos, method=metodo)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:
        fallar(8, "no se pudo hablar con el backend en %s: %s" % (BASE, exc))


# ── Paso 1 ──────────────────────────────────────────────────────────────────
print("[1] las 4 flags del plan, en el registro y con ayuda llana")
from services.harness_flags import FLAG_REGISTRY
from services.harness_flags_help import PLAIN_HELP

registradas = {f.key for f in FLAG_REGISTRY}
sin_registro = [k for k in KS if k not in registradas]
sin_ayuda = [k for k in KS if k not in PLAIN_HELP]
vacias = sorted({
    k for k in KS if k in PLAIN_HELP
    for campo in (PLAIN_HELP[k].what, PLAIN_HELP[k].on_effect,
                  PLAIN_HELP[k].off_effect, PLAIN_HELP[k].example)
    if not (campo or "").strip()
})
if sin_registro or sin_ayuda or vacias:
    fallar(2, "sin registro: %s | sin ayuda: %s | campos vacios: %s"
              % (sin_registro, sin_ayuda, vacias))
print("    4 flags registradas y con ayuda llana OK")

# ── Paso 2: contra la BD REAL ───────────────────────────────────────────────
# Unico punto donde se comprueba que la migracion ocurrio de verdad: el ALTER de
# db.py:304-312 se traga sus errores y los tests corren sobre sqlite temporal.
print("[2] columnas local_work_item_type / local_parent_iid en la BD REAL")
import config
from services.project_context import resolve_project_context

url_bd = config.DATABASE_URL
if not url_bd.startswith("sqlite"):
    fallar(7, "la BD no es sqlite: %s" % url_bd)
ruta_bd = url_bd.split("sqlite:///", 1)[-1]
ctx = resolve_project_context(PROYECTO)
if ctx is None:
    fallar(7, "no se pudo resolver el proyecto '%s'" % PROYECTO)

con = sqlite3.connect(ruta_bd)
try:
    columnas = {fila[1] for fila in con.execute("PRAGMA table_info(tickets)")}
    faltantes = [c for c in ("local_work_item_type", "local_parent_iid") if c not in columnas]
    if faltantes:
        fallar(7, "faltan columnas en la tabla tickets de la BD REAL: %s. El ALTER de "
                  "db.py se traga sus errores; los tests corren sobre sqlite temporal."
                  % ", ".join(faltantes))
    # El MISMO filtro que `_ticket_project_filter` (api/tickets.py:348-355), que NO
    # filtra por tracker_type: la respuesta mezcla ADO y GitLab del mismo proyecto.
    where = "(stacky_project_name = ? OR (stacky_project_name IS NULL AND project = ?))"
    args = (ctx.stacky_project_name, ctx.tracker_project)
    total_bd = con.execute("SELECT COUNT(*) FROM tickets WHERE " + where, args).fetchone()[0]
finally:
    con.close()
print("    BD: %s" % ruta_bd)
print("    columnas OK. Filas del proyecto en la BD (TODOS los trackers): %d" % total_bd)

# ── Paso 3 ──────────────────────────────────────────────────────────────────
print("[3] POST /api/tickets/sync")
estado, cuerpo = pedir("POST", "%s/api/tickets/sync?project=%s" % (BASE, PROYECTO),
                       {"project": PROYECTO})
if estado != 200:
    fallar(3, "sync devolvio %s. Cuerpo: %s" % (estado, cuerpo))
print("    sync 200: %s" % cuerpo)

# ── Paso 4 ──────────────────────────────────────────────────────────────────
print("[4] GET /api/tickets/hierarchy")
estado, cuerpo = pedir("GET", "%s/api/tickets/hierarchy?project=%s" % (BASE, PROYECTO))
if estado != 200:
    fallar(4, "hierarchy devolvio %s. Un 500 aca suele ser el ciclo vivo "
              "(ValueError: Circular reference detected). Cuerpo: %s" % (estado, cuerpo))
jer = json.loads(cuerpo)
epics = jer.get("epics") or []
orphans = jer.get("orphans") or []
children = [h for e in epics for h in (e.get("children") or [])]
print("    epics=%d children=%d orphans=%d" % (len(epics), len(children), len(orphans)))

# ── Paso 5 ──────────────────────────────────────────────────────────────────
# Un 200 NO prueba que la estructura sea serializable rio abajo.
print("[5] serializar la respuesta (json.dumps)")
try:
    json.dumps(jer)
except ValueError as exc:
    fallar(4, "la respuesta NO es serializable: %s" % exc)
print("    serializa OK")

# ── Paso 6 ──────────────────────────────────────────────────────────────────
print("[6] epics >= 1")
if not epics:
    fallar(5, "epics == 0: el operador NO ve ninguna epica. Clasifica al menos una "
              "desde la pantalla (los issues heredados no traen etiquetas).")

# ── Paso 7 ──────────────────────────────────────────────────────────────────
print("[7] conservacion: total y unicidad de (tracker_type, ado_id)")
suma = len(epics) + len(children) + len(orphans)
if suma != total_bd:
    fallar(6, "la respuesta trae %d tickets y la BD tiene %d filas para el proyecto "
              "(contando TODOS los trackers). Se perdio o se agrego algo."
              % (suma, total_bd))
vistos = {}
for t in epics + children + orphans:
    clave = ((t.get("tracker_type") or "(sin tracker)").strip().lower(), t.get("ado_id"))
    vistos[clave] = vistos.get(clave, 0) + 1
duplicados = sorted("%s#%s" % c for c, n in vistos.items() if n > 1)
if duplicados:
    fallar(6, "hay pares (tracker_type, ado_id) repetidos en la union de las tres "
              "listas: %s. El total puede cerrar igual: un duplicado compensa al que "
              "desaparecio." % ", ".join(duplicados))
print("    %d tickets, sin duplicados" % suma)

# ── Paso 8 ──────────────────────────────────────────────────────────────────
print("[8] resumen")
print("")
print("  epics    : %d" % len(epics))
print("  children : %d" % len(children))
print("  orphans  : %d" % len(orphans))
print("  total    : %d  (BD: %d)" % (suma, total_bd))
print("")
print("  por tracker_type (respuesta):")
por_tracker = {}
for t in epics + children + orphans:
    nombre = t.get("tracker_type") or "(sin tracker)"
    por_tracker[nombre] = por_tracker.get(nombre, 0) + 1
for nombre in sorted(por_tracker):
    print("    %s: %d" % (nombre, por_tracker[nombre]))
print("")
print("  huerfanos por motivo:")
if not orphans:
    print("    (ninguno)")
else:
    por_motivo = {}
    for t in orphans:
        motivo = t.get("motivo_huerfano") or "(sin motivo)"
        por_motivo[motivo] = por_motivo.get(motivo, 0) + 1
    for motivo in sorted(por_motivo):
        print("    %s: %d" % (motivo, por_motivo[motivo]))
print("")
print("  epicas y sus hijos:")
for e in epics:
    hijos = e.get("children") or []
    print("    #%s %s  [%d hijos]" % (e.get("ado_id"), e.get("title"), len(hijos)))
    for h in hijos:
        print("        - #%s %s" % (h.get("ado_id"), h.get("title")))
print("")
print("OK: el operador ve la jerarquia.")
sys.exit(0)
PYCODE
