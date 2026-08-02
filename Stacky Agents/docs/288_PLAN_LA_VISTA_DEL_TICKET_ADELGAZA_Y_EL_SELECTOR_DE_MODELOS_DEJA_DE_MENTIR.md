# Plan 288 — La vista del ticket adelgaza y el selector de modelos deja de mentir

**Estado:** PROPUESTO — **v1 → v2** (crítica adversarial aplicada)
**Fecha v1:** 2026-08-02 · **Fecha v2:** 2026-08-02
**Rama al escribir:** `docs/plan-279`
**Veredicto de la crítica sobre v1:** **RECHAZADO — 8 bloqueantes.** 76 de 85 anclajes eran correctos; el fallo **no fue de anclajes** sino de **supuestos de capacidad** y de **contradicciones entre fases**.
**Alcance:** dos ítems pedidos textualmente por el operador, independientes entre sí y en bloques separados.
**Bloque A** — retirar la superficie de "Clasificación" de la vista de tickets (interfaz solamente; cero cambios de datos, cero cambios de servidor).
**Bloque B** — el selector de modelos de Claude Code deja de ofrecer una lista fija que no coincide con la cuenta (servidor + interfaz; cero escrituras nuevas, cero consumo de modelo).
**Antecesores que se reusan, no se re-implementan:** 43 y 212 (cap de tier + allowlist + traza solicitado-vs-efectivo + sonda del programa instalado), 159 (catálogo único de modelos/efforts), 264 (matriz de capacidades por motor), 277 (clasificación local de jerarquía), 287 (ficha del ticket a pantalla completa — **frontera declarada en §7.1**).

> **Todo anclaje `archivo:línea` de este documento se verificó abriendo el archivo el 2026-08-02, y los de la v2 se RE-verificaron tras la crítica.** Los hechos externos (versión del programa de línea de comandos de Claude Code, salida de sus subcomandos, contenido de la configuración de la cuenta) se midieron **ejecutando los comandos**, y la salida literal está pegada en §4.4. Donde un número de línea puede correrse porque hay una sesión paralela viva en este árbol, el documento da además el **símbolo**; si el número no coincide, **manda el símbolo**.

---

## 0. CHANGELOG v1 → v2

Cada bullet cierra un hallazgo de la crítica. Los `C#` son los identificadores del informe.

**Bloqueantes cerrados**

- **C1 — `claude-fable-5[1m]`, `glm-4.7`, `glm-5.2`, `qwen2.5:3b`, `qwen2.5-coder:7b`, `qwen3-coder:30b-a3b-q4_K_M`.** El lector de cuenta de la v1 habría inyectado **esos seis ids** en el selector de Claude Code — **medido sobre el disco real del operador el 2026-08-02**, no supuesto. La v1 empeoraba exactamente lo que el operador pidió arreglar. **v2:** F7 pasa por un **filtro duro de admisión de tres condiciones** (§6.F7 regla 5) y publica lo descartado en `cuenta.omitidos` con su motivo, en vez de esconderlo.
- **C2 — F6 rompía TRES pruebas verdes.** Agregar `claude-fable-5` a `_OPUS_ALLOWLIST` pone rojas `tests/test_llm_router_opus_flag.py::test_fable_still_blocked_with_allow_opus` (`:41-43`), `tests/test_plan212_opus_end_to_end.py::test_decide_allow_opus_true_still_blocks_fable` (`:43-44`) y `tests/test_plan212_opus_end_to_end.py::test_is_opus_allowlisted` (`:52-55`) — la segunda **registrada en los dos scripts del arnés**. La tabla "Efectos verificados" de la v1 no las nombraba. **v2:** **`claude-fable-5` sale del alcance por completo** (catálogo y allowlist). F6 agrega **un solo id**: `claude-opus-5`. §8.9 explica por qué y qué haría falta para revisarlo.
- **C3 — F7/F8/F11 tenían criterios inalcanzables.** `_merge_probe` retorna temprano bajo `STACKY_TEST_MODE` (`services/model_catalog.py:128-129`) y §6 obliga a exportar `STACKY_TEST_MODE=1` antes de todo `pytest`: el cableado de la v1 nunca corría en pruebas, así que `cuenta.motivo` jamás aparecía en la respuesta y la contra-pata de F11 ("el bloque `claude_code_cli` SÍ cambió") no podía pasar. **v2:** el lector se cablea en una **función propia `_merge_cuenta`**, fuera de `_merge_probe`, **sin guarda de modo de prueba**, determinista porque siempre resuelve las rutas desde `CLAUDE_CONFIG_DIR` (§6.F7 cableado).
- **C4 — la flag nueva quedaba gateada por otra flag.** `_merge_probe` retorna en `:123-124` si `STACKY_MODEL_PROBE_ENABLED` está apagada: apagar la sonda mataba el lector de cuenta en silencio. Flag declarada independiente, implementada dependiente. **v2:** al vivir en `_merge_cuenta`, el lector depende **solo** de su propia flag. F7 tiene un caso de prueba dedicado.
- **C5 — contradicción §3.1 ↔ F11 ↔ F9 regla 6.** §3.1 prometía `{"disponible": false, "motivo": "no_aplica"}` para Codex y Copilot, pero F11 exige que esos dos bloques queden **byte-idénticos**: no se les puede agregar la clave. La regla 6 de F9 era entonces **un gate que no podía fallar nunca** (adorno) y ninguna regla cubría el caso real: `cuenta` **ausente**. **v2:** `cuenta` vive **solo** en `claude_code_cli`; la regla 6 pasa a ser "runtime distinto de `claude_code_cli` **o** `cuenta` ausente ⇒ `ok`, sin texto", que es el caso que de verdad ocurre.
- **C6 — F9 exigía `tsc` en 0 con tipos inexistentes.** `ModelCatalogResponse` (`frontend/src/api/endpoints.ts:1159-1166`) **no tiene** `error`; `RuntimeModelCatalog` (`:1140-1157`) **no tiene** `cuenta` ni `probe`. La v1 leía las tres y nunca mandaba editar ese archivo. **v2:** F8 incorpora la edición de `endpoints.ts` con el texto literal de los tres campos.
- **C7 — contrato contradictorio de `ofrecidos`.** El dataclass de la v1 decía "con su variante intacta" y §8.6 decía "F7 lo normaliza y no ofrece la variante". Irresoluble para un modelo menor. **v2:** `ofrecidos` **siempre** viene normalizado; la variante cruda viaja aparte en `crudos` solo para diagnóstico.
- **C8 — el invariante K5 no cubría el camino dinámico ni al agente DevOps.** La prueba de la v1 miraba el archivo estático; F7 abría una puerta por la que puede entrar cualquier id. Y `allow_opus_for_run` devuelve `False` para `agent_type == "devops"` (`services/claude_code_cli_runner.py:545-548`), así que Opus 5 se degrada en silencio **para ese agente**. **v2:** el invariante se prueba sobre el **catálogo efectivo ya fusionado**, el filtro de F7 lo garantiza por construcción, y el aviso de la pantalla dice lo del agente de DevOps (§6.F9 regla 9).

**Importantes cerrados**

- **C9 — el tapón de F2 era inerte.** `frontend/tsconfig.json` tiene `"noUnusedLocals": false`, así que `tsc --noEmit` **nunca** reporta una variable sin uso; y como no hay `allowJs`, **`TicketGraphView.jsx` no lo mira ningún `tsc`**. **v2:** F2 verifica el `.jsx` con `npx vite build`, que sí lo parsea, y el tapón se reescribe contra lo que de verdad detecta.
- **C10 — "actualización ante cambios" no se cumplía.** `useModelCatalog` cachea la promesa **a nivel de módulo** (`frontend/src/hooks/useModelCatalog.ts:12-19`) y nunca la invalida: una pestaña abierta se queda con la primera lista para siempre. **v2:** **[ADICIÓN ARQUITECTO] F9.1** — invalidación automática y refresco explícito, sin trabajo del operador.
- **C11 — línea base incompleta.** F0.1 no medía los dos archivos que la v1 iba a romper. **v2:** entran a F0.1 como puntos 13 y 14, y siguen ahí aunque ahora no se toquen (son el gate que prueba que la poda de fable se respetó).
- **C12 — `_EMERGENCY_FALLBACK` se muta en producción.** `load_model_catalog` asigna la **referencia** del diccionario de módulo (`services/model_catalog.py:103-104`) y `_merge_probe` le hace `append`: la constante queda contaminada para siempre. La v1 agregaba un segundo escritor sobre el mismo defecto. **v2:** F7.0 corrige con una copia profunda y una prueba que lo congela.
- **C13 — cómo se lee la flag.** Si el módulo nuevo usa `os.getenv`, `tests/test_flags_env_read_meta.py` se pone rojo (escanea `api/` y `services/`). **v2:** F7 da la línea literal con `config.config` y lo declara regla dura.
- **C14 — cambio de política disfrazado de dato.** Ampliar la allowlist a fable revierte una decisión de costo tomada y **testeada** por los planes 43 y 212. **v2:** eliminado (ver C2).
- **C15 — K7 se medía con `grep | wc -l`.** Cuenta líneas: el `import` y el uso en el mismo archivo suman 2, así que el umbral se alcanzaba sin montar nada. **v2:** K7 se mide con una prueba que verifica **los 4 archivos por nombre**.
- **C16 — ratchets de pantalla incompletos.** El plan nombraba 4; en `frontend/src/__tests__/` hay **once**. Un `.tsx` nuevo con texto visible tiene que pasar por los que aplican. **v2:** F9 corre la lista enumerada.

**Menores cerrados**

- **C17 — anclajes corregidos:** `docs/287…:109 → :145`, `:762 → :1041`; `backend/api/tickets.py:830 → :836` y `:900 → :923`; `backend/models.py:57 → :61` y `:141 → :147`; `services/harness_flags.py:610 → :614` y `:7186 → :7231`; `frontend/src/types.ts:115` es el comentario (los campos están en `:119-120`); en `plan277JerarquiaLocal.test.ts` el `:32` es un `describe` y el primer `it` está en `:33`.
- **C18** — se agrega la huella de regresión en `docs/sistema/error_fingerprints.json` (F12.c).
- **C19** — §4.4(a) decía `exit=1`; medido con tubería el código que se ve es el del último comando. Se corrige la forma de medirlo.
- **C20** — la palabra "Clasificación" **no existe** en `frontend/src`. Los rótulos reales son "Tipo (solo en Stacky)", "Cuelga del ticket número", "Guardar clasificación" y "Ver qué se va a cambiar". §4.1 lo dice para que el smoke busque lo correcto.

**Adiciones de arquitecto (no estaban en la v1)**

- **[ADICIÓN ARQUITECTO] F9.1 — el catálogo se refresca solo.** Cierra el punto 2 del pedido del operador ("actualización ante cambios"), que la v1 daba por cumplido y no cumplía.
- **[ADICIÓN ARQUITECTO] F7 regla 6 — `cuenta.omitidos`.** Lo que se descarta se **explica**, no se esconde: el operador ve por qué un modelo que su cuenta usó no está en la lista.

---

## 1. Objetivo y KPI

### 1.1 Objetivo

Dos defectos que el operador reportó con sus palabras, y que este plan cierra sin agregarle una sola tarea:

**A. La vista del ticket muestra un bloque que no sirve para gestionar el ticket.** El control de clasificación local (tipo local + padre local + publicar etiquetas) se monta en **tres** lugares de la vista de tickets. Ninguno de los tres aporta a la gestión del ticket: son herramientas de curaduría de jerarquía que el plan 277 construyó para un backfill puntual de GitLab. Este plan **las retira de la vista** y **conserva intacto el motor de datos**, porque el motor tiene un consumidor de producción que no es la vista (§2.2).

**B. El selector de modelos de Claude Code ofrece una lista fija que no es la del operador.** El catálogo es un archivo fechado el **2026-07-17** con 4 modelos. La cuenta del operador **ya ejecutó `claude-opus-5`** — 4.321.237 unidades de consumo el 2026-07-28, medido en su propia caché local — y `claude-opus-5` **no está en la lista**. Peor: aunque estuviera, el camino de ejecución lo **degradaría en silencio a `claude-sonnet-5`**, porque la lista de modelos de tier alto autorizados es un literal de un solo elemento que quedó viejo (§4.3). Este plan pone la lista al día, **hace que lo ofrecido sea realmente ejecutable**, agrega una fuente **real y verificada** de "qué modelos tiene esta cuenta" **con filtro de admisión**, y hace que la pantalla **diga en voz alta** cuándo está mostrando la lista de respaldo, cuándo no pudo leer la cuenta y **qué descartó y por qué**.

### 1.2 KPI — todos binarios, todos con comando

| # | KPI | HOY (medido 2026-08-02) | Meta del 288 | Comando que lo mide (desde `Stacky Agents`) |
|---|---|---|---|---|
| **K0** | Montajes de `JerarquiaLocalControl` en la vista de tickets | **2** (`pages/TicketBoard.tsx:713`, `components/TicketGraphView.jsx:486`) | **0** | `npx vitest run src/__tests__/plan288SuperficieClasificacion.test.ts` |
| **K1** | Montajes de `PublicarEtiquetasGitLab` en la vista de tickets | **1** (`pages/TicketBoard.tsx:1309`) | **0** | ídem K0 |
| **K2** | Acciones de ticket que **siguen** en la tarjeta | **4** en `TicketBoard.tsx` (`FinishWorkButton:586`, `CreateChildTaskButton:611`, `TicketLocalInsightButton:706`, `RecoverExecutionButton:572`) | **4** | ídem K0 |
| **K3** | Motor de datos de la clasificación con consumidor de producción vivo | **1** (`services/gitlab_sync.py:51-57`, contadores `usados_local_tipo` / `usados_local_padre`) | **1** — no se toca | `grep -c "usados_local_tipo" backend/services/gitlab_sync.py` ≥ 1 |
| **K4** | Modelos de la familia Claude 5 que la cuenta usó **y son ejecutables** y el catálogo NO ofrece | **1** (`claude-opus-5`) | **0** | `.venv/Scripts/python.exe -m pytest tests/test_plan288_catalogo_vivo.py -k paridad -q` |
| **K5** | Modelos del catálogo **efectivo** que el camino de elección explícita **degrada en silencio** | **1 de 4** hoy (`claude-opus-4-8` cuando nadie pide elección explícita) | **0** en el catálogo efectivo (archivo + sonda + cuenta) | `.venv/Scripts/python.exe -m pytest tests/test_plan288_catalogo_vivo.py -k ejecutable -q` |
| **K5b** | Ids **descartados** por el filtro de admisión que quedan **explicados** en la respuesta | **n/a** (no existe el filtro) | **100 %** — todo descarte lleva motivo en `cuenta.omitidos` | `.venv/Scripts/python.exe -m pytest tests/test_plan288_cuenta_local.py -k omitidos -q` |
| **K6** | Fuentes de verdad sobre "qué modelos tiene esta cuenta" leídas por Stacky | **0** (`grep -rn "additionalModelOptionsCache\|stats-cache\|oauthAccount" backend/` → **0 hits**) | **1** (`services/claude_account_models.py`) | `ls "backend/services/claude_account_models.py"` |
| **K7** | Superficies de selección de modelo que avisan el origen de la lista | **0** — `useModelCatalog` **descarta** `fallback_used`: devuelve solo `{catalog, loading}` (`frontend/src/hooks/useModelCatalog.ts:21-24`, `:49`) | **4**, por nombre de archivo | `npx vitest run src/__tests__/plan288AvisoMontado.test.ts` |
| **K8** | Sondas del programa instalado que hoy **siempre fallan** y nadie lo sabe | **1** (`services/model_probe.py:29-33`, 3 candidatos, los 3 dan `unknown option`) | **1, pero con el motivo publicado** en la respuesta y visible en la pantalla | §4.4 + `probe.reason` en la respuesta |
| **K9** | Refrescos posibles del catálogo en una pestaña abierta | **1** (la promesa es de módulo y no se invalida nunca: `useModelCatalog.ts:12-19`) | **N** — automático al volver a la pestaña + botón explícito | `npx vitest run src/services/__tests__/modelCatalogRefresh.test.ts` |
| **K10** | Deuda de formularios / de interfaz que este plan agrega | — | **0** (solo puede bajar) | los 11 ratchets de §6.F9 |
| **K11** | Flags nuevas | — | **1**, y nace **ON** | §5 |

---

## 2. Por qué ahora, y qué gap cierra respecto de los planes recientes

### 2.1 Bloque A — la serie 276→287 llenó la pantalla; falta podarla

- El **277** trajo la clasificación local de jerarquía para GitLab: el operador dice de qué tipo es un ticket y de cuál cuelga, **sin escribir en el GitLab de la empresa**. Fue correcto para lo que resolvía: un backfill de jerarquía sobre un GitLab que no tiene modelo de relaciones.
- El **282** y el **286** hicieron que el ruteo por proveedor deje de mentir, y el **287** propone abrir el ticket entero en una ficha a pantalla completa. Es decir: **la vista del ticket está por ganar densidad**, no por perderla.
- Justo por eso este es el momento de sacar lo que no aporta. Un control de curaduría de jerarquía, con dos campos editables y un botón que escribe en el GitLab de la empresa, **no es información de gestión del ticket**: es una herramienta de mantenimiento de datos que se coló en la ficha porque ahí estaba el ticket a mano.
- **El 284 y el 285 dejaron la lección aplicable acá**: verificar el escritor y nunca el lector deja funciones vivas que nadie mira. El espejo de esa lección es este bloque: **hay superficie de interfaz viva que nadie usa y que le cuesta atención al operador en cada ticket que abre**.

### 2.2 El hecho que decide el alcance del Bloque A

`lib/jerarquiaLocal.ts` y el motor del servidor **NO se borran**, y la razón está medida:

| Evidencia (re-verificada 2026-08-02) | Consecuencia |
|---|---|
| `backend/services/gitlab_sync.py:51-57` define `_CONTADORES_LOCAL` con 4 contadores (`usados_local_tipo:54`, `superseded_tipo`, `usados_local_padre:56`, `superseded_padre`) y `:129-136` documenta que la clasificación local **rellena el vacío** cuando GitLab no dice nada | El motor tiene un **consumidor de producción que no es la vista**: la sincronización. Borrarlo cambia el dato que ve el operador en el tablero |
| `backend/api/tickets.py:836` `_clasificacion_local_habilitada()` y `:923` el segundo uso, en la ruta `PATCH` que persiste | La ruta del servidor sigue existiendo y sigue gateada por su flag del 277 |
| `backend/models.py:61` y `:147` — las columnas locales viajan en `to_dict()` | Retirar la interfaz no cambia ni una clave del contrato |
| `backend/tests/test_plan277_clasificacion_local.py` está registrado en los DOS scripts del arnés (`scripts/run_harness_tests.sh:257`, `scripts/run_harness_tests.ps1:250`) | Como el motor no se toca, **ese archivo no se saca de ningún script**. §6.F10 lo dice explícito para que nadie lo borre "por prolijidad" |
| `frontend/src/__tests__/plan277JerarquiaLocal.test.ts` — sus **8 casos** importan **solo funciones puras de `lib/jerarquiaLocal.ts`** (verificado: `describe` en `:32,63,90,135`; `it` en `:33,41,54,64,79,91,136,158`) | El archivo de prueba del 277 **queda verde sin tocarlo**. Este plan no borra ni una prueba |

### 2.3 Bloque B — el catálogo quedó viejo y el clamp lo hace peor

- El **159** creó el catálogo único leído de disco con caché por fecha de modificación. Correcto, pero es **un archivo estático**: `backend/config/model_catalog.json` dice `"updated_at": "2026-07-17"`.
- El **212 F6** vio el problema y agregó una sonda al programa instalado (`services/model_probe.py`). La idea es la correcta. **El problema es que los tres subcomandos que prueba no existen** en el programa instalado hoy (§4.4). La sonda está viva, corre en producción con su flag en ON, y **siempre devuelve `no_candidate_worked`**. Sus pruebas (`tests/test_plan212_model_probe.py`) la ejercitan con dobles, así que están verdes y no revelan nada: es el caso de libro de **prueba verde sobre una capacidad muerta**.
- El **264** cerró el "modelo y effort elegibles en todo punto de uso" y montó `runtime_capabilities.capabilities_for`, que **reconstruye** la lista de modelos en la respuesta (`backend/api/agents.py:1489-1498`, con `_caps["models"] or runtimes[_rt].get("models") or []` en `:1495`). **Verificado el 2026-08-02:** `capabilities_for` deriva `models` del **catálogo vivo ya fusionado** (`services/runtime_capabilities.py:79,82`), así que lo que agregue este plan **sí llega a la pantalla**. No es una capa que anule el cambio, pero sí es una capa que hay que respetar: es la que borraría cualquier clave que no venga en `runtimes[_rt]`.
- Lo que ninguno de los tres cerró: **que lo ofrecido sea ejecutable**, **que la pantalla diga cuándo está mostrando el respaldo** y **que la lista se actualice sin recargar la aplicación**.

---

## 3. Principios y guardarraíles (se verifican en el DoD)

1. **Human-in-the-loop innegociable.** Este plan **no agrega ni un solo camino de escritura nuevo**. El Bloque A **quita** un botón que escribía en el GitLab de la empresa; el Bloque B solo **lee** (archivos locales y el archivo de catálogo). Ningún cambio decide nada por el operador. **Y ninguna decisión de costo se toma sola:** subir un modelo de tier alto a la lista de autorizados es una decisión explícita, escrita y acotada (§8.9).
2. **Mono-operador, sin autenticación real.** No hay roles ni permisos. `403` significa **flag apagada**, nunca permiso, y el cuerpo lo dice: `{"error": "feature_disabled"}`.
3. **Cero trabajo extra para el operador.** La única flag nueva nace **ON**. El Bloque A **no agrega flag**: retirar algo de la vista no puede exigir que el operador encienda un interruptor para que se retire (§5.3). El refresco de F9.1 es automático.
4. **Toda configuración del operador va por la pantalla.** La flag nueva es `env_only=False` y aparece en el panel del arnés.
5. **No degradar.** Ningún bucle, ningún sondeo periódico, ninguna llamada a un modelo. El lector de cuenta del Bloque B lee **dos archivos de texto del disco local**, con la misma caché por tiempo de vida que ya tiene el catálogo (300 s), y **nunca lanza**. El refresco de F9.1 dispara **como mucho una petición** por vuelta a la pestaña, y solo si pasó el tiempo de vida.
6. **Compatible hacia atrás.** El Bloque B **nunca quita del catálogo un id que ya estaba** — es la regla que el propio repositorio escribió en `services/model_catalog.py:113-117` ("UNION, nunca resta"). Ninguna clave existente de ninguna respuesta desaparece. **Matiz que la v1 no hacía:** "nunca resta" se aplica a **lo que ya estaba en el catálogo**, no obliga a **admitir todo lo que una fuente externa proponga**; un id nuevo que no pasa el filtro de admisión **no entra**, y se dice por qué.
7. **Español** en el documento, en los nombres de símbolos nuevos del dominio y en todo texto visible.
8. **`services/` no importa de `api/`.** El módulo nuevo vive en `services/` y la ruta lo importa, nunca al revés.
9. **La lógica verificable de la pantalla vive en `.ts` puro.** En este repositorio **no están instalados** `@testing-library/react` ni `jsdom`: no se puede montar un componente en una prueba. Los `.tsx` quedan tontos.

### 3.1 Paridad en los 3 motores de ejecución (Codex CLI, Claude Code CLI, GitHub Copilot Pro)

| Ítem | Codex CLI | Claude Code CLI | GitHub Copilot Pro | Fallback |
|---|---|---|---|---|
| **A** — retiro de la superficie de clasificación | Idéntico | Idéntico | Idéntico | **No aplica bifurcación.** El control depende del *tracker* (GitLab), no del motor que ejecuta agentes. Ningún símbolo del Bloque A nombra un motor |
| **B** — catálogo al día | **Sin cambio**: su bloque en el archivo es `{"id": "", "label": "Automático (decide Codex CLI)"}` y este plan no lo toca | **Es el ítem**: se agrega `claude-opus-5` y se lo hace ejecutable | **Sin cambio**: su lista se puebla viva desde `copilot_bridge.list_copilot_models()` (`services/model_catalog.py:174-194`) | Cada motor conserva exactamente su fuente actual |
| **B** — lector de la cuenta local | **No aplica**: la clave `cuenta` **no se agrega** a su bloque, que queda **byte-idéntico** | Aplica: `cuenta` vive **solo** acá | **No aplica**: ídem Codex | El lector escribe **únicamente** en el bloque `claude_code_cli`. Un gate lo verifica (§6.F11) |
| **B** — aviso "de dónde salió la lista" | Se muestra si su bloque cayó al respaldo (dato de nivel superior, común a los tres) | Ídem, y además el estado de la cuenta y los descartes | Ídem, y además el error de introspección que ya viaja en `error` | El aviso es **por motor**, derivado del dato, sin bifurcación de código |
| **B** — refresco automático (F9.1) | Idéntico | Idéntico | Idéntico | Un solo camino: se invalida la promesa del catálogo, que sirve a los tres |

**Gate binario de esta sección (F11):** el bloque `codex_cli` y el bloque `github_copilot` de la respuesta de `/api/agents/model-catalog` deben ser **exactamente iguales** antes y después del plan, comparados clave por clave, con el lector de cuenta encendido y apagado — **y el bloque `claude_code_cli` tiene que ser distinto entre encendido y apagado** (contra-pata, para que la primera mitad no pase por accidente cuando el lector no está cableado).

---

## 4. Glosario, reglas de lectura y rojos de fábrica

### 4.1 Glosario (términos de este repositorio que un modelo menor no conoce)

| Término | Qué es acá |
|---|---|
| **Clasificación local** | Lo que construyó el plan 277: el operador marca, **dentro de Stacky**, de qué tipo es un ticket de GitLab y de cuál cuelga, sin escribir en el GitLab de la empresa. Vive en `local_work_item_type` y `local_parent_iid`. **La palabra "Clasificación" NO aparece en `frontend/src`** (verificado: `grep -ri "clasificaci" src` no devuelve ningún rótulo con esa mayúscula suelta). Los **rótulos visibles reales** son: `"Tipo (solo en Stacky)"` (`JerarquiaLocalControl.tsx:81`), `"Cuelga del ticket número"` (`:103`), `"Guardar clasificación"` (`:124`), `"Sin clasificar"` (`:92`) y `"Ver qué se va a cambiar"` (`PublicarEtiquetasGitLab.tsx:116`). **El smoke de F12 busca ESOS textos, no la palabra "Clasificación"** |
| **Motor de datos** (de la clasificación) | Las columnas del modelo, la ruta `PATCH` del servidor, la lógica pura de `lib/jerarquiaLocal.ts` y los contadores de la sincronización. **Se conserva entero** |
| **Superficie de interfaz** (de la clasificación) | Los tres puntos donde ese motor se *monta* y el operador lo ve. **Es lo único que se retira** |
| **Catálogo de modelos** | `backend/config/model_catalog.json`, leído por `services/model_catalog.py` con caché de 300 s invalidada por fecha de modificación del archivo |
| **Catálogo efectivo** | Lo que devuelve `load_model_catalog()` **después** de fusionar sonda y cuenta. Es lo que ve la pantalla, y es contra esto que se prueba el invariante de ejecutabilidad |
| **Respaldo de emergencia** | La copia embebida del catálogo que se usa si el archivo no se puede leer. Hay **dos**, una por lado de la red: `services/model_catalog.py:26` y `frontend/src/services/modelCatalogFallback.ts:11`. El plan 212 dejó una prueba de paridad entre las dos |
| **Clamp** | `services/llm_router.py:38 clamp_model`. Es la **única** función que decide qué modelo está capado. Mapea cualquier modelo Claude de tier prohibido al tope (`CLAUDE_CAP_MODEL = "claude-sonnet-5"`, `:32`) |
| **Elección explícita** | Cuando el operador elige un modelo para **una** corrida. Es el único caso que puede saltarse el clamp, y solo si el id está en la lista de autorizados (`services/claude_code_cli_runner.py:534 allow_opus_for_run`) **y el agente no es el de DevOps** (`:545-548`) |
| **Filtro de admisión** (nuevo en la v2) | Las tres condiciones que un id propuesto por el lector de cuenta tiene que cumplir para entrar al catálogo. §6.F7 regla 5 |
| **Sonda** (del programa instalado) | `services/model_probe.py`. Pregunta al programa de línea de comandos qué modelos tiene. **Nunca invoca un modelo**: solo subcomandos de listado |
| **Ratchet** | Prueba que congela un número y solo lo deja bajar |
| **Rojo de fábrica** | Prueba que ya falla antes de que este plan toque nada. Se declara para que nadie lo confunda con una regresión propia |

### 4.2 Cómo se leen los `archivo:línea` de este documento

Hay una **sesión paralela viva** en este árbol (tomó los planes 286 y 287; sus archivos de prueba ya están registrados en el arnés en `run_harness_tests.sh:1018-1020` y `run_harness_tests.ps1:912-914`). Los números pueden correrse. **Regla: cuando este documento da un número de línea para un punto de inserción, da también el símbolo. Si el número no coincide, manda el símbolo.**

> **Esta regla NO es una excusa para anclajes flojos, y la v2 lo demuestra:** los 9 anclajes que la crítica encontró corridos están **corregidos con el valor real medido**, no tapados con la regla. La regla existe solo para el drift que ocurra **después** del 2026-08-02, y F0.0 la ejercita antes de tocar nada.

### 4.3 El defecto del Bloque B, en cuatro pasos verificados

Esto es lo que hay que entender antes de escribir una línea del Bloque B. Los cuatro pasos están anclados:

1. **El catálogo no tiene `claude-opus-5`.** `backend/config/model_catalog.json` lista exactamente 4 ids: `claude-sonnet-5`, `claude-opus-4-8`, `claude-haiku-4-5`, `claude-sonnet-4-6`. Fecha del archivo: `"updated_at": "2026-07-17"`.
2. **La sonda que debía arreglarlo está muerta.** `services/model_probe.py:29-33` prueba `models list --json`, `models --json` y `--list-models`. Los tres **no existen** en el programa instalado (§4.4). Devuelve `no_candidate_worked` siempre.
3. **Aunque el modelo estuviera en la lista, el camino de ejecución lo degradaría.** `services/llm_router.py:33` `_FORBIDDEN_CLAUDE_TIER = ("opus", "fable")` y `:35` `_OPUS_ALLOWLIST = {"claude-opus-4-8"}` — **un solo elemento**. `clamp_model` (`:38-57`) manda cualquier `claude-*opus*` o `claude-*fable*` a `CLAUDE_CAP_MODEL = "claude-sonnet-5"` salvo que `allow_opus=True` **y** el id esté en esa lista. Los cuatro puntos de entrada de elección explícita llaman con `allow_opus=True` (`api/agents.py:808`, `:1055`, `:1254`, `api/plans_board.py:176`), y el runner vuelve a decidir con `allow_opus_for_run` (`services/claude_code_cli_runner.py:942,955`).
   **Consecuencia medible:** si hoy se agregara `claude-opus-5` al catálogo y el operador lo eligiera, el runner ejecutaría `claude-sonnet-5`. La pantalla mostraría Opus 5. **Sería un plan que empeora el problema: cambia "no aparece" por "aparece y miente".**
4. **La pantalla no avisa cuando muestra la lista de respaldo, y no se actualiza nunca.** `frontend/src/hooks/useModelCatalog.ts` devuelve `{catalog, loading}` (`:21-24`, `:49`): **descarta `fallback_used`**, que sí viaja en la respuesta (`frontend/src/api/endpoints.ts:1164`). Los **5** consumidores (`components/EpicFromBriefModal.tsx:81,88`, `pages/PlansBoardPage.tsx:348`, `pages/TicketBoard.tsx:150`, `components/IncidentResolverModal.tsx:91`, `components/ModelDecisionChip.tsx:21`) no tienen forma de saberlo. El único lugar del repositorio que sí lo mira es `components/ModelPicker.tsx:78`, pero es **otra ruta** (`/api/agents/models`, que sirve `llm_router.CLAUDE_MODELS` — **3** modelos, sin ningún opus: `api/agents.py:1445`). Y encima la promesa del catálogo es **de módulo y no se invalida nunca** (`useModelCatalog.ts:12-19`), así que una pestaña abierta se queda con la primera lista para siempre.

### 4.4 Evidencia externa MEDIDA el 2026-08-02 (no inferida)

Todo esto se obtuvo ejecutando comandos en la máquina del operador. **Está pegado literal porque es el corazón del Bloque B.** Los tres bloques fueron **re-medidos en la crítica de la v2** y coinciden.

**(a) Versión y subcomandos del programa de línea de comandos de Claude Code**

```
$ claude --version
2.1.220 (Claude Code)

$ claude --help   (sección Commands, literal)
agents · auth · auto-mode · doctor · gateway · install · mcp · plugin|plugins ·
project · setup-token · ultrareview · update|upgrade
```

**No existe un subcomando `models`.** Ejecutando los tres candidatos de `services/model_probe.py:29-33`:

```
=== claude models list --json ===   error: unknown option '--json'
=== claude models --json ===        error: unknown option '--json'
=== claude --list-models ===        error: unknown option '--list-models'
```

> **Cómo medir el código de salida sin equivocarse (corrige C19):** `claude models --json > salida.txt 2>&1; echo $?`. **No** encadenar con `| head`, porque entonces `$?` es el de `head` y da 0 aunque el programa haya fallado. Lo que importa acá no es el número sino el mensaje: **`unknown option` en los tres**.

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
"additionalModelCostsCache": {},
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
  "claude-opus-4-8": {…}, "claude-opus-5": {…},
  "glm-4.7": {…}, "glm-5.2": {…},
  "qwen2.5:3b": {…}, "qwen2.5-coder:7b": {…}, "qwen3-coder:30b-a3b-q4_K_M": {…}
},
"dailyModelTokens": [ …, {"date": "2026-07-28",
                          "tokensByModel": {"claude-sonnet-5": 455132,
                                            "claude-opus-5": 4321237}} ]
```

**Conclusión (b):** hay una fuente **local, real, sin red, sin consumo y sin credenciales** que dice qué modelos esta cuenta **usó de verdad** (`modelUsage`, `dailyModelTokens`), cuáles el propio programa **le ofrece de más** (`additionalModelOptionsCache`), y qué **suscripción** tiene (`oauthAccount.organizationType = "claude_max"`, `organizationRateLimitTier = "default_claude_max_20x"`).

**(b-bis) ⚠ EL DATO QUE HUNDIÓ LA v1 — leer esto ANTES de escribir F7.**

`modelUsage` **NO contiene solo modelos de Claude.** En esta cuenta, hoy, tiene **once** claves, y **cinco no son de Anthropic**: `glm-4.7`, `glm-5.2`, `qwen2.5:3b`, `qwen2.5-coder:7b`, `qwen3-coder:30b-a3b-q4_K_M`. Son modelos de otros proveedores y modelos locales.

Si el lector volcara `modelUsage` + `additionalModelOptionsCache` al bloque `claude_code_cli` **sin filtrar** — que es exactamente lo que hacía la v1 — el selector de Claude Code mostraría hoy, en la máquina del operador, **estos seis ids nuevos**:

```
claude-fable-5[1m]   glm-4.7   glm-5.2   qwen2.5:3b   qwen2.5-coder:7b   qwen3-coder:30b-a3b-q4_K_M
```

Cinco de ellos **Claude Code CLI no los puede ejecutar**, y el sexto (`claude-fable-5[1m]`) el clamp lo degrada en silencio. **Sería lo contrario de lo que el operador pidió** ("no mostrar modelos sin acceso"). Por eso F7 tiene un **filtro de admisión obligatorio** (§6.F7 regla 5) y una prueba que lo congela con estos seis ids literales.

**(c) Lo que NO se puede hacer, dicho sin adornos**

| Camino que el operador podría esperar | Veredicto | Evidencia |
|---|---|---|
| Preguntarle al programa instalado por la lista de modelos | **NO EJECUTABLE** | §4.4(a): no hay subcomando de listado en 2.1.220 |
| Llamar a la ruta de listado de modelos del proveedor | **NO EJECUTABLE Y ADEMÁS NO RESPONDERÍA LA PREGUNTA** | Esa ruta refleja lo que ve una **clave de interfaz de programación**, no lo que da una **suscripción**. Acá el motor corre con la sesión del programa, no con clave: `services/claude_code_cli_runner.py` invoca el binario, no una ruta HTTP. Y `oauthAccount.billingType` es `"stripe_subscription"`. Aunque hubiera credencial, la lista que devolvería **no sería la de la suscripción del operador** |
| Verificar un modelo invocándolo | **PROHIBIDO** | Gastaría consumo en reposo. Violaría el principio 5 y la regla (A) de las flags |
| Leer lo que el programa ya guardó sobre esta cuenta | **EJECUTABLE, VERIFICADO — pero SOLO CON FILTRO** | §4.4(b) y §4.4(b-bis) |
| Poner el catálogo estático al día | **EJECUTABLE, TRIVIAL** | §4.3(1) |

**Este plan implementa los dos últimos y descarta los tres primeros por escrito.**

> **Lo que este plan NO promete, dicho con todas las letras.** El operador pidió "los modelos realmente disponibles según la suscripción". **Esa consulta no existe** para este modo de operación, y este plan **no la simula**. Lo que entrega es una señal **más débil pero honesta y verificable**: los modelos que **esta instalación de Claude Code registró como usados o como ofrecidos para esta cuenta**, filtrados a los que Stacky **puede ejecutar de verdad**, con el resto **explicado** en vez de escondido. Si mañana el programa expone un listado real, la sonda del 212 ya está en su lugar para tomarlo, y el filtro de admisión de F7 se aplica igual.

### 4.5 Rojos de fábrica declarados (medidos ANTES de tocar nada)

| Archivo | Estado hoy | Regla |
|---|---|---|
| `backend/tests/test_harness_flags_help.py` | rojo de fábrica conocido (4 fallidas) | **No es de este plan.** Se mide el **delta**: mismo número y mismos nombres al cerrar. Si aparece una violación nueva que nombra la key de este plan, el texto de ayuda está mal y se corrige el texto |
| `backend/tests/test_error_fingerprints_catalog.py` | rojo de fábrica conocido | Ídem. **La huella que agrega F12.c NO puede sumar una fallida nueva**: si la suma, la entrada está mal formada |
| `frontend/src/services/__tests__/plan273GateState.test.ts` | 2 aserciones rojas (espera 7 gates, hay 8) | Ídem. Este plan **no agrega ningún gate de pantalla** |
| `backend/tests/test_harness_ratchet_meta.py` + `tests/test_plan259_ratchet_script_parity.py` | **VERDES — 16 passed, RE-MEDIDO en la crítica el 2026-08-02** | Estos **no pueden** quedar rojos. Es el criterio duro de F10 |
| `backend/tests/test_llm_router_opus_flag.py` | **VERDE** — y su `test_fable_still_blocked_with_allow_opus` (`:41-43`) **es la razón por la que fable sale del alcance** | No se toca, no se modifica, tiene que seguir verde |
| `backend/tests/test_plan212_opus_end_to_end.py` | **VERDE** — `test_decide_allow_opus_true_still_blocks_fable` (`:43-44`) y `test_is_opus_allowlisted` (`:52-55`) congelan la política de fable | Ídem. Está registrado en los dos scripts del arnés (`sh:795`, `ps1:692`) |

**Regla de aceptación del plan:** ninguna prueba que hoy esté **verde** puede quedar roja. Los rojos de arriba deben quedar **exactamente igual**. Un "todo pasa" reportado no es evidencia: se pega la salida.

---

## 5. Flags

### 5.1 La única flag nueva

| Key | Tipo | Default | Categoría | Qué protege | Justificación del default |
|---|---|---|---|---|---|
| `STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED` | `bool` | **ON** (`default=True`) | `runtimes_cli` | El lector de la configuración local de la cuenta de Claude Code (§6.F7) y su aporte al catálogo | **Solo lectura, sin red, sin consumo, sin escritura.** Lee dos archivos de texto del disco del operador y no toca nada. **No cae en (A)**: no enciende bucle, demonio, barrido, sondeo, prefetch ni llamada a modelo — se evalúa dentro del refresco de caché que **ya existe** (300 s) y solo cuando alguien pide el catálogo. **No cae en (B)**: no escribe en ningún sistema, no borra nada, no decide nada por el operador. Lo de solo lectura va **siempre ON** |

**Ninguna otra flag nueva.** El resto del plan usa las que ya existen: `STACKY_MODEL_CATALOG_ENABLED` (`config.py:1026`, ON), `STACKY_MODEL_PROBE_ENABLED` (`config.py:1517`, ON), `STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED` y `STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED` (las del 277, **intocadas**).

> **INDEPENDENCIA DE LA FLAG (cierra C4).** La flag nueva **no depende de ninguna otra**. En la v1 el lector se cableaba dentro de `_merge_probe`, que retorna en `services/model_catalog.py:123-124` si `STACKY_MODEL_PROBE_ENABLED` está apagada: apagar la sonda mataba el lector **sin decirlo**. En la v2 el lector vive en su **propia función** `_merge_cuenta`, llamada desde `load_model_catalog` **después** de `_merge_probe`. **Caso de prueba obligatorio:** `cuenta_viva_con_la_sonda_apagada` (F7).

### 5.2 Las patas de la flag nueva — enumeradas con archivo y símbolo

> **Esta tabla es el contrato con el implementador.** Si falta una pata, la flag queda **muerta** o una suite ajena se pone roja. Los números fueron **re-verificados en la crítica el 2026-08-02**.

| # | Archivo | Estructura | Ancla (símbolo primero, número después) | Qué se agrega |
|---|---|---|---|---|
| 1 | `Stacky Agents/backend/config.py` | atributo de la clase de configuración | buscar `STACKY_MODEL_PROBE_ENABLED: bool = os.getenv(` (hoy `:1517`) y agregar **debajo** | `STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED: bool = os.getenv("STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED", "true").strip().lower() in ("1","true","yes")` — **usar exactamente el mismo patrón que la línea de arriba en ese archivo** |
| 2 | `Stacky Agents/backend/services/harness_flags.py` | `FLAG_REGISTRY` | abre en `FLAG_REGISTRY: tuple[FlagSpec, ...] = (` (**hoy `:614`** — la v1 decía 610); cierra justo antes de `_REGISTRY_INDEX: dict[str, FlagSpec] =` (**hoy `:7231`** — la v1 decía 7186) | 1 `FlagSpec` al final, antes del `)`. Texto literal en §5.4 |
| 3 | `Stacky Agents/backend/services/harness_flags.py` | `_CATEGORY_KEYS` (`:120`), tupla `"runtimes_cli"` | abre en `"runtimes_cli": (` (hoy `:121`) y cierra antes de `"contexto_memoria": (` (hoy `:133`). `STACKY_MODEL_CATALOG_ENABLED` ya está ahí (`:131`) | la key, al final de esa tupla |
| 4 | **`Stacky Agents/backend/tests/test_harness_flags.py`** | `_CURATED_DEFAULTS_ON` (es un **`set`** y vive en el **archivo de prueba**, no en el servicio) | abre en `_CURATED_DEFAULTS_ON = {` (hoy `:467`) | la key, al final del set. **Obligatorio**: `default_is_known` (`:465`) es `spec.default is not None`, así que declarar `default=True` **exige** la pertenencia al set |
| 5 | **`Stacky Agents/backend/tests/test_harness_flags_requires.py`** | `_REQUIRES_MAP_FROZEN` (dict, hoy `:120`) | **NO SE TOCA** | La flag **no declara `requires=`**. Verificado: `test_requires_map_is_frozen` (`:397`) construye `actual = {s.key: s.requires for s in FLAG_REGISTRY if s.requires}` (`:400`) — el filtro `if s.requires` **excluye** a las flags sin `requires`, así que **no hay entrada que agregar**. Agregar una entrada acá **rompe** la prueba con `Faltantes: [...]` |
| 6 | `Stacky Agents/backend/services/harness_flags_help.py` | `PLAIN_HELP` (dict) | buscar `PLAIN_HELP: dict` y `def plain_help_for`; agregar antes del `}` final | 1 entrada. Texto literal y validado en §5.5 |
| 7 | `Stacky Agents/backend/tests/test_harness_flags_bounds.py` | `_FROZEN_BOUNDS` | **NO SE TOCA** | Solo aplica a flags **numéricas**. Esta es `bool`. Verificar corriendo la prueba (F0.1 punto 11) |
| 8 | `Stacky Agents/deployment/harness_defaults.env` | snapshot de defaults | **NO SE TOCA** | Verificado: `tests/test_harness_flags_bounds.py:261 test_harness_defaults_env_within_bounds` **salta** si el archivo no está en `backend/`, y `tests/test_plan120_flags.py:94` declara por escrito que ese archivo es un **snapshot PARCIAL**. No hay gate que exija la entrada |
| 9 | Panel de flags de la pantalla | — | **NO SE TOCA** | El panel se deriva de `FLAG_REGISTRY` en tiempo de ejecución. Con `env_only=False` aparece sola. Se confirma en el smoke visual de F12 |

**Regla dura de lectura de la flag (cierra C13).** `services/claude_account_models.py` lee la flag **así y solo así**:

```python
from config import config as _cfg
...
if not getattr(_cfg, "STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED", True):
    return LecturaCuenta(disponible=False, motivo="flag_apagada", ...)
```

**PROHIBIDO `os.getenv("STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED", …)` dentro de `backend/services/` o `backend/api/`**: `tests/test_flags_env_read_meta.py` escanea esos dos directorios con el patrón `os.getenv\(\s*['"](STACKY_[A-Z0-9_]+)['"]\s*,` y pone rojo cualquier flag registrada leída así, salvo las de su allowlist congelada.

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
            "tipo de suscripcion) y SUMA al catalogo solo los que Stacky puede "
            "ejecutar de verdad; lo descartado se informa con su motivo. Solo "
            "lectura: sin red, sin credenciales y sin gasto. Nunca resta modelos."
        ),
        group="global",
        env_only=False,
        default=True,
        # SIN requires= a proposito: ver Plan 288 seccion 5.2 pata 5.
    ),
```

> **Regla dura verificada:** en `harness_flags.py` una flag que nace OFF se declara **omitiendo** el kwarg `default`, porque `default_is_known(spec)` es `spec.default is not None` y `False is not None`. Esta flag nace ON, así que declara `default=True` **y** entra a `_CURATED_DEFAULTS_ON`. **Las dos cosas, siempre juntas.**

### 5.5 Texto literal de `PLAIN_HELP` (pata 6)

Las reglas se leyeron del archivo de prueba real (`backend/tests/test_harness_flags_help.py`, **re-verificado en la crítica**): `what` entre 10 y 200 caracteres; `on_effect` y `off_effect` ≤ 240 y **empiezan con `"Si "`** (con espacio, **sin tilde**); `example` ≤ 300; los 4 no vacíos; **sin jerga** de `JARGON_DENYLIST` = `MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime` (sin distinguir mayúsculas y **con el plural opcional**: la expresión es `\b{term}s?\b`); sin claves `SCREAMING_SNAKE` (`\b[A-Z]+_[A-Z0-9_]+\b`); sin referencias a fase (`\bF\d`).

> El texto de abajo se redactó contra esas reglas. **Copiarlo literal.** Las palabras prohibidas más fáciles de meter sin querer en este dominio son *"runtime"*, *"token"* y *"endpoint"*: ninguna aparece.

```python
    "STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED": PlainHelp(
        what="Lee de tu equipo la lista de modelos que tu cuenta de Claude Code tiene habilitados, para ofrecerte solo esos.",
        on_effect="Si la activas: el selector suma los modelos que tu cuenta ya viene usando, siempre que Stacky pueda ejecutarlos de verdad, y te dice cuales dejo afuera y por que.",
        off_effect="Si la apagas: el selector muestra solo la lista fija que viene con Stacky, sin mirar tu cuenta.",
        example="Tu cuenta usa Opus 5 desde hace semanas; con esto aparece en la lista en vez de quedar invisible.",
    ),
```

---

## 6. Fases

> **Comandos canónicos.**
> **Servidor:** desde `Stacky Agents/backend`, `.venv/Scripts/python.exe -m pytest tests/<UN_ARCHIVO>.py -q --no-header -p no:cacheprovider`. **Usar `.venv` (Python 3.13.5), NO `venv` (3.11.9)** — `venv` no tiene las dependencias. **Un archivo por vez**: correr `pytest tests` entero da miles de errores de contaminación y **no es un veredicto**.
> **Antes de cualquier `pytest`, exportar `STACKY_TEST_MODE=1`** (en PowerShell: `$env:STACKY_TEST_MODE="1"`). Sin eso, un pytest suelto puede escribir en la base viva.
> **Consecuencia que la v1 ignoró:** con `STACKY_TEST_MODE=1`, `_merge_probe` **retorna temprano** (`services/model_catalog.py:128-129`). Por eso el lector de cuenta de este plan **no vive dentro de `_merge_probe`** (§6.F7) y por eso **ninguna** prueba del plan depende de esa guarda.
> **`pytest -k` sin coincidencias sale con código 0**: nunca usar `-k` como única prueba de que algo pasó; siempre mirar el conteo (`N passed`).
> **Pantalla:** desde `Stacky Agents/frontend`, `npx vitest run src/<ruta>/<archivo>.test.ts` (**por archivo, nunca la suite entera**: hay contaminación por orden) y `npx tsc --noEmit`. **`npx vitest run <ruta inexistente>` sale 1 pero pipeado se pierde el código de salida**: correrlo sin tubería.
> **`tsc` NO cubre todo (cierra C9).** `frontend/tsconfig.json` tiene `"noUnusedLocals": false` (nunca reporta variables sin uso), **no** declara `allowJs` (así que **`TicketGraphView.jsx` no se typechequea**) y `exclude` saca `src/**/__tests__/**` y `src/**/*.test.ts` (así que **los archivos de prueba tampoco**). Para verificar un cambio en un `.jsx` hay que **parsearlo de verdad**: `npx vite build`.

---

### F0.0 — Barrido de anclajes, ANTES de tocar nada

**Objetivo:** revalidar en 15 segundos los anclajes críticos, porque hay una sesión paralela viva en este árbol.
**Archivos:** ninguno (solo lectura). **Flag:** ninguna. **Trabajo del operador: ninguno.**

Correr desde `Stacky Agents`:

```powershell
Select-String -Path "frontend\src\pages\TicketBoard.tsx"                  -Pattern 'import JerarquiaLocalControl|import PublicarEtiquetasGitLab|<JerarquiaLocalControl|<PublicarEtiquetasGitLab|<TicketLocalInsightButton'
Select-String -Path "frontend\src\components\TicketGraphView.jsx"         -Pattern 'import JerarquiaLocalControl|<JerarquiaLocalControl|<FinishWorkButton'
Select-String -Path "frontend\src\lib\jerarquiaLocal.ts"                  -Pattern 'export function debeMostrarControlJerarquia|export function validarPadre|export function esPublicable'
Select-String -Path "backend\services\gitlab_sync.py"                     -Pattern '_CONTADORES_LOCAL|usados_local_tipo'
Select-String -Path "backend\config\model_catalog.json"                   -Pattern 'claude-opus-4-8|claude-sonnet-5'
Select-String -Path "backend\services\model_catalog.py"                   -Pattern '_EMERGENCY_FALLBACK|def load_model_catalog|def _merge_probe|STACKY_TEST_MODE'
Select-String -Path "backend\services\model_probe.py"                     -Pattern '_CANDIDATES|def probe_claude_models'
Select-String -Path "backend\services\llm_router.py"                      -Pattern '_OPUS_ALLOWLIST|def clamp_model|def is_opus_allowlisted|CLAUDE_CAP_MODEL'
Select-String -Path "backend\services\claude_code_cli_runner.py"          -Pattern 'def allow_opus_for_run'
Select-String -Path "backend\api\agents.py"                               -Pattern 'def model_catalog_route|capabilities_for'
Select-String -Path "backend\harness\pricing.py"                          -Pattern 'DEFAULT_PRICES'
Select-String -Path "backend\services\harness_flags.py"                   -Pattern 'FLAG_REGISTRY: tuple|"runtimes_cli": \('
Select-String -Path "backend\tests\test_harness_flags.py"                 -Pattern '_CURATED_DEFAULTS_ON = \{'
Select-String -Path "backend\tests\test_llm_router_opus_flag.py"          -Pattern 'def test_fable_still_blocked_with_allow_opus'
Select-String -Path "backend\tests\test_plan212_opus_end_to_end.py"       -Pattern 'def test_decide_allow_opus_true_still_blocks_fable|def test_is_opus_allowlisted'
Select-String -Path "backend\scripts\run_harness_tests.sh"                -Pattern 'HARNESS_TEST_FILES=\('
Select-String -Path "backend\scripts\run_harness_tests.ps1"               -Pattern '\$HarnessTestFiles = @\('
Select-String -Path "frontend\src\hooks\useModelCatalog.ts"               -Pattern 'export function useModelCatalog|UseModelCatalogResult|catalogPromise'
Select-String -Path "frontend\src\api\endpoints.ts"                       -Pattern 'export interface ModelCatalogResponse|export interface RuntimeModelCatalog'
```

**Criterio binario:** los 19 patrones imprimen **al menos una línea cada uno**. Si alguno no imprime nada, **parar** y avisar: el símbolo se renombró y el plan necesita una pasada de actualización.

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
| 5b | `npx vite build` (`frontend`) | **termina sin error** — anotar el tiempo, es el único gate que parsea `TicketGraphView.jsx` |
| 6 | `.venv/Scripts/python.exe -m pytest tests/test_plan277_clasificacion_local.py -q --no-header -p no:cacheprovider` (`backend`) | anotar el número |
| 7 | `.venv/Scripts/python.exe -m pytest tests/test_plan159_model_catalog_endpoint.py tests/test_plan159_model_catalog_loader.py tests/test_plan159_model_catalog_flag.py -q --no-header -p no:cacheprovider` (`backend`) | anotar el número |
| 8 | `.venv/Scripts/python.exe -m pytest tests/test_plan212_model_probe.py -q --no-header -p no:cacheprovider` (`backend`) | anotar el número |
| 9 | `.venv/Scripts/python.exe -m pytest tests/test_adaptive_selector.py tests/test_adaptive_selector_wiring.py tests/test_difficulty_routing.py tests/test_acceptance_contract.py -q --no-header -p no:cacheprovider` (`backend`) | anotar el número — **son las suites que congelan el clamp** |
| 10 | `.venv/Scripts/python.exe -m pytest tests/test_harness_ratchet_meta.py tests/test_plan259_ratchet_script_parity.py -q --no-header -p no:cacheprovider` (`backend`) | **16 passed** (re-medido 2026-08-02) |
| 11 | `.venv/Scripts/python.exe -m pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py tests/test_flags_env_read_meta.py tests/test_harness_flags_bounds.py -q --no-header -p no:cacheprovider` (`backend`) | anotar el número |
| 12 | `.venv/Scripts/python.exe -m pytest tests/test_harness_flags_help.py -q --no-header -p no:cacheprovider` (`backend`) | **rojo de fábrica** — anotar el número exacto de fallidas **y sus nombres** |
| **13** | `.venv/Scripts/python.exe -m pytest tests/test_llm_router_opus_flag.py -q --no-header -p no:cacheprovider` (`backend`) | **verde** — **NUEVO en la v2 (C11)**. Es el gate que prueba que fable siguió fuera |
| **14** | `.venv/Scripts/python.exe -m pytest tests/test_plan212_opus_end_to_end.py tests/test_llm_router_cap.py -q --no-header -p no:cacheprovider` (`backend`) | **verde** — **NUEVO en la v2 (C11)** |
| **15** | `.venv/Scripts/python.exe -m pytest tests/test_harness_pricing.py tests/test_model_policy.py -q --no-header -p no:cacheprovider` (`backend`) | anotar el número — **NUEVO en la v2** |
| **16** | `.venv/Scripts/python.exe -m pytest tests/test_error_fingerprints_catalog.py -q --no-header -p no:cacheprovider` (`backend`) | **rojo de fábrica** — anotar fallidas **y nombres**, porque F12.c toca ese catálogo |

**Criterio binario:** los 17 números quedan escritos. Al cerrar (F12) se vuelven a correr los 17 y **cada uno da igual o mejor**; el 12 y el 16 tienen que dar **exactamente las mismas fallidas, con los mismos nombres**.

---

## BLOQUE A — la vista del ticket adelgaza

### F1 — Centinela de DOS patas (ausencia + presencia), hoy ROJO

**Objetivo:** congelar en una sola prueba que la superficie de clasificación desapareció **y** que todo lo demás de la tarjeta sigue ahí.
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
 * Plan 288 F1 — la superficie de clasificacion local no se ve en la vista de tickets.
 *
 * DOS PATAS EN EL MISMO TEST, a proposito: un assert de AUSENCIA pasa solo si el
 * archivo no existe o si la ruta esta mal. La pata de PRESENCIA lo prueba vivo.
 */
const leer = (rel: string) => {
  const p = join(process.cwd(), rel);
  expect(existsSync(p), `no existe ${rel} — la ruta del test está mal, no es que el símbolo se fue`).toBe(true);
  return readFileSync(p, "utf-8");
};

const TABLERO = "src/pages/TicketBoard.tsx";
const GRAFO = "src/components/TicketGraphView.jsx";

describe("Plan 288 F1 — la vista del ticket no muestra la clasificación local", () => {
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
    expect(leer("src/types.ts")).toContain("local_parent_iid");
    // Los dos componentes SIGUEN EXISTIENDO: este plan los desmonta, no los borra.
    expect(existsSync(join(process.cwd(), "src/components/JerarquiaLocalControl.tsx"))).toBe(true);
    expect(existsSync(join(process.cwd(), "src/components/PublicarEtiquetasGitLab.tsx"))).toBe(true);
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

> **Qué pasa con `qc`, `refetchHierarchy` y `trackerType` — verificado, no supuesto (corrige C9).**
> `qc` (`:305`) queda usado en `:393-395`, `:426-429`, `:464-466`, `:589-590`, `:615-616` — **sigue vivo, no tocarlo**.
> `refetchHierarchy` (`:1001`) queda usado en `:1323` (`LoadErrorState onRetry`) — **sigue vivo, no tocarlo**.
> **NO confiar en `tsc` para detectar que se borró de más:** `frontend/tsconfig.json` declara `"noUnusedLocals": false`, así que **una variable sin uso NUNCA produce un error de `tsc`**. La v1 decía lo contrario y era falso. **La verificación real es la lista de comandos del criterio binario, en particular `npx vite build`.**

**(2) `Stacky Agents/frontend/src/components/TicketGraphView.jsx`** — dos ediciones:

| Qué | Anclaje por símbolo (hoy) | Acción |
|---|---|---|
| Comentario + import | `// Plan 277 F4 — clasificación local de jerarquía. El componente decide solo si se` / `// muestra (…)` / `import JerarquiaLocalControl from "./JerarquiaLocalControl";` (`:27-29`) | **borrar las 3 líneas** |
| Montaje | el bloque que abre en `{/* Plan 277 F4 — Tipo y Padre locales. Se renderiza solo en proyectos …` y termina en el `</div>` del envoltorio con `onClick={(e) => e.stopPropagation()}` (`:481-493`) | **borrar el bloque entero, comentario incluido** |

> **`TicketGraphView.jsx` es `.jsx` y NINGÚN `tsc` lo mira** (`tsconfig.json` no declara `allowJs`). Un `</div>` de más o de menos **pasaría el centinela de F1 y pasaría `tsc`**. El único gate que lo parsea de verdad es **`npx vite build`**, y por eso es obligatorio en el criterio de F2.

**Lo que NO se toca, y la razón (esto es tan importante como lo que se borra):**

| Archivo | Por qué se conserva |
|---|---|
| `frontend/src/components/JerarquiaLocalControl.tsx` | **No se borra.** El plan 287 lo nombra dos veces como acción reusable de su ficha (`docs/287_…md:145` y `:1041` — **anclajes corregidos en la v2**) y hay una **sesión paralela viva** que puede estar editándolo. Borrarlo genera un conflicto y rompe un plan ya escrito. Ver §7.1 y §8 |
| `frontend/src/components/PublicarEtiquetasGitLab.tsx` | Ídem. Además su lógica está cubierta por las pruebas del 277 |
| `frontend/src/lib/jerarquiaLocal.ts` | Es el motor; §2.2 |
| `frontend/src/types.ts:115` (comentario) y las claves `local_work_item_type` / `local_parent_iid` (`:119-120`) | Contrato del servidor. Sacarlas rompería la sincronización |
| Todo el servidor (`api/tickets.py`, `services/gitlab_sync.py`, `services/gitlab_hierarchy*.py`) y sus 2 flags del 277 | §2.2 |
| `frontend/src/__tests__/plan277JerarquiaLocal.test.ts` | Sus 8 casos importan **solo** funciones puras del motor. **Sigue verde sin tocarlo** |

**Criterio binario de F2 (los 6 comandos, desde `Stacky Agents/frontend`):**

```bash
npx vitest run src/__tests__/plan288SuperficieClasificacion.test.ts   # 3 passed
npx vitest run src/__tests__/plan277JerarquiaLocal.test.ts            # 8 passed, igual que F0.1
npx vitest run src/__tests__/formDebtRatchet.test.ts                  # verde
npx vitest run src/__tests__/uiDebtRatchet.test.ts                    # verde
npx tsc --noEmit                                                      # 0 errores
npx vite build                                                        # termina sin error  ← el único que parsea el .jsx
```

> **Los dos ratchets de deuda son "no aumenta", no "igual"** (`src/__tests__/formDebtRatchet.test.ts:76`: `if (count > allowed)`). Borrar marcado solo puede bajar el número, así que **no hay que regenerar ningún baseline**. Verificado con `grep -c`: ni `JerarquiaLocalControl.tsx` ni `PublicarEtiquetasGitLab.tsx` figuran en `formDebtBaseline.json`, `uiDebtBaseline.json` ni `motionDebtBaseline.json` (**0 coincidencias en los tres**).

---

### F3 — Frontera con el plan 287 (condicional; se ejecuta SOLO si el 287 ya está)

**Objetivo:** que el retiro no se deshaga solo cuando llegue la ficha a pantalla completa.
**Flag:** ninguna. **Trabajo del operador: ninguno.** **Motores:** neutro.

**Disparador — decisión mecánica, sin criterio (el resultado de F0.0):**

```powershell
Test-Path "frontend\src\components\ticket\TicketFullView.tsx"
```

- **`False` (el 287 todavía NO está implementado — es el caso esperado hoy, verificado el 2026-08-02):**
  **No se hace nada de código.** Se agrega **una sola línea de comentario** en la cabecera de `plan288SuperficieClasificacion.test.ts`:
  ```ts
  // Plan 288 F3 — el 287 no estaba implementado al correr este plan. Cuando exista
  // src/components/ticket/TicketFullView.tsx, AGREGAR acá el cuarto `it` del Plan 288 §6.F3.
  ```
  Y se anota en el registro de implementación: `F3 = rama NO-287`.

- **`True` (el 287 ya está implementado):**
  Agregar al archivo de F1 un cuarto `it` con la misma estructura de dos patas:

  ```ts
  it("la ficha a pantalla completa tampoco monta los controles de clasificación", () => {
    const src = leer("src/components/ticket/TicketFullView.tsx");
    expect(src).not.toContain("<JerarquiaLocalControl");
    expect(src).not.toContain("<PublicarEtiquetasGitLab");
    // PRESENCIA: la ficha sigue siendo la ficha
    expect(src).toContain("<FinishWorkButton");
  });
  ```

  Y retirar del `TicketFullView.tsx` los montajes correspondientes, con la misma disciplina de F2 (incluido `npx vite build`).
  Se anota en el registro: `F3 = rama 287-PRESENTE`.

**Criterio binario:** el archivo de F1 pasa completo, con 3 o 4 `it` según el caso, y **queda escrito en el registro de implementación cuál de las dos ramas se tomó**. Si el `Test-Path` da `True` y el registro dice `rama NO-287`, la fase está mal ejecutada.

> **Si el 287 se implementa DESPUÉS del 288** (el caso probable): el centinela de F1 **no cubre** un archivo que todavía no existe, así que el 288 **no puede** protegerse solo. Por eso la protección real es la instrucción escrita de §7.1 punto 3 **más** la línea de comentario que deja la rama NO-287 dentro del propio archivo de prueba, que es lo primero que va a leer quien lo toque.

---

## BLOQUE B — el selector de modelos deja de mentir

### F4 — Centinela del catálogo, hoy ROJO en dos aserciones distintas

**Objetivo:** dejar dos invariantes congelados **antes** de tocar nada: (a) el catálogo tiene el modelo que esta cuenta usa y Stacky puede ejecutar; (b) **todo lo que el catálogo EFECTIVO ofrece, el camino de ejecución lo respeta**.
**Valor:** (b) es lo que impide que este plan se convierta en "aparece y miente". **Flag:** ninguna. **Trabajo del operador: ninguno.** **Motores:** neutro.

**Archivo NUEVO:** `Stacky Agents/backend/tests/test_plan288_catalogo_vivo.py`

> **Cambio de fondo respecto de la v1 (cierra C8):** el invariante de ejecutabilidad se prueba sobre el **catálogo efectivo** — el que devuelve `load_model_catalog()` **después** de fusionar sonda y cuenta —, no sobre el archivo estático. Para poder hacerlo de forma determinista, el test construye el catálogo efectivo con una función auxiliar propia que llama a `_merge_cuenta` con `CLAUDE_CONFIG_DIR` apuntando a un `tmp_path` con contenido controlado. **Ninguna prueba lee el disco real del operador.**

**Casos (nombres exactos — el implementador no los cambia):**

| Test | Qué prueba | Estado hoy |
|---|---|---|
| `test_paridad_el_catalogo_ofrece_los_modelos_vigentes_de_claude_5` | El bloque `claude_code_cli` del archivo ofrece `claude-opus-5` **además** de los 4 que ya tenía | **ROJO** |
| `test_paridad_el_respaldo_de_emergencia_no_ofrece_menos_que_el_archivo` | El conjunto de ids de `_EMERGENCY_FALLBACK` ⊇ conjunto de ids del archivo | ROJO tras F5 si se olvida el respaldo |
| `test_ejecutable_todo_modelo_del_catalogo_efectivo_sobrevive_la_eleccion_explicita` | **El invariante central.** Para **cada** id `m` del bloque `claude_code_cli` del **catálogo efectivo** (archivo + sonda + cuenta): `allow_opus_for_run(m, "developer") is True` **o** `clamp_model(m) == m`. Si falla, el catálogo ofrece algo que el runner degrada en silencio | **ROJO** para `claude-opus-4-8` hoy; ROJO para `claude-opus-5` tras F5 hasta que F6 corra |
| `test_ejecutable_el_ruteo_automatico_sigue_capado_en_sonnet` | **Contra-prueba, misma corrida.** `clamp_model("claude-opus-5")` **sin** `allow_opus` sigue devolviendo `CLAUDE_CAP_MODEL`; y `clamp_model("claude-fable-5", allow_opus=True)` **también** sigue devolviendo `CLAUDE_CAP_MODEL`. F6 **no puede** aflojar el cap del ruteo automático **ni** tocar la política de fable | Verde hoy, tiene que **seguir** verde |
| `test_ausencia_y_presencia_ningun_modelo_desaparecio` | **Dos patas.** El conjunto de ids después ⊇ el conjunto de ids de la foto de F0.1 (**presencia**), y ningún id contiene el literal `claude-opus-4-7` ni `claude-3-` (**ausencia** de ids muertos) | Verde hoy, tiene que seguir verde |
| `test_precio_declarado_para_todo_modelo_ofrecido` | Para cada id ofrecido existe una entrada de precio que lo cubre **por prefijo** en `harness/pricing.py DEFAULT_PRICES` | **ROJO** tras F5 (`claude-opus-5` no tiene entrada; hoy hay `claude-opus-4` en `:25`, que **no** es prefijo de `claude-opus-5`) |
| `test_los_otros_dos_motores_no_cambian` | Los bloques `codex_cli` y `github_copilot` del archivo son idénticos, clave por clave, a una copia congelada dentro del propio test | Verde, tiene que seguir verde |
| `test_fable_sigue_fuera_del_catalogo_y_de_la_allowlist` | **Gate de alcance (nuevo en la v2).** `"claude-fable-5"` **no** está en el bloque `claude_code_cli` del archivo, **no** está en `_EMERGENCY_FALLBACK` y **no** está en `llm_router._OPUS_ALLOWLIST`. **Dos patas:** en el mismo test se afirma que `"claude-opus-5"` **sí** está en los tres lugares tras F5/F6 | ROJO en su pata de presencia hasta F6; su pata de ausencia tiene que estar verde **siempre** |

**Comando:**

```bash
# desde Stacky Agents/backend, con $env:STACKY_TEST_MODE="1"
.venv/Scripts/python.exe -m pytest tests/test_plan288_catalogo_vivo.py -q --no-header -p no:cacheprovider
```

**Criterio binario de F4:** la corrida imprime **`4 failed, 4 passed`** (o el número que dé, pero **anotado literal**), y las fallidas son exactamente `test_paridad_el_catalogo_ofrece_…`, `test_ejecutable_todo_modelo_del_catalogo_efectivo_…`, `test_precio_declarado_…` y `test_fable_sigue_fuera_…`. Si alguna de las otras 4 falla, **parar**: el test está mal escrito, no el código.

---

### F5 — El catálogo estático se pone al día (los TRES archivos, en un solo commit)

**Objetivo:** que `claude-opus-5` exista en la lista.
**Valor:** cierra el hecho concreto que reportó el operador. **Flag:** ninguna (es un dato). **Trabajo del operador: ninguno.** **Motores:** solo toca el bloque `claude_code_cli`.

> **Se agrega UN solo modelo, no dos (cierra C2 y C14).** La v1 agregaba también `claude-fable-5`. **Está prohibido en la v2**, y la razón está medida: hacerlo obliga a meter `claude-fable-5` en `_OPUS_ALLOWLIST` (o el invariante de F4 queda rojo para siempre), y eso **pone rojas tres pruebas verdes** que congelan una decisión de costo tomada por los planes 43 y 212: `tests/test_llm_router_opus_flag.py:41-43`, `tests/test_plan212_opus_end_to_end.py:43-44` y `:52-55`. **Cambiar la política de fable es una decisión del operador, no un efecto colateral de este plan.** §8.9 lo deja escrito con lo que haría falta.

**Archivos a editar — exactamente 3, y los 3 juntos o la prueba de paridad se pone roja:**

**(1) `Stacky Agents/backend/config/model_catalog.json`**

- `"updated_at"`: pasa de `"2026-07-17"` a `"2026-08-02"`.
- En `runtimes.claude_code_cli.models`, **agregar al principio de la lista** (para que quede arriba en el selector):
  ```json
  {"id": "claude-opus-5", "label": "Opus 5 (máxima calidad)", "recommended": false},
  ```
  **Los 4 existentes NO se tocan ni se reordenan entre sí.** `claude-sonnet-5` sigue siendo el `recommended: true` y el `default_model`: cambiar el default es una decisión de costo que este plan no toma.
- En `effort_support`, agregar:
  ```json
  "claude-opus-5": ["low", "medium", "high", "xhigh", "max"],
  ```
  **Justificación anclada:** `services/llm_router.py:60-81 clamp_effort_for_model` degrada por familia del nombre: `haiku` → `low/medium/high` (`:75-76`); `sonnet` → todo menos `xhigh` (`:77-79`); **cualquier otro (incluye opus) → todo soportado** (`:80-81`, comentario `# opus: todo soportado`). Esta fila **describe** lo que la función ya hace; no la cambia.
- En `effort_degrade`, agregar `"claude-opus-5": {}` (no degrada nada).

**(2) `Stacky Agents/backend/services/model_catalog.py`** — el mismo modelo en `_EMERGENCY_FALLBACK` (`:26-65`), con las mismas 3 estructuras (`models` `:34-39`, `effort_support` `:47-52`, `effort_degrade` `:53-58`). El propio comentario del archivo (`:28-30`) explica por qué: *"el fallback de emergencia NUNCA puede ofrecer menos que el archivo"*.

**(3) `Stacky Agents/frontend/src/services/modelCatalogFallback.ts`** — el mismo id en `EMERGENCY_MODEL_CATALOG` (`:11`), con la misma lista de effort. El comentario del archivo (`:10`) dice que hay una prueba de paridad que compara los dos conjuntos de ids.

**Nota sobre variantes de id (se aplica en F7, no acá):** la cuenta del operador registra también `claude-haiku-4-5-20251001` (el mismo Haiku 4.5 con fecha) y `claude-fable-5[1m]` (Fable 5 con ventana ampliada). **En F5 no se agrega ninguna de las dos**: la primera es el mismo modelo con sufijo de fecha, y la segunda es una variante de un modelo que este plan deja fuera de alcance (§8.9) y cuyo acceso la propia caché del programa declara en `false` (`s1mAccessCache.hasAccess: false`, §4.4(b)). F7 define la normalización y el filtro que las tratan.

**Criterio binario de F5:**

```bash
# backend
.venv/Scripts/python.exe -m pytest tests/test_plan288_catalogo_vivo.py -q --no-header -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/test_plan159_model_catalog_loader.py tests/test_plan159_model_catalog_endpoint.py -q --no-header -p no:cacheprovider
# frontend
npx vitest run src/__tests__/modelSelectorsConsistency.test.ts
npx tsc --noEmit
```

- `test_paridad_el_catalogo_ofrece_…` y `test_paridad_el_respaldo_…` pasan a **verde**.
- `test_ejecutable_…`, `test_precio_…` y la pata de presencia de `test_fable_sigue_fuera_…` **siguen rojos** — es lo correcto: F6 los cierra. **Anotarlo**, porque es la prueba de que el invariante funciona.
- Las suites del 159: **igual o mejor** que F0.1.

---

### F6 — Lo ofrecido se ejecuta: la lista de autorizados y los precios se ponen al día

**Objetivo:** que elegir Opus 5 ejecute Opus 5, sin aflojar el cap del ruteo automático y **sin tocar la política de fable**.
**Valor:** es lo que convierte el plan en verdadero. **Flag:** ninguna. **Trabajo del operador: ninguno.** **Motores:** solo Claude Code CLI (los otros dos no pasan por `clamp_model`; `harness/model_policy.py:23-30` lo aplica **solo** cuando `runtime == "claude_code_cli"`).

**Archivo 1 — `Stacky Agents/backend/services/llm_router.py`**, símbolo `_OPUS_ALLOWLIST` (hoy `:35`):

```python
# Plan 43 F1 — modelos de tier alto que el operador puede elegir EXPLICITAMENTE
# para una corrida puntual. Plan 288: se pone al dia contra el catalogo. La lista
# NO afecta el ruteo automatico: `clamp_model` sigue capando en CLAUDE_CAP_MODEL
# cuando `allow_opus=False`, que es el default de todos los caminos.
# INVARIANTE (tests/test_plan288_catalogo_vivo.py): todo id de tier prohibido que
# el catalogo EFECTIVO ofrezca tiene que estar aca, o el runner lo degrada en
# silencio. El filtro de admision de services/claude_account_models.py lo mantiene
# cierto tambien para los ids que llegan de la cuenta local.
# FABLE SIGUE FUERA A PROPOSITO (Plan 288 §8.9): lo congelan
# tests/test_llm_router_opus_flag.py::test_fable_still_blocked_with_allow_opus y
# tests/test_plan212_opus_end_to_end.py::{test_decide_allow_opus_true_still_blocks_fable,
# test_is_opus_allowlisted}. Sacarlo de ahi es una decision de costo del operador.
_OPUS_ALLOWLIST = {"claude-opus-4-8", "claude-opus-5"}
```

**Lo que NO cambia, y hay que dejarlo escrito en el mismo comentario:**
- `CLAUDE_CAP_MODEL` sigue siendo `"claude-sonnet-5"` (`:32`).
- `_FORBIDDEN_CLAUDE_TIER` sigue siendo `("opus", "fable")` (`:33`).
- La firma y el cuerpo de `clamp_model` (`:38-57`) **no se tocan**: el cambio es de **dato**, no de lógica.
- `CLAUDE_MODELS` (`:24`) **no se toca**: alimenta la ruta `/api/agents/models` de `api/agents.py:1445`, que es otra superficie (§8.4).

**Efectos verificados de este cambio — la tabla de la v1 estaba INCOMPLETA; esta se rehízo grepeando `_OPUS_ALLOWLIST|is_opus_allowlisted|fable` en TODO `backend/`:**

| Prueba / símbolo que toca la allowlist | Veredicto | Evidencia |
|---|---|---|
| `tests/test_adaptive_selector_wiring.py::test_proposal_always_passes_clamp` | **NO se rompe** | Usa el id sintético `"claude-opus-NOT-IN-ALLOWLIST"` (`:237`), que sigue fuera de la lista |
| `services/adaptive_selector.py:34` `assert _MODEL_OPUS in llm_router._OPUS_ALLOWLIST` | **NO se rompe** | `_MODEL_OPUS = "claude-opus-4-8"` (`:31`) sigue en el conjunto (solo se agrega un elemento) |
| `tests/test_adaptive_selector.py:154` `assert sel.model in llm_router._OPUS_ALLOWLIST` | **NO se rompe** | Solo exige pertenencia; ampliar el conjunto no la quita |
| `tests/test_acceptance_contract.py::…` (`:294`, `:311` `assert "fable" not in low`) | **NO se rompe** | Habla de fable, que este plan **no** agrega |
| `tests/test_difficulty_routing.py:191-194` | **NO se rompe** | Verifica `d.model == clamp_model(d.model)` y `"fable" not in d.model` sobre lo que `decide()` propone, y `decide()` nunca propone opus por sí solo |
| **`tests/test_llm_router_opus_flag.py::test_fable_still_blocked_with_allow_opus` (`:41-43`)** | **NO se rompe EN LA v2** — **SE ROMPÍA en la v1** | `clamp_model("claude-fable-5", allow_opus=True) == "claude-sonnet-5"`. Solo sigue verde porque fable **queda fuera** |
| **`tests/test_plan212_opus_end_to_end.py::test_decide_allow_opus_true_still_blocks_fable` (`:43-44`)** | **NO se rompe EN LA v2** — **SE ROMPÍA en la v1** | Ídem. Archivo **registrado en los dos scripts del arnés** (`sh:795`, `ps1:692`) |
| **`tests/test_plan212_opus_end_to_end.py::test_is_opus_allowlisted` (`:52-55`)** | **NO se rompe EN LA v2** — **SE ROMPÍA en la v1** | Afirma `is_opus_allowlisted(x) is False` para `(None, "", "claude-sonnet-5", "claude-opus-4-7", "claude-fable-5")`. **`claude-opus-5` no está en esa lista**, así que agregarlo es seguro |
| `tests/test_llm_router_cap.py:38`, `:95` | **NO se rompe** | Usa `clamp_model("claude-fable-5")` sin `allow_opus` y overrides `claude-opus-4-7` / `claude-fable-9`, todos fuera de la lista |

**Archivo 2 — `Stacky Agents/backend/harness/pricing.py`**, símbolo `DEFAULT_PRICES` (hoy `:24`):

Hoy tiene `"claude-opus-4": (5.0, 25.0)` (`:25`) y `"claude-fable-5": (10.0, 50.0)` (`:31`) pero **no** `claude-opus-5`. El diccionario matchea **por prefijo**, y `"claude-opus-5"` **no** empieza con `"claude-opus-4"` — el propio archivo ya documenta esa trampa en `:27` para el caso de sonnet. Agregar, junto a las otras entradas de Anthropic:

```python
    # Plan 288 — Opus 5. Prefijo propio: "claude-opus-5" NO matchea "claude-opus-4".
    "claude-opus-5": (5.0, 25.0),
```

> **Si el precio real difiere, se corrige el número, no la estructura.** Lo que este plan garantiza es que **exista** una entrada: sin ella, el centro de costos atribuye el gasto a la tarifa por defecto y el informe miente.

**Criterio binario de F6 (los 5 comandos, desde `Stacky Agents/backend`):**

```bash
.venv/Scripts/python.exe -m pytest tests/test_plan288_catalogo_vivo.py -q --no-header -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/test_adaptive_selector.py tests/test_adaptive_selector_wiring.py tests/test_difficulty_routing.py tests/test_acceptance_contract.py -q --no-header -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/test_llm_router_opus_flag.py -q --no-header -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/test_plan212_opus_end_to_end.py tests/test_llm_router_cap.py -q --no-header -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/test_harness_pricing.py -q --no-header -p no:cacheprovider
```

- El primero: **todo verde salvo lo que depende de F7** (el invariante sobre el catálogo efectivo con la cuenta apagada ya tiene que estar verde).
- El segundo, el tercero y el cuarto: **exactamente el mismo número que en F0.1 puntos 9, 13 y 14**. Si baja **uno solo**, el cambio del clamp rompió algo: **parar**.
- El quinto: igual o mejor que F0.1 punto 15.

---

### F7 — El lector de la cuenta local, CON filtro de admisión

**Objetivo:** que Stacky sepa qué modelos tiene **esta** cuenta, leyendo lo que el programa de Claude Code ya guardó en el disco del operador, **y que solo entren los que se pueden ejecutar de verdad**.
**Valor:** cierra los puntos 1 y 3 del comportamiento esperado ("consultar dinámicamente" y "no mostrar modelos sin acceso") con la **única** fuente que existe (§4.4). Sin red, sin credenciales, sin gasto.
**Flag:** `STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED` (**ON**). **Trabajo del operador: ninguno.** **Motores:** solo escribe en el bloque `claude_code_cli`; a Codex y Copilot **no les agrega ninguna clave**.

---

#### F7.0 — Antes de tocar nada: el respaldo de emergencia deja de contaminarse (cierra C12)

**Defecto verificado, preexistente:** `services/model_catalog.py:103-104` asigna `result["runtimes"] = _EMERGENCY_FALLBACK["runtimes"]` — **la referencia, no una copia** — y después `_merge_probe` le hace `cli.setdefault("models", []).append(...)` (`:150-154`). Resultado: en producción, la **constante de módulo** `_EMERGENCY_FALLBACK` queda mutada para siempre. La v1 agregaba un **segundo** escritor sobre el mismo defecto.

**Cambio (una línea):**

```python
    except Exception as e:  # noqa: BLE001
        logger.warning("model_catalog: fallback de emergencia (%s)", e)
        # Plan 288 F7.0 — COPIA PROFUNDA: `_merge_probe` y `_merge_cuenta` hacen
        # append sobre este dict. Sin la copia se muta la constante de modulo y el
        # respaldo de emergencia queda contaminado para el resto del proceso.
        result = {"fallback_used": True, "error": str(e), "loaded_at": now,
                  "runtimes": copy.deepcopy(_EMERGENCY_FALLBACK["runtimes"])}
```

Agregar `import copy` arriba del módulo.

**Caso de prueba (en `tests/test_plan288_catalogo_vivo.py`):** `test_el_respaldo_de_emergencia_no_se_contamina` — forzar dos cargas con el archivo ilegible y verificar que `len(_EMERGENCY_FALLBACK["runtimes"]["claude_code_cli"]["models"])` es **el mismo antes y después**. **Dos patas:** en el mismo test se verifica que la respuesta **sí** trajo los modelos (si no, el test pasaría con el catálogo vacío).

---

#### F7.1 — El módulo lector

**Archivo NUEVO:** `Stacky Agents/backend/services/claude_account_models.py`

**Contrato exacto (los nombres son parte del contrato; no renombrar):**

```python
"""Plan 288 F7 — Que modelos tiene ESTA cuenta de Claude Code, leido del disco.

CUATRO REGLAS DURAS:
1. **Nunca invoca un modelo ni sale a la red.** Lee dos archivos de texto locales.
2. **Nunca resta.** Lo leido se SUMA al catalogo; nunca quita un id que ya estaba.
3. **Nunca propaga una excepcion.** Sin archivos, con permisos denegados o con un
   JSON roto, devuelve `disponible=False` con el motivo y el catalogo queda igual.
4. **Nunca admite un id que Stacky no pueda ejecutar.** El archivo de estadisticas
   del programa registra TODO lo que la sesion uso, incluidos modelos de otros
   proveedores y modelos locales. Sin filtro, el selector de Claude Code mostraria
   ids que ese programa no puede correr. Ver `_admisible` y el Plan 288 §4.4(b-bis).

POR QUE ESTA FUENTE Y NO OTRA (medido el 2026-08-02, ver Plan 288 §4.4):
  - El programa instalado (2.1.220) NO tiene subcomando de listado: los 3
    candidatos de model_probe.py dan `unknown option`.
  - La ruta de listado del proveedor refleja una clave de interfaz, no una
    suscripcion; aca el motor corre con la sesion del programa
    (`oauthAccount.billingType == "stripe_subscription"`).
  - Estos dos archivos SI existen y SI traen el dato.

LO QUE ESTO NO ES: no es una consulta a la suscripcion. Es lo que esta instalacion
registro sobre esta cuenta, filtrado a lo ejecutable. Ver Plan 288 §4.4(c).
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
# Regla 5.a del filtro de admision.
_PREFIJO_ADMISIBLE = "claude-"


@dataclass(frozen=True)
class LecturaCuenta:
    disponible: bool
    motivo: str                 # ok | flag_apagada | sin_archivos | json_ilegible
    suscripcion: str            # p. ej. "claude_max"; "" si no se pudo leer
    nivel_de_limite: str        # p. ej. "default_claude_max_20x"; "" si no se pudo leer
    usados: tuple[str, ...]     # ids NORMALIZADOS y ADMISIBLES que esta cuenta ejecuto
    ofrecidos: tuple[str, ...]  # ids NORMALIZADOS y ADMISIBLES que el programa ofrece de mas
    etiquetas: dict             # id_normalizado -> rotulo que el propio programa le pone
    omitidos: tuple             # ((id_crudo, motivo), ...) — TODO lo que el filtro descarto
    crudos: tuple[str, ...]     # ids tal cual venian, solo para diagnostico


def ruta_config_claude() -> Path:
    """~/.claude.json, o el equivalente si CLAUDE_CONFIG_DIR esta definido."""


def ruta_stats_claude() -> Path:
    """~/.claude/stats-cache.json, o el equivalente bajo CLAUDE_CONFIG_DIR."""


def normalizar_id_modelo(crudo: str) -> str:
    """Saca el sufijo de fecha y el de variante. NO toca nada mas.

    'claude-haiku-4-5-20251001' -> 'claude-haiku-4-5'
    'claude-fable-5[1m]'        -> 'claude-fable-5'
    'claude-opus-5'             -> 'claude-opus-5'
    'qwen2.5-coder:7b'          -> 'qwen2.5-coder:7b'   (no se toca; el filtro lo rechaza)
    """


def _admisible(id_normalizado: str) -> tuple[bool, str]:
    """Filtro de admision. Devuelve (entra, motivo_si_no_entra)."""
```

**Reglas de comportamiento (cada una es un caso de prueba):**

| # | Regla |
|---|---|
| 1 | Flag apagada → `LecturaCuenta(disponible=False, motivo="flag_apagada", …)` y **no se abre ningún archivo** (se verifica con un doble sobre `Path.read_text` que cuenta llamadas: **0**). La flag se lee **desde `config.config`**, nunca con `os.getenv` (§5.2) |
| 2 | Ninguno de los dos archivos existe → `motivo="sin_archivos"`, listas vacías, **sin excepción** |
| 3 | `~/.claude.json` existe pero es JSON inválido → `motivo="json_ilegible"`, **sin excepción**; si el otro archivo sí se pudo leer, lo que salió de ahí **se conserva** |
| 4 | `crudos` = claves de `stats-cache.json → modelUsage` **más** las claves de cada `dailyModelTokens[].tokensByModel` **más** los `value` de `~/.claude.json → additionalModelOptionsCache` **más** los ids de `modelAccessCache` si trae alguno (hoy viene `[]`; el lector tolera lista vacía **y** lista de objetos con clave `id` o `value`). Sin repetir, conservando el orden de aparición |
| **5** | **FILTRO DE ADMISIÓN — las TRES condiciones, en este orden. Un id entra solo si las cumple las tres:** **(a)** el id **normalizado** empieza con `"claude-"` → si no: `omitidos += ((crudo, "otro_proveedor"),)`; **(b)** `llm_router.clamp_model(normalizado) == normalizado` **o** `llm_router.is_opus_allowlisted(normalizado)` → si no: `omitidos += ((crudo, "bloqueado_por_politica_de_costo"),)`; **(c)** el normalizado no está ya en el catálogo → si ya está: no se duplica y **no** cuenta como omitido. **Import perezoso de `llm_router` dentro de la función**, para que este módulo siga sin depender de nada de Stacky salvo `config` en el nivel superior |
| **6** | **[ADICIÓN ARQUITECTO] `omitidos` se PUBLICA, no se esconde.** Cada descarte viaja con su id crudo y su motivo hasta la respuesta y hasta la pantalla (F8, F9 regla 8). El operador tiene que poder ver *"tu cuenta usó `claude-fable-5`, Stacky no lo ofrece porque está bloqueado por política de costo"* en vez de preguntarse por qué falta |
| 7 | `etiquetas[id_normalizado] = label` cuando el objeto de `additionalModelOptionsCache` trae `label`; si no trae, no se inventa (no entra al diccionario) |
| 8 | `suscripcion = oauthAccount.organizationType` y `nivel_de_limite = oauthAccount.organizationRateLimitTier`; **nunca** se leen `emailAddress`, `accountUuid`, `displayName`, `organizationName` ni `organizationUuid` — no hacen falta y son datos personales |
| 9 | El lector **no cachea por su cuenta**: lo llama `_merge_cuenta` dentro del refresco de caché que ya existe (300 s). Un archivo que cambia se ve en el siguiente refresco o con `?refresh=true` |
| 10 | **Nunca resta.** Un id del catálogo que la cuenta no registra **se conserva** |

**Prueba de regresión literal del filtro (obligatoria).** Un caso de prueba usa **exactamente** el contenido medido el 2026-08-02 (§4.4(b)) como fixture, y afirma:

```python
assert lectura.usados == ("claude-sonnet-4-6", "claude-sonnet-5", "claude-haiku-4-5",
                          "claude-opus-4-8", "claude-opus-5")
assert lectura.ofrecidos == ()
assert dict(lectura.omitidos) == {
    "claude-fable-5":                "bloqueado_por_politica_de_costo",
    "claude-fable-5[1m]":            "bloqueado_por_politica_de_costo",
    "glm-4.7":                       "otro_proveedor",
    "glm-5.2":                       "otro_proveedor",
    "qwen2.5:3b":                    "otro_proveedor",
    "qwen2.5-coder:7b":              "otro_proveedor",
    "qwen3-coder:30b-a3b-q4_K_M":    "otro_proveedor",
}
```

**Este es el caso que la v1 no tenía y que la habría hundido.**

---

#### F7.2 — Cableado: función propia, NO dentro de `_merge_probe`

**Archivo a editar:** `Stacky Agents/backend/services/model_catalog.py`.

**Por qué una función propia (cierra C3 y C4):** `_merge_probe` retorna temprano en **dos** casos que no tienen nada que ver con este plan — `STACKY_MODEL_PROBE_ENABLED` apagada (`:123-124`) y `STACKY_TEST_MODE` activo (`:128-129`) —. Meter el lector adentro lo ata a una flag ajena y lo deja **inejecutable en pruebas**, que es donde hay que probarlo.

**(a) En `load_model_catalog`, símbolo `result = _merge_probe(result)` (hoy `:106`), agregar la línea siguiente:**

```python
    result = _merge_probe(result)
    result = _merge_cuenta(result)   # Plan 288 F7 — segunda fuente, independiente
```

**(b) Función nueva, inmediatamente después de `_merge_probe`:**

```python
def _merge_cuenta(catalog: dict) -> dict:
    """Plan 288 F7 — Suma al bloque claude_code_cli lo que la cuenta local declara.

    INDEPENDIENTE de _merge_probe a proposito (Plan 288 §5.1): no comparte su flag
    ni su guarda de modo de prueba. Es determinista porque el lector resuelve sus
    rutas desde CLAUDE_CONFIG_DIR, que los tests apuntan a un directorio temporal.

    Escribe SOLO en el bloque claude_code_cli. A codex_cli y github_copilot no les
    agrega ninguna clave: el gate de paridad de F11 lo exige.
    """
    try:
        from services.claude_account_models import leer_cuenta_claude

        cli = (catalog.get("runtimes") or {}).get("claude_code_cli")
        if not isinstance(cli, dict):
            return catalog

        lectura = leer_cuenta_claude()
        conocidos = {m.get("id") for m in (cli.get("models") or [])}
        agregados_cuenta: list = []

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
            "omitidos": [{"id": i, "motivo": m} for i, m in lectura.omitidos],
        }
        if agregados_cuenta:
            # Concatenar, no reemplazar: hoy puede valer "static_config_file" o
            # "static_config_file+live_probe".
            cli["source"] = f"{cli.get('source', 'static_config_file')}+cuenta_local"
        return catalog
    except Exception:  # noqa: BLE001 — el catalogo nunca cae por el lector de cuenta
        logger.debug("model_catalog: lector de cuenta fallo (no critico)", exc_info=True)
        return catalog
```

- El `import` de `leer_cuenta_claude` va **dentro** de la función, igual que hace `_merge_probe` con sus dependencias, para no crear un ciclo en tiempo de importación. Confirmarlo con `python -c "import services.model_catalog"`.
- **Además, en la misma fase — publicar el motivo de la sonda muerta.** El bloque `cli["probe"]` ya guarda `reason` (`:162-167`). No hay que cambiarlo: solo hay que asegurarse de que **viaje** hasta la pantalla (F8) y de dejar escrito en el comentario del módulo que `no_candidate_worked` es el valor **esperado** en el programa 2.x, para que nadie lo confunda con una avería.

**Archivo de prueba NUEVO:** `Stacky Agents/backend/tests/test_plan288_cuenta_local.py`, con **13 casos**, nombrados:

```
cuenta_flag_apagada_no_abre_archivos
cuenta_sin_archivos_no_lanza
cuenta_json_roto_conserva_lo_otro
cuenta_usados_normaliza_y_dedup
cuenta_ofrecidos_tolera_formas
cuenta_etiqueta_no_se_inventa
cuenta_no_lee_datos_personales
cuenta_no_cachea_por_su_cuenta
cuenta_no_duplica_ids_del_catalogo
cuenta_nunca_resta
cuenta_omitidos_filtro_literal_del_disco_real_2026_08_02
cuenta_viva_con_la_sonda_apagada
cuenta_cableada_bajo_modo_de_prueba
```

- `cuenta_omitidos_filtro_literal_…` es la prueba de regresión literal de §F7.1 (los 7 descartes con sus motivos).
- `cuenta_viva_con_la_sonda_apagada` fija `STACKY_MODEL_PROBE_ENABLED=False` y verifica que **igual** aparece `cli["cuenta"]["disponible"] is True` (cierra C4). **Dos patas:** en el mismo test se verifica que `cli` **no** tiene la clave `probe`, que es lo que prueba que la sonda de verdad estaba apagada.
- `cuenta_cableada_bajo_modo_de_prueba` corre con `STACKY_TEST_MODE=1` y verifica que `cli["cuenta"]` **existe** (cierra C3). **Dos patas:** en el mismo test se verifica que `cli["cuenta"]["agregados"]` trae el id sembrado en el `tmp_path`.

> **Los 13 usan archivos temporales propios con `tmp_path` + `monkeypatch.setenv("CLAUDE_CONFIG_DIR", …)`. NINGUNO lee el disco real del operador.** Es la diferencia entre una prueba y una lotería.

**Comando y criterio binario:**

```bash
.venv/Scripts/python.exe -m pytest tests/test_plan288_cuenta_local.py -q --no-header -p no:cacheprovider   # 13 passed
.venv/Scripts/python.exe -m pytest tests/test_plan288_catalogo_vivo.py -q --no-header -p no:cacheprovider  # TODO VERDE
.venv/Scripts/python.exe -m pytest tests/test_plan159_model_catalog_loader.py tests/test_plan159_model_catalog_endpoint.py -q --no-header -p no:cacheprovider  # igual o mejor que F0.1
python -c "import services.model_catalog"   # sin ImportError (desde backend, con el .venv)
```

---

### F8 — La respuesta publica de dónde salió cada modelo, y los TIPOS lo declaran

**Objetivo:** que la pantalla tenga con qué decir la verdad, **y que compile**.
**Valor:** cierra el punto 4 del comportamiento esperado. **Flag:** `STACKY_MODEL_CATALOG_ENABLED` (la que ya existe). **Trabajo del operador: ninguno.** **Motores:** aditivo para los tres en el nivel superior; `cuenta` solo en `claude_code_cli`.

**Archivo a editar 1 — `Stacky Agents/backend/api/agents.py`**, función `model_catalog_route` (símbolo; decorador `@bp.get("/model-catalog")` en `:1457`, `def` en `:1458`).

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

**Trampa verificada que hay que evitar:** el bloque del plan 264 (`:1485-1500`) **reconstruye** cada entrada de `runtimes` con un diccionario nuevo y usa `_caps["models"] or runtimes[_rt].get("models") or []` (`:1495`). Las claves `probe` y `cuenta` **sobreviven** porque el `{**runtimes[_rt], …}` de `:1490` las conserva — **pero solo si están en `runtimes[_rt]`**. Y `_caps["models"]` **no** las pisa, porque `capabilities_for` deriva sus modelos del **mismo catálogo ya fusionado** (`services/runtime_capabilities.py:79,82`). Verificarlo con un caso de prueba explícito:

| Test (en `tests/test_plan288_catalogo_vivo.py`) | Qué prueba |
|---|---|
| `test_respuesta_conserva_probe_y_cuenta_despues_del_enriquecido_de_capacidades` | Con el bloque de capacidades activo, la respuesta de la ruta trae `runtimes.claude_code_cli.cuenta.motivo` **y** `runtimes.claude_code_cli.cuenta.omitidos`. **Dos patas: presencia de las claves nuevas + presencia de `effort_mode`**, que es la clave que puso el 264 y que no puede desaparecer |
| `test_respuesta_trae_fallback_used_y_error` | Forzando un archivo de catálogo ilegible, la respuesta trae `fallback_used: true` y `error` no vacío |
| `test_los_modelos_del_catalogo_efectivo_llegan_a_la_respuesta` | El id agregado por la cuenta aparece en `runtimes.claude_code_cli.models` **después** del enriquecido del 264. Es la prueba de que la capa del 264 no anula el plan |

**Archivo a editar 2 — `Stacky Agents/frontend/src/api/endpoints.ts` (cierra C6; la v1 NO lo mencionaba y sin esto `tsc` falla).**

En `export interface RuntimeModelCatalog` (hoy abre en `:1140`), agregar antes del `}` de cierre:

```ts
  /** Plan 288 — solo en claude_code_cli: de dónde salió la lista y qué se descartó. */
  cuenta?: {
    disponible: boolean;
    motivo: string;
    suscripcion: string;
    nivel_de_limite: string;
    agregados: string[];
    omitidos: { id: string; motivo: string }[];
  };
  /** Plan 212 — resultado de la sonda al programa instalado. Plan 288: ahora se muestra. */
  probe?: { ok: boolean; command: string; reason: string; added: string[] };
```

En `export interface ModelCatalogResponse` (hoy abre en `:1159`), agregar antes del `}` de cierre:

```ts
  /** Plan 288 — el motivo por el que se usó el respaldo de emergencia. */
  error?: string | null;
```

> `RuntimeModelCatalog` **ya tiene** `error?: string | null` (verificado) — esa es la del bloque de Copilot y **no se toca ni se duplica**. La que falta es la de **nivel superior**, en `ModelCatalogResponse`.

**Criterio binario de F8:** los 3 casos nuevos en verde, `tests/test_plan159_model_catalog_endpoint.py` igual o mejor que F0.1, y `npx tsc --noEmit` en **0 errores**.

---

### F9 — La pantalla dice de dónde salió la lista (lógica pura + un solo componente)

**Objetivo:** que el operador vea, sin abrir nada, si está mirando su lista, la de respaldo, o una lista recortada — y por qué.
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

**Reglas (cada una es un caso de prueba, 9 en total):**

| # | Entrada | Salida |
|---|---|---|
| 1 | `res` `null`/`undefined` | `{nivel: "respaldo", texto: "Lista de respaldo: no se pudo consultar el catálogo de modelos.", detalle: ""}` |
| 2 | `res.ok === false` | igual que 1, con `res.reason` en `detalle` si viene |
| 3 | `res.fallback_used === true` | `nivel: "respaldo"`, texto que **nombra el motivo** (`res.error`) |
| 4 | catálogo bien, `cuenta.disponible === true`, `cuenta.omitidos` vacío | `nivel: "ok"`, `texto: ""` — **no se molesta al operador cuando todo salió bien** |
| 5 | catálogo bien pero `cuenta.disponible === false` | `nivel: "parcial"`, texto que dice que la lista es la de fábrica y por qué no se pudo leer la cuenta (`cuenta.motivo`) |
| **6** | **`cuenta` AUSENTE** (es el caso real de `codex_cli` y `github_copilot`: F11 prohíbe agregarles la clave) **o** `runtime !== "claude_code_cli"` | `nivel: "ok"`, `texto: ""` — **no aplicar no es un problema**. **Corrige C5: la v1 esperaba `motivo === "no_aplica"`, que nunca se produce** |
| 7 | `runtime === "github_copilot"` con `error` no vacío en su bloque | `nivel: "parcial"`, texto con el error de introspección |
| **8** | **`cuenta.omitidos.length > 0`** | `nivel: "parcial"`, texto que **lista los ids descartados con su motivo en castellano** (`otro_proveedor` → "no es un modelo de Claude Code"; `bloqueado_por_politica_de_costo` → "Stacky lo tiene bloqueado por política de costo"). **[ADICIÓN ARQUITECTO]** |
| **9** | `runtime === "claude_code_cli"` y el bloque ofrece algún id de tier alto | el `detalle` incluye: "el agente de mantenimiento y despliegue nunca usa modelos de tier alto, aunque los elijas" — **corrige C8**, porque `allow_opus_for_run` devuelve `False` para `agent_type == "devops"` (`services/claude_code_cli_runner.py:545-548`) |
| 10 | Un `runtime` que no está en la respuesta | `nivel: "respaldo"`, sin lanzar |

**Archivo NUEVO 2 — prueba:** `Stacky Agents/frontend/src/services/__tests__/modelCatalogOrigin.test.ts`, con los 10 casos, nombrados `origen_sin_respuesta`, `origen_no_ok`, `origen_respaldo_nombra_el_motivo`, `origen_todo_bien_no_molesta`, `origen_cuenta_ilegible_es_parcial`, `origen_cuenta_ausente_no_es_problema`, `origen_copilot_con_error`, `origen_omitidos_se_explican`, `origen_avisa_lo_del_agente_de_despliegue`, `origen_motor_desconocido_no_lanza`.

**Archivo NUEVO 3 — el componente tonto:** `Stacky Agents/frontend/src/components/AvisoCatalogoModelos.tsx`

- Props: `{ runtime: string }`.
- Usa `useModelCatalog()` y `describirOrigenCatalogo`.
- Si `nivel === "ok"` devuelve `null`. Si no, renderiza **un solo** `<p role="note" title={detalle}>{texto}</p>` **más** el botón de refresco de F9.1.
- **Sin estilos escritos a mano en el marcado ni colores en hexadecimal**: los ratchets de deuda cuentan por archivo. Si hace falta color, usar las variables del tema que **sí existen** (`--accent`, `--success`, `--danger`, `--border`, `--text-primary`, `--bg-panel`). **`--color-*` NO existe en este tema**: usarla deja el aviso invisible.
- Usar las primitivas de `components/ui` para el botón, no un `<button>` crudo (es lo que hace `JerarquiaLocalControl.tsx:13,123`).

**Archivo a editar 4 — `Stacky Agents/frontend/src/hooks/useModelCatalog.ts`:** el cambio es **aditivo**; ningún consumidor actual se rompe.

```ts
export interface UseModelCatalogResult {
  catalog: Record<string, RuntimeModelCatalog>;
  loading: boolean;
  /** Plan 288 — la respuesta cruda, para que la pantalla pueda decir de dónde salió. */
  respuesta: ModelCatalogResponse | null;
  /** Plan 288 F9.1 — fuerza una relectura del catálogo. */
  refrescar: () => void;
}
```

Guardar la respuesta en un `useState` paralelo y devolverla; `resolveModelCatalog` sigue haciendo exactamente lo que hace hoy.

**Archivos a editar 5..8 — montar el aviso en las 4 superficies de selección** (una línea cada una, al lado del selector de modelo que ya existe):

- `Stacky Agents/frontend/src/components/EpicFromBriefModal.tsx` (usa el catálogo en `:81,88`)
- `Stacky Agents/frontend/src/components/IncidentResolverModal.tsx` (`:91`)
- `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx` (`:348`)
- `Stacky Agents/frontend/src/pages/TicketBoard.tsx` (`:150`)

En cada uno: `<AvisoCatalogoModelos runtime={<el motor activo de esa pantalla>} />`. **`ModelDecisionChip.tsx` no se toca**: es un indicador de lo que ya se decidió, no un selector.

**Archivo NUEVO 9 — el gate de montaje (cierra C15):** `Stacky Agents/frontend/src/__tests__/plan288AvisoMontado.test.ts`

La v1 medía K7 con `grep -rn "AvisoCatalogoModelos" src | wc -l ≥ 4`, que **cuenta líneas**: el `import` y el uso en el mismo archivo ya suman 2, así que el umbral se alcanzaba montando el aviso en **dos** archivos. Se reemplaza por una prueba que verifica **los cuatro archivos por nombre**:

```ts
const SUPERFICIES = [
  "src/components/EpicFromBriefModal.tsx",
  "src/components/IncidentResolverModal.tsx",
  "src/pages/PlansBoardPage.tsx",
  "src/pages/TicketBoard.tsx",
];
// Por cada archivo: toContain("<AvisoCatalogoModelos") Y toContain("useModelCatalog")
// (dos patas: si el archivo perdió el selector, el aviso solo no significa nada).
// Y una pata de AUSENCIA: ModelDecisionChip.tsx NO monta el aviso.
```

**Criterio binario de F9 (cierra C16 — la lista completa de ratchets de pantalla que toca un `.tsx` nuevo):**

```bash
# desde Stacky Agents/frontend
npx vitest run src/services/__tests__/modelCatalogOrigin.test.ts      # 10 passed
npx vitest run src/__tests__/plan288AvisoMontado.test.ts              # verde
npx vitest run src/__tests__/modelSelectorsConsistency.test.ts        # verde (sigue sin listas locales)
npx vitest run src/__tests__/formDebtRatchet.test.ts                  # verde
npx vitest run src/__tests__/uiDebtRatchet.test.ts                    # verde
npx vitest run src/__tests__/formatDebtRatchet.test.ts                # verde
npx vitest run src/__tests__/motionDebtRatchet.test.ts                # verde
npx vitest run src/__tests__/copyDebtRatchet.test.ts                  # verde
npx vitest run src/__tests__/adhocModalRatchet.test.ts                # verde
npx vitest run src/__tests__/a11yCss.test.ts                          # verde
npx vitest run src/__tests__/formPrimitives.test.ts                   # verde
npx tsc --noEmit                                                      # 0 errores
npx vite build                                                        # termina sin error
```

**Si alguno de esos once estaba rojo ANTES**, se anota en F0.1 y el criterio pasa a ser **delta**, no absoluto.

---

### F9.1 — [ADICIÓN ARQUITECTO] El catálogo se refresca solo (cierra C10)

**Por qué existe esta fase.** El operador pidió textualmente *"actualización ante cambios"*. La v1 daba eso por cumplido con el tiempo de vida de 300 s del servidor. **Es falso**, y está medido: `frontend/src/hooks/useModelCatalog.ts:12-19` guarda la promesa en una variable **de módulo** (`catalogPromise`) que **nunca se invalida**. Consecuencia real: si el operador actualiza Claude Code, o Stacky detecta un modelo nuevo, **la pestaña abierta sigue mostrando la lista vieja hasta que se recargue la aplicación entera**. Con este plan eso sería especialmente cruel: `claude-opus-5` aparecería… en la próxima recarga.

**Restricciones que respeta:** cero trabajo extra para el operador (es automático); no degrada (a lo sumo **una** petición por vuelta a la pestaña, y solo si pasó el tiempo de vida); no agrega flag; idéntico en los 3 motores porque el catálogo es uno solo; human-in-the-loop intacto (no cambia ninguna selección, solo la lista disponible); reusa lo que existe (`ModelCatalogApi.get(true)` ya acepta `?refresh=true`, `endpoints.ts:1167-1169`).

**Archivo a editar — `Stacky Agents/frontend/src/hooks/useModelCatalog.ts`:**

```ts
// Plan 288 F9.1 — la promesa de modulo se puede invalidar. Sin esto, una pestaña
// abierta se queda con la primera lista para siempre y el TTL de 300s del servidor
// no sirve de nada del lado del navegador.
let catalogPromise: Promise<ModelCatalogResponse> | null = null;
let catalogPedidoEn = 0;
const TTL_MS = 300_000;

export function invalidarCatalogoModelos(): void {
  catalogPromise = null;
  catalogPedidoEn = 0;
}
```

Y en el hook:

- `refrescar()` llama a `invalidarCatalogoModelos()` y vuelve a pedir con `ModelCatalogApi.get(true)`.
- Un `useEffect` engancha `window.addEventListener("visibilitychange", …)` y `("focus", …)`: **si `document.visibilityState === "visible"` y pasaron más de `TTL_MS` desde `catalogPedidoEn`**, invalida y vuelve a pedir. Los dos escuchadores se limpian en el `return` del efecto.
- **Nunca** dispara si la pestaña está oculta, y **nunca** dispara dos veces seguidas antes del tiempo de vida: eso es lo que impide convertir esto en un sondeo.

**Archivo NUEVO — lógica pura extraída para poder probarla sin DOM:** `Stacky Agents/frontend/src/services/modelCatalogRefresh.ts`

```ts
/** Plan 288 F9.1 — ¿corresponde volver a pedir el catálogo? FUNCIÓN PURA. */
export function debeRefrescarCatalogo(
  visible: boolean,
  pedidoEnMs: number,
  ahoraMs: number,
  ttlMs: number,
): boolean;
```

**Archivo NUEVO — prueba:** `Stacky Agents/frontend/src/services/__tests__/modelCatalogRefresh.test.ts`, **6 casos**: `refresco_no_si_la_pestana_esta_oculta`, `refresco_no_antes_del_tiempo_de_vida`, `refresco_si_visible_y_vencido`, `refresco_si_nunca_se_pidio`, `refresco_tolera_reloj_hacia_atras`, `refresco_no_dispara_dos_veces_seguidas`.

**Criterio binario de F9.1:**

```bash
npx vitest run src/services/__tests__/modelCatalogRefresh.test.ts   # 6 passed
npx tsc --noEmit                                                    # 0 errores
```

Y en el smoke visual (F12 paso 9): con la aplicación abierta, editar `backend/config/model_catalog.json`, cambiar de pestaña y volver ⇒ **la lista nueva aparece sin recargar**.

---

### F10 — Los DOS ratchets del arnés, en el MISMO commit que crea los archivos de prueba

**Objetivo:** que el arnés corra las suites nuevas sin poner rojos a los dos guardianes que auditan la lista.
**Archivos:** `Stacky Agents/backend/scripts/run_harness_tests.sh` y `Stacky Agents/backend/scripts/run_harness_tests.ps1`. **Flag:** ninguna. **Trabajo del operador: ninguno.**

> **Por qué en el mismo commit que crea el archivo y no antes:** `tests/test_harness_ratchet_meta.py::test_ratchet_no_referencia_archivos_inexistentes` (`:79`) y `tests/test_plan259_ratchet_script_parity.py` ponen **rojas dos suites hoy verdes** si la lista nombra un archivo que todavía no existe. Y `test_ratchet_clasifica_todos_los_tests` (`:43`) las pone rojas si el archivo existe y **no** está ni en la lista ni en el allowlist. **Las dos direcciones fallan: hay que hacerlo junto.**

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
3. **NO agregar estos archivos a `backend/tests/harness_ratchet_allowlist.txt`.** Estar en los dos lugares pone roja a `test_allowlist_no_se_solapa_con_ratchet` (`test_harness_ratchet_meta.py:56`). Además el allowlist tiene hoy **194** entradas contra `_ALLOWLIST_MAX = 197` (`:66`) — **re-verificado en la crítica** — y **solo puede bajar**.

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
| `test_paridad_codex_y_copilot_no_cambian_con_la_cuenta_encendida` | Se arma la respuesta con `STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED` en `True` y en `False` y se comparan **clave por clave** los bloques `codex_cli` y `github_copilot`: iguales, **y ninguno de los dos tiene la clave `cuenta`**. **Dos patas: además se verifica que el bloque `claude_code_cli` SÍ cambió** (si no cambia, el lector no está cableado y la primera mitad pasaría por accidente). **Este test es implementable en la v2 porque `_merge_cuenta` no tiene guarda de modo de prueba (§6.F7.2); en la v1 era imposible** |
| `test_ningun_simbolo_nuevo_nombra_un_motor` | `grep -riE "codex\|copilot"` sobre `services/claude_account_models.py`, `frontend/src/services/modelCatalogOrigin.ts` y `frontend/src/services/modelCatalogRefresh.ts` da **0 coincidencias**. El único que puede nombrar `claude` es el lector, porque es el nombre del archivo de configuración que lee. **Excepción declarada:** `modelCatalogOrigin.ts` **sí** puede nombrar `github_copilot` en la regla 7, porque esa regla existe para mostrar el error de introspección de ese motor; el test excluye esa línea por su marca `// paridad-ok` |

**Criterio binario:** los 2 en verde.

---

### F12 — Cierre: se vuelven a correr los 17 de F0.1, se registra la huella y el smoke visual

**Objetivo:** probar que nada verde se puso rojo y que el operador ve lo que tiene que ver.
**Flag:** ninguna. **Trabajo del operador: solo el smoke visual (5 minutos), y es opcional — todo lo demás es automático.**

**(a) Regresión:** correr los 17 comandos de F0.1. **Cada uno da igual o mejor.** El 12 (ayuda de flags) y el 16 (catálogo de huellas) tienen que dar **exactamente las mismas fallidas y los mismos nombres**. **Se pega la salida literal, no se reporta "todo pasa".**

**(c) Huella de regresión (cierra C18).** Agregar a `Stacky Agents/docs/sistema/error_fingerprints.json`, dentro de `fingerprints`, con **exactamente** la forma que usan las 62 entradas existentes:

```json
{
  "id": "modelo_ofrecido_degradado_en_silencio",
  "title": "El selector ofrece un modelo que el ejecutor cambia por otro sin avisar",
  "class": "silent-substitution",
  "status": "open",
  "log_pattern": "clamped from '(claude-[a-z0-9.\\-]+)' to 'claude-sonnet-5'",
  "log_guarded": true,
  "killed_by": null,
  "guard_test": "tests/test_plan288_catalogo_vivo.py::test_ejecutable_todo_modelo_del_catalogo_efectivo_sobrevive_la_eleccion_explicita",
  "note": "Plan 288 F4/F6/F7. La huella cubre las DOS puertas: el catalogo estatico y el lector de la cuenta local. Un id de tier alto que llegue al catalogo sin estar en la lista de autorizados se ejecuta como sonnet-5 y la pantalla sigue mostrando el otro. status=open a proposito: es una huella de DETECCION.",
  "self_test": {
    "matches": ["INFO model_policy clamped from 'claude-opus-9' to 'claude-sonnet-5' (cap 5.2)"],
    "no_matches": ["INFO model_policy passthrough (dentro del cap)"]
  }
}
```

**Criterio binario de (c):** `tests/test_error_fingerprints_catalog.py` da **exactamente las mismas fallidas que en F0.1 punto 16** — ni una más. Si suma una, la entrada está mal formada y hay que corregirla, no dejarla.

**(b) Smoke visual — 9 pasos, con el resultado esperado escrito. Los textos son los REALES (§4.1), no la palabra "Clasificación":**

| # | Paso | Resultado esperado |
|---|---|---|
| 1 | Abrir el tablero de tickets de un proyecto **GitLab** con la flag `STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED` **encendida** | **No aparecen** los campos `"Tipo (solo en Stacky)"` ni `"Cuelga del ticket número"`, ni el botón `"Guardar clasificación"`. **Sí aparecen** las acciones de siempre |
| 2 | Cambiar a la vista de árbol o de grafo | **No aparece** el botón `"Ver qué se va a cambiar"` |
| 3 | Abrir un ticket de un proyecto **Azure DevOps** | La tarjeta se ve **exactamente igual que antes** del plan |
| 4 | Correr la sincronización de GitLab | Los contadores `usados_local_tipo` / `usados_local_padre` **siguen funcionando**: el motor no se tocó |
| 5 | Abrir cualquier selector de modelo (crear épica desde un resumen, resolver una incidencia, tablero de planes) | **Aparece `Opus 5`** en la lista, arriba. **NO aparecen** `glm-4.7`, `glm-5.2`, `qwen2.5:3b`, `qwen2.5-coder:7b`, `qwen3-coder:30b-a3b-q4_K_M` ni `claude-fable-5[1m]` |
| 6 | Mirar el aviso debajo del selector | Dice que se descartaron esos ids **y por qué** (uno por "no es un modelo de Claude Code", los de fable por "bloqueado por política de costo") |
| 7 | Elegir `Opus 5` y lanzar un agente con el motor Claude Code | En la traza de la ejecución, **solicitado y ejecutado coinciden**: no aparece la línea de degradado de `describeDowngrade` |
| 8 | Renombrar temporalmente `backend/config/model_catalog.json` y recargar | **Aparece el aviso de lista de respaldo** con el motivo, y el selector **sigue teniendo todos los modelos** (nunca queda vacío). Restaurar el nombre |
| 9 | **[ADICIÓN ARQUITECTO]** Con la aplicación abierta, editar `backend/config/model_catalog.json`, cambiar a otra pestaña del navegador y volver | **La lista nueva aparece sin recargar la aplicación.** Es el punto 2 del pedido del operador, que la v1 no cumplía |
| 10 | Abrir el panel de flags del arnés y buscar `STACKY_CLAUDE_ACCOUNT_MODELS_ENABLED` | Aparece, en la categoría de motores, **encendida**, con su texto en llano |

---

## 7. Riesgos y mitigaciones

### 7.1 RIESGO #1 — Frontera con el plan 287 (Bloque A)

**El problema, concreto:** el plan 287 está **escrito pero no implementado** (verificado el 2026-08-02: `frontend/src/components/ticket/TicketFullView.tsx` no existe) y nombra `JerarquiaLocalControl` **dos veces** como acción que su ficha va a **reusar** — en `docs/287_…md:145` (tabla "Acciones reusadas") y `:1041` (tabla de componentes, con el anclaje `components/JerarquiaLocalControl.tsx:31`). **Los dos anclajes están corregidos en la v2: la v1 decía `:109` y `:762` y ninguno de los dos era correcto.** Si el 288 se implementa primero y después alguien implementa el 287 al pie de la letra, **la clasificación vuelve a aparecer**, ahora en la ficha nueva, y el ítem del operador se deshace solo.

**Mitigación en tres capas:**
1. **Orden declarado:** el 288 se puede aplicar **antes o después** del 287 — no hay dependencia técnica. Lo que **no** puede pasar es que el 287 se implemente **sin leer esta sección**.
2. **F3 es condicional y cubre las dos ramas** con el mismo centinela, y su disparador es un `Test-Path`, no un juicio.
3. **El centinela de F1 es un gate de commit**, no un consejo — **para los archivos que existen**. Para el archivo que todavía no existe, la protección es la **línea de comentario** que F3 deja dentro del propio archivo de prueba, más esta instrucción: **quien implemente el 287 tiene que eliminar `JerarquiaLocalControl` y `PublicarEtiquetasGitLab` de las dos tablas de su documento (`:145` y `:1041`) y agregar el cuarto `it` de §6.F3 al centinela del 288.** El resto de su ficha no cambia.

**Por qué NO se borran los dos componentes** (decisión tomada, no pendiente): borrarlos genera un conflicto con un plan ya escrito y con una sesión paralela viva que puede tenerlos sucios; el criterio del operador es **de vista**, no de repositorio; y borrarlos **no baja ningún ratchet** (verificado con `grep -c`: **0 coincidencias** en `formDebtBaseline.json`, `uiDebtBaseline.json` y `motionDebtBaseline.json`). El borrado físico queda **fuera de scope** (§8.1) con su condición escrita.

### 7.2 RIESGO #2 — Supuesto de capacidad del ítem 2

**El problema:** "consultar dinámicamente los modelos habilitados para el usuario" suena a que existe una consulta. **No existe.** Un plan que la prometa entrega una fase inimplementable.

**Mitigación:** §4.4 mide los cinco caminos y descarta tres **con la salida del comando pegada**. El plan implementa los dos ejecutables y lo dice en el propio código (docstring de `services/claude_account_models.py`). **Lo que este plan NO promete:** que el listado refleje una autorización del proveedor. Refleja **lo que el programa de Claude Code guardó sobre esta cuenta en este equipo, filtrado a lo que Stacky puede ejecutar**.

**Riesgo residual #1 y su tapón:** el formato de `~/.claude.json` es interno del programa y puede cambiar sin aviso. Por eso el lector es **tolerante por diseño** (reglas 2, 3, 4 de F7), **nunca resta** y **nunca lanza**: si el formato cambia, Stacky vuelve exactamente al comportamiento de hoy y lo **dice** en el aviso (`nivel: "parcial"`).

**Riesgo residual #2 — el que hundió a la v1 — y su tapón:** el archivo de estadísticas **no distingue proveedor**. Hoy, en esta cuenta, cinco de sus once entradas son de otros proveedores o de modelos locales (§4.4(b-bis)). **El tapón es el filtro de admisión de F7 regla 5**, con su prueba de regresión literal sobre esos seis ids. Mañana pueden aparecer otros: el filtro es por **regla**, no por lista negra, así que sigue funcionando.

### 7.3 RIESGO #3 — Aflojar el clamp puede subir el gasto

**El problema:** `_OPUS_ALLOWLIST` es una barrera de costo. Ampliarla habilita modelos caros.

**Mitigación:** **el ruteo automático NO se toca.** `clamp_model` con su default `allow_opus=False` sigue capando en `claude-sonnet-5`, y `allow_opus_for_run` sigue exigiendo **elección explícita del operador para una corrida puntual** y sigue excluyendo al agente de DevOps (`services/claude_code_cli_runner.py:545-548`). El caso `test_ejecutable_el_ruteo_automatico_sigue_capado_en_sonnet` (F4) lo congela **en la misma corrida** que el caso que amplía. Y F6 agrega el precio de `claude-opus-5` para que el centro de costos no subestime.

**Se agrega UN solo id, no dos.** La v1 ampliaba también a fable, lo que **revertía** una decisión de costo tomada y testeada. En la v2 fable queda afuera y hay un gate (`test_fable_sigue_fuera_del_catalogo_y_de_la_allowlist`) que lo congela.

**Lo que el operador tiene que saber, y por eso aparece en la pantalla (F9 regla 9):** el agente de mantenimiento y despliegue **nunca** ejecuta un modelo de tier alto, aunque el operador lo elija. Antes esto era invisible; ahora se dice.

### 7.4 RIESGO #4 — Sesión paralela viva en el árbol

**El problema:** los planes 286 y 287 los está trabajando otra sesión, que ya movió el cierre de la lista del arnés y desplazó varios anclajes (**9 de los 85 anclajes de la v1 quedaron corridos por eso**).

**Mitigación:** F0.0 revalida por símbolo antes de tocar nada; el documento manda anclar por símbolo cuando el número no coincide (§4.2); y **está prohibido** `git stash`, `git reset`, `git checkout --`, `git rebase` y `git commit --amend`. Para commitear, `git commit -m "<mensaje>" -- "<rutas>"` — **el `-m` va ANTES del `--`**, y un archivo sin seguimiento necesita `git add -- "<ruta>"` primero.

### 7.5 RIESGO #5 — Falsos verdes

| Trampa | Tapón en este plan |
|---|---|
| Un `not.toContain` que pasa porque la ruta está mal | `leer()` afirma `existsSync` **antes** de leer, y cada `it` tiene aserciones de **presencia** |
| `pytest -k` sin coincidencias sale con código 0 | Todos los criterios exigen el **conteo** (`N passed`), no el código de salida |
| `pytest tests` entero como veredicto | Prohibido explícitamente en la cabecera de §6: **un archivo por vez** |
| Un ratchet ya rojo de fábrica que se confunde con regresión propia | §4.5 los declara con nombre; los criterios son en **delta** |
| Una prueba que lee el disco real de quien la corre | F7 obliga a `tmp_path` + `CLAUDE_CONFIG_DIR` en los 13 casos |
| `npx vitest run <ruta inexistente>` sale 1 pero pipeado se pierde | Correr sin tubería y mirar la salida |
| **Un cambio en `TicketGraphView.jsx` que `tsc` no ve** | **`npx vite build` en el criterio de F2 y de F9** — `tsconfig.json` no tiene `allowJs` |
| **Un "el tapón de tsc te avisa si borraste de más"** | **Falso: `noUnusedLocals: false`.** La v1 lo daba por cierto; la v2 lo dice y usa `vite build` |
| **Una prueba de cableado que no corre porque el código se saltea bajo `STACKY_TEST_MODE`** | `_merge_cuenta` **no tiene** esa guarda, y `cuenta_cableada_bajo_modo_de_prueba` lo verifica |
| **Un gate que después de su fase no puede fallar nunca** | La regla 6 de F9 se reescribió (era imposible de disparar); el invariante de F4 sigue vivo porque un id nuevo de tier alto lo rompe |
| **Un `grep \| wc -l` como criterio de montaje** | Reemplazado por `plan288AvisoMontado.test.ts`, que verifica **por nombre de archivo** |

---

## 8. Fuera de scope (explícito, para que nadie lo agregue "de paso")

1. **Borrar `JerarquiaLocalControl.tsx` y `PublicarEtiquetasGitLab.tsx`.** Condición para hacerlo en un plan futuro: que el 287 esté implementado **y** que su documento ya no los nombre como acciones reusadas. Hasta entonces, quedan.
2. **Borrar el motor de la clasificación local** (columnas, ruta `PATCH`, contadores de sincronización, flags del 277). Tiene consumidor de producción (§2.2).
3. **Cambiar el `default_model` del catálogo.** Es una decisión de costo del operador, no de este plan.
4. **Unificar `/api/agents/models` (que sirve `llm_router.CLAUDE_MODELS`, 3 modelos, `api/agents.py:1445`) con `/api/agents/model-catalog`.** Son dos superficies con dos consumidores distintos; unificarlas es un plan propio. **Consecuencia declarada:** `components/ModelPicker.tsx` sigue sin ver Opus 5, porque come de la otra ruta.
5. **Borrar `services/model_probe.py`.** La regla del repositorio es sumar, nunca restar: una versión futura del programa puede agregar el subcomando. Este plan **publica su motivo de fallo**, no lo borra.
6. **Agregar `claude-fable-5[1m]` al catálogo.** La caché de la cuenta declara `s1mAccessCache.hasAccess: false`; F7 lo normaliza a `claude-fable-5` y el filtro lo descarta con motivo `bloqueado_por_politica_de_costo`.
7. **Cualquier camino de escritura nuevo** hacia Azure DevOps, GitLab o el disco del operador.
8. **Tocar el catálogo de Codex o de Copilot.**
9. **Habilitar `claude-fable-5`.** **Fuera de scope por decisión explícita, no por olvido.** Hacerlo exige: (i) agregarlo a `_OPUS_ALLOWLIST`; (ii) **reescribir tres pruebas verdes** que congelan lo contrario — `tests/test_llm_router_opus_flag.py::test_fable_still_blocked_with_allow_opus` (`:41-43`), `tests/test_plan212_opus_end_to_end.py::test_decide_allow_opus_true_still_blocks_fable` (`:43-44`) y `::test_is_opus_allowlisted` (`:52-55`); (iii) revisar el precio de `harness/pricing.py:31` (`(10.0, 50.0)`, el doble que Opus). Es **una decisión de costo del operador**, con human-in-the-loop, no un efecto colateral de un plan de interfaz. Mientras tanto, el aviso de F9 le dice al operador que su cuenta lo usa y que Stacky lo tiene bloqueado.
10. **Sondear el disco de forma periódica.** El lector corre **solo** cuando alguien pide el catálogo y venció el tiempo de vida. Nada de demonios, nada de vigilantes de archivos.

---

## 9. Orden de implementación y Definición de Terminado

### 9.1 Orden numerado (cada paso es un commit; **ninguno se saltea**)

| # | Fase | Bloque | Depende de |
|---|---|---|---|
| 1 | **F0.0** barrido de anclajes | — | — |
| 2 | **F0.1** línea base medida (17 comandos) | — | F0.0 |
| 3 | **F1** centinela de dos patas (queda ROJO a propósito) | A | F0.1 |
| 4 | **F2** retirar los tres montajes | A | F1 |
| 5 | **F3** frontera con el 287 (condicional) | A | F2 |
| 6 | **F4** centinela del catálogo (queda ROJO a propósito) | B | F0.1 |
| 7 | **F5** catálogo al día en los 3 archivos (**solo `claude-opus-5`**) | B | F4 |
| 8 | **F6** lo ofrecido se ejecuta + precios (**solo `claude-opus-5`**) | B | F5 |
| 9 | **F7** copia del respaldo + lector de la cuenta con filtro + flag (las 9 filas de §5.2) | B | F6 |
| 10 | **F8** la respuesta publica origen y respaldo + **los tipos de `endpoints.ts`** | B | F7 |
| 11 | **F9** la pantalla dice de dónde salió la lista | B | F8 |
| 12 | **F9.1** [ADICIÓN ARQUITECTO] el catálogo se refresca solo | B | F9 |
| 13 | **F10** los DOS ratchets, junto con los archivos de prueba | B | F4, F7 |
| 14 | **F11** gate de paridad de motores | B | F7 |
| 15 | **F12** regresión completa + huella + smoke visual | — | todas |

> **F5 y F6 van en el MISMO commit o en commits consecutivos sin nada en el medio.** Entre uno y otro hay una ventana en la que el catálogo ofrece `claude-opus-5` y el runner lo degrada a `claude-sonnet-5`: es exactamente el defecto que este plan existe para matar. El centinela de F4 la deja **roja y visible**, así que no puede pasar inadvertida, pero **no se cierra el día con esa ventana abierta**.

> El Bloque A (pasos 3-5) y el Bloque B (pasos 6-14) son **independientes**: se pueden implementar en cualquier orden entre sí, o en dos commits separados. Dentro de cada bloque, el orden es **obligatorio**.

### 9.2 Definición de Terminado (global, binaria)

1. **K0 = 0, K1 = 0, K2 = 4** — `npx vitest run src/__tests__/plan288SuperficieClasificacion.test.ts` en verde con 3 (o 4) casos.
2. **K3 = 1** — `grep -c "usados_local_tipo" backend/services/gitlab_sync.py` ≥ 1, y `tests/test_plan277_clasificacion_local.py` con el **mismo conteo** que en F0.1.
3. **`plan277JerarquiaLocal.test.ts` sigue en 8 passed sin haberlo tocado.**
4. **Si `TicketFullView.tsx` existe**, el centinela lo cubre con su cuarto caso; si no existe, la línea de comentario de F3 está en el archivo de prueba y la rama tomada está en el registro.
5. **K4 = 0, K5 = 0, K5b = 100 %, K6 = 1** — `tests/test_plan288_catalogo_vivo.py` **todo verde**, `tests/test_plan288_cuenta_local.py` con **13 passed**, incluido `cuenta_omitidos_filtro_literal_del_disco_real_2026_08_02`.
6. **`claude-fable-5` sigue fuera** — `tests/test_llm_router_opus_flag.py` y `tests/test_plan212_opus_end_to_end.py` con **exactamente el mismo conteo** que en F0.1 puntos 13 y 14, y `test_fable_sigue_fuera_del_catalogo_y_de_la_allowlist` en verde.
7. **La flag nueva está viva en sus patas reales:** `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py`, `tests/test_flags_env_read_meta.py` y `tests/test_harness_flags_bounds.py` **verdes**; `tests/test_harness_flags_help.py` con **exactamente** las mismas fallidas de F0.1. **Y `cuenta_viva_con_la_sonda_apagada` en verde**, que es lo que prueba que la flag es independiente.
8. **K7 = 4** — `plan288AvisoMontado.test.ts` en verde: el aviso está en los 4 archivos por nombre y **no** en `ModelDecisionChip.tsx`.
9. **K9** — `modelCatalogRefresh.test.ts` con **6 passed** y el paso 9 del smoke confirmado.
10. **Los DOS ratchets del arnés en verde**, con las 2 rutas nuevas en los dos scripts y **ninguna** en el allowlist (que sigue en 194 ≤ 197).
11. **Paridad de motores probada:** los bloques `codex_cli` y `github_copilot` idénticos con la flag encendida y apagada y **sin la clave `cuenta`**, **y** el bloque `claude_code_cli` distinto (la contra-prueba).
12. **`npx tsc --noEmit` en 0 errores**, **`npx vite build` sin error**, y los **once** ratchets de pantalla de §6.F9 en verde (o en su delta declarado).
13. **La huella está en `docs/sistema/error_fingerprints.json`** y `tests/test_error_fingerprints_catalog.py` no sumó ni una fallida respecto de F0.1 punto 16.
14. **Los 17 comandos de F0.1 vueltos a correr, con la salida literal pegada en el registro de implementación.** "Todo pasa" **no es evidencia**.
15. **Trabajo del operador: ninguno.** La única flag nueva nace **ON**; nada exige configuración; el smoke visual es opcional.
