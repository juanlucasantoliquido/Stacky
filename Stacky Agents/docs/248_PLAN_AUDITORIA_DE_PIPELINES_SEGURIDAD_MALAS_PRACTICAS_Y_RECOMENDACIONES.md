# Plan 248 — Auditoría de pipelines: riesgos de seguridad, malas prácticas y recomendaciones

> Estado: **IMPLEMENTADO F0..F6** (2026-07-26) — **F6 se hizo entera**, con sus tres ediciones de
> montaje (C3): nada de módulo sin call site. Resultados REALES por archivo:
> `test_plan248_audit_core.py` **10 passed**, `test_plan248_security_rules.py` **29 passed**,
> `test_plan248_recommendations.py` **15 passed**, `test_plan248_audit_baseline.py`
> **12 passed + 1 skipped** (el `test_emit_baseline`, que sólo corre con la env var),
> `test_plan248_suppressions.py` **7 passed**, `test_plan248_api.py` **7 passed**.
> Frontend: `pipelineAuditModel.test.ts` **8 passed**, `npx tsc --noEmit` **0 errores**.
> Gates: `test_harness_flags.py` **56 passed / 0 failed** (número exacto de C7),
> `test_harness_ratchet_meta.py` **4 passed**, `test_plan243_reglas_semanticas.py` **27 passed**,
> `test_plan243_corpus_mirror.py` **8 passed**, `compileall services api` limpio.
> **Frontera con el 249 verificada mecánicamente:** `git diff --stat --
> backend/services/cicd_semantic_rules.py` → **sin salida**.
>
> **El baseline dio EXACTAMENTE lo que el plan predijo, sin retocar ninguna regla:**
> **17 hallazgos, 0 de severidad `error`, 17/17 con veredicto `REAL`** —
> SEC003 ×1 (`ci-dacpac.yml:38`), SEC005 ×4 (`:112`, `:99`, `:122`, `:102`),
> SEC006 ×1 (`security-scan-online.yml:56`), OPT001 ×3, OPT002 ×3,
> OPT003 ×2 (`cd-deploy-test.yml:123` y `:162`) y OPT004 ×3.
> `test_ley_de_severidad` y `test_toda_regla_dispara_sobre_su_repro` (las dos casillas que
> definen si el plan cumplió su tesis) están **verdes**.
>
> **Bug REAL encontrado al implementar (no del plan, sino del corpus):** el ancla de línea por
> primera ocurrencia textual caía en un **comentario**. `line_of(lines, "ubuntu-latest")` daba
> `ci-dacpac.yml:12` (un comentario que justifica la decisión) en vez del `vmImage:` de `:38`;
> lo mismo `"TEST-Server"` → `cd-deploy-test.yml:12` en vez de `:123`/`:162`. Los criterios
> binarios de F1 (`line == 38`) y F2 (`[123, 162]`) lo detectaron. Fix: `line_of_pair(lines, a, b)`
> en `cicd_audit_core.py` — la evidencia se sigue confirmando **en el árbol**, esto sólo la ancla
> bien. Es la misma trampa del comentario de §2.3, pero por el lado del ancla en vez del de la
> detección.
>
> **Desvío declarado:** `test_plan248_recommendations.py` tiene **15 funciones** en vez de las 22
> que decía el criterio de F2. El plan nombraba 8 positivo/negativo + 6 recuentos = **14**, y el
> "22" no cierra con su propia enumeración (mismo defecto de conteo que C8 corrigió para F1).
> Se implementaron las **14 nombradas** más `test_recuentos_exactos_del_corpus`, que asierta el
> diccionario completo `{OPT001:3, OPT002:3, OPT003:2, OPT004:3}` de una.
>
> **Pendiente:** sólo el **smoke visual manual** del panel.
>
> Estado previo: **v2 · CRITICADO** (2026-07-26). Pipeline: proponer ✓ → **criticar ✓ [este paso]** → implementar (`implementar-plan-stacky`) → supervisar.
> Autor v1: Claude Opus 5 (1M context). Crítica v2: juez **independiente** (no escribió la v1).
> **Veredicto de la v1: RECHAZADO** — 4 bloqueantes (C1 colisión de superficie con el 249, C2 bug de agrupación que produce un falso verde en el test capstone de F2, C3 panel sin punto de montaje, C4 cinco reglas sin gate que pruebe que disparan). Los 4 quedan corregidos en esta v2.
> Serie **"Mago de las Pipelines"** (246–252), plan **3 de 7**.
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro. **Paridad trivial: este plan NO usa LLM en ningún punto** (§3.2).
> Flag: `STACKY_PIPELINE_AUDIT_ENABLED`, default **ON**.
> Dependencias de serie: consume **246** (inventario) y **247** (perfil). **Degrada explícitamente si no están** (§2.5). No aplica fixes: eso es el **250**.

---

## CHANGELOG v1 → v2

Toda la evidencia de la v1 fue **re-verificada abriendo los archivos**. La tabla de anclajes de §2.1
resultó **casi enteramente correcta** (28 de 32 anclajes exactos al número de línea) y **los 12
recuentos del corpus de §2.2 son todos correctos**, incluidos los cuatro que un `grep` ingenuo
reporta mal por indentación variable (`command:  'test'` con dos espacios). Eso no se toca. Lo que
cambia:

**Bloqueantes corregidos**

- **C1 (BLOQUEANTE) · Colisión de superficie con el Plan 249.** F0 editaba
  `services/cicd_semantic_rules.py` (+4 líneas). Ese archivo está declarado **exclusivo del 249**
  en el mapa de colisiones del 246 (`246_PLAN_INVENTARIO_VIVO_DE_PIPELINES_MULTIPROVEEDOR.md:96`
  — *"249 | … **`services/cicd_semantic_rules.py`** (único plan que lo edita)"* — y `:107-109`).
  El orden de merge canónico (`:110`) manda que 248/250/251 vayan **en paralelo**, así que la
  colisión es real, no teórica. **Fix:** F0 ya **no edita nada** fuera de su propia superficie;
  importa `_iter_steps` / `_StepCtx` directamente con un alias local (§F0). Misma verdad única,
  cero bytes escritos en archivo ajeno.
- **C2 (BLOQUEANTE) · OPT002 no ve los pipelines de raíz, y su test negativo pasaba en verde por
  el bug.** `_iter_steps` emite `location = "steps[%d]"` para los pasos de raíz
  (`cicd_semantic_rules.py:126`), sin el segmento `.steps[`. El pseudocódigo v1 agrupaba con
  `ctx.location.rsplit(".steps[", 1)[0]`, que sobre `"steps[3]"` devuelve `"steps[3]"` ⇒ **cada
  paso de raíz queda en su propio grupo y `hubo_build` nunca se activa**. Cinco de los nueve golden
  son de raíz (`agendaweb-ci.yml:35`, `pr-validation-online.yml:36`, `ci-batch.yml:77`,
  `ci-dacpac.yml:40`, `security-scan-online.yml:42`). Consecuencias medidas: el recuento esperado de
  OPT002 habría sido **2, no 3** (`pr-validation-online` desaparece), y `agendaweb-ci` —el **control
  negativo** de la fase— habría dado 0 hallazgos **por el bug, no por su `--no-build`**. Un falso
  verde en el test capstone de una fase, en el plan cuya tesis es matar el falso rojo. **Fix:**
  `job_key()` explícita en F0, con su propio test sobre un fixture de raíz (§F0, §F2).
- **C3 (BLOQUEANTE) · F6 creaba un panel sin punto de montaje.** Declaraba crear
  `pipelineAuditModel.ts` y `PipelineAuditPanel.tsx` y **ningún** call site: ni
  `DevOpsPage.tsx` (`DEVOPS_SECTIONS:113`, `DevOpsHealth:32`), ni `endpoints.ts` (`:3818`), ni
  `api/devops.py` (`_health_payload:28`). Las tres superficies se las asigna el 246 §0.3 (`:80-87`).
  Es el patrón exacto que dejó inertes dos fases del Plan 176 (módulo testeado, sin consumidor).
  **Fix:** F5 y F6 declaran las tres ediciones, con anclaje y test de montaje.
- **C4 (BLOQUEANTE) · 5 de las 12 reglas tienen 0 hits sobre el corpus y nada probaba que
  disparen.** SEC001, SEC002, SEC004, SEC007 y SEC008 valen `0` en el baseline **por diseño** (la
  Ley de severidad las habilita a `error` justamente por eso). Pero entonces el baseline congelado
  **no las cubre**: un typo en el criterio las deja inertes y los 8 tests de F3 siguen verdes. Una
  regla de seguridad que nunca dispara es exactamente el falso sentido de seguridad que el plan dice
  combatir. **Fix: [ADICIÓN ARQUITECTO] contrato `repro=` obligatorio + meta-test**, reusando el
  mecanismo que **ya existe** en `pipeline_lint.py:70-72` (*"repro: (provider, yaml_minimo_que_dispara_la_regla) — OBLIGATORIO para toda regla"*). Ver §4.5 y F3.

**Importantes corregidos:** C5 duplicación parcial SEC002/PL014 en el sink `echo` · C6
`--emit-baseline` contradecía la pureza declarada del módulo · C7 el gate de `test_harness_flags.py`
se relajaba contra un baseline que **hoy es 56/56 verde** (medido) · C8 los 24 tests de F1/F2
"positivo + negativo por regla" no tenían nombre · C9 `/api/diag/health` no es el camino de los
paneles DevOps · C10 el DoD de "0 LLM / 0 red" era "por inspección", no binario · C11 SEC005
desalineaba `location` (del walk) con `line` (primera ocurrencia **textual**; `cd-deploy-test.yml`
tiene 4 `PublishBuildArtifacts@1`) · C12 `_SECURITY_MARKERS` sin case-folding declarado y con
`"test"` como substring puro · C13 SEC007 declaraba en §4.1 el caso `{branches:{exclude:['*']}}` que
su pseudocódigo no implementaba · C14 el DoD contaba 5 archivos de test y listaba 6.

**Menores corregidos (anclajes falsos, todos verificados uno por uno):** C15 `_PROD_MARKERS` está en
`cicd_semantic_rules.py:55`, no `:56` · C16 el criterio de PL012 está en `pipeline_lint.py:714`, no
`:715` · C17 `groupFindings` está en `pipelineLint.ts:61` (no `:62`) y `commitLintSummary` en `:156`
(no `:157`) · C18 §2.3 declaraba **1** ocurrencia de `IISWebAppDeploymentOnMachineGroup@0` y son
**2** (`agendaweb-ci.yml:143` y `ci-cd-online.yml:17`), ambas en comentarios ⇒ los falsos positivos
de un escáner por regex son **9**, no 8 · C19 la autorización citada como *"dossier §3: si tu plan
necesita un módulo más, prefijalo igual"* **no existe en el 246**; los dos módulos extra se
justifican ahora por otra vía · C20 se agrega la huella de regresión en
`docs/sistema/error_fingerprints.json`.

---

## 0. La tesis del plan (leer esto antes que nada)

Stacky ya sabe decir si un pipeline está **bien formado** (PL001..PL014, Plan 186) y si va a
**funcionar** en este ecosistema (RS001..RS009, Plan 243). No sabe decir si es **peligroso** ni si
es **caro**. Un YAML puede pasar los 23 chequeos actuales y aun así publicar un `Web.config` con
cadenas de conexión literales como artefacto descargable, o dejar un agente self-hosted colgado
para siempre porque nadie declaró un timeout.

Pero el riesgo real de escribir este plan no es quedarse corto: es el opuesto.

> **La tesis:** un auditor de seguridad que grita es peor que no tener auditor. Esta casa tiene un
> plan entero (241) dedicado a matar el **falso verde**; su pecado espejo es el **falso rojo**. Los
> 9 pipelines del corpus dorado **corren hoy en producción**. Si una regla nueva los pinta de rojo,
> hay exactamente dos posibilidades y el plan tiene que elegir una **por escrito, regla por regla**:
> o encontró algo real y valioso, o la regla está mal escrita. No hay tercera opción, y "es un
> warning nomás" no es una respuesta.

De ahí sale la única ley de diseño que gobierna todo el documento, y que es la contribución
central de este plan:

> ### Ley de severidad (§3.1)
> En `MODE_AUDIT`, una regla puede declarar `SEV_ERROR` **sólo si su recuento sobre el corpus
> dorado es exactamente 0**. Si una regla acierta sobre producción, en `MODE_AUDIT` su severidad
> máxima es `SEV_WARNING` — porque los 9 golden **corren hoy**, y decir "error" significaría
> afirmar que el sistema en producción está roto, lo cual es falso. La misma regla **sí** puede ser
> `SEV_ERROR` en `MODE_NL_STRICT`, donde el sujeto es un YAML que Stacky acaba de inventar y que
> todavía no corrió nunca.

Esta ley es **testeable y binaria** (`test_ley_de_severidad`, F3), resuelve de frente la trampa que
el Plan 243 sufrió en su C13, y usa el mismo eje `MODE_AUDIT` / `MODE_NL_STRICT` que ya existe en
`cicd_semantic_rules.py:43-48` en vez de inventar un mecanismo paralelo.

---

## 1. Objetivo y valor

Que el operador abra una pipeline que **ya existe** y vea, sin configurar nada y sin que Stacky
toque un solo byte del YAML, una lista corta de hallazgos donde cada uno dice **qué línea lo
provoca**, **por qué importa** y **cómo se arregla** — y que pueda archivar para siempre el
hallazgo que ya evaluó, sin que esa decisión se convierta en una venda.

**KPI / impacto medible:**

| KPI | Medición | Meta |
|---|---|---|
| **KPI-1 · Señal, no ruido** | Hallazgos totales sobre los 9 golden en `MODE_AUDIT` | ≤ 20, de los cuales **0 son `SEV_ERROR`** y **0 están marcados `FALSO_POSITIVO`** en la revisión de F3 |
| **KPI-2 · Evidencia obligatoria** | Hallazgos con `line=None` **y** `location=""` | **0** (un hallazgo sin ancla no se emite: es una opinión) |
| **KPI-3 · Supresión que no ciega** | Hallazgos suprimidos que reaparecen al mutar su evidencia | **100%** (fingerprint de evidencia, F4) |
| **KPI-4 · Costo cero de operación** | Llamadas a LLM y a la red por auditoría | **0 y 0** |
| **KPI-5 · Paridad** | Diferencia de salida entre Codex / Claude Code / Copilot | **byte-idéntica** (corolario de KPI-4) |

**Valor concreto ya demostrable con el corpus leído** (§2.2): la auditoría encuentra hoy, sin
inventar nada, que 4 pipelines publican como artefacto un paquete Web Deploy con las cadenas de
conexión sin parametrizar (SEC005), que el único escaneo de vulnerabilidades del ecosistema no
puede fallar la build (SEC006), que los dos jobs de deploy sobre el agente self-hosted `TEST-Server`
no tienen timeout (OPT003), y que el único pipeline Linux corre sobre una imagen que rota sola
(SEC003). Ninguno de esos cuatro lo detecta ninguna regla existente.

---

## 2. Evidencia (todo verificado abriendo los archivos el 2026-07-26)

### 2.1 Lo que YA existe y este plan reutiliza sin tocar

| Pieza | Anclaje (**símbolo** + línea) | Qué aporta a este plan |
|---|---|---|
| Severidades canónicas | `backend/services/pipeline_lint.py:18-20` (`SEV_ERROR`, `SEV_WARNING`, `SEV_INFO`) | Se **importan**, no se redefinen |
| Detector de secretos canónico | `backend/services/pipeline_lint.py:14` (`from services.secret_masking import mask_token_values`), usado en `_rule_pl012` (`:707`, criterio `if mask_token_values(val) != val:` en **`:714`** — C16: la v1 decía `:715`, que es el `findings.append`) | SEC001 usa el **mismo** criterio (prefijo conocido + ≥8), aplicado a otra zona del árbol |
| **Contrato `repro=` de regla** | `pipeline_lint.py:70-72` (`_rule(code, severity, providers, repro)`, docstring: *"repro: (provider, yaml_minimo_que_dispara_la_regla) — **OBLIGATORIO** para toda regla"*) | **[ADICIÓN ARQUITECTO]** SEC/OPT adoptan el mismo contrato: es lo que hace imposible una regla inerte (§4.5, C4) |
| Heurística de nombre secreto | `pipeline_lint.py:550` (`_SECRET_SUFFIXES`), `:553` (`_looks_secret`) | SEC002 la importa tal cual |
| Whitelist de refs built-in | `pipeline_lint.py:545` (`_ADO_WL_PREFIXES`) | Evita marcar `$(Build.*)` como variable de usuario |
| Búsqueda de línea best-effort | `pipeline_lint.py:80` (`_find_line`), `:90` (`_find_line_nth`) | Patrón que replica `line_of` (F0); no se importa porque exige un `LintContext` |
| **Los dos modos** | `cicd_semantic_rules.py:43-45` (`MODE_AUDIT`, `MODE_NL_STRICT`, `_MODES`), `:48` (`_NL_STRICT_ONLY`), doc del contrato en `:9-25` | Se **importan**. Este plan **no** define modos propios |
| Recorrido estructural con pool efectivo | `cicd_semantic_rules.py:73-82` (`_StepCtx`), `:105` (`_iter_steps`), `:85` (`_pool_of`), `:141` (`_pool_is_hosted`) | **Es exactamente el walk que necesito.** F0 lo **importa con alias**, sin editar el archivo (C1) |
| **Formato de `location` del walk** | `cicd_semantic_rules.py:122` (`"%sjobs[%d].steps[%d]"`), `:119` (`"%sdeployments[%d].steps[%d]"`), **`:126` (`"steps[%d]"` — los pasos de RAÍZ NO llevan el segmento `.steps[`)** | **C2.** Cualquier agrupación por job debe pasar por `job_key()` (F0), nunca por un `rsplit(".steps[")` crudo |
| Formato de hallazgo semántico | `cicd_semantic_rules.py:62-69` (`SemanticFinding`: `code`, `severity`, `message`, `location`, `evidence`) | `AuditFinding` es este dataclass **+2 campos** (`line`, `remediation`). Mismo lenguaje, no otro |
| Guardia de tamaño | `cicd_semantic_rules.py:51` (`MAX_YAML_BYTES = 512*1024`), uso en `check_semantics` (`:506-512`) | Se reusa el mismo límite y el mismo `RS000`-style de aviso |
| Extracción SIEMPRE por parser | `cicd_task_catalog.py:268` (`extract_task_dicts`), `:287` (`extract_task_refs`), `:244` (`is_deploy_step`), `:261` (`is_machine_group_task`) | Base de SEC006/SEC008; **nunca regex** (§2.3) |
| Corpus dorado + su cache | `cicd_corpus_mirror.py:47-52` (`_GOLDEN_DIRS`), `:80` (`_load_golden`), `:88` (`sorted(os.listdir(...))` ⇒ determinismo) | F3 resuelve el corpus con **este mismo** patrón de ruta |
| Ledger JSONL durable | `ci_run_ledger.py:29` (`_ledger_path` → `Path(runtime_paths.data_dir()) / "ci_runs.jsonl"`), `:18` (`MAX_ROWS`), `:61` (`_clean_entry`, allowlist estricta) | F4 copia el patrón exacto para las supresiones |
| Directorio de datos | `backend/runtime_paths.py:48` (`data_dir`) | Única fuente de la ruta durable |
| Patrón de blueprint | `backend/api/pipeline_generator.py:1-26` (docstring del contrato + `bp = Blueprint("pipeline_generator", __name__, url_prefix="/pipeline-generator")`) | F5 lo copia literalmente |
| Registro de blueprints | `backend/api/__init__.py:44` (import), `:117` (`api_bp.register_blueprint(pipeline_generator_bp)`) | Dónde se engancha el blueprint nuevo |
| Contrato de flags | `harness_flags.py:21-42` (`FlagSpec`, campos `key/type/label/description/group/default`), `:120` (`_CATEGORY_KEYS`) | F5 declara la flag |
| Curación de defaults ON | `backend/tests/test_harness_flags.py:467` (`_CURATED_DEFAULTS_ON = {`) | **La lista vive en el TEST, no en el módulo.** Toda flag con `default=True` va acá o el test queda rojo |
| Binding real de la flag | `backend/config.py:516-517` (`STACKY_PIPELINES_ENABLED: bool = os.getenv(...)`) | Patrón del atributo de `Config` |
| Ratchet de tests | `backend/scripts/run_harness_tests.sh:766-770` y `backend/scripts/run_harness_tests.ps1:679-683` (bloque `test_plan243_*`) | **DOS listas.** Todo `test_*.py` nuevo va en las dos |
| Tipos espejo del lint en el front | `frontend/src/components/devops/pipelineLint.ts:13-29` (`LintFinding`, `LintReport`), **`:61`** (`groupFindings`), **`:156`** (`commitLintSummary`) — C17: la v1 decía `:62` y `:157`, que son la primera línea del cuerpo de cada función | F6 espeja este archivo en estilo; **no lo modifica** |
| **Montaje del panel DevOps** (C3) | `frontend/src/pages/DevOpsPage.tsx:32` (`interface DevOpsHealth`), `:113` (`DEVOPS_SECTIONS: DevOpsSection[]`, registro declarativo con `id/label/healthKey/gateFlagKey/render(ctx)`), `frontend/src/api/endpoints.ts:3818` (`export const DevOps = {`) | **F5/F6 los editan.** Sin esto el panel es código muerto (patrón que dejó inertes 2 fases del Plan 176) |
| **Health de los paneles DevOps** (C3, C9) | `backend/api/devops.py:28` (`_health_payload`), keys existentes `cockpit_enabled` (Plan 239), `build_workshop_enabled` (Plan 201), `dev_build_verify_enabled` (Plan 210) | El camino canónico es **`/api/devops/health`**, NO `/api/diag/health`. F5 agrega 1 key al final del dict |

### 2.2 El corpus dorado, leído de verdad (fundamento de todas las reglas)

`backend/tests/fixtures/cicd_nl/golden/` — **9 archivos**, confirmado por `ls`. **Abrí 8 de los 9**
(el noveno, `bootstrap-server-environment.yml`, sólo por `grep` — declarado en §2.6).

Estos son los hechos que sostienen cada regla. Cada número fue verificado con `grep -rn` sobre la
carpeta completa, no recordado:

| Hecho verificado | Recuento en los 9 | Anclaje |
|---|---|---|
| `timeoutInMinutes` | **0** | ningún archivo lo declara |
| `persistCredentials` | **0** | — |
| `Cache@2` | **0** | ningún pipeline cachea dependencias |
| `continueOnError` | **1** | `security-scan-online.yml:56` |
| `vmImage` terminado en `-latest` | **1** | `ci-dacpac.yml:38` (`'ubuntu-latest'`); los otros 6 fijan `'windows-2022'` |
| `- checkout: self` explícito | **3** | `bootstrap-server-environment.yml:123`, `cd-deploy-test.yml:130`, `:169` |
| `fetchDepth` | **0** | — |
| Pool self-hosted (`pool.name` sin `vmImage`) | **3** | `cd-deploy-test.yml:121` y `:160` (`'TEST-Server'`); `bootstrap-server-environment.yml:117` (**dinámico**: `'${{ parameters.agentPool }}'`) |
| `DotNetCoreCLI@2` con `command: test` | **4** | `agendaweb-ci.yml:76`, `ci-cd-online.yml:104`, `nightly-build-online.yml:75`, `pr-validation-online.yml:64` |
| …de esos, con `--no-build` | **1** | sólo `agendaweb-ci.yml:80` |
| `pr:` activo (≠ `none`) | **3** | `ci-batch.yml:25`, `ci-dacpac.yml:24`, `pr-validation-online.yml:17`, `security-scan-online.yml:18` (**4**; ver nota) |
| `AutoParameterizationWebConfigConnectionStrings=false` + `DeployOnBuild=true` + `PublishBuildArtifacts@1` | **4** | `ci-cd-online.yml:86,98,122`; `cd-deploy-test.yml:63,73,99`; `agendaweb-ci.yml:56,68,112`; `nightly-build-online.yml:49,61,102` |

> Nota de honestidad sobre `pr:` activo: son **4** archivos (`ci-batch`, `ci-dacpac`,
> `pr-validation-online`, `security-scan-online`). `security-scan-online.yml` no tiene paso de
> restore, así que OPT001 lo excluye por su propia condición, no por conteo.

**Los tres hallazgos más valiosos del corpus, ya identificados por lectura:**

1. **`security-scan-online.yml:56`** — `continueOnError: true` sobre el paso
   `DotNetCoreCLI@2 / dotnet list --vulnerable`, con un comentario del autor en la misma línea:
   *"reporta pero no bloquea solo por esto (cubierto por el script)"*. Es decir: el **único** escaneo
   de vulnerabilidades del ecosistema no puede fallar la build. **Es un hallazgo REAL**, y el autor
   ya razonó sobre él. Ese par exacto —hallazgo real + decisión previa del operador— es el que
   justifica que exista la supresión persistente de F4, y **no** que la regla se ablande.

2. **`ci-dacpac.yml:38`** — `vmImage: 'ubuntu-latest'`, justificado en `:12`
   (*"dotnet build funciona en Linux (ubuntu-latest) → más rápido y barato"*). La justificación es
   sobre el **SO**, no sobre el **pin**: `-latest` rota solo y puede romper la build sin que nadie
   cambie una línea. Y el propio corpus prueba la remediación: los otros 6 pipelines fijan
   `windows-2022`. **Hallazgo REAL con precedente interno de fix.**

3. **`cd-deploy-test.yml:120-121` y `:159-160`** — dos stages de deploy sobre el pool self-hosted
   `TEST-Server`, sin `timeoutInMinutes` en ningún lado del archivo. En ADO el timeout por default
   de un job es 60 min en agentes MS-hosted, pero **0 (sin límite) en self-hosted**: un job colgado
   inmoviliza el agente del servidor TEST indefinidamente. **Hallazgo REAL**, y acotado a 2 jobs en
   todo el corpus.

### 2.3 La trampa del comentario, medida (por qué CERO regex)

El Plan 243 documentó en su C20 que `grep` sobre el corpus devuelve **12** `- task:` cuando
`yaml.safe_load` devuelve **10**, porque hay dos dentro de comentarios. Este plan volvió a medir el
mismo fenómeno **sobre el eje de seguridad**, y es peor:

| Patrón buscado por texto | Ocurrencias por `grep` | Ocurrencias reales (post `yaml.safe_load`) | Falsos positivos que produciría un escáner por regex |
|---|---|---|---|
| `environment:` con valor de producción/staging | **5** | **0** | `agendaweb-ci.yml:136`, `:154`; `ci-dacpac.yml:95`; `bootstrap-server-environment.yml:87`, `:89` — **las 5 en comentarios** |
| `$(SQL_CONNECTION_STRING)` en un input de deploy | **2** | **0** | `ci-dacpac.yml:106`, `:114` — ambas en comentarios |
| `IISWebAppDeploymentOnMachineGroup@0` (la tarea de ADO-369) | **2** (C18: la v1 decía 1) | **0** | `agendaweb-ci.yml:143` y `ci-cd-online.yml:17` — **las 2 en comentarios** |

Un escáner de seguridad por regex reportaría **9 falsos positivos** (C18: la v1 dijo 8) sobre pipelines que hoy
funcionan, incluida la acusación de "desplegás a Producción sin aprobación" contra un pipeline que
está **deshabilitado** (`agendaweb-ci.yml:14-15`, `trigger: none` / `pr: none`) y cuyo bloque de
producción es **documentación**. Por eso:

> **Regla dura, heredada del 243 C20 y reforzada acá:** toda extracción de evidencia es por
> `yaml.safe_load` sobre el árbol parseado. El texto crudo del YAML se usa **exclusivamente** para
> resolver el número de línea de una evidencia que ya se confirmó en el árbol (`line_of`, F0), nunca
> para decidir si un hallazgo existe. Un test negativo por cada uno de los 3 patrones de arriba lo
> verifica (F1).

### 2.4 Los anclajes del corpus valen **+1 línea** respecto del original

Al vendorizar el corpus, el Plan 243 F0 agregó a cada archivo una línea 1 de procedencia
(`# fuente: RSPACIFICO/pipelines/<x>.yml - copiado 2026-07-26 (plan 243 F0)`). Consecuencia
verificada, y que hay que conocer antes de escribir un solo test:

| El dossier / Plan 243 dice (original RSPACIFICO) | En el fixture está en |
|---|---|
| `nightly-build-online.yml:110` (`- script: \|` crudo) | **`:111`** |
| `ci-batch.yml:58-59` (`matrix`) | **`:59-60`** |
| `agendaweb-ci.yml:142` (task comentada) | **`:143`** |
| `ci-dacpac.yml:102` (task comentada) | **`:103`** |

**Todos los anclajes de este documento están expresados sobre el FIXTURE**, que es lo que los tests
van a abrir. No los "corrijas" contra el dossier.

### 2.5 Qué consume de 246 y 247, y cómo degrada si no están

Este plan es el tercero de la cadena `246 → 247 → 248`. **Ninguna de las dos dependencias es dura**:

| Entrada | Origen ideal | Degradación si el plan origen no está implementado |
|---|---|---|
| `pipeline_key` (identidad estable de la pipeline) | Plan **246**, registro del inventario | `pipeline_key = "sha256:" + sha256(yaml_text)[:16]`. La auditoría y las supresiones funcionan igual; lo único que se pierde es que la supresión sobrevive a un cambio de nombre de archivo |
| `profile` (perfil de catálogo por stack) | Plan **247**, perfilador | `profile = PROFILE_DOTNET_FRAMEWORK` (`cicd_task_catalog.py:30`), que es el único perfil que existe hoy |
| `provider` (`"ado"` / `"gitlab"`) | Plan **246** | Parámetro obligatorio del request; el llamador lo sabe |

El import de 246/247 se hace con `try/except ImportError` y una función `_resolve_pipeline_key()`
de una sola responsabilidad. **Criterio binario:** existe el test
`test_auditoria_funciona_sin_246_ni_247` que monkeypatchea ambos imports a `ImportError` y verifica
que la auditoría del corpus produce **exactamente el mismo baseline**.

### 2.6 Lo NO verificado (declarado)

Honestidad obligatoria (§5 del dossier). Nada de esto se usa como anclaje afirmativo:

1. **`bootstrap-server-environment.yml` NO fue abierto completo.** Se inspeccionó sólo por `grep`:
   `:87`, `:89` (comentarios sobre approval gates), `:116-117` (`pool: name: '${{ parameters.agentPool }}'`),
   `:118` (`environment: '${{ parameters.targetEnvironment }}'`), `:123` (`- checkout: self`).
   **Consecuencia práctica:** las filas del baseline de F3 correspondientes a este archivo **las
   genera el script, no las afirma este plan**. Ver F3, que convierte esto en un paso HITL explícito.
2. **El comportamiento del timeout por default de ADO** (60 min hosted / 0 = sin límite en
   self-hosted) es conocimiento de la plataforma, **no verificado contra la organización ADO de este
   operador**. Por eso OPT003 es `SEV_WARNING` y su mensaje dice *"verificá el default de tu
   organización"* en vez de afirmar una cifra.
3. **El contenido real de `Web.config`** en el repo RSPACIFICO no se abrió: SEC005 afirma que el
   artefacto **incluye** el `Web.config` sin parametrizar (cadena causal verificable en el propio
   YAML), y **pregunta** si ese archivo tiene credenciales reales. No afirma que las tenga.
4. **No se verificó** si los Environments `Test` de ADO tienen o no checks de aprobación: eso no
   vive en el YAML. SEC008 lo dice explícitamente en su mensaje en vez de suponerlo.
5. Este plan **no toca ninguna tabla**: la única persistencia nueva es un JSONL (F4).

---

## 3. Principios, guardarraíles y recortes de alcance

### 3.1 La Ley de severidad (repetida acá porque es normativa, no retórica)

En `MODE_AUDIT`: `SEV_ERROR` ⟺ recuento sobre el corpus dorado = 0. En `MODE_NL_STRICT` no hay
restricción, porque el sujeto es un YAML recién generado que nunca corrió.

Traducción operativa por regla (tabla completa en §4):

- **0 hits en el corpus** → puede ser `error`: SEC001, SEC002, SEC004, SEC007.
- **≥1 hit en el corpus** → tope `warning`: SEC003, SEC005, SEC006, OPT003.
- **Recomendación de eficiencia, nunca bloqueante** → `info`: OPT001, OPT002, OPT004.

### 3.2 Determinismo total: cero LLM, cero red

**Las 12 reglas son funciones puras** `(doc_parseado, lines, contexto) → list[AuditFinding]`. Sin
LLM, sin red, sin disco (la única lectura de disco es el corpus dorado en el *test*, y el JSONL de
supresiones en F4, ambos explícitos).

Esto no es una preferencia estética, y hay que decirlo dentro del plan porque es un requisito:

> **Un escáner de seguridad que depende de un modelo no es auditable ni reproducible.** No podés
> firmar un informe cuyo resultado cambia entre corridas, no podés hacer un baseline congelado
> contra él, y rompés la paridad de los 3 runtimes porque cada uno tiene un modelo distinto detrás.
> Además, un LLM no puede sostener KPI-1: alucinaría hallazgos plausibles sobre pipelines correctos,
> que es exactamente el falso rojo que este plan existe para evitar.

Corolario: la paridad Codex / Claude Code / Copilot es **byte-idéntica por construcción**, no por
esfuerzo. Cada fase igual declara su impacto por runtime (formato obligatorio del dossier §7).

### 3.3 Read-only e innegociablemente HITL

La auditoría **detecta, explica y propone**. No escribe YAML, no abre PRs, no dispara corridas, no
manda mensajes. El campo `remediation` de cada hallazgo es **texto para el operador**, no un patch
aplicable. Aplicar el fix es el **Plan 250**.

La única escritura que este plan hace en todo el sistema es **una línea JSONL cuando el operador
suprime un hallazgo a mano**, con un `reason` no vacío obligatorio (F4). No hay supresión
automática, ni silenciosa, ni por lote.

### 3.4 Multiproveedor por declaración explícita

Cada regla declara su tupla `providers`, igual que hace `pipeline_lint._rule` (`pipeline_lint.py:70`).
Una regla que sólo aplica a ADO **lo dice en su declaración** y el motor la saltea para GitLab; no
hay reglas que "más o menos" apliquen. Hoy 9 de 12 son ADO-only, porque **no hay corpus dorado de
GitLab** (dossier §2.4) y este plan **no lo crea** — eso es el **Plan 249**. Las 3 reglas
provider-agnósticas (SEC001, SEC002, OPT004) se implementan para ambos y se testean con fixtures
sintéticas mínimas, declaradas como tales.

### 3.5 Recortes de alcance que hago yo mismo (dossier §7: máx. 6 fases)

Para que esto entre en **una** corrida de implementación, recorto explícitamente:

- **6 fases exactas (F0..F5)**, no 9.
- **12 reglas** (8 SEC + 4 OPT), no 20. Las 5 candidatas descartadas están en §4.3 **con el motivo**,
  para que nadie las "reintroduzca por olvido".
- **Sin panel de tendencia histórica** de hallazgos (requiere el ledger del 246; se puede sumar
  después sin romper nada).
- **Sin auditoría por lote** de todo el inventario en una corrida: F5 audita **una** pipeline por
  request. El barrido masivo depende del 246 y se agrega después.
- **Sin reglas GitLab-específicas** (`GL001..GLnn`) → Plan **249**.

---

## 4. El corazón del plan: la tabla de reglas

### 4.1 Familia SEC — seguridad (`services/cicd_security_rules.py`)

| ID | Título | Sev. `MODE_AUDIT` | Sev. `MODE_NL_STRICT` | Providers | Evidencia exacta que la dispara (post `yaml.safe_load`) | Remediación (texto del hallazgo) | Hits corpus |
|---|---|---|---|---|---|---|---|
| **SEC001** | Secreto literal fuera del bloque `variables:` | `error` | `error` | ado, gitlab | Un valor **string** dentro de `inputs.*`, `arguments`, `env.*` o `parameters.*` para el que `mask_token_values(v) != v` (criterio canónico: prefijo de token conocido + ≥8 chars). **Zona que PL012 NO mira**: `_ado_declared` (`pipeline_lint.py:637`) sólo recorre `variables:` de raíz/stage/job | "Movelo a la caja fuerte de variables (Plan 94) y referencialo como `$(NOMBRE)`. Un literal en el YAML queda en el historial de git para siempre, incluso si lo borrás después." | **0** |
| **SEC002** | Secreto impreso en el log por un sink que PL014 no ve | `error` | `error` | ado, gitlab | Una ref cuyo nombre pasa `_looks_secret` (`pipeline_lint.py:553`) aparece dentro de un string ejecutable que además contiene alguno de `_LOG_SINKS`. **C5 — `echo` queda EXCLUIDO de `_LOG_SINKS` a propósito**: `_rule_pl014` (`:752`) ya dispara exactamente sobre ese substring (`:758`) y emitir los dos sería reportar el mismo hallazgo con dos códigos. **El gap real de PL014** es que **este corpus es 100% Windows/PowerShell** y PL014 sólo mira `"echo"` — `security-scan-online.yml:102` usa `Write-Host` (verificado), que PL014 no ve. SEC002 cubre **sólo** los sinks de PowerShell y los flags de verbosidad | "El log de una corrida es visible para cualquiera con permiso de lectura del proyecto. Marcá la variable como secreta (`##vso[task.setvariable variable=X;issecret=true]`) o no la imprimas." | **0** |
| **SEC003** | Imagen de agente sin versión fijada | `warning` | `error` | ado | `pool.vmImage` (efectivo: job > stage > raíz) es un string que termina en `-latest` | "`-latest` rota sin avisar y puede romper la build sin que cambies una línea. Fijá la versión (`ubuntu-24.04`), como ya hacen los otros 6 pipelines de este repo con `windows-2022`." | **1** — `ci-dacpac.yml:38` |
| **SEC004** | Checkout con credenciales persistidas | `error` | `error` | ado, gitlab | Paso `- checkout:` (ADO) o `variables.GIT_STRATEGY`+`CI_JOB_TOKEN` explícito (GitLab) con `persistCredentials: true` | "Deja el token de la corrida escrito en `.git/config` del workspace, al alcance de cualquier paso posterior del job. Quitalo; si un paso puntual necesita el token, pasáselo explícito y acotado a ese paso." | **0** |
| **SEC005** | Artefacto publicado con `Web.config` sin parametrizar | `warning` | `warning` | ado | En el **mismo pipeline**: (a) un `VSBuild@1` cuyo `inputs.msbuildArgs` contiene `DeployOnBuild=true` **y** `AutoParameterizationWebConfigConnectionStrings=false`, **y** (b) al menos un `PublishBuildArtifacts@1`. Se emite **una vez por pipeline** (dedup). **C11 — `location` y `line` deben apuntar al MISMO paso:** se toma el **primer** `PublishBuildArtifacts@1` del walk y su línea se resuelve con `line_of(lines, "PublishBuildArtifacts@", occurrence=n)` donde `n` es su **orden de aparición en el walk**, nunca con la primera ocurrencia textual a secas (`cd-deploy-test.yml` tiene **4**: `:99`, `:106`, `:144`, `:183`) | "Con `AutoParameterizationWebConfigConnectionStrings=false` las cadenas de conexión van al paquete tal cual están en el `Web.config` del repo, y el artefacto lo descarga cualquiera con permiso de lectura del proyecto. Revisá si ese `Web.config` tiene credenciales reales; si las tiene, parametrizá (quitá el `=false`) o excluí `Web.config` del paquete." | **4** — `ci-cd-online.yml:122`, `cd-deploy-test.yml:99`, `agendaweb-ci.yml:112`, `nightly-build-online.yml:102` |
| **SEC006** | Fallo enmascarado en un paso de seguridad o de test | `warning` | `error` | ado, gitlab | `continueOnError: true` (ADO) o `allow_failure: true` (GitLab) sobre un paso cuyo `task` está en `_SECURITY_TASKS` o cuyo `displayName`/`command` matchea `_SECURITY_MARKERS`. **C12 — la comparación es `marker in texto.lower()`, obligatoriamente case-folded**: el único hit real del corpus es `displayName: 'dotnet list — Vulnerabilidades en proyectos SDK-style'` (`security-scan-online.yml:55`) y **sin `.lower()` la regla da 0 hits y queda inerte**. **C12 — `test` se compara como palabra, no como substring**: el marcador es `("test",)` evaluado con `re.search(r"\btest\b", texto.lower())`, para no matchear `latest` / `contest` / `testigo` | "Un paso de seguridad o de test que no puede fallar la build es un falso verde: reporta el problema en un log que nadie lee y la corrida sale en verde igual. Quitá el `continueOnError`, o movés el gate adentro del script y suprimís este hallazgo dejando el motivo por escrito." | **1** — `security-scan-online.yml:56` |
| **SEC007** | Pool self-hosted expuesto a código de PR | `error` | `error` | ado | El pipeline tiene `pr:` **activo** (existe y no es `none`/`{branches:{exclude:['*']}}`) **y** algún job tiene pool efectivo self-hosted (`pool.name` presente, `pool.vmImage` ausente, **y el nombre NO es dinámico**, §4.4) | "Cualquiera que abra un PR ejecuta código en tu servidor. La disciplina que ya sigue este repo es separarlo: validación de PR en pool hosted (`pr-validation-online.yml:17,34`) y deploy en self-hosted con `pr: none` (`cd-deploy-test.yml:32,121`). Mantenela." | **0** |
| **SEC008** | Deploy a producción sin gate verificable desde el YAML | `warning` | *no se evalúa* | ado | Un job `- deployment:` cuyo `environment:` es un **literal** (no dinámico) que matchea `_PROD_MARKERS` (**`cicd_semantic_rules.py:55`** — C15: la v1 decía `:56`, que es una línea en blanco) | "El check de aprobación de un Environment vive en la configuración de ADO, no en el YAML: desde acá no se puede verificar. Confirmá a mano que el Environment tiene aprobación manual antes de que este stage llegue a correr." | **0** |

**Por qué SEC008 no existe en `MODE_NL_STRICT`:** porque ahí ya la cubre `RS009`
(`cicd_semantic_rules.py:472`), que **rechaza** generar cualquier pipeline con `environment` de
producción. Emitir las dos sería reportar el mismo problema dos veces con dos códigos distintos.
Este es el uso preciso del eje de modos que el plan exige: **no** para ablandar reglas, sino para
que cada modo tenga exactamente el conjunto que le corresponde.

### 4.2 Familia OPT — malas prácticas y optimización (`services/pipeline_recommendations.py`)

| ID | Título | Sev. | Providers | Modo | Evidencia exacta que la dispara | Remediación (texto del hallazgo) | Hits corpus |
|---|---|---|---|---|---|---|---|
| **OPT001** | Restore sin caché en un pipeline que corre en cada PR | `info` | ado | `audit` | Pipeline con `pr:` activo **y** al menos un paso de restore (`NuGetCommand@2` con `inputs.command == 'restore'`, o `DotNetCoreCLI@2` con `inputs.command == 'restore'`) **y** ningún paso `Cache@2` en todo el documento. Una vez por pipeline | "Este pipeline restaura dependencias desde cero en cada push a cada PR. Un `Cache@2` con clave sobre `packages.config` / `*.csproj` corta ese tiempo casi entero cuando las dependencias no cambiaron." | **3** — `ci-batch.yml:85`, `ci-dacpac.yml:50`, `pr-validation-online.yml:44` |
| **OPT002** | Recompilación innecesaria en el paso de tests | `info` | ado | `audit` | Un `DotNetCoreCLI@2` con `inputs.command == 'test'` que (a) está en el **mismo job** que un paso de build previo (`VSBuild@1`, o `DotNetCoreCLI@2` con `command == 'build'`) y (b) cuyo `inputs.arguments` **no** contiene `--no-build` | "`dotnet test` recompila por default: este job compila dos veces. Si el proyecto de test es parte de la solución que ya compilaste, agregá `--no-build` — es lo que hace `agendaweb-ci.yml:80` con este mismo par solución/proyecto. Si no es parte de la solución, ignorá este aviso y suprimilo." | **3** — `ci-cd-online.yml:101`, `nightly-build-online.yml:72`, `pr-validation-online.yml:61` |
| **OPT003** | Job self-hosted sin límite de tiempo | `warning` | ado | `audit` | Un job (o `- deployment:`) cuyo pool efectivo es self-hosted **literal** (§4.4) y que no declara `timeoutInMinutes` en el job, ni el stage, ni la raíz | "En agentes self-hosted el timeout por default de ADO es *sin límite* (verificá el default de tu organización): un job colgado inmoviliza el agente del servidor para siempre y ninguna corrida siguiente arranca. Declará `timeoutInMinutes` acorde a lo que tarda el deploy." | **2** — `cd-deploy-test.yml:123`, `:162` |
| **OPT004** | Checkout con historial completo | `info` | ado, gitlab | `audit` | Un paso `- checkout:` **explícito** que no declara `fetchDepth` (ADO) / job sin `GIT_DEPTH` con `checkout` explícito (GitLab) | "El checkout trae todo el historial del repo. Si el job sólo necesita los archivos actuales, `fetchDepth: 1` baja el tiempo de checkout y el disco del agente." | **3** — `bootstrap-server-environment.yml:123`, `cd-deploy-test.yml:130`, `:169` |

> **Por qué OPT004 exige un `- checkout:` explícito:** ADO hace un checkout implícito en todo job
> que no lo declare. Marcar la ausencia implícita dispararía sobre **9/9** pipelines: ruido puro
> (viola KPI-1). Al exigir que el paso esté escrito, la regla habla sólo donde alguien ya tomó una
> decisión sobre el checkout y puede refinarla. **Preferir 3 hallazgos accionables sobre 9
> hallazgos ciertos es el diseño, no una concesión.**

### 4.3 Candidatas EVALUADAS y DESCARTADAS (con el motivo, para que no vuelvan)

El brief pedía evaluar candidatas contra el corpus y quedarse sólo con las que se sostienen. Estas
**no** se sostienen, y el motivo importa tanto como las que sí:

| Candidata descartada | Motivo del descarte (verificado) |
|---|---|
| **Restore/build duplicado *entre jobs*** | En ADO **cada job corre en un agente limpio**: volver a restaurar no es un defecto, es un requisito de la plataforma. `cd-deploy-test.yml` tiene 3 stages y cada uno necesita lo suyo. La regla dispararía sobre todo pipeline multi-job del mundo. **Falso positivo sistemático.** (OPT002 sobrevive porque acota el caso al **mismo job**, donde la recompilación sí es redundante.) |
| **Jobs serializados que podrían ir en paralelo** | Requiere conocer la dependencia de **datos** real, que el YAML no declara. Y donde importaba, el corpus **ya está paralelo**: `cd-deploy-test.yml:118` y `:157` declaran ambos `dependsOn: Build`; `ci-batch.yml:75` declara `maxParallel: 7`. La regla no tendría a quién avisarle y sí a quién molestar. |
| **Falta de `condition` que evita trabajo inútil** | "Trabajo inútil" es una **intención**, no un hecho verificable en el YAML. Además el corpus usa `condition:` deliberadamente 8 veces (`always()`, `succeededOrFailed()`, `eq(variables['Build.Reason'],...)`). **No falsable ⇒ no es una regla.** |
| **"Artefacto con credenciales adentro"** (genérico) | No se puede abrir un artefacto que todavía no existe. Reemplazada por **SEC005**, que es una cadena causal enteramente verificable dentro del propio YAML. |
| **Secreto literal en el bloque `variables:`** | **Ya es PL012** (`pipeline_lint.py:707`). Duplicarla sería reportar dos códigos para el mismo problema. SEC001 cubre **exclusivamente** la zona que PL012 no recorre. |

### 4.4 Las tres formas de abstención honesta

Una regla que no puede saber algo **no lo inventa y no lo marca**. Tres casos, con implementación
explícita:

1. **Valor dinámico.** `is_dynamic(v)` ⟺ el string contiene `${{` o `$(`. Si la evidencia decisiva
   es dinámica, la regla **se abstiene**. Caso real: `bootstrap-server-environment.yml:117`
   (`pool: name: '${{ parameters.agentPool }}'`) y `:118`
   (`environment: '${{ parameters.targetEnvironment }}'`) — SEC007, SEC008 y OPT003 **no pueden
   saber** si eso es self-hosted ni si es producción, y **callan**.
2. **Abstención contabilizada, no escondida.** Cada abstención suma en
   `AuditReport.undetermined` y agrega una línea a `AuditReport.undetermined_notes`
   (`"SEC008 no pudo evaluar stages[0].jobs[0].environment: valor dinámico"`). El operador ve que la
   auditoría **no vio todo**, sin comerse un hallazgo falso. Esto es lo que separa "silencio honesto"
   de "silencio".
3. **Afirmación acotada.** Cuando el YAML prueba la causa pero no la consecuencia, el mensaje
   **afirma la causa y pregunta la consecuencia** (SEC005: afirma que el `Web.config` va sin
   parametrizar, pregunta si tiene credenciales reales; SEC008: afirma que no se puede verificar
   desde el YAML, pide confirmar a mano).

### 4.5 [ADICIÓN ARQUITECTO] El `repro` obligatorio: la ley que mata la regla inerte (C4)

La Ley de severidad de §3.1 tiene un agujero que la v1 no vio, y es grande justo donde más importa.
De las 12 reglas, **cinco valen 0 sobre el corpus dorado**: SEC001, SEC002, SEC004, SEC007 y SEC008.
Ese cero es **el requisito** que las habilita a `SEV_ERROR`. Pero tiene una consecuencia que se
lee al revés:

> El baseline congelado de F3 **no puede distinguir** una regla que vale 0 porque el corpus está
> limpio, de una regla que vale 0 **porque está rota**. Un typo en `_SECRET_INPUT_KEYS`, un
> `.lower()` olvidado en `_SECURITY_MARKERS` (C12) o un `startswith` mal escrito dejan la regla muda
> para siempre, y **los 8 tests de F3 siguen todos verdes**. Cinco de las ocho reglas de seguridad —
> las cinco de severidad más alta — quedarían certificadas por un test que no las mira.

Una regla de seguridad que nunca dispara no es neutral: es **peor** que no tenerla, porque el
operador ve el panel en verde y concluye que su pipeline está limpio. Es el falso verde del Plan 241
trasplantado a la seguridad, y este plan no puede introducirlo mientras predica contra el falso rojo.

**La solución no se inventa: ya está en la casa.** `pipeline_lint._rule` (`pipeline_lint.py:70-72`)
declara en su propia docstring:

> *"`repro: (provider, yaml_minimo_que_dispara_la_regla)` — **OBLIGATORIO** para toda regla"*

Las 12 reglas SEC/OPT adoptan **ese mismo contrato**:

| Pieza | Definición exacta |
|---|---|
| Registro | `_AUDIT_RULES: dict[str, RuleSpec]` en `cicd_audit_core.py`. Cada regla se registra con el decorador `@audit_rule(code, severity_audit, severity_nl, providers, modes, repro)` |
| `repro` | `tuple[str, str]` = `(provider, yaml_minimo)`. **No puede ser `None`**: el decorador lanza `ValueError` al importar el módulo si falta |
| Meta-test | `test_toda_regla_dispara_sobre_su_repro` (F3): para **cada** entrada de `_AUDIT_RULES`, correr `audit_yaml(spec.repro[1], provider=spec.repro[0])` y exigir **≥1 hallazgo con ese `code`** |
| Contra-test | `test_ningun_repro_dispara_otra_regla_de_seguridad` (F3): el `repro` de una regla no puede disparar **otra** SEC — si lo hace, las dos reglas se solapan y hay que angostar una (es el gate mecánico de la no-duplicación de §4.3) |

**Por qué esto vale más que cualquier regla nueva:** convierte "la regla funciona" de una afirmación
del implementador en un hecho verificado por la máquina, y lo hace **por regla**, no por total.
Cierra la Ley de severidad por su tercer lado: §3.1 exige que `error` ⟺ 0 hits en el corpus, F3
exige que el total sea 0, y §4.5 exige que ese 0 sea **el silencio de un corpus limpio y no el de una
regla muerta**. Cuesta 12 strings de YAML de 4 líneas y no agrega ni una llamada de red, ni un byte
de trabajo al operador, ni una dependencia entre fases: es exactamente el patrón que las 14 reglas
PL ya cumplen desde el Plan 186.

---

## 5. Fases

> Comandos: todos salen del **§4 del dossier**. Recordatorio de la trampa de la casa: en `backend/`
> conviven `backend/.venv` (Python **3.13.5**) y `backend/venv` (3.11.9). **Se usa `.venv`.**
> Los tests backend se corren **siempre por archivo**.

---

### F0 — El contrato de hallazgo y la espina compartida

**Objetivo:** que exista un único formato de hallazgo de auditoría y un único recorrido del YAML,
para que SEC y OPT no puedan divergir entre sí ni del walk que ya usa el Plan 243.
**Valor:** sin esto, F1 y F2 copian el recorrido de `cicd_semantic_rules` y a la tercera corrección
los tres divergen en silencio.

**Archivos:**

- **CREAR** `Stacky Agents/backend/services/cicd_audit_core.py`
- **NADA MÁS.** F0 **no edita ningún archivo existente** (C1).

> ### C1 — Frontera de superficie: por qué F0 ya NO toca `cicd_semantic_rules.py`
>
> La v1 agregaba 4 líneas aditivas a `services/cicd_semantic_rules.py` para publicar el walk.
> **Eso es una colisión con el Plan 249.** El mapa de colisiones de la serie
> (`246_PLAN_INVENTARIO_VIVO_DE_PIPELINES_MULTIPROVEEDOR.md:96`) asigna ese archivo como superficie
> **exclusiva** del 249 —*"249 | … **`services/cicd_semantic_rules.py`** (único plan que lo edita)"*—
> y `:107-109` lo repite: *"Es el único que toca `cicd_semantic_rules.py` … no choca con nadie salvo
> en las 5 superficies universales"*. El orden de merge canónico (`:110`) manda 248/250/251
> **en paralelo**, así que la colisión no es hipotética.
>
> **Sustituto, sin perder nada:** Python no necesita que un símbolo sea público para importarlo.
> `cicd_audit_core.py` hace el alias **de su lado**:
>
> ```python
> # Import del walk canónico del Plan 243. NO se edita cicd_semantic_rules.py:
> # ese archivo es superficie exclusiva del Plan 249 (246 §0.3). El alias vive acá.
> from services.cicd_semantic_rules import (
>     MODE_AUDIT, MODE_NL_STRICT, _MODES, MAX_YAML_BYTES,
>     _iter_steps as iter_steps,      # cicd_semantic_rules.py:105
>     _StepCtx as StepCtx,            # cicd_semantic_rules.py:73-82
> )
> ```
>
> Se conserva íntegro el objetivo original (**una sola verdad sobre pool efectivo y `location`**,
> cero copias del walk) y se elimina el conflicto de merge. El test que lo protege también se
> conserva, invertido: `test_walk_importado_es_el_del_243` verifica
> `cicd_audit_core.iter_steps is cicd_semantic_rules._iter_steps`, de modo que si el 249 renombra o
> cambia ese símbolo, **el 248 se entera con un rojo**, no con una divergencia silenciosa.

> **Nota de nomenclatura (C19).** El 246 §0.3 (`:95`) reserva para el 248 exactamente cinco
> superficies: `services/cicd_security_rules.py`, `services/pipeline_recommendations.py`,
> `api/pipeline_audit.py`, `pipelineAuditModel.ts`, `PipelineAuditPanel.tsx`. La v1 citaba un
> permiso —*"si tu plan necesita un módulo más, prefijalo igual"*— **que no existe en el 246**.
> Los dos módulos extra se justifican por otra vía, verificable: `cicd_audit_core.py` y
> `pipeline_audit_suppressions.py` son archivos **nuevos con nombre no reclamado por ningún plan
> de la serie** (contrastado contra las 7 filas de `246:93-99`), por lo que su creación **no puede
> colisionar con nadie**. Lo que el §0.3 prohíbe es *editar archivo ajeno*, no *crear archivo
> propio*. Si el implementador prefiere cero módulos extra, la alternativa es fusionar
> `cicd_audit_core.py` dentro de `cicd_security_rules.py`: es más grande pero igual de válido.
> **Lo que está prohibido en ambos caminos es tocar `cicd_semantic_rules.py`.**

**Símbolos EXACTOS a crear en `cicd_audit_core.py`:**

```python
"""services/cicd_audit_core.py — Plan 248 F0. Contrato común de la auditoría.

PURO: sin red, sin disco, sin LLM, sin config. Determinista ⇒ paridad trivial en los 3 runtimes.
"""
AUDIT_RULES_VERSION = "248.1"

@dataclass(frozen=True)
class AuditFinding:
    code: str            # "SEC003" | "OPT002"
    severity: str        # SEV_ERROR | SEV_WARNING | SEV_INFO (importados de pipeline_lint)
    message: str         # es-AR, llano, dice POR QUÉ importa
    location: str        # "stages[1].jobs[0].steps[2]" — del walk, NUNCA vacío
    line: int | None     # 1-based sobre el YAML fuente; best-effort
    evidence: str        # el fragmento/valor exacto que la disparó
    remediation: str     # es-AR, imperativo, CÓMO se arregla. NUNCA vacío
    providers: tuple     # ("ado",) | ("ado", "gitlab")

@dataclass(frozen=True)
class AuditReport:
    ok: bool                    # ⟺ counts["error"] == 0
    findings: tuple             # tuple[AuditFinding, ...] ordenada por (line, code)
    counts: dict                # {"error": n, "warning": n, "info": n}
    suppressed: tuple           # hallazgos que existían pero fueron suprimidos (F4)
    undetermined: int           # abstenciones (§4.4)
    undetermined_notes: tuple
    rules_version: str
    mode: str
    duration_ms: float
    def to_dict(self) -> dict: ...

def line_of(lines: list, needle: str, occurrence: int = 1) -> int | None: ...
def is_dynamic(value) -> bool: ...          # "${{" o "$(" en el string
def effective_pool(ctx) -> dict: ...        # delega en el pool ya resuelto por _StepCtx
def pool_is_self_hosted(pool: dict) -> bool: ...   # name presente, vmImage ausente, name NO dinámico
def evidence_fingerprint(code: str, location: str, evidence: str) -> str: ...  # sha256[:16]
def finding(...) -> AuditFinding: ...       # constructor que ASSERTa location y remediation no vacíos

# ── C2 — agrupación por job. NUNCA hacer rsplit(".steps[") a mano. ────────────
def job_key(location: str) -> str:
    """Identidad del job/contenedor de un paso, para las reglas que razonan 'por job'.

    `_iter_steps` emite TRES formas de location (cicd_semantic_rules.py:119, :122, :126):
      "stages[1].jobs[0].steps[2]"        -> "stages[1].jobs[0]"
      "stages[1].deployments[0].steps[2]" -> "stages[1].deployments[0]"
      "steps[2]"   (pasos de RAÍZ)        -> "(root)"     <-- el caso que rompía OPT002

    Un `location.rsplit(".steps[", 1)[0]` crudo devuelve "steps[2]" para el tercer caso,
    es decir UN GRUPO POR PASO, y toda regla 'mismo job' queda muda en los 5 golden de raíz.
    """
    marker = ".steps["
    if marker in location:
        return location.rsplit(marker, 1)[0]
    if location.startswith("steps["):
        return "(root)"
    return location
```

**El walk NO se publica editando el 243** (C1): se importa con alias desde `cicd_audit_core.py`,
según el bloque de la nota de arriba. **Cero archivos ajenos modificados en esta fase.**

**Casos borde cubiertos:** `line_of` con `needle` que no aparece → `None` (nunca lanza);
`is_dynamic(None)` / `is_dynamic(123)` → `False`; `pool_is_self_hosted({"name": "${{ p.x }}"})` →
`False` (dinámico ⇒ abstención, §4.4); `finding()` con `remediation=""` → `AssertionError`
(KPI-2 se hace imposible de violar por construcción, no por revisión);
`job_key("steps[0]") == job_key("steps[7]") == "(root)"` (C2).

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_plan248_audit_core.py`

1. `test_finding_exige_location_y_remediation` — `finding(..., remediation="")` lanza `AssertionError`.
2. `test_line_of_devuelve_none_si_no_esta` y `test_line_of_respeta_occurrence`.
3. `test_is_dynamic_reconoce_ambas_sintaxis` — `${{ }}` y `$( )`; y `False` para no-strings.
4. `test_pool_self_hosted_se_abstiene_con_nombre_dinamico` — el caso `bootstrap-server-environment.yml:117`.
5. `test_walk_importado_es_el_del_243` (C1) — `cicd_audit_core.iter_steps is cicd_semantic_rules._iter_steps`
   **y** `cicd_semantic_rules` no fue modificado: `"iter_steps"` **no** está en su namespace público
   (`assert not hasattr(cicd_semantic_rules, "iter_steps")`). Este segundo assert es el que detecta
   que alguien reintrodujo el diff de la v1 y volvió a chocar con el 249.
6. `test_walk_sobre_cd_deploy_test` — sobre el fixture real, `iter_steps` devuelve los pasos
   de los 2 `- deployment:` con `location` que empieza en `stages[1].deployments[0].steps[` y pool
   `{"name": "TEST-Server"}`.
7. **`test_job_key_agrupa_los_pasos_de_raiz` (C2, el que faltaba)** — los tres casos:
   `job_key("stages[1].jobs[0].steps[2]") == "stages[1].jobs[0]"`,
   `job_key("stages[1].deployments[0].steps[2]") == "stages[1].deployments[0]"`,
   `job_key("steps[0]") == job_key("steps[9]") == "(root)"`.
8. **`test_job_key_sobre_pr_validation_agrupa_todo_junto` (C2)** — sobre el fixture real
   `pr-validation-online.yml` (pasos de raíz, `:36`): `len({job_key(c.location) for c in iter_steps(doc)}) == 1`.
   Es el test que habría atrapado el bug de OPT002 antes de escribir OPT002.

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan248_audit_core.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan243_reglas_semanticas.py -q   # no regresión del 243
```

**Criterio de aceptación BINARIO:** los **8** tests pasan **y** `test_plan243_reglas_semanticas.py`
sigue verde con el mismo número de tests que antes (F0 ya no lo toca, así que el número **debe** ser
idéntico: cualquier cambio ahí significa que se editó el archivo del 249).

**Flag:** ninguna (módulo puro sin consumidor todavía; se cablea en F5).
**Impacto por runtime:** Codex / Claude Code / Copilot — **idéntico**; código puro sin LLM ni red.
Fallback: no aplica (no hay dependencia externa que pueda faltar).
**Trabajo del operador: ninguno.**

---

### F1 — Las 8 reglas SEC

**Objetivo:** emitir los hallazgos de seguridad SEC001..SEC008 con evidencia, línea y remediación.
**Valor:** es la mitad del producto; sola ya detecta los 6 hallazgos reales de §2.2.

**Archivo:** **CREAR** `Stacky Agents/backend/services/cicd_security_rules.py`

**Símbolos EXACTOS:**

```python
SECURITY_RULES_VERSION = "248.1"        # única fuente de versión de SEC; AuditReport.rules_version
                                        # usa AUDIT_RULES_VERSION de cicd_audit_core (C-menor)

_SECURITY_TASKS = frozenset({...})      # tasks de scan conocidas
# C12 — se comparan SIEMPRE contra texto.lower(). `test` va aparte, como PALABRA.
_SECURITY_MARKERS = ("vulnerab", "security", "scan", "audit", "sast", "dependency-check")
_SECURITY_WORD_MARKERS = ("test",)      # re.search(r"\btest\b", texto.lower())
# C5 — `echo` NO está: ya es PL014 (pipeline_lint.py:758). SEC002 cubre sólo lo que PL014 no ve.
_LOG_SINKS = ("write-host", "write-output", "write-debug", "--verbose", "-verbose", "--debug")
_SECRET_INPUT_KEYS = ("arguments", "script", "custom", "msbuildArgs", "connectionString")

def _sec001_secreto_literal(ctxs, doc, lines, provider) -> list: ...
def _sec002_secreto_al_log(ctxs, lines, provider) -> list: ...
def _sec003_imagen_sin_pin(ctxs, lines) -> list: ...
def _sec004_persist_credentials(ctxs, lines, provider) -> list: ...
def _sec005_artefacto_webconfig(doc, ctxs, lines) -> list: ...
def _sec006_fallo_enmascarado(ctxs, lines, provider) -> list: ...
def _sec007_selfhosted_expuesto_a_pr(doc, ctxs, lines) -> list: ...
def _sec008_prod_sin_gate(doc, lines, notes) -> list: ...

def check_security(yaml_text, *, provider, profile, mode=MODE_AUDIT) -> tuple:
    """→ (findings, undetermined_notes). Determinista, sin LLM, sin red.
    `mode` inválido lanza ValueError (falla ruidosa, igual que check_semantics:504)."""
```

**Pseudocódigo de las dos reglas menos obvias:**

```python
# SEC005 — una vez por pipeline, anclada en el Publish
# C11: `location` y `line` DEBEN apuntar al mismo paso. cd-deploy-test.yml tiene 4
# `PublishBuildArtifacts@1` (:99, :106, :144, :183); `line_of(lines, needle)` sin
# `occurrence` devuelve SIEMPRE la primera línea textual, que puede no ser el paso
# que el walk eligió. Se lleva el ordinal del walk y se lo pasa a `occurrence`.
def _sec005_artefacto_webconfig(doc, ctxs, lines):
    tiene_publish, ordinal = None, 0
    for ctx in ctxs:
        if str(ctx.step.get("task") or "").startswith("PublishBuildArtifacts@"):
            ordinal += 1
            if tiene_publish is None:
                tiene_publish = ctx
                publish_ordinal = ordinal
                break
    if tiene_publish is None:
        return []
    for ctx in ctxs:
        if not str(ctx.step.get("task") or "").startswith("VSBuild@"):
            continue
        args = str(_task_inputs(ctx.step).get("msbuildArgs") or "")
        if "DeployOnBuild=true" in args and \
           "AutoParameterizationWebConfigConnectionStrings=false" in args:
            return [finding(code="SEC005", severity=SEV_WARNING, ...,
                            location=tiene_publish.location,
                            line=line_of(lines, "PublishBuildArtifacts@",
                                         occurrence=publish_ordinal),   # C11
                            evidence="AutoParameterizationWebConfigConnectionStrings=false")]
    return []

# C13 — helper único de "pr activo", usado por SEC007 y OPT001. La v1 declaraba en §4.1
# el caso `{branches: {exclude: ['*']}}` y el pseudocódigo NO lo implementaba.
def _pr_esta_activo(doc) -> bool:
    pr = doc.get("pr")
    if pr is None or pr is False:
        return False
    if isinstance(pr, str):
        return pr.strip().lower() != "none"          # `pr: none` => string "none" post safe_load
    if isinstance(pr, dict):
        excl = ((pr.get("branches") or {}) if isinstance(pr.get("branches"), dict) else {}).get("exclude")
        if isinstance(excl, list) and "*" in [str(x) for x in excl] and not (
                (pr.get("branches") or {}).get("include")):
            return False                              # exclude:['*'] sin include => apagado
        return True
    return bool(pr)

# SEC007 — pr activo + pool self-hosted literal
def _sec007_selfhosted_expuesto_a_pr(doc, ctxs, lines):
    if not _pr_esta_activo(doc):
        return []                                    # cd-deploy-test.yml:32 => 0 hallazgos
    out, vistos = [], set()
    for ctx in ctxs:
        if not pool_is_self_hosted(ctx.pool):        # dinámico => abstención (§4.4)
            continue
        if ctx.location in vistos:
            continue
        vistos.add(ctx.location)
        out.append(finding(code="SEC007", severity=SEV_ERROR, ...))
    return out
```

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_plan248_security_rules.py`

**C8 — los 16 tests positivo/negativo, NOMBRADOS uno por uno** (la v1 decía "16" sin nombrarlos, y
un test sin nombre no es un criterio binario). El YAML positivo de cada regla **es su `repro`**
(§4.5): se escribe una sola vez, se registra en el decorador y el test lo consume — no se duplica.

| # | Test positivo (usa el `repro` de la regla) | Test negativo (mismo YAML, sin la condición) |
|---|---|---|
| SEC001 | `test_sec001_positivo_token_literal_en_arguments` | `test_sec001_negativo_valor_corto_no_dispara` |
| SEC002 | `test_sec002_positivo_write_host_con_ref_secreta` | `test_sec002_negativo_echo_lo_cubre_pl014` (C5: con `echo`, SEC002 **no** emite) |
| SEC003 | `test_sec003_positivo_vmimage_latest` | `test_sec003_negativo_vmimage_pineada` |
| SEC004 | `test_sec004_positivo_persist_credentials_true` | `test_sec004_negativo_checkout_sin_persist` |
| SEC005 | `test_sec005_positivo_deploy_sin_parametrizar_con_publish` | `test_sec005_negativo_sin_publish_no_dispara` |
| SEC006 | `test_sec006_positivo_continue_on_error_en_scan` | `test_sec006_negativo_continue_on_error_en_paso_neutro` |
| SEC007 | `test_sec007_positivo_pr_activo_con_pool_selfhosted` | `test_sec007_negativo_pr_none_con_pool_selfhosted` |
| SEC008 | `test_sec008_positivo_environment_produccion_literal` | `test_sec008_negativo_environment_test` |

Más los **3 tests anti-regex** de §2.3, que son los que hacen el plan honesto:

7. `test_environment_produccion_en_comentario_no_dispara_sec008` — sobre `agendaweb-ci.yml` real:
   `SEC008` devuelve **0** pese a que `grep "environment: 'Production'"` da 1 hit (`:154`).
8. `test_connection_string_en_comentario_no_dispara_sec001` — sobre `ci-dacpac.yml` real: **0**
   pese a los 2 hits de texto (`:106`, `:114`).
9. `test_task_machine_group_en_comentario_no_existe` — `extract_task_dicts(agendaweb-ci)` no
   contiene `IISWebAppDeploymentOnMachineGroup@0` (línea de texto `:143`).

Más los 4 hallazgos reales, cada uno contra su fixture y su línea exacta:

10. `test_sec003_dispara_en_ci_dacpac` — 1 hallazgo, `line == 38`, evidence `ubuntu-latest`.
11. `test_sec006_dispara_en_security_scan` — 1 hallazgo, `line == 56`.
12. `test_sec005_dispara_una_vez_por_pipeline` — sobre los 4 fixtures: exactamente 1 por archivo.
13. `test_sec007_no_dispara_en_el_corpus` — 0 sobre los 9 (`pr-validation` es hosted;
    `cd-deploy-test` es `pr: none`).
14. `test_sec008_se_abstiene_con_environment_dinamico` — `bootstrap-server-environment.yml`: 0
    hallazgos y **1** entrada en `undetermined_notes`.
15. `test_mode_invalido_lanza_valueerror`.
16. **`test_sec006_matchea_display_name_con_acento_y_mayuscula` (C12)** — sobre
    `security-scan-online.yml` real, cuyo `displayName` es
    `'dotnet list — Vulnerabilidades en proyectos SDK-style'` (`:55`): SEC006 emite **1** hallazgo.
    Sin `.lower()` la regla da 0 y queda inerte; este test lo convierte en rojo.
17. **`test_sec006_no_matchea_latest_como_test` (C12)** — un paso con
    `displayName: 'Publicar imagen latest'` y `continueOnError: true` ⇒ **0** hallazgos
    (`test` es palabra, no substring).
18. **`test_sec005_line_y_location_apuntan_al_mismo_publish` (C11)** — sobre `cd-deploy-test.yml`
    (4 `PublishBuildArtifacts@1`): el `line` del hallazgo cae dentro del rango de líneas del paso
    identificado por su `location`; concretamente `line == 99` **y**
    `location.startswith("stages[0].")`.

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan248_security_rules.py -q
```

**Criterio de aceptación BINARIO:** los **28** tests pasan (16 nombrados de la tabla + los 12
numerados). En particular, los 3 tests anti-regex (7, 8, 9) devuelven **0 hallazgos** sobre archivos
donde `grep` da hits, y el 16 devuelve **1** sobre un `displayName` con mayúscula y acento.

**Flag:** protegida por `STACKY_PIPELINE_AUDIT_ENABLED` en el borde (F5); el servicio no lee config.
**Impacto por runtime:** idéntico en los 3 (puro). Fallback: no aplica.
**Trabajo del operador: ninguno.**

---

### F2 — Las 4 reglas OPT

**Objetivo:** emitir las recomendaciones de eficiencia OPT001..OPT004.
**Valor:** convierte la auditoría en algo que además **ahorra tiempo de agente**, no sólo que reta.

**Archivo:** **CREAR** `Stacky Agents/backend/services/pipeline_recommendations.py`

**Símbolos EXACTOS:**

```python
RECOMMENDATION_RULES_VERSION = "248.1"

_RESTORE_TASKS = {"NuGetCommand@2": "restore", "DotNetCoreCLI@2": "restore"}
_BUILD_TASKS = ("VSBuild@1", "MSBuild@1")

def _opt001_restore_sin_cache(doc, ctxs, lines) -> list: ...
def _opt002_recompilacion_en_tests(ctxs, lines) -> list: ...
def _opt003_selfhosted_sin_timeout(doc, ctxs, lines, notes) -> list: ...
def _opt004_checkout_historial_completo(ctxs, lines, provider) -> list: ...

def check_recommendations(yaml_text, *, provider, mode=MODE_AUDIT) -> tuple:
    """→ (findings, undetermined_notes). Sólo evalúa en MODE_AUDIT: una recomendación de
    eficiencia sobre un YAML que Stacky acaba de generar es ruido — el generador ya emite
    la forma buena por construcción. En MODE_NL_STRICT devuelve ((), ())."""
```

**Pseudocódigo de OPT002 (la que exige el "mismo job") — CORREGIDO (C2):**

> **C2, el bloqueante que este pseudocódigo tenía.** La v1 agrupaba con
> `ctx.location.rsplit(".steps[", 1)[0]`. `_iter_steps` emite `"steps[%d]"` para los pasos de raíz
> (`cicd_semantic_rules.py:126`), **sin** el segmento `.steps[`, así que ese `rsplit` devuelve el
> location entero ⇒ **un grupo por paso** ⇒ `hubo_build` nunca se activa. Cinco de los nueve golden
> son de raíz (`agendaweb-ci.yml:35`, `pr-validation-online.yml:36`, `ci-batch.yml:77`,
> `ci-dacpac.yml:40`, `security-scan-online.yml:42`). Efecto medido sobre el corpus: OPT002 habría
> dado **2 hallazgos, no 3** (se perdía `pr-validation-online.yml:61`), y —peor— `agendaweb-ci`, que
> es el **control negativo** de la fase, habría dado 0 **por el bug y no por su `--no-build`**:
> un falso verde en el test capstone, en el plan que existe para matar los falsos. Se usa
> `job_key()` de F0, y su test dedicado (`test_job_key_agrupa_los_pasos_de_raiz`) corre **antes**.

```python
def _opt002_recompilacion_en_tests(ctxs, lines):
    out = []
    por_job = {}
    for ctx in ctxs:
        por_job.setdefault(job_key(ctx.location), []).append(ctx)   # C2 — NUNCA rsplit crudo
    for _job, pasos in sorted(por_job.items()):
        hubo_build = False
        for ctx in pasos:
            ref = str(ctx.step.get("task") or "")
            inputs = _task_inputs(ctx.step)
            if ref in _BUILD_TASKS or (ref.startswith("DotNetCoreCLI@")
                                       and inputs.get("command") == "build"):
                hubo_build = True
                continue
            if not (ref.startswith("DotNetCoreCLI@") and inputs.get("command") == "test"):
                continue
            if hubo_build and "--no-build" not in str(inputs.get("arguments") or ""):
                out.append(finding(code="OPT002", severity=SEV_INFO, ...,
                                   location=ctx.location,
                                   evidence="command: test sin --no-build"))
    return out
```

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_plan248_recommendations.py`

**C8 — los 8 tests positivo/negativo, NOMBRADOS** (el positivo consume el `repro` de la regla, §4.5):

| # | Positivo | Negativo |
|---|---|---|
| OPT001 | `test_opt001_positivo_pr_con_restore_sin_cache` | `test_opt001_negativo_con_cache_no_dispara` |
| OPT002 | `test_opt002_positivo_build_y_test_en_el_mismo_job` | `test_opt002_negativo_con_no_build` |
| OPT003 | `test_opt003_positivo_selfhosted_sin_timeout` | `test_opt003_negativo_con_timeout_en_el_stage` |
| OPT004 | `test_opt004_positivo_checkout_explicito_sin_fetchdepth` | `test_opt004_negativo_con_fetchdepth_1` |

Más los recuentos exactos contra el corpus real:

9. `test_opt001_dispara_en_los_3_pipelines_de_pr` — `{ci-batch, ci-dacpac, pr-validation-online}`,
   y **no** en `security-scan-online` (no tiene restore) ni en `agendaweb-ci`/`nightly` (`pr: none`).
   *(Verificado en la crítica: los tres declaran `command: 'restore'` explícito —`ci-batch.yml:88`,
   `ci-dacpac.yml:53`, `pr-validation-online.yml:47`— así que la condición literal de §4.2 se
   sostiene y no hace falta asumir el default de `NuGetCommand@2`.)*
10. **`test_opt002_dispara_en_pr_validation_online` (C2, el test que la v1 no tenía)** — sobre
    `pr-validation-online.yml`, que es de **raíz** (`:36`) con `VSBuild@1` en `:52` y
    `DotNetCoreCLI@2 command:'test'` en `:61`: exactamente **1** hallazgo. **Con el `rsplit` de la v1
    este test da 0.** Es el gate del bloqueante.
11. `test_opt002_no_dispara_en_agendaweb_ci` — el control negativo del corpus: tiene `--no-build`
    (`:80`) ⇒ 0 hallazgos. **Y para que ese 0 signifique algo** (C2), el mismo test verifica que el
    grupo existe y contiene el build: `job_key` de todos sus pasos == `"(root)"` y el `VSBuild@1`
    (`:56`) cae en ese grupo. Sin este segundo assert, el test pasa en verde aunque la regla esté muda.
12. `test_opt003_dispara_solo_en_cd_deploy_test` — exactamente 2 (`:123`, `:162`), y se **abstiene**
    en `bootstrap-server-environment.yml` (pool dinámico) sumando 1 a `undetermined`.
13. `test_opt004_ignora_el_checkout_implicito` — sobre `ci-cd-online.yml` (sin `- checkout:`
    explícito) ⇒ **0**; sobre `cd-deploy-test.yml` ⇒ **2** (`:130`, `:169`).
14. `test_recommendations_no_evalua_en_nl_strict` — `check_recommendations(..., mode=MODE_NL_STRICT)`
    devuelve `((), ())` para los 9 fixtures.

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan248_recommendations.py -q
```

**Criterio de aceptación BINARIO:** los **22** tests pasan (8 nombrados + 14 numerados), con los
recuentos **exactos** por regla: **OPT001 = 3, OPT002 = 3, OPT003 = 2, OPT004 = 3**. Un recuento
distinto significa que la regla se ensanchó o se angostó de más: se corrige la regla, **no** el test.

**Flag:** `STACKY_PIPELINE_AUDIT_ENABLED` en el borde (F5).
**Impacto por runtime:** idéntico en los 3 (puro). Fallback: no aplica.
**Trabajo del operador: ninguno.**

---

### F3 — El orquestador y el baseline congelado (el gate anti-falso-positivo)

**Objetivo:** una sola función `audit_yaml()` que compone SEC + OPT, y un baseline revisado a mano
que hace **imposible** que una regla se ensanche en silencio.
**Valor:** es lo que convierte KPI-1 en un gate binario en vez de una intención.

**Archivos:**

- **EDITAR** `Stacky Agents/backend/services/cicd_audit_core.py` (agregar `audit_yaml`)
- **CREAR** `Stacky Agents/backend/tests/fixtures/cicd_nl/audit_baseline.json`

```python
def audit_yaml(yaml_text: str, *, provider: str, profile: str = PROFILE_DOTNET_FRAMEWORK,
               mode: str = MODE_AUDIT, pipeline_key: str | None = None,
               suppressions: list | None = None) -> AuditReport:
    """SEC + OPT sobre un pipeline. Determinista, sin LLM, sin red.

    Guardias, en orden (copiadas de check_semantics:497-524):
      - mode no en _MODES            -> ValueError
      - len(yaml_text) > MAX_YAML_BYTES -> AuditReport con 1 warning "AUD000", sin analizar
      - YAMLError                    -> AuditReport con 1 warning "AUD000"
      - doc no es dict               -> AuditReport vacío ok=True
    Las supresiones se aplican DESPUÉS de calcular todo: un hallazgo suprimido va a
    `suppressed`, nunca desaparece del cómputo (F4).
    """
```

**El baseline y su regla de oro.** `audit_baseline.json` es una lista de filas
`{file, code, location, line, severity, evidence_fingerprint, veredicto}` — una por hallazgo de la
auditoría sobre los 9 golden en `MODE_AUDIT`.

> **C6 — el generador NO va dentro de `cicd_audit_core.py`.** La v1 mandaba
> `python -m services.cicd_audit_core --emit-baseline`, lo que contradice de frente el docstring que
> el propio F0 le pone al módulo (*"PURO: sin red, sin disco, sin LLM, sin config"*): un `__main__`
> que lista un directorio, abre 9 archivos y escribe un JSON **es** disco. Además la v1 no decía
> dónde escribe ni con qué cwd. **Fix:** el generador vive en el archivo de test, que es quien ya
> tiene permiso de tocar disco y ya sabe resolver el corpus con el patrón de
> `cicd_corpus_mirror.py:47-52`. Comando exacto, con la ruta exacta:
>
> ```powershell
> cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
> $env:STACKY_EMIT_AUDIT_BASELINE = "1"
> .venv\Scripts\python.exe -m pytest tests/test_plan248_audit_baseline.py -q -k emit
> Remove-Item Env:\STACKY_EMIT_AUDIT_BASELINE
> ```
>
> `test_emit_baseline` hace `pytest.skip("solo con STACKY_EMIT_AUDIT_BASELINE=1")` cuando la env var
> no está, así que en una corrida normal **no escribe nada** y el módulo de producción sigue puro.

Generado el archivo, **se revisa a mano**, escribiendo en cada fila `"veredicto": "REAL"` o
`"veredicto": "FALSO_POSITIVO"`.

> **Gate binario de la fase, y el punto entero del plan:** si el baseline revisado contiene **una
> sola** fila `FALSO_POSITIVO`, **la fase no está terminada**. La corrección es **angostar la
> regla** hasta que esa fila desaparezca. Está explícitamente **prohibido** marcar la fila como
> "aceptada", subirle el umbral al test, o suprimirla con el mecanismo de F4 — la supresión es para
> el operador sobre **sus** pipelines, no para el implementador sobre **su propio ruido**.

**Baseline esperado según el análisis de §4 (8 archivos leídos):** **16 hallazgos, 0 de severidad
`error`** — SEC003 ×1, SEC005 ×4, SEC006 ×1, OPT001 ×3, OPT002 ×3, OPT003 ×2, OPT004 ×2, más las
filas de `bootstrap-server-environment.yml` (OPT004 ×1 esperada; el resto lo determina el
generador, porque ese archivo **no fue abierto completo** — §2.6). **Si el generador produce un
número distinto para los 8 archivos leídos, hay un bug en las reglas de F1/F2, no en este plan.**

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_plan248_audit_baseline.py`

1. `test_baseline_congelada` — `audit_yaml` sobre los 9 golden == `audit_baseline.json`, comparando
   la tupla `(file, code, location, line, severity)` exacta.
2. `test_ley_de_severidad` — **el capstone.** Para los 9 golden en `MODE_AUDIT`:
   `report.counts["error"] == 0`. Es el análogo directo de `test_corpus_dorado_sin_errores` del 243
   y la verificación mecánica de §3.1.
3. `test_baseline_sin_falsos_positivos` — ninguna fila del JSON tiene `veredicto != "REAL"`.
4. `test_toda_regla_error_tiene_cero_hits` — recorre las 12 reglas: si su severidad en `MODE_AUDIT`
   es `SEV_ERROR`, su recuento sobre los 9 golden debe ser 0. Cierra la ley por el otro lado: no
   alcanza con que el total sea 0 hoy, tiene que ser 0 **por regla**.
5. `test_todo_hallazgo_tiene_ancla_y_remediacion` — KPI-2: para las 16 filas,
   `location != ""` y `remediation != ""`.
6. `test_auditoria_funciona_sin_246_ni_247` — con ambos imports forzados a `ImportError`, el
   baseline es idéntico (§2.5).
7. `test_yaml_gigante_no_cuelga` — 600 KB ⇒ 1 warning `AUD000`, sin analizar.
8. `test_yaml_roto_no_lanza` — YAML inválido ⇒ 1 warning `AUD000`, `ok=True`.
9. **`test_toda_regla_dispara_sobre_su_repro` (C4, [ADICIÓN ARQUITECTO], §4.5) — el capstone que
   faltaba.** Para **cada** entrada de `_AUDIT_RULES`: `audit_yaml(spec.repro[1], provider=spec.repro[0], mode=spec.modes[0])`
   devuelve **≥1 hallazgo con `code == spec.code`**. Sin este test, las 5 reglas que valen 0 sobre el
   corpus (SEC001, SEC002, SEC004, SEC007, SEC008) están certificadas por un baseline que no las mira.
10. **`test_toda_regla_declara_repro` (C4)** — `_AUDIT_RULES` tiene exactamente **12** entradas y
    ninguna con `repro is None`. Es el gate que impide agregar una regla 13 sin su reproductor.
11. **`test_ningun_repro_dispara_otra_regla_de_seguridad` (C4/C5)** — el `repro` de cada regla
    produce hallazgos de **un solo** `code` de la familia SEC. Es el gate mecánico de la
    no-duplicación de §4.3: si el `repro` de SEC002 también dispara SEC001, las dos se solapan.
12. **`test_sec002_no_duplica_pl014` (C5)** — el YAML `- script: echo $(API_KEY)` pasa por
    `pipeline_lint.lint_yaml` **y** por `check_security`: PL014 emite 1 hallazgo, **SEC002 emite 0**.
    Dos códigos para el mismo hecho es exactamente lo que §4.3 prohíbe.

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan248_audit_baseline.py -q
```

**Criterio de aceptación BINARIO:** los **12** tests pasan **y** `audit_baseline.json` tiene
`veredicto == "REAL"` en el 100% de sus filas. El 9 y el 10 son innegociables: sin ellos, el plan
entrega un panel de seguridad que puede estar mudo y verde a la vez.

**Flag:** `STACKY_PIPELINE_AUDIT_ENABLED` en el borde (F5).
**Impacto por runtime:** idéntico. El baseline es un archivo versionado, no depende del runtime.
**Trabajo del operador: ninguno.** (La revisión del baseline la hace **el implementador**, una vez,
antes de cerrar la fase — no el operador.)

---

### F4 — Supresiones que persisten pero no ciegan

**Objetivo:** que el operador archive un hallazgo que ya evaluó, con motivo escrito, y que esa
decisión **caduque sola** si la evidencia cambia.
**Valor:** sin esto, SEC006 le grita al operador sobre `security-scan-online.yml:56` para siempre y
la auditoría entera se vuelve ruido que se ignora.

**Archivo:** **CREAR** `Stacky Agents/backend/services/pipeline_audit_suppressions.py`

Patrón **copiado** de `ci_run_ledger.py` (`:29` `_ledger_path`, `:18` `MAX_ROWS`, `:61` `_clean_entry`):

```python
ENTRY_FIELDS = ("pipeline_key", "code", "location", "evidence_fingerprint",
                "reason", "created_at", "created_by")
MAX_ROWS = 500

def _ledger_path() -> Path:
    return Path(runtime_paths.data_dir()) / "pipeline_audit_suppressions.jsonl"

def add_suppression(entry: dict) -> None: ...   # reason vacío -> ValueError (HITL, sin excepción)
def list_suppressions(pipeline_key: str | None = None) -> list: ...
def remove_suppression(pipeline_key: str, code: str, location: str) -> bool: ...
def apply_suppressions(findings: tuple, suppressions: list) -> tuple:
    """→ (visibles, suprimidos). Una supresión matchea SOLO si coinciden los CUATRO:
    pipeline_key, code, location y evidence_fingerprint."""
```

**La decisión de diseño que importa** — por qué el `evidence_fingerprint` es parte de la clave:

> Una supresión por `(pipeline_key, code, location)` sola sería una **venda**: el operador suprime
> hoy el `continueOnError: true` del escaneo de vulnerabilidades porque el script hace el gate por
> dentro; el año que viene alguien cambia ese paso y la supresión **sigue tapando** un hallazgo que
> ya no es el mismo. Con el fingerprint incluido, cualquier cambio en la evidencia (`sha256` del
> triple `code|location|evidence`) hace que la supresión **deje de matchear** y el hallazgo
> **reaparece**. Es la misma disciplina de `docs/sistema/error_fingerprints.json`: una decisión
> vale para el hecho que se evaluó, no para el lugar donde estaba.

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_plan248_suppressions.py` (con `tmp_path`
monkeypatcheando `runtime_paths.data_dir`; **nunca** escribe en el data dir real)

1. `test_reason_vacio_es_rechazado` — `add_suppression({... "reason": ""})` ⇒ `ValueError`.
2. `test_supresion_oculta_el_hallazgo` — SEC006 sobre `security-scan-online.yml` pasa de `findings`
   a `suppressed`; `counts` no lo cuenta.
3. `test_supresion_caduca_si_cambia_la_evidencia` — **el test que justifica el diseño**: se suprime
   SEC006, se muta el YAML (`continueOnError: true` → un paso distinto con otro `displayName`), y el
   hallazgo **reaparece** en `findings`.
4. `test_supresion_no_derrama_a_otra_pipeline` — misma `code`+`location` en otro `pipeline_key` ⇒
   sigue visible.
5. `test_retencion_500` — la fila 501 expulsa la más vieja.
6. `test_remove_suppression_devuelve_false_si_no_existe`.
7. `test_ledger_corrupto_no_rompe_la_auditoria` — JSONL con una línea inválida ⇒ se ignora esa fila
   y la auditoría corre igual.

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan248_suppressions.py -q
```

**Criterio de aceptación BINARIO:** los 7 tests pasan; en particular el 3, que es el que distingue
una supresión de una venda.

**Flag:** `STACKY_PIPELINE_AUDIT_ENABLED`.
**Impacto por runtime:** idéntico; JSONL local, sin red.
**Trabajo del operador: ninguno** para auditar. Suprimir es **opt-in explícito con motivo escrito** —
y es la única acción del plan entero que requiere una decisión humana, por diseño (§3.3).

---

### F5 — Blueprint, flag y cableado

**Objetivo:** exponer la auditoría por HTTP detrás de la flag, con guard per-request.
**Valor:** sin esto nada de F0–F4 es alcanzable desde la UI.

**Archivos:**

- **CREAR** `Stacky Agents/backend/api/pipeline_audit.py`
- **EDITAR** `Stacky Agents/backend/api/__init__.py` (2 líneas: import junto a `:44`, registro junto a `:117`)
- **EDITAR** `Stacky Agents/backend/services/harness_flags.py` (`FlagSpec` + entrada en `_CATEGORY_KEYS`, `:120`)
- **EDITAR** `Stacky Agents/backend/tests/test_harness_flags.py` (`_CURATED_DEFAULTS_ON`, `:467`)
- **EDITAR** `Stacky Agents/backend/config.py` (atributo, patrón de `:516-517`)
- **EDITAR** `Stacky Agents/backend/scripts/run_harness_tests.sh` y `.ps1` (**las DOS listas**)
- **EDITAR** `Stacky Agents/backend/api/devops.py` (**C3/C9**) — **1 key al final del dict de
  `_health_payload`** (`:28`), junto a `cockpit_enabled` / `build_workshop_enabled` /
  `dev_build_verify_enabled`:
  ```python
  "pipeline_audit_enabled": bool(
      getattr(cfg, "STACKY_PIPELINE_AUDIT_ENABLED", False)
  ),  # Plan 248 — auditoría de pipelines (read-only)
  ```
  Este es el camino canónico de los paneles DevOps (`/api/devops/health`), y es la superficie que el
  246 §0.3 (`:85`) le asigna a este plan. **La v1 decía `/api/diag/health`, que no es donde vive
  este contrato.**

```python
# api/pipeline_audit.py — patrón EXACTO de api/pipeline_generator.py:1-26
bp = Blueprint("pipeline_audit", __name__, url_prefix="/pipeline-audit")

def _guard():
    from config import config          # GOTCHA: la INSTANCIA, no el módulo (dossier §3)
    if not getattr(config, "STACKY_PIPELINE_AUDIT_ENABLED", False):
        abort(404)                     # guard PER-REQUEST, nunca en el registro del blueprint
```

| Método | Ruta final | Body / Query | Respuesta |
|---|---|---|---|
| `POST` | `/api/pipeline-audit/scan` | `{yaml, provider, profile?, mode?, pipeline_key?}` | `AuditReport.to_dict()` |
| `GET` | `/api/pipeline-audit/suppressions` | `?pipeline_key=` | `{items: [...]}` |
| `POST` | `/api/pipeline-audit/suppress` | `{pipeline_key, code, location, evidence_fingerprint, reason}` | `201` / `400` si falta `reason` |
| `DELETE` | `/api/pipeline-audit/suppress` | `{pipeline_key, code, location}` | `200 {removed: bool}` |

**La flag, completa:**

```python
FlagSpec(
    key="STACKY_PIPELINE_AUDIT_ENABLED",
    type="bool",
    default=True,   # default ON: NINGUNA de las 4 excepciones duras aplica — es read-only,
                    # sin red, sin LLM, no publica nada y no reduce la seguridad por default.
                    # Curada en _CURATED_DEFAULTS_ON (test_harness_flags.py:467).
    label="Auditoría de pipelines",
    description=(
        "Plan 248 - audita pipelines existentes: riesgos de seguridad (SEC001..SEC008) y "
        "recomendaciones de optimización (OPT001..OPT004). Read-only: detecta y explica, "
        "nunca aplica cambios. OFF: el panel de auditoría desaparece y /api/pipeline-audit/* "
        "devuelve 404; el lint PL001..PL014 y las reglas RS001..RS009 siguen idénticos."
    ),
    group="global",
),
```

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_plan248_api.py`

1. `test_scan_devuelve_report` — POST con `cd-deploy-test.yml` ⇒ 200 con los hallazgos del baseline.
2. `test_flag_off_da_404` — con la flag OFF, las 4 rutas devuelven 404. **Se hace con la INSTANCIA**
   (`monkeypatch.setattr(config.config, "STACKY_PIPELINE_AUDIT_ENABLED", False)`); parchear el
   módulo devuelve el default y el test pasaría en falso (gotcha del dossier §3).
3. `test_suppress_sin_reason_da_400`.
4. `test_suppress_y_scan_devuelve_suprimido` — round-trip completo.
5. `test_yaml_faltante_da_400`.
6. `test_provider_invalido_da_400`.
7. **`test_health_expone_la_flag` (C3/C9)** — `GET /api/devops/health` incluye la key
   `pipeline_audit_enabled` con valor `True`; con la flag apagada en la **instancia**, `False`.

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan248_api.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q        # tras tocar harness_flags
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q # tras crear test_*.py
```

> **C7 — el baseline de los dos gates está MEDIDO, no supuesto.** Corridos el 2026-07-26 con
> `backend\.venv` (Python 3.13.5), **sobre el árbol de esta rama y antes de tocar nada**:
>
> | Comando | Resultado medido HOY |
> |---|---|
> | `pytest tests/test_harness_flags.py -q` | **56 passed** (VERDE, 0 fallos) |
> | `pytest tests/test_harness_ratchet_meta.py -q` | **4 passed** (VERDE) |
>
> La v1 decía *"`test_harness_flags.py` sin fallos **nuevos** respecto de los 4 ajenos conocidos"*.
> **Eso relaja un gate que hoy está 100% verde** y habilita el peor final posible: romper
> `test_harness_flags.py` con la flag nueva y atribuirlo a una deuda ajena que en este archivo **no
> existe**. (Los 4 fallos ajenos son de `test_harness_flags_help`, que es **otro archivo** y **no**
> está en la lista de comandos de esta fase.) El criterio pasa a ser un **número exacto**.

**Criterio de aceptación BINARIO:**
- Los **7** tests de `test_plan248_api.py` pasan.
- `pytest tests/test_harness_flags.py -q` ⇒ **56 passed, 0 failed**. La flag nueva **no agrega
  tests**: el gate de curación es una igualdad de conjuntos, así que se valida dentro de los 56 que
  ya existen. **Cualquier `failed`, o un `passed` menor a 56, es rojo propio.**
- `pytest tests/test_harness_ratchet_meta.py -q` ⇒ **4 passed**, con los **6** archivos
  `test_plan248_*.py` registrados en **ambas** listas (C14: son 6, no 5 — ver DoD).

**Flag:** `STACKY_PIPELINE_AUDIT_ENABLED`, **default ON**.
**Impacto por runtime:** idéntico en los 3 (endpoint Flask determinista). Fallback: si 246/247 no
existen, `pipeline_key` y `profile` se resuelven por default (§2.5) y la ruta sigue respondiendo 200.
**Trabajo del operador: ninguno** (opt-in, default ON).

---

### F6 — El panel

> **Nota de alcance (§3.5):** el dossier permite hasta 6-7 fases; F0..F5 son las 6 que entran con
> seguridad en una corrida. **F6 es la séptima y es opcional dentro de esta corrida**: si el
> implementador llega con presupuesto, la hace; si no, **F0..F5 ya entregan valor completo por API**
> y F6 se mueve tal cual está escrita acá. No se recorta el contenido de F6: se mueve entera o se
> hace entera — **y "entera" ahora incluye sus tres ediciones de montaje** (C3). Lo que **no** se
> mueve es la key de health de F5: esa va sí o sí, porque es la superficie compartida que el 246
> §0.3 (`:85`) le asigna a este plan y postergarla sólo mueve el conflicto de merge al futuro.
>
> **Regla dura si F6 se mueve:** entonces **no se crean** `pipelineAuditModel.ts` ni
> `PipelineAuditPanel.tsx`. Está prohibido dejar los dos archivos creados "listos para cablear":
> eso es precisamente el código muerto de C3.

**Objetivo:** mostrar los hallazgos agrupados por severidad, con el YAML anclado por línea y el
botón de suprimir con motivo.

**Archivos:**

- **CREAR** `Stacky Agents/frontend/src/devops/pipelineAuditModel.ts` (**puro**, toda la lógica)
- **CREAR** `Stacky Agents/frontend/src/components/devops/PipelineAuditPanel.tsx` (**sólo render**)
- **EDITAR** `Stacky Agents/frontend/src/api/endpoints.ts` (**C3**) — un `export const PipelineAudit = {...}`
  **al final del archivo**, con los 4 métodos de la tabla de F5. Patrón y vecinos verificados:
  `:3818` (`export const DevOps`), `:4193` (`export const DevOpsBuildWorkshop`). **Ojo con el
  wrapper:** `api.get`/`api.post` **lanzan** en cualquier respuesta no-2xx, así que el 404 de la
  flag apagada debe manejarse con el camino crudo, no con un `catch` mudo.
- **EDITAR** `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` (**C3**) — tres puntos exactos:
  1 key `pipeline_audit_enabled?: boolean` en `interface DevOpsHealth` (`:32`), 1 import del panel,
  y **1 entrada nueva al final de `DEVOPS_SECTIONS`** (`:113`) con
  `healthKey: 'pipeline_audit_enabled'` y `gateFlagKey: 'STACKY_PIPELINE_AUDIT_ENABLED'`.

> ### C3 — por qué estas dos ediciones dejaron de ser opcionales
>
> La v1 creaba los dos archivos del panel y **ningún call site**. Eso no es "una fase corta": es
> código muerto que pasa sus propios tests. Es exactamente lo que dejó **inertes dos fases enteras
> del Plan 176** (módulo testeado, sin consumidor, descubierto recién al correrlo). Además, las tres
> superficies son las que el 246 §0.3 (`:80-87`) le asignó a este plan, así que omitirlas no evita
> la colisión de merge: sólo la posterga.

Espeja el estilo de `frontend/src/components/devops/pipelineLint.ts:13-29` (tipos) y `:61`
(`groupFindings`), **sin modificar ese archivo**:

```ts
export type AuditSeverity = 'error' | 'warning' | 'info';
export interface AuditFinding { code, severity, message, location, line, evidence,
                                remediation, providers, evidence_fingerprint }
export interface AuditReport  { ok, findings, counts, suppressed, undetermined,
                                undetermined_notes, rules_version, mode, duration_ms }

export function groupAuditFindings(fs: AuditFinding[]): GroupedAudit;   // error/warning/info
export function auditSummary(r: AuditReport | null): { tone, text };    // es-AR, 1 línea
export function familyOf(code: string): 'seguridad' | 'optimizacion';   // SEC* / OPT*
export function canSuppress(f: AuditFinding, reason: string): boolean;  // reason.trim() !== ''
```

**Contrato UX obligatorio.** La auditoría es **read-only**: el panel muestra `remediation` como
**texto**, y **no** ofrece ningún botón de "arreglar" — aplicar es el **Plan 250** (dossier §1).
El único botón que escribe algo es "Suprimir", y está **deshabilitado hasta que el motivo tenga
texto** (`canSuppress`), coherente con el HITL del panel (Plan 106 F5,
`PipelineBuilderSection.tsx:382-383`). Si `undetermined > 0`, el panel muestra
`undetermined_notes` en un bloque "La auditoría no pudo evaluar N puntos" — la abstención se ve,
no se esconde (§4.4).

**Tests PRIMERO:** `Stacky Agents/frontend/src/devops/__tests__/pipelineAuditModel.test.ts`

1. `groupAuditFindings` ordena por `(line, code)` y separa las 3 severidades.
2. `familyOf('SEC003') === 'seguridad'`, `familyOf('OPT002') === 'optimizacion'`.
3. `auditSummary(null)` ⇒ tono `none`; con 0 hallazgos ⇒ `ok`; con warnings ⇒ `warn`.
4. `canSuppress` es `false` con `reason` vacío o sólo espacios.
5. `auditSummary` menciona `undetermined` cuando es > 0.
6. **`test_seccion_registrada_en_devops_sections` (C3)** — `DEVOPS_SECTIONS` contiene exactamente
   una entrada con `id === 'pipeline-audit'` y su `healthKey === 'pipeline_audit_enabled'`.
   Es el test que hace imposible repetir el "módulo sin call site" del Plan 176.

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/devops/__tests__/pipelineAuditModel.test.ts
npx tsc --noEmit
```

> **Gate real del panel (RTL/jsdom no está instalado en este repo):** el render no es automatizable.
> El criterio verificable es `npx tsc --noEmit` limpio + el test 6 (registro declarativo) + un smoke
> visual manual del operador. Se declara así en vez de prometer un test de render que no puede correr.

**Criterio de aceptación BINARIO:** los **6** tests pasan y `npx tsc --noEmit` sale limpio.
**Flag:** el panel se monta sólo si **`/api/devops/health`** reporta `pipeline_audit_enabled: true`
(C9: la v1 decía `/api/diag/health`).
**Impacto por runtime:** idéntico (frontend, sin LLM).
**Trabajo del operador: ninguno** (opt-in, default ON).

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Severidad | Mitigación (concreta, dentro del plan) |
|---|---|---|---|
| R1 | **Falso rojo**: una regla marca producción y el operador deja de mirar la auditoría | **Alta** | Ley de severidad (§3.1) + baseline congelado con veredicto `REAL` por fila + `test_toda_regla_error_tiene_cero_hits` (F3). Es el riesgo que gobierna el diseño entero |
| R2 | La supresión se vuelve una venda permanente | Alta | `evidence_fingerprint` en la clave: la supresión caduca sola al mutar la evidencia. `test_supresion_caduca_si_cambia_la_evidencia` (F4) |
| R3 | Una regla se ensancha en una corrección futura y nadie lo nota | Alta | `test_baseline_congelada` compara la tupla exacta: cualquier hallazgo nuevo o corrido de línea rompe el test y obliga a una decisión consciente |
| R4 | Duplicar PL012/PL014 y reportar el mismo problema con dos códigos | Media | SEC001 y SEC002 están definidas **por la zona que PL no recorre** (§4.1), con el anclaje del código PL exacto que lo prueba (`_ado_declared:637`, `_rule_pl014:752`) |
| R5 | Se cuela un `grep` en alguna regla y aparecen los 8 falsos positivos de §2.3 | Media | Los 3 tests anti-regex de F1 (casos 7, 8, 9) fallan si eso pasa |
| R6 | Los anclajes se desfasan como en el 243 C16 | Media | Todo anclaje de este doc lleva **símbolo + línea** (§2.1) y está expresado sobre el **fixture**, con la corrección +1 documentada en §2.4 |
| R7 | 246/247 no están implementados y F5 rompe | Media | Degradación explícita (§2.5) + `test_auditoria_funciona_sin_246_ni_247` (F3) |
| R8 | El plan no entra en una corrida (el 243 se partió por esto, C25) | Media | 6 fases duras + F6 declarada movible **entera** (§F6) + 5 candidatas ya descartadas (§4.3) |
| R9 | `bootstrap-server-environment.yml` produce hallazgos inesperados en el baseline | Baja | Declarado en §2.6: sus filas las genera el script y las revisa el implementador; el plan **no** afirma su recuento |
| R10 | Un test escribe en el JSONL real del operador | Baja | F4 exige `tmp_path` + monkeypatch de `runtime_paths.data_dir` en **todos** sus tests |
| **R11** | **Una regla de seguridad queda INERTE (0 hits por bug, no por corpus limpio) y el panel muestra verde falso** | **Alta** (C4) | `repro` obligatorio (§4.5) + `test_toda_regla_dispara_sobre_su_repro` y `test_toda_regla_declara_repro` (F3). Es el riesgo que la v1 no vio y que afecta a **5 de las 8 reglas SEC** |
| **R12** | **Colisión de merge con el 249 sobre `cicd_semantic_rules.py`** | **Alta** (C1) | F0 ya no lo edita; `test_walk_importado_es_el_del_243` incluye `assert not hasattr(cicd_semantic_rules, "iter_steps")`, que se pone rojo si alguien reintroduce el diff |
| **R13** | **Una regla "por job" queda muda en los 5 golden de raíz** | **Alta** (C2) | `job_key()` en F0 con 2 tests propios, y el assert de grupo dentro del control negativo de OPT002 |
| **R14** | **El panel se construye y nunca se monta (código muerto que pasa sus tests)** | **Alta** (C3) | F5 agrega la key de health y F6 declara las 3 ediciones de montaje + `test_seccion_registrada_en_devops_sections`. Precedente real: 2 fases inertes del Plan 176 |
| **R15** | El implementador atribuye un rojo propio a "los 4 fallos ajenos" | Media (C7) | El baseline de los dos gates está **medido y escrito** en F5: `test_harness_flags.py` = **56 passed**, `test_harness_ratchet_meta.py` = **4 passed** |

---

## 7. Fuera de scope (nombrando los otros planes de la serie)

- **Descubrir pipelines** (definiciones ADO + GitLab + YAMLs del repo, estado de última corrida) →
  **Plan 246**. Este plan **consume** su registro; no lo reimplementa. Si no está, degrada (§2.5).
- **Perfilar stack, anatomía y propósito** de una pipeline → **Plan 247**. Este plan consume
  `profile`; si no está, usa `PROFILE_DOTNET_FRAMEWORK`.
- **Catálogo y reglas base de GitLab (`GL001..GLnn`)**, corpus dorado de GitLab, endurecimiento del
  parser/renderer GitLab → **Plan 249**. Acá sólo 3 de 12 reglas son provider-agnósticas y se
  declara así (§3.4).
- **Aplicar el fix / editar el YAML por lenguaje natural** → **Plan 250**. Este plan es
  **read-only**: `remediation` es texto, no un patch (§3.3).
- **Matriz de entornos y valores que sólo el operador conoce** → **Plan 251**.
- **Paquete de entrega, README operativo y frontera de capacidades** → **Plan 252**.
- **Reglas estructurales PL001..PL014** (`pipeline_lint.py`) y **semánticas RS001..RS009**
  (`cicd_semantic_rules.py`): **no se tocan, no se duplican, no se reescriben.** Este plan importa
  sus severidades, sus helpers y sus modos, y agrega el eje seguridad/eficiencia que ninguna cubre.
  **En la v1 esta frase era falsa**: F0 editaba `cicd_semantic_rules.py` (+4 líneas), contradiciendo
  este mismo párrafo y pisando la superficie exclusiva del 249. En la v2 es literalmente cierta, y
  hay dos gates que la sostienen: el `assert not hasattr(...)` del test 5 de F0 y el chequeo de
  `git status` del DoD.
- **Producción**: este plan no despliega, no dispara corridas y no escribe en ningún servidor.
- **Tendencia histórica de hallazgos** y **auditoría por lote de todo el inventario**: recortadas
  por mí en §3.5; se pueden sumar después sin romper ningún contrato de acá.

---

## 8. Glosario, orden de implementación y DoD

### 8.1 Glosario

| Término | Significado en este plan |
|---|---|
| **SEC00n** | Hallazgo de **seguridad**. Familia nueva, `services/cicd_security_rules.py` |
| **OPT00n** | Hallazgo de **malas prácticas / eficiencia**. Familia nueva, `services/pipeline_recommendations.py` |
| **PL0nn** | Regla **estructural** existente (Plan 186). No se toca |
| **RS00n** | Regla **semántica** existente (Plan 243). No se toca |
| **`MODE_AUDIT`** | El sujeto es un YAML que **ya existe y corre**. Importado de `cicd_semantic_rules.py:43` |
| **`MODE_NL_STRICT`** | El sujeto es un YAML que **Stacky acaba de generar** y nunca corrió. Importado de `:44` |
| **Ley de severidad** | `SEV_ERROR` en `MODE_AUDIT` ⟺ 0 hits sobre el corpus dorado (§3.1) |
| **Abstención** | La regla no puede saber (valor dinámico) ⇒ no emite y **suma a `undetermined`** (§4.4) |
| **Baseline congelado** | `audit_baseline.json`: la foto revisada a mano de los hallazgos sobre los 9 golden |
| **`evidence_fingerprint`** | `sha256(code\|location\|evidence)[:16]`. Hace que una supresión caduque al mutar la evidencia |
| **Corpus dorado** | Los **9** `.yml` reales de `backend/tests/fixtures/cicd_nl/golden/` |

### 8.2 Orden de implementación (estricto, por dependencia)

```
F0 (contrato + espina)  →  F1 (SEC)  ┐
                        →  F2 (OPT)  ┴→  F3 (orquestador + baseline)  →  F4 (supresiones)
                                                                       →  F5 (blueprint + flag)
                                                                       →  F6 (panel, movible entera)
```

F1 y F2 son independientes entre sí y pueden hacerse en cualquier orden, **las dos después de F0**.
F3 **no puede empezar** hasta que F1 y F2 estén verdes: su baseline es la suma de ambas.

### 8.3 Definition of Done (binaria)

- [ ] **5 archivos de código creados si F6 se mueve; 7 si F6 se hace** (C14 — la v1 se contaba mal a
      sí misma): `services/cicd_audit_core.py`, `services/cicd_security_rules.py`,
      `services/pipeline_recommendations.py`, `services/pipeline_audit_suppressions.py`,
      `api/pipeline_audit.py` **(+ `frontend/src/devops/pipelineAuditModel.ts` y
      `components/devops/PipelineAuditPanel.tsx` sólo si F6 entra — nunca uno sin el otro ni sin su
      montaje, C3)**.
- [ ] **1 fixture creada:** `backend/tests/fixtures/cicd_nl/audit_baseline.json`, con
      `veredicto == "REAL"` en el **100%** de sus filas.
- [ ] **7 archivos editados** (C1: `cicd_semantic_rules.py` **ya NO está en esta lista**):
      `api/__init__.py` (+2), `api/devops.py` (+1 key de health), `services/harness_flags.py`,
      `tests/test_harness_flags.py`, `config.py`, y las **dos** listas `run_harness_tests.sh` /
      `.ps1`. **+2 si F6 entra:** `frontend/src/api/endpoints.ts`, `frontend/src/pages/DevOpsPage.tsx`.
- [ ] **`git status` no muestra `services/cicd_semantic_rules.py` modificado** (C1/R12 — gate
      mecánico de la frontera con el 249).
- [ ] **6 archivos de test backend** creados y registrados en **AMBAS** listas del ratchet
      (C14 — son **6**, contados uno por uno): `test_plan248_audit_core.py`,
      `test_plan248_security_rules.py`, `test_plan248_recommendations.py`,
      `test_plan248_audit_baseline.py`, `test_plan248_suppressions.py`, `test_plan248_api.py`.
- [ ] `.venv\Scripts\python.exe -m pytest tests/test_plan248_<cada uno>.py -q` → **verde uno por uno**.
- [ ] `tests/test_harness_ratchet_meta.py` → **4 passed** (baseline medido).
- [ ] `tests/test_plan243_reglas_semanticas.py` y `tests/test_plan243_corpus_mirror.py` → **verdes y
      con el MISMO número de tests que antes** (F0 ya no toca ese archivo: cualquier cambio en el
      conteo significa que se cruzó la frontera del 249).
- [ ] `tests/test_harness_flags.py` → **56 passed, 0 failed** (C7 — número exacto medido, no
      "sin fallos nuevos").
- [ ] **`test_ley_de_severidad` verde**: los 9 pipelines de producción tienen **0 hallazgos
      `SEV_ERROR`** en `MODE_AUDIT`. *(Este es el criterio que define si el plan cumplió su tesis.)*
- [ ] **`test_toda_regla_dispara_sobre_su_repro` y `test_toda_regla_declara_repro` verdes** (C4 —
      el otro criterio que define si el plan cumplió su tesis: sin esto, "0 errores" puede
      significar "12 reglas mudas").
- [ ] `npx tsc --noEmit` limpio y `npx vitest run src/devops/__tests__/pipelineAuditModel.test.ts`
      verde (si F6 se hace).
- [ ] **12 reglas** implementadas y presentes en la tabla de §4, cada una con severidad, perfil,
      modo, evidencia, remediación **y `repro`**.
- [ ] **0 llamadas a LLM y 0 llamadas de red** en todo el código del plan. **C10 — esto es un test,
      no una inspección** (`test_modulos_sin_red_ni_llm` en `test_plan248_audit_core.py`): recorre
      con `ast.parse` los 5 módulos nuevos y falla si alguno importa `requests`, `httpx`, `urllib`,
      `socket`, `pm_llm_client` o `copilot_bridge`. Se usa **AST, nunca regex sobre el texto**: un
      centinela textual de este tipo ya se rompió antes en esta casa, y además la palabra
      `copilot_bridge` aparece **en este mismo párrafo**, que es justo la clase de auto-colisión
      que un grep-gate produce.
- [ ] **Huella de regresión registrada** (C20): 1 entrada en `docs/sistema/error_fingerprints.json`
      con `id: "AUD-REGLA-INERTE"`, patrón "regla de auditoría con 0 hits sobre el corpus y sin
      `repro` que la dispare", `guard_test: "test_toda_regla_dispara_sobre_su_repro"`, plan 248,
      fecha 2026-07-26.
