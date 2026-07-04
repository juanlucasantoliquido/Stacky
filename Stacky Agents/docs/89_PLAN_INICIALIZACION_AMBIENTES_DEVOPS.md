# Plan 89 — Inicialización de ambientes desde el panel DevOps

**Estado:** PROPUESTO
**Versión:** v2 → v3 (2ª crítica adversarial `criticar-y-mejorar-plan` — foco:
usabilidad end-to-end + escalabilidad del panel, 2026-07-04)
**Fecha:** 2026-07-03 (v1) / 2026-07-04 (v2) / 2026-07-04 (v3)
**Serie DevOps:** plan 3 de 3 (CIERRE de la serie).
**Dependencias:** plan 88 **en su versión v3** (`88_PLAN_PUBLICACIONES_PARAMETRIZABLES_PROCESOS_DEVOPS.md`,
commit `d5ced3e6` — publicaciones; provee la "publicación inicial TODO", el helper
`mergeKeysIntoProfile` + `draftNameForPreset` y el fixture de resolución congelado),
que a su vez depende del plan 87 **en su versión v3**
(`87_PLAN_PANEL_DEVOPS_CREADOR_GRAFICO_PIPELINES.md`, commit `f3d2234d` — panel
DevOps base; contrato de extensión §3.12/C20: registro DECLARATIVO con
`healthKey`/`gateFlagKey`/`gateMessage` + `render(ctx)`, gate renderizado por el
SHELL con `FlagGateBanner`, montaje persistente, namespacing heredable). Las
versiones previas (`59918622`/`a001e544` v1; `e533c283`/`6a233e67` v2) quedaron
SUPERADAS: este doc fue reescrito contra los contratos v3. Este plan CUMPLE el
namespacing del §3.12: flag `STACKY_DEVOPS_ENVIRONMENTS_ENABLED`, health
`environments_enabled`, rutas `/api/devops/environments/*`, key
`devops_environment_settings`. Además, planes 45/71/72/73 implementados —
VERIFICADO:

| Pieza reusada | Origen |
|---|---|
| `DevOpsPage` + `DEVOPS_SECTIONS` DECLARATIVO (`id/label/icon?/healthKey?/gateFlagKey?/gateMessage?/render(ctx)`), gate en el SHELL, montaje persistente | plan 87 **v3** F4 (§3.12/C20) |
| `FlagGateBanner` (aviso en llano + "Activar ahora" vía `HarnessFlags.update`) | plan 87 v3 F4/F5.0 (`frontend/src/components/devops/FlagGateBanner.tsx`) |
| `DevOpsHealth` con index signature — keys aditivas (`publications_enabled?`, y acá `environments_enabled?`) sin tocar el shell | plan 87 v3 F4 / 88 v3 F5 |
| Blueprint `backend/api/devops.py` + health con booleans por sub-feature | plan 87 v3 F1 / 88 v3 F3 |
| Materializador puro `build_publication_spec` (`services/publication_spec.py`) — semántica congelada por `tests/fixtures/plan88_resolution_cases.json` | plan 88 v3 F1 |
| Endpoint materialize: `api.post("/api/devops/publications/materialize", {project, preset_name})` | plan 88 v3 F3/F4 |
| Helper puro `mergeKeysIntoProfile` (riel GET→merge→PUT) en `frontend/src/devops/presetsModel.ts` | plan 88 v3 F4 |
| Modelo en client_profile: `devops_publication_presets` (name único, ≤120, cap 50), `devops_publication_settings`, `publish_group` | plan 88 v3 §4 |
| `ALLOWED_PROCESS_KINDS = {"entry","processing","output"}` | `backend/api/client_profile.py:57` |
| Preview/commit YAML HITL | `backend/api/pipeline_generator.py:34,52,59-60` (plan 73) |
| Trigger/monitor CI HITL | `backend/api/ci.py:26,76,139,174` (plan 72) |
| PUT client_profile con validación aditiva por key — **el PUT REEMPLAZA el profile completo** | `backend/api/client_profile.py:127,138-156,161` (plan 45; riel C2) |
| vitest instalado como devDependency | plan 87 v3 **F3.0** (NO re-instalar; correr SIEMPRE por archivo) |
| FlagSpec: `label` y `group` son campos REQUERIDOS | `backend/services/harness_flags.py:21-33` |

> **Nota de secuencia:** implementar 87 v3 → 88 v3 → 89 v3. Las fases F0-F2 de este
> plan no tocan código de 87/88 y pueden adelantarse; F3-F5 requieren 87 v3 F1/F4 y
> 88 v3 F1/F3/F4.
>
> **Declaración de no-contacto (patrón 88 v2 C13):** este plan NO agrega campos a
> `PipelineSpec` ⇒ el centinela `test_f1_spec_shape_frozen` (87 v3) y los tipos TS
> espejo (`specBuilder.ts`) quedan INTACTOS. Tampoco toca
> `tests/fixtures/plan88_resolution_cases.json` ni reimplementa la semántica de
> resolución del 88: la publicación inicial se COMPONE vía el endpoint materialize.

## CHANGELOG v2 → v3 (foco: feature LISTA PARA USAR + panel escalable)

- **C17 (IMPORTANTE, resuelto):** gating HAND-ROLLED contra el contrato del panel:
  F5 v2 reemplazaba la sección por un mensaje propio si
  `ctx.health.environments_enabled !== true` (patrón MigratorPage) y el banner del
  Paso 2 era texto plano. El 87 v3 (§3.12/C20) fija el gate DECLARATIVO en el
  registro (el SHELL renderiza `FlagGateBanner` con "Activar ahora"). v3: la entrada
  de `DEVOPS_SECTIONS` declara `healthKey/gateFlagKey/gateMessage`; la sección no
  contiene ningún aviso propio de SU flag; el banner del Paso 2 (dependencia del 88)
  pasa a ser `FlagGateBanner` con `flagKey="STACKY_DEVOPS_PUBLICATIONS_ENABLED"`
  (gate de sub-feature DENTRO de la sección, mismo patrón que generator/trigger en
  el 87). Dependencias re-ancladas: 87 v3 (`f3d2234d`) y 88 v3 (`d5ced3e6`).
- **C18 (IMPORTANTE, resuelto):** primera vez sin guía: el wizard no definía qué
  pasa sin `devops_environment_settings` guardados (el operador podía "Calcular
  plan" sin raíz configurada y comerse un 400 crudo). v3: stepper visual con estado
  por paso (Configuración / Carpetas / Publicación inicial); sin settings guardados,
  el Paso 0 se abre pre-poblado con `emptyEnvironmentSettings()` (layout Pacífico
  editable) + CTA "Configurá la raíz del ambiente para empezar" + botón "Usar
  layout de ejemplo"; "Calcular plan" queda `disabled` hasta que haya settings
  guardados con root válido, con hint que apunta al Paso 0. Happy path ≤ 4 clicks
  (criterio binario F6).
- **C19 (IMPORTANTE, resuelto):** errores async sin camino garantizado a la UI
  (paridad 87 v3 C16 / 88 v3 C17): la v2 especificaba mensajes para 409/failed/
  ignored pero no el catch GENÉRICO (red caída, 500 inesperado, 400 del PUT fuera
  del flujo feliz). v3: TODA llamada async de la sección va en try/catch hacia
  `actionError` visible en un área fija; prohibido `console.*` como único destino.
- **C20 (MENOR, resuelto):** la nota de F0 sobre agregar las líneas de
  harness_defaults.env de 87/88 "si faltan" quedó obsoleta: el 87 v3 (C13) y el 88
  (C8) ya poseen las suyas. v3 la reduce a salvaguarda por orden de implementación.
- **C21 (MENOR, resuelto):** referencias de versión stale (87 v2 F3.0, "montada
  como sección del 87 v2", tabla de reuso) re-ancladas a los contratos v3; tabla
  amplia con `FlagGateBanner` y el registro declarativo.
- **C22 (MENOR, resuelto):** F6 sin criterios binarios de usabilidad (paridad 87 v3
  C19 / 88 v3 C21). v3 agrega el bloque de usabilidad + escalabilidad al checklist.
- **[ADICIÓN ARQUITECTO v3] Verificación automática post-apply:** tras un apply
  exitoso, la UI re-llama `/plan` automáticamente y muestra el badge binario
  **"Ambiente verificado: N carpetas existentes, 0 pendientes"** (todas las entries
  en `exists_ok`) o, si queda algo (`to_create`/`conflict`/`unsafe`/`failed`), un
  panel rojo con la lista exacta. Convierte la idempotencia (que ya estaba testeada
  en backend) en EVIDENCIA visible para el operador: el HITL no termina en "click y
  fe", termina en verificación en disco. Costo: 1 llamada extra al endpoint de PLAN
  ya existente (solo-lectura), helper puro `allExistsOk(entries)` + 1 test vitest;
  cero backend nuevo.

## CHANGELOG v1 → v2

- **C1 (BLOQUEANTE, resuelto):** F5 v1 registraba la sección con
  `render: () => <EnvironmentsSection />` — contrato del 87 **v1**, muerto. El contrato
  vigente (87 v2 C4/C9) es `render: (ctx: DevOpsSectionContext) => ReactNode`. Además
  v1 leía "health" sin decir de dónde. v2 fija literal:
  `render: (ctx) => <EnvironmentsSection ctx={ctx} />`, los booleans se leen de
  `ctx.health`, y `DevOpsHealth` se amplía ADITIVAMENTE con la key OPCIONAL
  `environments_enabled?: boolean`.
- **C2 (BLOQUEANTE, resuelto):** F5 v1 persistía `devops_environment_settings` "vía PUT
  client-profile (patrón presets plan 88 F5)" — referencia al 88 **v1**, cuyo flujo de
  guardado era justamente el bug que el 88 v2 C2 corrigió: `put_client_profile`
  REEMPLAZA el profile completo (`api/client_profile.py:161`); un modelo menor habría
  PUTeado solo `{"devops_environment_settings": {...}}` y BORRADO `process_catalog`,
  presets y el resto de la config del operador. Ídem el "Crear preset TODO" del Paso 2
  (upsert + PUT sin riel). v2 impone el riel **GET → merge → PUT** (§3.9) con el helper
  `mergeKeysIntoProfile` del 88 v2 F4 (importado, NO duplicado) y flujo literal en F5.
- **C3 (IMPORTANTE, resuelto):** el snippet `FlagSpec` de F0 v1 omitía `label` y
  `group`, campos REQUERIDOS del dataclass (`harness_flags.py:21-33`) ⇒ TypeError al
  importar. Tercera repetición del mismo C3 (87 v1, 88 v1). v2 trae el snippet completo.
- **C4 (IMPORTANTE, resuelto):** faltaba la pata de deploy de la flag:
  `backend/harness_defaults.env` + test dedicado (causa raíz RECURRENTE, planes 74/75;
  ya corregida en 88 v2 C8). v2: F0 agrega la línea
  `STACKY_DEVOPS_ENVIRONMENTS_ENABLED=false` + `test_f0_harness_defaults_contains_flag`.
- **C5 (IMPORTANTE, resuelto):** el encabezado v1 citaba las dependencias por los
  commits **v1** (87 `59918622`, 88 `a001e544`) y sus contratos ya superados. v2
  re-ancla a 87 v2 (`e533c283`) y 88 v2 (`6a233e67`) y actualiza la tabla de reuso
  (mergeKeysIntoProfile, materialize, render(ctx), vitest F3.0).
- **C6 (IMPORTANTE, resuelto):** defensas Windows INCOMPLETAS en `_safe_segment`/plan:
  no rechazaba caracteres inválidos (`< > " | ? *`, controles), ni nombres reservados
  (CON, PRN, AUX, NUL, COM1..COM9, LPT1..LPT9), ni segmentos terminados en `.`/espacio,
  ni paths >260 chars, ni dedup case-insensitive (en Windows `IN_` y `in_` son la MISMA
  carpeta), ni symlinks (el check con `abspath` NO resuelve symlinks: un dir enlazado
  dentro de root puede redirigir la creación FUERA de root). v2: `is_safe_segment`
  endurecido + containment por `os.path.realpath` + límite de longitud + dedup
  `casefold()` + tests dedicados (F1/F2/F3).
- **C7 (IMPORTANTE, resuelto):** `apply_environment` v1 no manejaba fallos de
  `os.makedirs` (root en drive inexistente, sin permisos, path largo) ⇒ excepción ⇒
  500 con creación A MEDIAS y sin reporte. v2: try/except OSError POR ruta, se sigue
  con las demás, respuesta incluye `failed: [{path, error}]`, nunca 500 + test con
  monkeypatch.
- **C8 (IMPORTANTE, resuelto — ver también ADICIÓN):** plan dry-run STALE: si el
  catálogo/settings cambian entre el plan y el apply, la v1 re-derivaba server-side e
  ignoraba EN SILENCIO los paths pedidos que ya no están en el layout — el operador
  confirmaba N carpetas y se creaban M sin explicación (rompe la honestidad del HITL).
  v2: fingerprint obligatorio del plan (409 `plan_stale` si no coincide) + campo
  `ignored_not_in_layout` visible en la respuesta.
- **C9 (IMPORTANTE, resuelto):** `test_f1_traversal_process_name_sanitized` v1 era
  internamente contradictorio: el slug regex `[^a-zA-Z0-9._-]+ → "-"` PRESERVA los
  puntos, así que `_slug("../../evil") == "..-..-evil"` — contiene `".."` y el assert
  "ningún path contiene `..`" habría fallado SIEMPRE. v2: `_slug` colapsa secuencias de
  puntos y recorta bordes (`"../../evil"` → `"evil"`), y el test afirma ambas cosas:
  ningún componente igual a `".."` y ningún `".."` como substring.
- **C10 (IMPORTANTE, resuelto):** `build_environment_layout` v1 prometía "nunca lanza"
  pero iteraba `entry.get("kind")` sin chequear que la entrada sea dict ⇒
  AttributeError con un catálogo editado a mano (misma clase C5 del 88 v2). v2:
  entradas no-dict se OMITEN + `test_f1_non_dict_entries_ignored`.
- **C11 (MENOR, resuelto):** el snippet de `endpoints.ts` en F5 v1 describía los paths
  sin `/api` y daba DOS descripciones contradictorias de `confirm` (auto-inyectado vs
  argumento). v2: snippet literal con `api.post("/api/devops/environments/...")` y
  firma única `environmentApply(project, paths, confirm, fingerprint)`.
- **C12 (MENOR, resuelto):** F3 v1 importaba `_safe_segment` (privado, underscore)
  desde `api/client_profile.py`. v2 lo renombra público: `is_safe_segment`.
- **C13 (MENOR, resuelto):** el centinela anti-destrucción no incluía `"rename"`
  (`os.rename`/`os.renames`/`Path.rename` quedaban permitidos). v2 lo agrega a la
  lista prohibida.
- **C14 (MENOR, resuelto):** faltaba declarar el no-contacto con el contrato congelado
  de la serie: `PipelineSpec`/`test_f1_spec_shape_frozen` intactos y
  `plan88_resolution_cases.json` intocado (bloque agregado al encabezado).
- **C15 (MENOR, resuelto):** root INEXISTENTE: `os.makedirs` crea intermedios, así que
  un typo en `environment_root` crearía el árbol entero en el lugar equivocado sin
  aviso. v2: el plan responde `root_exists: bool` y la UI muestra el warning literal
  "La raíz no existe: se creará completa al aplicar. Verificá la ruta."
- **C16 (MENOR, resuelto):** el preámbulo de comandos no anclaba vitest: v2 declara que
  vitest viene instalado por el 87 v2 **F3.0** (NO re-instalar) y que se corre SIEMPRE
  por archivo (nunca `npx vitest run` a secas — colectaría los `.tsx` huérfanos de
  `src/components/__tests__/`).
- **[ADICIÓN ARQUITECTO] Fingerprint de plan (integridad dry-run → apply):** el
  plan-then-apply v1 no tenía integridad verificable entre lo que el operador VIO y lo
  que se APLICA. v2 agrega `layout_fingerprint` (sha256 de root normalizado + rutas
  relativas ordenadas, helper puro sin I/O): `/plan` lo devuelve, `/apply` lo EXIGE en
  el body y responde **409 `plan_stale`** si el layout re-derivado ya no coincide (el
  catálogo o los settings cambiaron entre medio). El checkbox HITL pasa a confirmar un
  plan CONCRETO e inmutable, no "lo que haya en ese momento". Cero costo para el
  operador (la UI lo pasa sola), puro y testeable, y convierte el caso borde más
  traicionero del plan (stale) en un error explícito y recuperable ("Recalculá el
  plan"). Complemento: `ignored_not_in_layout` en la respuesta del apply hace visible
  cualquier path pedido que el server descartó.

---

## 1. Objetivo + KPI

Inicializar un **ambiente nuevo** desde el panel DevOps en dos partes: **(a)** crear el
**sistema de carpetas** que los procesos del cliente necesitan — estructura DERIVADA
del process_catalog parametrizado (jamás hardcodeada): en Pacífico, las carpetas de
entrada `IN_` (donde deja Mul2Bane), `productivas` (donde pasa IncHost / aplica RSCore)
y `salida` (donde genera RsExtrae) — con mapeo `kind → subcarpetas` parametrizable por
UI; y **(b)** disparar la **publicación inicial** de lo parametrizado como "TODO",
reusando el materializador del plan 88 v2 SIN duplicar una línea. Regla de oro:
**IDEMPOTENTE Y NUNCA DESTRUCTIVO** — re-inicializar un ambiente existente detecta y
reporta, jamás borra ni sobrescribe (plan-then-apply con HITL y fingerprint).

**KPI / impacto esperado** (aspiracional; los criterios binarios están en F6):
- Ambiente nuevo operativo (carpetas + publicación inicial previewada) en < 5 minutos
  desde la UI, 0 comandos manuales de mkdir, 0 YAML a mano.
- Re-inicializar un ambiente ya inicializado ⇒ **0 cambios en disco** (todo
  `exists_ok`) con reporte visible — criterio binario F2.
- Cero caminos de código capaces de borrar: verificado por test centinela
  anti-destrucción (F2).
- El apply NUNCA ejecuta un plan distinto del que el operador confirmó (fingerprint,
  criterio binario F4).

## 2. Por qué ahora / gap que cierra

Con 87 (crear pipelines gráficamente) y 88 (publicar procesos parametrizados) el panel
DevOps cubre el día 2 en adelante. El día 0 — montar un ambiente nuevo: carpetas del
flujo batch + primera publicación completa — sigue siendo manual, propenso a error
(carpeta faltante ⇒ el batch falla en runtime) y sin trazabilidad. Este plan cierra la
serie: el catálogo de procesos (plan 45) ya sabe QUÉ existe y de QUÉ kind es; de ahí se
DERIVA el layout de carpetas, y la publicación inicial es literalmente el preset TODO
del plan 88. Todo el conocimiento ya está en Stacky; solo falta el ejecutor no
destructivo.

## 3. Principios y guardarraíles (NO negociables)

1. **Human-in-the-loop en dos escalones + integridad:** primero el operador VE el plan
   de carpetas (dry-run puro, endpoint de PLAN solo-lectura); recién con confirmación
   explícita (`confirm:true`) Y el `fingerprint` del plan visto (ADICIÓN) se aplica
   SOLO lo aprobado; si el layout cambió entre medio ⇒ 409 `plan_stale`, nada se toca.
   La publicación inicial pasa por los MISMOS HITL de los planes 88/73/72
   (materializar solo-lectura → commit con checkbox → trigger con preview).
2. **Nunca destructivo:** ningún camino de código de este plan borra, renombra ni
   sobrescribe NADA. Prohibidos `shutil.rmtree`, `os.rmdir`, `os.remove`, `os.unlink`,
   `os.replace`, `os.rename` (y variantes), `shutil.move` y toda escritura de archivos
   en el módulo de inicialización. Hay test centinela que lo verifica sobre el código
   fuente (F2, lista C13). `conflict` (existe un ARCHIVO donde va una carpeta) se
   REPORTA, jamás se toca.
3. **Dónde se crean las carpetas — decisión justificada:** en la **máquina del
   operador** (filesystem local del backend). Justificación: Stacky es mono-operador y
   el backend corre local en esa máquina (riel del sistema); los ambientes batch del
   dominio son rutas de disco visibles para el operador. La raíz es parametrizada por
   el operador (`environment_root`), validada: **ruta absoluta** y **NO raíz de disco**
   (ni `C:\` ni `/`).
4. **Anti path-traversal y anti-escape (defensa en 4 capas, C6):** (a) los nombres de
   proceso se sanitizan a slug endurecido (F1: colapsa `..`, sin reservados Windows);
   (b) los segmentos del layout pasan `is_safe_segment` (F1/F3: relativos, sin `..`,
   sin `: < > " | ? *` ni controles, sin reservados CON..LPT9, sin terminar en `.` o
   espacio); (c) containment con **realpath**: toda ruta final se verifica
   `os.path.commonpath([realpath(root), realpath(final)]) == realpath(root)` — resuelve
   symlinks del tramo existente (un dir enlazado no puede redirigir fuera de root);
   (d) límite de longitud total (>240 chars ⇒ `unsafe`, margen bajo MAX_PATH=260).
5. **Flag propia** `STACKY_DEVOPS_ENVIRONMENTS_ENABLED`: `FLAG_REGISTRY` con
   `requires="STACKY_DEVOPS_PANEL_ENABLED"` (nota: `requires` acepta UNA key bool,
   plan 82 `harness_flags.py:30` — la dependencia funcional del plan 88 se declara acá
   y en la UI por mensaje, NO en `requires`), categoría `devops`, `env_only=False` ⇒
   alta en `config.py` (gotcha plan 81), **SIN `default=`** (gotcha
   `_CURATED_DEFAULTS_ON`), **CON `label` y `group`** (campos requeridos, C3), **con
   `PlainHelp`** (meta-test plan 86) **y con su línea en `backend/harness_defaults.env`**
   (pata de deploy, C4).
6. **Byte-idéntico con flag OFF:** endpoints nuevos 404, sección UI ausente,
   validaciones aditivas inertes.
7. **Mono-operador sin auth. No degradar:** contratos 45/71/72/73/87/88 intactos;
   todo aditivo; `PipelineSpec` y `plan88_resolution_cases.json` INTOCADOS (C14).
   **Ratchet:** tests nuevos registrados en `backend/scripts/run_harness_tests.{sh,ps1}`.
8. **3 runtimes (Codex/Claude/Copilot):** no toca el camino de agentes; impacto
   NINGUNO en los tres (se declara por fase).
9. **NUNCA PUTear un client_profile parcial (C2 — riel §3.9 del 88 v2 / §3.10 del 87
   v2):** `put_client_profile` REEMPLAZA el profile completo
   (`api/client_profile.py:161`). TODO guardado desde la UI de este plan
   (`devops_environment_settings`, y el preset TODO del Paso 2) hace **GET del profile
   actual → merge en memoria (`mergeKeysIntoProfile`, helper del 88 v2 F4, importado de
   `presetsModel.ts`, NO duplicado) → PUT del profile completo**. Prohibido enviar
   `{"devops_environment_settings": {...}}` solo: borraría `process_catalog`, presets
   y el resto de la config del operador.

## 4. Modelo de datos (contrato, consumido por F1-F5)

Key NUEVA en client_profile (patrón plan 45/87/88):

```json
"devops_environment_settings": {
  "environment_root": "C:\\ambientes\\pacifico",   // absoluta, NO raíz de disco
  "folder_layout": {                                 // kind → subcarpetas relativas
    "entry":      ["IN_"],
    "processing": ["productivas"],
    "output":     ["salida"],
    "default":    []                                  // kinds desconocidos/ausentes
  },
  "per_process_subfolder": false                     // true ⇒ además <carpeta>/<slug-proceso>
}
```

**Semántica del layout (F1, determinista):**
- Entradas del catálogo que NO sean dict se IGNORAN silenciosamente (C10; misma
  tolerancia que el 88 v2 C5 con catálogos editados a mano).
- Para cada entrada dict con kind `k`: aporta las carpetas de `folder_layout[k]`
  (si `k` no está en el layout ⇒ `folder_layout["default"]`).
- Si `per_process_subfolder == true`: además aporta `carpeta/<slug(name)>` por cada
  proceso (slug endurecido del §3.4/F1; entradas sin `name` string no vacío se ignoran).
- Resultado: lista de rutas RELATIVAS, únicas (dedup **case-insensitive por
  `casefold()`**, C6 — en Windows `IN_` y `in_` son la misma carpeta; gana la primera
  en orden `sorted`), ordenadas (`sorted`), sin separador inicial/final, separador
  interno SIEMPRE `/`. Segmentos inválidos en el layout NO llegan acá: los rechaza la
  validación F3 al guardar; el builder además los OMITE defensivamente (nunca lanza).
- Catálogo vacío o layout todo vacío ⇒ lista vacía (el plan resultante reporta 0
  entradas; la UI lo muestra, no es error).

**Estados del plan de carpetas (F2):** para cada ruta relativa `p` con final
`f = abspath(join(root, p))`:
- `to_create` — `f` no existe.
- `exists_ok` — `f` existe y es directorio.
- `conflict` — `f` existe y NO es directorio (archivo): se reporta, NUNCA se toca.
- `unsafe` — falló el containment por realpath (§3.4c), o `len(f) > 240` (§3.4d): se
  reporta con `reason` (`"fuera_de_root"` | `"path_demasiado_largo"`), NUNCA se crea.

**Respuesta de `/plan` (contrato F2/F4):**
```json
{
  "root": "C:\\ambientes\\pacifico",
  "root_exists": true,
  "layout_fingerprint": "<sha256 hex>",
  "entries": [{"path": "IN_", "status": "to_create", "reason": null}],
  "summary": {"to_create": 1, "exists_ok": 0, "conflict": 0, "unsafe": 0}
}
```

**Respuesta de `/apply` (contrato F2/F4):**
```json
{
  "created": ["IN_"], "skipped_existing": [], "conflicts": [], "unsafe": [],
  "failed": [],                       // [{"path": rel, "error": str}] — C7, nunca 500
  "ignored_not_in_layout": []          // paths pedidos que el server descartó — C8
}
```

## 5. Fases

> Comandos de test: idénticos a planes 87 v2 / 88 v2 — backend pytest POR ARCHIVO con
> `backend/.venv/Scripts/python.exe` desde `Stacky Agents/backend`; frontend
> `npx tsc --noEmit` + `npx vitest run <archivo>` en `Stacky Agents/frontend`.
> vitest queda instalado por el **87 v3 F3.0** (C16): NO re-instalarlo y NUNCA correr
> `npx vitest run` sin archivo (colectaría los `.tsx` huérfanos de
> `src/components/__tests__/` que importan `@testing-library/react` inexistente).

### F0 — Flag `STACKY_DEVOPS_ENVIRONMENTS_ENABLED`

**Objetivo:** alta de la flag en las 4 patas + la pata de deploy (C4), colgada de la
del panel (misma mecánica que 87 v2 F0 / 88 v2 F0).

**Archivos a editar:**
1. `Stacky Agents/backend/config.py` — junto a las flags devops de 87/88:
   ```python
   STACKY_DEVOPS_ENVIRONMENTS_ENABLED: bool = os.getenv(
       "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", "false"
   ).strip().lower() == "true"
   ```
2. `Stacky Agents/backend/services/harness_flags.py`:
   - `_CATEGORY_KEYS["devops"]` += `"STACKY_DEVOPS_ENVIRONMENTS_ENABLED",  # Plan 89 — inicialización de ambientes`.
   - `FlagSpec` nuevo junto a los de 87/88. Snippet COMPLETO (C3: `label` y `group`
     son campos REQUERIDOS del dataclass, `harness_flags.py:21-33`):
     ```python
     FlagSpec(
         key="STACKY_DEVOPS_ENVIRONMENTS_ENABLED",
         type="bool",
         label="Ambientes DevOps (Plan 89)",
         description=(
             "Plan 89 — Seccion Ambientes del panel DevOps: crea el arbol de "
             "carpetas del ambiente derivado del catalogo (plan-then-apply con "
             "confirmacion, NUNCA borra ni sobrescribe) y lanza la publicacion "
             "inicial reusando el plan 88. Default OFF. Con OFF los endpoints "
             "/api/devops/environments/* dan 404 y la seccion no aparece."
         ),
         group="global",  # mismo group que STACKY_DEVOPS_PANEL_ENABLED (87 v2 F0)
         env_only=False,  # editable por UI (categoría 'devops')
         requires="STACKY_DEVOPS_PANEL_ENABLED",  # Plan 82 — declarativo, informa en UI
     )
     ```
     ⚠️ SIN `default=`, SIN `reserved=` (consumidor real en F4).
3. `Stacky Agents/backend/services/harness_flags_help.py` — entrada `PlainHelp`
   (modelo: la de `STACKY_PIPELINE_GENERATOR_ENABLED`, línea 595; mencionar en llano:
   "solo crea carpetas nuevas, nunca borra nada").
4. **(C4)** `Stacky Agents/backend/harness_defaults.env`: agregar la línea
   `STACKY_DEVOPS_ENVIRONMENTS_ENABLED=false` (pata de deploy; snapshot horneado en
   `backend\.env` en cada release; mantener orden alfabético). Nota v3 (C20): el 87
   v3 (C13) y el 88 (C8) ya agregan sus propias líneas en sus F0; si por orden de
   implementación aún faltaran, agregarlas en el mismo commit.

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan89_environments_flag.py`:
- `test_f0_flag_in_registry` (`env_only is False`,
  `requires == "STACKY_DEVOPS_PANEL_ENABLED"`, `group == "global"`, `label` no vacío),
  `test_f0_flag_in_category_devops`,
  `test_f0_config_default_off` (patrón inmune al env del runner, 87 v2 C8:
  `monkeypatch.delenv` + `importlib.reload(config)`),
  `test_f0_flag_has_plain_help`,
  `test_f0_harness_defaults_contains_flag` (C4: el archivo contiene el literal
  `STACKY_DEVOPS_ENVIRONMENTS_ENABLED=false`; patrón
  `tests/test_plan75_deep_links_wiring.py:50-58`).
- No-regresión: `tests/test_harness_flags.py` + `tests/test_flag_wiring.py`.

**Ratchet:** registrar el archivo. **Criterio binario:** 5+2 verdes; default OFF.
**Flag:** `STACKY_DEVOPS_ENVIRONMENTS_ENABLED` (default OFF).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno (opt-in).

### F1 — Layout PURO: `build_environment_layout` (catálogo → rutas relativas)

**Objetivo:** derivar determinísticamente el árbol de carpetas del catálogo, sin I/O,
con sanitización endurecida para Windows (C6/C9/C10).

**Archivo NUEVO:** `Stacky Agents/backend/services/environment_init.py`
```python
"""environment_init.py — Plan 89. Inicialización de ambientes.
build_environment_layout / layout_fingerprint: PUROS (sin I/O).
plan_environment: solo LECTURA de FS.
apply_environment: SOLO os.makedirs (nunca borra; ver test centinela F2)."""
import hashlib
import os
import re

_LAYOUT_KINDS = ("entry", "processing", "output", "default")
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_INVALID_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')

def _slug(name: str) -> str:
    """Slug endurecido (C9). Base: regex de api/pipeline_generator.py:27-31 (copiado,
    no importado) + colapso de puntos (sin '..') + guard de reservados Windows."""
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "").strip().lower())
    s = re.sub(r"\.\.+", ".", s).strip("-.")      # '../../evil' -> 'evil'
    if s.split(".")[0] in _WINDOWS_RESERVED:      # 'con' -> 'p-con'
        s = "p-" + s
    return s or "proceso"

def is_safe_segment(seg: str) -> bool:
    """Segmento relativo seguro (C6, público — lo importa api/client_profile.py F3).
    Reglas por COMPONENTE (split en / y \\): no vacío, != '..', sin '..' como
    substring, sin caracteres inválidos Windows (<>:"|?* y controles), no reservado
    (CON..LPT9, con o sin extensión), no termina en '.' ni espacio. Además el
    segmento completo: no absoluto, no arranca con separador."""
    seg = (seg or "").strip()
    if not seg or os.path.isabs(seg) or seg.startswith(("/", "\\")):
        return False
    for comp in re.split(r"[\\/]+", seg):
        if (not comp or ".." in comp or _INVALID_CHARS.search(comp)
                or comp.split(".")[0].lower() in _WINDOWS_RESERVED
                or comp.endswith((".", " "))):
            return False
    return True

def build_environment_layout(catalog: list[dict], settings: dict | None) -> list[str]:
    """Rutas RELATIVAS únicas y ordenadas según §4. Nunca lanza; omite lo inválido
    (entradas no-dict del catálogo incluidas, C10). settings None o sin
    folder_layout -> []. Separador interno SIEMPRE '/'. Dedup case-insensitive por
    casefold() preservando la primera en orden sorted (C6)."""

def layout_fingerprint(root: str, rel_paths: list[str]) -> str:
    """ADICIÓN — sha256 hex de abspath(root) + '\\n' + '\\n'.join(rel_paths).
    PURO (sin I/O). Identifica un plan concreto para el handshake plan->apply."""
```
(Implementación de `build_environment_layout`: iterar catálogo; `continue` si la
entrada no es dict; por entrada tomar
`folder_layout.get(kind, folder_layout.get("default", []))`; filtrar con
`is_safe_segment`; si `per_process_subfolder` ⇒ agregar `f"{seg}/{_slug(name)}"` solo
si `name` es string no vacío; luego `out = sorted(set(acc))` y dedup final:
`seen = set(); [p for p in out if not (p.casefold() in seen or seen.add(p.casefold()))]`.)

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan89_environment_layout.py`
(reusar el array `catalog` de `tests/fixtures/plan88_resolution_cases.json` como
fixture local — SOLO lectura, jamás modificarlo — + settings §4):
- `test_f1_pacifico_layout_basic`: settings §4 con `per_process_subfolder=false` ⇒
  `["IN_", "productivas", "salida"]` (orden `sorted`, dedup aunque haya 2 processing).
- `test_f1_per_process_subfolders`: `per_process_subfolder=true` ⇒ incluye
  `"IN_/mul2bane"`, `"productivas/inchost"`, `"productivas/rscore"`,
  `"salida/rsextrae"` además de las 3 bases.
- `test_f1_unknown_kind_uses_default`: entrada `kind="zzz"` con
  `default=["misc"]` ⇒ aporta `"misc"`.
- `test_f1_empty_settings_empty`: settings `None` ⇒ `[]`; `folder_layout` ausente ⇒ `[]`.
- `test_f1_unsafe_segments_omitted`: layout con `["../fuga", "C:\\abs", "ok"]` ⇒ solo
  `"ok"` aparece.
- `test_f1_traversal_process_name_sanitized` (C9): entrada `name="../../evil"`,
  `per_process_subfolder=true` ⇒ resultado contiene `"IN_/evil"`; assert doble:
  ningún path del resultado contiene `".."` como substring Y ningún componente
  (split por `/`) es igual a `".."`.
- `test_f1_non_dict_entries_ignored` (C10): catálogo `["basura", 42, {...válida...}]`
  ⇒ solo la válida aporta; nada lanza.
- `test_f1_windows_invalid_chars_omitted` (C6): layout `{"entry": ["IN|X", "ok"]}` ⇒
  solo `"ok"`; ídem con `"aux"` y `"carpeta."` (termina en punto) omitidos.
- `test_f1_reserved_names_omitted` (C6): layout con `["CON", "lpt1", "normal"]` ⇒ solo
  `"normal"`; y proceso `name="CON"` con per_process ⇒ slug `"p-con"` (no `"con"`).
- `test_f1_case_insensitive_dedup` (C6): layout `{"entry": ["IN_"], "output": ["in_"]}`
  ⇒ UNA sola entrada en el resultado (gana `"IN_"`, primera en sorted... verificar con
  el assert `len(result) == 1`).
- `test_f1_deterministic_and_pure`: dos llamadas con los mismos argumentos devuelven
  listas iguales; catálogo y settings de entrada no mutados (deepcopy previo); y
  `layout_fingerprint(root, paths)` es estable para los mismos argumentos y CAMBIA si
  cambia un path o el root.

**Ratchet:** registrar. **Criterio binario:** 11 tests verdes.
**Flag:** ninguna (puro, sin consumidores hasta F4). **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F2 — Plan-then-apply NO destructivo (`plan_environment` / `apply_environment`)

**Objetivo:** clasificar rutas (dry-run) y crear SOLO lo aprobado, sin capacidad
técnica de borrar, sin 500 ante fallos parciales (C7), con containment por realpath (C6).

**Archivo a editar:** `Stacky Agents/backend/services/environment_init.py` (agregar):
```python
def validate_root(root: str) -> str | None:
    """None si OK; mensaje de error si no. Reglas: string no vacío, os.path.isabs,
    y NO raíz de disco: normpath(root) != normpath(splitdrive(root)[0] + os.sep)
    (cubre 'C:\\' en Windows y '/' en POSIX)."""

def plan_environment(root: str, rel_paths: list[str]) -> dict:
    """SOLO LECTURA. Retorna el contrato §4:
    {'root', 'root_exists': os.path.isdir(root),                  # C15
     'layout_fingerprint': layout_fingerprint(root, rel_paths),   # ADICIÓN
     'entries': [{'path', 'status', 'reason'}], 'summary': {...}}
    Por cada rel: final = os.path.abspath(os.path.join(root, rel)).
    'unsafe' reason='fuera_de_root' si
      os.path.commonpath([os.path.realpath(os.path.abspath(root)),
                          os.path.realpath(final)]) != os.path.realpath(os.path.abspath(root))
      (realpath resuelve symlinks del tramo EXISTENTE — C6; ValueError de commonpath
      — drives distintos — también es unsafe).
    'unsafe' reason='path_demasiado_largo' si len(final) > 240 (C6, margen MAX_PATH).
    'to_create' si not os.path.exists(final); 'exists_ok' si os.path.isdir(final);
    'conflict' en el resto (existe y no es dir); reason=None salvo unsafe."""

def apply_environment(root: str, rel_paths: list[str]) -> dict:
    """CREA SOLO to_create. Re-planifica server-side (plan_environment) y aplica
    os.makedirs(final, exist_ok=True) ÚNICAMENTE a los to_create (nunca confía en la
    lista del cliente). Cada makedirs va en try/except OSError: el fallo se acumula en
    'failed' y se CONTINÚA con el resto (C7 — jamás excepción hacia arriba).
    Retorna {'created': [rel...], 'skipped_existing': [...], 'conflicts': [...],
    'unsafe': [...], 'failed': [{'path': rel, 'error': str(e)}]}.
    Los conflict/unsafe JAMÁS se tocan. NUNCA borra nada."""
```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan89_environment_plan_apply.py`
(usar `tmp_path` de pytest como root real):
- `test_f2_validate_root_rules`: `""` ⇒ error; relativa ⇒ error; raíz de disco
  (`os.path.splitdrive(str(tmp_path))[0] + os.sep` en Windows, `"/"` en POSIX) ⇒
  error; `tmp_path` ⇒ None.
- `test_f2_plan_fresh_all_to_create`: root vacío + 3 rutas ⇒ 3 `to_create`; la
  respuesta trae `root_exists is True` y `layout_fingerprint` string no vacío.
- `test_f2_plan_existing_dir_exists_ok`: pre-crear `IN_` ⇒ `exists_ok`.
- `test_f2_plan_file_conflict`: pre-crear ARCHIVO llamado `salida` ⇒ `conflict`.
- `test_f2_plan_unsafe_traversal`: rel `"../fuera"` ⇒ `unsafe` reason
  `"fuera_de_root"` (y NO aparece nunca en to_create).
- `test_f2_plan_symlink_escape_unsafe` (C6): crear dir externo `tmp_path.parent/"ext"`
  y symlink `tmp_path/"link" -> ext` (envolver `os.symlink` en
  `try/except (OSError, NotImplementedError): pytest.skip("symlink no soportado")` —
  en Windows sin developer mode no hay privilegio); plan de `"link/sub"` ⇒ `unsafe`
  reason `"fuera_de_root"` (realpath lo resuelve fuera de root).
- `test_f2_plan_long_path_unsafe` (C6): rel de 300 chars (p.ej. `"a"*300`) ⇒ `unsafe`
  reason `"path_demasiado_largo"`.
- `test_f2_plan_fingerprint_stable_and_sensitive` (ADICIÓN): dos planes con los mismos
  argumentos ⇒ mismo `layout_fingerprint`; agregar una rel ⇒ fingerprint distinto.
- `test_f2_apply_creates_only_to_create`: aplicar ⇒ dirs creados; el archivo
  `salida` sigue INTACTO byte a byte (leer contenido antes/después).
- `test_f2_apply_idempotent_second_run_zero`: aplicar 2 veces ⇒ segunda vez
  `created == []` y plan posterior todo `exists_ok` (criterio de idempotencia del plan).
- `test_f2_apply_unsafe_never_created`: aplicar con `"../fuera"` en la lista ⇒ termina
  en `unsafe`, nada creado fuera de root (verificar que `tmp_path.parent` no ganó
  entradas nuevas).
- `test_f2_apply_partial_failure_reported` (C7): monkeypatch
  `services.environment_init.os.makedirs` para lanzar `OSError("denegado")` SOLO en
  una de 3 rutas ⇒ las otras 2 en `created`, la fallida en `failed` con su mensaje,
  y la llamada NO lanza.
- `test_f2_source_has_no_destructive_calls` (CENTINELA anti-destrucción): leer el
  texto de `services/environment_init.py` y assert que NO contiene ninguno de:
  `"rmtree"`, `"rmdir"`, `"unlink"`, `"os.remove"`, `"os.replace"`, `"rename"` (C13 —
  cubre os.rename/os.renames/Path.rename), `"shutil.move"`, `"open("` (el módulo no
  escribe archivos, solo crea directorios; `hashlib` no necesita `open`).

**Ratchet:** registrar. **Criterio binario:** 13 tests verdes.
**Flag:** ninguna (sin consumidores hasta F4). **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F3 — Validación aditiva de `devops_environment_settings` en client_profile

**Objetivo:** persistencia segura por UI del root y el layout.

**Archivo a editar:** `Stacky Agents/backend/api/client_profile.py` — después del
bloque del plan 88 F2, mismo patrón aditivo (key ausente = no-op):
```python
# Plan 89 F3 — settings de ambiente (aditivo).
env_settings = profile.get("devops_environment_settings")
if env_settings is not None:
    if not isinstance(env_settings, dict):
        return jsonify({"ok": False, "error": "devops_environment_settings debe ser un objeto."}), 400
    root = env_settings.get("environment_root")
    if root is not None:
        from services.environment_init import validate_root
        err = validate_root(root)
        if err:
            return jsonify({"ok": False, "error": f"environment_root: {err}"}), 400
    layout = env_settings.get("folder_layout")
    if layout is not None:
        from services.environment_init import is_safe_segment  # público (C12)
        if not isinstance(layout, dict) or any(k not in ("entry", "processing", "output", "default") for k in layout):
            return jsonify({"ok": False, "error": "folder_layout: keys en {entry,processing,output,default}."}), 400
        for k, segs in layout.items():
            if not isinstance(segs, list) or any(not isinstance(s, str) or not is_safe_segment(s) for s in segs):
                return jsonify({"ok": False, "error": f"folder_layout.{k}: lista de rutas relativas seguras (sin '..', sin caracteres invalidos de Windows, sin nombres reservados, no absolutas)."}), 400
    pps = env_settings.get("per_process_subfolder")
    if pps is not None and not isinstance(pps, bool):
        return jsonify({"ok": False, "error": "per_process_subfolder debe ser booleano."}), 400
```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan89_env_settings_validation.py`:
- `test_f3_absent_key_noop` (PUT sin la key ⇒ 200).
- `test_f3_root_relative_400`, `test_f3_root_drive_root_400`,
  `test_f3_layout_bad_key_400`, `test_f3_layout_traversal_segment_400`
  (`{"entry": ["../x"]}` ⇒ 400), `test_f3_pps_not_bool_400`.
- `test_f3_layout_windows_invalid_char_400` (C6): `{"entry": ["IN|X"]}` ⇒ 400.
- `test_f3_layout_reserved_name_400` (C6): `{"entry": ["CON"]}` ⇒ 400.
- `test_f3_valid_roundtrip`: PUT con settings §4 (root = un `tmp_path` real) ⇒ 200 y
  GET los devuelve intactos.

**Ratchet:** registrar. **Criterio binario:** 9 tests verdes + tests de client_profile
de planes 45/87/88 verdes.
**Flag:** ninguna (aditivo inerte). **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F4 — Endpoints `POST /api/devops/environments/plan` y `/apply`

**Objetivo:** exponer plan-then-apply con datos reales del proyecto, HITL server-side
+ handshake por fingerprint (ADICIÓN) + reporte de descartes (C8).

**Archivo a editar:** `Stacky Agents/backend/api/devops.py` (del plan 87 v2 F1;
imports VERIFICADOS, patrón 88 v2 C7:
`from services.environment_init import build_environment_layout, plan_environment,
apply_environment, validate_root, layout_fingerprint` +
`from services.client_profile import load_client_profile` — ya importado por 88 F3):
```python
def _load_env_context(body):
    """Helper compartido plan/apply. Retorna ((root, rel_paths), None) o (None, respuesta_error)."""
    project = body.get("project")
    if not project:
        return None, (jsonify({"error": "project es obligatorio"}), 400)
    profile = load_client_profile(project) or {}
    settings = profile.get("devops_environment_settings")
    settings = settings if isinstance(settings, dict) else {}   # defensivo (clase C5 del 88)
    root = settings.get("environment_root")
    err = validate_root(root or "")
    if err:
        return None, (jsonify({"error": f"environment_root invalido o no configurado: {err}",
                               "kind": "environment_root_invalid"}), 400)
    catalog = profile.get("process_catalog")
    rel_paths = build_environment_layout(catalog if isinstance(catalog, list) else [], settings)
    return (root, rel_paths), None

@bp.post("/environments/plan")
def environment_plan_route():
    """Dry-run SOLO-LECTURA del árbol de carpetas."""
    if not getattr(_config.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False):
        abort(404)
    ctx, err = _load_env_context(request.get_json(silent=True) or {})
    if err: return err
    root, rel_paths = ctx
    return jsonify(plan_environment(root, rel_paths))

@bp.post("/environments/apply")
def environment_apply_route():
    """Crea SOLO to_create. HITL: confirm=True + fingerprint del plan visto (ADICIÓN)."""
    if not getattr(_config.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False):
        abort(404)
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400
    fingerprint = body.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        return jsonify({"error": "fingerprint del plan es obligatorio (respuesta de /plan)"}), 400
    ctx, err = _load_env_context(body)
    if err: return err
    root, rel_paths = ctx
    if fingerprint != layout_fingerprint(root, rel_paths):
        return jsonify({"error": "el layout cambio desde el ultimo plan; recalcular el plan",
                        "kind": "plan_stale"}), 409
    requested = body.get("paths")
    if not isinstance(requested, list) or not requested:
        return jsonify({"error": "paths (lista no vacia) es obligatorio"}), 400
    # server-side: solo la intersección con el layout derivado del catálogo REAL
    approved = [p for p in rel_paths if p in set(requested)]
    result = apply_environment(root, approved)
    result["ignored_not_in_layout"] = sorted(set(requested) - set(rel_paths))  # C8: visible
    return jsonify(result)
```
Además, en `devops_health_route`: agregar
`"environments_enabled": bool(getattr(cfg, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False))`
(aditivo; previsto por el 87 v2 F4: "las keys nuevas del health viajan por ctx.health
de forma aditiva").
**La publicación inicial NO necesita backend nuevo:** el frontend (F5) reusa
`POST /api/devops/publications/materialize` (plan 88 v2 F3) + preview/commit (plan 73)
+ trigger (plan 72).

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan89_environments_endpoints.py`
(fixtures flag on/off sobre `STACKY_DEVOPS_ENVIRONMENTS_ENABLED`, patrón
`test_plan73_generator_endpoint.py:8-31`; el LOADER se patchea donde se usa:
`unittest.mock.patch("api.devops.load_client_profile", ...)` — patrón 88 v2 C7;
root = `tmp_path`):
- `test_f4_plan_flag_off_404`, `test_f4_apply_flag_off_404`.
- `test_f4_plan_no_root_400`: profile sin `environment_root` ⇒ 400 con
  `kind == "environment_root_invalid"`.
- `test_f4_plan_ok`: profile con catálogo Pacífico + settings §4 ⇒ 200, 3 entries
  `to_create`, respuesta con `layout_fingerprint` y `root_exists`.
- `test_f4_apply_without_confirm_400`: `confirm` ausente o `false` ⇒ 400 (HITL).
- `test_f4_apply_missing_fingerprint_400` (ADICIÓN): confirm sin `fingerprint` ⇒ 400.
- `test_f4_apply_stale_fingerprint_409` (ADICIÓN/C8): fingerprint de un plan viejo
  (mockear un catálogo, planear, cambiar el catálogo mockeado, aplicar con el
  fingerprint viejo) ⇒ 409 con `kind == "plan_stale"` y CERO dirs creados.
- `test_f4_apply_creates_and_reports`: confirm + fingerprint fresco + paths = los 3 ⇒
  200, `created` == 3, dirs existen bajo `tmp_path`.
- `test_f4_apply_ignored_not_in_layout_visible` (C8): paths con `"../evil"` y una ruta
  inexistente en el layout (con fingerprint fresco) ⇒ 200, ambos listados en
  `ignored_not_in_layout`, `created` NO los incluye; nada fuera de root.
- `test_f4_rerun_idempotent`: segundo apply (con fingerprint fresco del segundo plan)
  ⇒ `created == []`; segundo plan ⇒ todo `exists_ok`.
- `test_f4_health_exposes_environments_enabled`.

**Ratchet:** registrar. **Criterio binario:** 11 tests verdes + tests plan 87 F1 /
88 F3 verdes (health sigue compatible).
**Flag:** `STACKY_DEVOPS_ENVIRONMENTS_ENABLED` (guard per-request en ambos endpoints).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F5 — Frontend: sección "Ambientes" (wizard de 3 pasos con stepper)

**Objetivo:** UI del flujo completo: configurar → plan → aplicar → verificación →
publicación inicial, montada como sección DECLARATIVA del 87 v3 (`render(ctx)` +
healthKey, C1/C17), con stepper guiado (C18) y guardando SIEMPRE por el riel
GET→merge→PUT (C2).

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/environmentModel.ts` (TS puro):
- Tipos espejo §4: `EnvironmentSettings` (`folder_layout` con keys
  `entry|processing|output|default`), `PlanEntry {path, status, reason}` con
  `status: "to_create"|"exists_ok"|"conflict"|"unsafe"`;
  `EnvironmentPlanResponse {root, root_exists, layout_fingerprint, entries, summary}`;
  `EnvironmentApplyResponse {created, skipped_existing, conflicts, unsafe, failed, ignored_not_in_layout}`.
- Funciones puras: `emptyEnvironmentSettings()` (layout Pacífico §4 como default de
  UI: entry→IN_, processing→productivas, output→salida — SOLO como sugerencia inicial
  editable, no hardcode de backend); `validateSettingsLocal(s): string[]` (espejo de
  F3 para feedback inmediato: root no vacío/absoluto-a-simple-vista
  `/^[A-Za-z]:[\\/]|^\//`, segmentos sin `..`, sin `<>:"|?*`, sin reservados
  CON/PRN/AUX/NUL/COM1-9/LPT1-9 — la fuente de verdad sigue siendo el backend F3);
  `summarizePlan(entries)`; `selectablePaths(entries): string[]` (solo `to_create`);
  **`allExistsOk(entries): boolean` (ADICIÓN v3)** — true si `entries` no está vacío
  y TODAS tienen `status === "exists_ok"` (alimenta el badge "Ambiente verificado"
  de la verificación post-apply).

**Archivo NUEVO:** `Stacky Agents/frontend/src/components/devops/EnvironmentsSection.tsx`
— recibe `ctx: DevOpsSectionContext` (contrato 87 v3 F4; C1). El gating de SU flag
NO vive acá (C17): lo declara la entrada del registro y lo renderiza el shell.
**Wizard con stepper visual (C18):** cabecera con los 3 pasos
(1. Configuración / 2. Carpetas / 3. Publicación inicial) y estado por paso:
"listo" (verde) / "pendiente" (gris) — Paso 0 está "listo" si hay settings
guardados con root válido; Paso 1 si el último plan post-apply dio
`allExistsOk`; Paso 2 nunca se marca automáticamente (HITL).
**Errores visibles (C19):** TODA llamada async de la sección (GET/PUT del profile,
plan, apply, materialize) va en try/catch hacia `actionError: string | null`
renderizado en un área fija ("No se pudo <acción>: <mensaje>"). Prohibido
`console.*` como único destino.
- **Paso 0 — Configuración:** editor de `devops_environment_settings` (input root,
  3+1 listas de segmentos por kind, toggle per_process_subfolder).
  **Primera vez (C18):** si el profile no tiene la key, el editor se abre
  pre-poblado con `emptyEnvironmentSettings()` (layout Pacífico como sugerencia
  editable) + CTA "Configurá la raíz del ambiente para empezar" + botón "Usar
  layout de ejemplo" (re-aplica `emptyEnvironmentSettings()` si el operador borró
  todo). Mientras no haya settings GUARDADOS con root válido, el botón "Calcular
  plan" del Paso 1 queda `disabled` con hint "Primero guardá la configuración del
  Paso 1".
  **Flujo de guardado (C2 — read-modify-write OBLIGATORIO, riel §3.9):**
  1. GET fresco `/api/projects/<name>/client-profile`; `base = json.profile ?? {}`.
  2. `merged = mergeKeysIntoProfile(base, { devops_environment_settings: nuevosSettings })`
     — helper del 88 v2 F4, importado de `src/devops/presetsModel.ts` (NO duplicarlo).
  3. `PUT /api/projects/<name>/client-profile` con body `{ profile: merged }`.
  PROHIBIDO PUTear solo la key nueva: el PUT REEMPLAZA el profile completo
  (`client_profile.py:161`) y borraría `process_catalog`, presets y el resto.
  Si el PUT devuelve 400 (validación F3), mostrar el `error` literal del backend.
  **Gating (C17 — declarativo):** el gate de `environments_enabled` lo declara la
  entrada del registro y lo renderiza el SHELL con `FlagGateBanner` (87 v3 §3.12);
  esta sección NO contiene ningún aviso propio de su flag. La dependencia del Paso 2
  (sub-feature del 88) SÍ vive dentro de la sección: si
  `ctx.health.publications_enabled !== true` ⇒ en lugar del Paso 2, `FlagGateBanner`
  con `flagKey="STACKY_DEVOPS_PUBLICATIONS_ENABLED"`, message "La publicación
  inicial necesita la sección Publicaciones (flag
  STACKY_DEVOPS_PUBLICATIONS_ENABLED, plan 88)." y `onEnabled={ctx.refetchHealth}`
  (mismo patrón que generator/trigger en el 87 F5).
- **Paso 1 — Carpetas (plan-then-apply):** botón "Calcular plan" ⇒
  `DevOps.environmentPlan(project)` ⇒ guardar `layout_fingerprint` en estado + tabla
  de entries con color por status (to_create verde, exists_ok gris, conflict rojo con
  leyenda "existe un archivo con ese nombre; Stacky NUNCA lo toca", unsafe rojo con su
  `reason`). Si `root_exists === false` ⇒ warning amarillo: "La raíz no existe: se
  creará completa al aplicar. Verificá la ruta." (C15). Checkbox HITL "Confirmo crear
  las N carpetas nuevas" ⇒ habilita botón "Crear carpetas" ⇒
  `DevOps.environmentApply(project, selectablePaths(entries), confirmChecked, fingerprint)`
  ⇒ reporte created/skipped/conflicts/failed/ignored_not_in_layout (failed en rojo,
  ignored en ámbar). Respuesta 409 `plan_stale` ⇒ mensaje "El catálogo o la
  configuración cambiaron desde el último plan. Recalculá el plan." + limpiar el plan
  mostrado (ADICIÓN v2). Re-correr sobre ambiente inicializado muestra "0 cambios —
  ambiente ya inicializado".
  **Verificación automática post-apply ([ADICIÓN ARQUITECTO v3]):** tras un apply
  con respuesta 200, la UI re-llama `DevOps.environmentPlan(project)` (solo-lectura)
  y evalúa `allExistsOk(entries)`: si true ⇒ badge verde "Ambiente verificado:
  N carpetas existentes, 0 pendientes" y el Paso 1 del stepper pasa a "listo"; si
  false ⇒ panel rojo "Quedaron pendientes:" con la lista exacta de entries no
  `exists_ok` (+ los `failed` del apply). El operador termina con evidencia de
  disco, no con fe en el click.
- **Paso 2 — Publicación inicial (TODO):** selector de preset (los
  `devops_publication_presets` del proyecto, preseleccionando el primero con
  `mode==="todo"`; si no hay ninguno, botón "Crear preset TODO" que construye
  `{name:"inicial-todo", mode:"todo", groups:[], target:"gitlab"}` y lo guarda con el
  MISMO riel C2: GET fresco →
  `merged = mergeKeysIntoProfile(base, { devops_publication_presets: upsertPreset(existentes, presetTodo) })`
  (`upsertPreset` del 88 v2 F4) → PUT `{ profile: merged }`; si el PUT da 400 — p.ej.
  cap 50 del 88 v2 — mostrar el error literal). Botón "Materializar publicación
  inicial" ⇒ reusa EXACTAMENTE la cadena del plan 88 v2 F5:
  `DevOps.materializePublication(project, presetName)` → `PipelineYamlPreview` →
  `CommitPipelineModal` (HITL) → `TriggerPipelineSection` (HITL, visible solo si
  `ctx.health.trigger_enabled === true`). CERO lógica de publicación nueva; la
  semántica de resolución es la congelada por `plan88_resolution_cases.json` (C14 —
  este plan NO la reimplementa ni la toca).

**Archivos a editar:**
- `Stacky Agents/frontend/src/api/endpoints.ts` — extender el namespace `DevOps` del
  87 v2 F3 (helper real `api.post` con path COMPLETO `/api/...` — C11):
  ```ts
  environmentPlan: (project: string) =>
    api.post<EnvironmentPlanResponse>("/api/devops/environments/plan", { project }),
  environmentApply: (project: string, paths: string[], confirm: boolean, fingerprint: string) =>
    api.post<EnvironmentApplyResponse>("/api/devops/environments/apply",
      { project, paths, confirm, fingerprint }),
  ```
  Firma ÚNICA (C11): `confirm` es SIEMPRE argumento del caller — el componente pasa el
  estado del checkbox; el helper NUNCA lo auto-inyecta.
- `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` — `DEVOPS_SECTIONS` += entrada
  DECLARATIVA (contrato de extensión 87 v3 §3.12/C20 — C1/C17; el shell renderiza
  `FlagGateBanner` cuando `health.environments_enabled !== true`):
  ```ts
  {
    id: "ambientes",
    label: "Ambientes",
    healthKey: "environments_enabled",
    gateFlagKey: "STACKY_DEVOPS_ENVIRONMENTS_ENABLED",
    gateMessage: "La sección Ambientes necesita la flag STACKY_DEVOPS_ENVIRONMENTS_ENABLED (Configuración → Arnés, categoría DevOps).",
    render: (ctx) => <EnvironmentsSection ctx={ctx} />,
  },
  ```
  Opcional (tipado explícito): ampliar `DevOpsHealth` con `environments_enabled?:
  boolean` — la index signature del 87 v3 ya la admite sin tocar el shell; el
  backend la envía desde F4.

**Tests PRIMERO** — `Stacky Agents/frontend/src/devops/environmentModel.test.ts`
(vitest TS puro; instalado por 87 v3 F3.0, correr POR archivo — C16):
- `empty_settings_pacifico_defaults` (IN_/productivas/salida presentes y editables);
- `validate_root_relative_fails`; `validate_segment_traversal_fails`;
- `validate_segment_windows_char_fails` (C6: `"IN|X"` y `"CON"` fallan);
- `summarize_counts`; `selectable_only_to_create` (entries mixtos ⇒ solo to_create);
- `all_exists_ok_badge` (ADICIÓN v3): entries todas `exists_ok` ⇒ true; con una
  `to_create` o `conflict` ⇒ false; lista vacía ⇒ false.
Comando: `npx vitest run src/devops/environmentModel.test.ts`.

**Criterio binario:** vitest verde (7 tests) + `npx tsc --noEmit` 0 errores; el botón
"Crear carpetas" está `disabled` sin checkbox (HITL verificable por código); todo PUT
de client-profile de esta sección pasa por `mergeKeysIntoProfile` (verificable: grep
de `client-profile` en `EnvironmentsSection.tsx` — ninguna llamada PUT construye el
body sin el helper) (C2); Paso 2 no contiene lógica propia de materialización (solo
composición de componentes 88: `EnvironmentsSection` no importa `publication_spec` ni
renderers). Además (v3): la entrada del registro declara
`healthKey/gateFlagKey/gateMessage` y `EnvironmentsSection.tsx` NO contiene el
literal `STACKY_DEVOPS_ENVIRONMENTS_ENABLED` (grep — solo `DevOpsPage.tsx` lo tiene)
(C17); el banner del Paso 2 es `FlagGateBanner` (no texto plano) (C17); "Calcular
plan" `disabled` sin settings guardados (C18); tras apply exitoso se re-llama
`/plan` y se evalúa `allExistsOk` (ADICIÓN v3); toda llamada async tiene catch hacia
`actionError` (C19).
**Flag:** `STACKY_DEVOPS_ENVIRONMENTS_ENABLED` (+ master vía `requires`; + mensaje por
`publications_enabled` para el Paso 2).
**Runtimes:** sin impacto. **Trabajo del operador:** opt-in (activar la flag);
configurar root/layout es USO de la feature con defaults sugeridos.

### F6 — Cierre de la serie: no-regresión + checklist binario

**Comandos (todos deben pasar):**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_plan89_environments_flag.py tests/test_plan89_environment_layout.py tests/test_plan89_environment_plan_apply.py tests/test_plan89_env_settings_validation.py tests/test_plan89_environments_endpoints.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan88_publications_flag.py tests/test_plan88_publication_spec.py tests/test_plan88_presets_validation.py tests/test_plan88_materialize_endpoint.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan87_devops_flag.py tests/test_plan87_devops_endpoints.py tests/test_plan87_drafts_validation.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan73_generator_endpoint.py tests/test_harness_flags.py tests/test_flag_wiring.py -q
cd "../frontend"
npx vitest run src/devops/environmentModel.test.ts
npx vitest run src/devops/presetsModel.test.ts
npx vitest run src/devops/specBuilder.test.ts
npx tsc --noEmit
```

**Checklist binario de done:**
- [ ] Flag OFF ⇒ `/api/devops/environments/plan` y `/apply` 404, sección ausente,
      byte-idéntico.
- [ ] Ambiente fresco: plan muestra to_create + fingerprint; apply con confirm +
      fingerprint crea; los dirs existen.
- [ ] Re-inicialización: segundo plan todo `exists_ok`, segundo apply `created == []`,
      0 cambios en disco.
- [ ] Archivo donde va carpeta ⇒ `conflict` reportado e INTACTO tras apply.
- [ ] `"../"` en cualquier input ⇒ nunca se crea nada fuera de root (tests F1/F2/F4);
      symlink dentro de root que apunta afuera ⇒ `unsafe` (test F2).
- [ ] Fingerprint stale ⇒ 409 `plan_stale` y CERO dirs creados; paths descartados
      visibles en `ignored_not_in_layout` (ADICIÓN/C8).
- [ ] Fallo parcial de makedirs ⇒ reportado en `failed`, resto creado, nunca 500 (C7).
- [ ] Centinela anti-destrucción verde (el módulo no contiene borrado, rename ni
      escritura de archivos — lista C13).
- [ ] Guardar settings o el preset TODO NO pierde ninguna key ajena del client_profile
      (riel GET→merge→PUT con `mergeKeysIntoProfile`) (C2).
- [ ] Publicación inicial: 100% composición de 88/73/72 (cero lógica nueva de
      publicación; verificable: `EnvironmentsSection` no importa
      `publication_spec`/renderers, solo componentes del 88).
- [ ] `test_f1_spec_shape_frozen` (87 v3) y `plan88_resolution_cases.json` INTACTOS
      (C14).
- [ ] Tests registrados en ambos scripts de ratchet.
- [ ] **Usabilidad (v3, C22 — verificables por código/manual binario):**
  - [ ] Primera vez (sin settings): Paso 0 pre-poblado con el layout de ejemplo +
        CTA; "Calcular plan" `disabled` con hint (C18).
  - [ ] Happy path ≤ 4 clicks: "Usar layout de ejemplo"/guardar → "Calcular plan" →
        checkbox HITL → "Crear carpetas" ⇒ badge "Ambiente verificado" (con las
        flags necesarias ON).
  - [ ] Con ambientes OFF (y panel ON) la sección muestra `FlagGateBanner` con
        "Activar ahora"; ídem el Paso 2 con publicaciones OFF (C17).
  - [ ] Tras el apply, la verificación automática re-planifica y muestra el badge
        verde o el panel rojo con pendientes exactos (ADICIÓN v3).
  - [ ] Apagar el backend y clickear "Calcular plan" muestra el error en el área
        visible de la sección, no solo en consola (C19).
  - [ ] Stepper con estado por paso visible (C18).
- [ ] **Escalabilidad (87 v3 §3.12):** la sección cumple el namespacing
      (flag/health/rutas/key de client_profile) y NO introduce mecanismos paralelos
      de gating ni de persistencia.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Borrado accidental (el riesgo capital) | Ningún API destructivo en el módulo + test centinela F2 sobre el código fuente (incl. `rename`, C13) + apply solo interseca con to_create re-planificado server-side |
| Path traversal vía nombre de proceso o segmento de layout | Slug endurecido sin `..` (F1/C9) + `is_safe_segment` (F1/F3) + containment por **realpath** (F2/C6) + tests dedicados en F1, F2, F3 y F4 (defensa en 4 capas) |
| Symlink dentro de root apuntando afuera | Containment por `os.path.realpath` (no `abspath`) ⇒ `unsafe` (C6 + test F2) |
| Nombres inválidos/reservados de Windows (`IN|X`, `CON`, path >260, `IN_` vs `in_`) | `is_safe_segment` + guard de reservados en slug + límite 240 chars + dedup `casefold()` (C6, tests F1/F2/F3/F5) |
| **Plan stale: catálogo cambió entre dry-run y apply** | **Fingerprint obligatorio + 409 `plan_stale` + `ignored_not_in_layout` visible (ADICIÓN/C8)** |
| Fallo parcial de makedirs (permisos, drive inexistente) ⇒ 500 y creación a medias | try/except OSError POR ruta + `failed` en la respuesta + test con monkeypatch (C7) |
| **PUT de client_profile REEMPLAZA el profile ⇒ guardar settings/preset podría borrar config del operador (C2)** | Riel §3.9 + flujo F5 read-modify-write literal + `mergeKeysIntoProfile` del 88 v2 (importado, no duplicado) + criterio grep en F5 |
| Operador apunta root a `C:\` | `validate_root` rechaza raíz de disco (F2/F3) |
| Root con typo inexistente ⇒ árbol creado en lugar equivocado | `root_exists` en la respuesta del plan + warning literal en UI (C15) |
| Cliente manda `paths` arbitrarios al apply | El server IGNORA todo path fuera del layout derivado del catálogo real y lo REPORTA en `ignored_not_in_layout` (F4 + test) |
| Doble apply concurrente | `os.makedirs(..., exist_ok=True)` es race-safe; idempotencia por diseño |
| Catálogo editado a mano con entradas no-dict | `build_environment_layout` las omite, nunca lanza (C10 + test) |
| Carpetas creadas pero publicación inicial falla | Pasos independientes y re-entrantes: re-correr Paso 1 es no-op (idempotente), Paso 2 se reintenta solo |
| Confusión de flags (panel/publicaciones/ambientes) | `FlagGateBanner` con "Activar ahora" (87 v3): el gate de la sección lo declara el registro; el del Paso 2 nombra la flag exacta del 88 (C17) |
| Plan 87/88 sin implementar | Dependencia y orden declarados (versiones v3); F0-F2 implementables en aislamiento |
| **Primera vez sin guía / plan sin settings ⇒ 400 crudo (C18)** | Paso 0 pre-poblado + CTA + "Calcular plan" disabled con hint + stepper con estados |
| Apply "exitoso" sin evidencia en disco | Verificación automática post-apply: re-plan + `allExistsOk` ⇒ badge verde o panel rojo con pendientes (ADICIÓN v3) |
| Gating hand-rolled divergente del panel (C17) | Entrada declarativa en el registro + criterio grep en F5 |

## 7. Fuera de scope (v1)

- Crear carpetas en servidores REMOTOS (SSH/UNC/agentes): v1 es filesystem local de
  la máquina del operador (justificación §3.3); remoto exigiría credenciales y otro
  modelo de seguridad. **[NOTA DE COMPATIBILIDAD 2026-07-04]** ese "otro plan" ya
  existe: el **plan 91** (registro de servidores DevOps con alias; credenciales en
  Windows Credential Manager vía `keyring`, nunca en texto plano) expone
  `get_credential(alias)` en `server_registry.py` y `ctx.selectedServer` en el shell
  del panel como LOS puntos de consumo para una futura extensión remota (v2 de este
  plan resolvería `environment_root` como path UNC del servidor seleccionado). Esta
  v1 sigue siendo local-only; nada de este plan cambia.
- Borrar/renombrar/mover carpetas o "desinicializar" ambientes (violaría §3.2).
- Plantillas de contenido inicial DENTRO de las carpetas (archivos seed).
- Múltiples ambientes por proyecto (v1: un `environment_root` por client_profile; N
  ambientes = N proyectos, que es el modelo actual de Stacky).
- Scheduling de la publicación inicial (HITL siempre).
- Resolución automática de conflictos (`conflict` SIEMPRE queda en manos del operador,
  fuera de Stacky).

## 8. Glosario

- **Ambiente**: árbol de carpetas de disco que los procesos batch del cliente esperan
  (entrada/productivas/salida) + su primera publicación.
- **Plan-then-apply**: patrón en dos pasos — dry-run que clasifica sin tocar nada, y
  aplicación explícita SOLO de lo aprobado (análogo a `terraform plan/apply`).
- **layout_fingerprint**: sha256 de root + rutas del plan; el apply lo exige para
  garantizar que se aplica EXACTAMENTE el plan que el operador vio (409 `plan_stale`
  si cambió). ADICIÓN v2.
- **to_create / exists_ok / conflict / unsafe (+reason)**: estados del plan de
  carpetas (§4).
- **environment_root**: raíz absoluta del ambiente en la máquina del operador,
  parametrizada en `devops_environment_settings` del client_profile.
- **folder_layout**: mapeo `kind → subcarpetas relativas`; deriva el árbol del
  process_catalog (el conocimiento vive en el catálogo, no en el código).
- **Publicación inicial (TODO)**: primera publicación del ambiente usando un preset
  `mode="todo"` del plan 88 v2 (resolución dinámica de todo el catálogo, semántica
  congelada por `plan88_resolution_cases.json`).
- **mergeKeysIntoProfile**: helper puro TS del 88 v2 F4 que mezcla un patch de keys
  sobre el profile completo antes del PUT (el PUT reemplaza TODO el documento, §3.9).
- **Flujo canónico Pacífico / preset / materializar / HITL / ratchet /
  client_profile / DevOpsSectionContext**: ver glosarios de los planes 87 v2 §7 y
  88 v2 §8.

## 9. Orden de implementación

1. F0 — flag (4 patas + harness_defaults.env; tests meta verdes).
2. F1 — `build_environment_layout` + `layout_fingerprint` puros (11 tests).
3. F2 — `plan_environment`/`apply_environment` + centinela anti-destrucción (13 tests).
4. F3 — validación aditiva `devops_environment_settings` (9 tests).
5. F4 — endpoints plan/apply (fingerprint + ignored) + health key (requiere 87 v2 F1).
6. F5 — `environmentModel.ts` (incl. `allExistsOk`) + `EnvironmentsSection`
   (stepper C18, errores C19, verificación post-apply ADICIÓN v3, riel
   GET→merge→PUT) + entrada declarativa en `DEVOPS_SECTIONS` con healthKey/gate
   (C17) (requiere 87 v3 F4/F5 y 88 v3 F3/F4/F5).
7. F6 — cierre de la serie.

## 10. Definición de Hecho (DoD)

- 49 tests backend nombrados (F0:5, F1:11, F2:13, F3:9, F4:11) verdes por archivo con
  el venv; vitest F5 verde (7 tests, incl. `all_exists_ok_badge`);
  `npx tsc --noEmit` 0 errores.
- No-regresión: suites de planes 87/88/73 + meta-tests del arnés verdes;
  `test_f1_spec_shape_frozen` y `plan88_resolution_cases.json` intactos (C14).
- Flag OFF ⇒ byte-idéntico. Checklist F6 completo (incluye los bloques de
  usabilidad C22 y escalabilidad §3.12; cero gating hand-rolled C17).
- Idempotencia demostrada por test (re-run ⇒ 0 cambios), centinela anti-destrucción
  verde (Stacky NO PUEDE borrar nada desde este plan, por construcción), apply
  atómicamente honesto (fingerprint 409 / failed / ignored_not_in_layout visibles).
- Ningún PUT parcial de client_profile (C2); cero lógica de publicación nueva (todo
  compuesto del 88 v2).
