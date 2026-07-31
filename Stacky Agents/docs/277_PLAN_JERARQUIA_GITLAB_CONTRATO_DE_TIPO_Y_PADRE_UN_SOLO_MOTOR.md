**Estado:** v1 (SIN CRITICAR) · **Autor:** StackyArchitectaUltraEficientCode · **Fecha:** 2026-07-31
**Origen:** pedido del operador del 2026-07-31 — *"en ADO manejo una jerarquía que empieza en la épica «Violeta Lugo»; de ahí se desprenden las tareas y dentro de ellas los comentarios. Quiero replicar ese esquema en GitLab. Si no defino la jerarquía, todo termina siendo issues y no los puedo distinguir."*
**Advertencia sobre este header:** el campo `Estado:` **NO es evidencia**. Verificá con `git log --all --grep="plan-277"` y con los comandos de F0.
**Predecesor directo:** plan 276 (GitLab self-hosted de punta a punta), rama `docs/plan-276`, commit `57d678af`. Este plan **asume 276 implementado** y lo declara prerequisito duro medido en F0.

# Plan 277 — La jerarquía de GitLab deja de ser plana: un solo contrato de tipo y padre, que se escribe igual que se lee

## 1. Objetivo

Que un proyecto **GitLab** muestre la misma jerarquía que hoy solo existe en **Azure DevOps**: una **épica** (el caso real: *"Violeta Lugo"*), de la que cuelgan los tickets de **análisis funcional**, **análisis técnico** e **implementación**, cada uno con sus comentarios — y que esa jerarquía sea **legible, distinguible y estable** en el grafo, en el board y en la API.

Hoy no lo es, y no es un problema de configuración del operador: es que **el camino de lectura de GitLab no puede expresar la jerarquía**. Los dos campos de los que depende `GET /api/tickets/hierarchy` se leen de fuentes que en una instancia **self-hosted sin licencia Premium** están siempre vacías:

| Campo | De dónde sale hoy | Qué pasa en GitLab CE/Free |
|---|---|---|
| `parent_ado_id` | `body.get("epic", {})` → `iid`/`id` (`services/gitlab_provider.py:99-101`) | El objeto `epic` **solo existe con licencia Premium/Ultimate**. En CE la clave nunca viene ⇒ `parent = None` **siempre**. |
| `work_item_type` | única fuente: la label `type::<x>` (`services/gitlab_provider.py:102-111`) | Esa label **solo la escribe Stacky al crear** (`create_item`, `:314`). Los 1009 issues que ya viven en RIPLEY no la tienen ⇒ `"Issue"` **siempre**. |

Y `api/tickets.py:646-654` clasifica exactamente por esos dos campos:

```python
wi_type = (t.work_item_type or "").lower()
if wi_type == "epic":            epics.append(d)
elif t.parent_ado_id and t.parent_ado_id in ado_id_to_ticket:
                                 ado_id_to_ticket[t.parent_ado_id]["children"].append(d)
else:                            orphans.append(d)
```

Con las dos fuentes muertas, la tercera rama se lleva **el 100 %** de los tickets. **Eso es, literalmente, el síntoma que reporta el operador**: *"todos los elementos terminan siendo issues y no tengo forma clara de distinguirlos"*. No es una impresión: es el `else`.

Este plan define **un solo contrato** — dos prefijos de etiqueta, `type::` y `epic::` — con **un solo motor** que lo lee y lo escribe, y con **tres caminos de degradación explícitos y medidos** (Premium nativo / etiquetas / clasificación local), en vez de las cuatro implementaciones dispersas y divergentes que hay hoy.

### KPI / impacto esperado

Medible con los comandos de cada fase, sin telemetría nueva. Los valores "hoy" salen de F0, que se corre **antes** de tocar una línea.

| Métrica | Hoy (a medir en F0) | Objetivo |
|---|---|---|
| Tickets GitLab que caen en `orphans` en `GET /api/tickets/hierarchy` | **100 %** (por construcción: las 2 fuentes están vacías) | **≤ 100 % − (los que tengan contrato)**, y **0 %** para los clasificados |
| Épicas visibles en el grafo de un proyecto GitLab | **0** | **≥ 1** (*"Violeta Lugo"*) |
| Motores distintos que interpretan la etiqueta `type::` | **4** (`gitlab_provider.py:102-111`, `migrator_verify.py:69-77`, `migrator_epics.py:62`, `incident_context.py:239`) | **1** (`services/gitlab_hierarchy.py`) |
| Mecanismos capaces de expresar "este ticket es hijo de aquel" en GitLab CE | **0** (`epic` es Premium; el fallback de issue-links es **simétrico** y además silenciado) | **1**, direccional y verificable (`epic::<iid>`) |
| Rutas del write path que fallan en silencio al enlazar un padre | **1** (`gitlab_provider.py:167-168`, `except Exception: pass`) | **0** |
| Tipos de la etiqueta que sobreviven al parser de `migrator_verify` | Los que matchean `type::(\w+)` — **`type::user story` NO matchea** aunque `create_item:314` lo escribe así | **100 %** de los canónicos, normalizados |
| Vocabulario de fases compartido entre la jerarquía y los comentarios de fase del plan 77 | **0 %** (la jerarquía no tiene vocabulario) | **100 %** (`funcional`/`tecnico`/`implementacion`, las 3 claves ya vivas en `_ISSUE_PHASE_MARKERS`, `api/tickets.py:7088-7092`) |
| `RecursionError`/`Circular reference` alcanzable desde una etiqueta escrita a mano | **sí** (ver §5, riesgo R1) | **no** (guarda + test) |
| Épicas cerradas que dejan a sus hijos huérfanos | **todas** (el sync pide `state="open"`, `services/gitlab_sync.py`) | **0** (F6 trae los padres faltantes) |

**Flags nuevas: 4 — tres `default=True` y una `default=False`** con su categoría de excepción escrita (§3.5). Ninguna otra.

> **PREREQUISITO DURO.** Este plan **no funciona** sin el plan 276 implementado: sin `services/gitlab_sync.py` no hay filas de GitLab en la tabla `tickets` y no hay jerarquía que armar. F0 lo mide en un comando y **aborta** si falta. Además siguen aplicando los 6 prerequisitos de visibilidad de 276 F0.8, incluido `STACKY_GITLAB_ENABLED` (default de fábrica **`false`**, `config.py:1209-1210`).

---

## 2. Por qué ahora / gap que cierra

### 2.1 El plan 276 dejó el grafo poblado, pero plano

276 F5.1 agregó `work_item_type` a `_normalize_issue` con un comentario que dice exactamente por qué (`services/gitlab_provider.py:102-105`):

> *"el tipo sale de la label `type::<x>` que este mismo provider escribe al crear (`_type_label`). Sin esto el campo no se emitía, `api/tickets.py` clasificaba por `work_item_type == "epic"` y TODO caía en `orphans`."*

Ese arreglo es correcto **para los issues que Stacky creó**. Pero los 53 issues abiertos de RIPLEY (1009 totales) **no los creó Stacky**: los creó el migrador Mantis→GitLab del plan 217. Y 276 **no tocó el `parent`**, que sigue leyéndose de `body.get("epic")`. Resultado: 276 pobló la tabla y el grafo dejó de estar vacío — pero quedó **plano**. Este plan es la continuación natural y el operador la pidió el mismo día.

### 2.2 Ya existe media solución, escrita, y está desconectada

`services/migrator_epics.py` — plan 74 F3 — **ya resolvió conceptualmente el problema**, para el migrador y solo para el migrador:

```python
def _free_degrade_decision(reason: str) -> EpicDecision:
    return EpicDecision(
        strategy="free_degrade",
        item_type_for_create="issue",
        extra_labels=("type::epic",),      # <-- migrator_epics.py:62
        reason=reason,
    )
```

Es decir: **el repo ya decidió que en GitLab Free una épica es un issue con la etiqueta `type::epic`.** Lo que falta es (a) que esa decisión valga también para el **camino de lectura** y para el **camino de escritura del provider**, no solo para el migrador; (b) que exista el análogo para el **padre**, que hoy no tiene ninguna etiqueta; y (c) que haya **un solo lugar** donde esté escrita. Este plan no inventa una convención: **promueve la que ya está en el repo a contrato de primera clase**.

### 2.3 Cuatro motores, ya divergentes

| # | Dónde | Qué hace | Divergencia medida |
|---|---|---|---|
| 1 | `services/gitlab_provider.py:102-111` | `for etiqueta in labels: if startswith("type::") → split.capitalize()` | Toma **la primera** del array — y el orden de `labels` en la API de GitLab **no está garantizado**. |
| 2 | `services/migrator_verify.py:69-77` | `re.match(r"type::(\w+)", label)` → `.capitalize()` | `\w+` **no matchea espacios**: `type::user story` (que `create_item:314` escribe tal cual con `item.item_type="User Story"`) se pierde. |
| 3 | `services/migrator_epics.py:62` | escribe `("type::epic",)` | Único que **escribe** minúscula canónica. |
| 4 | `services/incident_context.py:239` | comparación por **substring**, con comentario propio explicando por qué | Un `type::epic` matchearía una búsqueda de `type::epi`. |

Cuatro lecturas del mismo dato, tres reglas distintas de normalización, cero tests que las comparen entre sí. Es el patrón de "dos motores de probe" que ya costó 8 planes en este mismo eje.

### 2.4 El write path **no puede** expresar un padre en CE

`services/gitlab_provider.py:145-168`, `_link_parent`, tiene dos caminos y **los dos fallan** en una instancia sin licencia:

```python
if self._epics_native and self._group:                     # requiere Premium/Ultimate
    ... POST /groups/{group}/epics/{parent}/issues
    except TrackerApiError as e:
        if e.status == 403: pass                           # degrada
# Fallback: issue-links
try:
    ... POST /projects/{proj}/issues/{child}/links
except Exception:
    pass                                                   # <-- :167-168, SILENCIO TOTAL
```

Dos defectos, los dos verificables leyendo el archivo:

1. **El fallback no es direccional.** Un *issue link* de GitLab CE es una relación `relates_to` **simétrica**: no dice quién es el padre. Los tipos direccionales (`blocks` / `is_blocked_by`) son de pago. Aunque el POST funcione, `_normalize_issue` **no tiene de dónde leer el padre**: no lo lee de `links` (nunca hace ese GET) y `body["epic"]` sigue vacío. **El enlace se escribe en un lugar que nadie lee.**
2. **`except Exception: pass`.** Si el POST falla —permisos, `link_type` no soportado, 404— el operador no se entera nunca. El comentario del propio código lo admite: *"silencioso — no bloquear la creación del issue"*.

Por eso este plan **no agrega una quinta pata de cableado**: cambia el mecanismo por uno que el read path pueda leer.

### 2.5 El vocabulario de las tres fases **ya existe** y nadie lo usó para la jerarquía

`api/tickets.py:7088-7100`:

```python
_ISSUE_PHASE_MARKERS = {
    "funcional":      "<!-- stacky:issue-phase:funcional -->",
    "tecnico":        "<!-- stacky:issue-phase:tecnico -->",
    "implementacion": "<!-- stacky:issue-phase:implementacion -->",
}
_AGENT_TYPE_TO_ISSUE_PHASE = {"functional": "funcional", "technical": "tecnico", "developer": "implementacion"}
```

Son **exactamente** las tres fases que pide el operador. El plan 77 las materializó como **comentarios idempotentes dentro de UN issue** ("Issue como épica de un solo ticket"). El operador pide lo **complementario**: que además puedan ser **tickets hermanos bajo una épica**, como en ADO. Este plan reusa ese vocabulario **carácter por carácter** — sin acentos, sin variantes — para que las dos formas hablen el mismo idioma y un ticket `type::funcional` sea reconocible por el mismo `agent_type` que ya publica su comentario de fase.

---

## 3. Principios y guardarraíles

### 3.1 Los rieles duros del producto (no negociables)

- **3 runtimes con paridad real.** Todo lo de este plan es HTTP + SQLAlchemy + funciones puras: **no hay una sola llamada a un modelo**. Codex CLI, Claude Code CLI y GitHub Copilot Pro se comportan **idénticamente**; se declara por fase y se fija con el test de F1.
- **Human-in-the-loop innegociable.** Nada clasifica solo y nada escribe solo en el GitLab del operador. El backfill de F5 **muestra el diff y espera confirmación**, y su flag nace OFF.
- **Mono-operador, sin auth real.** Cero RBAC, cero multiusuario.
- **Cero trabajo extra para el operador.** F1-F4, F6-F8 son invisibles o automáticas. La única acción nueva es **opcional** (clasificar a mano lo que GitLab no dice) y vive donde el operador ya está mirando.
- **No degradar.** Sin queries nuevas por ticket (todo sale del payload que el sync ya trae), sin llamadas HTTP extra salvo la de F6 (acotada y contada), backward-compatible con ADO byte a byte.
- **Reusar lo existente.** `type::epic` (migrador), `funcional`/`tecnico`/`implementacion` (plan 77), `_migrate_add_columns` (`db.py:269`), `FLAG_REGISTRY`, `workItemTypeColor.ts`. **Nada nuevo que ya exista.**

### 3.2 GitLab es el sistema de registro (regla de precedencia, declarada una vez)

> **Lo que dice GitLab gana. La clasificación local de Stacky solo llena el vacío, nunca discute.**

Precedencia para `work_item_type`, en este orden exacto y sin excepciones:

1. La etiqueta `type::<x>` del issue (**decisiva**).
2. El campo nativo `type` / `issue_type` del payload REST (**decisivo** para `task`, `incident`, `test_case`; `issue` **no** es decisivo — es el default de GitLab y no es una afirmación).
3. La clasificación local de Stacky (F4), si existe.
4. `"Issue"`.

Precedencia para el padre:

1. La etiqueta `epic::<iid>` (**la única que se escribe en `parent_ado_id`**).
2. Clasificación local de Stacky (F4).
3. `None`.

> **POR QUÉ EL `epic` NATIVO DE PREMIUM *NO* ENTRA EN `parent_ado_id` (decisión, no olvido).** El `iid` de una épica nativa vive en el **namespace del grupo**, no en el del proyecto. `parent_ado_id` se compara contra `Ticket.ado_id`, que para GitLab lleva el **`iid` del issue dentro del proyecto** (`services/gitlab_sync.py`, mapeo de 276 F5.2). Son dos numeraciones distintas: escribir un `epic.iid` ahí produce un padre **que nunca va a machear** —el ticket cae igual en `orphans`— con el agravante de que el dato equivocado **tapa la causa real**. Además, la épica nativa **no es un issue**, así que no está en la tabla `tickets` en absoluto. Por eso el `epic` nativo se **conserva y se expone** como `parent_native_epic_iid` (diagnóstico y deep-link, `epic_url` ya existe en `gitlab_provider.py:242`) y **no** se escribe en `parent_ado_id`. Sincronizar épicas de grupo es **fuera de scope** (§7).

### 3.3 El contrato, escrito una sola vez

```
type::<tipo>     en el ITEM        →  qué es este ticket
epic::<iid>      en el HIJO        →  de qué ticket cuelga (iid del issue padre, dentro del mismo proyecto)
```

**Tipos canónicos** (token de etiqueta → valor guardado en `Ticket.work_item_type`, `String(40)`):

| Etiqueta | `work_item_type` | Rótulo en la UI | De dónde sale el nombre |
|---|---|---|---|
| `type::epic` | `Epic` | Épica | `migrator_epics.py:62` (ya se escribe así) |
| `type::funcional` | `Funcional` | Análisis Funcional | `_ISSUE_PHASE_MARKERS`, `api/tickets.py:7089` |
| `type::tecnico` | `Tecnico` | Análisis Técnico | `_ISSUE_PHASE_MARKERS`, `api/tickets.py:7090` |
| `type::implementacion` | `Implementacion` | Implementación | `_ISSUE_PHASE_MARKERS`, `api/tickets.py:7091` |
| `type::bug` | `Bug` | Bug | `workItemTypeColor.ts:13` |
| `type::task` | `Task` | Task | `workItemTypeColor.ts:12` |
| `type::feature` | `Feature` | Feature | `workItemTypeColor.ts:14` |
| `type::issue` | `Issue` | Issue | default |

**Cinco reglas de forma, obligatorias** (cada una tiene su test en F1):

1. **Los tokens son ASCII, minúscula, sin espacios ni acentos.** `implementacion`, no `implementación`. Motivo medido: `migrator_verify.py:70` usa `type::(\w+)`, que no matchea espacios, y `create_item` (`:314`) hoy escribe `type::User Story` con espacio y mayúsculas. La normalización se centraliza en F1 y **el write path pasa por ella**.
2. **Un solo `type::` por issue decide.** Si hay más de uno, gana el **primero en orden alfabético** de los canónicos presentes, y se registra un warning con los dos valores. Nunca "el primero del array": el orden de `labels` que devuelve la API de GitLab **no está garantizado** y hoy `gitlab_provider.py:106-110` depende de él, lo que hace la clasificación **no determinista entre corridas**.
3. **`::` no implica *scoped label*.** Las scoped labels (exclusión mutua automática) son **Premium**. En CE `type::epic` es una etiqueta común cuyo nombre contiene `::`. **El contrato no depende de la exclusión mutua** — por eso existe la regla 2. En Premium, además, se obtiene gratis.
4. **`epic::<iid>` lleva el `iid`, nunca el título.** El `iid` es inmutable; el título no (*"Violeta Lugo"* se puede renombrar y la jerarquía debe sobrevivir).
5. **Un valor de `type::` desconocido no se descarta**: se normaliza (`strip().lower()`) y se guarda capitalizado, truncado a 40 caracteres. Perder el dato del operador está prohibido.

### 3.4 Reglas antifalso-verde de este plan

- **Cero mocks del propio contrato.** Los tests de F1 corren contra `gitlab_hierarchy.py` real. Los de F2 arman payloads con la **forma literal de la API de GitLab** (`{"id","iid","labels":[...],"epic":{...},"type":...}`), no diccionarios inventados.
- **Todo test de "no está" guarda primero.** Un `assert x not in y` que nunca vio `x` guardado pasa por accidente. Los tests de precedencia **siembran el caso contrario** y verifican que fue desplazado.
- **Los gates de conteo corren dos veces.** Idempotencia real, no `created == 0` (que también pasa si el sync se rompió).
- **`pytest -k` sin match da exit 0.** Todos los comandos de este plan son **por archivo** y declaran el número exacto de casos esperados.

### 3.5 Las 4 flags nuevas, con su default y su justificación

| Flag | Default | Por qué |
|---|---|---|
| `STACKY_GITLAB_HIERARCHY_CONTRACT_ENABLED` | **True** | Parsear etiquetas que **ya existen** en el payload. Solo-lectura respecto de GitLab; el resultado se escribe en la BD de Stacky. No cae en (A) —cero llamadas a modelo, cero polling— ni en (B). |
| `STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED` | **True** | Guarda la clasificación **en la BD de Stacky** (columnas nuevas de `tickets`). **No toca el GitLab del operador.** On-demand, disparada por el operador desde la UI. No cae en (A) ni en (B): (B) exige escribir en un sistema **del operador** o sacarle la decisión, y acá el operador **es** quien decide, ítem por ítem. Precedente idéntico: `STACKY_GITLAB_SYNC_ENABLED` (`harness_flags.py:5509-5511`), que también escribe en la BD de Stacky y nace ON. |
| `STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED` | **False** | **Excepción (B): escribe en un sistema REAL del operador.** Hace `PUT /projects/:id/issues/:iid` con `add_labels` contra el GitLab de la empresa (`services/gitlab_provider.py` usa ese mismo verbo en `:305-309`), modificando issues que Stacky no creó. Precedente exacto de partición: `STACKY_PIPELINE_NL_EDIT_ENABLED` (ON, planea/diffea) vs `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` (OFF, escribe). Acá la parte inocua es F4 (clasificar local, ON) y la que escribe es F5 (OFF). |
| `STACKY_GITLAB_SYNC_PARENTS_ENABLED` | **True** | Un `GET` extra y acotado por los padres referenciados que no vinieron en el listado de abiertos (típicamente épicas cerradas). Solo-lectura sobre GitLab, escribe en la BD de Stacky, **on-demand** dentro del sync que el operador ya disparó, con tope duro de ítems. No cae en (A) —no es polling ni barrido: solo pide los `iid` que las etiquetas ya nombraron— ni en (B). |

---

## 4. Fases

> **Python del venv (comando base, reusado en TODAS las fases backend).** Se corre desde `Stacky Agents\backend`:
> ```powershell
> $PY = "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe"
> ```
> **Con punto.** Hay **dos** venvs (`backend\.venv` py3.13.5 y `backend\venv` py3.11.9) y los dos importan; este plan usa `.venv`. Control: `& $PY --version` debe decir **3.13.5**.
> Frontend: desde `Stacky Agents\frontend`, `npx vitest run <archivo>`. **No hay RTL/jsdom instalados**: toda lógica de UI verificable va en `.ts` puro y lo visual se cubre con smoke manual declarado paso a paso.

---

### F0 — Línea base: probar que hoy TODO cae en `orphans`

**Objetivo:** medir el "antes" con números, y abortar temprano si falta un prerequisito. **Valor:** sin esto, cualquier mejora posterior es una afirmación sin contraste — y el gate de F8 no tendría contra qué comparar.

**Archivos a crear:** ninguno (F0 no modifica código).
**Archivos a editar:** ninguno.

**Paso 1 — Prerequisito duro: el plan 276 está implementado.**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
$PY = ".\.venv\Scripts\python.exe"
& $PY -c "import services.gitlab_sync as m; print('OK 276:', m.sync_gitlab_tickets.__name__)"
```
**Si esto falla, el plan 277 se detiene acá.** Sin `gitlab_sync` no hay filas de GitLab en `tickets` y no hay jerarquía posible. Remedio: implementar el plan 276 (rama `docs/plan-276`, commit `57d678af`).

**Paso 2 — Los 6 prerequisitos de visibilidad de 276 F0.8.** Correr el preflight de ese plan tal cual. **Debe pasar los 6**, en particular `STACKY_GITLAB_ENABLED=true` (default de fábrica `false`, `config.py:1209-1210`).

**Paso 3 — Censo de los 4 motores de `type::` (el número del KPI).**
```powershell
Select-String -Path services\gitlab_provider.py,services\migrator_verify.py,services\migrator_epics.py,services\incident_context.py -Pattern 'type::' | Measure-Object | Select-Object -ExpandProperty Count
```
Anotar el número. **Se espera ≥ 4 archivos distintos.** Al terminar F2 el único que **interpreta** debe ser `gitlab_hierarchy.py`.

**Paso 4 — La foto del defecto: 100 % huérfanos.** Con el backend levantado y el proyecto GitLab sincronizado:
```powershell
$r = Invoke-RestMethod "http://localhost:5000/api/tickets/hierarchy?project=RIPLEY"
"epics={0}  orphans={1}  children={2}" -f $r.epics.Count, $r.orphans.Count, (($r.epics | ForEach-Object { $_.children.Count } | Measure-Object -Sum).Sum)
```
**Se espera `epics=0`, `children=0`, `orphans=N>0`.** Guardar la salida literal en el commit de F0 como el "antes". Si `orphans=0` también, el prerequisito del paso 1/2 no se cumplió de verdad: volver al paso 2.

**Paso 5 — Qué edición es la instancia (decide si el camino nativo existe).** Con el token del operador:
```powershell
# 200 => épicas nativas disponibles (Premium/Ultimate) | 403 => sin licencia | 404 => el grupo no existe
curl.exe -s -o NUL -w "%{http_code}`n" -H "PRIVATE-TOKEN: $env:GITLAB_TOKEN" `
  "https://srvcgit01.imsolutions.local/api/v4/groups/<GRUPO>/epics"
```
Anotar el código. **Es el mismo criterio que ya usa `_link_parent` (`gitlab_provider.py:158-160`, degrada en 403)**, así que no se inventa una detección nueva. Con 403/404 el camino que sirve es el de etiquetas (F1-F3) y el nativo queda como diagnóstico (§3.2).

**Paso 6 — Cuántos issues traen ya alguna etiqueta del contrato.** Decide cuánto trabajo real hace F4/F5:
```powershell
& $PY - <<'PY'
import os, requests
tok = os.environ["GITLAB_TOKEN"]; base = "https://srvcgit01.imsolutions.local/api/v4"
proj = requests.utils.quote("<GRUPO>/<PROYECTO>", safe="")
s = requests.Session(); s.headers["PRIVATE-TOKEN"] = tok
r = s.get(f"{base}/projects/{proj}/issues", params={"state": "opened", "per_page": 100}, verify=os.environ.get("STACKY_CA_BUNDLE", True))
issues = r.json()
con_tipo   = [i for i in issues if any(str(l).lower().startswith("type::") for l in (i.get("labels") or []))]
con_padre  = [i for i in issues if any(str(l).lower().startswith("epic::") for l in (i.get("labels") or []))]
con_nativo = [i for i in issues if i.get("epic")]
print(f"abiertos={len(issues)}  con type::={len(con_tipo)}  con epic::={len(con_padre)}  con epic nativo={len(con_nativo)}")
PY
```
**Se espera `con type::=0  con epic::=0  con epic nativo=0`** en RIPLEY (los issues los creó el migrador del plan 217, no Stacky). Ese cero **es la justificación de F4**: sin clasificación local, el contrato no tiene de dónde leer nada y el plan no le cambia nada al operador.

**Criterio de aceptación (binario):** los 6 pasos corridos, con las salidas pegadas en el commit de F0. El paso 4 **debe** mostrar `epics=0` y `children=0`; si muestra otra cosa, el "antes" de este plan es distinto al que asume y hay que re-leer §1 antes de seguir.
**Flag:** ninguna (F0 no cambia comportamiento).
**Impacto por runtime:** ninguno — F0 es medición. **Trabajo del operador: ninguno** (lo corre el implementador).

---

### F1 — El contrato, en un solo módulo, con funciones puras

**Objetivo:** una única fuente de verdad para escribir y leer `type::` y `epic::`. **Valor:** mata la divergencia de 4 motores antes de agregar el quinto.

**Archivos a crear:** `Stacky Agents/backend/services/gitlab_hierarchy.py`, `Stacky Agents/backend/tests/test_plan277_contrato_jerarquia.py`
**Archivos a editar:** ninguno todavía (F2 y F3 lo consumen).

**Símbolos EXACTOS que crea el módulo** (nombres literales, no equivalentes):

```python
"""services/gitlab_hierarchy.py — Plan 277 F1. El contrato de jerarquía de GitLab.

UN SOLO MOTOR. Antes de este módulo había CUATRO lecturas de `type::` con tres
reglas de normalización distintas y cero tests que las compararan:
  - services/gitlab_provider.py:102-111   (primer label del array; orden NO garantizado)
  - services/migrator_verify.py:69-77     (regex type::(\\w+); pierde `type::user story`)
  - services/migrator_epics.py:62         (escribe "type::epic")
  - services/incident_context.py:239      (comparación por substring)

FUNCIONES PURAS. Este módulo NO hace I/O: ni HTTP, ni BD, ni lectura de config.
Es la condición que hace que su test corra igual en los 3 runtimes y en CI sin red.
"""
from __future__ import annotations

PREFIJO_TIPO: str = "type::"
PREFIJO_PADRE: str = "epic::"

# token de etiqueta -> valor de Ticket.work_item_type (String(40))
TIPOS_CANONICOS: dict[str, str] = {
    "epic":           "Epic",
    "funcional":      "Funcional",
    "tecnico":        "Tecnico",
    "implementacion": "Implementacion",
    "bug":            "Bug",
    "task":           "Task",
    "feature":        "Feature",
    "issue":          "Issue",
}

# campo nativo REST `type`/`issue_type` (GitLab >= 15.2, disponible en Free)
# -> work_item_type. `issue` NO está: es el default de GitLab y no es una afirmación.
TIPOS_NATIVOS: dict[str, str] = {
    "task":      "Task",
    "incident":  "Bug",
    "test_case": "Task",
}

TIPO_POR_DEFECTO: str = "Issue"
_MAX_TIPO: int = 40          # Ticket.work_item_type es String(40) — models.py:55


def normalizar_token(valor: str | None) -> str:
    """'  Implementación ' -> 'implementacion'. ASCII, minúscula, sin espacios.

    Regla 1 del contrato (§3.3): los tokens no llevan acentos ni espacios porque
    `migrator_verify.py:70` los parsea con `type::(\\w+)`, que no matchea espacios,
    y porque `create_item` (gitlab_provider.py:314) hoy escribe el item_type crudo.
    Espacios y guiones colapsan a '_'; los acentos se pliegan a ASCII vía NFKD.
    """


def etiqueta_de_tipo(work_item_type: str | None) -> str:
    """'Análisis Funcional' -> 'type::analisis_funcional'. Nunca devuelve vacío."""


def etiqueta_de_padre(parent_iid: int | str) -> str:
    """123 -> 'epic::123'. Levanta ValueError si no es un entero positivo.

    Regla 4 del contrato: va el iid, NUNCA el título. El título se renombra;
    el iid no.
    """


def tipo_desde_labels(labels: list[str] | str | None) -> str | None:
    """Devuelve el work_item_type según la etiqueta `type::`, o None si no hay.

    DETERMINISTA (regla 2 del contrato): si hay MÁS DE UNA etiqueta `type::`,
    gana la primera en ORDEN ALFABÉTICO del token — nunca "la primera del array",
    porque el orden de `labels` que devuelve la API de GitLab no está garantizado
    y hace la clasificación distinta entre dos corridas idénticas.

    Acepta list[str] o el string separado por comas (el migrador lo pasa así,
    migrator_verify.py:46-47). Un token fuera de TIPOS_CANONICOS NO se descarta:
    se devuelve capitalizado y truncado a 40 (regla 5).
    """


def padre_desde_labels(labels: list[str] | str | None) -> int | None:
    """Devuelve el iid del padre según `epic::<iid>`, o None.

    Si hay más de una, gana el iid MENOR (determinismo, mismo motivo que arriba)
    y se deja constancia en el warning del llamador. Un valor no entero o <= 0
    se ignora (devuelve None) en vez de reventar.
    """


def clasificar_issue(body: dict) -> dict:
    """El payload crudo de un issue de GitLab -> el veredicto del contrato.

    Returns:
        {
          "work_item_type": str,                  # nunca vacío; TIPO_POR_DEFECTO si no hay señal
          "parent_iid": int | None,               # SOLO de la etiqueta epic:: (ver §3.2)
          "parent_native_epic_iid": int | None,   # del `epic` de Premium; NO va a parent_ado_id
          "origen_tipo": str,                     # "label" | "nativo" | "defecto"
          "origen_padre": str,                    # "label" | "ninguno"
          "avisos": list[str],                    # multi-tipo, multi-padre, token desconocido
        }

    PRECEDENCIA (§3.2), sin excepciones:
      tipo:  etiqueta type::  >  campo nativo type/issue_type  >  TIPO_POR_DEFECTO
      padre: etiqueta epic::  >  None
    El `epic` nativo NO entra en parent_iid: su iid vive en el namespace del GRUPO
    y parent_ado_id se compara contra Ticket.ado_id, que lleva el iid del issue
    dentro del PROYECTO. Escribirlo ahí produce un padre que nunca machea y tapa
    la causa real. Se conserva aparte para diagnóstico y deep-link (epic_url).
    """
```

**Casos borde que el módulo debe manejar sin reventar** (cada uno tiene test):
`labels=None`; `labels=[]`; `labels=""`; `labels` como string con comas y espacios; `type::` sin valor; `epic::` sin valor; `epic::abc`; `epic::-3`; `epic::0`; `type::` con mayúsculas (`TYPE::EPIC`); dos `type::`; dos `epic::`; token de 200 caracteres; `body={}`; `body={"epic": None}`; `body={"epic": {}}`; `body={"type": "TASK"}`.

**Tests PRIMERO — `tests/test_plan277_contrato_jerarquia.py`, 24 casos:**

| # | Caso | Qué defecto mata |
|---|---|---|
| 1-3 | `normalizar_token`: `"Implementación"`→`"implementacion"`, `"User Story"`→`"user_story"`, `"  EPIC "`→`"epic"` | El espacio de `create_item:314` y el acento que rompe `\w+` |
| 4-5 | `etiqueta_de_tipo("Epic") == "type::epic"`; `etiqueta_de_tipo(None)` no devuelve `"type::"` pelado | Etiqueta vacía escrita en GitLab |
| 6-7 | `etiqueta_de_padre(123) == "epic::123"`; `etiqueta_de_padre("abc")` levanta `ValueError` | Etiqueta de padre corrupta |
| 8-11 | `tipo_desde_labels`: los 8 canónicos; `None`/`[]`/`""` → `None`; string con comas → funciona | Las 3 normalizaciones divergentes |
| **12** | **Dos `type::` (`["type::tecnico","type::epic"]`) → `"Epic"` (alfabético), y `avisos` tiene 1 entrada** | El no-determinismo de `gitlab_provider.py:106-110`. **Correr el mismo test con la lista invertida y exigir el MISMO resultado** — ese es el gate: si alguien vuelve a "la primera del array", una de las dos órdenes falla. |
| 13 | `type::user story` (con espacio, tal como lo escribe hoy `create_item:314`) → **no se pierde** | El agujero de `type::(\w+)` en `migrator_verify.py:70` |
| 14 | Token desconocido `type::spike` → `"Spike"`, no `"Issue"` | Regla 5: no perder el dato del operador |
| 15 | Token de 200 chars → guardado truncado a **40** sin excepción | `String(40)` en `models.py:55` |
| 16-18 | `padre_desde_labels`: `epic::123`→`123`; `epic::abc`/`epic::-3`/`epic::0`→`None`; dos `epic::` → el menor + aviso | Padre corrupto que revienta el `int()` del sync |
| 19 | `clasificar_issue` con `labels=["type::epic"]` y `epic={"iid":9}` → `work_item_type="Epic"`, `parent_iid=None`, `parent_native_epic_iid=9` | **El §3.2**: el epic nativo NO contamina `parent_ado_id` |
| 20 | `clasificar_issue` con `labels=["type::funcional","epic::42"]` → `("Funcional", 42, "label", "label")` | El camino feliz del contrato |
| 21 | `clasificar_issue` con `body={"type":"task"}` sin labels → `"Task"`, `origen_tipo="nativo"` | La señal nativa gratis de GitLab ≥15.2 |
| 22 | `clasificar_issue` con `body={"type":"issue"}` sin labels → `"Issue"`, `origen_tipo="defecto"` (**no** `"nativo"`) | `issue` es el default de GitLab, no una afirmación |
| **23** | **Precedencia: `labels=["type::epic"]` Y `body["type"]="task"` → `"Epic"`** (la etiqueta gana) — y el caso **inverso sembrado**: sin la etiqueta, el mismo body da `"Task"` | Un assert de precedencia que nunca vio el caso contrario pasa por accidente |
| 24 | `clasificar_issue({})` y `clasificar_issue({"epic": None})` no levantan y devuelven el defecto | Payload parcial de la API |

**Comando:**
```powershell
& $PY -m pytest tests\test_plan277_contrato_jerarquia.py -q
```
**Criterio de aceptación (binario):** **24 passed**, y
```powershell
& $PY -c "import services.gitlab_hierarchy as m, inspect; src=inspect.getsource(m); assert 'requests' not in src and 'session_scope' not in src and 'import config' not in src; print('PURO OK')"
```
imprime `PURO OK` (el módulo no hace I/O; es lo que garantiza la paridad de runtimes).

**Ratchet:** registrar `tests/test_plan277_contrato_jerarquia.py` en **los dos** scripts (`backend/scripts/run_harness_tests.ps1` **y** `.sh` — divergen y el meta-test parsea solo el `.sh`).
**Flag:** ninguna (módulo puro, sin consumidores todavía).
**Impacto por runtime:** idéntico en los 3 — funciones puras, sin I/O, sin modelo. **Fallback:** no aplica.
**Trabajo del operador: ninguno.**

---

### F2 — El read path consume el contrato (y los 4 motores pasan a ser 1)

**Objetivo:** que `_normalize_issue` clasifique con `gitlab_hierarchy` y que los otros 3 motores dejen de tener regla propia. **Valor:** el ticket empieza a saber qué es y de quién cuelga.

**Archivos a editar:** `Stacky Agents/backend/services/gitlab_provider.py`, `Stacky Agents/backend/services/migrator_verify.py`, `Stacky Agents/backend/services/incident_context.py`, `Stacky Agents/backend/services/gitlab_sync.py`
**Archivos a crear:** `Stacky Agents/backend/tests/test_plan277_read_path.py`

**Diff 1 — `services/gitlab_provider.py:95-116`** (reemplaza el bloque del plan 276 F5.1):

```diff
 def _normalize_issue(self, body: dict) -> dict:
     assignees = body.get("assignees") or []
     assignee_names = [a.get("username") for a in assignees if a.get("username")]
     labels = body.get("labels") or []
-    # parent: si tiene epic_iid (GitLab Premium) o _link_parent_id inyectado
-    parent = body.get("epic", {}) or {}
-    parent_id = str(parent.get("iid") or parent.get("id") or "") or None
-    tipo = "Issue"
-    for etiqueta in labels:
-        if isinstance(etiqueta, str) and etiqueta.lower().startswith("type::"):
-            tipo = etiqueta.split("::", 1)[1].strip().capitalize() or "Issue"
-            break
+    # Plan 277 F2 — la clasificación sale del contrato, no de este archivo.
+    # Lo de antes tenía dos defectos medidos: (1) el `epic` de Premium NUNCA
+    # viene en CE ⇒ parent_id siempre None ⇒ todo caía en `orphans`
+    # (api/tickets.py:646-654); (2) "la primera etiqueta del array" es NO
+    # DETERMINISTA — el orden de `labels` de la API no está garantizado.
+    from services.gitlab_hierarchy import clasificar_issue   # import local: evita ciclo
+    veredicto = clasificar_issue(body)
+    for aviso in veredicto["avisos"]:
+        logger.warning("Plan 277 contrato (issue iid=%s): %s", body.get("iid"), aviso)
     return {
         ...
-        "work_item_type": tipo,
-        "parent": parent_id,
+        "work_item_type": veredicto["work_item_type"],
+        "parent": veredicto["parent_iid"],                     # int | None (antes: str | None)
+        "parent_native_epic_iid": veredicto["parent_native_epic_iid"],
+        "origen_tipo": veredicto["origen_tipo"],
+        "origen_padre": veredicto["origen_padre"],
     }
```

> **CAMBIO DE TIPO, DECLARADO.** `parent` pasa de `str | None` a `int | None`. El único consumidor es `services/gitlab_sync.py`, que hace `_a_int(item.get("parent"))` — y `_a_int` acepta ambos (`int(str(valor).strip())`). **No requiere cambio ahí**, pero sí un test que lo fije (caso 8 de abajo), porque si mañana alguien saca el `_a_int` el `None` explota.
> **`logger` en `gitlab_provider.py`:** el módulo **no tiene** `logger` hoy. Agregar `import logging` y `logger = logging.getLogger(__name__)` al head, junto a los imports existentes (`:19-25`). Es la única línea nueva de infraestructura del archivo.

**Diff 2 — `services/migrator_verify.py:69-77`**: `_infer_type_from_labels` deja de tener regex propia y delega. Se **conserva el nombre de la función** (tiene llamadores en `:48`) y se le cambia solo el cuerpo:

```diff
-def _infer_type_from_labels(labels: list[str]) -> str | None:
-    """Extrae el tipo del label type::X."""
-    for label in labels:
-        m = _TYPE_LABEL_RE.match(label.strip())
-        if m:
-            t = m.group(1)
-            return t.capitalize() if t else None
-    return None
+def _infer_type_from_labels(labels: list[str]) -> str | None:
+    """Extrae el tipo del label type::X. Plan 277 F2: delega en el contrato.
+
+    La regex propia (`type::(\\w+)`) perdía `type::user story` — exactamente lo
+    que `gitlab_provider.create_item:314` escribe cuando el item_type tiene
+    espacio. Y capitalizaba distinto que el provider. Un solo motor.
+    """
+    from services.gitlab_hierarchy import tipo_desde_labels
+    return tipo_desde_labels(labels)
```
Y se **borra** `_TYPE_LABEL_RE` (`:14`) si no queda otro uso (verificar con `Select-String -Path services\migrator_verify.py -Pattern '_TYPE_LABEL_RE'` ⇒ debe dar **0** tras el cambio).

**Diff 3 — `services/incident_context.py:239`**: la comparación por substring pasa a usar `PREFIJO_TIPO` del contrato en vez del literal `"type::"`. Cambio mínimo: importar la constante y usarla. **No se cambia la semántica de substring** (el comentario de ese archivo explica por qué es substring); solo deja de tener el literal duplicado.

**Diff 4 — `services/gitlab_sync.py`**: agregar el guard de la flag y persistir el origen. En el bucle, después de `tipo = item.get("work_item_type") or "Issue"`:

```diff
+            # Plan 277 F2 — con el contrato apagado el sync se comporta EXACTO
+            # como en 276: sin padre por etiqueta. No se rompe nada.
+            if not bool(getattr(config.config, "STACKY_GITLAB_HIERARCHY_CONTRACT_ENABLED", True)):
+                parent_ado_id = None
+            else:
+                parent_ado_id = _a_int(item.get("parent"))
-            parent_ado_id = _a_int(item.get("parent"))
```
(`gitlab_sync.py` **no importa `config` hoy**: agregar `import config` al head, con el comentario `# importado a nivel módulo para poder parchear en tests`, igual que `gitlab_provider.py:25`.)

**Tests PRIMERO — `tests/test_plan277_read_path.py`, 12 casos:**

| # | Caso | Gate |
|---|---|---|
| 1 | Payload CE real (sin `epic`, con `labels=["type::epic"]`) → `work_item_type="Epic"`, `parent=None` | El caso de la épica *"Violeta Lugo"* |
| 2 | Payload CE con `["type::funcional","epic::42"]` → `("Funcional", 42)` | El caso de un hijo |
| 3 | Payload **sin ninguna etiqueta** (el estado real de los 53 issues de RIPLEY, medido en F0 paso 6) → `("Issue", None)` | Backward-compat: nada empeora |
| 4 | Payload Premium con `epic={"iid":9}` y sin `epic::` → `parent=None` **y** `parent_native_epic_iid=9` | §3.2 — el nativo no contamina |
| 5 | `["type::tecnico","type::epic"]` y su **inverso** dan el mismo `work_item_type` | El determinismo (gate de `gitlab_provider.py:106-110`) |
| 6 | Un aviso del contrato **llega al log** (`caplog`) con el `iid` del issue | Que el multi-tipo no sea silencioso |
| 7 | `_infer_type_from_labels(["type::user story"])` **no devuelve `None`** | El agujero de `\w+`; **sembrar primero** el caso `["type::epic"]` que sí funcionaba, para que el test distinga "arreglado" de "roto de otra forma" |
| 8 | `sync_gitlab_tickets` con `parent` **int** escribe `parent_ado_id` int; con `parent=None` escribe `None` | El cambio de tipo `str`→`int` |
| 9 | Con `STACKY_GITLAB_HIERARCHY_CONTRACT_ENABLED=False` el sync escribe `parent_ado_id=None` **aunque la etiqueta esté** | Que la flag sea un kill-switch **real**, no una flag registrada pero muerta |
| 10 | Con la flag en `False`, `work_item_type` **sigue** saliendo del contrato | La flag gatea el **padre**, no el tipo (el tipo ya existía en 276 y apagarlo sería una regresión) |
| 11 | `Select-String` sobre `migrator_verify.py` con patrón `_TYPE_LABEL_RE` da **0** | La regex vieja se borró de verdad |
| 12 | Un proyecto **ADO** pasa por `sync_tickets` sin tocar ninguna línea nueva (monkeypatchear `clasificar_issue` y afirmar que **no** se llamó) | Backward-compat de ADO, byte-idéntico |

**Comando:**
```powershell
& $PY -m pytest tests\test_plan277_read_path.py -q                       # 12 passed
& $PY -m pytest tests\test_plan276_gitlab_sync.py -q                     # 16 passed, sin regresión
& $PY -m pytest tests\test_plan276_hierarchy_gitlab.py -q                # 5 passed, sin regresión
& $PY -m pytest tests\test_plan74_migrator_verify.py -q                  # sin regresión — F2 le cambia el CUERPO a
                                                                          # _infer_type_from_labels, que este archivo cubre.
                                                                          # Verificado que existe; anotar el conteo previo.
```
**Criterio de aceptación (binario):** 12 + 16 + 5 passed, y el censo del paso 3 de F0 baja: `Select-String -Path services\migrator_verify.py -Pattern 'type::\(' ` en **0 coincidencias**.

**Ratchet:** registrar `tests/test_plan277_read_path.py` en los dos scripts.
**Flag:** `STACKY_GITLAB_HIERARCHY_CONTRACT_ENABLED`, **default True** (§3.5).
**Impacto por runtime:** idéntico en los 3 — parseo de strings + SQLAlchemy. **Fallback:** con la flag OFF, comportamiento **idéntico al plan 276** (sin padre por etiqueta), no una degradación nueva.
**Trabajo del operador: ninguno.**

---

### F3 — El write path escribe lo que el read path sabe leer

**Objetivo:** que cuando **Stacky** cree un hijo, escriba `epic::<iid>` (y un `type::` normalizado), y que el enlace deje de fallar en silencio. **Valor:** cierra el lazo — lo que Stacky escribe, Stacky lo vuelve a leer.

**Archivos a editar:** `Stacky Agents/backend/services/gitlab_provider.py`
**Archivos a crear:** `Stacky Agents/backend/tests/test_plan277_write_path.py`

**Diff 1 — `_type_label` (`:76-77`) pasa por el contrato:**
```diff
 def _type_label(self, item_type: str) -> str:
-    return f"type::{item_type}"
+    # Plan 277 F3 — antes escribía el item_type CRUDO: `type::User Story`, con
+    # espacio y mayúsculas. Eso lo perdía el parser del migrador
+    # (migrator_verify.py:70, `type::(\w+)`) y no matcheaba el canónico.
+    from services.gitlab_hierarchy import etiqueta_de_tipo
+    return etiqueta_de_tipo(item_type)
```

**Diff 2 — `_link_parent` (`:145-168`) escribe la etiqueta y deja de ser mudo:**
```diff
 def _link_parent(self, child_iid: str, parent_id: str) -> None:
-    """Establece la relación padre-hijo (F7): epics nativos o issue-links."""
+    """Establece la relación padre-hijo. Plan 277 F3: la etiqueta es el mecanismo
+    PRIMARIO; el epic nativo queda como camino Premium; los issue-links se retiran.
+
+    POR QUÉ SE RETIRAN LOS ISSUE-LINKS: un link de GitLab CE es `relates_to`,
+    SIMÉTRICO — no dice quién es el padre — y `_normalize_issue` nunca los lee
+    (jamás hace GET /links). Se estaba escribiendo en un lugar que nadie lee, y
+    el POST estaba envuelto en `except Exception: pass`, así que su fallo era
+    invisible. La etiqueta `epic::<iid>` es direccional, viaja en el mismo
+    payload que el listado ya trae (cero requests extra al leer) y es visible y
+    filtrable en la UI de GitLab.
+    """
     proj_path = self._client._project_path()
     if self._epics_native and self._group:
-        try: ... POST /groups/{group}/epics/{parent}/issues ; return
-        except TrackerApiError as e:
-            if e.status == 403: pass
-            else: raise
+        try:
+            ... POST /groups/{self._group}/epics/{parent_id}/issues ...
+            return
+        except TrackerApiError as e:
+            if e.status != 403:
+                raise
+            logger.info("Plan 277: épicas nativas rechazadas (403) — degradando a etiqueta epic::")
-    # Fallback: issue-links (siempre disponible)
-    try:
-        ... POST /projects/{proj}/issues/{child}/links ...
-    except Exception:
-        pass  # silencioso — no bloquear la creación del issue
+    # Camino primario en CE: la etiqueta.
+    from services.gitlab_hierarchy import etiqueta_de_padre
+    try:
+        etiqueta = etiqueta_de_padre(parent_id)          # ValueError si parent_id no es iid
+    except ValueError:
+        logger.warning("Plan 277: parent_id %r no es un iid válido; el hijo %s queda huérfano.",
+                       parent_id, child_iid)
+        return
+    try:
+        self._client._request(
+            "PUT",
+            f"/projects/{proj_path}/issues/{child_iid}",
+            json_body={"add_labels": etiqueta},
+        )
+    except Exception as exc:
+        # v277: NO se traga. Antes era `pass` mudo y el operador nunca sabía que
+        # la jerarquía no se había escrito. Se registra y se re-lanza envuelto:
+        # quien crea el item decide si el hijo huérfano es aceptable.
+        logger.error("Plan 277: no se pudo etiquetar el padre de %s: %s", child_iid, exc)
+        raise TrackerApiError(
+            f"El issue {child_iid} se creó pero no se pudo enlazar a su padre "
+            f"{parent_id} (etiqueta {etiqueta}): {exc}"
+        ) from exc
```

> **DECISIÓN EXPLÍCITA sobre el re-lanzado.** `_link_parent` se llama **después** de crear el issue (`create_item:334`). Si ahora levanta, el issue **ya existe** en GitLab y la excepción sale hacia el llamador. Eso es **intencional y es lo correcto**: un hijo sin padre es un dato incompleto y el operador tiene que enterarse. Pero para que no rompa flujos existentes, `create_item` **captura y anota**, no propaga:
> ```diff
>      if item.parent_id:
> -        self._link_parent(str(body.get("iid") or body.get("id") or ""), item.parent_id)
> +        try:
> +            self._link_parent(str(body.get("iid") or body.get("id") or ""), item.parent_id)
> +        except TrackerApiError as exc:
> +            # El issue YA existe: no se puede deshacer ni se debe. Se devuelve
> +            # creado pero con la falla visible, en vez del silencio de antes.
> +            result["parent_link_error"] = str(exc)
> +            logger.error("Plan 277: issue creado sin enlace de padre: %s", exc)
>      return result
> ```
> Así el fallo **existe en el resultado** (`parent_link_error`) sin abortar la creación. Es el punto medio entre el `pass` mudo de hoy y romper el flujo.

**Tests PRIMERO — `tests/test_plan277_write_path.py`, 9 casos** (todos con el `_client._request` mockeado; **cero red**):

| # | Caso | Gate |
|---|---|---|
| 1 | `_type_label("User Story")` → `"type::user_story"` (no `"type::User Story"`) | El espacio que rompía el parser |
| 2 | `create_item` con `item_type="Epic"` manda `labels` conteniendo `"type::epic"` | El camino de la épica |
| 3 | `_link_parent("7","42")` con `_epics_native=False` hace **`PUT`** a `/issues/7` con `{"add_labels":"epic::42"}` | El mecanismo nuevo, verificado por verbo y body |
| 4 | `_link_parent` **no** hace ningún POST a `/links` | Los issue-links se retiraron de verdad (assert de ausencia **con el caso positivo sembrado**: el test verifica primero que sí hubo un `PUT`, así "no hubo POST" no pasa por "no hubo nada") |
| 5 | `_epics_native=True` + `_group` → intenta el POST nativo y **no** etiqueta | El camino Premium se conserva |
| 6 | El POST nativo devuelve **403** → cae a la etiqueta y loguea `INFO` | La degradación del `:158-160`, preservada |
| 7 | El POST nativo devuelve **500** → **re-lanza** (no degrada) | Que solo el 403 signifique "sin licencia" |
| 8 | El `PUT` de la etiqueta falla → `create_item` devuelve el issue **con `parent_link_error`** y **no** levanta | El fin del `except Exception: pass` sin romper el flujo |
| 9 | `_link_parent("7","no-es-un-iid")` → loguea `WARNING` y **no** hace request | `etiqueta_de_padre` protege de escribir basura en GitLab |

**Comando:**
```powershell
& $PY -m pytest tests\test_plan277_write_path.py -q                      # 9 passed
& $PY -m pytest tests\test_plan74_migrator_epics.py -q                   # sin regresión (el archivo EXISTE, verificado)
```
**Criterio de aceptación (binario):** 9 passed, y `Select-String -Path services\gitlab_provider.py -Pattern 'except Exception:\s*$' -Context 0,1 | Select-String 'pass'` en **0 coincidencias** dentro de `_link_parent`.

**Ratchet:** registrar `tests/test_plan277_write_path.py` en los dos scripts.
**Flag:** `STACKY_GITLAB_HIERARCHY_CONTRACT_ENABLED`, **default True**. Con OFF, `_type_label` y `_link_parent` **conservan el comportamiento nuevo** (es corrección de defecto: escribir `type::User Story` y tragarse errores son bugs, no features detrás de una flag).
**Impacto por runtime:** idéntico en los 3 — HTTP. **Fallback:** si la instancia es Premium, gana el camino nativo; si devuelve 403, la etiqueta.
**Trabajo del operador: ninguno.**

---

### F4 — Clasificación local: el operador nombra la épica sin tocar GitLab

**Objetivo:** que el operador pueda decir *"este ticket es la épica «Violeta Lugo»"* y *"estos tres cuelgan de ella"* **sin escribir una sola letra en el GitLab de la empresa**. **Valor:** es lo único que le sirve **hoy** — F0 paso 6 mide que los 53 issues de RIPLEY tienen **cero** etiquetas del contrato, así que sin esto el plan no le cambia nada.

**Archivos a editar:** `Stacky Agents/backend/models.py`, `Stacky Agents/backend/db.py`, `Stacky Agents/backend/services/gitlab_sync.py`, `Stacky Agents/backend/api/tickets.py`
**Archivos a crear:** `Stacky Agents/backend/tests/test_plan277_clasificacion_local.py`

**Diff 1 — dos columnas nuevas en `models.Ticket`** (después de `parent_ado_id`, `models.py:57`):
```diff
     parent_ado_id: Mapped[int | None] = mapped_column(Integer)
+    # Plan 277 F4 — clasificación LOCAL de Stacky. Se usa SOLO cuando el tracker
+    # no dijo nada (§3.2: GitLab es el sistema de registro). Nunca se escribe en
+    # GitLab desde acá: eso es F5, detrás de otra flag.
+    local_work_item_type: Mapped[str | None] = mapped_column(String(40))
+    local_parent_iid: Mapped[int | None] = mapped_column(Integer)
```

**Diff 2 — `db.py:273`, agregar a la lista de `migrations`** (mecanismo idempotente que ya existe, `_migrate_add_columns`, `db.py:269-312`):
```diff
         ("tickets", "assigned_to_ado", "VARCHAR(200)"),
+        # Plan 277 F4 — clasificación local de jerarquía (GitLab sin etiquetas).
+        ("tickets", "local_work_item_type", "VARCHAR(40)"),
+        ("tickets", "local_parent_iid", "INTEGER"),
```
> **Es ADD COLUMN sobre la BD del operador.** Es aditivo, idempotente (`PRAGMA table_info` antes de cada ALTER, `db.py:305-309`), no borra ni reescribe nada y es el mecanismo que este repo ya usa para **15 columnas**. No cae en la excepción (B): (B) es *"DDL/DML contra una BD **suya**"* en el sentido de las bases de sus sistemas (el comparador de BD, `STACKY_SQL_EXEC_ENABLED`); esta es **la BD de Stacky**. Aun así: **hacer copia del archivo `.db` antes de la primera corrida** es parte del DoD.

**Diff 3 — el sync respeta la precedencia** (`services/gitlab_sync.py`, dentro del bucle, **antes** del upsert):
```python
# Plan 277 F4 — GitLab es el sistema de registro (§3.2). La clasificación local
# SOLO llena el vacío; si GitLab dijo algo, gana GitLab y la local queda como
# `superseded` (contada, nunca borrada: es dato del operador).
if _clasificacion_local_habilitada():
    if origen_tipo == "defecto" and fila is not None and fila.local_work_item_type:
        tipo = fila.local_work_item_type
        usados_local_tipo += 1
    elif origen_tipo != "defecto" and fila is not None and fila.local_work_item_type \
            and fila.local_work_item_type != tipo:
        superseded_tipo += 1
    if parent_ado_id is None and fila is not None and fila.local_parent_iid:
        parent_ado_id = fila.local_parent_iid
        usados_local_padre += 1
    elif parent_ado_id is not None and fila is not None and fila.local_parent_iid \
            and fila.local_parent_iid != parent_ado_id:
        superseded_padre += 1
```
y los 4 contadores se suman al dict de retorno (**aditivo**: `fetched/created/updated/removed/skipped` no cambian, así que `api/tickets.py:5995-6021` sigue funcionando sin tocar nada).

> **CASO BORDE OBLIGATORIO:** en la **primera** aparición de un issue, `fila is None` y la clasificación local no existe todavía — correcto, no hay nada que aplicar. La clasificación local se aplica **desde el sync siguiente** a que el operador la escriba. Documentarlo en el docstring; es un caso de test.

**Diff 4 — endpoint nuevo, `api/tickets.py`** (junto a los demás de tickets):
```python
@bp.patch("/<int:ticket_id>/hierarchy")
def set_local_hierarchy(ticket_id: int):
    """Plan 277 F4 — clasificación LOCAL de un ticket. NO toca GitLab.

    Body: {"work_item_type": str | null, "parent_iid": int | null}
      - `null` en un campo BORRA esa clasificación local (vuelve a mandar el tracker).
      - Campo AUSENTE = no se toca (PATCH parcial de verdad).
    Respuestas:
      200 {"ok": true, "ticket": {...}}
      400 {"ok": false, "error": "validation", "message": ...}   -> tipo/iid inválido, o auto-padre
      404 si el ticket no existe
      409 {"ok": false, "error": "cycle", "message": ...}        -> el padre haría un ciclo
    """
```

**Las tres validaciones que este endpoint DEBE tener** (cada una con test; la tercera evita una caída real del backend):

1. **`work_item_type` normalizado y acotado.** Pasa por `normalizar_token` + `TIPOS_CANONICOS`; longitud ≤ 40. Un valor libre se acepta capitalizado (regla 5) pero **truncado**.
2. **`parent_iid` != el `ado_id` del propio ticket.** Auto-padre ⇒ **400**.
3. **Sin ciclos.** Recorrer la cadena de padres (tope duro **50 saltos**) y rechazar con **409** si se vuelve a pisar un `ado_id` ya visto.

> **POR QUÉ LA VALIDACIÓN 3 NO ES TEÓRICA — es un crash alcanzable, hoy.** En `api/tickets.py:648-651`, si `t.parent_ado_id == t.ado_id`, entonces `d` y `ado_id_to_ticket[t.parent_ado_id]` **son el mismo objeto**, y `d["children"].append(d)` crea una **auto-referencia**. `jsonify` sobre esa estructura levanta `ValueError: Circular reference detected` ⇒ **500 en `GET /api/tickets/hierarchy`**, es decir: la pantalla entera del grafo se cae por un solo dato. Con `epic::<iid>` escrito a mano en GitLab, o con este endpoint sin validar, es alcanzable en un click. **La validación acá no alcanza** (la etiqueta puede venir de GitLab): F6 agrega además la **guarda defensiva en el endpoint del grafo**.

**Frontend** — `Stacky Agents/frontend/src/components/TicketGraphView.jsx` y `Stacky Agents/frontend/src/pages/TicketBoard.tsx`: en la tarjeta de un ticket **de un proyecto GitLab**, un control "Tipo" (select con los 8 canónicos) y "Padre" (input de `iid` con el título del padre resuelto al lado). Solo visible si `tracker_type === "gitlab"` **y** la flag está ON. La lógica de validación va en **`.ts` puro** (`Stacky Agents/frontend/src/lib/jerarquiaLocal.ts`) porque **no hay RTL/jsdom**; el render se cubre con smoke manual.

**Tests PRIMERO — `tests/test_plan277_clasificacion_local.py`, 14 casos:**

| # | Caso | Gate |
|---|---|---|
| 1-2 | Las 2 columnas existen tras `init_db()`; correr `_migrate_add_columns()` **dos veces** no levanta | Idempotencia del ALTER |
| 3 | PATCH con `work_item_type="Epic"` → la fila queda con `local_work_item_type="Epic"` **y `work_item_type` sin tocar** | La local no pisa la remota en la escritura |
| 4 | PATCH con `parent_iid` = el propio `ado_id` → **400** | Auto-padre |
| 5 | PATCH que cerraría un ciclo A→B→A → **409** | El crash de `jsonify` |
| 6 | PATCH con `work_item_type=null` **borra** la local — **sembrando primero** un valor y verificando que estaba | Un assert de ausencia que nunca vio el dato guardado pasa por accidente |
| 7 | PATCH sin la clave `parent_iid` **no la toca** (PATCH parcial real) | Borrado accidental por omisión |
| 8 | Ticket inexistente → **404** | — |
| 9 | Sync: issue **sin** etiquetas + local `"Epic"` → la fila queda `work_item_type="Epic"`, `usados_local_tipo=1` | El caso del operador |
| 10 | Sync: issue **con** `type::bug` + local `"Epic"` → la fila queda `"Bug"`, `superseded_tipo=1`, **y la local sigue guardada** | §3.2 + no destruir el dato |
| 11 | Sync: primera aparición (`fila is None`) + no hay local → no revienta, `usados_local_*=0` | El caso borde declarado |
| 12 | Con `STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED=False`: el sync **ignora** las columnas locales aunque tengan valor, y el PATCH devuelve **403** con `{"error":"flag_off"}` nombrando la flag | Kill-switch real (una flag registrada pero muerta pasa el gate del registro y no hace nada) |
| 13 | El PATCH **no** hace ninguna llamada HTTP a GitLab (monkeypatchear `GitLabClient._request` y afirmar 0 llamadas) | **Es la promesa central de F4**: no toca el sistema del operador |
| 14 | Segunda corrida del sync sin cambios: `created=0, updated=0` **y conteo de filas idéntico** | Idempotencia (los 3 asserts juntos: solos, cada uno pasa por accidente) |

**Comando:**
```powershell
& $PY -m pytest tests\test_plan277_clasificacion_local.py -q             # 14 passed
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src\__tests__\plan277JerarquiaLocal.test.ts               # 6 passed
```
**Smoke manual (10 pasos, porque no hay RTL/jsdom):** 1) Levantar back+front. 2) Proyecto **RIPLEY**. 3) Tab de tickets, sincronizar. 4) Verificar que **todos** están en huérfanos (la foto de F0). 5) En el ticket *"Violeta Lugo"*, poner Tipo = **Épica**. 6) Refrescar: aparece en la sección de épicas. 7) En otro ticket, Padre = el `iid` de *"Violeta Lugo"*. 8) Refrescar: cuelga de la épica. 9) Poner el ticket como padre **de sí mismo**: debe rechazar con mensaje, **no** dejar la pantalla en blanco. 10) Cambiar a un proyecto **ADO**: el control de jerarquía **no aparece** y la lista no cambió.

**Ratchet:** registrar el test backend en los dos scripts.
**Flag:** `STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED`, **default True** (§3.5 — escribe en la BD de Stacky, nunca en GitLab, y es el operador quien decide ítem por ítem).
**Impacto por runtime:** idéntico en los 3 — HTTP + SQLAlchemy, sin modelo. **Fallback:** con la flag OFF el control no se renderiza y el PATCH devuelve 403 nombrando la flag y dónde encenderla.
**Trabajo del operador:** **opcional**. La jerarquía que GitLab ya declare por etiquetas se arma sola (F2). Este control existe **solo** para el caso —el real, medido en F0 paso 6— de issues heredados sin etiqueta. No es un paso obligatorio nuevo: sin usarlo, el sistema queda exactamente como lo dejó el plan 276.

---

### F5 — Backfill: escribir las etiquetas EN GitLab (con diff y confirmación)

**Objetivo:** que la clasificación local del operador pueda **publicarse** como etiquetas reales, para que la vean también la UI de GitLab, los boards y cualquier otra herramienta. **Valor:** convierte una decisión local en el estándar del proyecto — pero **solo si el operador lo pide, viendo antes qué se va a tocar**.

**Archivos a crear:** `Stacky Agents/backend/services/gitlab_hierarchy_backfill.py`, `Stacky Agents/backend/tests/test_plan277_backfill_labels.py`
**Archivos a editar:** `Stacky Agents/backend/api/tickets.py`

**Dos funciones, dos endpoints, y la separación es el punto:**

```python
def planificar_backfill(project_name: str) -> dict:
    """READ-ONLY. Devuelve el diff: qué etiquetas se agregarían a qué issues.

    NO hace ninguna escritura. Returns:
      {"proyecto": str, "total": int,
       "cambios": [{"ado_id": int, "iid": int, "title": str, "url": str,
                    "agregar": ["type::epic", "epic::42"],
                    "ya_tiene": ["type::bug"],          # conflicto: GitLab ya dice otra cosa
                    "conflicto": bool}],
       "con_conflicto": int}
    Un issue cuyo `type::` remoto DIFIERE de la clasificación local se marca
    `conflicto=True` y NO entra en `agregar` (§3.2: GitLab manda). Se lista para
    que el operador lo vea y decida a mano en GitLab.
    """

def ejecutar_backfill(project_name: str, ado_ids: list[int], *, provider=None) -> dict:
    """ESCRIBE EN EL GITLAB DEL OPERADOR. Un PUT add_labels por issue.

    - Solo los `ado_ids` que el operador mandó EXPLÍCITAMENTE. Nunca "todos".
      Una lista vacía devuelve {"escritos": 0} sin tocar nada.
    - Solo AGREGA etiquetas (`add_labels`). NUNCA `remove_labels`, nunca `labels`
      (que REEMPLAZA el set entero y borraría las etiquetas del operador).
    - Los `ado_ids` con `conflicto=True` se rechazan aunque vengan en la lista.
    - Corta ante el primer fallo, devuelve lo escrito y lo pendiente, y no reintenta.
    Returns: {"escritos": int, "omitidos": int, "fallidos": [{"ado_id","error"}],
              "pendientes": [int]}
    """
```

Endpoints: `GET /api/tickets/hierarchy/backfill/plan?project=<n>` (200, read-only, **sin flag**: es un diff) y `POST /api/tickets/hierarchy/backfill/apply` con body `{"project": str, "ado_ids": [int]}` (**gateado por la flag OFF**; con la flag apagada devuelve **403** `{"error":"flag_off"}` nombrando la flag).

**Tests PRIMERO — `tests/test_plan277_backfill_labels.py`, 11 casos:**

| # | Caso | Gate |
|---|---|---|
| 1 | `planificar_backfill` **no hace ningún request de escritura** (0 `PUT`/`POST`; los `GET` sí) | Que el "plan" sea de verdad read-only |
| 2 | El plan lista `agregar=["type::epic"]` para un ticket con local `"Epic"` y sin etiqueta remota | Camino feliz |
| 3 | Un ticket con `type::bug` remoto y local `"Epic"` → `conflicto=True` y **no** entra en `agregar` | §3.2 |
| 4 | `ejecutar_backfill` con la flag **OFF** → el endpoint devuelve **403** y **cero** requests | La flag es un kill-switch real |
| 5 | `ejecutar_backfill(ado_ids=[])` → `escritos=0` y **cero** requests | "Nunca todos por defecto" |
| 6 | `ejecutar_backfill` usa **`add_labels`**, nunca la clave `labels` (assert sobre el body del `PUT`) | **`labels` REEMPLAZA el set entero**: borraría etiquetas del operador. Es destrucción de datos. |
| 7 | Un `ado_id` con `conflicto=True` en la lista → se **omite**, `omitidos=1`, y **no** se le hace `PUT` | Que el rechazo no dependa solo de la UI |
| 8 | El 2º de 3 issues falla → `escritos=1`, `fallidos` tiene 1, `pendientes` tiene 1, y **no hay 4º request** | Corte ante el fallo, sin reintentos ciegos |
| 9 | Un `ado_id` que **no pertenece** al proyecto pedido → se omite (no se escribe en el proyecto equivocado) | Cross-project |
| 10 | Correr `ejecutar_backfill` **dos veces** con la misma lista: la 2ª no rompe y `add_labels` de una etiqueta ya presente es no-op | Idempotencia |
| 11 | El plan de un proyecto **ADO** devuelve `total=0` y no construye ningún `GitLabClient` | Backward-compat |

**Comando:** `& $PY -m pytest tests\test_plan277_backfill_labels.py -q` ⇒ **11 passed**.
**Criterio de aceptación (binario):** 11 passed **y** `Select-String -Path services\gitlab_hierarchy_backfill.py -Pattern '"labels"'` en **0 coincidencias** (solo puede aparecer `add_labels`).

**Smoke manual (obligatorio, 6 pasos):** 1) Flag OFF (default): el botón "Publicar etiquetas en GitLab" está **deshabilitado** con hint que nombra la flag. 2) Encender la flag por UI. 3) Apretar "Ver qué se va a cambiar": aparece la lista con N issues y los conflictos marcados. 4) Deseleccionar todos menos uno. 5) Confirmar: escribe **1**. 6) Abrir ese issue en GitLab y verificar que **tiene la etiqueta nueva y conserva las que ya tenía**.

**Ratchet:** registrar el test en los dos scripts.
**Flag:** `STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED`, **default False** — **excepción (B): escribe en un sistema REAL del operador.** Hace `PUT /projects/:id/issues/:iid` con `add_labels` contra el GitLab de la empresa, modificando issues que Stacky no creó (`services/gitlab_hierarchy_backfill.py::ejecutar_backfill`). El **plan** (`planificar_backfill`) es read-only y **no** lleva flag: es la partición ON/OFF del precedente `STACKY_PIPELINE_NL_EDIT_ENABLED` / `..._COMMIT_ENABLED`.
**Impacto por runtime:** idéntico en los 3 — HTTP. **Fallback:** con la flag OFF, F4 sigue dando la jerarquía completa **dentro de Stacky**; lo único que no ocurre es que GitLab también la vea.
**Trabajo del operador:** **opt-in explícito**, y es correcto que lo sea: es la única acción del plan que modifica su sistema.

---

### F6 — El grafo no se cae, no miente, y no pierde a los padres cerrados

**Objetivo:** cerrar los tres modos de falla del endpoint del grafo. **Valor:** que la jerarquía que F2-F5 construyeron **se vea**, siempre, sin pantallas rotas.

**Archivos a editar:** `Stacky Agents/backend/api/tickets.py` (`:615-656`), `Stacky Agents/backend/services/gitlab_sync.py`
**Archivos a crear:** `Stacky Agents/backend/tests/test_plan277_grafo_jerarquia.py`

**Diff 1 — la guarda anti-ciclo en `get_hierarchy` (`api/tickets.py:646-654`):**
```diff
     for t in all_tickets:
         d = ado_id_to_ticket[t.ado_id]
         wi_type = (t.work_item_type or "").lower()
         if wi_type == "epic":
             epics.append(d)
-        elif t.parent_ado_id and t.parent_ado_id in ado_id_to_ticket:
+        # Plan 277 F6 — `parent_ado_id == ado_id` hace `d["children"].append(d)`:
+        # una AUTO-REFERENCIA que revienta jsonify con "Circular reference
+        # detected" ⇒ 500 y pantalla del grafo caída por UN dato. Es alcanzable
+        # con una etiqueta `epic::<propio iid>` escrita a mano en GitLab, así que
+        # validar solo en el endpoint de F4 no alcanza.
+        elif (
+            t.parent_ado_id
+            and t.parent_ado_id != t.ado_id
+            and t.parent_ado_id in ado_id_to_ticket
+            and not _crea_ciclo(t.ado_id, t.parent_ado_id, all_tickets)
+        ):
             ado_id_to_ticket[t.parent_ado_id]["children"].append(d)
         else:
             orphans.append(d)
```
`_crea_ciclo(ado_id, parent_id, tickets)` — helper nuevo en el mismo archivo: recorre la cadena de padres con un `set` de visitados y **tope duro de 50 saltos**; devuelve `True` si vuelve a `ado_id` o si agota el tope. Un ticket cuyo padre haría ciclo cae en `orphans` **con un warning logueado** — se pierde el enlace, nunca la pantalla.

**Diff 2 — traer los padres que faltan (`services/gitlab_sync.py`, al final del bucle):**
```python
# Plan 277 F6 — el sync pide `state="open"`. Una épica CERRADA no viene en el
# listado, así que sus hijos apuntan a un `parent_ado_id` que no está en la BD y
# el endpoint del grafo los manda a `orphans` (api/tickets.py:648-651). Se piden
# UNO A UNO, y solo, los iid que las etiquetas nombraron y no llegaron.
if _sync_parents_habilitado():
    referenciados = {p for p in parents_vistos if p}
    presentes = {ado_id de todo lo que se upserteó} | {ado_id ya en BD del proyecto}
    faltantes = sorted(referenciados - presentes)[:_TOPE_PADRES]   # _TOPE_PADRES = 50
    for iid in faltantes:
        try:
            body = provider.get_item(str(iid))     # ya existe: gitlab_provider.py:205-208
        except Exception as exc:
            padres_fallidos += 1; logger.warning(...); continue
        ... mismo upsert por la terna, mismo mapeo ...
        padres_traidos += 1
    if len(referenciados - presentes) > _TOPE_PADRES:
        logger.warning("Plan 277: %d padres faltantes exceden el tope de %d; se trajeron los primeros %d.",
                       len(referenciados - presentes), _TOPE_PADRES, _TOPE_PADRES)
```
> **EL TOPE SE LOGUEA SIEMPRE QUE RECORTA.** Una cota silenciosa se lee como "trajimos todos" cuando no fue así. `padres_traidos`, `padres_fallidos` y `padres_omitidos_por_tope` se suman al dict de retorno (aditivo).

**Diff 3 — los rótulos de tipo, en el frontend.** `Stacky Agents/frontend/src/utils/workItemTypeColor.ts` gana las 3 fases del contrato:
```diff
 const WORK_ITEM_TYPE_COLORS: Record<string, string> = {
   issue:   "#FF3B5C",
   epic:    "#8B5CF6",
   task:    "#3B82F6",
   bug:     "#EF4444",
   feature: "#10B981",
+  // Plan 277 — las 3 fases del contrato de jerarquía. Los tokens son ASCII sin
+  // acento (regla 1 del contrato); el ACENTO va solo en el rótulo visible.
+  funcional:      "#F59E0B", // ámbar — Análisis Funcional
+  tecnico:        "#06B6D4", // cian  — Análisis Técnico
+  implementacion: "#3B82F6", // azul  — Implementación (comparte familia con task, es su ejecución)
 };
+
+/** Rótulo visible por tipo. El token guardado es ASCII; el rótulo lleva acento. */
+const WORK_ITEM_TYPE_LABELS: Record<string, string> = {
+  epic: "Épica", funcional: "Análisis Funcional",
+  tecnico: "Análisis Técnico", implementacion: "Implementación",
+};
```
y `formatWorkItemTypeLabel` (`:53-57`) consulta ese mapa **antes** de devolver el crudo (conservando el prefijo `INCIDENT_ICON` para `issue`/`bug`, que ya existe por a11y).

**Tests PRIMERO — `tests/test_plan277_grafo_jerarquia.py`, 10 casos:**

| # | Caso | Gate |
|---|---|---|
| **1** | Ticket con `parent_ado_id == ado_id` → el endpoint devuelve **200** (no 500) y ese ticket está en `orphans` | **El crash de `jsonify`.** Verificar además que `json.dumps(respuesta)` **no** levanta — un `assert status == 200` solo no prueba que la estructura sea serializable si el test no la serializa |
| 2 | Ciclo A→B→A → 200, los dos en `orphans`, warning logueado | El ciclo indirecto |
| 3 | Cadena de 60 tickets encadenados → 200 sin `RecursionError` | El tope de 50 saltos |
| 4 | Épica + 3 hijos (`funcional`/`tecnico`/`implementacion`) → `len(epics)==1`, `len(children)==3`, `orphans==0` | **El caso "Violeta Lugo" completo** |
| 5 | Padre cerrado ausente → tras el sync con `STACKY_GITLAB_SYNC_PARENTS_ENABLED=True`, aparece y sus hijos **dejan de ser huérfanos** — **sembrando primero** la corrida con la flag OFF que los deja huérfanos | Un test de "ahora sí cuelga" que nunca vio el "antes" no prueba nada |
| 6 | Con la flag de padres OFF: **cero** llamadas a `get_item` | Kill-switch real |
| 7 | 60 padres faltantes → se traen **50** y se loguea el recorte con el número real | La cota que no miente |
| 8 | `get_item` de un padre falla → `padres_fallidos=1`, el sync **termina** y devuelve el resto | Un padre roto no tumba la corrida |
| 9 | Proyecto ADO: el bloque de padres no ejecuta (assert de que `get_item` no se llamó) | Backward-compat |
| 10 | Un proyecto con tickets ADO **y** GitLab con `ado_id` colisionando: un hijo GitLab **no** cuelga de un padre ADO | La colisión de namespaces del riesgo R2 |

**Comando:**
```powershell
& $PY -m pytest tests\test_plan277_grafo_jerarquia.py -q                 # 10 passed
& $PY -m pytest tests\test_plan276_hierarchy_gitlab.py -q                # 5 passed, sin regresión
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src\utils\__tests__\workItemTypeColor.test.ts             # sin regresión + 4 casos nuevos
```
**Criterio de aceptación (binario):** 10 + 5 passed, el test de colores sin regresión, y el caso 1 verificado **serializando** la respuesta.

**Ratchet:** registrar el test backend en los dos scripts.
**Flag:** `STACKY_GITLAB_SYNC_PARENTS_ENABLED`, **default True** (§3.5). La guarda anti-ciclo **no lleva flag**: es corrección de un crash.
**Impacto por runtime:** idéntico en los 3. **Fallback:** con la flag de padres OFF, los hijos de una épica cerrada quedan en `orphans` — que es el comportamiento de hoy, no una regresión.
**Trabajo del operador: ninguno.**

---

### F7 — Registro de las 4 flags y ayuda en castellano llano

**Objetivo:** que las 4 flags existan en las 4 superficies que este repo exige. **Valor:** una flag que no está en el registro rompe `test_every_registry_flag_is_categorized` a propósito (`harness_flags.py:546-547`), y una sin ayuda deja al operador sin saber qué apaga.

**Archivos a editar:** `Stacky Agents/backend/config.py`, `Stacky Agents/backend/services/harness_flags.py` (**dos** lugares), `Stacky Agents/backend/services/harness_flags_help.py`

**Las 4 superficies, verificadas contra una flag real de 276** (`STACKY_GITLAB_SYNC_ENABLED`):

| # | Archivo | Qué se agrega | Anclaje del patrón |
|---|---|---|---|
| 1 | `config.py` | El atributo `os.getenv(...)` con el default | `config.py:1355-1357` |
| 2 | `services/harness_flags.py` | La key en `_CATEGORY_KEYS`, categoría GitLab | `harness_flags.py:538-542` |
| 3 | `services/harness_flags.py` | El `FlagSpec(key=..., type="bool", default=..., label=..., description=...)` | `harness_flags.py:5508-5520` |
| 4 | `services/harness_flags_help.py` | El `PlainHelp(what=, on_effect=, off_effect=, example=)` | `harness_flags_help.py:39-44` |

> **La flag OFF necesita su comentario de curaduría.** `STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED` lleva, en la línea del `default=False`, el comentario literal: `# default OFF — excepción (B): PUT add_labels contra el GitLab del operador (gitlab_hierarchy_backfill.ejecutar_backfill)`. Las tres ON llevan `# default ON` con el motivo en una línea, siguiendo `harness_flags.py:5511`.

**Test — se reusa el que ya existe, no se escribe uno nuevo:**
```powershell
& $PY -m pytest tests\test_harness_flags.py -q
& $PY -m pytest tests\test_harness_flags_help.py -q
```
> **`test_harness_flags_help` tiene 4 fallos PREEXISTENTES** ajenos a este plan. El criterio es **delta**: correrlo **antes** de tocar nada, anotar el número exacto de fallos, y exigir **el mismo número** después. Un gate compartido rojo de fábrica no se juzga por "verde/rojo" sino por "no empeoró".

**Criterio de aceptación (binario):** `test_harness_flags.py` en verde; `test_harness_flags_help.py` con **exactamente los mismos fallos** que en la corrida previa (número anotado en el commit); y
```powershell
& $PY -c "from services.harness_flags import FLAG_REGISTRY as R; ks={f.key for f in R}; n=[k for k in ['STACKY_GITLAB_HIERARCHY_CONTRACT_ENABLED','STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED','STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED','STACKY_GITLAB_SYNC_PARENTS_ENABLED'] if k not in ks]; assert not n, n; print('4 flags registradas OK')"
```
**Ratchet:** no aplica (no hay archivo de test nuevo).
**Flag:** las 4 (esta fase **es** su registro).
**Impacto por runtime:** idéntico en los 3 — es configuración. **Trabajo del operador: ninguno** (las 4 aparecen solas en la pantalla de flags, que ya existe).

---

### F8 — Gate ejecutable de cierre: "el operador VE la jerarquía"

**Objetivo:** un solo comando con **exit code** que prueba la meta del plan. **Valor:** es el único criterio que distingue "las fases cerraron" de "el operador ve la épica con sus hijos".

**Archivos a crear:** `Stacky Agents/backend/scripts/smoke_plan277_jerarquia.ps1` y `Stacky Agents/backend/scripts/smoke_plan277_jerarquia.sh` (**los dos**: los ratchets divergen y el `.ps1` es el que corre en esta máquina)

**Qué hace, en orden, y sale ≠ 0 en cualquier fallo:**
1. Verifica que las 4 flags están en el registro (el `-c` de F7). Si falta una ⇒ **exit 2**.
2. Dispara el sync del proyecto (`POST /api/tickets/sync`) y lee la respuesta. Si no es 200 ⇒ **exit 3**, imprimiendo el body.
3. `GET /api/tickets/hierarchy?project=<n>` y calcula `epics`, `children`, `orphans`.
4. **Serializa la respuesta con `ConvertTo-Json -Depth 20` / `json.dumps`.** Si levanta ⇒ **exit 4** (es el gate del ciclo de F6; un 200 no prueba que la estructura sea serializable río abajo).
5. **exit 5** si `epics == 0` — la meta del operador no se cumplió.
6. **exit 6** si `epics + children + orphans` **≠** el conteo de filas GitLab en la BD. Es el gate de que el grafo no pierde tickets por el camino.
7. Imprime la tabla final: `epics / children / orphans / total` y, por cada épica, su título e hijos. **exit 0**.

```powershell
# uso
.\scripts\smoke_plan277_jerarquia.ps1 -Project RIPLEY -BaseUrl http://localhost:5000
if ($LASTEXITCODE -ne 0) { "FALLÓ con código $LASTEXITCODE" }
```

**Criterio de aceptación (binario):** el script sale **0** contra RIPLEY, con `epics ≥ 1` y la épica *"Violeta Lugo"* listada con sus hijos. La salida literal se pega en el commit de F8.

> **Antes de correr el gate hay que clasificar al menos una épica** (F4, paso 5 del smoke) — porque F0 paso 6 mide que los issues heredados no traen etiquetas. **Eso no es una trampa del gate**: es exactamente el flujo del operador, y si el gate pasara sin ninguna clasificación estaría midiendo otra cosa.

**Ratchet:** registrar **los dos** scripts en los dos ratchets.
**Flag:** ninguna (el gate solo lee).
**Impacto por runtime:** idéntico en los 3 — HTTP. **Trabajo del operador: ninguno** (lo corre el implementador).

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (dónde) |
|---|---|---|---|
| **R1** | **Auto-referencia ⇒ 500 en el grafo.** `parent_ado_id == ado_id` hace `d["children"].append(d)` y `jsonify` levanta `Circular reference detected`: se cae la pantalla entera por un dato. Alcanzable con una etiqueta escrita a mano en GitLab. | **Alta** — es el `elif` de `api/tickets.py:648` tal como está hoy | Validación en F4 (400/409) **y** guarda defensiva en F6 (el dato malo puede venir de GitLab, no solo del endpoint) **y** el test que **serializa** la respuesta |
| **R2** | **Colisión de `ado_id` entre trackers.** `ado_id_to_ticket` se indexa por `ado_id` sobre todos los tickets del filtro de proyecto. Un proyecto migrado de ADO a GitLab conserva filas viejas cuyo `ado_id` puede coincidir con un `iid` de GitLab ⇒ un hijo GitLab colgaría de un padre ADO. | Media (solo en proyectos migrados) | Caso 10 de F6 lo fija. **Mitigación mínima declarada:** en `get_hierarchy`, el enlace hijo→padre exige además `t.tracker_type == padre.tracker_type`. Es un cambio de 1 línea y va **dentro** del diff 1 de F6 |
| **R3** | **`labels` vs `add_labels`.** Un implementador que use `{"labels": "..."}` en el PUT **reemplaza el set entero** y borra las etiquetas del operador. Es destrucción de datos irreversible sobre su sistema. | Media (es la clave "natural" de la API) | Caso 6 de F5 (assert sobre el body) + el `Select-String` del criterio de aceptación + la advertencia en el docstring |
| **R4** | **El contrato se escribe pero nadie lo lee** (lo que ya pasó con los issue-links). | Baja tras F2/F3 | El gate de F8 lee **por HTTP** lo que F3 escribió; el caso 4 de F3 verifica que el mecanismo viejo se retiró |
| **R5** | **Etiquetas con `::` en Premium se vuelven scoped y se excluyen mutuamente**, borrando una `type::` anterior al agregar otra. | Baja (efecto **deseado**) | La regla 2 del contrato hace la lectura determinista con o sin exclusión mutua; F0 paso 5 mide la edición antes de empezar |
| **R6** | El operador clasifica local, después GitLab dice otra cosa, y su trabajo **se pierde en silencio**. | Media | §3.2 + caso 10 de F4: la local **nunca se borra**, se cuenta como `superseded` y el sync lo devuelve |
| **R7** | **El tope de 50 padres recorta y se lee como "trajimos todos"**. | Media en proyectos grandes | El `logger.warning` obligatorio con el número real + caso 7 de F6 |
| **R8** | La migración de columnas corre sobre la **BD real de 181 MB** del operador. | Baja (es ADD COLUMN idempotente, mecanismo con 15 precedentes) | Copia del `.db` antes de la primera corrida (DoD) + casos 1-2 de F4 (doble ejecución) |
| **R9** | `SQLITE_LOCKED` hace flaky cualquier test de BD de este plan. | Media (conocida en este repo) | Todos los tests de BD usan la fixture de sqlite temporal por test (`tmp_path`), el patrón de 276 F5.5. **Nunca la BD compartida** |

---

## 6. Fuera de scope (declarado, no olvidado)

1. **Sincronizar épicas nativas de grupo** (`GET /groups/:id/epics`). Requiere Premium, una tabla o convención nueva para un objeto que **no es un issue**, y un segundo namespace de ids. §3.2 explica por qué el `epic` nativo se conserva como diagnóstico y no como padre. Plan aparte si el operador saca licencia.
2. **Renombrar la columna `ado_id`** a algo agnóstico. Toca 7 archivos de frontend y la API pública. Ya estaba fuera de scope en 276 §7 y sigue estándolo.
3. **Milestones de GitLab como agrupador.** Son nativos, gratis y vienen en el payload — pero un milestone **no tiene comentarios ni descripción propia**, así que no puede ser la épica *"Violeta Lugo"* que el operador describe (*"la épica … de la que se desprenden las tareas"*). Se descarta por el requerimiento, no por dificultad.
4. **Crear automáticamente los 3 hijos** (funcional/técnico/implementación) al marcar una épica. Es una **escritura no pedida** en el sistema del operador y le sacaría la decisión: choca con el riel de human-in-the-loop. Si se quisiera, va como acción explícita con preview, en otro plan.
5. **Migrar los comentarios de fase del plan 77 a tickets hijos.** Las dos formas coexisten a propósito: 77 = un issue con 3 comentarios; 277 = una épica con 3 hijos. Este plan **alinea el vocabulario** para que sean interoperables; convertir una en otra es otro trabajo.
6. **Jira y Mantis.** El contrato vive en `gitlab_hierarchy.py` y es específico de GitLab. Los otros trackers siguen exactamente como hoy.
7. **Paginación de más de 50 padres faltantes.** F6 recorta y **lo dice**. Subir el tope es config, no código.

---

## 7. Glosario

- **`iid`** — *internal id*: el número visible de un issue **dentro de su proyecto** GitLab (el `#42`). Se repite entre proyectos distintos. Es lo que Stacky guarda en `Ticket.ado_id`.
- **`id`** — el id **global** de GitLab, único en toda la instancia. Stacky lo guarda en `Ticket.external_id` y es la clave de upsert (junto con `stacky_project_name` y `tracker_type`).
- **Épica nativa** — objeto de GitLab a **nivel de grupo**, disponible solo con licencia Premium/Ultimate. No es un issue y no vive en la tabla `tickets`.
- **Scoped label** — etiqueta con `::` que en Premium se auto-excluye con sus hermanas de mismo prefijo. En CE es una etiqueta común cuyo nombre contiene `::`. El contrato de este plan **no depende** de la exclusión mutua.
- **`type::` / `epic::`** — los dos prefijos del contrato de este plan. El primero dice **qué es** el ticket; el segundo, **de quién cuelga**.
- **Huérfano (`orphans`)** — en `GET /api/tickets/hierarchy`, todo ticket que no es épica y no tiene un padre presente en la BD. Hoy son el 100 % de los tickets GitLab.
- **`work_item_type`** — columna `String(40)` de `tickets`. En ADO viene de `System.WorkItemType`; en GitLab, del contrato.
- **`parent_ado_id`** — columna `Integer` de `tickets`. Guarda el `ado_id` **del padre**, no su `id` global.
- **Ratchet** — los dos scripts (`run_harness_tests.ps1` y `.sh`) donde hay que registrar todo test nuevo. **Divergen**: medido el 2026-07-31, **776** líneas con `test_`/`pytest` en el `.sh` contra **712** en el `.ps1` (delta 64). El meta-test solo parsea el `.sh`, así que registrar solo ahí **pasa el gate y deja el `.ps1` incompleto**: hay que tocar **los dos**. Y no admite rutas con espacios.
- **Categoría de excepción (A)/(B)** — las dos únicas razones por las que una flag nueva puede nacer OFF: (A) quema tokens en reposo; (B) escribe en un sistema real del operador, destruye datos o le saca la decisión.
- **Falso verde** — un test que pasa sin probar lo que dice probar. Los tres de este plan: `assert` de ausencia sin sembrar el caso positivo, `created == 0` como prueba de idempotencia, y `pytest -k` sin match (exit 0).

---

## 8. Orden de implementación

1. **F0** — Medir el "antes" y abortar si falta el plan 276. **Nada de código.** Pegar las 6 salidas en el commit.
2. **F1** — `services/gitlab_hierarchy.py` + sus 24 tests. Es el cimiento: todo lo demás lo importa.
3. **F7 (parcial)** — Registrar `STACKY_GITLAB_HIERARCHY_CONTRACT_ENABLED` en las 4 superficies **ahora**, porque F2 la lee. Las otras 3 flags, cuando llegue su fase.
4. **F2** — Read path: `_normalize_issue` + los 3 motores consolidados + 12 tests. Después de esto, un issue **con** etiquetas ya arma jerarquía.
5. **F3** — Write path: `_type_label`, `_link_parent`, `create_item` + 9 tests. Cierra el lazo escribir↔leer.
6. **F4** — Columnas + endpoint + UI + 14 tests + smoke de 10 pasos. **Es la fase que le sirve al operador hoy.** Registrar su flag.
7. **F6** — Guarda anti-ciclo, padres faltantes, colores + 10 tests. Va **antes** que F5 porque protege de un crash y F5 no es urgente.
8. **F5** — Backfill a GitLab + 11 tests + smoke de 6 pasos. Registrar su flag (**OFF**). Es lo último que se construye porque es lo único que escribe afuera.
9. **F7 (completo)** — Cerrar el registro de las 4 flags y correr el delta de `test_harness_flags_help`.
10. **F8** — El gate ejecutable. **Si sale ≠ 0, el plan no está hecho**, sin importar cuántas fases figuren cerradas.

---

## 9. Definición de Hecho (DoD)

El plan 277 está hecho cuando **todas** estas líneas son verdaderas y están verificadas con su comando:

- [ ] **F0 corrido y pegado**: los 6 pasos, con `epics=0` y `children=0` documentados como el "antes".
- [ ] **Copia del `.db`** del operador hecha antes de la primera corrida con las columnas nuevas.
- [ ] `tests/test_plan277_contrato_jerarquia.py` ⇒ **24 passed**, y el módulo pasa el check de pureza (sin `requests`, sin `session_scope`, sin `config`).
- [ ] `tests/test_plan277_read_path.py` ⇒ **12 passed**.
- [ ] `tests/test_plan277_write_path.py` ⇒ **9 passed**.
- [ ] `tests/test_plan277_clasificacion_local.py` ⇒ **14 passed**.
- [ ] `tests/test_plan277_backfill_labels.py` ⇒ **11 passed**.
- [ ] `tests/test_plan277_grafo_jerarquia.py` ⇒ **10 passed**.
- [ ] `src/__tests__/plan277JerarquiaLocal.test.ts` ⇒ **6 passed**; `workItemTypeColor.test.ts` sin regresión + 4 casos nuevos.
- [ ] **Sin regresión** en `test_plan276_gitlab_sync.py` (16), `test_plan276_hierarchy_gitlab.py` (5), `test_plan74_migrator_verify.py`, `test_plan74_migrator_epics.py` y `test_harness_flags.py`. Los cuatro primeros **existen hoy** (verificado) y los dos de `plan74` cubren código que F2/F3 modifican.
- [ ] `test_harness_flags_help.py` con **el mismo número exacto** de fallos preexistentes que antes de tocar nada (número anotado en el commit).
- [ ] **Las 4 flags** en las 4 superficies; la única OFF (`STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED`) con su categoría **(B)** escrita en la línea del default.
- [ ] **Los 8 archivos de test/script nuevos registrados en LOS DOS ratchets** (`.ps1` y `.sh`).
- [ ] **Un solo motor**: `Select-String -Path services\migrator_verify.py -Pattern '_TYPE_LABEL_RE'` en **0**.
- [ ] **Cero `except Exception: pass`** dentro de `_link_parent`.
- [ ] **Cero `"labels"`** (solo `"add_labels"`) en `gitlab_hierarchy_backfill.py`.
- [ ] **Smoke manual de F4** (10 pasos) corrido, con captura del paso 8 (el hijo colgando de *"Violeta Lugo"*).
- [ ] **Smoke manual de F5** (6 pasos) corrido, con la verificación de que el issue **conservó** sus etiquetas previas.
- [ ] **`smoke_plan277_jerarquia.ps1` sale 0** contra RIPLEY, con `epics ≥ 1`, salida pegada en el commit.
- [ ] `& $PY -m compileall backend` sin errores y `npx tsc --noEmit` en **0**.
- [ ] La huella del error `Circular reference detected` de R1 registrada en `docs/sistema/error_fingerprints.json` (convención del repo, igual que 276 §10).
