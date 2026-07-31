# smoke_plan277_jerarquia.ps1 — Plan 277 F8: EL GATE DE CIERRE.
#
# Un solo comando con EXIT CODE que prueba la meta del plan: que el operador VE la
# epica con sus hijos. Es el unico criterio que distingue "las fases cerraron" de
# "la jerarquia existe en la pantalla".
#
# Uso:
#   .\scripts\smoke_plan277_jerarquia.ps1 -Project RIPLEY -BaseUrl http://localhost:5000
#   if ($LASTEXITCODE -ne 0) { "FALLO con codigo $LASTEXITCODE" }
#
# ── PENDIENTE: LA CORRIDA EN VIVO ES DEL OPERADOR ───────────────────────────
# Al implementar F8 (2026-07-31) este script NO se pudo correr: no habia backend
# levantado (puerto 5000 libre) ni token de GitLab. Lo verificado fue la SINTAXIS
# (`[ScriptBlock]::Create(...)` para el .ps1, `bash -n` para el .sh, y `compile()`
# sobre los tres bloques de Python embebidos). Lo que falta es apretar el boton.
#
# ANTES DE CORRERLO, DOS COSAS MEDIDAS SOBRE LA BASE REAL (solo lectura, 2026-07-31):
#   - Las 2 columnas de F4 YA existen en la BD del operador => el paso 2 NO va a dar
#     exit 7. La migracion ocurrio de verdad.
#   - Hay 0 tickets clasificados localmente y 53 filas de GitLab en RIPLEY => hoy este
#     gate sale **exit 5** (epics == 0). NO es un bug del gate: los issues heredados no
#     traen etiquetas, asi que hay que clasificar al menos UNA epica desde la pantalla
#     (el smoke de F4) antes de correrlo. Si pasara sin ninguna clasificacion estaria
#     midiendo otra cosa.
#
# CODIGOS DE SALIDA (cada uno es un fallo DISTINTO; un 1 generico no sirve de nada):
#   0  todo bien
#   2  falta alguna de las 4 flags en el registro, o alguna sin ayuda llana
#   7  faltan las columnas local_work_item_type / local_parent_iid en la BD REAL
#   3  POST /api/tickets/sync no devolvio 200
#   4  la respuesta de /hierarchy no se puede serializar (ciclo vivo)
#   5  epics == 0: la meta del operador NO se cumplio
#   6  se perdio o se duplico algun ticket
#   8  no se pudo hablar con el backend / no se encontro el interprete
#
# POR QUE EL PASO 7 COMPARA CONTRA EL TOTAL DEL PROYECTO Y NO CONTRA LAS FILAS DE
# GITLAB: `get_hierarchy` filtra con `_ticket_project_filter` (api/tickets.py:348-355),
# que compara SOLO stacky_project_name/project y NO filtra por tracker_type. La
# respuesta mezcla ADO y GitLab del mismo proyecto de Stacky, asi que con una sola fila
# ADO en el proyecto la comparacion contra "filas GitLab" daria exit 6 sobre una
# implementacion perfecta.
#
# Y EL CHEQUEO DE DUPLICADOS ES LA OTRA MITAD: el total puede cerrar igual con el
# indice roto, porque un ticket duplicado compensa numericamente al que desaparecio.
# Contar apariciones por (tracker_type, ado_id) es lo que distingue "no se perdio
# nada" de "se perdio uno y se duplico otro".
param(
  [Parameter(Mandatory = $true)][string]$Project,
  [string]$BaseUrl = "http://localhost:5000"
)

$ErrorActionPreference = "Stop"
$backend = Split-Path -Parent $PSScriptRoot

function Write-Paso($n, $texto) { Write-Host "[$n] $texto" }
function Fallar($codigo, $texto) {
  Write-Host "FALLO ($codigo): $texto"
  exit $codigo
}

# ── Interprete: el venv del repo primero, el del PATH como ultimo recurso ────
$PY = $null
foreach ($cand in @(
    (Join-Path $backend ".venv\Scripts\python.exe"),
    (Join-Path $backend "venv\Scripts\python.exe"))) {
  if (Test-Path $cand) { $PY = $cand; break }
}
if (-not $PY) {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) { $PY = $cmd.Source }
}
if (-not $PY) { Fallar 8 "no se encontro un interprete de Python (probe backend\.venv y el PATH)." }

# ── Paso 1: las 4 flags registradas Y con ayuda llana no vacia ───────────────
Write-Paso 1 "las 4 flags del plan, en el registro y con ayuda llana"

$codigoFlags = @'
import sys
KS = [
    "STACKY_GITLAB_HIERARCHY_CONTRACT_ENABLED",
    "STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED",
    "STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED",
    "STACKY_GITLAB_SYNC_PARENTS_ENABLED",
]
from services.harness_flags import FLAG_REGISTRY
from services.harness_flags_help import PLAIN_HELP
registradas = {f.key for f in FLAG_REGISTRY}
sin_registro = [k for k in KS if k not in registradas]
sin_ayuda = [k for k in KS if k not in PLAIN_HELP]
vacias = [
    k for k in KS if k in PLAIN_HELP
    for campo in (PLAIN_HELP[k].what, PLAIN_HELP[k].on_effect,
                  PLAIN_HELP[k].off_effect, PLAIN_HELP[k].example)
    if not (campo or "").strip()
]
if sin_registro or sin_ayuda or vacias:
    print("sin registro: %s | sin ayuda: %s | campos vacios: %s"
          % (sin_registro, sin_ayuda, sorted(set(vacias))))
    sys.exit(1)
print("4 flags registradas y con ayuda llana OK")
'@

Push-Location $backend
try {
  $salidaFlags = $codigoFlags | & $PY - 2>&1
  $okFlags = ($LASTEXITCODE -eq 0)
} finally { Pop-Location }
Write-Host "    $salidaFlags"
if (-not $okFlags) { Fallar 2 "faltan flags en el registro o ayuda llana." }

# ── Paso 2: las 2 columnas nuevas, contra la BD REAL ─────────────────────────
# Es el UNICO punto donde se comprueba que la migracion ocurrio de verdad: el ALTER
# de db.py:304-312 se traga sus errores con `except Exception: pass`, y todos los
# tests corren sobre un sqlite temporal.
Write-Paso 2 "columnas local_work_item_type / local_parent_iid en la BD REAL"

$codigoBd = @'
import json, os, sqlite3, sys

proyecto = os.environ["SMOKE277_PROJECT"]
import config
url = config.DATABASE_URL
if not url.startswith("sqlite"):
    print(json.dumps({"error": "la BD no es sqlite: %s" % url}))
    sys.exit(2)
ruta = url.split("sqlite:///", 1)[-1]

con = sqlite3.connect(ruta)
try:
    columnas = {fila[1] for fila in con.execute("PRAGMA table_info(tickets)")}
    faltantes = [c for c in ("local_work_item_type", "local_parent_iid") if c not in columnas]

    # El MISMO filtro que `_ticket_project_filter` (api/tickets.py:348-355): por
    # stacky_project_name, con el fallback por `project` para las filas viejas que lo
    # tienen en NULL. NO se filtra por tracker_type, a proposito: la respuesta del
    # endpoint tampoco lo hace y el total tiene que ser comparable.
    from services.project_context import resolve_project_context
    ctx = resolve_project_context(proyecto)
    if ctx is None:
        print(json.dumps({"error": "no se pudo resolver el proyecto '%s'" % proyecto}))
        sys.exit(3)
    where = "(stacky_project_name = ? OR (stacky_project_name IS NULL AND project = ?))"
    args = (ctx.stacky_project_name, ctx.tracker_project)
    total = con.execute("SELECT COUNT(*) FROM tickets WHERE " + where, args).fetchone()[0]
    por_tracker = {
        (t or "(sin tracker)"): n
        for (t, n) in con.execute(
            "SELECT tracker_type, COUNT(*) FROM tickets WHERE " + where
            + " GROUP BY tracker_type", args)
    }
finally:
    con.close()

print(json.dumps({
    "db": ruta, "faltantes": faltantes, "total_bd": total,
    "por_tracker": por_tracker, "stacky_project_name": ctx.stacky_project_name,
}))
'@

$env:SMOKE277_PROJECT = $Project
Push-Location $backend
try {
  $salidaBd = $codigoBd | & $PY - 2>&1
  $okBd = ($LASTEXITCODE -eq 0)
} finally { Pop-Location }
if (-not $okBd) { Fallar 7 "no se pudo inspeccionar la BD real: $salidaBd" }
$bd = $salidaBd | ConvertFrom-Json
if ($bd.error) { Fallar 7 $bd.error }
Write-Host "    BD: $($bd.db)"
if ($bd.faltantes.Count -gt 0) {
  Fallar 7 ("faltan columnas en la tabla tickets de la BD REAL: " + ($bd.faltantes -join ", ") +
            ". El ALTER de db.py se traga sus errores; los tests corren sobre sqlite temporal.")
}
Write-Host "    columnas OK. Filas del proyecto en la BD (TODOS los trackers): $($bd.total_bd)"

# ── Paso 3: sync ────────────────────────────────────────────────────────────
Write-Paso 3 "POST /api/tickets/sync"
$urlSync = "$BaseUrl/api/tickets/sync?project=$([uri]::EscapeDataString($Project))"
$estadoSync = 0
$cuerpoSync = ""
try {
  $r = Invoke-WebRequest -Uri $urlSync -Method Post -ContentType "application/json" `
       -Body (@{ project = $Project } | ConvertTo-Json) -UseBasicParsing
  $estadoSync = [int]$r.StatusCode
  $cuerpoSync = $r.Content
} catch {
  $resp = $_.Exception.Response
  if ($resp) {
    $estadoSync = [int]$resp.StatusCode
    try {
      $lector = New-Object System.IO.StreamReader($resp.GetResponseStream())
      $cuerpoSync = $lector.ReadToEnd()
    } catch { $cuerpoSync = "(sin cuerpo legible)" }
  } else {
    Fallar 8 "no se pudo hablar con el backend en $BaseUrl : $($_.Exception.Message)"
  }
}
if ($estadoSync -ne 200) { Fallar 3 "sync devolvio $estadoSync. Cuerpo: $cuerpoSync" }
Write-Host "    sync 200: $cuerpoSync"

# ── Paso 4: la jerarquia ────────────────────────────────────────────────────
Write-Paso 4 "GET /api/tickets/hierarchy"
$urlJer = "$BaseUrl/api/tickets/hierarchy?project=$([uri]::EscapeDataString($Project))"
try {
  $rj = Invoke-WebRequest -Uri $urlJer -Method Get -UseBasicParsing
} catch {
  $resp = $_.Exception.Response
  if ($resp) {
    $estado = [int]$resp.StatusCode
    Fallar 4 ("hierarchy devolvio $estado. Un 500 aca suele ser el ciclo vivo " +
              "(ValueError: Circular reference detected).")
  }
  Fallar 8 "no se pudo hablar con el backend en $BaseUrl : $($_.Exception.Message)"
}
if ([int]$rj.StatusCode -ne 200) { Fallar 4 "hierarchy devolvio $($rj.StatusCode)." }
$jer = $rj.Content | ConvertFrom-Json

$epics = @($jer.epics)
$orphans = @($jer.orphans)
$children = @()
foreach ($e in $epics) { $children += @($e.children) }
$nEpics = $epics.Count
$nChildren = $children.Count
$nOrphans = $orphans.Count
Write-Host "    epics=$nEpics children=$nChildren orphans=$nOrphans"

# ── Paso 5: serializar (el gate del ciclo) ──────────────────────────────────
# Un 200 NO prueba que la estructura sea serializable rio abajo: el objeto ya viajo
# como texto. Volver a serializarlo con profundidad grande es lo que revienta si algo
# se contiene a si mismo.
Write-Paso 5 "serializar la respuesta (ConvertTo-Json -Depth 20)"
try {
  $null = $jer | ConvertTo-Json -Depth 20
} catch {
  Fallar 4 "la respuesta NO es serializable: $($_.Exception.Message)"
}
Write-Host "    serializa OK"

# ── Paso 6: la meta del operador ────────────────────────────────────────────
Write-Paso 6 "epics >= 1"
if ($nEpics -eq 0) {
  Fallar 5 ("epics == 0: el operador NO ve ninguna epica. Clasifica al menos una " +
            "desde la pantalla (los issues heredados no traen etiquetas) y volve a correr.")
}

# ── Paso 7: nada perdido, nada duplicado ────────────────────────────────────
Write-Paso 7 "conservacion: total y unicidad de (tracker_type, ado_id)"
$suma = $nEpics + $nChildren + $nOrphans
if ($suma -ne [int]$bd.total_bd) {
  Fallar 6 ("la respuesta trae $suma tickets y la BD tiene $($bd.total_bd) filas para el " +
            "proyecto (contando TODOS los trackers). Se perdio o se agrego algo.")
}
$vistos = @{}
$duplicados = @()
foreach ($t in ($epics + $children + $orphans)) {
  $tracker = "$($t.tracker_type)".ToLower()
  if (-not $tracker) { $tracker = "(sin tracker)" }
  $clave = "$tracker#$($t.ado_id)"
  if ($vistos.ContainsKey($clave)) { $duplicados += $clave } else { $vistos[$clave] = 1 }
}
if ($duplicados.Count -gt 0) {
  Fallar 6 ("hay pares (tracker_type, ado_id) repetidos en la union de las tres listas: " +
            (($duplicados | Select-Object -Unique) -join ", ") +
            ". El total puede cerrar igual: un duplicado compensa al que desaparecio.")
}
Write-Host "    $suma tickets, sin duplicados"

# ── Paso 8: la tabla final ──────────────────────────────────────────────────
Write-Paso 8 "resumen"
Write-Host ""
Write-Host "  epics    : $nEpics"
Write-Host "  children : $nChildren"
Write-Host "  orphans  : $nOrphans"
Write-Host "  total    : $suma  (BD: $($bd.total_bd))"
Write-Host ""
Write-Host "  por tracker_type (respuesta):"
($epics + $children + $orphans) | Group-Object { "$($_.tracker_type)" } |
  ForEach-Object { Write-Host "    $($_.Name): $($_.Count)" }
Write-Host ""
Write-Host "  huerfanos por motivo:"
if ($nOrphans -eq 0) {
  Write-Host "    (ninguno)"
} else {
  $orphans | Group-Object { "$($_.motivo_huerfano)" } |
    ForEach-Object { Write-Host "    $($_.Name): $($_.Count)" }
}
Write-Host ""
Write-Host "  epicas y sus hijos:"
foreach ($e in $epics) {
  Write-Host "    #$($e.ado_id) $($e.title)  [$(@($e.children).Count) hijos]"
  foreach ($h in @($e.children)) { Write-Host "        - #$($h.ado_id) $($h.title)" }
}
Write-Host ""
Write-Host "OK: el operador ve la jerarquia."
exit 0
