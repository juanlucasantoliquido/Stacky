# Plan 250 — Editar y optimizar una pipeline que ya existe, describiendo el cambio en lenguaje natural

> Estado: **v1 · PROPUESTO** (2026-07-26). Pipeline: **proponer ✓ [este paso]** → criticar (`criticar-y-mejorar-plan`) → implementar (`implementar-plan-stacky`) → supervisar.
> Autor: Claude Opus 5 (1M context).
> Serie: **"Mago de las Pipelines"** (246–252). Este es el **250**. Contrato compartido: dossier de la serie §1.
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro — **paridad obligatoria**. **F0–F4 no usan LLM**; sólo F5 lo usa, con una única llamada acotada y mockeable.
> Flag: `STACKY_PIPELINE_NL_EDIT_ENABLED`, default **ON** (el commit sigue exigiendo confirmación explícita).

---

## 0. La tesis del plan (leer esto antes que nada)

El operador dice *"agregale un stage de tests antes del deploy"* o *"esta pipeline no cachea las
dependencias, arreglalo"*, y obtiene **un cambio quirúrgico revisable** sobre el archivo que ya
tiene — no una pipeline nueva.

Crear desde cero (243/244) y editar lo existente parecen el mismo problema. **No lo son, y el
segundo es más difícil**, por una razón que se puede medir:

> Un pipeline real no es su AST. Es su AST **más** los comentarios que explican por qué está
> escrito así, el orden en que el autor lo dejó, la alineación de sus valores, y las
> construcciones que el modelo interno de Stacky no cubre.

Si el sistema parsea a `PipelineSpec` y vuelve a renderizar, **destruye todo eso en silencio**.
No es una hipótesis: se corrió sobre el corpus dorado vendorizado por el Plan 243 F0
(`backend/tests/fixtures/cicd_nl/golden/`), con las funciones que hoy existen
(`parse_ado_yaml` → `to_ado_yaml`, `services/pipeline_renderers.py:453` y `:79`):

| Golden | Líneas antes → después | Comentarios antes → después |
|---|---|---|
| `agendaweb-ci.yml` | 160 → 58 | **81 → 0** |
| `bootstrap-server-environment.yml` | 146 → 75 | **44 → 0** |
| `cd-deploy-test.yml` | 189 → 129 | **31 → 0** |
| `ci-batch.yml` | 102 → 32 | **36 → 0** |
| `ci-cd-online.yml` | 127 → 63 | **47 → 0** |
| `ci-dacpac.yml` | 116 → 42 | **57 → 0** |
| `nightly-build-online.yml` | 115 → 79 | **18 → 0** |
| `pr-validation-online.yml` | 80 → 48 | **11 → 0** |
| `security-scan-online.yml` | 103 → 62 | **12 → 0** |
| **TOTAL** | **1138 → 588 (−48 %)** | **337 → 0 (−100 %)** |

Entre esos 337 comentarios está el postmortem de **ADO-369** (`ci-cd-online.yml:10-30` en el
fixture): 21 líneas que explican por qué se eliminaron dos stages de deploy y por qué no hay que
reintroducirlos. Es exactamente el conocimiento que el Plan 243 F3 convirtió en la regla RS002.
**Un editor que regenera borra el comentario que documenta el incidente y deja la regla que lo
detecta: pierde la mitad del sistema inmunitario y encima lo hace sin avisar.**

Esta casa prohíbe explícitamente perder trabajo del operador. Por lo tanto:

> **TESIS: el editor NO regenera. Edita el documento original por splice de líneas,
> preservando byte por byte todo lo que no tocó, y prueba esa preservación con un test que se
> pone rojo si desaparece un solo comentario o una sola construcción no modelada.**

---

## 1. Objetivo y valor (KPI medibles)

Que el operador abra una pipeline que ya existe, escriba *"agregá la publicación del artefacto
después de los tests"*, vea **el diff exacto de las 8 líneas que se agregan**, y lo commitee a una
rama con confirmación — sin que se toque ni una coma del resto del archivo.

| KPI | Hoy | Con el 250 | Cómo se mide (binario) |
|---|---|---|---|
| **KPI-1 · Preservación** | 0/337 comentarios sobreviven a un round-trip | **337/337** | `test_los_337_comentarios_del_corpus_sobreviven` (F0) |
| **KPI-2 · Cirugía** | n/a (no existe la capacidad) | 0 líneas modificadas fuera de los hunks declarados | `test_el_diff_real_no_sale_de_los_hunks_declarados` (F0) |
| **KPI-3 · No romper** | n/a | 0 patches ofrecidos que introduzcan un error nuevo de lint o de semántica | `test_patch_que_introduce_error_nuevo_no_se_ofrece` (F2) |
| **KPI-4 · HITL** | n/a | 0 escrituras sin `confirm=True` | `test_commit_sin_confirm_es_400` (F3) |
| **KPI-5 · Costo** | n/a | ≤ **1** llamada LLM por pedido de edición | `test_una_sola_llamada_llm_por_pedido` (F5) |

**Valor cualitativo:** hoy, modificar una pipeline de 130 líneas con 47 comentarios significa
abrir el YAML a mano. Con esto, significa **leer un diff de 8 líneas y apretar Confirmar**.

---

## 2. Evidencia (verificada abriendo cada archivo el 2026-07-26)

> Regla de anclajes del dossier §5 y del Plan 243 §7.2: **todo anclaje lleva el símbolo**. El
> número es una pista; si no coincide, greppeá el símbolo y **nunca concluyas que no existe**.

### 2.1 Lo que YA existe y este plan reutiliza sin reimplementar

| Pieza | Anclaje (archivo:línea `(símbolo)`) | Qué aporta a este plan |
|---|---|---|
| Parser ADO tolerante | `backend/services/pipeline_renderers.py:453 (parse_ado_yaml)` | Se usa **sólo para entender la estructura**, jamás para reescribir el archivo |
| Emisor de un paso `task:` | `backend/services/pipeline_renderers.py:110 (_task_step_doc)` | Renderiza el bloque **nuevo** que se inserta (sólo ese bloque) |
| Declaración de lo no modelado | `backend/services/pipeline_renderers.py:28 (UNSUPPORTED_CONSTRUCTS)`, `:51 (scan_unsupported)` | Invariante de preservación: lo no modelado no puede desaparecer |
| Lint estructural | `backend/services/pipeline_lint.py:791 (lint_yaml)`, `:33 (LintFinding)`, `:43 (LintReport)`, `:18-20 (SEV_ERROR/SEV_WARNING/SEV_INFO)` | Gate G-LINT por delta |
| **Doctrina de cirugía de líneas (precedente de la casa)** | `backend/services/pipeline_lint.py:29` — comentario literal del campo `LintFix.new_yaml`: *"YAML COMPLETO corregido (cirugía de líneas, nunca re-dump)"* | **El Plan 186 ya decidió esto para los autofixes.** El 250 generaliza la misma doctrina |
| Helpers de splice ya probados | `pipeline_lint.py:218 (_rebuild)`, `:225 (_fix_replace_on_line)`, `:236 (_fix_delete_line)`, `:244 (_fix_insert_after)`, `:252 (_key_indent)` | Convención de reconstrucción y de newline final |
| Reglas semánticas por perfil | `backend/services/cicd_semantic_rules.py:497 (check_semantics)`, `:43 (MODE_AUDIT)`, `:44 (MODE_NL_STRICT)`, `:48 (_NL_STRICT_ONLY)`, `:62 (SemanticFinding)`, `:51 (MAX_YAML_BYTES = 512*1024)` | Gate G-SEM por delta. **La elección de modo es la decisión sutil de §F2** |
| Catálogo cerrado de tareas | `backend/services/cicd_task_catalog.py:199 (get_task)`, `:204 (is_allowed)`, `:209 (validate_inputs)`, `:43 (TaskSpec)`, `:30 (PROFILE_DOTNET_FRAMEWORK)`, `:268 (extract_task_dicts)` | El LLM elige **dentro** del catálogo; nunca inventa una tarea |
| Escritura al repo | `backend/services/repo_writer.py:30 (get_repo_writer)`, `:17 (RepoWriter.commit_file(path, content, branch, message))` | **Acepta contenido literal y ruta arbitraria** ⇒ sirve para commitear el archivo parcheado tal cual |
| Ritual HITL del commit | `backend/api/pipeline_generator.py:59` (`if body.get("confirm") is not True: → 400 "confirm=True requerido (HITL)"`) | Se copia **el mismo ritual**, palabra por palabra |
| Modal de commit con confirm | `frontend/src/components/devops/CommitPipelineModal.tsx:41 (confirmChecked)`, `:145` (texto del checkbox), `:163` (botón deshabilitado sin confirm) | Lenguaje UX del commit ya establecido |
| **Diff con LCS ya en el panel** | `frontend/src/components/devops/pipelineLint.ts:91 (buildDiffLines)`, `:79 (DiffRow)`, `:87 (DiffResult.rows)`; consumido en `PipelineLintPanel.tsx:13` (import) y `:190` (render) | **No se escribe ni una línea de diff nueva en el frontend**: ya existe y ya se usa para previsualizar autofixes |
| Segundo diff (referencia) | `frontend/src/components/dbcompare/lineDiff.ts:22 (diffLines)`, `:12 (MAX_LINES = 3000)` | Precedente del cap duro para no colgar la UI con un LCS O(n·m) |
| Contrato UX de IA del panel | `frontend/src/components/devops/PipelineBuilderSection.tsx:382-383` (Plan 106 F5, literal: *"pide sugerencias al modelo local y PRE-RELLENA solo lo que está vacío (KPI-5, HITL): nunca pisa lo que el operador ya escribió"*), `:384 (handleSuggestWithLocalLlm)`, `:403-408` (patrón "sólo si está vacío") | **Este plan entra por ese mismo lenguaje** |
| Seam de LLM | `backend/services/pm/pm_llm_client.py:278 (call_llm)`, `:90 (LLMCallSpec)`, `:98 (temperature=0.0)`, `:99 (fixture_id)`, `:101 (expect_json)` — docstring `:281-283`: *"Nunca lanza excepción al caller por fallas de red/SDK: devuelve `success=False`"* | Única llamada LLM, mockeable por `fixture_id` |
| Contrato de flags | `backend/services/harness_flags.py:21 (FlagSpec)`, `:22 (key)`, `:23 (type)`, `:29 (default)`, `:30-32 (requires — informativo, ningún runner lo evalúa)`, `:33 (min_value)`, `:34 (max_value)` | Ambas flags configurables **desde la UI** |
| Ratchet de tests (**DOS listas**) | `backend/scripts/run_harness_tests.sh:20 (HARNESS_TEST_FILES=()` **y** `backend/scripts/run_harness_tests.ps1:13 ($HarnessTestFiles = @()` | Todo `test_*.py` nuevo se registra **en las dos** |
| Curación de defaults ON | `backend/tests/test_harness_flags.py:467 (_CURATED_DEFAULTS_ON)` | Una flag `default=True` fuera de esta lista pone rojo `test_default_known_only_for_curated` |
| Corpus dorado real | `backend/tests/fixtures/cicd_nl/golden/*.yml` (9 archivos, Plan 243 F0) | **Los fixtures de edición son pipelines de producción**, no YAMLs de juguete |

### 2.2 El hallazgo técnico que hace posible la cirugía: `yaml.compose()` da marcas de línea

`PyYAML 6.0.3` (ya en `requirements.txt`, verificado por el Plan 243 §pipeline_renderers.py:9)
expone `yaml.compose(text)` → árbol de `Node` con `start_mark.line`, `start_mark.column`,
`end_mark.line`. **Corrido de verdad contra el corpus** con
`backend/.venv\Scripts\python.exe` (Python 3.13.5):

```
compose ok: MappingNode 32 127
'trigger'   clave L32   valor L33..44
'pr'        clave L44   valor L44..44
'variables' clave L47   valor L48..55
'pool'      clave L55   valor L56..61
'stages'    clave L61   valor L62..127        (líneas 0-based)
```

Es decir: **se puede localizar cualquier nodo en el texto original sin perder el texto original**.
Ese es todo el mecanismo. No hace falta ninguna dependencia nueva.

> **`ruamel.yaml` NO está instalado** — verificado: `ModuleNotFoundError: No module named 'ruamel'`.
> Agregarlo caería en la **excepción dura (3)** del dossier §6 (*prerequisito no garantizado en la
> instalación default*) y rompería la paridad de runtimes en cualquier máquina que instale sin
> tocar `requirements.txt`. **Se descarta explícitamente.** El camino es PyYAML + splice.

### 2.3 La trampa del `end_mark` (esto es lo que un modelo menor rompe en silencio)

Sobre `ci-cd-online.yml`, los 6 items de `stages[0].jobs[0].steps`:

```
item 3  → start_mark.line 100   end_mark.line 112     (- task: DotNetCoreCLI@2)
item 4  → start_mark.line 112   end_mark.line 121     (- task: PublishTestResults@2)
```

Pero el contenido real del item 3 **termina en la línea 109**. Las líneas 110 y 111 son:

```
110  ''                                              ← línea en blanco
111  '    # 4. Publicar resultados de tests en ADO'   ← comentario del paso SIGUIENTE
```

**`end_mark.line` de un item de secuencia es EXCLUSIVO y se traga las líneas en blanco y el
comentario que introduce al item siguiente.** Una implementación ingenua que inserte "después del
item 3" en la línea `end_mark.line` deja el paso nuevo **debajo** del comentario
`# 4. Publicar resultados de tests en ADO`, huerfanando ese comentario sobre el paso equivocado.
Es corrupción silenciosa: el YAML sigue siendo válido y el operador tiene que descubrirlo leyendo.

**Regla obligatoria, sin margen de interpretación (se codifica en F0 y se testea):**

```
fin_efectivo(item) = max{ i ∈ [start_mark.line, end_mark.line)
                          : L[i].strip() != "" y no L[i].lstrip().startswith("#") }
punto_de_insercion_despues_de(item) = fin_efectivo(item) + 1
```

Las líneas en blanco y los comentarios finales **quedan con el item siguiente**, que es donde el
autor los puso.

### 2.4 La indentación no es una constante: se deriva del archivo

Los dos estilos conviven en el corpus real:

| Archivo | Forma | Columna del `-` | Columna de las claves |
|---|---|---|---|
| `ci-cd-online.yml:63` | `- stage: Build` (a ras) | 0 | 2 |
| `cd-deploy-test.yml:116` | `  - stage: DeployAgendaWeb` (indentado) | 2 | 4 |
| `ci-cd-online.yml:71` | `    - task: NuGetToolInstaller@1` | 4 | 6 |
| `cd-deploy-test.yml:135` | `                - task: PowerShell@2` | 16 | 18 |

`yaml.compose` da `item.start_mark.column` = columna de la **primera clave** del mapping
(6 y 18 en los casos de arriba). La columna del guion se lee del texto:
`dash_col = start_mark.column - 2`, **verificando** que `L[start][dash_col] == '-'`; si no
coincide (por ejemplo un item escrito como `-` solo en su línea y las claves abajo), **se devuelve
un error accionable, nunca se adivina** (test 11 de F0).

### 2.5 El flujo de commit existente NO sirve tal cual (y por qué)

`backend/api/pipeline_generator.py:52 (commit_route)` es HITL y correcto para **crear**, pero para
**editar** tiene dos bloqueos verificados:

1. `:67` — `yaml_str = to_ado_yaml(spec) if target == "ado" else to_gitlab_yaml(spec)`:
   **regenera desde el spec**. Es exactamente la ruta que borra los 337 comentarios (§0).
2. `:70` — `path = "azure-pipelines.yml" if target == "ado" else ".gitlab-ci.yml"`: **ruta
   hardcodeada**. No puede apuntar a `pipelines/ci-cd-online.yml`, que es donde viven los
   pipelines reales.

**Decisión:** se reutiliza **el seam** (`get_repo_writer(...).commit_file(...)`,
`repo_writer.py:30` y `:17`) y **el ritual** (`confirm is not True` → 400, copiado de
`pipeline_generator.py:59`), pero **no** la ruta `/commit`. El endpoint del 250 manda el texto
parcheado literal y la ruta real. `pipeline_generator.py` **no se modifica** (retrocompatible).

### 2.6 Trampa del corpus vendorizado: **+1 línea respecto de todos los anclajes del Plan 243**

El Plan 243 F0 agregó una línea de procedencia al principio de cada fixture
(`# fuente: RSPACIFICO/pipelines/<archivo> - copiado 2026-07-26 (plan 243 F0)`). Por lo tanto
**todo anclaje del Plan 243 al corpus está desplazado exactamente +1 respecto del fixture
vendorizado**. Verificado con `grep -n` sobre los fixtures:

| Lo que dice el Plan 243 | Dónde está de verdad en `backend/tests/fixtures/cicd_nl/golden/` |
|---|---|
| `nightly-build-online.yml:110` (`- script: |` crudo) | **`:111`** |
| `ci-batch.yml:58-59` (`matrix:`) | **`:60`** |
| `ci-cd-online.yml:9-29` (postmortem ADO-369) | **`:10-30`** |

**Este plan ancla siempre al fixture vendorizado** (que es lo que corren los tests), y lo dice
acá para que quien implemente no crea que el 243 se equivocó ni "corrija" nada.

### 2.7 Lo NO verificado (declarado)

- **No se abrieron** `ci-dacpac.yml`, `security-scan-online.yml`, `pr-validation-online.yml`,
  `bootstrap-server-environment.yml`, `agendaweb-ci.yml` ni `ci-batch.yml` línea por línea: de
  ellos sólo se verificó, por ejecución, el conteo de líneas/comentarios de la tabla §0 y los tres
  `grep` de §2.6. Los tests de F0 los recorren **por enumeración del directorio**, no por anclaje
  a una línea concreta de cada uno, precisamente para no depender de lo no verificado.
- **`services/pipeline_recommendations.py` y `cicd_security_rules.py` (Plan 248) NO existen hoy**
  — están reservados en el dossier §3. El puente `OPT*` de F5 se implementa con **import blando**
  y degradación declarada (§F5), no asumiendo que estén.
- **No se verificó** que el `RepoWriter` concreto de ADO soporte `commit_file` (el
  `/commit` existente devuelve **501** para `target="ado"` vía `NotImplementedError`,
  `pipeline_generator.py:86-88`, y `CommitPipelineModal.tsx:90-92` lo muestra como *"Render-only
  v1"* salvo que la capability `adoCommitSupported` esté presente). **F3 declara este camino como
  degradación honesta**: si el writer no soporta escritura, el endpoint devuelve 501 con el patch
  y el diff intactos, y la UI ofrece **copiar el YAML parcheado al portapapeles**. Nunca se
  presenta como "commiteado".
- Este plan **no toca ninguna tabla de base de datos**.

---

## 3. Principios, guardarraíles y alcance

**En alcance:** editar un YAML ADO existente por verbos cerrados; describir el cambio en lenguaje
natural; diff visible; gates por delta; commit HITL a una rama; puente opcional con las
recomendaciones del 248.

**Guardarraíles no negociables (dossier §6), codificados en las fases:**

1. **Human-in-the-loop, y acá es el corazón.** Nada se escribe ni se commitea sin `confirm=True`
   explícito. El operador **siempre ve el diff antes**. El sistema no aplica un patch por su
   cuenta ni siquiera cuando el gate está verde. F3 lo prueba con `test_commit_sin_confirm_es_400`.
2. **Cero trabajo extra al operador.** Flag `STACKY_PIPELINE_NL_EDIT_ENABLED` default **ON**
   (ninguna de las 4 excepciones duras aplica: no bypasea revisión humana —al contrario, la
   exige—, no es destructiva —escribe sólo en rama y previa confirmación—, no agrega prerequisitos
   —PyYAML ya está—, y no reduce la seguridad por default —agrega gates).
3. **Paridad de 3 runtimes.** F0–F4 **no invocan LLM ni red**: paridad trivial. F5 usa una única
   llamada por `pm_llm_client.call_llm` (`:278`), que **nunca lanza** (`:281-283`), y tiene
   fallback declarado (§F5).
4. **No degradar, backward-compatible.** No se modifica `pipeline_generator.py`, ni
   `pipeline_renderers.py`, ni `pipeline_lint.py`, ni `cicd_semantic_rules.py`. Todo el código
   nuevo vive en módulos nuevos. El panel gráfico actual queda **idéntico** con la flag en OFF.
5. **Mono-operador sin auth.** Ningún RBAC, ningún rol. El `confirm` es del operador, punto.

**Fuera de alcance (§6 lo detalla plan por plan):** crear pipelines desde cero, descubrir,
perfilar, definir reglas nuevas, GitLab, entornos, bundle.

**Recorte de alcance decidido por adelantado (precedente: el 243 tuvo que partirse, su C25):**
este plan tiene **exactamente 6 fases (F0..F5)** y **provider ADO solamente**. Se recorta a
propósito:

- **Verbos cerrados, 7 y ni uno más** (§F1). Nada de "editar cualquier cosa".
- **Sin bucle de auto-reparación.** Ninguno. Si el intent no valida, se le pregunta al operador
  (§F5). El 243 aprendió con su C10 que un bucle sin techo es una fuga; el techo más honesto y
  más barato es **cero reintentos automáticos** cuando el humano está mirando la pantalla.
- **GitLab queda afuera** de la ruta NL de edición (el 249 lleva la paridad GitLab del motor).
- **Si la corrida de implementación no llega a F5**, la feature ya está completa y es útil:
  F0–F4 entregan edición quirúrgica por controles estructurados, con diff y commit HITL. F5 sólo
  agrega la puerta de entrada en lenguaje natural.

---

## F0 — Motor de anclajes y splice quirúrgico (`pipeline_patcher.py`)

**Objetivo:** poder modificar N líneas de un YAML dejando **todas las demás byte-idénticas**, y
probarlo sobre 9 pipelines de producción. **Sin LLM, sin red, sin I/O.**

**Crear:** `backend/services/pipeline_patcher.py`, `backend/tests/test_plan250_patcher.py`.
**Editar:** nada.

```python
# backend/services/pipeline_patcher.py
PATCHER_VERSION = "250.1"
MAX_YAML_BYTES = 512 * 1024      # mismo límite que cicd_semantic_rules.py:51
MAX_OPS_PER_PLAN = 12            # techo duro: un patch no es una reescritura

@dataclass(frozen=True)
class Anchor:
    path: str          # "stages[0].jobs[0].steps"
    kind: str          # "seq" | "map" | "scalar"
    key_line: int|None # línea 0-based de la clave que abre el bloque; None en items
    start_line: int    # 0-based, primera línea del VALOR
    end_line: int      # 0-based INCLUSIVE, fin EFECTIVO (§2.3)
    key_col: int       # columna de las claves hijas
    dash_col: int|None # columna del guion si kind == "seq"; None si no
    item_paths: tuple  # para seq: paths de sus items, en orden

@dataclass(frozen=True)
class EditOp:
    kind: str          # "insert_after" | "insert_before" | "replace" | "delete"
    anchor_path: str   # path del Anchor sobre el que opera
    lines: tuple       # líneas YA indentadas a insertar; () para "delete"
    reason: str        # español, 1 línea: por qué existe esta op (va al hunk)

@dataclass(frozen=True)
class Hunk:
    start_line: int    # 1-based sobre el ORIGINAL
    end_line: int      # 1-based INCLUSIVE sobre el ORIGINAL; == start_line-1 si es inserción pura
    before: tuple      # líneas originales del rango
    after: tuple       # líneas resultantes
    reason: str

@dataclass(frozen=True)
class PatchResult:
    ok: bool
    text: str          # YAML resultante; == entrada si ok is False
    hunks: tuple
    errors: tuple      # mensajes en español; () si ok

def build_anchor_index(yaml_text: str) -> tuple[dict, tuple]:
    """→ ({path: Anchor}, errores). Usa yaml.compose(); NUNCA regex. Jamás lanza."""

def render_block(doc: dict, *, key_col: int, dash_col: int|None) -> tuple:
    """dict de UN paso/job/stage → líneas indentadas. Usa yaml.safe_dump(sort_keys=False)
    sobre ESE dict solo, y re-indenta. Nunca toca el documento completo."""

def apply_ops(yaml_text: str, ops: tuple) -> PatchResult:
    """Aplica las ops de abajo hacia arriba (índices estables). PURA."""
```

**Reglas duras que el implementador NO puede reinterpretar:**

1. **`build_anchor_index` usa `yaml.compose`, jamás `grep`/`re`/lectura por líneas** para
   localizar estructura (misma doctrina que el Plan 243 C20 impuso al catálogo).
2. **Fin efectivo** exactamente como §2.3. Escribirlo de otra forma rompe el test 2.
3. **Columnas derivadas del archivo** exactamente como §2.4. Si `L[start][dash_col] != '-'`
   ⇒ `errors` con mensaje accionable y `ok=False`. **Nunca adivinar.**
4. **Ops solapadas ⇒ rechazo total.** Si dos ops tocan rangos que se intersectan, no se aplica
   ninguna: `ok=False`. Un patch a medias es peor que ninguno.
5. **Newline final preservado** con la convención ya existente de `pipeline_lint.py:218
   (_rebuild)`: si el original terminaba en `\n`, el resultado también.
6. **`len(yaml_text) > MAX_YAML_BYTES` ⇒ `ok=False`** con un error, nunca colgar el request
   (espejo de `cicd_semantic_rules.py:506-512`).
7. **`len(ops) > MAX_OPS_PER_PLAN` ⇒ `ok=False`.**
8. **`yaml.YAMLError` ⇒ `ok=False` con el error**, jamás propagar la excepción.

**Tests PRIMERO (12) — `backend/tests/test_plan250_patcher.py`:**

| # | Test | Qué prueba |
|---|---|---|
| 1 | `test_indice_de_anclajes_de_ci_cd_online` | `build_anchor_index` sobre el fixture devuelve `stages[0].jobs[0].steps` con `key_col == 6`, `dash_col == 4` y **6** `item_paths` |
| 2 | `test_fin_efectivo_excluye_comentario_del_siguiente_item` | **§2.3.** El `Anchor` de `stages[0].jobs[0].steps[3]` tiene `end_line == 109` (0-based), **no 111** |
| 3 | `test_insertar_paso_al_final_preserva_los_47_comentarios` | Insertar un `- task: PublishCodeCoverageResults@2` al final de los steps de `ci-cd-online.yml`: el resultado tiene **47** líneas de comentario, igual que el original |
| 4 | `test_el_diff_real_no_sale_de_los_hunks_declarados` | **KPI-2.** Con `difflib.SequenceMatcher` (stdlib) sobre `(before, after)`, **todo opcode distinto de `equal` cae dentro de un `Hunk` declarado**. Es la prueba de que los hunks son la verdad y no una reconstrucción |
| 5 | `test_los_337_comentarios_del_corpus_sobreviven` | **KPI-1, CAPSTONE.** Para **los 9** goldens: aplicar una inserción al final del primer bloque `steps:` encontrado y afirmar que el conteo de líneas-comentario del resultado es **igual** al del original. Total del corpus: **337** |
| 6 | `test_construcciones_no_modeladas_no_desaparecen` | Para los 9: `scan_unsupported(after) == scan_unsupported(before)` (`pipeline_renderers.py:51`). En particular `ci-batch.yml` conserva `"matrix"` y `bootstrap-server-environment.yml` conserva `"compile_time_expression"` |
| 7 | `test_indentacion_se_deriva_del_archivo` | El mismo paso insertado en `ci-cd-online.yml` sale con guion en col 4 y en `cd-deploy-test.yml` (dentro del deployment) con guion en col 16 |
| 8 | `test_newline_final_se_preserva` | Con y sin `\n` final: el resultado respeta el original |
| 9 | `test_yaml_invalido_no_lanza` | `apply_ops("stages: [\n", ops)` ⇒ `ok is False`, sin excepción |
| 10 | `test_yaml_gigante_rechazado` | 600 KB ⇒ `ok is False` con error; no procesa |
| 11 | `test_item_con_dash_en_linea_propia_no_soportado` | `- \n  task: X` ⇒ `ok is False` con error accionable. **No adivina** |
| 12 | `test_ops_solapadas_rechazadas` | Dos ops sobre rangos que se cruzan ⇒ `ok is False` y `text == entrada` |

**Comando exacto (dossier §4):**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan250_patcher.py -q
```

**Registrar** `tests/test_plan250_patcher.py` en **las DOS listas del ratchet**:
`backend/scripts/run_harness_tests.sh:20 (HARNESS_TEST_FILES=()` y
`backend/scripts/run_harness_tests.ps1:13 ($HarnessTestFiles = @()`, y correr
`.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q`.

**Criterio de aceptación (BINARIO):** 12/12 verdes, en particular los tests 2, 4, 5 y 6. Además
`test_harness_ratchet_meta.py` verde.

**Flag:** ninguna (módulo puro sin consumidor todavía; se cablea en F3).
**Impacto por runtime:** idéntico en los 3 — no hay LLM, red ni I/O. **Fallback: no aplica,
no hay nada que degradar.**
`Trabajo del operador: ninguno`

---

## F1 — Verbos de edición cerrados: `EditIntent` → `EditPlan` (determinista)

**Objetivo:** un conjunto **cerrado y pequeño** de cambios expresables, compilados a `EditOp`s de
forma 100 % reproducible. **Sin LLM.**

**Crear:** `backend/tests/test_plan250_verbos.py`.
**Editar:** `backend/services/pipeline_patcher.py` (agrega la capa de verbos; mismo módulo porque
comparte el índice de anclajes y no tiene sentido separarla).

```python
EDIT_VERBS = (
    "add_step",          # agregar un paso `- task:` a un job existente
    "remove_step",       # quitar un paso por su ref (`PublishTestResults@2`) o índice
    "move_step",         # reordenar un paso dentro del mismo job
    "set_task_input",    # cambiar/agregar un `inputs.<clave>` de un paso existente
    "add_stage",         # agregar un stage completo (build/test) antes o después de otro
    "set_trigger_paths", # reemplazar el bloque trigger.paths.include
    "set_schedule",      # agregar/reemplazar el bloque schedules
)

@dataclass(frozen=True)
class EditIntent:
    verb: str
    target_path: str      # path del índice de F0, p.ej. "stages[0].jobs[0].steps"
    anchor_ref: str|None  # ref del paso de referencia, p.ej. "PublishBuildArtifacts@1"
    position: str         # "before" | "after" | "end"
    task_ref: str|None    # "PublishTestResults@2" — DEBE estar en el catálogo del perfil
    inputs: dict
    display_name: str
    values: tuple         # para set_trigger_paths / set_schedule
    notes: tuple          # supuestos asumidos — SE MUESTRAN SIEMPRE al operador

def plan_edit(yaml_text: str, intent: EditIntent, *, profile: str) -> tuple[tuple, tuple]:
    """→ (ops, errores). DETERMINISTA: mismo (yaml_text, intent, profile) ⇒ mismas ops,
    byte por byte, siempre. NO aplica nada: sólo planifica."""
```

**Validaciones obligatorias antes de emitir una sola op:**

- `verb not in EDIT_VERBS` ⇒ error. **Lista cerrada.**
- `task_ref` con `is_allowed(profile, task_ref) is False`
  (`cicd_task_catalog.py:204`) ⇒ error. **El editor no puede introducir una tarea que no esté
  en el catálogo**, ni aunque el operador la escriba a mano en el formulario.
- `validate_inputs(profile, task_ref, inputs) != []` (`:209`) ⇒ error con la lista de inputs
  inválidos.
- `display_name` y todo valor de `inputs`: **una sola línea** (sin `\n` ni `\r`), **≤ 200
  caracteres**, sin caracteres de control. Se emiten siempre por `yaml.safe_dump` del dict del
  paso (nunca por concatenación de strings), de modo que el quoting lo hace PyYAML.
- `anchor_ref` que no existe en `target_path` ⇒ error nombrando las refs que **sí** están
  (mensaje accionable, no "no encontrado").
- **El texto en lenguaje natural NUNCA se copia al YAML**, ni siquiera como comentario
  (herencia directa del Plan 243 C7).

**Renderizado del bloque nuevo:** se arma el dict del paso con la misma forma que
`pipeline_renderers.py:110 (_task_step_doc)` — claves en orden `task` → `displayName` →
`condition` → `inputs` — y se pasa por `render_block` de F0 con las columnas del anchor.

**Tests PRIMERO (10) — `backend/tests/test_plan250_verbos.py`:**

1. `test_add_step_al_final_de_ci_cd_online` — el plan devuelve **1** op `insert_after` sobre
   `steps[5]` y el YAML resultante parsea y contiene la nueva ref.
2. `test_add_step_antes_de_una_ref` — `position="before"`, `anchor_ref="PublishBuildArtifacts@1"`
   ⇒ la ref nueva queda entre `PublishTestResults@2` y `PublishBuildArtifacts@1`.
3. `test_remove_step_por_ref` — quitar `PublishTestResults@2` de `ci-cd-online.yml` borra **su**
   rango y deja los 47 comentarios menos los 2 propios de ese paso.
4. `test_move_step_reordena_sin_reescribir` — mover un paso produce exactamente 2 hunks y ninguna
   otra línea cambia.
5. `test_set_task_input_cambia_una_sola_linea` — cambiar `configuration` en `VSBuild@1` produce
   **1** hunk de **1** línea.
6. `test_add_stage_respeta_el_estilo_del_archivo` — en `cd-deploy-test.yml` (stages indentados a
   col 2) el stage nuevo sale con guion en col 2.
7. `test_tarea_fuera_del_catalogo_rechazada` — `task_ref="MSBuild@1"` ⇒ error, **0 ops**.
8. `test_input_invalido_rechazado` — `inputs={"msbuildArguments": "x"}` sobre `VSBuild@1` ⇒ error
   (el input real es `msbuildArgs`).
9. `test_display_name_multilinea_rechazado` — `display_name="a\nb"` ⇒ error, 0 ops.
10. `test_determinismo` — 2 corridas de `plan_edit` con el mismo intent ⇒ ops **idénticas**.

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan250_verbos.py -q`
(+ registrar el archivo en las dos listas del ratchet).

**Criterio de aceptación (BINARIO):** 10/10 verdes **y** `tests/test_plan250_patcher.py` sigue en
12/12 (no regresión).

**Flag:** ninguna todavía.
**Impacto por runtime:** idéntico en los 3, sin LLM. **Fallback: no aplica.**
`Trabajo del operador: ninguno`

---

## F2 — Gates por DELTA (`pipeline_diff.py`): no ofrecer un patch que rompe

**Objetivo:** que un patch que introduce un error **no se ofrezca**, sin volver ineditables los
pipelines que hoy ya tienen hallazgos.

**Crear:** `backend/services/pipeline_diff.py`, `backend/tests/test_plan250_gates_delta.py`.
**Editar:** nada.

### La decisión sutil, por escrito: qué modo de regla se aplica al resultado de una edición

`check_semantics` (`cicd_semantic_rules.py:497`) tiene dos modos: `MODE_AUDIT` (`:43`) y
`MODE_NL_STRICT` (`:44`), y `RS004`/`RS006`/`RS008` sólo corren en el estricto (`:48`).

**Aplicar `MODE_NL_STRICT` al documento completo editado sería un error de diseño.** Prueba
concreta: `nightly-build-online.yml:111` tiene un `- script: |` crudo y real. Si el operador pide
"cambiale la configuración del build a Debug", el gate estricto sobre el documento entero
reportaría **RS008 error** sobre un paso que el operador no tocó, en un pipeline que corre en
producción desde siempre. El patch quedaría bloqueado por una falta ajena. El operador aprendería
en dos días a ignorar el semáforo — **que es el peor resultado posible para un gate**.

**Aplicar sólo `MODE_AUDIT` también sería un error**, por el lado opuesto: RS004 y RS008 existen
justamente para que **Stacky** no emita PowerShell inline ni tareas fuera del catálogo (Plan 243
C5/C7). Si Stacky escribe, Stacky se somete al estándar estricto.

**Decisión (se implementa así y se testea así):**

| Qué se evalúa | Modo | Qué bloquea |
|---|---|---|
| Documento completo **después** vs **antes** | `MODE_AUDIT` | Sólo los findings **nuevos** con severidad `error` (delta) |
| Los bloques que **el patch introdujo**, aislados en un documento sintético mínimo | `MODE_NL_STRICT` | **Cualquier** finding `error` |
| `lint_yaml(after, "ado")` vs `lint_yaml(before, "ado")` (`pipeline_lint.py:791`) | — | Sólo los findings **nuevos** con `SEV_ERROR` |

**El delta se calcula por identidad de finding, no por conteo**: dos findings son "el mismo" si
coinciden `(code, message)` **normalizando** el índice numérico de `location`/`line` (porque un
paso insertado corre los índices de todos los siguientes y un conteo ingenuo daría falsos
positivos en masa). Esta normalización es la parte que un modelo menor haría mal, así que se
especifica:

```python
def _finding_key(code: str, message: str, location: str) -> tuple:
    """`stages[1].jobs[0].steps[4]` → `stages[].jobs[].steps[]`. Un paso insertado
    desplaza los índices de los siguientes: comparar índices crudos produciría
    decenas de findings 'nuevos' que en realidad son los mismos de antes."""
    return (code, message, re.sub(r"\[\d+\]", "[]", location or ""))
```

```python
DIFF_VERSION = "250.1"

@dataclass(frozen=True)
class GateDelta:
    gate: str            # "LINT" | "SEM_AUDIT" | "SEM_NL_STRICT"
    passed: bool
    new_errors: tuple    # findings NUEVOS con severidad error
    new_warnings: tuple
    resolved: tuple      # findings que el patch HIZO DESAPARECER (se muestran: es valor)
    skipped_reason: str  # "" si corrió

@dataclass(frozen=True)
class EditReview:
    ok: bool             # True ⇔ ningún gate con new_errors
    gates: tuple
    hunks: tuple
    summary: str         # español, derivado (NO redactado por un LLM)
    unsupported: tuple   # scan_unsupported(after) — se informa, no bloquea

def review_patch(before: str, after: str, hunks: tuple, *, profile: str,
                 repo_root: str|None = None) -> EditReview
```

**Reglas duras:**
- **`resolved` se muestra**: si el patch arregla algo (por ejemplo agrega el `PublishBuildArtifacts@1`
  que faltaba), el operador tiene que verlo. Un gate que sólo sabe decir "no" enseña a ignorarlo.
- **`unsupported` nunca bloquea**: es informativo (misma doctrina que el espejo de corpus del
  243 F3.5, que es `info` y no puede cambiar el estado).
- **`repo_root is None` ⇒ RS006 no se evalúa** y el gate lo declara en `skipped_reason`;
  **jamás se reporta como "validado"** (herencia del 243 §4).
- Si `after` no parsea ⇒ `ok=False` con el error de PL001. El patch no se ofrece.

**Tests PRIMERO (9) — `backend/tests/test_plan250_gates_delta.py`:**

1. `test_error_preexistente_no_bloquea_la_edicion` — editar `nightly-build-online.yml` (que tiene
   el `- script: |` de `:111`) con un `set_task_input` inocuo ⇒ `ok is True`. **Es el test que
   impide que el gate se vuelva inútil por estricto.**
2. `test_patch_que_introduce_error_nuevo_no_se_ofrece` — **KPI-3.** Un patch que agrega
   `IISWebAppDeploymentOnMachineGroup@0` en un stage con `pool: vmImage:` ⇒ `ok is False` con
   **RS002** en `new_errors`. *Es ADO-369 detectado en la ruta de edición.*
3. `test_paso_insertado_se_evalua_en_nl_strict` — un patch que inserta `PowerShell@2` con
   `inputs.script` inline ⇒ **RS004 error**, aunque el documento completo en `audit` no lo marque.
4. `test_indices_desplazados_no_cuentan_como_nuevos` — insertar un paso al principio de un job de
   6 pasos **no** produce ningún `new_error` ni `new_warning` por corrimiento de índices.
5. `test_findings_resueltos_se_reportan` — un patch que elimina la causa de un finding lo lista en
   `resolved`.
6. `test_lint_delta_solo_reporta_lo_nuevo` — un YAML con un `SEV_ERROR` de lint preexistente sigue
   siendo editable.
7. `test_sin_repo_root_rs006_se_declara_skipped` — `repo_root=None` ⇒ `skipped_reason` no vacío y
   **nunca** `passed` por omisión.
8. `test_after_no_parsea_bloquea` — `after` corrupto ⇒ `ok is False`.
9. `test_unsupported_se_informa_y_no_bloquea` — editar `ci-batch.yml` (que tiene `matrix:` en
   `:60`) ⇒ `unsupported` contiene `"matrix"` y `ok is True`.

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan250_gates_delta.py -q`
(+ las dos listas del ratchet).

**Criterio de aceptación (BINARIO):** 9/9 verdes, en particular 1, 2, 3 y 4. Además, sin regresión:
`.venv\Scripts\python.exe -m pytest tests/test_plan243_reglas_semanticas.py -q` verde.

**Flag:** ninguna todavía.
**Impacto por runtime:** idéntico en los 3, sin LLM. **Fallback: no aplica.**
`Trabajo del operador: ninguno`

---

## F3 — Blueprint `api/pipeline_editor.py` + commit HITL + flags

**Objetivo:** exponer el motor con el mismo ritual de confirmación que ya existe, y dejar las dos
flags configurables **desde la UI**.

**Crear:** `backend/api/pipeline_editor.py`, `backend/tests/test_plan250_api.py`,
`backend/tests/test_plan250_flag.py`.
**Editar:** `backend/api/__init__.py` (importar y registrar el blueprint, patrón de `:44` y `:77+`),
`backend/services/harness_flags.py`, `backend/config.py`,
`backend/tests/test_harness_flags.py:467 (_CURATED_DEFAULTS_ON)`.

```python
"""api/pipeline_editor.py — Blueprint edición quirúrgica de pipelines existentes. Plan 250 F3."""
from __future__ import annotations
import config as _config
from flask import Blueprint, abort, jsonify, request

# url_prefix="/pipeline-editor" → ruta final /api/pipeline-editor/...
# NO "/api/pipeline-editor" (daría /api/api/...) y NO registrar en app.py.
bp = Blueprint("pipeline_editor", __name__, url_prefix="/pipeline-editor")
```

| Método | Ruta | Cuerpo | Devuelve |
|---|---|---|---|
| POST | `/plan` | `{yaml, intent, profile, repo_root?}` | `{ops, hunks, review, before_sha256, after_sha256}` — **no escribe nada** |
| POST | `/commit` | `{project, path, branch, message, intent, profile, before_sha256, approved_after_sha256, confirm}` | resultado de `commit_file` |
| GET | `/verbs` | — | `{verbs: EDIT_VERBS, catalog: {ref: [inputs...]}}` para el formulario de F4 |

**Guard de flag PER-REQUEST** en cada handler (nunca en el registro del blueprint):

```python
if not getattr(_config.config, "STACKY_PIPELINE_NL_EDIT_ENABLED", False):
    abort(404)
```

> **Gotcha dura del dossier §3:** el consumidor lee **la instancia** (`_config.config`), no el
> módulo. `getattr` del módulo devuelve el default y **mata el branch OFF** (el test flag-off
> pasaría en falso).

**Candados de `/commit`, en este orden exacto:**

1. `body.get("confirm") is not True` ⇒ **400** `{"error": "confirm=True requerido (HITL)"}`
   — literal copiado de `pipeline_generator.py:59-60`.
2. `branch` vacío o igual a la rama por defecto del repo ⇒ **400**. **Nunca se commitea sobre la
   rama por defecto.**
3. Se **relee el archivo actual** y se compara su sha256 con `before_sha256`. Si difiere ⇒
   **409** `{"error": "el archivo cambió desde que viste el diff", "before_sha256": <nuevo>}`.
   *El operador aprobó un diff contra una versión; escribir contra otra sería escribir a ciegas.*
4. Se **recompila el patch en el servidor** desde `intent` (F1) y se aplica (F0). Si el sha256 del
   resultado ≠ `approved_after_sha256` ⇒ **409** con el diff nuevo.
   **El servidor NUNCA acepta el YAML final que manda el cliente.**
5. `review_patch(...)` (F2). Si `ok is False` ⇒ **422** con los `new_errors`.
6. Recién ahí: `get_repo_writer(project).commit_file(path=path, content=after, branch=branch,
   message=message)` (`repo_writer.py:30`, `:17`).
7. `NotImplementedError` ⇒ **501** con `{"yaml": after, "hunks": [...]}` intactos (§2.7): la UI
   ofrece copiar el YAML parcheado. **Nunca se presenta como "commiteado".**
   `TrackerApiError` ⇒ su `status` real (patrón de `pipeline_generator.py:83-85`).

**Flags** (`services/harness_flags.py`, patrón de `:21 (FlagSpec)`):

```python
FlagSpec(
    key="STACKY_PIPELINE_NL_EDIT_ENABLED",
    type="bool",
    default=True,   # default ON: ninguna de las 4 excepciones duras aplica (§3);
                    # curada en _CURATED_DEFAULTS_ON (test_harness_flags.py:467)
    label="Edición de pipelines en lenguaje natural",
    description=(
        "Plan 250 - Modificar una pipeline existente describiendo el cambio; patch "
        "quirúrgico con diff visible y commit con confirmación. OFF: desaparece el panel "
        "de edición y sus 3 endpoints dan 404; el builder gráfico queda IDÉNTICO a hoy."
    ),
    group="global",
),
FlagSpec(
    key="STACKY_PIPELINE_NL_EDIT_MAX_LLM_CALLS",
    type="int",
    default=1, min_value=1, max_value=3,
    label="Llamadas al modelo por pedido de edición",
    description=(
        "Plan 250 - Techo duro de invocaciones al LLM para interpretar UN pedido. "
        "Default 1: sin reintentos automáticos; si el pedido es ambiguo se le pregunta "
        "al operador, que sale más barato y más honesto que adivinar."
    ),
    group="global",
    requires="STACKY_PIPELINE_NL_EDIT_ENABLED",
),
```

> **Gotchas obligatorias:** (a) una `FlagSpec` con `default=True` **debe** estar además en
> `_CURATED_DEFAULTS_ON` (`backend/tests/test_harness_flags.py:467`) o
> `test_default_known_only_for_curated` se pone rojo; (b) toda flag nueva necesita su entrada en
> `_CATEGORY_KEYS` (`services/harness_flags.py`) o el meta-test de categorización falla; (c)
> `requires` es **informativo para la UI — ningún runner lo evalúa** (`harness_flags.py:30-32`),
> así que F5 **debe** chequear `STACKY_PIPELINE_NL_EDIT_ENABLED` por su cuenta.

**Tests PRIMERO (8 + 4):**

`backend/tests/test_plan250_api.py` (8):
1. `test_endpoints_404_con_flag_off` — los 3 endpoints con la flag OFF.
2. `test_plan_devuelve_hunks_y_review` — 200 con `hunks` no vacío.
3. `test_plan_no_escribe_nada` — el fixture en disco queda byte-idéntico tras `/plan`.
4. `test_commit_sin_confirm_es_400` — **KPI-4.**
5. `test_commit_sobre_rama_default_es_400`.
6. `test_commit_con_before_sha_desactualizado_es_409`.
7. `test_commit_ignora_el_yaml_del_cliente` — se manda un `yaml` malicioso en el body y se afirma
   que lo commiteado es el recompilado del servidor.
8. `test_commit_con_review_en_rojo_es_422`.

`backend/tests/test_plan250_flag.py` (4):
1. Ambas flags aparecen en el catálogo que consume la UI.
2. `STACKY_PIPELINE_NL_EDIT_MAX_LLM_CALLS = 0` y `= 4` son rechazadas por `apply_updates`.
3. `test_default_known_only_for_curated` verde.
4. La flag nueva tiene categoría en `_CATEGORY_KEYS`.

**Comandos:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_plan250_api.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan250_flag.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```
> **Rojo ajeno conocido (dossier §4):** `test_harness_flags_help` tiene **4 fallos preexistentes
> que NO son tuyos**. Validá tus 4 tests de forma aislada; no "arregles" los ajenos.

**Criterio de aceptación (BINARIO):** 12/12 verdes (8+4), ratchet meta verde con los 5 archivos de
test registrados en **las dos** listas, y `tests/test_plan73_generator_endpoint.py` verde
(prueba de que `pipeline_generator.py` no se tocó).

**Flag:** `STACKY_PIPELINE_NL_EDIT_ENABLED`, default **ON**.
**Impacto por runtime:** idéntico en los 3 — el blueprint no invoca LLM.
**Fallback:** flag OFF ⇒ 404 en los 3 endpoints y el panel no se renderiza; el builder gráfico
queda **exactamente como hoy**.
`Trabajo del operador: opt-in, default ON`

---

## F4 — Panel de edición con diff (sin LLM todavía): la feature ya sirve acá

**Objetivo:** que el operador edite una pipeline existente por **controles estructurados**, vea el
diff y commitee — todo sin modelo. Si la corrida de implementación muere después de esta fase,
**la feature está completa y es útil**.

**Crear:** `frontend/src/devops/pipelineEditModel.ts` (**modelo PURO, toda la lógica testeable**),
`frontend/src/devops/__tests__/pipelineEditModel.test.ts`,
`frontend/src/components/devops/PipelineEditNlPanel.tsx`,
`frontend/src/components/devops/PipelineEditNlPanel.module.css`.
**Editar:** `frontend/src/api/endpoints.ts` (objeto `PipelineEditor` con `plan`, `commit`,
`verbs`), `frontend/src/components/devops/PipelineBuilderSection.tsx` (montar el panel).

```ts
// frontend/src/devops/pipelineEditModel.ts — PURO, sin React, sin fetch
export const MAX_EDIT_LINES = 3000;   // espejo de lineDiff.ts:12 (MAX_LINES)

export interface EditFormState { verb: string; targetPath: string; anchorRef: string|null;
  position: 'before'|'after'|'end'; taskRef: string|null; inputs: Record<string,string>;
  displayName: string; }

/** Habilita "Ver diff" sólo si el formulario está completo para ese verbo. */
export function isPlanRequestReady(s: EditFormState): boolean

/** Resumen en español del cambio, DERIVADO de los hunks (nunca redactado por un LLM). */
export function summarizeHunks(hunks: Hunk[]): string

/** Contrato Plan 106 F5 (PipelineBuilderSection.tsx:382-383): PRE-RELLENA sólo lo vacío.
 *  Nunca pisa un campo que el operador ya escribió. */
export function prefillOnlyEmpty(current: EditFormState, suggested: Partial<EditFormState>): EditFormState

/** Gate de tamaño: por encima del cap no se pide diff (se ofrece el YAML crudo). */
export function canRenderDiff(before: string, after: string): boolean
```

**Contrato de UI (no negociable):**

- **El diff se muestra SIEMPRE antes de cualquier escritura.** Se renderiza con
  `buildDiffLines(before, after)` de `frontend/src/components/devops/pipelineLint.ts:91`
  (`DiffRow` en `:79`) — **el mismo componente visual que ya usa `PipelineLintPanel.tsx:190`**
  para previsualizar autofixes. **No se escribe ni una línea de código de diff nuevo.**
- Junto al diff completo se listan los **hunks** con su `reason`, para que el operador vea
  **qué op causó qué cambio** y no tenga que deducirlo de un LCS.
- El botón de commit repite el ritual de `CommitPipelineModal.tsx:41,145,163`: checkbox de
  confirmación obligatorio, botón deshabilitado sin él.
- El semáforo muestra `new_errors` (bloquean el commit), `new_warnings` (no bloquean) y
  **`resolved`** (lo que el patch arregla).
- Si `review.ok is false`, el botón de commit está deshabilitado **y el diff se muestra igual**:
  el operador tiene derecho a ver lo que Stacky se negó a ofrecerle.
- **Gotcha de la casa:** en un `.tsx` **nuevo** el `uiDebtRatchet` tiene alcance 0 ⇒ **cero
  `style={{...}}` inline**, todo al `.module.css`.

**Tests PRIMERO (8) — `frontend/src/devops/__tests__/pipelineEditModel.test.ts`:**

1. `isPlanRequestReady` es `false` sin `taskRef` para `add_step`, `true` con él.
2. `isPlanRequestReady` no exige `taskRef` para `remove_step`.
3. `prefillOnlyEmpty` **no pisa** un `displayName` que ya tiene texto.
4. `prefillOnlyEmpty` **sí** rellena un `displayName` vacío.
5. `summarizeHunks` con 1 hunk de inserción dice "1 bloque agregado" y con 0 hunks dice
   "sin cambios".
6. `canRenderDiff` es `false` por encima de `MAX_EDIT_LINES`.
7. `summarizeHunks` es puro: 2 llamadas ⇒ el mismo string.
8. El estado inicial del formulario no habilita el commit.

> **No hay tests de render:** `@testing-library/react` y `jsdom` **no están instalados** en este
> frontend. Por eso **toda la lógica vive en el modelo puro** y el `.tsx` es sólo cableado. El
> gate real del componente es `npx tsc --noEmit` + el smoke visual del operador.

**Comandos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/devops/__tests__/pipelineEditModel.test.ts
npx tsc --noEmit
```
> `npm test` **falla**: no hay script `test` en `package.json`. Se usa `npx vitest`.

**Criterio de aceptación (BINARIO):** 8/8 verdes, `npx tsc --noEmit` sin errores nuevos, y el
ratchet de deuda de UI **no crece**.

**Flag:** `STACKY_PIPELINE_NL_EDIT_ENABLED` (el panel no se monta si la flag está OFF; se lee del
health, como el resto de las flags de UI).
**Impacto por runtime:** idéntico en los 3 — el panel no llama a ningún modelo en esta fase.
**Fallback:** flag OFF ⇒ el panel no existe y `PipelineBuilderSection` queda **idéntico a hoy**.
`Trabajo del operador: opt-in, default ON`

---

## F5 — La puerta de entrada en lenguaje natural (única llamada LLM) + puente con el 248

**Objetivo:** que el operador escriba *"agregale un stage de tests antes del deploy"* y eso se
convierta en **un `EditIntent` validado**, que entra por el mismo camino de F1→F0→F2→F4.

**Crear:** `backend/services/pipeline_edit_intent.py`,
`backend/tests/test_plan250_edit_intent.py`,
`backend/tests/fixtures/pipeline_edit/intents/*.json` (**≥6**).
**Editar:** `backend/api/pipeline_editor.py` (endpoint `POST /interpret`),
`frontend/src/components/devops/PipelineEditNlPanel.tsx` (caja de texto),
`frontend/src/devops/pipelineEditModel.ts` (sin lógica nueva de negocio: sólo el estado de la caja).

```python
PROMPT_TYPE = "pipeline_edit_intent_v1"
INTENT_SCHEMA: dict          # cerrado; verbo ∈ EDIT_VERBS, task_ref ∈ catálogo del perfil

def interpret_edit(text: str, *, yaml_text: str, profile: str,
                   fixture_id: str|None = None) -> tuple[EditIntent|None, tuple]:
    """→ (intent, preguntas). UNA sola llamada a call_llm. Nunca lanza."""
```

**El LLM NO escribe YAML. Nunca. Bajo ninguna condición.** Recibe:

1. la lista literal de `EDIT_VERBS` (7),
2. **el índice de anclajes** de F0 (los `path` disponibles) y **la espina de tareas**
   (`extract_task_refs`, `cicd_task_catalog.py:287`) — **no el YAML completo**: es más chico, más
   barato y no expone los comentarios ni los valores del archivo al modelo,
3. el catálogo del perfil como **referencia cerrada** (`is_allowed`, `validate_inputs`).

Y devuelve **un JSON de `EditIntent`**, con `LLMCallSpec` (`pm_llm_client.py:90`):
`expect_json=True` (`:101`), `temperature=0.0` (`:98`), `prompt_type=PROMPT_TYPE`,
`fixture_id` pasante (`:99`).

**Ambigüedad explícita — no adivina:** si no puede resolver el `target_path`, o el pedido no cae
en ninguno de los 7 verbos, devuelve `(None, (preguntas,))` **nombrando el dato que falta**. Las
`notes` (supuestos asumidos) **se muestran siempre**, antes del diff.

### Techo de costo y de reintentos (numérico y duro)

- **Máximo 1 llamada LLM por pedido** (`STACKY_PIPELINE_NL_EDIT_MAX_LLM_CALLS`, default **1**,
  `min_value=1`, `max_value=3`).
- **Cero reintentos automáticos.** Si el JSON no valida contra `INTENT_SCHEMA`, o el `task_ref`
  no está en el catálogo, **se devuelve la pregunta al operador**; no se reinvoca al modelo.
  *Justificación explícita: el 243 documentó en su C10 que el bucle de auto-reparación sin techo
  es una fuga. Con el operador mirando la pantalla, preguntarle cuesta 0 tokens y acierta más.*
- **Máximo 12 `EditOp` por plan** (`MAX_OPS_PER_PLAN`, F0). Un pedido que requiera más se rechaza
  con "partilo en dos ediciones".
- El texto NL **no se persiste** en ningún lado; **no se copia al YAML** ni como comentario.

### Determinismo (declarado con su mitigación)

| Tramo | ¿Determinista? | Mitigación |
|---|---|---|
| `EditIntent` → `EditPlan` → texto parcheado (F1+F0) | **SÍ, byte por byte** | `test_determinismo` (F1) |
| NL → `EditIntent` (F5) | **NO garantizado** entre versiones de modelo, aun con `temperature=0.0` | (a) el `EditIntent` **se muestra al operador antes del diff**, en castellano y campo por campo; (b) los tests usan `fixture_id` ⇒ **cero red**; (c) el `EditIntent` es chico y cerrado: dos interpretaciones distintas producen dos intents visiblemente distintos, no dos YAML sutilmente distintos |

**Este es el punto entero del diseño:** el no determinismo se concentra en una estructura de 8
campos que el operador lee de un vistazo, en vez de repartirse por 130 líneas de YAML.

### Fallback explícito por runtime (obligatorio)

| Runtime | Camino normal | Fallback si no hay LLM disponible |
|---|---|---|
| **Codex CLI** | `call_llm` con el backend configurado | La caja NL muestra el error de `call_llm` (`success=False`, `pm_llm_client.py:281-283`) y **el formulario de verbos de F4 sigue 100 % operativo** |
| **Claude Code CLI** | ídem | ídem |
| **GitHub Copilot Pro** | ídem (`_call_copilot`) | ídem |

**La respuesta a "¿y si el runtime no tiene LLM?" no es "no anda": es "andá por el formulario".**
F0–F4 no dependen de ningún modelo, así que la capacidad de editar quirúrgicamente **nunca se
pierde**; lo único que se pierde es escribir el pedido en prosa. Eso se dice en la UI con esas
palabras, no se oculta.

### Puente con el Plan 248 (recomendaciones `OPT*`) — degradación declarada

```python
def recommendation_to_intent(rec_id: str, yaml_text: str, *, profile: str):
    """Si el 248 está implementado, traduce una recomendación OPT* a un EditIntent.
    Import BLANDO: si services/pipeline_recommendations.py no existe, devuelve
    (None, ("el módulo de recomendaciones (plan 248) no está instalado",)).
    NUNCA lanza ImportError."""
    try:
        from services.pipeline_recommendations import get_recommendation
    except ImportError:
        return None, ("...",)
```

El endpoint `/verbs` devuelve `{"recommendations_available": bool}`; la UI muestra el botón
**"Aplicar esta recomendación"** sólo si es `true`. **Si el 248 no está, no hay botón y no hay
error**: la edición NL pura funciona igual. Verificado en §2.7: hoy ese módulo **no existe**.

**Tests PRIMERO (9) — `backend/tests/test_plan250_edit_intent.py` (todos con `fixture_id`, sin red):**

1. `test_seis_fixtures_producen_el_intent_esperado` — los 6 JSON de
   `backend/tests/fixtures/pipeline_edit/intents/` → `EditIntent` esperado, campo por campo.
2. `test_pedido_ambiguo_devuelve_preguntas` — *"mejorá esto"* ⇒ `(None, (preguntas,))` nombrando
   el dato faltante.
3. `test_verbo_fuera_de_la_lista_rechazado` — el modelo devuelve `verb="delete_pipeline"` ⇒
   `(None, ...)`, **0 ops**.
4. `test_tarea_alucinada_rechazada` — `task_ref="VSBuild@2"` ⇒ rechazo (no está en el catálogo).
5. `test_una_sola_llamada_llm_por_pedido` — **KPI-5.** Con un doble de `call_llm` que cuenta
   invocaciones: **exactamente 1**, incluso cuando el JSON devuelto es inválido.
6. `test_no_lanza_si_call_llm_falla` — `success=False` ⇒ `(None, (mensaje,))`, sin excepción.
7. `test_el_texto_nl_no_llega_al_yaml` — se pide una edición con un texto que contiene
   `# hackme` y `$(malicious)`, y se afirma que **ninguna de esas cadenas aparece** en el YAML
   resultante.
8. `test_recomendacion_sin_plan_248_degrada` — `recommendation_to_intent` con el módulo ausente ⇒
   `(None, (mensaje,))`, **sin `ImportError`**.
9. `test_intent_se_muestra_antes_del_diff` — el endpoint `/interpret` devuelve `intent` **y**
   `notes`, y **no** devuelve `yaml` ni `hunks` (el diff exige el paso `/plan` aparte, que es
   donde el operador confirma el intent).

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan250_edit_intent.py -q`
(+ las dos listas del ratchet).

**Criterio de aceptación (BINARIO):** 9/9 verdes, **cero acceso a red** (guard de red del arnés
verde), y el KPI-5 probado por el test 5.

**Flag:** `STACKY_PIPELINE_NL_EDIT_ENABLED` (default ON) +
`STACKY_PIPELINE_NL_EDIT_MAX_LLM_CALLS` (default 1). **F5 chequea la primera por su cuenta**: el
`requires` es informativo (`harness_flags.py:30-32`).
**Impacto por runtime:** ver la tabla de fallback de arriba. En tests, `fixture_id` ⇒ cero red en
los 3 runtimes.
`Trabajo del operador: opt-in, default ON`

---

## 4. Gestión de errores (transversal)

| Falla | Comportamiento |
|---|---|
| Pedido NL ambiguo | `(None, preguntas)`. **No adivina.** 0 reintentos automáticos |
| LLM caído / runtime sin modelo | `call_llm` no lanza (`pm_llm_client.py:281-283`); la caja NL reporta el error y **el formulario de verbos sigue operativo** |
| `task_ref` fuera del catálogo | Rechazo en F1, antes de emitir una sola op |
| Patch introduce un error nuevo | `review.ok is False` ⇒ commit deshabilitado; el diff **se muestra igual** |
| Error preexistente en el archivo | **No bloquea** (gates por delta, §F2) |
| YAML no parsea (antes) | `ok=False` con el error de PL001; no se ofrece patch |
| YAML no parsea (después) | `ok=False`; el patch **no se ofrece** |
| YAML > 512 KB | `ok=False` con mensaje; no se procesa (espejo de `cicd_semantic_rules.py:51`) |
| > 12 ops en un plan | Rechazo con "partilo en dos ediciones" |
| Ops solapadas | Rechazo **total**; nunca se aplica media edición |
| Item con `-` en línea propia | Error accionable; **nunca se adivina la indentación** |
| El archivo cambió desde el diff | **409** con el sha nuevo; el operador vuelve a ver el diff |
| El cliente manda un YAML final | **Se ignora**: el servidor recompila desde el `intent` |
| Rama = rama por defecto | **400.** Nunca se commitea sobre la rama por defecto |
| Writer sin soporte de escritura | **501** con el YAML parcheado y los hunks intactos; la UI ofrece copiar. **Nunca se dice "commiteado"** |
| Plan 248 ausente | El botón de recomendaciones **no se muestra**; la edición NL funciona igual |
| `repo_root` ausente | RS006 no se evalúa y se declara `skipped`; **nunca** "validado" por omisión |
| Flag OFF | 404 en los 4 endpoints; el panel no se renderiza; **el builder gráfico queda idéntico a hoy** |

## 5. Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | **Pérdida silenciosa de comentarios o de construcciones no modeladas** | Media | **Crítico** | Tests 3, 5 y 6 de F0 sobre los 9 goldens: 337 comentarios y `scan_unsupported` invariante. Es el riesgo que define el plan |
| R2 | El `end_mark` mal interpretado huerfana comentarios en el paso equivocado | **Alta** | Alto | §2.3 escrito como fórmula + `test_fin_efectivo_excluye_comentario_del_siguiente_item` |
| R3 | Gates demasiado estrictos vuelven ineditables los pipelines reales | **Alta** | Alto | Delta en vez de valor absoluto + `test_error_preexistente_no_bloquea_la_edicion` (F2) |
| R4 | Corrimiento de índices produce decenas de findings "nuevos" falsos | Alta | Medio | `_finding_key` normaliza `[\d+]` → `[]` + test 4 de F2 |
| R5 | El LLM inventa una tarea o un input | Media | Alto | Catálogo cerrado (`is_allowed`, `validate_inputs`) + RS008 en `nl_strict` sobre los bloques insertados |
| R6 | Inyección hacia agentes self-hosted vía el pedido NL | Baja | **Crítico** | El NL nunca llega al YAML (test 7 de F5); `display_name`/`inputs` de 1 línea, ≤200 chars, emitidos por `yaml.safe_dump`; RS004 bloquea `PowerShell@2` inline |
| R7 | El operador aprueba un diff y se escribe otro archivo | Baja | Alto | Doble sha256 (`before_sha256` + `approved_after_sha256`) ⇒ 409 |
| R8 | No determinismo del LLM confunde al operador | Media | Medio | El `EditIntent` (8 campos) se muestra **antes** del diff; el tramo intent→patch es determinista |
| R9 | El alcance no entra en una corrida | Media | Alto | **6 fases**, provider ADO solo, 7 verbos, sin bucle de reparación (§3), y F0–F4 entregan la feature completa sin LLM |
| R10 | Costo de LLM | Baja | Bajo | 1 llamada por pedido, tope por flag, 0 reintentos |

**Reversibilidad (explícita, como pide el alcance):**

1. **Nada se escribe sin `confirm=True`.** El estado por defecto es "no escrito".
2. **Todo commit va a una rama**, nunca a la rama por defecto (candado 2 de F3). Descartar la
   rama restaura el estado anterior **byte por byte** — y esto es cierto *porque* el patch es un
   splice sobre el original, no una regeneración: no hay ruido de reformateo que sobreviva.
3. `git revert` del commit funciona limpio por la misma razón.
4. `STACKY_PIPELINE_NL_EDIT_ENABLED=false` **desde la UI** apaga la feature entera.
5. Las 6 fases son **aditivas**: no se modifica ningún módulo existente de pipelines
   (`pipeline_generator.py`, `pipeline_renderers.py`, `pipeline_lint.py`,
   `cicd_semantic_rules.py` quedan intactos), así que revertir el plan es borrar archivos nuevos
   más 4 líneas de registro.

## 6. Fuera de scope (nombrando los planes de la serie)

- **Crear una pipeline desde cero por lenguaje natural** → **Planes 243 (F0..F3.5) y 244
  (F4..F9)**. El 250 **no** genera pipelines: sólo modifica una que ya existe. Si el archivo no
  existe, el panel lo dice y remite al generador.
- **Descubrir qué pipelines hay** (registro multiproveedor, estado de última corrida) → **Plan
  246**. El 250 recibe la ruta y el contenido; no los busca.
- **Perfilar** (stack, anatomía, propósito en 1 línea) → **Plan 247**.
- **Definir reglas nuevas de seguridad o de optimización** (`SEC001..SECnn`, recomendaciones
  `OPT*`) → **Plan 248**. El 250 **consume** sus recomendaciones si están (puente con import
  blando, §F5) y **no define ni una regla nueva**. Tampoco redefine `PL001..PL014`
  (Plan 186) ni `RS001..RS009` (Plan 243 F3): las **usa**.
- **Paridad GitLab del motor** (catálogo GitLab, `GL001..GLnn`, endurecer parser/renderer GitLab)
  → **Plan 249**. El 250 es **ADO solamente**; cuando el 249 exista, el motor de F0 sirve igual
  porque es agnóstico de proveedor (opera sobre texto YAML y marcas de línea), pero **este plan no
  lo declara soportado ni lo testea**.
- **Matriz de entornos y valores que sólo el operador conoce** → **Plan 251**.
- **Paquete de entrega, README operativo y frontera de capacidades** → **Plan 252**.
- **Registrar la definición en ADO y disparar la primera corrida** → **Plan 244 F8**. El 250
  termina en el commit a la rama; **no dispara ninguna corrida**.
- **Migrar los pipelines existentes** a ningún modelo nuevo.

## 7. Glosario, orden de implementación y DoD

### 7.1 Glosario

| Término | Significado exacto en este plan |
|---|---|
| **Patch quirúrgico** | Reemplazo de un conjunto de rangos de líneas del documento original. Todo lo demás queda **byte-idéntico** |
| **Round-trip / regeneración** | `parse → modelo → render`. **Prohibido** en la ruta de edición: destruye 337/337 comentarios (§0) |
| **Anchor** | Nodo del YAML localizado en el texto (path + rango de líneas + columnas), obtenido con `yaml.compose` |
| **Fin efectivo** | Última línea con contenido real de un nodo, excluyendo blancos y comentarios que pertenecen al siguiente (§2.3) |
| **Hunk** | Rango del original + sus líneas antes/después + el motivo. Es **la verdad** del cambio, no una reconstrucción por LCS |
| **Gate por delta** | Un hallazgo bloquea sólo si **no estaba antes** del patch |
| **`EditIntent`** | Estructura cerrada de 8 campos: lo único que produce el LLM |
| **`EditPlan`** | Tupla de `EditOp` derivada del intent de forma 100 % determinista |

### 7.2 Orden de implementación (obligatorio)

**F0 → F1 → F2 → F3 → F4 → F5.** Ninguna fase depende de una posterior.
F1 usa el índice de F0; F2 usa los hunks de F0; F3 usa F0+F1+F2; F4 usa F3; F5 usa F1 y el
catálogo del 243 F0.

> **Punto de corte seguro:** al terminar **F4**, la feature está **completa y usable**
> (edición quirúrgica por controles, diff visible, commit HITL, sin ningún modelo). **F5 sólo
> agrega la puerta de entrada en prosa.** Si la corrida se queda sin sesión, se corta acá y se
> declara; no se entrega media F5.

### 7.3 Comandos exactos (dossier §4, verificados el 2026-07-26)

> **Trampa de la casa:** conviven `backend/.venv` (**Python 3.13.5**) y `backend/venv`
> (**3.11.9**). **Usá `.venv`.** El frontend **no tiene script `test`**: `npm test` falla, se usa
> `npx vitest`. Los tests se corren **por archivo** (la suite completa se contamina).

```powershell
# --- BACKEND ---
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan250_patcher.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan250_verbos.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan250_gates_delta.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan250_api.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan250_flag.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan250_edit_intent.py -q

# --- BACKEND: no regresión (nada de esto puede ponerse rojo) ---
.venv\Scripts\python.exe -m pytest tests/test_plan73_round_trip.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan73_render_ado.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan73_generator_endpoint.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan243_reglas_semanticas.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan243_renderer_ado.py -q

# --- BACKEND: obligatorios tras crear tests / tocar flags ---
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q

# --- FRONTEND ---
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/devops/__tests__/pipelineEditModel.test.ts
npx tsc --noEmit
```

### 7.4 Definición de Hecho (BINARIA)

- [ ] **6** archivos de test backend verdes, corridos **por archivo**: `test_plan250_patcher.py`
      (12), `test_plan250_verbos.py` (10), `test_plan250_gates_delta.py` (9),
      `test_plan250_api.py` (8), `test_plan250_flag.py` (4), `test_plan250_edit_intent.py` (9)
      = **52 casos**.
- [ ] **1** archivo de test frontend verde: `pipelineEditModel.test.ts` (8).
- [ ] **KPI-1:** `test_los_337_comentarios_del_corpus_sobreviven` verde — **337/337** sobre los 9
      goldens.
- [ ] **KPI-2:** `test_el_diff_real_no_sale_de_los_hunks_declarados` verde sobre los 9 goldens.
- [ ] `test_construcciones_no_modeladas_no_desaparecen` verde — `scan_unsupported` invariante,
      con `matrix` conservado en `ci-batch.yml` y `compile_time_expression` en
      `bootstrap-server-environment.yml`.
- [ ] `test_fin_efectivo_excluye_comentario_del_siguiente_item` verde — el `end_mark` está bien
      interpretado (§2.3).
- [ ] **KPI-3:** `test_patch_que_introduce_error_nuevo_no_se_ofrece` verde — **ADO-369 se
      detectaría también en la ruta de edición**.
- [ ] `test_error_preexistente_no_bloquea_la_edicion` verde — el gate no es inútil de estricto.
      *Este y el anterior, los dos, o el gate es mentira.*
- [ ] **KPI-4:** `test_commit_sin_confirm_es_400` y `test_commit_sobre_rama_default_es_400` verdes.
- [ ] `test_commit_ignora_el_yaml_del_cliente` verde — el servidor recompila siempre.
- [ ] **KPI-5:** `test_una_sola_llamada_llm_por_pedido` verde — exactamente 1, aun con JSON
      inválido.
- [ ] `test_el_texto_nl_no_llega_al_yaml` verde.
- [ ] `test_recomendacion_sin_plan_248_degrada` verde — **sin `ImportError`**.
- [ ] **No regresión:** `test_plan73_round_trip.py`, `test_plan73_render_ado.py`,
      `test_plan73_generator_endpoint.py`, `test_plan243_reglas_semanticas.py`,
      `test_plan243_renderer_ado.py` verdes. **`pipeline_generator.py`,
      `pipeline_renderers.py`, `pipeline_lint.py` y `cicd_semantic_rules.py` sin modificar**
      (verificable con `git diff --name-only`).
- [ ] `test_harness_ratchet_meta.py` verde con los **6** archivos registrados en **las DOS**
      listas (`run_harness_tests.sh:20` y `run_harness_tests.ps1:13`).
- [ ] `test_default_known_only_for_curated` verde; ambas flags visibles y editables **desde la UI**.
- [ ] `npx tsc --noEmit` sin errores nuevos; ratchet de deuda de UI **sin crecer**; **cero
      `style={{...}}` inline** en el `.tsx` nuevo.
- [ ] **Paridad de runtimes:** F0–F4 no invocan LLM ni red ⇒ corren igual en Codex CLI, Claude
      Code CLI y GitHub Copilot Pro (**fallback: no aplica, no hay nada que degradar**). F5 pasa
      por `call_llm`, que **nunca lanza**; **fallback explícito**: sin modelo, la caja NL informa
      el error y **el formulario de verbos de F4 sigue 100 % operativo**.
- [ ] **Smoke visual del operador** (no automatizable: no hay `jsdom` ni
      `@testing-library/react`): abrir una pipeline real, pedir un cambio, **ver el diff**,
      confirmar, y verificar en la rama que **los comentarios siguen ahí**.
