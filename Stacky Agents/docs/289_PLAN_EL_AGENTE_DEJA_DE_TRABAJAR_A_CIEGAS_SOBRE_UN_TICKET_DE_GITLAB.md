# Plan 289 — El agente deja de trabajar a ciegas sobre un ticket de GitLab

**Estado:** v1 — PROPUESTO (papel). NO implementado.
**Rama en la que se escribió:** `docs/plan-279`
**Fecha:** 2026-08-02
**Depende de:** Plan 286 (IMPLEMENTADO, `64a58ff4`..`af9a5ec1`) — reusa su helper `tracker_efectivo_de_ticket`.
**Frontera con planes hermanos en vuelo:** 287 y 288 (sesión paralela VIVA). Ver §3.6.

---

## 1. Objetivo y KPI

### 1.1 Objetivo

Hoy, cuando un agente de Stacky corre sobre un ticket de un proyecto **GitLab**, el pipeline de
enriquecimiento de contexto le entrega **cero** bloques del tracker: no lee los comentarios del
issue. La causa no es una decisión de diseño; es un `except` que se traga un error de
construcción de cliente y devuelve la lista vacía sin decir nada al operador
(`services/ado_context.py:212` construye un cliente de Azure DevOps, `:217-220` se come el fallo).

Este plan hace **una sola cosa**: que los **comentarios** del issue lleguen al contexto del agente
también en GitLab, por la costura de proveedor que ya existe (`get_tracker_provider`), sin tocar
ninguno de los caminos de Azure DevOps salvo por un endurecimiento deliberado y declarado
(enmascarado de secretos).

Y hace una cosa previa, sin la cual el resultado no sería medible: **que el contador de
enriquecimiento sobreviva en los tres runtimes**. Hoy sólo lo persiste uno de tres.

**Los adjuntos quedan explícitamente FUERA de scope.** Ver §6.1 — no es pereza, es que el
proveedor de GitLab no descarga contenido y hacerlo es un plan aparte.

### 1.2 KPI — todos binarios, todos con comando

Medidos el **2026-08-02** contra una **copia read-only** de la BD viva
`Stacky Agents/backend/data/stacky_agents.db` (194.068.480 bytes). **No se escribió en la BD del
operador.**

| # | KPI | Hoy (medido) | Meta | Cómo se verifica |
|---|---|---|---|---|
| K1 | Bloques de comentarios que recibe un agente sobre un issue de GitLab con N comentarios | **0** | **1 bloque con hasta 30 comentarios** | `tests/test_plan289_contexto_por_tracker.py` (F6) |
| K2 | Ejecuciones de la BD viva con la clave `ado_context` en su metadata | **4 de 222** (1,8 %) — las 4 son de `github_copilot` y las 4 dicen `skipped_reason: agent_not_in_enrich_list` | **las 3 runtimes escriben la clave** | F2 + §7.3 (smoke manual) |
| K3 | Ejecuciones del runtime `claude_code_cli` con la clave `ado_context` | **0 de 173** | **> 0** | F2 |
| K4 | Ejecuciones de la BD viva con `ado_context.comments_count > 0` | **0 de 222** | **> 80 %** de las corridas sobre issues **que tienen** comentarios | §7.3 — **sólo declarable con F2 hecha** |
| K5 | Ejecuciones `functional`/`technical` de RIPLEY (GitLab) con contexto de tracker | **0 de 6** (ids 211, 212, 215, 216, 219, 220) | **> 0** | §7.3 |
| K6 | Comentarios del bloque que pasan por enmascarado de secretos (ADO **y** GitLab) | **0 %** — `ado_context` no llama a `mask_token_values` | **100 %** | F5 |
| K7 | `tests/test_ado_context.py` | **9 failed, 8 passed** — rojo **ambiental**, causado por este mismo defecto | **17 passed** | F1 |

> **K2/K3/K4 son la razón por la que este plan tiene una fase (F2) que parece ajena al título.**
> Sin ella, cualquier criterio de aceptación que hable de porcentajes de ejecuciones es
> **inventado**: el dato no existe en la base porque **173 de 222 ejecuciones corrieron por
> `claude_code_cli`, y ese runtime tira el contador**.

**Reparto medido por runtime (222 ejecuciones, BD viva, 2026-08-02):**

| `metadata.runtime` | ejecuciones | con clave `ado_context` |
|---|---|---|
| `claude_code_cli` | **173** | **0** |
| `github_copilot` | 24 | **4** |
| *(sin runtime)* | 25 | 0 |

**Corrección de una cifra que circulaba en la formulación del pedido:** no son *"5 ejecuciones
`functional`/`technical` de RIPLEY"* sino **6** (ids 211 `functional`, 212 `technical`, 215
`functional`, 216 `technical`, 219 `technical`, 220 `technical`); y el `0` no es sólo de RIPLEY:
es **0 de 222** en toda la base, incluido Azure DevOps.

---

## 2. Por qué ahora, y qué gap cierra respecto de los planes recientes

### 2.1 Lo que el Plan 286 dejó cerrado (NO lo repitas)

`docs/286_PLAN_EL_RUTEO_DE_ESCRITURA_LE_PREGUNTA_AL_PROYECTO_NO_A_LA_COLUMNA.md`
(IMPLEMENTADO, F0..F7) dejó vivo y verificado:

- **`services/project_context.tracker_efectivo_de_ticket(ticket) -> str`** (`:201-256`), con
  precedencia **columna explícita > config del proyecto > `_DEFAULT_TRACKER_TYPE`**. Nunca
  levanta, nunca devuelve cadena vacía.
- El memo por `mtime` sobre `get_project_config` (`_TRACKER_DECLARADO_MEMO`,
  `project_context.py:106`) y su `_reset_memo_tracker_declarado()` para tests (`:109`).
- El kill-switch **compartido** `ruteo_estricto_por_tracker()` (`project_context.py:78`), default
  `True`.

**Regla dura de este plan: el 289 NO escribe otro resolvedor de tracker.** Si necesitás saber a
qué tracker pertenece un ticket, llamás a `tracker_efectivo_de_ticket`. Si sólo tenés el nombre
del proyecto, llamás a `tracker_is_azure_devops(project_name)` (`project_context.py:46`). Nada más.

### 2.2 Lo que el Plan 282 dejó cerrado (NO lo dupliques)

`docs/282_PLAN_GITLAB_DEJA_DE_SER_UN_ADO_DISFRAZADO_PARIDAD_Y_FLUIDEZ.md` (IMPLEMENTADO) construyó
`services/comment_publish_router.py`: un adaptador **client-shaped** que envuelve al provider de
GitLab con la forma del **cliente ADO** para **PUBLICAR** un comentario
(`comment_publish_router.py:64-74`, `post_comment(item_id, body_html, content_format="html")`
adaptando a la firma de dos argumentos del provider).

**Ese adaptador es de ESCRITURA y NO sirve para este plan**, por dos razones concretas:

1. Sólo expone `post_comment` y `comment_exists` (`:64` y `:77`). **No expone lectura de
   comentarios.**
2. Su forma de entrada es la del cliente ADO; lo que este plan necesita es lo contrario:
   **traducir la SALIDA de GitLab a la forma que ya consume `ado_context`.**

El 282 también dejó `gitlab_factory_only_enabled()` (`tracker_provider.py:176`) y la regla de
**un solo constructor** de `GitLabTrackerProvider`, que es `get_tracker_provider`
(`tracker_provider.py:125`). **Este plan usa esa fábrica y ninguna otra**: construir
`GitLabTrackerProvider(...)` a mano pierde el `ca_bundle` y muere con
`CERTIFICATE_VERIFY_FAILED` contra el GitLab interno (`tracker_provider.py:167-173`).

### 2.3 El gap, con la evidencia abierta y verificada

**(a) El camino de lectura de contexto es ADO-only y falla en silencio.**

`services/ado_context.py:209-220`:

```python
    try:
        from services.project_context import build_ado_client

        client = build_ado_client(
            project_name=project_name,
            tracker_project=tracker_project,
            ticket=ticket,
        )
    except Exception as e:
        logger.warning("ado_context — no se pudo instanciar AdoClient: %s", e)
        stats["errors"].append(f"ado_client_init_failed: {e}")
        return [], stats
```

`build_ado_client` levanta para todo proyecto no-ADO (`project_context.py:521-524`):

```python
    if ctx.tracker_type != _DEFAULT_TRACKER_TYPE:
        raise AdoConfigError(
            f"El proyecto '{ctx.stacky_project_name}' no usa Azure DevOps (tracker_type={ctx.tracker_type})."
        )
```

**Evidencia de ejecución, no inferida:** correr `tests/test_ado_context.py` en esta máquina
(proyecto activo = `RIPLEY`, `issue_tracker.type = gitlab`) produce **9 failed, 8 passed** con este
warning capturado en los 9:

```
WARNING stacky_agents.ado_context:ado_context.py:218 ado_context — no se pudo instanciar AdoClient:
El proyecto 'RIPLEY' no usa Azure DevOps (tracker_type=gitlab).
```

Es decir: **el propio archivo de tests del módulo ya está rojo por el defecto que este plan
arregla**, y nadie lo vio porque el rojo depende del proyecto activo del operador
(`backend/data/active_project.json` → `{"active": "RIPLEY"}`) y porque el archivo está exento del
ratchet (`backend/tests/harness_ratchet_allowlist.txt:10`, marcado `# pendiente-de-triage`).

**(b) El seam es común a los 3 runtimes; el contador NO.**

Los tres runtimes llaman al mismo pipeline, `services/context_enrichment.enrich_blocks` (`:60`):

| Runtime | Sitio de llamada | Qué hace con el 2º valor de retorno |
|---|---|---|
| GitHub Copilot Pro | `agent_runner.py:809` | lo guarda en `ado_enrich_stats` y lo persiste en `md["ado_context"]` (`:871` y `:1051`) |
| Claude Code CLI | `services/claude_code_cli_runner.py:677` | lo asigna a **`_ado_stats`** y **lo tira** |
| Codex CLI | `services/codex_cli_runner.py:334` | lo asigna a **`_ado_stats`** y **lo tira** |

Con `claude_code_cli` representando **173 de 222** ejecuciones de la base, el contador
prácticamente no existe. Cualquier métrica sobre él es hoy inmedible.

**(c) La consecuencia real sobre el trabajo del agente.**

Sobre un issue de GitLab el agente **no lee los comentarios**. Los otros dos síntomas que se le
suelen atribuir a este mismo bug tienen una causa distinta y hay que decirlo con precisión, porque
si no el implementador va a "arreglar" algo que ya está decidido:

- **Criterios de aceptación:** `services/acceptance_criteria.resolve` (def en `:25`) devuelve `""`
  para todo proyecto no-ADO **a propósito**, por un guard explícito del Plan 281 F7 (`:42-46`, con
  el motivo escrito en el comentario de `:38-41`): `Microsoft.VSTS.Common.AcceptanceCriteria` **es
  un campo de Azure DevOps y en GitLab no existe**. Lo mismo en
  `services/self_review._resolve_criteria` (def en `:43`, guard en `:56-60`). **No es un bug y NO
  se toca en este plan.** Ver §6.2.
- **Adjuntos:** ver §6.1.

**(d) Las formas NO coinciden — verificado abriendo los dos adaptadores.**

| Qué | Azure DevOps | GitLab |
|---|---|---|
| Firma | `fetch_comments(self, ado_id: int, top: int = 20)` — `services/ado_client.py:431` | `fetch_comments(self, item_id: str)` — **sin `top`** — `services/gitlab_provider.py:472` |
| Salida | normalizada a `{"author", "date", "text"}` en `ado_client.py:455`; `text` es **HTML** | **notas crudas** de la API; `_fetch_notes_raw` (`gitlab_provider.py:463-470`) sólo filtra `system` |
| Claves reales de la nota | — | `body` (Markdown), `author: {name, username, ...}`, `created_at`, `system` — uso vigente en el repo: `gitlab_provider.py:651-653` |
| Paginado | `$top` en la URL (`ado_client.py:439`) | `_request_paginated` hasta `page_cap` páginas (`gitlab_provider.py:465-467`) — **sin tope de ítems** |
| Adjuntos | `{"name","size","url","text_content","mime_type"}` (`ado_client.py:458`, consumido en `ado_context.py:289-293`) | `{"name","url","path"}` — `gitlab_provider.py:526-542`; los saca por **regex de la descripción**, **no descarga contenido** |

⇒ **Comentarios = un normalizador de 3 campos.** **Adjuntos con texto inlineado = una descarga que
el provider no hace hoy.** De ahí el recorte de scope.

---

## 3. Principios y guardarraíles (se verifican en el DoD, §7.4)

- **P1 — Aditivo, nunca sustitutivo.** El camino ADO queda **byte-idéntico**, con **una sola**
  excepción declarada: el enmascarado de secretos de F5, que también lo endurece. Cero cambios en
  los 20+ call sites que hoy llaman a `ado_context`.
- **P2 — Un solo armador de bloques.** El bloque de comentarios se arma **en un solo lugar** para
  los dos trackers. Dos armadores son dos oportunidades de divergir: el primer bug de divergencia
  aparecería el día que alguien toque el orden de los comentarios en un solo lado.
- **P3 — Sin resolvedor nuevo.** §2.1.
- **P4 — Un solo constructor de provider:** `get_tracker_provider` (`tracker_provider.py:125`).
  Prohibido `GitLabTrackerProvider(...)` a mano (§2.2).
- **P5 — El tope de comentarios es explícito y está testeado.** GitLab no acepta `top`; sin tope
  del lado de Stacky un issue con 200 notas revienta la ventana de contexto.
- **P6 — Ningún test nuevo toca la BD real ni la red.** `backend/tests/conftest.py` **no aísla la
  base**: sólo setea `STACKY_TEST_MODE` (`:18`) y bloquea el egress no-loopback (`:35`). Un test
  que importe `db`, `app` o `models` escribe en la base **del operador**. Los archivos de test de
  este plan **no importan `db`, ni `app`, ni `models`**: usan `types.SimpleNamespace` y
  `monkeypatch`.
- **P7 — Human-in-the-loop y mono-operador.** El plan no agrega pantallas, ni decisiones, ni auth,
  ni roles. `403` en Stacky significa "flag apagada", nunca "permiso".
- **P8 — Trabajo del operador: ninguno.** Repetido en cada fase.
- **P9 — Backward-compatible.** Con la flag de F6 apagada, o con `STACKY_GITLAB_ENABLED=false`, el
  comportamiento vuelve al de hoy, y el motivo queda **escrito en `stats`** (no en silencio).

### 3.6 Frontera con los planes 287 y 288 (sesión paralela VIVA)

Los planes **287** (ficha de ticket a pantalla completa) y **288** (vista del ticket + selector de
modelos) los está trabajando **otra sesión, en el mismo árbol**, y commitea cada pocos minutos.

- **287** toca `api/tickets.py`, `services/provider_coupling_audit.py` y el frontend, y agrega
  `tests/test_plan287_ficha_ticket.py` — **ya registrado** en los dos ratchets (última entrada de
  ambos arrays al 2026-08-02).
- **288** toca el frontend y el catálogo de modelos.

**Ninguno de los dos toca los archivos de este plan** (`services/ado_context.py`,
`services/context_enrichment.py`, `services/claude_code_cli_runner.py`,
`services/codex_cli_runner.py`, `agent_runner.py`). **La única frontera real son los dos scripts
de ratchet**, que los tres planes editan. Por eso §4.3 obliga a anclar por **símbolo** y a releer
la cola del array en el momento de editar.

**Prohibido** en toda la implementación: `git stash`, `git reset`, `git rebase`, `git amend`,
`git checkout` de archivos, y commitear con `git commit` sin pathspec. Siempre
`git commit -- "<ruta>" ...` con las rutas propias, y `git status --short` antes de cada commit.

---

## 4. Decisiones transversales que valen para TODAS las fases

### 4.1 Entorno y comandos exactos

**Medido el 2026-08-02:** los **dos** venvs tienen las dependencias
(`import pytest, flask, sqlalchemy` da `ok` en ambos) y producen **resultados idénticos** en las 16
suites medidas en §4.6.

- `backend/.venv/Scripts/python.exe` → **Python 3.13.5**
- `backend/venv/Scripts/python.exe` → **Python 3.11.9**

**Usá `.venv` (3.13.5)** — un solo intérprete para todo el plan, que es con el que se tomaron los
baselines de §4.6. (El Plan 286 mandaba usar `venv`; da lo mismo, pero **no mezcles**: si empezás
con uno, terminá con ese.)

Todos los comandos se corren **parado en `Stacky Agents/backend`**:

```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
./.venv/Scripts/python.exe -m pytest tests/test_plan289_contexto_por_tracker.py -q
```

**Correr SIEMPRE por archivo. Nunca `pytest tests` entero** — la suite completa tiene
contaminación cruzada conocida y **no es un veredicto**.

**Guard anti-falso-verde obligatorio en cada fase.** Un archivo que no colecta nada sale con
**exit 0** y parece verde:

```bash
./.venv/Scripts/python.exe -m pytest tests/test_plan289_<archivo>.py --collect-only -q | tail -3
```

Tiene que imprimir un número **mayor que cero** y **coincidente con el que la fase declara**.

### 4.2 Los tests no tocan la BD ni la red

Ver P6. Concretamente, en este plan:

- El **ticket** se representa con `types.SimpleNamespace(ado_id=..., stacky_project_name=...,
  tracker_type=..., project=...)`.
- El **provider** se representa con una clase local `_FakeProvider` con `fetch_comments(item_id)`.
- La **fábrica** se inyecta con
  `monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda p=None: fake)`.
- El **contexto de proyecto** se inyecta con
  `monkeypatch.setattr("services.project_context.resolve_project_context", lambda *a, **k: ctx)`.
- La **sesión de BD** (sólo en F2) se inyecta como `session_factory=`; **no se importa `db`**.

### 4.3 Ratchets: DOS archivos, sintaxis distinta, registro en la fase que crea el test

Rutas absolutas (verificadas 2026-08-02):

- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\scripts\run_harness_tests.ps1`
- `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\scripts\run_harness_tests.sh`
- allowlist: `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\harness_ratchet_allowlist.txt`
  (208 líneas)

Ambos scripts hacen `cd` a `backend/` antes de correr, así que las rutas van como `tests/...`,
**sin espacios y sin el prefijo `Stacky Agents/`** (los ratchets **no admiten rutas con espacios**).

**Sintaxis — `.ps1`** (array `$HarnessTestFiles`): comillas dobles + **coma final**, salvo la
última entrada del array, que va **sin** coma. Una coma colgante rompió el `.ps1` del Plan 266 y el
propio archivo lo advierte en su comentario de `:867-870`.

```powershell
  "tests/test_plan283_e2e.py",
  "tests/test_plan287_ficha_ticket.py"
)
```

**Sintaxis — `.sh`** (array bash `HARNESS_TEST_FILES`): ruta **pelada**, sin comillas y sin comas.

```bash
  tests/test_plan283_e2e.py
  tests/test_plan287_ficha_ticket.py
)
```

**Anclaje por SÍMBOLO, no por línea.** Al 2026-08-02 la última entrada de **ambos** arrays es
`tests/test_plan287_ficha_ticket.py` (`.ps1:982` cierra con `)`, `.sh:1066` cierra con `)`), pero la
sesión paralela está agregando entradas. **Releé la cola del array antes de editar** y aplicá la
regla: la entrada nueva va **inmediatamente antes de la línea que cierra el array (`)`)**, y en el
`.ps1` hay que **agregarle la coma a la que era la última**.

**Cuatro gates ajenos gobiernan esto** (medidos hoy, todos VERDES):

| Gate | Qué exige | Hoy |
|---|---|---|
| `tests/test_harness_ratchet_meta.py::test_ratchet_no_referencia_archivos_inexistentes` | ninguna ruta registrada puede faltar en disco | **4 passed** en la suite |
| `tests/test_harness_ratchet_meta.py::test_ratchet_clasifica_todos_los_tests` | todo `tests/test_*.py` está en el ratchet **o** en la allowlist | idem |
| `tests/test_harness_ratchet_meta.py::test_allowlist_no_se_solapa_con_ratchet` | **ningún archivo puede estar en los dos** | idem |
| `tests/test_plan259_ratchet_script_parity.py` | paridad `.sh` ↔ `.ps1` y ninguna ruta a archivo inexistente | **12 passed** |

⇒ **Regla dura: cada fase registra, en los DOS ratchets, sólo el archivo que ESA fase crea, en el
MISMO commit.** Registrar por adelantado un archivo que todavía no existe pone **rojas dos suites
ajenas**.

⇒ **Regla dura 2: no registres `tests/test_ado_context.py` ni `tests/test_context_enrichment.py`.**
Están en la allowlist (`harness_ratchet_allowlist.txt:10` y `:55`) y registrarlos sin sacarlos de
ahí rompe `test_allowlist_no_se_solapa_con_ratchet`, que **hoy está verde**. Sacarlos de la
allowlist es una decisión de otro plan.

**Archivos nuevos de este plan y su fase de registro:**

- **F0** registra `tests/test_plan289_contexto_por_tracker.py`.
- **F2** registra `tests/test_plan289_stat_de_contexto.py`.

### 4.4 Impacto por runtime — idéntico en los tres, sin `if runtime`

| Fase | Codex CLI | Claude Code CLI | GitHub Copilot Pro | Fallback |
|---|---|---|---|---|
| F0, F1, F3, F4, F5, F6, F7 | idéntico | idéntico | idéntico | ninguno hace falta: el código vive en `services/`, **por debajo** de la bifurcación de runtime, y se alcanza por el seam común `context_enrichment.enrich_blocks` (`agent_runner.py:809`, `claude_code_cli_runner.py:677`, `codex_cli_runner.py:334`) |
| **F2** | **cambia** (`codex_cli_runner.py:334`) | **cambia** (`claude_code_cli_runner.py:677`) | no cambia — ya persiste (`agent_runner.py:871, 1051`); se le agrega la escritura temprana para que los tres compartan la misma función | la escritura es best-effort: si falla, se loguea `warn` y el run sigue |

**No hay que escribir ni un `if runtime == ...` en todo el plan.**

### 4.5 Trabajo del operador

**Ninguno, en todas las fases.** Sin migración de datos, sin re-configurar proyectos, sin pantallas
nuevas, sin tocar flags a mano (la única flag nace **ON**). El cambio toma efecto en el próximo
arranque del backend, como cualquier cambio de código.

### 4.6 Baselines de no-regresión — MEDIDOS Y CONGELADOS

Medidos el **2026-08-02**, en `docs/plan-279`, con
`./.venv/Scripts/python.exe -m pytest tests/<archivo> -q`, **un archivo por corrida**.

| Suite | Baseline exacto | Fases que la pueden mover |
|---|---|---|
| `tests/test_ado_context.py` | **`9 failed, 8 passed`** ← rojo AMBIENTAL, ver §4.7 | **F1** (pasa a `17 passed`), F5, F6 |
| `tests/test_context_enrichment.py` | `8 passed` | F2 |
| `tests/test_context_enrichment_client_profile.py` | `14 passed` | — (control) |
| `tests/test_acceptance_criteria_injection.py` | `9 passed` | — (control; §6.2) |
| `tests/test_ado_blocker_block.py` | **medilo en F0** y anotalo acá | F5 (extracción del armador) |
| `tests/test_block_priorities_contract.py` | **medilo en F0** y anotalo acá | F5/F6 (id de bloque) |
| `tests/test_plan282_publicacion_comentario.py` | `7 passed` | — (control) |
| `tests/test_plan282_censo_paridad.py` | `2 passed` | F4 (archivo nuevo en `services/`) |
| `tests/test_plan282_fabrica_unica.py` | `4 passed` | F4 (usa la fábrica) |
| `tests/test_plan282_assignee_no_borra.py` | `6 passed` | — (control) |
| `tests/test_plan286_tracker_efectivo.py` | `16 passed` | F6 (consume el helper) |
| `tests/test_plan286_ruteo_de_escritura.py` | `13 passed` | F6 |
| `tests/test_plan286_columna_no_rutea.py` | `6 passed` | F6 |
| `tests/test_tracker_provider_conformance.py` | `13 passed` | F4 |
| `tests/test_gitlab_provider.py` | `26 passed` | F3/F4 |
| `tests/test_u1_self_review.py` | `2 passed` | — (control; §6.2) |
| `tests/test_harness_flags.py` | `59 passed` | **F6** (flag nueva) |
| `tests/test_harness_flags_help.py` | **`4 failed, 4 passed`** ← **ROJO DE FÁBRICA** | **F6** — el criterio es **delta CERO** |
| `tests/test_harness_ratchet_meta.py` | `4 passed` | F0/F2 |
| `tests/test_plan259_ratchet_script_parity.py` | `12 passed` | F0/F2 |

> **`tests/test_harness_flags_help.py` está ROJO DE FÁBRICA y no lo rompiste vos.** Los 4 que
> fallan hoy son `test_plain_help_covers_all_registry_keys`,
> `test_plain_help_fields_non_empty_and_bounded`, `test_plain_help_on_off_start_with_si` y
> `test_plain_help_avoids_jargon_denylist`. Es deuda ajena. **No la arregles acá.** El criterio de
> este plan sobre esa suite es **exactamente `4 failed, 4 passed`**, ni mejor ni peor. Igual hay
> que **agregar** la entrada de `PLAIN_HELP` de la flag nueva (F6): omitirla no movería el
> contador, pero dejaría la flag sin explicación en lenguaje llano, que es el propósito del
> archivo.
>
> **`tests/test_harness_flags.py` está VERDE (`59 passed`) y la flag nueva lo puede romper por
> DOS caminos distintos** (`_CURATED_DEFAULTS_ON` y `_CATEGORY_KEYS`). Ver F6.

**Cómo se usa esta tabla:** antes de cada fase que toca una de esas suites, la corrés y verificás
que da el baseline. Después del cambio tiene que dar **el mismo número** (salvo donde la tabla dice
lo contrario). Si da otro, **el cambio rompió algo — no edites el test ajeno**.

### 4.7 El rojo ambiental de `test_ado_context.py` — leelo antes de F0

`build_ado_context_blocks()` se llama en esos tests **sin `project_name`**, así que
`resolve_project_context` cae a su paso 4: **el proyecto activo**
(`project_context.py:417-422`). En esta máquina el proyecto activo es `RIPLEY`
(`backend/data/active_project.json`), cuyo `issue_tracker.type` es `gitlab`
(`backend/projects/RIPLEY/config.json`). Resultado: `build_ado_client` levanta y **9 tests fallan**.

Consecuencias que el implementador tiene que tener presentes:

1. **El baseline `9 failed, 8 passed` es de ESTA máquina.** En una máquina con proyecto activo ADO
   ese archivo da `17 passed`. **Volvelo determinista en F1** para que deje de depender del
   entorno; si no, F5 y F6 no tienen gate de no-regresión utilizable.
2. **Cuando F6 encienda el dispatcher, esos 9 tests seguirían rojos** (con OTRO mensaje de error:
   el camino iría a GitLab, el `_FakeAdoClient` no se usaría y saldría por `TrackerConfigError` o
   por el bloqueo de egress del conftest). Por eso F1 va **antes** que F6: hacerlos deterministas
   los pone verdes **y los mantiene verdes**.

Proyectos y trackers de esta máquina (leídos de `backend/projects/*/config.json`, 2026-08-02):

| Proyecto | `issue_tracker.type` |
|---|---|
| `RIPLEY` (**activo**) | `gitlab` |
| `RSPACIFICO` | `azure_devops` |
| `RSSICREA` | `azure_devops` |
| `B2IMPACT` | *(sin `issue_tracker.type`)* |

### 4.8 El id del ítem: para GitLab es el `iid`, y ya está en `ticket.ado_id`

Éste es el punto que más fácil se equivoca, así que va escrito con su evidencia:

- `services/gitlab_sync.py:144-145`: `external_id = _a_int(item.get("id"))` y
  **`ado_id = _a_int(item.get("iid"))`**. Es decir, en un ticket de GitLab **`ticket.ado_id`
  guarda el `iid`** (el número visible dentro del proyecto), y `external_id` guarda el id global.
- La API de notas de GitLab que usa el provider es
  `/projects/{proj}/issues/{item_id}/notes` (`gitlab_provider.py:466`), que espera el **`iid`**.
- Precedente vivo en el repo: `services/incident_dev_autocommit.py:234` hace
  `get_tracker_provider(project).post_comment(str(ado_id), body)`.
- Verificado contra la BD viva: el ticket con `ado_id=1124` tiene
  `ado_url=https://srvcgit01.imsolutions.local/juanluca.santoliquido/ripley/-/issues/1124`.
  El `iid` de la URL **es** el `ado_id`.

⇒ **El valor que hay que pasarle a `provider.fetch_comments(...)` es `str(ticket.ado_id)`.**
No `external_id`. No `ticket.id`.

### 4.9 Un dato de SQLAlchemy que hace falta y no es obvio

`enrich_blocks` captura el `Ticket` dentro de un `session_scope()` (`context_enrichment.py:86-99`)
y lo usa **después**, ya desacoplado. Eso funciona porque
`db.py:39` construye el `sessionmaker` con **`expire_on_commit=False`**: al cerrar la sesión los
atributos ya cargados **siguen accesibles** en la instancia detached.

⇒ Es **seguro** leer `ticket_obj.tracker_type` y `ticket_obj.stacky_project_name` fuera de la
sesión. **No re-consultes la base** para obtenerlos.

---

## 5. Fases

Orden por dependencia estricta: **F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7**.

- La pata **A** del centinela de F0 (el bloque que hoy no existe) se vuelve verde en **F6**.
- La pata **B** (el contador que se pierde) se vuelve verde en **F2**.

---

### F0 — Los dos centinelas, hoy en rojo, con `xfail(strict=True)`

**Objetivo (1 frase):** dejar escritos, como tests, los dos defectos que este plan cierra, de modo
que el rojo sea real, verificable, y **se convierta solo** en un fallo si alguien los pone verdes
sin sacar el marcador.

**Archivos:**

- **CREA** `backend/tests/test_plan289_contexto_por_tracker.py`
- **EDITA** `backend/scripts/run_harness_tests.ps1` (registro)
- **EDITA** `backend/scripts/run_harness_tests.sh` (registro)

**Por qué `xfail(strict=True)` y no un rojo pelado.** Un archivo de test rojo registrado en el
ratchet deja el ratchet rojo desde F0 hasta F6. Con `@pytest.mark.xfail(strict=True, reason=...)`:

- **Hoy** el test corre, falla, y pytest lo reporta como `xfailed` → la suite sale **verde** y el
  ratchet no se rompe.
- **El día que pase** (F6), pytest lo reporta como `XPASS(strict)` = **FAILED** → obliga a sacar el
  marcador en el mismo commit que lo pone verde. Es un rojo que **se autodenuncia**.
- **`strict=False` NO sirve**: un test que empieza a pasar sale como `xpassed` y **nadie se entera**.

**Cómo se comprueba que el rojo es por la razón correcta (obligatorio, no opcional):**

```bash
# 1. Con el marcador: tiene que decir xfailed, NO xpassed.
./.venv/Scripts/python.exe -m pytest tests/test_plan289_contexto_por_tracker.py -q -rxX

# 2. Sin el marcador: se ve el fallo REAL y hay que leerlo.
./.venv/Scripts/python.exe -m pytest tests/test_plan289_contexto_por_tracker.py --runxfail -q
```

El fallo del paso 2 tiene que ser **la lista de bloques vacía**, y en la salida capturada tiene que
aparecer `ado_client_init_failed: El proyecto 'GITLABTEST' no usa Azure DevOps
(tracker_type=gitlab).`. **Si el fallo es otro (import error, `AttributeError`, fixture rota), el
centinela no está probando nada** y hay que arreglarlo antes de seguir.

**Contenido del archivo — pseudocódigo con casos borde:**

```python
"""Plan 289 — El agente deja de trabajar a ciegas sobre un ticket de GitLab.

PATA A (xfail hasta F6): con un proyecto GitLab, el enriquecimiento produce el
  bloque de comentarios con las notas del issue.
PATA B (xfail hasta F2): los 3 runtimes persisten el contador de enriquecimiento.

NO importa db, ni app, ni models (P6). El ticket es un SimpleNamespace y el
provider es un doble local.
"""
from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Dobles ───────────────────────────────────────────────────────────────────

NOTAS_GITLAB = [
    {"id": 11, "body": "Primera nota del cliente", "system": False,
     "author": {"name": "Ana Perez", "username": "aperez"},
     "created_at": "2026-07-30T10:11:12.000Z"},
    {"id": 12, "body": "Segunda nota con detalle", "system": False,
     "author": {"name": "Beto Diaz", "username": "bdiaz"},
     "created_at": "2026-07-31T09:00:00.000Z"},
    {"id": 13, "body": "Tercera nota", "system": False,
     "author": {"name": "Ana Perez", "username": "aperez"},
     "created_at": "2026-08-01T08:00:00.000Z"},
]


class _FakeGitLabProvider:
    name = "gitlab"

    def __init__(self, notas):
        self._notas = notas
        self.llamadas = []

    def fetch_comments(self, item_id):          # firma REAL de GitLab: SIN top
        self.llamadas.append(item_id)
        return list(self._notas)


def _ctx_gitlab():
    """Doble de ProjectContext con tracker gitlab."""
    return types.SimpleNamespace(
        stacky_project_name="GITLABTEST", tracker_type="gitlab",
        tracker_project="grupo/proyecto", organization=None,
        base_url="https://gitlab.interno", tracker_group="grupo",
        workspace_root=None, auth_path=None, vscode_port=None,
    )


@pytest.fixture
def proyecto_gitlab(monkeypatch):
    """Fija el contexto de proyecto a uno GitLab y devuelve el provider falso.

    Parchea LOS DOS seams por separado a propósito:
      - resolve_project_context: lo consume build_ado_client (project_context.py:505)
      - get_tracker_provider:    lo consumira el dispatcher de F6
    """
    import services.project_context as pc
    import services.tracker_provider as tp

    fake = _FakeGitLabProvider(NOTAS_GITLAB)
    monkeypatch.setattr(pc, "resolve_project_context", lambda *a, **k: _ctx_gitlab())
    monkeypatch.setattr(tp, "get_tracker_provider", lambda project=None: fake)
    return fake


# ── PATA A — el bloque que hoy no existe (verde en F6) ───────────────────────

@pytest.mark.xfail(strict=True, reason="Plan 289 F6 lo pone verde: hoy el enriquecimiento es ADO-only")
def test_un_issue_de_gitlab_con_3_notas_produce_un_bloque_con_las_3(proyecto_gitlab):
    from services.ado_context import build_ado_context_blocks

    ticket = types.SimpleNamespace(
        ado_id=1124, external_id=1124, stacky_project_name="GITLABTEST",
        tracker_type="gitlab", project="grupo/proyecto",
    )
    blocks, stats = build_ado_context_blocks(
        1124, project_name="GITLABTEST", tracker_project="grupo/proyecto", ticket=ticket,
    )

    comentarios = [b for b in blocks if b.get("id") == "ado-comments"]
    assert len(comentarios) == 1, f"esperaba 1 bloque de comentarios, hay {len(comentarios)}: {blocks}"
    contenido = comentarios[0]["content"]
    assert "Primera nota del cliente" in contenido
    assert "Segunda nota con detalle" in contenido
    assert "Tercera nota" in contenido
    assert stats["comments_count"] == 3
    # El id que se le pasa al provider es el iid, que vive en ado_id (§4.8).
    assert proyecto_gitlab.llamadas == ["1124"]


# ── PATA B — el contador que se pierde (verde en F2) ─────────────────────────

_SITIOS_DE_ENRIQUECIMIENTO = (
    # (ruta relativa a backend/, funcion que llama a enrich_blocks)
    ("agent_runner.py", "_run_in_background"),
    ("services/claude_code_cli_runner.py", "_run_in_background"),
    ("services/codex_cli_runner.py", "_run_in_background"),
)
# NOTA (obligatoria, es la trampa de este censo): los nombres de funcion de arriba
# hay que VERIFICARLOS abriendo cada archivo en F0 y corrigiendolos si difieren.
# El censo tiene DOS patas justamente para eso.


def _funcion_del_modulo(ruta_rel: str, nombre: str):
    """Devuelve el nodo AST de la funcion, o None si no existe."""
    arbol = ast.parse((ROOT / ruta_rel).read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) and nodo.name == nombre:
            return nodo
    return None


def _llama_a(nodo, nombre_funcion: str) -> bool:
    """True si dentro del nodo hay una llamada `f(...)` o `mod.f(...)`."""
    for hijo in ast.walk(nodo):
        if not isinstance(hijo, ast.Call):
            continue
        f = hijo.func
        if isinstance(f, ast.Name) and f.id == nombre_funcion:
            return True
        if isinstance(f, ast.Attribute) and f.attr == nombre_funcion:
            return True
    return False


@pytest.mark.parametrize("ruta,funcion", _SITIOS_DE_ENRIQUECIMIENTO)
def test_pata_de_presencia_la_funcion_vigilada_existe(ruta, funcion):
    """Sin esta pata, borrar o renombrar la funcion dejaria el censo verde POR AUSENCIA."""
    assert _funcion_del_modulo(ruta, funcion) is not None, (
        f"{ruta}::{funcion} no existe. El censo de abajo quedaria verde por ausencia, "
        f"no por correccion. Actualiza _SITIOS_DE_ENRIQUECIMIENTO."
    )


@pytest.mark.parametrize("ruta,funcion", _SITIOS_DE_ENRIQUECIMIENTO)
def test_pata_de_presencia_la_funcion_llama_al_pipeline(ruta, funcion):
    """La funcion vigilada es, de verdad, la que enriquece."""
    assert _llama_a(_funcion_del_modulo(ruta, funcion), "enrich_blocks")


@pytest.mark.xfail(strict=True, reason="Plan 289 F2 lo pone verde: hoy 2 de 3 runtimes tiran el stat")
@pytest.mark.parametrize("ruta,funcion", _SITIOS_DE_ENRIQUECIMIENTO)
def test_los_3_runtimes_persisten_el_contador(ruta, funcion):
    assert _llama_a(_funcion_del_modulo(ruta, funcion), "persistir_stats_de_contexto"), (
        f"{ruta}::{funcion} llama a enrich_blocks pero no persiste el contador"
    )
```

**Casos borde que el archivo debe cubrir en F0 y que ya están arriba:**

- Nota con `system: True` → no debe aparecer (lo filtra el provider; se prueba de verdad en F3).
- `ticket.ado_id` es `int`, el provider recibe `str` → el assert
  `proyecto_gitlab.llamadas == ["1124"]` lo fija.
- La función vigilada podría renombrarse → la **pata de presencia** lo grita.

**Antes de commitear F0, verificá los nombres de función.** El pseudocódigo asume
`_run_in_background` en los tres. **Abrí los tres archivos y confirmalo**; si en alguno el nombre es
otro, corregí `_SITIOS_DE_ENRIQUECIMIENTO`. Si no, las dos patas de presencia salen rojas y **eso
es correcto**: te están avisando.

**Registro en los ratchets (en ESTE commit).** `.ps1`: agregarle coma a la última entrada actual e
insertar `  "tests/test_plan289_contexto_por_tracker.py"` antes del `)`. `.sh`: insertar
`  tests/test_plan289_contexto_por_tracker.py` antes del `)`. Precedido, en ambos, por el
comentario de bloque:

```
  # Plan 289 - El agente deja de trabajar a ciegas sobre un ticket de GitLab
```

**Criterio BINARIO de F0** (los 4 comandos, todos desde `backend/`):

```bash
./.venv/Scripts/python.exe -m pytest tests/test_plan289_contexto_por_tracker.py --collect-only -q | tail -3
#   → 10 tests (1 pata A + 3+3 presencia + 3 pata B)

./.venv/Scripts/python.exe -m pytest tests/test_plan289_contexto_por_tracker.py -q
#   → "6 passed, 4 xfailed"   (NUNCA "xpassed": si dice xpassed, el defecto no existe y el plan sobra)

./.venv/Scripts/python.exe -m pytest tests/test_harness_ratchet_meta.py -q
#   → 4 passed

./.venv/Scripts/python.exe -m pytest tests/test_plan259_ratchet_script_parity.py -q
#   → 12 passed
```

**Flag:** ninguna. Es un archivo de tests.
**Impacto por runtime:** ninguno (no toca código de producción). **Fallback:** n/a.
**Trabajo del operador: ninguno.**

---

### F1 — `test_ado_context.py` deja de depender del proyecto activo

**Objetivo (1 frase):** que el archivo de tests del módulo que este plan modifica sea
**determinista**, para que F5 y F6 tengan un gate de no-regresión que signifique algo.

**Archivo:** **EDITA** `backend/tests/test_ado_context.py`. **Nada más.**

**Qué se cambia y qué NO.** **No se toca ni un assert.** Se agrega **una sola fixture autouse** que
fija el contexto de proyecto a uno de Azure DevOps sintético, para que `build_ado_client` no caiga
al proyecto activo del operador (§4.7):

```python
@pytest.fixture(autouse=True)
def _proyecto_ado_determinista(monkeypatch):
    """Plan 289 F1 — Estos tests llamaban a build_ado_context_blocks() SIN project_name,
    asi que resolve_project_context caia al PROYECTO ACTIVO del operador
    (project_context.py:417-422). En una maquina con proyecto activo GitLab, 9 de los 17
    fallaban con 'no usa Azure DevOps'. El rojo no era del modulo: era del entorno.
    Esta fixture fija un contexto ADO sintetico y no cambia ningun assert.
    """
    import types

    import services.project_context as pc

    ctx = types.SimpleNamespace(
        stacky_project_name="ADOTEST", tracker_type="azure_devops",
        tracker_project="ProyectoADO", organization="orgtest",
        base_url=None, tracker_group=None, workspace_root=None,
        auth_path=None, vscode_port=None,
    )
    monkeypatch.setattr(pc, "resolve_project_context", lambda *a, **k: ctx)
```

**Casos borde:**

- La fixture tiene que ir **antes** de `patch_client` en el orden de resolución. Como `patch_client`
  es una fixture *pedida por parámetro* y ésta es `autouse`, pytest resuelve la `autouse` primero.
  Si aun así hubiera un problema de orden, la señal es un test que sigue fallando con el mensaje
  `no usa Azure DevOps` — no la ignores.
- `monkeypatch.setattr(pc, "resolve_project_context", ...)` funciona porque `build_ado_client`
  llama a `require_project_context` (`project_context.py:505`) **dentro del mismo módulo**, así que
  resuelve el símbolo por atributo del módulo en cada llamada.
- **No** parchees `build_ado_client` entero: eso taparía la línea `:521-524`, que es justamente lo
  que hace falta ejercitar.
- **No** toques `harness_ratchet_allowlist.txt` (§4.3, regla dura 2).

**Criterio BINARIO:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_ado_context.py -q
#   ANTES: 9 failed, 8 passed
#   DESPUES: 17 passed        ← exacto, ni uno mas ni uno menos

./.venv/Scripts/python.exe -m pytest tests/test_ado_context.py --collect-only -q | tail -3
#   → 17 tests   (si baja de 17, borraste un test sin querer)
```

**Flag:** ninguna — es un archivo de tests.
**Impacto por runtime:** ninguno. **Fallback:** n/a.
**Trabajo del operador: ninguno.**

---

### F2 — El contador de enriquecimiento sobrevive en los 3 runtimes

**Objetivo (1 frase):** que los tres runtimes persistan `metadata["ado_context"]` llamando a **una
sola función compartida**, para que la métrica de este plan (K2/K3/K4) sea medible.

**Archivos:**

- **EDITA** `backend/services/context_enrichment.py` — agrega `persistir_stats_de_contexto`.
- **EDITA** `backend/services/claude_code_cli_runner.py` — línea `:677`.
- **EDITA** `backend/services/codex_cli_runner.py` — línea `:334`.
- **EDITA** `backend/agent_runner.py` — línea `:809`.
- **CREA** `backend/tests/test_plan289_stat_de_contexto.py`.
- **EDITA** los DOS ratchets (registro del archivo nuevo).

**Tests PRIMERO.** `backend/tests/test_plan289_stat_de_contexto.py`:

```python
"""Plan 289 F2 — el contador de enriquecimiento se persiste igual en los 3 runtimes.

NO importa db: la sesion se inyecta por session_factory (P6).
"""
from __future__ import annotations

import contextlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class _FilaFalsa:
    def __init__(self, md=None):
        self.metadata_dict = md if md is not None else {}


class _SesionFalsa:
    def __init__(self, fila):
        self._fila = fila
        self.gets = []

    def get(self, modelo, pk):
        self.gets.append((modelo, pk))
        return self._fila


def _factory(fila):
    @contextlib.contextmanager
    def _f():
        yield _SesionFalsa(fila)
    return _f


def test_escribe_la_clave_ado_context_sin_pisar_lo_que_ya_habia():
    from services.context_enrichment import persistir_stats_de_contexto

    fila = _FilaFalsa({"runtime": "codex_cli", "vscode_agent_filename": "X.agent.md"})
    ok = persistir_stats_de_contexto(
        execution_id=42, stats={"comments_count": 3, "errors": []},
        session_factory=_factory(fila),
    )
    assert ok is True
    assert fila.metadata_dict["ado_context"] == {"comments_count": 3, "errors": []}
    assert fila.metadata_dict["runtime"] == "codex_cli"          # no piso lo previo
    assert fila.metadata_dict["vscode_agent_filename"] == "X.agent.md"


def test_stats_none_no_escribe_nada():
    """ado_id ausente -> enrich_blocks devuelve None; no se inventa una clave vacia."""
    from services.context_enrichment import persistir_stats_de_contexto

    fila = _FilaFalsa({"runtime": "claude_code_cli"})
    assert persistir_stats_de_contexto(
        execution_id=1, stats=None, session_factory=_factory(fila)) is False
    assert "ado_context" not in fila.metadata_dict


def test_execution_id_none_no_explota():
    from services.context_enrichment import persistir_stats_de_contexto

    fila = _FilaFalsa()
    assert persistir_stats_de_contexto(
        execution_id=None, stats={"comments_count": 1}, session_factory=_factory(fila)) is False


def test_fila_inexistente_no_explota():
    from services.context_enrichment import persistir_stats_de_contexto

    @contextlib.contextmanager
    def _sin_fila():
        yield types.SimpleNamespace(get=lambda *a, **k: None)

    assert persistir_stats_de_contexto(
        execution_id=999, stats={"comments_count": 1}, session_factory=_sin_fila) is False


def test_metadata_dict_none_se_trata_como_dict_vacio():
    from services.context_enrichment import persistir_stats_de_contexto

    fila = _FilaFalsa(None)
    fila.metadata_dict = None
    assert persistir_stats_de_contexto(
        execution_id=7, stats={"comments_count": 0}, session_factory=_factory(fila)) is True
    assert fila.metadata_dict["ado_context"] == {"comments_count": 0}


def test_una_excepcion_de_la_sesion_no_tumba_el_run():
    """Persistir un contador NUNCA puede romper una ejecucion del agente."""
    from services.context_enrichment import persistir_stats_de_contexto

    @contextlib.contextmanager
    def _rompe():
        raise RuntimeError("database is locked")
        yield  # pragma: no cover

    assert persistir_stats_de_contexto(
        execution_id=5, stats={"comments_count": 2}, session_factory=_rompe) is False
```

**Implementación — en `services/context_enrichment.py`, después de `enrich_blocks`:**

```python
def persistir_stats_de_contexto(
    *,
    execution_id: int | None,
    stats: dict | None,
    session_factory=None,
    log: LogFn | None = None,
) -> bool:
    """Plan 289 F2 — Persiste el contador de enriquecimiento en metadata["ado_context"].

    Los 3 runtimes llaman a ESTA funcion. Antes de este plan solo agent_runner lo
    persistia (agent_runner.py:871 y :1051); claude_code_cli_runner.py:677 y
    codex_cli_runner.py:334 asignaban el valor a `_ado_stats` y lo TIRABAN, con lo
    que 173 de 222 ejecuciones de la base no tenian el dato.

    Se escribe TEMPRANO (justo despues de enriquecer) y no al cerrar el run, a
    proposito: si el run muere despues, el dato de contexto igual queda. Idempotente:
    volver a escribirlo con el mismo valor no cambia nada.

    NUNCA levanta. Devuelve True solo si escribio.
    """
    log = log or _noop_log
    if execution_id is None or stats is None:
        return False
    try:
        if session_factory is None:
            from db import session_scope as session_factory  # import local: evita ciclos
        with session_factory() as sesion:
            fila = sesion.get(AgentExecution, execution_id)
            if fila is None:
                return False
            md = dict(fila.metadata_dict or {})
            md["ado_context"] = stats
            fila.metadata_dict = md
        return True
    except Exception as exc:  # noqa: BLE001 — un contador nunca tumba un run
        log("warn", f"no se pudo persistir el contador de contexto: {exc}")
        return False
```

**Cableado — los 3 sitios, con el diff exacto:**

`services/claude_code_cli_runner.py:677`

```diff
-        enriched_blocks, _ado_stats = context_enrichment.enrich_blocks(
+        enriched_blocks, ado_stats = context_enrichment.enrich_blocks(
             ticket_id=ticket_id,
             agent_type=agent_type or "",
             raw_blocks=raw_blocks,
             project_ctx=project_ctx,
             log=log,
         )
+        # Plan 289 F2 — el contador se persiste ACA, no al cerrar: antes se tiraba.
+        context_enrichment.persistir_stats_de_contexto(
+            execution_id=execution_id, stats=ado_stats, log=log,
+        )
```

`services/codex_cli_runner.py:334` — **el mismo diff, palabra por palabra.**

`agent_runner.py:809`

```diff
         raw_blocks, ado_enrich_stats = context_enrichment.enrich_blocks(
             ticket_id=ticket_id,
             agent_type=agent_type,
             raw_blocks=raw_blocks,
             project_ctx=project_ctx,
             log=log,
         )
+        # Plan 289 F2 — paridad: los 3 runtimes escriben por la MISMA funcion. Las
+        # escrituras de :871 y :1051 se conservan (no se tocan): son idempotentes y
+        # sacarlas seria una regresion de un camino que hoy funciona.
+        context_enrichment.persistir_stats_de_contexto(
+            execution_id=execution_id, stats=ado_enrich_stats, log=log,
+        )
```

**Casos borde:**

- `execution_id` **está en scope** en los tres sitios (los dos runners CLI lo usan unas líneas
  antes para armar `run_dir = .../ str(execution_id)`; `agent_runner` lo usa en `:795` para el
  nombre del hilo de heartbeat). **Verificalo igual antes de editar.**
- `enrich_blocks` devuelve `None` como 2º valor cuando el ticket no tiene `ado_id`
  (`context_enrichment.py:1475-1476`). El helper lo trata y no escribe.
- **NO** uses `_mark_terminal(..., metadata={...})` (existe en los dos runners:
  `claude_code_cli_runner.py:3168-3205`, `codex_cli_runner.py:1962-1998`, y mergea con
  `current_md.update(metadata or {})`). Es tentador pero tiene **muchos call sites** (error,
  éxito, cancelación) y habría que tocar todos: una sola omisión deja el dato perdido en ese
  camino.
- El `import db` es **local a la función** para no romper el árbol de imports del módulo.

**Criterio BINARIO:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_plan289_stat_de_contexto.py --collect-only -q | tail -3
#   → 6 tests
./.venv/Scripts/python.exe -m pytest tests/test_plan289_stat_de_contexto.py -q
#   → 6 passed
./.venv/Scripts/python.exe -m pytest tests/test_plan289_contexto_por_tracker.py -q
#   → "6 passed, 4 xfailed" pasa a "9 passed, 1 xfailed"
#     (la PATA B se pone verde: hay que SACARLE el marcador xfail en ESTE commit,
#      o pytest la reporta como XPASS(strict) = FAILED)
./.venv/Scripts/python.exe -m pytest tests/test_context_enrichment.py -q
#   → 8 passed   (baseline §4.6)
./.venv/Scripts/python.exe -m pytest tests/test_harness_ratchet_meta.py -q     # → 4 passed
./.venv/Scripts/python.exe -m pytest tests/test_plan259_ratchet_script_parity.py -q  # → 12 passed
```

**Flag: ninguna, y por qué.** Persistir un contador que el propio código ya calcula no quema
tokens en reposo, no escribe en ningún sistema del operador y no le saca ninguna decisión. Una
flag acá sería una flag ON redundante que cuesta 5 patas y no compra reversibilidad real: el
"rollback" es no escribir una clave de metadata.

**Impacto por runtime:** ver §4.4 — es la única fase que toca los tres archivos de runtime.
**Fallback:** el helper devuelve `False` y loguea `warn`; el run continúa.
**Trabajo del operador: ninguno.**

---

### F3 — El normalizador PURO de notas de GitLab

**Objetivo (1 frase):** traducir una nota cruda de GitLab a la forma canónica que
`ado_context` ya consume, con una función **pura**, sin red, sin provider y sin config.

**Archivos:** **CREA** `backend/services/tracker_context.py`.
**Tests:** se agregan a `backend/tests/test_plan289_contexto_por_tracker.py` (ya registrado en F0).

**La forma canónica** es la que produce `ado_client.fetch_comments` en `ado_client.py:455`:
`{"author": str, "date": str, "text": str}`. Este plan le agrega **una clave nueva y opcional**,
`"is_html"`, cuya **ausencia significa `True`** — así el camino ADO queda byte-idéntico.

**Por qué `is_html` no es opcional como decisión.** Los comentarios de ADO son **HTML** y
`ado_context._html_to_text` (`:131`) les saca los tags. Los de GitLab son **Markdown**. Pasar
Markdown por `_html_to_text` **borra texto**: un comentario que diga `List<int>` o
`<NombreDelCampo>` pierde ese fragmento, porque el `HTMLParser` lo interpreta como un tag. Es una
pérdida silenciosa de contexto técnico, que es justo lo que este plan viene a arreglar.

**Tests PRIMERO** (agregar al archivo de F0):

```python
# ── F3 — normalizador puro ───────────────────────────────────────────────────

def test_normaliza_una_nota_completa():
    from services.tracker_context import normalizar_notas_gitlab

    out = normalizar_notas_gitlab([NOTAS_GITLAB[0]])
    assert out == [{
        "author": "Ana Perez",
        "date": "2026-07-30",          # created_at recortado a 10, igual que ADO
        "text": "Primera nota del cliente",
        "is_html": False,
    }]


def test_autor_cae_a_username_y_despues_a_interrogacion():
    from services.tracker_context import normalizar_notas_gitlab

    solo_username = {"body": "x", "author": {"username": "cdiaz"}, "created_at": "2026-01-02T00:00:00Z"}
    sin_autor = {"body": "y", "created_at": "2026-01-02T00:00:00Z"}
    autor_no_dict = {"body": "z", "author": "texto suelto", "created_at": ""}
    out = normalizar_notas_gitlab([solo_username, sin_autor, autor_no_dict])
    assert [c["author"] for c in out] == ["cdiaz", "?", "?"]


def test_nota_sin_body_se_descarta():
    from services.tracker_context import normalizar_notas_gitlab

    assert normalizar_notas_gitlab([{"body": "", "author": {"name": "A"}},
                                    {"body": "   ", "author": {"name": "A"}},
                                    {"author": {"name": "A"}}]) == []


def test_nota_system_se_descarta_aunque_el_provider_falle_en_filtrarla():
    """Cinturon y tirantes: el provider ya filtra system, pero el normalizador NO confia."""
    from services.tracker_context import normalizar_notas_gitlab

    assert normalizar_notas_gitlab([{"body": "changed title", "system": True,
                                     "author": {"name": "A"}, "created_at": "2026-01-01T00:00:00Z"}]) == []


def test_created_at_vacio_o_ausente_da_cadena_vacia():
    from services.tracker_context import normalizar_notas_gitlab

    out = normalizar_notas_gitlab([{"body": "x", "author": {"name": "A"}},
                                   {"body": "y", "author": {"name": "A"}, "created_at": None}])
    assert [c["date"] for c in out] == ["", ""]


def test_entrada_que_no_es_lista_de_dicts_no_explota():
    from services.tracker_context import normalizar_notas_gitlab

    assert normalizar_notas_gitlab(None) == []
    assert normalizar_notas_gitlab([]) == []
    assert normalizar_notas_gitlab(["texto", 3, None]) == []


def test_el_orden_de_entrada_se_conserva():
    from services.tracker_context import normalizar_notas_gitlab

    out = normalizar_notas_gitlab(NOTAS_GITLAB)
    assert [c["text"] for c in out] == [
        "Primera nota del cliente", "Segunda nota con detalle", "Tercera nota"]
```

**Implementación:**

```python
"""services/tracker_context.py — Plan 289. Contexto de ticket POR PROVEEDOR.

Modulo HERMANO de services/ado_context.py. Su unica responsabilidad es leer los
comentarios de un ticket por la costura de proveedor (get_tracker_provider) y
devolverlos en la FORMA CANONICA que ado_context ya consume, con tope explicito.

NO arma bloques: eso lo hace ado_context, en un solo lugar, para los dos trackers
(P2 del plan). Dos armadores son dos oportunidades de divergir.

PURO respecto de la BD: no importa db, ni models, ni app.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("stacky_agents.tracker_context")

# Tope de comentarios que se traen al contexto. 30 y no otro numero: es EXACTAMENTE
# el `top=30` que usa el camino ADO (services/ado_context.py:229), asi que los dos
# trackers entregan la misma cantidad de contexto.
#
# NO es una flag registrada, a proposito: el modulo hermano ya tiene este idioma
# (ADO_CONTEXT_ATTACH_MAX_TEXT_FILES, ado_context.py:30-32 y :223) y subir este
# numero no es una decision de producto sino una forma de reventar la ventana de
# contexto. La env var existe como valvula de emergencia, no como configuracion.
_DEFAULT_MAX_COMMENTS = 30
_ENV_MAX_COMMENTS = "TRACKER_CONTEXT_MAX_COMMENTS"


def max_comments() -> int:
    raw = (os.environ.get(_ENV_MAX_COMMENTS) or "").strip()
    if not raw:
        return _DEFAULT_MAX_COMMENTS
    try:
        valor = int(raw)
    except ValueError:
        logger.warning(
            "tracker_context — %s='%s' no es int, usando %d",
            _ENV_MAX_COMMENTS, raw, _DEFAULT_MAX_COMMENTS,
        )
        return _DEFAULT_MAX_COMMENTS
    return max(0, valor)


def normalizar_notas_gitlab(notas) -> list[dict]:
    """Nota cruda de GitLab -> forma canonica {author, date, text, is_html}.

    FUNCION PURA. Mapeo (claves reales verificadas en gitlab_provider.py:651-653):
      body       -> text     (Markdown, NO HTML -> is_html=False)
      author.name -> author  (cae a author.username, y despues a "?"; espeja el
                              displayName -> uniqueName -> "?" de ado_client.py:452-453)
      created_at -> date     (recortado a 10 chars, igual que ado_client.py:454)

    Descarta: notas sin texto y notas `system` (el provider ya las filtra en
    gitlab_provider.py:468-469; aca no se confia en eso).
    """
    salida: list[dict] = []
    for nota in notas or []:
        if not isinstance(nota, dict):
            continue
        if nota.get("system"):
            continue
        texto = (nota.get("body") or "").strip()
        if not texto:
            continue
        autor_raw = nota.get("author")
        autor_dict = autor_raw if isinstance(autor_raw, dict) else {}
        autor = (autor_dict.get("name") or autor_dict.get("username") or "?").strip() or "?"
        fecha = (nota.get("created_at") or "")[:10]
        salida.append({"author": autor, "date": fecha, "text": texto, "is_html": False})
    return salida
```

**Criterio BINARIO:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_plan289_contexto_por_tracker.py --collect-only -q | tail -3
#   → 17 tests   (10 de F0 + 7 de F3)
./.venv/Scripts/python.exe -m pytest tests/test_plan289_contexto_por_tracker.py -q
#   → "16 passed, 1 xfailed"   (solo la PATA A sigue en xfail)
./.venv/Scripts/python.exe -m pytest tests/test_gitlab_provider.py -q     # → 26 passed
./.venv/Scripts/python.exe -m pytest tests/test_plan282_censo_paridad.py -q  # → 2 passed
```

> **Por qué `test_plan282_censo_paridad.py` está en el criterio:** F3 agrega un archivo nuevo a
> `services/`, y hay censos por AST que recorren `services/*.py`
> (`services/provider_coupling_audit.py:206 _archivos_censables`). `tracker_context.py` **no debe
> moverlos**, porque el censo de `scan_ado_only_sites` sólo mira funciones que llaman a
> `ADO_BUILDERS` (`provider_coupling_audit.py:125-127, 314-315`) y este módulo **no llama a
> `build_ado_client`**. Si el número cambia, algo se coló.

**Flag:** ninguna — función pura sin consumidor todavía.
**Impacto por runtime:** ninguno (código muerto hasta F6). **Fallback:** n/a.
**Trabajo del operador: ninguno.**

---

### F4 — El lector por proveedor, con tope explícito

**Objetivo (1 frase):** una función que, dado un proyecto y un `item_id`, devuelva los comentarios
**ya normalizados y ya topeados**, por la fábrica única de providers, sin levantar nunca.

**Archivo:** **EDITA** `backend/services/tracker_context.py`.
**Tests:** se agregan a `backend/tests/test_plan289_contexto_por_tracker.py`.

**Tests PRIMERO:**

```python
# ── F4 — lector por proveedor ────────────────────────────────────────────────

def test_lee_los_comentarios_por_la_fabrica_y_los_normaliza(proyecto_gitlab):
    from services.tracker_context import fetch_comentarios_normalizados

    comentarios, stats = fetch_comentarios_normalizados(project_name="GITLABTEST", item_id=1124)
    assert [c["text"] for c in comentarios] == [
        "Primera nota del cliente", "Segunda nota con detalle", "Tercera nota"]
    assert stats == {"comments_count": 3, "comments_truncated": False, "errors": []}
    assert proyecto_gitlab.llamadas == ["1124"]     # str, y es el iid (§4.8)


def test_el_tope_recorta_y_lo_DECLARA(monkeypatch):
    """Un issue con mas notas que el tope entrega EXACTAMENTE el tope, y lo dice."""
    import services.tracker_provider as tp
    from services.tracker_context import fetch_comentarios_normalizados

    muchas = [{"body": f"nota {i}", "system": False, "author": {"name": "A"},
               "created_at": "2026-01-01T00:00:00Z"} for i in range(200)]
    monkeypatch.setattr(tp, "get_tracker_provider", lambda project=None: _FakeGitLabProvider(muchas))

    comentarios, stats = fetch_comentarios_normalizados(project_name="GITLABTEST", item_id=1)
    assert len(comentarios) == 30                     # el default, = top=30 de ADO
    assert stats["comments_count"] == 30
    assert stats["comments_truncated"] is True
    # Se quedan las MAS RECIENTES: las notas vienen mas viejas primero.
    assert comentarios[-1]["text"] == "nota 199"
    assert comentarios[0]["text"] == "nota 170"


def test_el_tope_se_puede_bajar_por_env(monkeypatch):
    import services.tracker_provider as tp
    from services.tracker_context import fetch_comentarios_normalizados

    monkeypatch.setenv("TRACKER_CONTEXT_MAX_COMMENTS", "2")
    monkeypatch.setattr(tp, "get_tracker_provider", lambda project=None: _FakeGitLabProvider(NOTAS_GITLAB))
    comentarios, stats = fetch_comentarios_normalizados(project_name="GITLABTEST", item_id=1)
    assert len(comentarios) == 2
    assert stats["comments_truncated"] is True
    assert [c["text"] for c in comentarios] == ["Segunda nota con detalle", "Tercera nota"]


def test_tope_cero_devuelve_cero_comentarios_sin_error(monkeypatch):
    import services.tracker_provider as tp
    from services.tracker_context import fetch_comentarios_normalizados

    monkeypatch.setenv("TRACKER_CONTEXT_MAX_COMMENTS", "0")
    monkeypatch.setattr(tp, "get_tracker_provider", lambda project=None: _FakeGitLabProvider(NOTAS_GITLAB))
    comentarios, stats = fetch_comentarios_normalizados(project_name="GITLABTEST", item_id=1)
    assert comentarios == []
    assert stats["comments_count"] == 0
    assert stats["errors"] == []


def test_el_master_switch_de_gitlab_apagado_se_DECLARA_no_se_confunde(monkeypatch):
    """STACKY_GITLAB_ENABLED=false NO puede reportarse como un error de Azure DevOps."""
    import services.tracker_provider as tp
    from services.tracker_context import fetch_comentarios_normalizados

    def _explota(project=None):
        raise tp.TrackerConfigError("issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false")

    monkeypatch.setattr(tp, "get_tracker_provider", _explota)
    comentarios, stats = fetch_comentarios_normalizados(project_name="GITLABTEST", item_id=1)
    assert comentarios == []
    assert len(stats["errors"]) == 1
    assert stats["errors"][0].startswith("tracker_provider_unavailable:")
    assert "azure devops" not in stats["errors"][0].lower()      # y NUNCA lo contrario


def test_un_fallo_de_red_del_provider_no_levanta(monkeypatch):
    import services.tracker_provider as tp
    from services.tracker_context import fetch_comentarios_normalizados

    class _Rompe:
        name = "gitlab"
        def fetch_comments(self, item_id):
            raise tp.TrackerApiError(503, "gateway timeout", kind="transient")

    monkeypatch.setattr(tp, "get_tracker_provider", lambda project=None: _Rompe())
    comentarios, stats = fetch_comentarios_normalizados(project_name="GITLABTEST", item_id=1)
    assert comentarios == []
    assert stats["errors"][0].startswith("fetch_comments_failed:")


def test_un_provider_sin_fetch_comments_se_declara_no_se_rompe(monkeypatch):
    import services.tracker_provider as tp
    from services.tracker_context import fetch_comentarios_normalizados

    monkeypatch.setattr(tp, "get_tracker_provider", lambda project=None: object())
    comentarios, stats = fetch_comentarios_normalizados(project_name="GITLABTEST", item_id=1)
    assert comentarios == []
    assert stats["errors"][0].startswith("capability_missing:")
```

**Implementación (agregar a `services/tracker_context.py`):**

```python
def fetch_comentarios_normalizados(
    *, project_name: str | None, item_id, log=None,
) -> tuple[list[dict], dict]:
    """Comentarios de un ticket, por la costura de proveedor, ya normalizados y topeados.

    `item_id` es el id que el proveedor entiende. Para GitLab es el **iid**, que en
    Stacky vive en `Ticket.ado_id` (gitlab_sync.py:145). Se convierte a str porque
    GitLabTrackerProvider.fetch_comments espera str (gitlab_provider.py:472).

    NUNCA levanta. Devuelve (comentarios, stats) donde stats declara el motivo de
    todo lo que no se pudo hacer: un contexto vacio SIN explicacion es el defecto
    que este plan cierra.
    """
    stats: dict = {"comments_count": 0, "comments_truncated": False, "errors": []}

    # Import LOCAL y por MODULO (no `from ... import get_tracker_provider`): los
    # tests parchean el atributo del modulo, y un import por nombre congelaria la
    # referencia al cargar. Mismo motivo por el que tracker_provider.py:121 importa
    # `resolve_project_context` a nivel modulo "para poder parchear en tests".
    from services import tracker_provider as _tp

    try:
        provider = _tp.get_tracker_provider(project_name)
    except Exception as exc:  # noqa: BLE001
        stats["errors"].append(f"tracker_provider_unavailable: {exc}")
        return [], stats

    fetch = getattr(provider, "fetch_comments", None)
    if not callable(fetch):
        stats["errors"].append(
            f"capability_missing: el proveedor '{getattr(provider, 'name', '?')}' "
            f"no expone fetch_comments"
        )
        return [], stats

    try:
        crudos = fetch(str(item_id))
    except Exception as exc:  # noqa: BLE001
        stats["errors"].append(f"fetch_comments_failed: {exc}")
        return [], stats

    comentarios = normalizar_notas_gitlab(crudos)

    tope = max_comments()
    if len(comentarios) > tope:
        # Se conservan las MAS RECIENTES: GitLab devuelve las notas de mas vieja a
        # mas nueva, y el contexto util de un ticket es el final de la conversacion.
        # Es la misma politica que ADO, que pide `order=desc` con $top (ado_client.py:439).
        stats["comments_truncated"] = True
        comentarios = comentarios[len(comentarios) - tope:]

    stats["comments_count"] = len(comentarios)
    if log:
        log("info", f"tracker_context — {len(comentarios)} comentarios "
                    f"(tope={tope}, recortado={stats['comments_truncated']})")
    return comentarios, stats
```

**Casos borde ya cubiertos por los tests:** tope 0, tope por env inválido, provider sin el método,
`TrackerConfigError` del master switch, `TrackerApiError` de red, notas más viejas primero.

**Un caso borde que NO se resuelve acá y hay que saberlo:** `normalizar_notas_gitlab` se llama
incondicionalmente, así que si mañana entra un tercer proveedor por esta función habrá que
despachar el normalizador por `provider.name`. Hoy la fábrica sólo devuelve `azure_devops` o
`gitlab` (`tracker_provider.py:130-164`) y el dispatcher de F6 sólo entra por el camino no-ADO, así
que el único que llega acá es GitLab. **Está declarado en §6.4.**

**Criterio BINARIO:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_plan289_contexto_por_tracker.py --collect-only -q | tail -3
#   → 24 tests
./.venv/Scripts/python.exe -m pytest tests/test_plan289_contexto_por_tracker.py -q
#   → "23 passed, 1 xfailed"
./.venv/Scripts/python.exe -m pytest tests/test_tracker_provider_conformance.py -q  # → 13 passed
./.venv/Scripts/python.exe -m pytest tests/test_plan282_fabrica_unica.py -q         # → 4 passed
```

**Flag:** ninguna — sigue sin consumidor.
**Impacto por runtime:** ninguno todavía. **Fallback:** n/a.
**Trabajo del operador: ninguno.**

---

### F5 — Un solo armador de bloques, con enmascarado de secretos y título honesto

**Objetivo (1 frase):** extraer el armado del bloque de comentarios a **una función pura
compartida** que enmascare secretos y sepa poner el título del tracker correcto, **sin cambiar el
comportamiento del camino ADO salvo por el enmascarado**.

**Archivo:** **EDITA** `backend/services/ado_context.py`.
**Tests:** se agregan a `backend/tests/test_plan289_contexto_por_tracker.py`.

**Decisión 1 — el `id` del bloque NO cambia; el TÍTULO sí.** Esto cierra el punto "el bloque
miente", y la decisión está tomada, no queda ambigua:

- **`id` sigue siendo `"ado-comments"`** para los dos trackers. Motivos concretos y verificables:
  1. `_BLOCK_PRIORITY` lo mapea a **30** (`context_enrichment.py:431`). Un id nuevo caería en
     `_DEFAULT_PRIORITY = 50` (`:434`), es decir **más alto** que `harness-patterns` (45) y
     `ado-similar-tickets` (40): bajo presión de presupuesto se podarían **otros** bloques en vez de
     éste. Sería un cambio de comportamiento silencioso, no una mejora.
  2. El guard de idempotencia depende del id (`ado_context.py:372-373`).
  3. Dos `.agent.md` de producción lo nombran por escrito: `Stacky/agents/Developer.agent.md:178`
     y `Stacky/agents/FunctionalAnalyst.agent.md:51` y `:312`.
  4. `tests/test_ado_blocker_block.py` y `tests/test_block_priorities_contract.py:49` asertan sobre
     ese id.
- **El título pasa a depender del tracker.** ADO conserva **exactamente** `"Comentarios ADO del
  ticket"` (lo asertan `ado_context.py:273` y `tests/test_ado_context.py:127`); GitLab recibe
  `"Comentarios del ticket (GitLab)"`.

**Decisión 2 — el enmascarado se aplica a los DOS caminos.** Es un endurecimiento deliberado del
camino ADO, no un efecto colateral: los comentarios los escriben personas y llegan enteros al
prompt del agente. Se usa `services.secret_masking.mask_token_values` (`:20`), que ya cubre
`ghp_`, `github_pat_`, `glpat-`, `xoxb-`, `xoxp-`, `AKIA` y `eyJhbGciOi` (`:11`).

**Tests PRIMERO:**

```python
# ── F5 — armador compartido ──────────────────────────────────────────────────

def test_el_armador_enmascara_un_token_de_gitlab():
    from services.ado_context import construir_bloques_de_comentarios

    comentarios = [{"author": "A", "date": "2026-01-01",
                    "text": "el token es glpat-AbCdEf1234567890xyz, probalo",
                    "is_html": False}]
    bloques, n = construir_bloques_de_comentarios(comentarios, titulo="X")
    assert n == 1
    contenido = bloques[0]["content"]
    assert "glpat-AbCdEf1234567890xyz" not in contenido
    assert "<posible-secreto-omitido>" in contenido
    assert "probalo" in contenido            # el resto del comentario sobrevive


def test_el_armador_enmascara_tambien_en_el_camino_ADO():
    """El endurecimiento es deliberado y vale para los dos trackers."""
    from services.ado_context import construir_bloques_de_comentarios

    comentarios = [{"author": "A", "date": "2026-01-01",
                    "text": "<p>usa ghp_ABCDEFGHIJKLMNOPQRSTUV para clonar</p>"}]  # sin is_html
    bloques, _ = construir_bloques_de_comentarios(comentarios, titulo="Comentarios ADO del ticket")
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUV" not in bloques[0]["content"]


def test_markdown_de_gitlab_no_pasa_por_el_limpiador_de_html():
    """is_html=False: `List<int>` no se puede perder. Es contexto tecnico."""
    from services.ado_context import construir_bloques_de_comentarios

    comentarios = [{"author": "A", "date": "2026-01-01",
                    "text": "revisar el metodo Get<List<int>>() del repositorio", "is_html": False}]
    bloques, _ = construir_bloques_de_comentarios(comentarios, titulo="X")
    assert "List<int>" in bloques[0]["content"]


def test_html_de_ado_sigue_pasando_por_el_limpiador():
    """Sin is_html (camino ADO): el HTML se limpia, byte-identico a hoy."""
    from services.ado_context import construir_bloques_de_comentarios

    comentarios = [{"author": "A", "date": "2026-01-01", "text": "<p>hola</p><p>chau</p>"}]
    bloques, _ = construir_bloques_de_comentarios(comentarios, titulo="X")
    assert "<p>" not in bloques[0]["content"]
    assert "hola" in bloques[0]["content"] and "chau" in bloques[0]["content"]


def test_el_titulo_es_el_que_se_le_pasa_y_el_id_NO_cambia():
    from services.ado_context import construir_bloques_de_comentarios

    bloques, _ = construir_bloques_de_comentarios(
        [{"author": "A", "date": "", "text": "x", "is_html": False}],
        titulo="Comentarios del ticket (GitLab)")
    assert bloques[0]["id"] == "ado-comments"        # NO se renombra: ver Decision 1
    assert bloques[0]["title"] == "Comentarios del ticket (GitLab)"


def test_comentario_que_queda_vacio_tras_limpiar_no_produce_linea():
    from services.ado_context import construir_bloques_de_comentarios

    bloques, n = construir_bloques_de_comentarios(
        [{"author": "A", "date": "", "text": "<p></p>"}], titulo="X")
    assert bloques == [] and n == 0


def test_sin_comentarios_no_hay_bloque():
    from services.ado_context import construir_bloques_de_comentarios

    assert construir_bloques_de_comentarios([], titulo="X") == ([], 0)
```

**Implementación — refactor de `services/ado_context.py`.**

Se extrae el cuerpo que hoy vive en `:228-275` a una función pura, **conservando el orden exacto**
(primero `ado-blocker` si corresponde, después `ado-comments`) y el separador `"\n\n---\n\n"`:

```python
def construir_bloques_de_comentarios(
    raw_comments: list[dict], *, titulo: str,
) -> tuple[list[dict], int]:
    """Plan 289 F5 — Arma los bloques de comentarios. UNICO armador, los 2 trackers.

    Entrada: comentarios en forma canonica {author, date, text[, is_html]}.
      - `is_html` AUSENTE significa True (camino ADO: byte-identico a antes del plan).
      - `is_html=False` (camino GitLab, Markdown) SALTEA _html_to_text: pasarle
        Markdown al parser de HTML borra fragmentos como `List<int>`.

    Devuelve (bloques, cantidad_de_comentarios_renderizados). Los bloques salen en el
    mismo orden que antes: ado-blocker (si hay) primero, ado-comments despues.

    Plan 289 F5 — todo el texto pasa por mask_token_values ANTES de entrar al bloque.
    Es un endurecimiento DELIBERADO que tambien alcanza a Azure DevOps.
    """
    from services.secret_masking import mask_token_values

    if not raw_comments:
        return [], 0

    def _texto(c: dict) -> str:
        crudo = c.get("text") or ""
        limpio = _html_to_text(crudo) if c.get("is_html", True) else crudo.strip()
        return mask_token_values(limpio)

    bloques: list[dict] = []

    # ── ado-blocker (Plan 133 F3) — se detecta ANTES para que quede primero.
    #    CERO fetch extra: reusa la misma lista.
    try:
        from config import config as _config

        if getattr(_config, "STACKY_ADO_BLOCKER_BLOCK_ENABLED", False):
            from services.business_preflight import BLOCKER_MARKER  # lazy: evita ciclos

            con_marca = [c for c in raw_comments if BLOCKER_MARKER in _texto(c)]
            if con_marca:
                bloqueante = max(con_marca, key=lambda c: (c.get("date") or ""))
                bloques.append({
                    "kind": "text",
                    "id": "ado-blocker",
                    "title": "🚫 Bloqueante técnico detectado (server-side)",
                    "content": (
                        f"Autor: {bloqueante.get('author', '?')}\n"
                        f"Fecha: {bloqueante.get('date', '')}\n\n"
                        f"{_texto(bloqueante)}"
                    ),
                    "priority": "high",
                })
    except Exception as e:  # noqa: BLE001 — best-effort, nunca bloquea el enrich
        logger.warning("ado_context — detección de ado-blocker falló: %s", e)

    lineas: list[str] = []
    for c in raw_comments:
        texto = _texto(c)
        if not texto:
            continue
        lineas.append(f"**{c.get('author', '?')}** ({c.get('date', '')}):\n{texto}")

    if lineas:
        bloques.append({
            "kind": "text",
            "id": "ado-comments",
            "title": titulo,
            "content": "\n\n---\n\n".join(lineas),
        })
    return bloques, len(lineas)
```

Y el bloque `:227-278` de `build_ado_context_blocks` queda:

```python
    # ── Comentarios ──────────────────────────────────────────────────────────
    try:
        raw_comments = client.fetch_comments(ado_id, top=30)
        nuevos, cantidad = construir_bloques_de_comentarios(
            raw_comments, titulo="Comentarios ADO del ticket",
        )
        blocks.extend(nuevos)
        stats["comments_count"] = cantidad
    except Exception as e:
        logger.warning("ado_context — fetch_comments(%s) falló: %s", ado_id, e)
        stats["errors"].append(f"fetch_comments_failed: {e}")
```

**Casos borde / trampas del refactor:**

- **El `ado-blocker` se detectaba sobre `_html_to_text(...)` y ahora se detecta sobre `_texto(...)`,
  que además enmascara.** Es correcto y es lo que se quiere (el marcador no es un secreto), pero
  significa que `tests/test_ado_blocker_block.py` **es el gate de esta extracción**. Medí su
  baseline en F0 y exigí el mismo número.
- **`stats["comments_count"]` ahora es `len(lineas)`**, que es exactamente lo que era antes
  (`ado_context.py:269`). No lo cambies a `len(raw_comments)`: la diferencia son los comentarios
  que quedan vacíos al limpiar, y hay un test ajeno que la ejercita
  (`test_build_blocks_skips_empty_comment_text`).
- **No muevas la sección de adjuntos.** Queda tal cual.
- **No cambies el título de ADO.** `tests/test_ado_context.py:127` lo asserta literal.

**Criterio BINARIO:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_plan289_contexto_por_tracker.py -q
#   → "30 passed, 1 xfailed"
./.venv/Scripts/python.exe -m pytest tests/test_ado_context.py -q               # → 17 passed  (F1)
./.venv/Scripts/python.exe -m pytest tests/test_ado_blocker_block.py -q         # → el baseline de F0
./.venv/Scripts/python.exe -m pytest tests/test_block_priorities_contract.py -q # → el baseline de F0
./.venv/Scripts/python.exe -m pytest tests/test_context_enrichment.py -q        # → 8 passed
```

**Flag:** ninguna. El enmascarado **no lleva flag a propósito**: una flag para "¿enmascaro
secretos?" cuya posición OFF filtra credenciales al prompt de un LLM es una flag que no debería
existir. Si el enmascarado rompiera algo, el rollback es el `git revert` de la fase.

**Impacto por runtime:** idéntico en los 3 (§4.4). **Fallback:** el `try/except` de la detección
de bloqueante se conserva tal cual.
**Trabajo del operador: ninguno.**

---

### F6 — La flag y el dispatcher: el camino se enciende

**Objetivo (1 frase):** que `build_ado_context_blocks`, cuando el proyecto **no** es Azure DevOps,
delegue la lectura de comentarios en `tracker_context` en vez de morir construyendo un cliente de
ADO.

**Archivos:**

- **EDITA** `backend/config.py` (pata 1)
- **EDITA** `backend/services/harness_flags.py` (patas 2 y 3)
- **EDITA** `backend/services/harness_flags_help.py` (pata 5)
- **EDITA** `backend/tests/test_harness_flags.py` (pata 4)
- **EDITA** `backend/services/ado_context.py` (el dispatcher)
- **EDITA** `backend/tests/test_plan289_contexto_por_tracker.py` (**sacar el `xfail` de la PATA A**)

#### 6.1 La flag: `STACKY_TRACKER_CONTEXT_ENABLED`, **default ON**

**Por qué ON, con la categoría escrita en la línea:** leer los comentarios de un issue es una
operación de **solo lectura**. No quema tokens en reposo (sólo corre cuando el operador lanza una
ejecución, y no hay daemon que la dispare) y no escribe en ningún sistema real del operador ni le
saca ninguna decisión. **No cae en (A) ni en (B) ⇒ nace ON.**

**Por qué existe la flag, si el 286 argumentó contra las flags redundantes:** porque acá sí compra
algo que no existe. Es un **camino de red nuevo en el trayecto caliente de toda ejecución** sobre
un proyecto GitLab, contra una instancia self-hosted. Ninguna flag vigente tiene esa semántica:
`ruteo_estricto_por_tracker()` gobierna el **ruteo de escritura** (Plan 281/286) y
`STACKY_GITLAB_ENABLED` es el master switch del **puerto entero** — apagarlo mata mucho más que
esto.

**Las 5 patas, con archivo y símbolo exactos.** Las cinco van en **el mismo commit**.

| # | Archivo | Qué se agrega |
|---|---|---|
| 1 | `backend/config.py` | `STACKY_TRACKER_CONTEXT_ENABLED = os.getenv("STACKY_TRACKER_CONTEXT_ENABLED", "true").lower() == "true"` — nótese **`"true"`**: es el default EFECTIVO |
| 2 | `backend/services/harness_flags.py` → `FLAG_REGISTRY` | una `FlagSpec` con **`default=True`** |
| 3 | `backend/services/harness_flags.py` → `_CATEGORY_KEYS` (`:120`) | la key dentro de la tupla de `"paridad_proveedores"` (`CategorySpec` en `:112`) |
| 4 | `backend/tests/test_harness_flags.py` → `_CURATED_DEFAULTS_ON` (`:467-1099`) | la key |
| 5 | `backend/services/harness_flags_help.py` → `PLAIN_HELP` (`:25`) | una entrada `PlainHelp(what=…, on_effect=…, off_effect=…, example=…)` |

**Las patas 3 y 4 no son opcionales y cada una rompe un test distinto**, y los dos están **verdes**
hoy (`test_harness_flags.py` = `59 passed`):

- sin la pata 4 → `test_default_known_only_for_curated` (`test_harness_flags.py:1174-1183`) falla,
  porque exige `{s.key for s in FLAG_REGISTRY if default_is_known(s)} == _CURATED_DEFAULTS_ON`
  **exactamente**;
- sin la pata 3 → `test_every_registry_flag_is_categorized` (`test_harness_flags.py:1102`) falla.

**Regla mecánica que no se puede violar:** `default_is_known(spec)` es `spec.default is not None`.
Por eso una flag **OFF** se declara **sin** `default=` en su `FlagSpec` (ni siquiera
`default=False`) y con `os.getenv(KEY, "false")` en `config.py`. **Esta flag es ON**, así que lleva
`default=True` **y** entrada en `_CURATED_DEFAULTS_ON`.

**Texto literal de la `FlagSpec` (pata 2):**

```python
    FlagSpec(
        key="STACKY_TRACKER_CONTEXT_ENABLED",
        type="bool",
        label="Comentarios del ticket en el contexto del agente (GitLab)",
        description=(
            "Plan 289 — Cuando el proyecto no usa Azure DevOps, Stacky lee los "
            "comentarios del ticket por la costura de proveedor y los inyecta al "
            "contexto del agente, igual que ya hace con Azure DevOps. Solo LECTURA: "
            "no escribe nada en el tracker. Apagarla devuelve el comportamiento "
            "previo al plan (el agente trabaja sin los comentarios del issue)."
        ),
        group="global",
        env_only=False,
        # Curada en _CURATED_DEFAULTS_ON (test_default_known_only_for_curated).
        default=True,
    ),
```

**Texto literal de `PLAIN_HELP` (pata 5).** El archivo tiene un gate que exige que `on_effect` y
`off_effect` **empiecen con `"Si "`** (sin tilde) — `test_plain_help_on_off_start_with_si`:

```python
    "STACKY_TRACKER_CONTEXT_ENABLED": PlainHelp(
        what="Hace que el agente lea los comentarios del ticket también cuando el proyecto usa GitLab, no solo con Azure DevOps.",
        on_effect="Si la activás: antes de trabajar, el agente ve lo último que se conversó en el ticket, así que no vuelve a preguntar lo que ya está respondido.",
        off_effect="Si la apagás: el agente arranca sin los comentarios del ticket de GitLab, igual que antes de este cambio.",
        example="Como leer los mensajes anteriores de una conversación antes de contestar, en vez de responder viendo solo el asunto.",
    ),
```

> **Aviso:** `tests/test_harness_flags_help.py` está **ROJO DE FÁBRICA** (`4 failed, 4 passed`,
> §4.6). Agregar la entrada correctamente **no lo pone verde** y **no lo empeora**. El criterio de
> esta fase sobre esa suite es **delta CERO**.

#### 6.2 El dispatcher

Va **arriba de todo** en `build_ado_context_blocks`, antes del `try` que construye el cliente ADO
(hoy `ado_context.py:209`):

```python
    # ── Plan 289 F6 — dispatcher por tracker. ADITIVO: si el proyecto es ADO
    #    (o la flag esta apagada) el resto de la funcion corre BYTE-IDENTICO.
    #    PROHIBIDO leer `ticket.tracker_type` para decidir: la columna miente
    #    (Plan 281/286). Se pregunta al helper del Plan 286.
    try:
        from config import config as _cfg289

        if getattr(_cfg289, "STACKY_TRACKER_CONTEXT_ENABLED", True):
            from services.project_context import (
                tracker_efectivo_de_ticket,
                tracker_is_azure_devops,
            )

            if ticket is not None:
                _tracker = tracker_efectivo_de_ticket(ticket)
                _es_ado = _tracker == "azure_devops"
            else:
                # Sin ticket no hay a quien preguntarle la precedencia completa;
                # el resolvedor canonico por nombre de proyecto alcanza y conserva
                # el fail-closed a ADO del Plan 281 (project_context.py:63-65).
                _es_ado = tracker_is_azure_devops(project_name)

            if not _es_ado:
                return _bloques_por_proveedor(
                    item_id=ado_id, project_name=project_name, stats=stats,
                )
    except Exception as e:  # noqa: BLE001 — el dispatcher NUNCA tumba el enrich
        logger.warning("ado_context — dispatcher por tracker falló: %s", e)
        stats["errors"].append(f"tracker_dispatch_failed: {e}")
```

Y la rama no-ADO, en el mismo módulo:

```python
def _bloques_por_proveedor(
    *, item_id: int, project_name: str | None, stats: dict,
) -> tuple[list[dict], dict]:
    """Plan 289 F6 — rama no-ADO: comentarios por la costura de proveedor.

    Los ADJUNTOS quedan fuera a proposito (§6.1 del plan 289): el proveedor de
    GitLab no descarga contenido, solo saca links por regex de la descripcion
    (gitlab_provider.py:526-542). `attachments_count` se queda en 0 y se DECLARA
    el motivo, para que un 0 no se confunda con un fallo.
    """
    from services import tracker_context

    comentarios, cstats = tracker_context.fetch_comentarios_normalizados(
        project_name=project_name, item_id=item_id,
    )
    bloques, cantidad = construir_bloques_de_comentarios(
        comentarios, titulo="Comentarios del ticket (GitLab)",
    )
    stats["comments_count"] = cantidad
    stats["comments_truncated"] = cstats.get("comments_truncated", False)
    stats["errors"].extend(cstats.get("errors") or [])
    stats["attachments_skipped_reason"] = "provider_sin_descarga_de_adjuntos"
    return bloques, stats
```

**Casos borde:**

- **`ticket=None`.** Pasa en el flujo *epic-from-brief*. Se resuelve por nombre de proyecto, y si
  tampoco hay, `tracker_is_azure_devops` devuelve `True` (fail-closed, `project_context.py:63-65`)
  ⇒ camino de hoy. **Correcto y deliberado.**
- **Flag apagada** ⇒ ni se importa `tracker_context`; camino byte-idéntico.
- **`STACKY_GITLAB_ENABLED=false`** ⇒ `get_tracker_provider` levanta `TrackerConfigError` y F4 lo
  devuelve como `tracker_provider_unavailable: …`, **no** como un error de Azure DevOps. Ojo con
  esto: el default en código de esa flag es **`false`** (`config.py:1291-1298`), y en esta máquina
  está en `true` por `backend/.env:7`. En un deploy nuevo el camino queda apagado **y lo dice**.
- **Un `Exception` en el dispatcher** no tumba el enrich: se anota en `stats["errors"]` y sigue el
  camino ADO. Es la degradación honesta.
- El `except` de `:217-220` **se conserva tal cual**: sigue siendo la red de contención del camino
  ADO real (PAT vencido, org mal configurada).

**Quitar el `xfail` de la PATA A en ESTE commit.** Si no, `strict=True` la reporta como
`XPASS(strict)` = **FAILED**.

**Criterio BINARIO:**

```bash
./.venv/Scripts/python.exe -m pytest tests/test_plan289_contexto_por_tracker.py -q
#   → "31 passed"   (cero xfailed: la PATA A ya no lleva marcador)
./.venv/Scripts/python.exe -m pytest tests/test_ado_context.py -q            # → 17 passed
./.venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q          # → 60 passed (59 + la key nueva no suma test; si sigue en 59, tambien vale: lo que NO puede haber es un failed)
./.venv/Scripts/python.exe -m pytest tests/test_harness_flags_help.py -q     # → 4 failed, 4 passed  (delta CERO)
./.venv/Scripts/python.exe -m pytest tests/test_plan286_tracker_efectivo.py -q   # → 16 passed
./.venv/Scripts/python.exe -m pytest tests/test_plan286_ruteo_de_escritura.py -q # → 13 passed
./.venv/Scripts/python.exe -m pytest tests/test_plan286_columna_no_rutea.py -q   # → 6 passed
./.venv/Scripts/python.exe -m pytest tests/test_context_enrichment.py -q         # → 8 passed
```

> El conteo de `test_harness_flags.py` puede quedar en 59 (agregar una key a un `set` no crea un
> test). **El criterio duro es `0 failed`.** Si aparece un `failed`, es la pata 3 o la 4.

**Impacto por runtime:** idéntico en los 3 (§4.4).
**Fallback:** flag OFF → comportamiento previo; provider no disponible → `stats["errors"]` con el
motivo y camino ADO.
**Trabajo del operador: ninguno** (la flag nace ON).

---

### F7 — Documentación, métrica y cierre

**Objetivo (1 frase):** dejar el módulo documentado, la métrica declarada con su método de medición
y el barrido final de no-regresión corrido.

**Archivos:**

- **EDITA** `backend/services/README_ado_context.md` — la tabla de `:50` y el ejemplo de `:59`
  siguen diciendo que `ado-comments` es sólo de ADO. Agregar: (a) el dispatcher por tracker,
  (b) el título distinto por tracker con el mismo id y **por qué**, (c) el enmascarado, (d) el tope
  y su env var, (e) que los adjuntos son ADO-only.
- **EDITA** este mismo documento: sección `## 10. IMPLEMENTADO` con el resultado medido por fase.

**Método de medición de la métrica de campo (K4).** Se corre **después** de un uso real, contra una
**copia read-only** de la base:

```bash
# 1. copiar la base a un temporal (NUNCA consultar la viva)
cp "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/data/stacky_agents.db" "$SCRATCH/ro.db"

# 2. contar
python - "$SCRATCH/ro.db" <<'EOF'
import json, sqlite3, sys
con = sqlite3.connect(sys.argv[1]); con.row_factory = sqlite3.Row
q = """select e.metadata_json md from agent_executions e
       join tickets t on t.id = e.ticket_id
       where t.stacky_project_name in (select 'RIPLEY')"""
tot = con_ac = con_com = 0
for r in con.execute(q):
    try: m = json.loads(r["md"] or "{}")
    except Exception: m = {}
    tot += 1
    ac = m.get("ado_context")
    if ac is not None:
        con_ac += 1
        if (ac or {}).get("comments_count", 0) > 0: con_com += 1
print(f"total={tot} con_ado_context={con_ac} comments_count>0={con_com}")
EOF
```

**Baseline de esa consulta, medido el 2026-08-02: `total=15 con_ado_context=0 comments_count>0=0`.**

**Meta declarable:** de las ejecuciones **posteriores al deploy de este plan** sobre issues de
GitLab **que tengan al menos un comentario**, **> 80 %** con `comments_count > 0`. El `< 100 %` es
honesto: hay ejecuciones que se saltean el enriquecimiento por `agent_type`
(`ado_context.is_enrichment_enabled`, `:119-128` — `incident_dev` no está en la lista) y ésas van a
seguir dando 0 legítimamente.

**Smoke manual (requiere backend levantado y token de GitLab; NO es un test):**

1. Con el proyecto activo en `RIPLEY`, lanzar un agente `technical` sobre un issue **que tenga
   comentarios** (p. ej. `ado_id=1120`, `RF-001`).
2. En los logs de la corrida tiene que aparecer
   `tracker_context — N comentarios (tope=30, recortado=False)`.
3. En la ficha de la ejecución, `metadata.ado_context.comments_count` tiene que ser `N > 0`.
4. Repetir con el runtime `codex_cli` y con `github_copilot` (paridad de los 3, §4.4).

**Barrido final de no-regresión — las 20 suites de §4.6, una por una.** Cada una tiene que dar su
baseline, con las tres excepciones que este plan cambia a propósito:
`test_ado_context.py` **9 failed, 8 passed → 17 passed**;
`test_plan289_contexto_por_tracker.py` **31 passed**;
`test_plan289_stat_de_contexto.py` **6 passed**.

**Flag:** ninguna.
**Impacto por runtime:** ninguno (documentación y medición).
**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Por qué es real (evidencia) | Mitigación en el plan |
|---|---|---|---|
| R1 | **Reventar la ventana de contexto.** `GitLabTrackerProvider.fetch_comments` **no acepta `top`** (`gitlab_provider.py:472`) y `_request_paginated` trae hasta `page_cap` páginas | un issue de soporte con 200 notas entra entero al prompt | **F4**: tope de 30 (= el `top=30` de ADO, `ado_context.py:229`), se conservan las más recientes, y se **declara** en `stats["comments_truncated"]`. Tests: `test_el_tope_recorta_y_lo_DECLARA`, `test_el_tope_se_puede_bajar_por_env`, `test_tope_cero_devuelve_cero_comentarios_sin_error` |
| R2 | **Credenciales pegadas en un comentario llegan al prompt del LLM.** `ado_context` **no** llama a `mask_token_values` hoy | los comentarios los escriben personas; `secret_masking.py:11` existe justamente porque pasa | **F5**: el enmascarado va en el armador **compartido**, así que endurece **también ADO**. Riesgo del endurecimiento: romper un test ADO ⇒ el criterio de F5 exige `test_ado_context.py` en `17 passed` y `test_ado_blocker_block.py` en su baseline |
| R3 | **El bloque miente o se rompe la idempotencia.** El título dice "ADO" (`:273`) y el guard de idempotencia depende del id (`:372-373`) | renombrar el id cambia además la prioridad de 30 a 50 (`context_enrichment.py:431` vs `:434`) y rompe 2 `.agent.md` y 2 suites | **F5, Decisión 1, sin ambigüedad**: **id igual, título distinto**. Test: `test_el_titulo_es_el_que_se_le_pasa_y_el_id_NO_cambia` |
| R4 | **La métrica no es medible.** 2 de 3 runtimes tiran el contador (`claude_code_cli_runner.py:677`, `codex_cli_runner.py:334`) | **173 de 222** ejecuciones de la BD viva son `claude_code_cli` y **0** tienen la clave | **F2 va ANTES que la fase que declara la métrica.** El KPI K4 dice explícitamente "sólo declarable con F2 hecha" |
| R5 | **Falsa paridad entre runtimes.** El seam es común pero el contador no | ver R4 | **F2** unifica por **una sola función** (`persistir_stats_de_contexto`) llamada por los tres; el censo de F0 (PATA B) lo vigila con **dos patas** (presencia + llamada) |
| R6 | **Romper Azure DevOps.** 20+ call sites | el 100 % del trabajo productivo de RSPACIFICO pasa por ahí | Dispatcher **aditivo** y **arriba de todo**; con la flag OFF o proyecto ADO no se ejecuta ni un import nuevo. Gates: `test_ado_context.py`, `test_ado_blocker_block.py`, `test_block_priorities_contract.py`, `test_context_enrichment.py` |
| R7 | **Rutear por la columna `tracker_type`.** Es el bug que el 281 y el 286 vinieron a cerrar | `models.py:50` declara `default="azure_devops"`: la columna es ruido | Dispatcher usa `tracker_efectivo_de_ticket` (286) o `tracker_is_azure_devops`. **Prohibido leer la columna**, escrito en el comentario del código |
| R8 | **El id equivocado.** Para GitLab el id del issue es el **iid** | `gitlab_sync.py:145` guarda el `iid` en `ado_id`; `external_id` guarda otro número | §4.8 con la evidencia, y el assert `proyecto_gitlab.llamadas == ["1124"]` |
| R9 | **Perder texto técnico al limpiar HTML sobre Markdown** | `_html_to_text` (`:131`) usa `HTMLParser`: `List<int>` se come | `is_html=False` en el normalizador; test `test_markdown_de_gitlab_no_pasa_por_el_limpiador_de_html` |
| R10 | **El master switch de GitLab apagado se reporta como error del otro proveedor** | es un patrón conocido del repo; `STACKY_GITLAB_ENABLED` tiene default **`false`** en código (`config.py:1291-1298`) | F4 lo captura y lo declara como `tracker_provider_unavailable:`; test `test_el_master_switch_de_gitlab_apagado_se_DECLARA_no_se_confunde` |
| R11 | **Un centinela verde por ausencia.** Si una fase renombra la función vigilada, el censo de la PATA B pasaría sin probar nada | pasó antes en este repo | **Dos patas** en F0: presencia de la función **y** presencia de la llamada. La de presencia **no** lleva `xfail` |
| R12 | **Colisión con la sesión paralela en los ratchets** | 287 y 288 editan los mismos dos archivos y commitean cada pocos minutos | §4.3: anclar por símbolo, releer la cola del array antes de editar, y `git commit -- "<rutas propias>"` con `git status --short` previo |
| R13 | **El rojo de F0 deja el ratchet rojo 6 fases** | el archivo se registra en F0 | `xfail(strict=True)`: hoy sale `xfailed` (suite verde) y el día que pase sale `XPASS(strict)` = FAILED, forzando sacar el marcador |
| R14 | **Latencia extra en el trayecto caliente.** El enriquecimiento agrega N llamadas HTTP a un GitLab self-hosted | `_request_paginated` puede hacer varias páginas | El tope de 30 acota el trabajo útil, pero **no acota las páginas que el provider ya pidió**. Declarado en §6.5 como límite conocido; la flag ON/OFF es el control real |

---

## 7. Fuera de scope (explícito, para que nadie lo agregue de contrabando)

### 6.1 Adjuntos de GitLab en el contexto

**Fuera.** `GitLabTrackerProvider.fetch_attachments` (`gitlab_provider.py:526-542`) devuelve
`{"name", "url", "path"}` sacados por **regex de la descripción del issue**
(`!\[([^\]]*)\]\((/uploads/[^\)]+)\)`), y **no descarga el contenido**. El camino ADO consume
`{"name","size","url","text_content","mime_type"}` (`ado_context.py:289-293`) y el cliente ADO sí
descarga texto hasta 64 KiB (`ado_client.py:458`).

Traer paridad de adjuntos exige: descargar el binario con el token, decidir un tope de bytes,
inferir el mime, manejar imágenes (que no son texto), y un presupuesto de red por corrida. **Es un
plan propio.** Lo que este plan sí hace es **declarar el hueco** en vez de dejar un `0` mudo:
`stats["attachments_skipped_reason"] = "provider_sin_descarga_de_adjuntos"` (F6).

### 6.2 Criterios de aceptación en GitLab

**Fuera, y no es un bug.** `services/acceptance_criteria.resolve` (def `:25`) y
`services/self_review._resolve_criteria` (def `:43`) devuelven `""` para todo tracker no-ADO por un
guard **explícito** del Plan 281 F7, cuyo motivo está escrito en el código:
`Microsoft.VSTS.Common.AcceptanceCriteria` **es un campo de Azure DevOps** y GitLab no tiene un
equivalente de primera clase. Un plan futuro puede decidir mapearlo a una sección del cuerpo del
issue o a una checklist de Markdown; **eso es una decisión de producto, no un arreglo.**

### 6.3 El `ado-blocker` como capacidad declarada de GitLab

**Semi-dentro, sin fase propia.** Cae "gratis": F5 hace que la detección del marcador corra sobre
la **misma lista normalizada**, así que un comentario con el marcador en un issue de GitLab produce
el bloque `ado-blocker` igual que en ADO. **Lo que NO hace este plan** es verificar que eso
satisfaga `stacky_required_blocks: "ado-epic-structured|ado-blocker|run-directive, client-profile"`
de `Stacky/agents/FunctionalAnalyst.agent.md:8` sobre un proyecto GitLab. Es una verificación de
otro eje.

### 6.4 Un tercer proveedor

**Fuera.** `get_tracker_provider` sólo devuelve `azure_devops` o `gitlab`
(`tracker_provider.py:130-164`); `jira` y `mantis` se rechazan por diseño (`:162-164`, y el
docstring del módulo lo dice). Cuando entre un tercero, `fetch_comentarios_normalizados` tendrá que
despachar el normalizador por `provider.name`. **Está anotado en el docstring de F4.**

### 6.5 Cachés, presupuesto de red y paginado

**Fuera.** No se toca `services/ado_read_cache` (el `_inject_ado_context` ya lo usa cuando
`STACKY_ADO_READ_CACHE_TTL_SEC > 0`, `context_enrichment.py:1481-1502`) ni se agrega un tope de
páginas al lado de Stacky. El tope de F4 es de **ítems entregados al prompt**, no de **páginas
pedidas al servidor**.

### 6.6 Renombrar `ado_context` / `ado-comments`

**Fuera.** Ver F5, Decisión 1. Un rename tocaría el mapa de prioridades, el guard de idempotencia,
dos `.agent.md`, dos suites de test y el README. Sin capacidad nueva a cambio.

---

## 8. Glosario, orden de implementación y Definición de Hecho

### 8.1 Glosario (términos de ESTE repo que un modelo menor no conoce)

| Término | Qué es |
|---|---|
| **ContextBlock** | `dict` con `{"kind","id","title","content"}` que se concatena al prompt del agente. **No hay clase `Block`.** |
| **Seam / costura** | Punto único por el que pasa un comportamiento. Acá: `context_enrichment.enrich_blocks` (3 runtimes) y `tracker_provider.get_tracker_provider` (2 trackers). |
| **iid** | Número del issue **dentro** del proyecto GitLab. En Stacky vive en `Ticket.ado_id` (§4.8). |
| **Ratchet** | Los dos scripts `backend/scripts/run_harness_tests.{ps1,sh}` que corren la lista curada de suites. Sintaxis distinta, ya divergen, **no admiten rutas con espacios**. |
| **Rojo de fábrica** | Suite que ya estaba roja antes de tocar nada. El criterio contra ella es **delta cero**, nunca "ponerla verde". |
| **Pata** | Cada archivo que hay que tocar para que una flag exista de verdad. Esta flag tiene **5**. |
| **Runtime** | Motor de ejecución: `github_copilot` (`agent_runner.py`), `claude_code_cli`, `codex_cli`. **No** es lo mismo que `LLM_BACKEND`. |
| **`xfail(strict=True)`** | Marca "esto tiene que fallar". Si pasa, pytest lo reporta **FAILED**. Es un rojo que se autodenuncia. |
| **Forma canónica** | `{"author","date","text"[, "is_html"]}`. La produce `ado_client.fetch_comments` (`:455`) y, desde F3, `tracker_context.normalizar_notas_gitlab`. |

### 8.2 Orden de implementación (estricto)

| Fase | Qué entrega | Commit | Pone verde |
|---|---|---|---|
| F0 | 2 centinelas rojos + registro en los 2 ratchets | `test(plan-289): F0 - los dos centinelas del contexto por tracker` | — |
| F1 | `test_ado_context.py` determinista | `test(plan-289): F1 - el test del contexto deja de depender del proyecto activo` | K7 |
| F2 | el contador en los 3 runtimes | `feat(plan-289): F2 - el contador de contexto sobrevive en los 3 runtimes` | F0 pata B, K2, K3 |
| F3 | normalizador puro | `feat(plan-289): F3 - normalizador de notas de GitLab a la forma canonica` | — |
| F4 | lector por proveedor + tope | `feat(plan-289): F4 - lector de comentarios por la costura de proveedor` | — |
| F5 | armador compartido + enmascarado + título | `feat(plan-289): F5 - un solo armador de bloques, con enmascarado de secretos` | K6 |
| F6 | flag + dispatcher | `feat(plan-289): F6 - el agente lee los comentarios del issue de GitLab` | F0 pata A, K1, K5 |
| F7 | doc + métrica + barrido | `docs(plan-289): F7 - documentacion, metrica y barrido de no-regresion` | K4 |

**Regla de commits:** uno por fase, con `git commit -- "<rutas propias>"`, precedido de
`git status --short`. **Nunca** `push`, `--no-verify`, `amend`, `reset`, `rebase`, `stash`,
`checkout`.

### 8.3 Definición de Hecho (DoD) — binaria, sin interpretación

1. **F0..F7 commiteadas**, una por commit, en ese orden.
2. `tests/test_plan289_contexto_por_tracker.py` → **`31 passed`**, cero `xfailed`, cero `xpassed`.
3. `tests/test_plan289_stat_de_contexto.py` → **`6 passed`**.
4. `tests/test_ado_context.py` → **`17 passed`** (era `9 failed, 8 passed`).
5. Las **20 suites de §4.6** dan su baseline exacto. Las dos rojas de fábrica
   (`test_harness_flags_help.py` = `4 failed, 4 passed`) dan **delta cero**.
6. `tests/test_harness_ratchet_meta.py` = **`4 passed`** y
   `tests/test_plan259_ratchet_script_parity.py` = **`12 passed`** después de **cada** registro.
7. Los **2 archivos nuevos de test** están en **los DOS** ratchets, y **ninguno** de ellos está
   además en `tests/harness_ratchet_allowlist.txt`.
8. La flag `STACKY_TRACKER_CONTEXT_ENABLED` tiene sus **5 patas**, nace **ON**, y
   `tests/test_harness_flags.py` sale con **`0 failed`**.
9. `grep -rn "ticket.tracker_type" services/ado_context.py services/tracker_context.py` → **cero
   resultados** (el ruteo va por el helper del 286, R7).
10. `grep -rn "GitLabTrackerProvider(" services/tracker_context.py` → **cero resultados** (un solo
    constructor, P4).
11. `services/tracker_context.py` **no** importa `db`, `models` ni `app`; los 2 archivos de test
    nuevos tampoco.
12. `README_ado_context.md` actualizado con el dispatcher, el título por tracker, el enmascarado, el
    tope y el hueco de adjuntos.
13. Sección `## 10. IMPLEMENTADO` agregada a este documento con el resultado **medido** por fase.
14. **Trabajo del operador: ninguno.** Sin migración, sin re-configurar proyectos, sin flags que
    tocar a mano.

---

## 9. Tabla de anclajes — verificados el 2026-08-02 abriendo cada archivo

| Anclaje declarado | Estado | Detalle |
|---|---|---|
| `services/ado_context.py:212` `build_ado_client(` | **OK** | |
| `services/ado_context.py:217-220` `except` que traga | **OK** | |
| `services/ado_context.py:229` `fetch_comments(ado_id, top=30)` | **OK** | |
| `services/ado_context.py:272-273` id/título del bloque | **OK** | |
| `services/ado_context.py:371-374` guard de idempotencia | **OK** — línea exacta **`:372-373`** | el `if` está en `:373` |
| `services/ado_client.py:431` `fetch_comments(ado_id, top=20)` | **OK** | el default es `20`, no `30`; el `30` lo pasa `ado_context` |
| `services/ado_client.py:455` normalización a `{author,date,text}` | **OK** | |
| `services/gitlab_provider.py:472` `fetch_comments(item_id)` sin `top` | **OK** | |
| `services/gitlab_provider.py:463-470` `_fetch_notes_raw` | **OK** | |
| `services/gitlab_provider.py:526-544` `fetch_attachments` | **línea real distinta** | el cuerpo va de **`:526` a `:542`** |
| `services/context_enrichment.py:60` `enrich_blocks` | **OK** | |
| `agent_runner.py:809` llamada a `enrich_blocks` | **OK** | |
| `agent_runner.py:871` y `:1051` persistencia de `md["ado_context"]` | **OK** | |
| `services/claude_code_cli_runner.py:677` `_ado_stats` descartado | **OK** | |
| `services/codex_cli_runner.py:334` `_ado_stats` descartado | **OK** | |
| `services/acceptance_criteria.py:42` | **OK la línea, MATIZ en el fondo** | `:42` es exactamente el `if (` del guard (cuerpo `:42-46`, comentario `:38-41`), dentro de `resolve`, def en `:25`. **Pero NO es un `except` que traga: es un `return ""` deliberado del Plan 281 F7.** Ver §6.2 |
| `services/self_review.py:56` | **OK la línea, mismo matiz** | `:56` es el `if (` del guard (cuerpo `:56-60`, comentario `:50-55`), dentro de `_resolve_criteria`, def en `:43`. Mismo carácter deliberado |
| `services/secret_masking.py:20` `mask_token_values` | **OK** | |
| `services/project_context.py:201` `tracker_efectivo_de_ticket` | **OK** | |
| `services/project_context.py:521-524` el `raise AdoConfigError` | **OK** | |
| `services/tracker_provider.py:125` `get_tracker_provider` | **OK** | |
| `services/gitlab_sync.py:144-145` `external_id`=id, `ado_id`=**iid** | **OK** | |
| `models.py:68-77` índice único `(stacky_project_name, tracker_type, external_id)` | **OK** | |
| `db.py:39` `expire_on_commit=False` | **OK** | |
| `backend/scripts/run_harness_tests.ps1` / `.sh` | **OK** | última entrada de ambos: `tests/test_plan287_ficha_ticket.py` |
| `tests/harness_ratchet_allowlist.txt:10` y `:55` | **OK** | `test_ado_context.py` y `test_context_enrichment.py`, `# pendiente-de-triage` |
| `tests/test_harness_flags.py:467-1099` `_CURATED_DEFAULTS_ON` | **OK** | **335 keys** (el docstring que dice "las 12 keys curadas" está **stale**) |
| `tests/test_harness_flags.py:1174-1183` `test_default_known_only_for_curated` | **OK** | |
| `tests/test_harness_flags.py:1102` `test_every_registry_flag_is_categorized` | **OK** | |
| `services/harness_flags.py:20-41` dataclass `FlagSpec` (14 campos) | **OK** | |
| `services/harness_flags.py:112` `CategorySpec("paridad_proveedores", …)` | **OK** | 20 categorías + `otros` |
| `services/harness_flags_help.py:25` `PLAIN_HELP` | **OK** | |
| `config.py:1291-1298` `STACKY_GITLAB_ENABLED` default **`false`** | **OK** | en esta máquina está en `true` por `backend/.env:7` |
