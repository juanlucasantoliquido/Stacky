# Plan 288 — La vista del ticket adelgaza y el selector de modelos deja de mentir

**Estado:** PROPUESTO (v1)
**Fecha:** 2026-08-02
**Rama al escribir:** `docs/plan-279`
**Alcance:** dos ítems pedidos textualmente por el operador, independientes entre sí y en bloques separados.
**Bloque A** — retirar la superficie de "Clasificación" de la vista de tickets (interfaz solamente; cero cambios de datos, cero cambios de servidor).
**Bloque B** — el selector de modelos de Claude Code deja de ofrecer una lista fija que no coincide con la cuenta (servidor + interfaz; cero escrituras nuevas, cero consumo de modelo).
**Antecesores que se reusan, no se re-implementan:** 159 (catálogo único de modelos/efforts), 212 (selector vivo + traza solicitado-vs-efectivo + sonda del programa instalado), 264 (matriz de capacidades por motor), 277 (clasificación local de jerarquía), 287 (ficha del ticket a pantalla completa — **frontera declarada en §7.1**).

> **Todo anclaje `archivo:línea` de este documento se verificó abriendo el archivo el 2026-08-02.** Los hechos externos (versión del programa de línea de comandos de Claude Code, salida de sus subcomandos, contenido de la configuración de la cuenta) se midieron **ejecutando los comandos**, y la salida literal está pegada en §4.4. Donde un número de línea puede correrse porque hay una sesión paralela viva en este árbol, el documento da además el **símbolo**; si el número no coincide, **manda el símbolo**.

---

## 1. Objetivo y KPI

### 1.1 Objetivo

Dos defectos que el operador reportó con sus palabras, y que este plan cierra sin agregarle una sola tarea:

**A. La vista del ticket muestra un bloque que no sirve para gestionar el ticket.** El control de "Clasificación" (tipo local + padre local + publicar etiquetas) se monta en **tres** lugares de la vista de tickets. Ninguno de los tres aporta a la gestión del ticket: son herramientas de curaduría de jerarquía que el plan 277 construyó para un backfill puntual de GitLab. Este plan **las retira de la vista** y **conserva intacto el motor de datos**, porque el motor tiene un consumidor de producción que no es la vista (§2.2).

**B. El selector de modelos de Claude Code ofrece una lista fija que no es la del operador.** El catálogo es un archivo fechado el **2026-07-17** con 4 modelos. La cuenta del operador **ya ejecutó `claude-opus-5`** — 4.321.237 unidades de consumo el 2026-07-28, medido en su propia caché local — y `claude-opus-5` **no está en la lista**. Peor: aunque estuviera, el camino de ejecución lo **degradaría en silencio a `claude-sonnet-5`**, porque la lista de modelos de tier alto autorizados es un literal de un solo elemento que quedó viejo (§4.3). Este plan pone la lista al día, **hace que lo ofrecido sea realmente ejecutable**, agrega una fuente **real y verificada** de "qué modelos tiene esta cuenta", y hace que la pantalla **diga en voz alta** cuándo está mostrando la lista de respaldo.

### 1.2 KPI — todos binarios, todos con comando

| # | KPI | HOY (medido 2026-08-02) | Meta del 288 | Comando que lo mide (desde `Stacky Agents`) |
|---|---|---|---|---|
| **K0** | Montajes de `JerarquiaLocalControl` en la vista de tickets | **2** (`pages/TicketBoard.tsx:713`, `components/TicketGraphView.jsx:486`) | **0** | `grep -c "<JerarquiaLocalControl" frontend/src/pages/TicketBoard.tsx frontend/src/components/TicketGraphView.jsx` |
| **K1** | Montajes de `PublicarEtiquetasGitLab` en la vista de tickets | **1** (`pages/TicketBoard.tsx:1309`) | **0** | `grep -c "<PublicarEtiquetasGitLab" frontend/src/pages/TicketBoard.tsx` |
| **K2** | Acciones de ticket que **siguen** en la tarjeta (no se puede romper nada al retirar) | **4** en `TicketBoard.tsx` (`FinishWorkButton`, `CreateChildTaskButton`, `TicketLocalInsightButton`, `RecoverExecutionButton`) | **4** | `npx vitest run src/__tests__/plan288SuperficieClasificacion.test.ts` |
| **K3** | Motor de datos de la clasificación con consumidor de producción vivo | **1** (`services/gitlab_sync.py:50-54`, contadores `usados_local_tipo` / `usados_local_padre`) | **1** — no se toca | `grep -c "usados_local_tipo" backend/services/gitlab_sync.py` ≥ 1 |
| **K4** | Modelos de la familia Claude 5 que la cuenta usó y el catálogo NO ofrece | **2** (`claude-opus-5`, `claude-fable-5`) | **0** | `.venv/Scripts/python.exe -m pytest tests/test_plan288_catalogo_vivo.py -k paridad -q` |
| **K5** | Modelos ofrecidos por el catálogo que el camino de ejecución **degrada en silencio** | **1 de 4** hoy (`claude-opus-4-8` con `allow_opus=False`, que es el default de todos los caminos salvo elección explícita); **3 de 6** si se agregaran opus-5 y fable-5 sin tocar la lista de autorizados | **0** | `.venv/Scripts/python.exe -m pytest tests/test_plan288_catalogo_vivo.py -k ejecutable -q` |
| **K6** | Fuentes de verdad sobre "qué modelos tiene esta cuenta" leídas por Stacky | **0** (`grep -rn "additionalModelOptionsCache\|stats-cache\|oauthAccount" backend/` → **0 hits**) | **1** (`services/claude_account_models.py`) | `ls "backend/services/claude_account_models.py"` |
| **K7** | Superficies de selección de modelo que avisan "esta es la lista de respaldo" | **0** — `useModelCatalog` **descarta** `fallback_used`: devuelve solo `{catalog, loading}` (`frontend/src/hooks/useModelCatalog.ts:21-24`, `:49`) | **≥ 4** | `grep -rn "AvisoCatalogoModelos" frontend/src \| wc -l` ≥ 4 |
| **K8** | Sondas del programa instalado que hoy **siempre fallan** y nadie lo sabe | **1** (`services/model_probe.py`, 3 candidatos, los 3 dan `unknown option`) | **1, pero con el motivo publicado** en la respuesta y visible en la pantalla | §4.4 + `grep -c "probe" backend/api/agents.py` ≥ 1 |
| **K9** | Deuda de formularios / de interfaz que este plan agrega | — | **0** (solo puede bajar) | `npx vitest run src/__tests__/formDebtRatchet.test.ts` y `src/__tests__/uiDebtRatchet.test.ts` |
| **K10** | Flags nuevas | — | **1**, y nace **ON** | §5 |

---

## 2. Por qué ahora, y qué gap cierra respecto de los planes recientes

### 2.1 Bloque A — la serie 276→287 llenó la pantalla; falta podarla

- El **277** trajo la clasificación local de jerarquía para GitLab: el operador dice de qué tipo es un ticket y de cuál cuelga, **sin escribir en el GitLab de la empresa**. Fue correcto para lo que resolvía: un backfill de jerarquía sobre un GitLab que no tiene modelo de relaciones.
- El **282** y el **286** hicieron que el ruteo por proveedor deje de mentir, y el **287** propone abrir el ticket entero en una ficha a pantalla completa. Es decir: **la vista del ticket está por ganar densidad**, no por perderla.
- Justo por eso este es el momento de sacar lo que no aporta. Un control de curaduría de jerarquía, con dos campos editables y un botón que escribe en el GitLab de la empresa, **no es información de gestión del ticket**: es una herramienta de mantenimiento de datos que se coló en la ficha porque ahí estaba el ticket a mano.
- **El 284 y el 285 dejaron la lección aplicable acá**: verificar el escritor y nunca el lector deja funciones vivas que nadie mira. El espejo de esa lección es este bloque: **hay superficie de interfaz viva que nadie usa y que le cuesta atención al operador en cada ticket que abre**.

### 2.2 El hecho que decide el alcance del Bloque A

`lib/jerarquiaLocal.ts` y el motor del servidor **NO se borran**, y la razón está medida:

| Evidencia | Consecuencia |
|---|---|
| `backend/services/gitlab_sync.py:50-54` define 4 contadores (`usados_local_tipo`, `usados_local_padre`, …) y `:130-133` documenta que la clasificación local **rellena el vacío** cuando GitLab no dice nada | El motor tiene un **consumidor de producción que no es la vista**: la sincronización. Borrarlo cambia el dato que ve el operador en el tablero |
| `backend/api/tickets.py:830` `_clasificacion_local_habilitada()` y `:900` el `PATCH` que persiste | La ruta del servidor sigue existiendo y sigue gateada por su flag del 277 |
| `backend/models.py:57` y `:141` — las columnas locales viajan en `to_dict()` | Retirar la interfaz no cambia ni una clave del contrato |
| `backend/tests/test_plan277_clasificacion_local.py` está registrado en los DOS scripts del arnés (`scripts/run_harness_tests.sh:257`, `scripts/run_harness_tests.ps1:250`) | Como el motor no se toca, **ese archivo no se saca de ningún script**. §6.F10 lo dice explícito para que nadie lo borre "por prolijidad" |
| `frontend/src/__tests__/plan277JerarquiaLocal.test.ts` — sus **8 casos** importan **solo funciones puras de `lib/jerarquiaLocal.ts`** (verificado: `describe`/`it` en `:32,41,54,64,79,91,136,158`) | El archivo de prueba del 277 **queda verde sin tocarlo**. Este plan no borra ni una prueba |

### 2.3 Bloque B — el catálogo quedó viejo y el clamp lo hace peor

- El **159** creó el catálogo único leído de disco con caché por fecha de modificación. Correcto, pero es **un archivo estático**: `backend/config/model_catalog.json` dice `"updated_at": "2026-07-17"`.
- El **212 F6** vio el problema y agregó una sonda al programa instalado (`services/model_probe.py`). La idea es la correcta. **El problema es que los tres subcomandos que prueba no existen** en el programa instalado hoy (§4.4). La sonda está viva, corre en producción con su flag en ON, y **siempre devuelve `no_candidate_worked`**. Sus pruebas (`tests/test_plan212_model_probe.py`) la ejercitan con dobles, así que están verdes y no revelan nada: es el caso de libro de **prueba verde sobre una capacidad muerta**.
- El **264** cerró el "modelo y effort elegibles en todo punto de uso" y montó `runtime_capabilities.capabilities_for`, que **pisa** la lista de modelos en la respuesta (`backend/api/agents.py:1495`). Es una capa más entre el archivo y la pantalla que hay que respetar.
- Lo que ninguno de los tres cerró: **que lo ofrecido sea ejecutable**, y **que la pantalla diga cuándo está mostrando el respaldo**.

---

## 3. Principios y guardarraíles (se verifican en el DoD)

1. **Human-in-the-loop innegociable.** Este plan **no agrega ni un solo camino de escritura nuevo**. El Bloque A **quita** un botón que escribía en el GitLab de la empresa; el Bloque B solo **lee** (archivos locales y el archivo de catálogo). Ningún cambio decide nada por el operador.
2. **Mono-operador, sin autenticación real.** No hay roles ni permisos. `403` significa **flag apagada**, nunca permiso, y el cuerpo lo dice: `{"error": "feature_disabled"}`.
3. **Cero trabajo extra para el operador.** La única flag nueva nace **ON**. El Bloque A **no agrega flag**: retirar algo de la vista no puede exigir que el operador encienda un interruptor para que se retire (§5.3).
4. **Toda configuración del operador va por la pantalla.** La flag nueva es `env_only=False` y aparece en el panel del arnés.
5. **No degradar.** Ningún bucle, ningún sondeo periódico, ninguna llamada a un modelo. El lector de cuenta del Bloque B lee **dos archivos de texto del disco local**, con la misma caché por tiempo de vida que ya tiene el catálogo (300 s), y **nunca lanza**.
6. **Compatible hacia atrás.** El Bloque B **suma, nunca resta** modelos — es la regla que el propio repositorio ya escribió en `services/model_catalog.py:113-117` ("UNION, nunca resta"). Ninguna clave existente de ninguna respuesta desaparece.
7. **Español** en el documento, en los nombres de símbolos nuevos del dominio y en todo texto visible.
8. **`services/` no importa de `api/`.** El módulo nuevo vive en `services/` y la ruta lo importa, nunca al revés.
9. **La lógica verificable de la pantalla vive en `.ts` puro.** En este repositorio **no están instalados** `@testing-library/react` ni `jsdom`: no se puede montar un componente en una prueba. Los `.tsx` quedan tontos.

### 3.1 Paridad en los 3 motores de ejecución (Codex CLI, Claude Code CLI, GitHub Copilot Pro)

| Ítem | Codex CLI | Claude Code CLI | GitHub Copilot Pro | Fallback |
|---|---|---|---|---|
| **A** — retiro de la superficie de clasificación | Idéntico | Idéntico | Idéntico | **No aplica bifurcación.** El control depende del *tracker* (GitLab), no del motor que ejecuta agentes. Ningún símbolo del Bloque A nombra un motor |
| **B** — catálogo al día | **Sin cambio**: su bloque en el archivo es `{"id": "", "label": "Automático (decide Codex CLI)"}` y este plan no lo toca | **Es el ítem**: se agregan los modelos que faltan y se hacen ejecutables | **Sin cambio**: su lista se puebla viva desde `copilot_bridge.list_copilot_models()` (`services/model_catalog.py:174-194`) | Cada motor conserva exactamente su fuente actual |
| **B** — lector de la cuenta local | **No aplica**: no hay cuenta de Claude que leer ⇒ el lector devuelve `{"disponible": false, "motivo": "no_aplica"}` y el bloque de Codex queda **byte-idéntico** | Aplica | **No aplica**: ídem Codex | El lector se aplica **solo** al bloque `claude_code_cli`. Un gate lo verifica (§6.F11) |
| **B** — aviso "lista de respaldo" | Se muestra si su bloque cayó al respaldo | Ídem | Ídem — y además muestra el error de introspección que ya viaja en `error` | El aviso es **por motor**, derivado del dato, sin bifurcación de código |

**Gate binario de esta sección (F11):** el bloque `codex_cli` y el bloque `github_copilot` de la respuesta de `/api/agents/model-catalog` deben ser **exactamente iguales** antes y después del plan, comparados clave por clave, con el lector de cuenta encendido y apagado.

---

## 4. Glosario, reglas de lectura y rojos de fábrica

### 4.1 Glosario (términos de este repositorio que un modelo menor no conoce)

| Término | Qué es acá |
|---|---|
| **Clasificación local** | Lo que construyó el plan 277: el operador marca, **dentro de Stacky**, de qué tipo es un ticket de GitLab y de cuál cuelga, sin escribir en el GitLab de la empresa. Vive en `local_work_item_type` y `local_parent_iid` |
| **Motor de datos** (de la clasificación) | Las columnas del modelo, la ruta `PATCH` del servidor, la lógica pura de `lib/jerarquiaLocal.ts` y los contadores de la sincronización. **Se conserva entero** |
| **Superficie de interfaz** (de la clasificación) | Los tres puntos donde ese motor se *monta* y el operador lo ve. **Es lo único que se retira** |
| **Catálogo de modelos** | `backend/config/model_catalog.json`, leído por `services/model_catalog.py` con caché de 300 s invalidada por fecha de modificación del archivo |
| **Respaldo de emergencia** | La copia embebida del catálogo que se usa si el archivo no se puede leer. Hay **dos**, una por lado de la red: `services/model_catalog.py:26` y `frontend/src/services/modelCatalogFallback.ts:11`. El plan 212 dejó una prueba de paridad entre las dos |
| **Clamp** | `services/llm_router.py:38 clamp_model`. Es la **única** función que decide qué modelo está capado. Mapea cualquier modelo Claude de tier prohibido al tope (`claude-sonnet-5`) |
| **Elección explícita** | Cuando el operador elige un modelo para **una** corrida. Es el único caso que puede saltarse el clamp, y solo si el id está en la lista de autorizados (`services/claude_code_cli_runner.py:534 allow_opus_for_run`) |
| **Sonda** (del programa instalado) | `services/model_probe.py`. Pregunta al programa de línea de comandos qué modelos tiene. **Nunca invoca un modelo**: solo subcomandos de listado |
| **Ratchet** | Prueba que congela un número y solo lo deja bajar |
| **Rojo de fábrica** | Prueba que ya falla antes de que este plan toque nada. Se declara para que nadie lo confunda con una regresión propia |

### 4.2 Cómo se leen los `archivo:línea` de este documento

Hay una **sesión paralela viva** en este árbol (tomó los planes 286 y 287; sus archivos de prueba ya están registrados en los scripts del arnés en `run_harness_tests.sh:1018-1020`). Los números pueden correrse. **Regla: cuando este documento da un número de línea para un punto de inserción, da también el símbolo. Si el número no coincide, manda el símbolo.** F0.0 revalida los anclajes críticos en 15 segundos antes de tocar nada.

### 4.3 El defecto del Bloque B, en cuatro pasos verificados

Esto es lo que hay que entender antes de escribir una línea del Bloque B. Los cuatro pasos están anclados:

1. **El catálogo no tiene `claude-opus-5`.** `backend/config/model_catalog.json:9-14` lista exactamente 4 ids: `claude-sonnet-5`, `claude-opus-4-8`, `claude-haiku-4-5`, `claude-sonnet-4-6`. Fecha del archivo: `"updated_at": "2026-07-17"` (`:3`).
2. **La sonda que debía arreglarlo está muerta.** `services/model_probe.py:29-33` prueba `models list --json`, `models --json` y `--list-models`. Los tres **no existen** en el programa instalado (§4.4). Devuelve `no_candidate_worked` siempre.
3. **Aunque el modelo estuviera en la lista, el camino de ejecución lo degradaría.** `services/llm_router.py:33` `_FORBIDDEN_CLAUDE_TIER = ("opus", "fable")` y `:35` `_OPUS_ALLOWLIST = {"claude-opus-4-8"}` — **un solo elemento**. `clamp_model` (`:38-57`) manda cualquier `claude-*opus*` o `claude-*fable*` a `CLAUDE_CAP_MODEL = "claude-sonnet-5"` salvo que `allow_opus=True` **y** el id esté en esa lista. Y `allow_opus_for_run` (`services/claude_code_cli_runner.py:534-548`) devuelve `True` **solo** si `is_opus_allowlisted(model_override)`.
   **Consecuencia medible:** si hoy se agregara `claude-opus-5` al catálogo y el operador lo eligiera, el runner ejecutaría `claude-sonnet-5`. La pantalla mostraría Opus 5. **Sería un plan que empeora el problema: cambia "no aparece" por "aparece y miente".**
4. **La pantalla no avisa cuando muestra la lista de respaldo.** `frontend/src/hooks/useModelCatalog.ts` devuelve `{catalog, loading}` (`:21-24`, `:49`): **descarta `fallback_used`**, que sí viaja en la respuesta (`frontend/src/api/endpoints.ts:1164`). Los **5** consumidores (`components/EpicFromBriefModal.tsx:81,88`, `pages/PlansBoardPage.tsx:348`, `pages/TicketBoard.tsx:150`, `components/IncidentResolverModal.tsx:91`, `components/ModelDecisionChip.tsx:21`) no tienen forma de saberlo. El único lugar del repositorio que sí lo mira es `components/ModelPicker.tsx:78`, pero es **otra ruta** (`/api/agents/models`, que sirve `llm_router.CLAUDE_MODELS` — **3** modelos, sin ningún opus).

### 4.4 Evidencia externa MEDIDA el 2026-08-02 (no inferida)

Todo esto se obtuvo ejecutando comandos en la máquina del operador. **Está pegado literal porque es el corazón del Bloque B.**

**(a) Versión y subcomandos del programa de línea de comandos de Claude Code**

```
$ claude --version
2.1.220 (Claude Code)

$ claude --help   (sección Commands)
agents · auth · auto-mode · doctor · gateway · install · mcp · plugin|plugins ·
project · setup-token · ultrareview · update|upgrade
```

**No existe un subcomando `models`.** Ejecutando los tres candidatos de `services/model_probe.py:29-33`:

```
=== claude models list --json ===  exit=1   error: unknown option '--json'
=== claude models --json ===       exit=1   error: unknown option '--json'
=== claude --list-models ===       exit=1   error: unknown option '--list-models'
```

**Conclusión (a):** el camino "preguntarle al programa por un listado" **no es ejecutable hoy**. La sonda se conserva (una versión futura puede agregarlo, y la regla del repositorio es sumar nunca restar), pero **su motivo de fallo tiene que publicarse** en vez de quedar mudo.

**(b) Lo que el programa SÍ escribe en disco sobre esta cuenta**

`~/.claude.json` (75.364 bytes) tiene, entre sus claves de primer nivel:

```json
"additionalModelOptionsCache": [
  {"value": "claude-fable-5[1m]", "label": "Fable",
   "description": "Fable 5 · Most capable for your hardest and longest-running tasks"}
],
"modelAccessCache": [],
"orgModelDefaultCache": null,
"s1mAccessCache": {"c26268e0-…": {"hasAccess": false, "hasAccessNotAsDefault": false, "timestamp": 1776740538128}},
"oauthAccount": {
  "billingType": "stripe_subscription",
  "organizationType": "claude_max",
  "organizationRateLimitTier": "default_claude_max_20x",
  "hasExtraUsageEnabled": false,
  …
}
```

`~/.claude/stats-cache.json` (14.855 bytes) tiene:

```json
"modelUsage": {
  "claude-sonnet-4-6": {…}, "claude-sonnet-5": {…},
  "claude-haiku-4-5-20251001": {…}, "claude-fable-5": {…},
  "claude-opus-4-8": {…}, "claude-opus-5": {…}
},
"dailyModelTokens": [ …, {"date": "2026-07-28",
                          "tokensByModel": {"claude-sonnet-5": 455132,
                                            "claude-opus-5": 4321237}} ]
```

**Conclusión (b):** hay una fuente **local, real, sin red, sin consumo y sin credenciales** que dice qué modelos esta cuenta **usó de verdad** (`modelUsage`, `dailyModelTokens`), cuáles el propio programa **le ofrece de más** (`additionalModelOptionsCache`), y qué **suscripción** tiene (`oauthAccount.organizationType = "claude_max"`, `organizationRateLimitTier = "default_claude_max_20x"`). **`claude-opus-5` y `claude-fable-5` están ahí y no están en el catálogo de Stacky.**

**(c) Lo que NO se puede hacer, dicho sin adornos**

| Camino que el operador podría esperar | Veredicto | Evidencia |
|---|---|---|
| Preguntarle al programa instalado por la lista de modelos | **NO EJECUTABLE** | §4.4(a): no hay subcomando de listado en 2.1.220 |
| Llamar a la ruta de listado de modelos del proveedor | **NO EJECUTABLE Y ADEMÁS NO RESPONDERÍA LA PREGUNTA** | Esa ruta refleja lo que ve una **clave de interfaz de programación**, no lo que da una **suscripción**. Acá el motor corre con la sesión del programa, no con clave: `services/claude_code_cli_runner.py` invoca el binario, no una ruta HTTP. Y `oauthAccount.billingType` es `"stripe_subscription"`, es decir **suscripción**, no consumo por clave. Aunque hubiera credencial, la lista que devolvería **no sería la de la suscripción del operador** |
| Verificar un modelo invocándolo | **PROHIBIDO** | Gastaría consumo en reposo. Violaría el principio 5 y la regla (A) de las flags |
| Leer lo que el programa ya guardó sobre esta cuenta | **EJECUTABLE, VERIFICADO** | §4.4(b) |
| Poner el catálogo estático al día | **EJECUTABLE, TRIVIAL** | §4.3(1) |

**Este plan implementa los dos últimos y descarta los tres primeros por escrito.** No promete una "consulta a la suscripción" que no existe.

### 4.5 Rojos de fábrica declarados (medidos ANTES de tocar nada)

| Archivo | Estado hoy | Regla |
|---|---|---|
| `backend/tests/test_harness_flags_help.py` | rojo de fábrica conocido (4 fallidas) | **No es de este plan.** Se mide el **delta**: mismo número y mismos nombres al cerrar. Si aparece una violación nueva que nombra la key de este plan, el texto de ayuda está mal y se corrige el texto |
| `backend/tests/test_error_fingerprints_catalog.py` | rojo de fábrica conocido | Ídem |
| `frontend/src/services/__tests__/plan273GateState.test.ts` | 2 aserciones rojas (espera 7 gates, hay 8) | Ídem. Este plan **no agrega ningún gate de pantalla** |
| `backend/tests/test_harness_ratchet_meta.py` + `tests/test_plan259_ratchet_script_parity.py` | **VERDES — 16 passed, medido el 2026-08-02** | Estos **no pueden** quedar rojos. Es el criterio duro de F10 |

**Regla de aceptación del plan:** ninguna prueba que hoy esté **verde** puede quedar roja. Los rojos de arriba deben quedar **exactamente igual**. Un "todo pasa" reportado no es evidencia: se pega la salida.

---

## 5. Flags

### 5.1 La única flag nueva

| Key | Tipo | Default | Categoría | Qué protege | Justificación del default |
|---|---|---|---|---|---|
| `STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED` | `bool` | **ON** (`default=True`) | `runtimes_cli` | El lector de la configuración local de la cuenta de Claude Code (§6.F7) y su aporte al catálogo | **Solo lectura, sin red, sin consumo, sin escritura.** Lee dos archivos de texto del disco del operador y no toca nada. **No cae en (A)**: no enciende bucle, demonio, barrido, sondeo, prefetch ni llamada a modelo — se evalúa dentro del refresco de caché que **ya existe** (300 s) y solo cuando alguien pide el catálogo. **No cae en (B)**: no escribe en ningún sistema, no borra nada, no decide nada por el operador. Lo de solo lectura va **siempre ON** |

**Ninguna otra flag nueva.** El resto del plan usa las que ya existen: `STACKY_MODEL_CATALOG_ENABLED` (`config.py:1026`, ON), `STACKY_MODEL_PROBE_ENABLED` (`config.py:1517`, ON), `STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED` y `STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED` (las del 277, **intocadas**).

### 5.2 Las patas de la flag nueva — enumeradas con archivo y símbolo

> **Esta tabla es el contrato con el implementador.** Si falta una pata, la flag queda **muerta** o una suite ajena se pone roja. Están verificadas el 2026-08-02.

| # | Archivo | Estructura | Ancla (símbolo primero, número después) | Qué se agrega |
|---|---|---|---|---|
| 1 | `Stacky Agents/backend/config.py` | atributo de la clase de configuración | buscar `STACKY_MODEL_PROBE_ENABLED: bool = os.getenv(` (hoy `:1517`) y agregar **debajo** | `STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED: bool = os.getenv("STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED", "true").strip().lower() in ("1","true","yes")` — **usar exactamente el mismo patrón que la línea de arriba en ese archivo** |
| 2 | `Stacky Agents/backend/services/harness_flags.py` | `FLAG_REGISTRY` | abre en `FLAG_REGISTRY: tuple[FlagSpec, ...] = (` (hoy `:610`); cierra justo antes de `_REGISTRY_INDEX: dict[str, FlagSpec] =` (hoy `:7186`) | 1 `FlagSpec` al final, antes del `)`. Texto literal en §5.4 |
| 3 | `Stacky Agents/backend/services/harness_flags.py` | `_CATEGORY_KEYS`, tupla `"runtimes_cli"` | abre en `"runtimes_cli": (` (hoy `:121`) y cierra antes de `"contexto_memoria": (` (hoy `:133`). `STACKY_MODEL_CATALOG_ENABLED` ya está ahí (`:131`) | la key, al final de esa tupla |
| 4 | **`Stacky Agents/backend/tests/test_harness_flags.py`** | `_CURATED_DEFAULTS_ON` (es un **`set`** y vive en el **archivo de prueba**, no en el servicio) | abre en `_CURATED_DEFAULTS_ON = {` (hoy `:467`) | la key, al final del set. **Obligatorio**: el comentario del propio archivo (`:463-466`) dice *"toda flag con `spec.default=True` DEBE estar aquí (`default_is_known == True` ⇔ pertenencia a este set)"* |
| 5 | **`Stacky Agents/backend/tests/test_harness_flags_requires.py`** | `_REQUIRES_MAP_FROZEN` (dict, hoy `:120`) | **NO SE TOCA** | La flag **no declara `requires=`**. Verificado el 2026-08-02: `test_requires_map_is_frozen` (`:397-405`) construye `actual = {s.key: s.requires for s in FLAG_REGISTRY if s.requires}` — el filtro `if s.requires` **excluye** a las flags sin `requires`, así que **no hay entrada que agregar**. Agregar una entrada acá **rompe** la prueba con `Faltantes: [...]` |
| 6 | `Stacky Agents/backend/services/harness_flags_help.py` | `PLAIN_HELP` (dict) | buscar `PLAIN_HELP: dict` y `def plain_help_for`; agregar antes del `}` final | 1 entrada. Texto literal y validado en §5.5 |
| 7 | `Stacky Agents/backend/tests/test_harness_flags_bounds.py` | `_FROZEN_BOUNDS` | **NO SE TOCA** | Solo aplica a flags **numéricas**. Esta es `bool`. Verificar corriendo la prueba (F0.2) |
| 8 | Panel de flags de la pantalla | — | **NO SE TOCA** | El panel se deriva de `FLAG_REGISTRY` en tiempo de ejecución. Con `env_only=False` aparece sola. Se confirma en el smoke visual de F12 |

### 5.3 Por qué el Bloque A NO agrega flag (decisión explícita)

Sería un error, y la regla de este repositorio lo dice: *"lo de solo lectura va siempre ON"* y *"no son motivos válidos: 'para no cambiar el comportamiento actual'"*. Una flag `STACKY_TICKET_CLASSIFICATION_UI_ENABLED` tendría que nacer **ON** — y ON significa **que el bloque se sigue viendo**, es decir, el ítem del operador **no quedaría resuelto**. Nacer OFF no está permitido: retirar un control de la pantalla no quema consumo en reposo (A) ni escribe en un sistema real (B). **Conclusión: el retiro es incondicional, sin interruptor, y el centinela de F1 lo congela.** Además, retirar el botón de publicar etiquetas **reduce** la superficie de escritura al GitLab de la empresa, que va en la dirección correcta del guardarraíl 1.

### 5.4 Texto literal de la `FlagSpec` (pata 2)

Va al final de `FLAG_REGISTRY`, antes del `)` de cierre:

```python
    # ── Plan 288 — el selector de modelos deja de mentir ──────────────────────
    FlagSpec(
        key="STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED",
        type="bool",
        label="Modelos habilitados en tu cuenta de Claude Code",
        description=(
            "Plan 288 — Lee del disco local lo que el programa de Claude Code ya "
            "guardo sobre esta cuenta (modelos usados, opciones extra ofrecidas y "
            "tipo de suscripcion) y lo SUMA al catalogo de modelos. Solo lectura: "
            "sin red, sin credenciales y sin gasto. Nunca resta modelos."
        ),
        group="global",
        env_only=False,
        default=True,
        # SIN requires= a proposito: ver Plan 288 seccion 5.2 pata 5.
    ),
```

> **Regla dura verificada:** en `harness_flags.py` una flag que nace OFF se declara **omitiendo** el kwarg `default`, porque `default_is_known(spec)` es `spec.default is not None` y `False is not None`. Esta flag nace ON, así que declara `default=True` **y** entra a `_CURATED_DEFAULTS_ON`. **Las dos cosas, siempre juntas.**

### 5.5 Texto literal de `PLAIN_HELP` (pata 6)

Las reglas se leyeron del archivo de prueba real (`backend/tests/test_harness_flags_help.py`): `what` entre 10 y 200 caracteres; `on_effect` y `off_effect` ≤ 240 y **empiezan con `"Si "`** (con espacio, **sin tilde**); `example` ≤ 300; los 4 no vacíos; **sin jerga** de `JARGON_DENYLIST` = `MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime` (sin distinguir mayúsculas y **con el plural incluido**); sin claves en mayúsculas con guión bajo; sin referencias a fase (`\bF\d`).

> El texto de abajo se redactó contra esas reglas. **Copiarlo literal.** Las palabras prohibidas más fáciles de meter sin querer en este dominio son *"runtime"*, *"token"* y *"endpoint"*: ninguna aparece.

```python
    "STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED": PlainHelp(
        what="Lee de tu equipo la lista de modelos que tu cuenta de Claude Code tiene habilitados, para ofrecerte solo esos.",
        on_effect="Si la activas: el selector suma los modelos que tu cuenta ya viene usando o que el programa de Claude Code te ofrece, leyendo archivos que ese programa ya guarda en tu equipo.",
        off_effect="Si la apagas: el selector muestra solo la lista fija que viene con Stacky, sin mirar tu cuenta.",
        example="Tu cuenta usa Opus 5 desde hace semanas; con esto aparece en la lista en vez de quedar invisible.",
    ),
```

---

## 6. Fases

> **Comandos canónicos.**
> **Servidor:** desde `Stacky Agents/backend`, `.venv/Scripts/python.exe -m pytest tests/<UN_ARCHIVO>.py -q --no-header -p no:cacheprovider`. **Usar `.venv` (Python 3.13.5), NO `venv` (3.11.9)** — `venv` no tiene las dependencias. **Un archivo por vez**: correr `pytest tests` entero da miles de errores de contaminación y **no es un veredicto**.
> **Antes de cualquier `pytest`, exportar `STACKY_TEST_MODE=1`** (en PowerShell: `$env:STACKY_TEST_MODE="1"`). Sin eso, un pytest suelto puede escribir en la base viva.
> **`pytest -k` sin coincidencias sale con código 0**: nunca usar `-k` como única prueba de que algo pasó; siempre mirar el conteo (`N passed`).
> **Pantalla:** desde `Stacky Agents/frontend`, `npx vitest run src/<ruta>/<archivo>.test.ts` (**por archivo, nunca la suite entera**: hay contaminación por orden) y `npx tsc --noEmit`. **`npx vitest run <ruta inexistente>` sale 1 pero pipeado se pierde el código de salida**: correrlo sin pipe.

---

### F0.0 — Barrido de anclajes, ANTES de tocar nada

**Objetivo:** revalidar en 15 segundos los 14 anclajes críticos, porque hay una sesión paralela viva en este árbol.
**Archivos:** ninguno (solo lectura). **Flag:** ninguna. **Trabajo del operador: ninguno.**

Correr desde `Stacky Agents`:

```powershell
Select-String -Path "frontend\src\pages\TicketBoard.tsx"                  -Pattern 'import JerarquiaLocalControl|import PublicarEtiquetasGitLab|<JerarquiaLocalControl|<PublicarEtiquetasGitLab|TicketLocalInsightButton'
Select-String -Path "frontend\src\components\TicketGraphView.jsx"         -Pattern 'import JerarquiaLocalControl|<JerarquiaLocalControl|FinishWorkButton'
Select-String -Path "frontend\src\lib\jerarquiaLocal.ts"                  -Pattern 'export function debeMostrarControlJerarquia|export function validarPadre|export function esPublicable'
Select-String -Path "backend\services\gitlab_sync.py"                     -Pattern 'usados_local_tipo'
Select-String -Path "backend\config\model_catalog.json"                   -Pattern 'claude-opus-4-8|claude-sonnet-5'
Select-String -Path "backend\services\model_catalog.py"                   -Pattern '_EMERGENCY_FALLBACK|def load_model_catalog|def _merge_probe'
Select-String -Path "backend\services\model_probe.py"                     -Pattern '_CANDIDATES|def probe_claude_models'
Select-String -Path "backend\services\llm_router.py"                      -Pattern '_OPUS_ALLOWLIST|def clamp_model|def is_opus_allowlisted|CLAUDE_CAP_MODEL'
Select-String -Path "backend\services\claude_code_cli_runner.py"          -Pattern 'def allow_opus_for_run'
Select-String -Path "backend\api\agents.py"                               -Pattern 'def model_catalog_route|capabilities_for'
Select-String -Path "backend\harness\pricing.py"                          -Pattern 'DEFAULT_PRICES'
Select-String -Path "backend\services\harness_flags.py"                   -Pattern 'FLAG_REGISTRY: tuple|"runtimes_cli": \('
Select-String -Path "backend\tests\test_harness_flags.py"                 -Pattern '_CURATED_DEFAULTS_ON = \{'
Select-String -Path "backend\scripts\run_harness_tests.sh"                -Pattern 'HARNESS_TEST_FILES=\('
Select-String -Path "backend\scripts\run_harness_tests.ps1"               -Pattern '\$HarnessTestFiles = @\('
Select-String -Path "frontend\src\hooks\useModelCatalog.ts"               -Pattern 'export function useModelCatalog|UseModelCatalogResult'
```

**Criterio binario:** los 16 patrones imprimen **al menos una línea cada uno**. Si alguno no imprime nada, **parar** y avisar: el símbolo se renombró y el plan necesita una pasada de actualización.

**Además, comprobar si el plan 287 ya está implementado:**

```powershell
Test-Path "frontend\src\components\ticket\TicketFullView.tsx"
```

Anotar el resultado: decide si F3 se ejecuta o se salta (§6.F3).

---

### F0.1 — Línea base medida de los gates que este plan cruza

**Objetivo:** dejar por escrito el número de **hoy** de cada gate, para que el criterio de aceptación sea un **delta** y no un absoluto.
**Archivos:** ninguno. **Flag:** ninguna. **Trabajo del operador: ninguno.**

Correr y **anotar la salida literal**:

| # | Comando (directorio) | Baseline esperado hoy |
|---|---|---|
| 1 | `npx vitest run src/__tests__/plan277JerarquiaLocal.test.ts` (`frontend`) | **verde, 8 casos** |
| 2 | `npx vitest run src/__tests__/formDebtRatchet.test.ts` (`frontend`) | **verde** |
| 3 | `npx vitest run src/__tests__/uiDebtRatchet.test.ts` (`frontend`) | **verde** |
| 4 | `npx vitest run src/__tests__/modelSelectorsConsistency.test.ts` (`frontend`) | **verde** |
| 5 | `npx tsc --noEmit` (`frontend`) | **0 errores** |
| 6 | `.venv/Scripts/python.exe -m pytest tests/test_plan277_clasificacion_local.py -q --no-header -p no:cacheprovider` (`backend`) | anotar el número |
| 7 | `.venv/Scripts/python.exe -m pytest tests/test_plan159_model_catalog_endpoint.py tests/test_plan159_model_catalog_loader.py tests/test_plan159_model_catalog_flag.py -q --no-header -p no:cacheprovider` (`backend`) | anotar el número |
| 8 | `.venv/Scripts/python.exe -m pytest tests/test_plan212_model_probe.py -q --no-header -p no:cacheprovider` (`backend`) | anotar el número |
| 9 | `.venv/Scripts/python.exe -m pytest tests/test_adaptive_selector.py tests/test_adaptive_selector_wiring.py tests/test_difficulty_routing.py tests/test_acceptance_contract.py -q --no-header -p no:cacheprovider` (`backend`) | anotar el número — **son las suites que congelan el clamp** |
| 10 | `.venv/Scripts/python.exe -m pytest tests/test_harness_ratchet_meta.py tests/test_plan259_ratchet_script_parity.py -q --no-header -p no:cacheprovider` (`backend`) | **16 passed** (medido 2026-08-02) |
| 11 | `.venv/Scripts/python.exe -m pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py tests/test_flags_env_read_meta.py tests/test_harness_flags_bounds.py -q --no-header -p no:cacheprovider` (`backend`) | anotar el número |
| 12 | `.venv/Scripts/python.exe -m pytest tests/test_harness_flags_help.py -q --no-header -p no:cacheprovider` (`backend`) | **rojo de fábrica** — anotar el número exacto de fallidas **y sus nombres** |

**Criterio binario:** los 12 números quedan escritos. Al cerrar (F12) se vuelven a correr los 12 y **cada uno da igual o mejor**; el 12 tiene que dar **exactamente las mismas fallidas, con los mismos nombres**.

---

## BLOQUE A — la vista del ticket adelgaza

### F1 — Centinela de DOS patas (ausencia + presencia), hoy ROJO

**Objetivo:** congelar en una sola prueba que la superficie de "Clasificación" desapareció **y** que todo lo demás de la tarjeta sigue ahí.
**Valor:** un `expect(...).not.toContain(...)` solo **pasa por accidente** si el archivo no existe, si la ruta está mal escrita o si alguien renombra el símbolo. La pata de **presencia** en el **mismo** conjunto de aserciones lo hace imposible.
**Flag:** ninguna (es una prueba). **Trabajo del operador: ninguno.** **Motores:** neutro.

> **Por qué es un escaneo de código fuente y no un montaje de componente:** este repositorio **no tiene** `@testing-library/react` ni `jsdom`. El patrón probado acá es leer el archivo con `readFileSync` y afirmar sobre su texto — es exactamente lo que hace `src/__tests__/modelSelectorsConsistency.test.ts:1-23`. Se copia ese patrón.

**Archivo NUEVO:** `Stacky Agents/frontend/src/__tests__/plan288SuperficieClasificacion.test.ts`

**Contenido exacto (copiar; los nombres de los `it` son parte del contrato):**

```ts
import { readFileSync, existsSync } from "fs";
import { join } from "path";
import { describe, it, expect } from "vitest";

/**
 * Plan 288 F1 — la superficie de "Clasificación" no se ve en la vista de tickets.
 *
 * DOS PATAS EN EL MISMO TEST, a propósito: un assert de AUSENCIA pasa solo si el
 * archivo no existe o si la ruta está mal. La pata de PRESENCIA lo prueba vivo.
 */
const leer = (rel: string) => {
  const p = join(process.cwd(), rel);
  expect(existsSync(p), `no existe ${rel} — la ruta del test está mal, no es que el símbolo se fue`).toBe(true);
  return readFileSync(p, "utf-8");
};

const TABLERO = "src/pages/TicketBoard.tsx";
const GRAFO = "src/components/TicketGraphView.jsx";

describe("Plan 288 F1 — la vista del ticket no muestra la clasificación", () => {
  it("el tablero no monta ni importa los controles de clasificación, y SÍ conserva sus 4 acciones", () => {
    const src = leer(TABLERO);
    // AUSENCIA
    expect(src).not.toContain("<JerarquiaLocalControl");
    expect(src).not.toContain("<PublicarEtiquetasGitLab");
    expect(src).not.toContain('from "../components/JerarquiaLocalControl"');
    expect(src).not.toContain('from "../components/PublicarEtiquetasGitLab"');
    // PRESENCIA — en el MISMO test: si esto falla, el archivo se vació o se rompió
    expect(src).toContain("<FinishWorkButton");
    expect(src).toContain("<CreateChildTaskButton");
    expect(src).toContain("<TicketLocalInsightButton");
    expect(src).toContain("<RecoverExecutionButton");
  });

  it("el grafo no monta ni importa el control de clasificación, y SÍ conserva sus acciones", () => {
    const src = leer(GRAFO);
    expect(src).not.toContain("<JerarquiaLocalControl");
    expect(src).not.toContain('from "./JerarquiaLocalControl"');
    expect(src).toContain("<FinishWorkButton");
    expect(src).toContain("<CreateChildTaskButton");
    expect(src).toContain("<RecoverExecutionButton");
  });

  it("el motor de datos NO se borró: la lógica pura sigue exportada y con sus consumidores", () => {
    const motor = leer("src/lib/jerarquiaLocal.ts");
    expect(motor).toContain("export function debeMostrarControlJerarquia");
    expect(motor).toContain("export function validarPadre");
    expect(motor).toContain("export function esPublicable");
    expect(motor).toContain("export const TIPOS_CANONICOS_JERARQUIA");
    // Y las claves del contrato del servidor siguen viajando en el tipo del ticket.
    expect(leer("src/types.ts")).toContain("local_work_item_type");
  });
});
```

**Comando (desde `Stacky Agents/frontend`):**

```bash
npx vitest run src/__tests__/plan288SuperficieClasificacion.test.ts
```

**Antes de F2, los 2 primeros `it` tienen que FALLAR** (por las 6 aserciones de ausencia) y el tercero **tiene que pasar**. Anotar la salida literal: eso prueba que el centinela mira el lugar correcto.

**Criterio binario de F1:** `2 failed | 1 passed`.

---

### F2 — Retirar los tres montajes (el cambio real del Bloque A)

**Objetivo:** que el operador deje de ver el bloque de clasificación en la vista de tickets.
**Valor:** el ítem del operador, cerrado. **Flag:** ninguna (§5.3). **Trabajo del operador: ninguno.** **Motores:** neutro.

**Archivos a editar — exactamente 2:**

**(1) `Stacky Agents/frontend/src/pages/TicketBoard.tsx`** — cuatro ediciones:

| Qué | Anclaje por símbolo (hoy) | Acción |
|---|---|---|
| Comentario + import | `// Plan 277 F4 — clasificación local de jerarquía (se auto-oculta fuera de GitLab).` seguido de `import JerarquiaLocalControl from "../components/JerarquiaLocalControl";` (`:22-23`) | **borrar las 2 líneas** |
| Import | `import PublicarEtiquetasGitLab from "../components/PublicarEtiquetasGitLab";  // Plan 277 F5` (`:24`) | **borrar la línea** |
| Montaje en la tarjeta | el bloque que abre en el comentario `{/* Plan 277 F4 — Tipo y Padre locales, precargados del payload. …` y termina en el `</div>` que cierra el `<div onClick={(e) => e.stopPropagation()}>` que envuelve a `<JerarquiaLocalControl …/>` (`:708-720`) | **borrar el bloque entero, comentario incluido** |
| Montaje del panel de publicación | el bloque que abre en `{/* Plan 277 F5 — publicar en GitLab las etiquetas de la clasificación local. …` y termina en el `)}` de `{(viewMode === "tree" \|\| viewMode === "graph") && ( … )}` que envuelve a `<PublicarEtiquetasGitLab …/>` (`:1305-1314`) | **borrar el bloque entero, comentario incluido** |

> **Cuidado con la variable `qc`:** los dos montajes usaban `qc.invalidateQueries(...)` y `refetchHierarchy()` dentro de sus callbacks. Esas funciones **se siguen usando en otros lugares del archivo**; no borrar sus declaraciones. Si `npx tsc --noEmit` reporta una variable sin uso después de la edición, **es la señal de que se borró de más**: revertir esa línea puntual, no todo.

**(2) `Stacky Agents/frontend/src/components/TicketGraphView.jsx`** — dos ediciones:

| Qué | Anclaje por símbolo (hoy) | Acción |
|---|---|---|
| Comentario + import | `// Plan 277 F4 — clasificación local de jerarquía. El componente decide solo si se` / `// muestra (…)` / `import JerarquiaLocalControl from "./JerarquiaLocalControl";` (`:27-29`) | **borrar las 3 líneas** |
| Montaje | el bloque que abre en `{/* Plan 277 F4 — Tipo y Padre locales. Se renderiza solo en proyectos …` y termina en el `</div>` del envoltorio con `onClick={(e) => e.stopPropagation()}` (`:481-493`) | **borrar el bloque entero, comentario incluido** |

**Lo que NO se toca, y la razón (esto es tan importante como lo que se borra):**

| Archivo | Por qué se conserva |
|---|---|
| `frontend/src/components/JerarquiaLocalControl.tsx` | **No se borra.** El plan 287 lo nombra dos veces como acción reusable de su ficha (`docs/287_…md:109` y `:762`) y hay una **sesión paralela viva** que puede estar editándolo. Borrarlo genera un conflicto y rompe un plan ya escrito. Ver §7.1 y §8 |
| `frontend/src/components/PublicarEtiquetasGitLab.tsx` | Ídem. Además su lógica está cubierta por las pruebas del 277 |
| `frontend/src/lib/jerarquiaLocal.ts` | Es el motor; §2.2 |
| `frontend/src/types.ts:115` y las claves `local_work_item_type` / `local_parent_iid` | Contrato del servidor. Sacarlas rompería la sincronización |
| Todo el servidor (`api/tickets.py`, `services/gitlab_sync.py`, `services/gitlab_hierarchy*.py`) y sus 2 flags del 277 | §2.2 |
| `frontend/src/__tests__/plan277JerarquiaLocal.test.ts` | Sus 8 casos importan **solo** funciones puras del motor. **Sigue verde sin tocarlo** |

**Criterio binario de F2 (los 5 comandos):**

```bash
# desde Stacky Agents/frontend
npx vitest run src/__tests__/plan288SuperficieClasificacion.test.ts   # 3 passed
npx vitest run src/__tests__/plan277JerarquiaLocal.test.ts            # 8 passed, igual que F0.1
npx vitest run src/__tests__/formDebtRatchet.test.ts                  # verde
npx vitest run src/__tests__/uiDebtRatchet.test.ts                    # verde
npx tsc --noEmit                                                      # 0 errores
```

> **Los dos ratchets de deuda son "no aumenta", no "igual"** (`src/__tests__/formDebtRatchet.test.ts:72-85`: `if (count > allowed)`). Borrar marcado solo puede bajar el número, así que **no hay que regenerar ningún baseline**. Verificado: ni `JerarquiaLocalControl.tsx` ni `PublicarEtiquetasGitLab.tsx` figuran en `formDebtBaseline.json`, `uiDebtBaseline.json` ni `motionDebtBaseline.json`.

---

### F3 — Frontera con el plan 287 (condicional; se ejecuta SOLO si el 287 ya está)

**Objetivo:** que el retiro no se deshaga solo cuando llegue la ficha a pantalla completa.
**Flag:** ninguna. **Trabajo del operador: ninguno.** **Motores:** neutro.

**Disparador:** el resultado del `Test-Path "frontend\src\components\ticket\TicketFullView.tsx"` de F0.0.

- **Si dio `False` (el 287 todavía NO está implementado — es el caso esperado hoy):**
  **No se hace nada de código.** Se agrega **una fila** a la tabla de criterios de F1 en forma de comentario en la cabecera del archivo de prueba, y se anota en §7.1 la instrucción para quien implemente el 287. El centinela de F1 ya cubre los dos archivos que existen; cuando el 287 cree su ficha, **el que la implemente tiene prohibido montar ahí `JerarquiaLocalControl` o `PublicarEtiquetasGitLab`**, y el criterio de aceptación de este plan (§9, DoD punto 4) lo obliga a extender el centinela.

- **Si dio `True` (el 287 ya está implementado):**
  Agregar al archivo de F1 un cuarto `it` con la misma estructura de dos patas:

  ```ts
  it("la ficha a pantalla completa tampoco monta los controles de clasificación", () => {
    const src = leer("src/components/ticket/TicketFullView.tsx");
    expect(src).not.toContain("<JerarquiaLocalControl");
    expect(src).not.toContain("<PublicarEtiquetasGitLab");
    // PRESENCIA: la ficha sigue siendo la ficha
    expect(src).toContain("Dialog");
  });
  ```

  Y retirar del `TicketFullView.tsx` los montajes correspondientes, con la misma disciplina de F2.

**Criterio binario:** el archivo de F1 pasa completo, con 3 o 4 `it` según el caso, y **queda escrito en el registro de implementación cuál de las dos ramas se tomó**.

---

## BLOQUE B — el selector de modelos deja de mentir

### F4 — Centinela del catálogo, hoy ROJO en dos aserciones distintas

**Objetivo:** dejar dos invariantes congelados **antes** de tocar nada: (a) el catálogo tiene los modelos que esta cuenta usa; (b) **todo lo que el catálogo ofrece, el camino de ejecución lo respeta**.
**Valor:** (b) es lo que impide que este plan se convierta en "aparece y miente". **Flag:** ninguna. **Trabajo del operador: ninguno.** **Motores:** neutro.

**Archivo NUEVO:** `Stacky Agents/backend/tests/test_plan288_catalogo_vivo.py`

**Casos (nombres exactos — el implementador no los cambia):**

| Test | Qué prueba | Estado hoy |
|---|---|---|
| `test_paridad_el_catalogo_ofrece_los_modelos_vigentes_de_claude_5` | El bloque `claude_code_cli` del archivo ofrece `claude-opus-5` y `claude-fable-5` **además** de los 4 que ya tenía | **ROJO** |
| `test_paridad_el_respaldo_de_emergencia_no_ofrece_menos_que_el_archivo` | El conjunto de ids de `_EMERGENCY_FALLBACK` ⊇ conjunto de ids del archivo | ROJO tras F5 si se olvida el respaldo |
| `test_ejecutable_todo_modelo_ofrecido_sobrevive_el_camino_de_eleccion_explicita` | **El invariante central.** Para **cada** id `m` ofrecido por `claude_code_cli`: `allow_opus_for_run(m, "developer") is True` **o** `clamp_model(m) == m`. Si falla, el catálogo ofrece algo que el runner degrada en silencio | **ROJO** para `claude-opus-4-8` hoy; ROJO para opus-5 y fable-5 tras F5 hasta que F6 corra |
| `test_ejecutable_el_ruteo_automatico_sigue_capado_en_sonnet` | **Contra-prueba, misma corrida.** `clamp_model("claude-opus-5")` **sin** `allow_opus` sigue devolviendo `CLAUDE_CAP_MODEL`; y `clamp_model("claude-fable-5")` también. F6 **no puede** aflojar el cap del ruteo automático | Verde hoy, tiene que **seguir** verde |
| `test_ausencia_y_presencia_ningun_modelo_desaparecio` | **Dos patas.** El conjunto de ids después ⊇ el conjunto de ids de la foto de F0.1 (**presencia**), y ningún id contiene el literal `claude-opus-4-7` ni `claude-3-` (**ausencia** de ids muertos) | Verde hoy, tiene que seguir verde |
| `test_precio_declarado_para_todo_modelo_ofrecido` | Para cada id ofrecido existe una entrada de precio que lo cubre por prefijo en `harness/pricing.py DEFAULT_PRICES` | **ROJO** tras F5 (`claude-opus-5` no tiene entrada; hoy hay `claude-opus-4`) |
| `test_los_otros_dos_motores_no_cambian` | Los bloques `codex_cli` y `github_copilot` del archivo son idénticos, clave por clave, a una copia congelada dentro del propio test | Verde, tiene que seguir verde |

**Comando:**

```bash
# desde Stacky Agents/backend, con $env:STACKY_TEST_MODE="1"
.venv/Scripts/python.exe -m pytest tests/test_plan288_catalogo_vivo.py -q --no-header -p no:cacheprovider
```

**Criterio binario de F4:** la corrida imprime **`3 failed, 4 passed`** (o el número que dé, pero **anotado literal**), y las fallidas son exactamente `test_paridad_el_catalogo_ofrece_…`, `test_ejecutable_todo_modelo_ofrecido_…` y `test_precio_declarado_…`. Si alguna de las otras 4 falla, **parar**: el test está mal escrito, no el código.

---

### F5 — El catálogo estático se pone al día (los TRES archivos, en un solo commit)

**Objetivo:** que `claude-opus-5` y `claude-fable-5` existan en la lista.
**Valor:** cierra el hecho concreto que reportó el operador. **Flag:** ninguna (es un dato). **Trabajo del operador: ninguno.** **Motores:** solo toca el bloque `claude_code_cli`.

**Archivos a editar — exactamente 3, y los 3 juntos o la prueba de paridad se pone roja:**

**(1) `Stacky Agents/backend/config/model_catalog.json`**

- `"updated_at"`: pasa de `"2026-07-17"` a `"2026-08-02"`.
- En `runtimes.claude_code_cli.models`, **agregar al principio de la lista** (para que queden arriba en el selector):
  ```json
  {"id": "claude-opus-5", "label": "Opus 5 (máxima calidad)", "recommended": false},
  {"id": "claude-fable-5", "label": "Fable 5 (tareas largas y difíciles)", "recommended": false},
  ```
  **Los 4 existentes NO se tocan ni se reordenan entre sí.** `claude-sonnet-5` sigue siendo el `recommended: true` y el `default_model`: cambiar el default es una decisión de costo que este plan no toma.
- En `effort_support`, agregar:
  ```json
  "claude-opus-5":  ["low", "medium", "high", "xhigh", "max"],
  "claude-fable-5": ["low", "medium", "high", "xhigh", "max"],
  ```
  **Justificación anclada:** `services/llm_router.py:60-81 clamp_effort_for_model` degrada por familia del nombre: `haiku` → `low/medium/high`; `sonnet` → todo menos `xhigh`; **cualquier otro (incluye opus y fable) → todo soportado** (`:80-81`, comentario `# opus: todo soportado`). Estas dos filas **describen** lo que la función ya hace; no la cambian.
- En `effort_degrade`, agregar `"claude-opus-5": {}` y `"claude-fable-5": {}` (no degradan nada).

**(2) `Stacky Agents/backend/services/model_catalog.py`** — el mismo par de modelos en `_EMERGENCY_FALLBACK` (`:26-65`), con las mismas 4 estructuras (`models`, `effort_support`, `effort_degrade`). El propio comentario del archivo (`:28-30`) explica por qué: *"el fallback de emergencia NUNCA puede ofrecer menos que el archivo"*.

**(3) `Stacky Agents/frontend/src/services/modelCatalogFallback.ts`** — el mismo par en `EMERGENCY_MODEL_CATALOG` (`:11-42`), con los mismos ids y las mismas listas de effort. El comentario del archivo (`:8-10`) dice que hay una prueba de paridad que compara los dos conjuntos de ids.

**Nota sobre variantes de id (importante, se aplica en F7, no acá):** la cuenta del operador registra también `claude-haiku-4-5-20251001` (el mismo Haiku 4.5 con fecha) y `claude-fable-5[1m]` (Fable 5 con ventana de contexto ampliada). **En F5 no se agrega ninguna de las dos**: la primera es el mismo modelo con sufijo de fecha, y la segunda depende de un acceso que la propia caché del programa declara en `false` para esta cuenta (`s1mAccessCache.hasAccess: false`, §4.4(b)). F7 define la normalización que las trata.

**Criterio binario de F5:**

```bash
# backend
.venv/Scripts/python.exe -m pytest tests/test_plan288_catalogo_vivo.py -q --no-header -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/test_plan159_model_catalog_loader.py tests/test_plan159_model_catalog_endpoint.py -q --no-header -p no:cacheprovider
# frontend
npx vitest run src/__tests__/modelSelectorsConsistency.test.ts
npx tsc --noEmit
```

- `test_paridad_…` y `test_paridad_el_respaldo_…` pasan a **verde**.
- `test_ejecutable_…` y `test_precio_…` **siguen rojos** — es lo correcto: F6 los cierra. **Anotarlo**, porque es la prueba de que el invariante funciona.
- Las suites del 159: **igual o mejor** que F0.1.

---

### F6 — Lo ofrecido se ejecuta: la lista de autorizados y los precios se ponen al día

**Objetivo:** que elegir Opus 5 ejecute Opus 5, sin aflojar el cap del ruteo automático.
**Valor:** es lo que convierte el plan en verdadero. **Flag:** ninguna. **Trabajo del operador: ninguno.** **Motores:** solo Claude Code CLI (los otros dos no pasan por `clamp_model`; `harness/model_policy.py:23-30` lo aplica **solo** cuando `runtime == "claude_code_cli"`).

**Archivo 1 — `Stacky Agents/backend/services/llm_router.py`**, símbolo `_OPUS_ALLOWLIST` (hoy `:35`):

```python
# Plan 43 F1 — modelos de tier alto que el operador puede elegir EXPLÍCITAMENTE
# para una corrida puntual. Plan 288: se pone al día contra el catálogo. La lista
# NO afecta el ruteo automático: `clamp_model` sigue capando en CLAUDE_CAP_MODEL
# cuando `allow_opus=False`, que es el default de todos los caminos.
# INVARIANTE (tests/test_plan288_catalogo_vivo.py): todo id de tier prohibido que
# el catálogo OFREZCA tiene que estar acá, o el runner lo degrada en silencio.
_OPUS_ALLOWLIST = {"claude-opus-4-8", "claude-opus-5", "claude-fable-5"}
```

**Lo que NO cambia, y hay que dejarlo escrito en el mismo comentario:**
- `CLAUDE_CAP_MODEL` sigue siendo `"claude-sonnet-5"` (`:32`).
- `_FORBIDDEN_CLAUDE_TIER` sigue siendo `("opus", "fable")` (`:33`).
- La firma y el cuerpo de `clamp_model` (`:38-57`) **no se tocan**: el cambio es de **dato**, no de lógica.
- `CLAUDE_MODELS` (`:24`) **no se toca**: alimenta la ruta `/api/agents/models` de `api/agents.py:1445`, que es otra superficie (§8).

**Efectos verificados de este cambio — se comprobaron antes de escribirlo:**

| Prueba que podría romperse | Veredicto | Evidencia |
|---|---|---|
| `tests/test_adaptive_selector_wiring.py::test_proposal_always_passes_clamp` | **NO se rompe** | Usa el id sintético `"claude-opus-NOT-IN-ALLOWLIST"` (`:237`), que sigue fuera de la lista |
| `services/adaptive_selector.py:34` `assert _MODEL_OPUS in llm_router._OPUS_ALLOWLIST` | **NO se rompe** | `_MODEL_OPUS = "claude-opus-4-8"` (`:31`) sigue en el conjunto (solo se agregan elementos) |
| `tests/test_acceptance_contract.py::test_clamp_model_nunca_opus` | **NO se rompe** | Llama a `clamp_model` con el default `allow_opus=False`, que sigue capando |
| `tests/test_difficulty_routing.py` | **NO se rompe** | Verifica `d.model == clamp_model(d.model)` sobre lo que `decide()` propone, y `decide()` nunca propone opus por sí solo |

**Archivo 2 — `Stacky Agents/backend/harness/pricing.py`**, símbolo `DEFAULT_PRICES` (hoy `:24`):

Hoy tiene `"claude-opus-4": (5.0, 25.0)` y `"claude-fable-5": (10.0, 50.0)` pero **no** `claude-opus-5`. El diccionario matchea **por prefijo**, y `"claude-opus-5"` **no** empieza con `"claude-opus-4"`. Agregar, junto a las otras entradas de Anthropic:

```python
    # Plan 288 — Opus 5. Prefijo propio: "claude-opus-5" NO matchea "claude-opus-4".
    "claude-opus-5": (5.0, 25.0),
```

> **Si el precio real difiere, se corrige el número, no la estructura.** Lo que este plan garantiza es que **exista** una entrada: sin ella, el centro de costos atribuye el gasto a la tarifa por defecto y el informe miente.

**Criterio binario de F6 (los 3 comandos, desde `Stacky Agents/backend`):**

```bash
.venv/Scripts/python.exe -m pytest tests/test_plan288_catalogo_vivo.py -q --no-header -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/test_adaptive_selector.py tests/test_adaptive_selector_wiring.py tests/test_difficulty_routing.py tests/test_acceptance_contract.py -q --no-header -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/test_harness_pricing.py -q --no-header -p no:cacheprovider
```

- El primero: **todo verde** (los 7 casos, incluidos `test_ejecutable_…` y `test_precio_…`).
- El segundo: **exactamente el mismo número que en F0.1 punto 9**. Si baja, el cambio del clamp rompió algo: **parar**.
- El tercero: igual o mejor que su estado previo.

---

### F7 — El lector de la cuenta local: la única fuente dinámica que existe de verdad

**Objetivo:** que Stacky sepa qué modelos tiene **esta** cuenta, leyendo lo que el programa de Claude Code ya guardó en el disco del operador.
**Valor:** cierra los puntos 1 y 2 del comportamiento esperado ("consultar dinámicamente" y "actualizar cuando cambie la disponibilidad") con la **única** fuente que existe (§4.4). Sin red, sin credenciales, sin gasto.
**Flag:** `STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED` (**ON**). **Trabajo del operador: ninguno.** **Motores:** solo aporta al bloque `claude_code_cli`; para Codex y Copilot devuelve `no_aplica` y no toca sus bloques.

**Archivo NUEVO:** `Stacky Agents/backend/services/claude_account_models.py`

**Contrato exacto (los nombres son parte del contrato; no renombrar):**

```python
"""Plan 288 F7 — Qué modelos tiene ESTA cuenta de Claude Code, leído del disco.

TRES REGLAS DURAS, iguales a las de services/model_probe.py:
1. **Nunca invoca un modelo ni sale a la red.** Lee dos archivos de texto locales.
2. **Nunca resta.** Lo leído se SUMA al catálogo; nunca quita un id que ya estaba.
3. **Nunca propaga una excepción.** Sin archivos, con permisos denegados o con un
   JSON roto, devuelve `disponible=False` con el motivo y el catálogo queda igual.

POR QUÉ ESTA FUENTE Y NO OTRA (medido el 2026-08-02, ver Plan 288 §4.4):
  - El programa instalado (2.1.220) NO tiene subcomando de listado: los 3
    candidatos de model_probe.py dan `unknown option`.
  - La ruta de listado del proveedor refleja una clave de interfaz, no una
    suscripción; acá el motor corre con la sesión del programa
    (`oauthAccount.billingType == "stripe_subscription"`).
  - Estos dos archivos SÍ existen y SÍ traen el dato.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("stacky.services.claude_account_models")

__all__ = [
    "LecturaCuenta", "leer_cuenta_claude", "normalizar_id_modelo",
    "ruta_config_claude", "ruta_stats_claude",
]

# El programa respeta CLAUDE_CONFIG_DIR para mover ~/.claude a otro lado.
_ENV_DIR = "CLAUDE_CONFIG_DIR"
# Sufijo de fecha que el programa agrega a algunos ids: claude-haiku-4-5-20251001
_SUFIJO_FECHA = re.compile(r"-\d{8}$")
# Variante de ventana de contexto: claude-fable-5[1m]
_SUFIJO_VARIANTE = re.compile(r"\[[^\]]+\]$")


@dataclass(frozen=True)
class LecturaCuenta:
    disponible: bool
    motivo: str                 # ok | flag_apagada | sin_archivos | json_ilegible | no_aplica
    suscripcion: str            # p. ej. "claude_max"; "" si no se pudo leer
    nivel_de_limite: str        # p. ej. "default_claude_max_20x"; "" si no se pudo leer
    usados: tuple[str, ...]     # ids NORMALIZADOS que esta cuenta ejecutó de verdad
    ofrecidos: tuple[str, ...]  # ids que el programa ofrece de más (con su variante intacta)
    etiquetas: dict             # id_ofrecido -> rótulo que el propio programa le pone


def ruta_config_claude() -> Path:
    """~/.claude.json, o el equivalente si CLAUDE_CONFIG_DIR está definido."""


def ruta_stats_claude() -> Path:
    """~/.claude/stats-cache.json, o el equivalente bajo CLAUDE_CONFIG_DIR."""


def normalizar_id_modelo(crudo: str) -> str:
    """Saca el sufijo de fecha y el de variante. NO toca nada más.

    'claude-haiku-4-5-20251001' -> 'claude-haiku-4-5'
    'claude-fable-5[1m]'        -> 'claude-fable-5'
    'claude-opus-5'             -> 'claude-opus-5'
    """


def leer_cuenta_claude() -> LecturaCuenta:
    """Lee las dos rutas. NUNCA lanza. Respeta la flag."""
```

**Reglas de comportamiento (cada una es un caso de prueba):**

| # | Regla |
|---|---|
| 1 | Flag apagada → `LecturaCuenta(disponible=False, motivo="flag_apagada", …)` y **no se abre ningún archivo** (se verifica con un doble sobre `Path.read_text` que cuenta llamadas: **0**) |
| 2 | Ninguno de los dos archivos existe → `motivo="sin_archivos"`, listas vacías, **sin excepción** |
| 3 | `~/.claude.json` existe pero es JSON inválido → `motivo="json_ilegible"`, **sin excepción**; si el otro archivo sí se pudo leer, lo que salió de ahí **se conserva** |
| 4 | `usados` = las claves de `stats-cache.json → modelUsage` **más** las claves de cada `dailyModelTokens[].tokensByModel`, **normalizadas** y sin repetir, conservando el orden de aparición |
| 5 | `ofrecidos` = los `value` de `~/.claude.json → additionalModelOptionsCache` **más** los ids de `modelAccessCache` si trae alguno (hoy viene `[]`; el lector tolera lista vacía **y** lista de objetos con clave `id` o `value`) |
| 6 | `etiquetas[id] = label` cuando el objeto de `additionalModelOptionsCache` trae `label`; si no trae, no se inventa (no entra al diccionario) |
| 7 | `suscripcion = oauthAccount.organizationType` y `nivel_de_limite = oauthAccount.organizationRateLimitTier`; **nunca** se leen `emailAddress`, `accountUuid` ni `displayName` — no hacen falta y son datos personales |
| 8 | El lector **no cachea por su cuenta**: lo llama `_merge_probe` dentro del refresco de caché que ya existe (300 s). Un archivo que cambia se ve en el siguiente refresco o con `?refresh=true` |
| 9 | Un id que el catálogo **ya tiene** no se duplica; uno nuevo entra con la etiqueta `"<id> (habilitado en tu cuenta)"` o con la etiqueta que trajo el programa |
| 10 | **Nunca resta.** Un id del catálogo que la cuenta no registra **se conserva** |

**Cableado — `Stacky Agents/backend/services/model_catalog.py`, función `_merge_probe` (símbolo, hoy `:111`):**

Después del bloque que suma lo de la sonda y **antes** del `return catalog`, agregar la segunda fuente. Reusa el mismo bloque `cli` que ya está resuelto:

```python
        # ── Plan 288 F7 — segunda fuente: lo que la cuenta local declara ──────
        lectura = leer_cuenta_claude()
        if lectura.disponible:
            for mid in (*lectura.ofrecidos, *lectura.usados):
                if mid in conocidos:
                    continue
                cli.setdefault("models", []).append({
                    "id": mid,
                    "label": lectura.etiquetas.get(mid) or f"{mid} (habilitado en tu cuenta)",
                    "recommended": False,
                })
                conocidos.add(mid)
                agregados_cuenta.append(mid)
        cli["cuenta"] = {
            "disponible": lectura.disponible,
            "motivo": lectura.motivo,
            "suscripcion": lectura.suscripcion,
            "nivel_de_limite": lectura.nivel_de_limite,
            "agregados": agregados_cuenta,
        }
```

- El `import` va **arriba del módulo**, no adentro de la función: `from services.claude_account_models import leer_cuenta_claude`. **Ojo con el ciclo**: `model_catalog` ya importa `claude_code_cli_runner` de forma perezosa dentro de `_merge_probe` por esa razón; `claude_account_models` **no importa nada de Stacky salvo `config`**, así que el import de arriba es seguro. Confirmarlo con `python -c "import services.model_catalog"`.
- **La guarda de pruebas se conserva**: `_merge_probe` ya sale temprano si `STACKY_TEST_MODE` está activo (`services/model_catalog.py:128-129`). El lector de cuenta **debe quedar del lado de adentro de esa guarda** para que ninguna prueba dependa de qué hay en el disco de quien la corre.
- `agregados_cuenta` se inicializa en `[]` junto a `agregados`.
- Si `agregados_cuenta` no está vacío, `cli["source"]` pasa a incluir `+cuenta_local` (concatenar, no reemplazar: hoy puede valer `"static_config_file"` o `"static_config_file+live_probe"`).

**Además, en la misma fase — publicar el motivo de la sonda muerta.** El bloque `cli["probe"]` ya guarda `reason` (`:162-167`). No hay que cambiarlo: solo hay que asegurarse de que **viaje** hasta la pantalla (F8) y de dejar escrito en el comentario del módulo que `no_candidate_worked` es el valor **esperado** en el programa 2.x, para que nadie lo confunda con una avería.

**Archivo de prueba NUEVO:** `Stacky Agents/backend/tests/test_plan288_cuenta_local.py`, con **10 casos**, uno por regla, nombrados `cuenta_flag_apagada_no_abre_archivos`, `cuenta_sin_archivos_no_lanza`, `cuenta_json_roto_conserva_lo_otro`, `cuenta_usados_normaliza_y_dedup`, `cuenta_ofrecidos_tolera_formas`, `cuenta_etiqueta_no_se_inventa`, `cuenta_no_lee_datos_personales`, `cuenta_no_cachea_por_su_cuenta`, `cuenta_no_duplica_ids_del_catalogo`, `cuenta_nunca_resta`.

> **Los 10 usan archivos temporales propios con `tmp_path` + `monkeypatch.setenv("CLAUDE_CONFIG_DIR", …)`. NINGUNO lee el disco real del operador.** Es la diferencia entre una prueba y una lotería.

**Comando y criterio binario:**

```bash
.venv/Scripts/python.exe -m pytest tests/test_plan288_cuenta_local.py -q --no-header -p no:cacheprovider   # 10 passed
.venv/Scripts/python.exe -m pytest tests/test_plan159_model_catalog_loader.py -q --no-header -p no:cacheprovider  # igual o mejor que F0.1
python -c "import services.model_catalog"   # sin ImportError (desde backend, con el .venv)
```

---

### F8 — La respuesta publica de dónde salió cada modelo y si es el respaldo

**Objetivo:** que la pantalla tenga con qué decir la verdad.
**Valor:** cierra el punto 4 del comportamiento esperado. **Flag:** `STACKY_MODEL_CATALOG_ENABLED` (la que ya existe). **Trabajo del operador: ninguno.** **Motores:** aditivo para los tres.

**Archivo a editar:** `Stacky Agents/backend/api/agents.py`, función `model_catalog_route` (símbolo, hoy `:1457`).

**Cambio — puramente aditivo, ninguna clave existente se toca:**

```python
    return jsonify({
        "ok": True,
        "cached_at": catalog["loaded_at"],
        "ttl_sec": TTL_SEC,
        "fallback_used": catalog["fallback_used"],   # ya estaba
        "error": catalog.get("error"),               # Plan 288 — ya estaba en el dict, no viajaba
        "runtimes": runtimes,
    })
```

**Trampa verificada que hay que evitar:** el bloque del plan 264 (`:1485-1500`) **reconstruye** cada entrada de `runtimes` con un diccionario nuevo y usa `_caps["models"] or runtimes[_rt].get("models") or []` (`:1495`). Las claves `probe` y `cuenta` que F7 agregó **sobrevivirían** porque el `{**runtimes[_rt], …}` las conserva — **pero solo si están en `runtimes[_rt]`**. Verificarlo con un caso de prueba explícito:

| Test (en `tests/test_plan288_catalogo_vivo.py`) | Qué prueba |
|---|---|
| `test_respuesta_conserva_probe_y_cuenta_despues_del_enriquecido_de_capacidades` | Con el bloque de capacidades activo, la respuesta de la ruta trae `runtimes.claude_code_cli.probe.reason` **y** `runtimes.claude_code_cli.cuenta.motivo`. **Dos patas: presencia de las dos claves nuevas + presencia de `effort_mode`**, que es la clave que puso el 264 y que no puede desaparecer |
| `test_respuesta_trae_fallback_used_y_error` | Forzando un archivo de catálogo ilegible, la respuesta trae `fallback_used: true` y `error` no vacío |

**Criterio binario:** los 2 casos nuevos en verde y `tests/test_plan159_model_catalog_endpoint.py` igual o mejor que F0.1.

---

### F9 — La pantalla dice de dónde salió la lista (lógica pura + un solo componente)

**Objetivo:** que el operador vea, sin abrir nada, si está mirando su lista o la de respaldo.
**Valor:** cierra el punto 4 del comportamiento esperado del lado visible. **Flag:** ninguna (es dato derivado). **Trabajo del operador: ninguno.** **Motores:** el aviso es por motor, sin bifurcación.

**Archivo NUEVO 1 — lógica pura:** `Stacky Agents/frontend/src/services/modelCatalogOrigin.ts`

```ts
import type { ModelCatalogResponse } from "../api/endpoints";

export type NivelAviso = "ok" | "respaldo" | "parcial";

export interface AvisoCatalogo {
  nivel: NivelAviso;
  /** Texto listo para mostrar. Vacío cuando nivel === "ok". */
  texto: string;
  /** Detalle opcional para el `title` del elemento. Vacío si no hay. */
  detalle: string;
}

/**
 * Decide qué contarle al operador sobre el origen de la lista de un motor.
 * FUNCIÓN PURA: no toca red, no toca el DOM, no lanza nunca.
 */
export function describirOrigenCatalogo(
  res: ModelCatalogResponse | null | undefined,
  runtime: string,
): AvisoCatalogo;
```

**Reglas (cada una es un caso de prueba, 8 en total):**

| # | Entrada | Salida |
|---|---|---|
| 1 | `res` `null`/`undefined` | `{nivel: "respaldo", texto: "Lista de respaldo: no se pudo consultar el catálogo de modelos.", detalle: ""}` |
| 2 | `res.ok === false` | igual que 1, con `res.reason` en `detalle` si viene |
| 3 | `res.fallback_used === true` | `nivel: "respaldo"`, texto que **nombra el motivo** (`res.error`) |
| 4 | catálogo bien, `cuenta.disponible === true` y `cuenta.agregados.length > 0` | `nivel: "ok"`, `texto: ""` — **no se molesta al operador cuando todo salió bien** |
| 5 | catálogo bien pero `cuenta.disponible === false` con `motivo !== "no_aplica"` | `nivel: "parcial"`, texto que dice que la lista es la de fábrica y por qué no se pudo leer la cuenta |
| 6 | `cuenta.motivo === "no_aplica"` (Codex, Copilot) | `nivel: "ok"`, `texto: ""` — **no aplica no es un problema** |
| 7 | `runtime === "github_copilot"` con `error` no vacío | `nivel: "parcial"`, texto con el error de introspección |
| 8 | Un `runtime` que no está en la respuesta | `nivel: "respaldo"`, sin lanzar |

**Archivo NUEVO 2 — prueba:** `Stacky Agents/frontend/src/services/__tests__/modelCatalogOrigin.test.ts`, con los 8 casos, nombrados `origen_sin_respuesta`, `origen_no_ok`, `origen_respaldo_nombra_el_motivo`, `origen_todo_bien_no_molesta`, `origen_cuenta_ilegible_es_parcial`, `origen_no_aplica_no_es_problema`, `origen_copilot_con_error`, `origen_motor_desconocido_no_lanza`.

**Archivo NUEVO 3 — el componente tonto:** `Stacky Agents/frontend/src/components/AvisoCatalogoModelos.tsx`

- Props: `{ runtime: string }`.
- Usa `useModelCatalog()` y `describirOrigenCatalogo`.
- Si `nivel === "ok"` devuelve `null`. Si no, renderiza **un solo** `<p role="note" title={detalle}>{texto}</p>`.
- **Sin estilos escritos a mano en el marcado ni colores en hexadecimal**: los dos ratchets de deuda cuentan por archivo. Si hace falta color, usar las variables del tema que **sí existen** (`--accent`, `--success`, `--danger`, `--border`, `--text-primary`, `--bg-panel`). **`--color-*` NO existe en este tema**: usarla deja el aviso invisible.

**Archivo a editar 4 — `Stacky Agents/frontend/src/hooks/useModelCatalog.ts`:** el cambio es **aditivo**; ningún consumidor actual se rompe.

```ts
export interface UseModelCatalogResult {
  catalog: Record<string, RuntimeModelCatalog>;
  loading: boolean;
  /** Plan 288 — la respuesta cruda, para que la pantalla pueda decir de dónde salió. */
  respuesta: ModelCatalogResponse | null;
}
```

Guardar la respuesta en un `useState` paralelo y devolverla; `resolveModelCatalog` sigue haciendo exactamente lo que hace hoy.

**Archivos a editar 5..8 — montar el aviso en las 4 superficies de selección** (una línea cada una, al lado del selector de modelo que ya existe):

- `Stacky Agents/frontend/src/components/EpicFromBriefModal.tsx`
- `Stacky Agents/frontend/src/components/IncidentResolverModal.tsx`
- `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx`
- `Stacky Agents/frontend/src/pages/TicketBoard.tsx`

En cada uno: `<AvisoCatalogoModelos runtime={<el motor activo de esa pantalla>} />`. **`ModelDecisionChip.tsx` no se toca**: es un indicador de lo que ya se decidió, no un selector.

**Criterio binario de F9:**

```bash
# desde Stacky Agents/frontend
npx vitest run src/services/__tests__/modelCatalogOrigin.test.ts      # 8 passed
npx vitest run src/__tests__/modelSelectorsConsistency.test.ts        # verde (sigue sin listas locales)
npx vitest run src/__tests__/formDebtRatchet.test.ts                  # verde
npx vitest run src/__tests__/uiDebtRatchet.test.ts                    # verde
npx tsc --noEmit                                                      # 0 errores
```

Y `grep -rn "AvisoCatalogoModelos" src | wc -l` ≥ **5** (4 montajes + la definición).

---

### F10 — Los DOS ratchets del arnés, en el MISMO commit que crea los archivos de prueba

**Objetivo:** que el arnés corra las suites nuevas sin poner rojos a los dos guardianes que auditan la lista.
**Archivos:** `Stacky Agents/backend/scripts/run_harness_tests.sh` y `Stacky Agents/backend/scripts/run_harness_tests.ps1`. **Flag:** ninguna. **Trabajo del operador: ninguno.**

> **Por qué en el mismo commit que crea el archivo y no antes:** `tests/test_harness_ratchet_meta.py::test_ratchet_no_referencia_archivos_inexistentes` y `tests/test_plan259_ratchet_script_parity.py` ponen **rojas dos suites hoy verdes** si la lista nombra un archivo que todavía no existe. Y `test_ratchet_clasifica_todos_los_tests` (`test_harness_ratchet_meta.py:43`) las pone rojas si el archivo existe y **no** está ni en la lista ni en el allowlist. **Las dos direcciones fallan: hay que hacerlo junto.**

**Los DOS archivos de prueba nuevos del servidor a registrar:**

```
tests/test_plan288_catalogo_vivo.py
tests/test_plan288_cuenta_local.py
```

**`run_harness_tests.sh`** — la lista abre en `HARNESS_TEST_FILES=(` (hoy `:20`) y cierra en el `)` (hoy `:1066`). Última entrada hoy: `tests/test_plan283_e2e.py` (`:1065`). Es un **array de bash: SIN comas**. Agregar dos líneas nuevas antes del `)`:

```bash
  tests/test_plan288_catalogo_vivo.py
  tests/test_plan288_cuenta_local.py
```

**`run_harness_tests.ps1`** — la lista abre en `$HarnessTestFiles = @(` (hoy `:13`) y cierra en el `)` (hoy `:982`). Última entrada hoy: `"tests/test_plan283_e2e.py"` (`:981`), **sin coma final**. Es un **array de PowerShell: hay que agregarle la coma a la que hoy es la última** y después las dos nuevas:

```powershell
  "tests/test_plan283_e2e.py",
  "tests/test_plan288_catalogo_vivo.py",
  "tests/test_plan288_cuenta_local.py"
```

**Tres reglas que rompen el ratchet si se ignoran:**
1. **Misma ruta relativa exacta en los dos archivos** — la paridad se compara textualmente.
2. **Sin rutas con espacios** — el ratchet no las admite.
3. **NO agregar estos archivos a `backend/tests/harness_ratchet_allowlist.txt`.** Estar en los dos lugares pone roja a `test_allowlist_no_se_solapa_con_ratchet` (`test_harness_ratchet_meta.py:56`). Además el allowlist tiene hoy **194** entradas contra `_ALLOWLIST_MAX = 197` (`:66`) y **solo puede bajar**.

**Los archivos de prueba de la pantalla (`*.test.ts`) NO se registran en ningún lado** — verificado: los dos scripts del arnés solo listan rutas `tests/*.py`; la única mención de `vitest` en `run_harness_tests.sh` es un comentario (`:1011`).

**`tests/test_plan277_clasificacion_local.py` NO se saca de ningún script** (`run_harness_tests.sh:257`, `run_harness_tests.ps1:250`): el motor del 277 sigue vivo (§2.2).

**Criterio binario:**

```bash
.venv/Scripts/python.exe -m pytest tests/test_plan259_ratchet_script_parity.py tests/test_harness_ratchet_meta.py -q --no-header -p no:cacheprovider
```

**Verde, y con el mismo conteo o mayor que las 16 de F0.1 punto 10.** Además:
`grep -c "test_plan288_catalogo_vivo\|test_plan288_cuenta_local" scripts/run_harness_tests.sh scripts/run_harness_tests.ps1` → **2 y 2**.

---

### F11 — Gate de paridad de motores

**Objetivo:** probar que los otros dos motores quedaron **byte-idénticos**.
**Archivos:** solo pruebas. **Flag:** ninguna. **Trabajo del operador: ninguno.**

**Casos, en `tests/test_plan288_catalogo_vivo.py`:**

| Test | Qué prueba |
|---|---|
| `test_paridad_codex_y_copilot_no_cambian_con_la_cuenta_encendida` | Se arma la respuesta con `STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED` en `True` y en `False` y se comparan **clave por clave** los bloques `codex_cli` y `github_copilot`: iguales. **Dos patas: además se verifica que el bloque `claude_code_cli` SÍ cambió** (si no cambia, el lector no está cableado y la primera mitad pasaría por accidente) |
| `test_ningun_simbolo_nuevo_nombra_un_motor` | `grep -riE "codex\|copilot"` sobre `services/claude_account_models.py` y `frontend/src/services/modelCatalogOrigin.ts` da **0 coincidencias**. El único que puede nombrar `claude` es el lector, porque es el nombre del archivo de configuración que lee |

**Criterio binario:** los 2 en verde.

---

### F12 — Cierre: se vuelven a correr los 12 de F0.1 y el smoke visual

**Objetivo:** probar que nada verde se puso rojo y que el operador ve lo que tiene que ver.
**Flag:** ninguna. **Trabajo del operador: solo el smoke visual (5 minutos), y es opcional — todo lo demás es automático.**

**(a) Regresión:** correr los 12 comandos de F0.1. **Cada uno da igual o mejor.** El 12 (ayuda de flags) tiene que dar **exactamente las mismas fallidas y los mismos nombres**. **Se pega la salida literal, no se reporta "todo pasa".**

**(b) Smoke visual — 8 pasos, con el resultado esperado escrito:**

| # | Paso | Resultado esperado |
|---|---|---|
| 1 | Abrir el tablero de tickets de un proyecto **GitLab** con la flag `STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED` **encendida** | **No aparece** el bloque de tipo/padre ni el botón "Guardar clasificación". **Sí aparecen** las acciones de siempre |
| 2 | Cambiar a la vista de árbol o de grafo | **No aparece** el botón "Ver qué se va a cambiar" ni "Publicar etiquetas en GitLab" |
| 3 | Abrir un ticket de un proyecto **Azure DevOps** | La tarjeta se ve **exactamente igual que antes** del plan |
| 4 | Correr la sincronización de GitLab | Los contadores `usados_local_tipo` / `usados_local_padre` **siguen funcionando**: el motor no se tocó |
| 5 | Abrir cualquier selector de modelo (crear épica desde un resumen, resolver una incidencia, tablero de planes) | **Aparecen `Opus 5` y `Fable 5`** en la lista, arriba |
| 6 | Elegir `Opus 5` y lanzar un agente con el motor Claude Code | En la traza de la ejecución, **solicitado y ejecutado coinciden**: no aparece la línea de degradado de `describeDowngrade` |
| 7 | Renombrar temporalmente `backend/config/model_catalog.json` y recargar | **Aparece el aviso de lista de respaldo** con el motivo, y el selector **sigue teniendo todos los modelos** (nunca queda vacío). Restaurar el nombre |
| 8 | Abrir el panel de flags del arnés y buscar `STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED` | Aparece, en la categoría de motores, **encendida**, con su texto en llano |

---

## 7. Riesgos y mitigaciones

### 7.1 RIESGO #1 — Frontera con el plan 287 (Bloque A)

**El problema, concreto:** el plan 287 está **escrito pero no implementado** (verificado el 2026-08-02: `frontend/src/components/ticket/TicketFullView.tsx` no existe) y nombra `JerarquiaLocalControl` **dos veces** como acción que su ficha va a **reusar** (`docs/287_…md:109` y `:762`). Si el 288 se implementa primero y después alguien implementa el 287 al pie de la letra, **la clasificación vuelve a aparecer**, ahora en la ficha nueva, y el ítem del operador se deshace solo.

**Mitigación en tres capas:**
1. **Orden declarado:** el 288 se puede aplicar **antes o después** del 287 — no hay dependencia técnica. Lo que **no** puede pasar es que el 287 se implemente **sin leer esta sección**.
2. **F3 es condicional y cubre las dos ramas** con el mismo centinela.
3. **El centinela de F1 es un gate de commit**, no un consejo. Si el 287 monta `JerarquiaLocalControl` en su ficha, `plan288SuperficieClasificacion.test.ts` se pone rojo. **Instrucción para quien implemente el 287: eliminar `JerarquiaLocalControl` y `PublicarEtiquetasGitLab` de la lista de "acciones reusadas" de su §3.3 y §7; el resto de su ficha no cambia.**

**Por qué NO se borran los dos componentes** (decisión tomada, no pendiente): borrarlos genera un conflicto con un plan ya escrito y con una sesión paralela viva que puede tenerlos sucios; el criterio del operador es **de vista**, no de repositorio; y borrarlos **no baja ningún ratchet** (verificado: no figuran en ninguno de los tres baselines de deuda). El borrado físico queda **fuera de scope** (§8) con su condición escrita.

### 7.2 RIESGO #2 — Supuesto de capacidad del ítem 2

**El problema:** "consultar dinámicamente los modelos habilitados para el usuario" suena a que existe una consulta. **No existe.** Un plan que la prometa entrega una fase inimplementable.

**Mitigación:** §4.4 mide los cinco caminos y descarta tres **con la salida del comando pegada**. El plan implementa los dos ejecutables y lo dice en el propio código (docstring de `services/claude_account_models.py`). **Lo que este plan NO promete:** que el listado refleje una autorización del proveedor. Refleja **lo que el programa de Claude Code guardó sobre esta cuenta en este equipo** — que en la práctica es la mejor señal disponible, porque incluye los modelos que la cuenta **ejecutó de verdad**, pero **no es una consulta de suscripción**.

**Riesgo residual y su tapón:** el formato de `~/.claude.json` es interno del programa y puede cambiar sin aviso. Por eso el lector es **tolerante por diseño** (reglas 2, 3, 5 de F7), **nunca resta** y **nunca lanza**: si el formato cambia, Stacky vuelve exactamente al comportamiento de hoy y lo **dice** en el aviso (`nivel: "parcial"`).

### 7.3 RIESGO #3 — Aflojar el clamp puede subir el gasto

**El problema:** `_OPUS_ALLOWLIST` es una barrera de costo. Ampliarla habilita modelos caros.

**Mitigación:** **el ruteo automático NO se toca.** `clamp_model` con su default `allow_opus=False` sigue capando en `claude-sonnet-5`, y `allow_opus_for_run` sigue exigiendo **elección explícita del operador para una corrida puntual** y sigue excluyendo al agente de DevOps (`services/claude_code_cli_runner.py:545-548`). El caso de prueba `test_ejecutable_el_ruteo_automatico_sigue_capado_en_sonnet` (F4) lo congela **en la misma corrida** que el caso que amplía. Y F6 agrega el precio de `claude-opus-5` para que el centro de costos no subestime.

### 7.4 RIESGO #4 — Sesión paralela viva en el árbol

**El problema:** los planes 286 y 287 los está trabajando otra sesión, que ya movió el cierre de la lista del arnés (`run_harness_tests.sh` cerraba en `:1061` según el 287 y hoy cierra en `:1066`).

**Mitigación:** F0.0 revalida por símbolo antes de tocar nada; el documento manda anclar por símbolo cuando el número no coincide; y **está prohibido** `git stash`, `git reset`, `git checkout --`, `git rebase` y `git commit --amend`. Para commitear, `git commit -m "<mensaje>" -- "<rutas>"` — **el `-m` va ANTES del `--`**, y un archivo sin seguimiento necesita `git add -- "<ruta>"` primero.

### 7.5 RIESGO #5 — Falsos verdes

| Trampa | Tapón en este plan |
|---|---|
| Un `not.toContain` que pasa porque la ruta está mal | `leer()` afirma `existsSync` **antes** de leer, y cada `it` tiene aserciones de **presencia** |
| `pytest -k` sin coincidencias sale con código 0 | Todos los criterios exigen el **conteo** (`N passed`), no el código de salida |
| `pytest tests` entero como veredicto | Prohibido explícitamente en la cabecera de §6: **un archivo por vez** |
| Un ratchet ya rojo de fábrica que se confunde con regresión propia | §4.5 los declara con nombre; los criterios son en **delta** |
| Una prueba que lee el disco real de quien la corre | F7 obliga a `tmp_path` + `CLAUDE_CONFIG_DIR` en los 10 casos |
| `npx vitest run <ruta inexistente>` sale 1 pero pipeado se pierde | Correr sin pipe y mirar la salida |

---

## 8. Fuera de scope (explícito, para que nadie lo agregue "de paso")

1. **Borrar `JerarquiaLocalControl.tsx` y `PublicarEtiquetasGitLab.tsx`.** Condición para hacerlo en un plan futuro: que el 287 esté implementado **y** que su documento ya no los nombre como acciones reusadas. Hasta entonces, quedan.
2. **Borrar el motor de la clasificación local** (columnas, ruta `PATCH`, contadores de sincronización, flags del 277). Tiene consumidor de producción (§2.2).
3. **Cambiar el `default_model` del catálogo.** Es una decisión de costo del operador, no de este plan.
4. **Unificar `/api/agents/models` (que sirve `llm_router.CLAUDE_MODELS`, 3 modelos) con `/api/agents/model-catalog`.** Son dos superficies con dos consumidores distintos; unificarlas es un plan propio.
5. **Borrar `services/model_probe.py`.** La regla del repositorio es sumar, nunca restar: una versión futura del programa puede agregar el subcomando. Este plan **publica su motivo de fallo**, no lo borra.
6. **Agregar `claude-fable-5[1m]` al catálogo.** La caché de la cuenta declara `s1mAccessCache.hasAccess: false`; F7 lo normaliza a `claude-fable-5` y no ofrece la variante.
7. **Cualquier camino de escritura nuevo** hacia Azure DevOps, GitLab o el disco del operador.
8. **Tocar el catálogo de Codex o de Copilot.**

---

## 9. Orden de implementación y Definición de Terminado

### 9.1 Orden numerado (cada paso es un commit; **ninguno se saltea**)

| # | Fase | Bloque | Depende de |
|---|---|---|---|
| 1 | **F0.0** barrido de anclajes | — | — |
| 2 | **F0.1** línea base medida | — | F0.0 |
| 3 | **F1** centinela de dos patas (queda ROJO a propósito) | A | F0.1 |
| 4 | **F2** retirar los tres montajes | A | F1 |
| 5 | **F3** frontera con el 287 (condicional) | A | F2 |
| 6 | **F4** centinela del catálogo (queda ROJO a propósito) | B | F0.1 |
| 7 | **F5** catálogo al día en los 3 archivos | B | F4 |
| 8 | **F6** lo ofrecido se ejecuta + precios | B | F5 |
| 9 | **F7** lector de la cuenta local + flag (las 6 patas vivas de §5.2) | B | F6 |
| 10 | **F8** la respuesta publica origen y respaldo | B | F7 |
| 11 | **F9** la pantalla dice de dónde salió la lista | B | F8 |
| 12 | **F10** los DOS ratchets, junto con los archivos de prueba | B | F4, F7 |
| 13 | **F11** gate de paridad de motores | B | F7 |
| 14 | **F12** regresión completa + smoke visual | — | todas |

> El Bloque A (pasos 3-5) y el Bloque B (pasos 6-13) son **independientes**: se pueden implementar en cualquier orden entre sí, o en dos commits separados. Dentro de cada bloque, el orden es **obligatorio**.

### 9.2 Definición de Terminado (global, binaria)

1. **K0 = 0, K1 = 0, K2 = 4** — `npx vitest run src/__tests__/plan288SuperficieClasificacion.test.ts` en verde con 3 (o 4) casos.
2. **K3 = 1** — `grep -c "usados_local_tipo" backend/services/gitlab_sync.py` ≥ 1, y `tests/test_plan277_clasificacion_local.py` con el **mismo conteo** que en F0.1.
3. **`plan277JerarquiaLocal.test.ts` sigue en 8 passed sin haberlo tocado.**
4. **Si `TicketFullView.tsx` existe**, el centinela lo cubre con su cuarto caso.
5. **K4 = 0, K5 = 0, K6 = 1** — `tests/test_plan288_catalogo_vivo.py` **todo verde**, `tests/test_plan288_cuenta_local.py` con **10 passed**.
6. **La flag nueva está viva en sus 6 patas reales:** `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py`, `tests/test_flags_env_read_meta.py` y `tests/test_harness_flags_bounds.py` **verdes**; `tests/test_harness_flags_help.py` con **exactamente** las mismas fallidas de F0.1.
7. **K7 ≥ 4** — el aviso está montado en las 4 superficies de selección y su lógica pura tiene 8 casos verdes.
8. **Los DOS ratchets del arnés en verde**, con las 2 rutas nuevas en los dos scripts y **ninguna** en el allowlist.
9. **Paridad de motores probada:** los bloques `codex_cli` y `github_copilot` idénticos con la flag encendida y apagada, **y** el bloque `claude_code_cli` distinto (la contra-prueba).
10. **`npx tsc --noEmit` en 0 errores** y los 4 ratchets de la pantalla en verde.
11. **Los 12 comandos de F0.1 vueltos a correr, con la salida literal pegada en el registro de implementación.** "Todo pasa" **no es evidencia**.
12. **Trabajo del operador: ninguno.** La única flag nueva nace **ON**; nada exige configuración; el smoke visual es opcional.
