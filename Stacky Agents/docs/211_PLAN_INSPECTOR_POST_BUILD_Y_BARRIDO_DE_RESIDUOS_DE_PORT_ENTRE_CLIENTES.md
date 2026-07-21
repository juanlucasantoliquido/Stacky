# Plan 211 — Inspector post-build + barrido de residuos de port entre clientes

> Estado: **PROPUESTO v1** (2026-07-21). Pipeline: proponer → **[este paso ✓]** → criticar (`criticar-y-mejorar-plan`) → implementar (`implementar-plan-stacky`) → supervisar.
> Autor: StackyArchitectaUltraEficientCode (perfil normal, heredado de Opus 4.8).
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro (paridad obligatoria; el núcleo NO usa LLM).
>
> **Estado: CRITICADO v2 — RECHAZADO→CORREGIDO (2026-07-21).** Juez adversarial (perfil normal, heredado de Opus 4.8). v1 tenía 2 BLOQUEANTES (falsos positivos que bajaban el gate del developer). Esta v2 los corrige.

---

## Changelog v1 → v2 (correcciones del juez, anclado en repo)

- **C1 (BLOQUEANTE) — Match por substring de tokens cortos elevado a bloqueante.** v1 hacía `if tok in low` (substring crudo) con `_MIN_TOKEN_LEN=4` y `server/path/workspace = blocking`: un token ajeno de 4 chars como `crea` (cliente CREA) matcheaba dentro de `CrearCliente`/`Creacion` y **bajaba el `gate_ok` del developer** sobre código legítimo (viola human-in-the-loop + DX + "no degradar"). **Fix v2:** match por **límite de palabra** (lookarounds no-alfanuméricos, no substring) + severidad **bloqueante solo para tokens de alta confianza** (`len≥6` o con dígito/separador de host/ruta) — un token corto/común nunca baja el gate, cae a `warning`. (F2)
- **C2 (BLOQUEANTE) — El catálogo excluía el proyecto ACTIVO GLOBAL, no el del TICKET.** v1: el contribuidor llamaba `build_foreign_token_catalog(None)` → excluía `get_active_project()` (estado global). Si el developer corre un ticket de Pacífico y el activo global es Ripley, v1 **NO excluía Pacífico** (trataba los tokens propios como ajenos → tormenta de bloqueantes sobre el proyecto correcto) y **excluía Ripley** (ceguera al residuo real). Rompe la premisa multicliente central. **Fix v2:** el catálogo se resuelve con el **proyecto del ticket** (`dev_build_verify.project_name_for_ado(ado_id)`), no con `None`/activo global. (F3)
- **C3 (IMPORTANTE) — `changed_files` en árbol compartido / developer que commitea.** v1 usaba `git status --porcelain` (working tree) con fallback ciego a `HEAD`. En árbol compartido con sesión paralela viva, el porcelain trae archivos de OTRA sesión; y si el developer commiteó, `HEAD` puede no ser su commit. **Fix v2:** `changed_files` acepta un `base_ref` opcional para diff acotado (`base_ref..HEAD`, autoría confiable); sin él degrada al working tree pero **la severidad efectiva exige alta confianza para bloquear** (C1) → un archivo ajeno nunca voltea el gate por un token dudoso. Hazard documentado. (F2/R9)
- **C4 (IMPORTANTE) — Acoplamiento de metadata cruzado 211→210.** v1 F4 pedía "agregar la escritura de `execution.metadata['build_findings']` en el punto donde el 210 re-persiste el veredicto" = editar código dueño del 210 (seam CONGELADA, con juez del 210 corriendo en paralelo). **Fix v2:** el 211 **no toca el 210**; la UI (F5) consume el resumen que el 210 **ya** persiste (`execution.metadata['build_verdict']`), extendido con los `blocking_findings`/`warnings` que el `BuildVerdict` (contrato §5 del 210) ya define. Se declara como **dependencia dura** sobre el 210, no como edit oportunista. (F4/F5)
- **C5 (IMPORTANTE) — Doble registro de contribuidores duplica findings.** v1 `register()` no era idempotente: si `create_app()` corre >1 vez (tests), los contribuidores se registraban dos veces → findings duplicados → doble bloqueante. **Fix v2:** guard `_REGISTERED` a nivel módulo. (F3/R6)
- **C6 (IMPORTANTE) — Parser de `git status --porcelain` sin especificar.** v1 mencionaba `_parse_porcelain` sin definirlo → un modelo menor lo haría naïve y fallaría con renames (`R  old -> new`) y paths con espacios/unicode (git los cita y escapa). **Fix v2:** `_parse_porcelain` especificado (salta `XY `, toma el destino en renames, descomilla C-escapes). (F2)
- **C7 (IMPORTANTE, seguridad) — Símbolo de masking inexistente.** v1 importaba `from services.secret_masking import mask_secrets` — **no existe**; el real es `mask_token_values` (`services/secret_masking.py:20`). El `except` silencioso dejaba el masking SIN aplicar → un residuo en una línea con credenciales se publicaba **sin enmascarar** (degrada seguridad). **Fix v2:** símbolo exacto `mask_token_values`. (F2/R4)
- **C8 (MENOR) — Nomenclatura `kind` incoherente.** El caso bloqueante de OutputPath es el **token ajeno**, no "absoluto"; v1 lo llamaba `abs_output_path`. **Fix v2:** `foreign_output_path` (blocking) vs `abs_output_path` (warning, absoluto propio). (§5/F1)
- **C9 (MENOR) — Typo en comentario (`'onlin e'`).** Corregido. (F2)
- **C10 (MENOR) — Sin huella de error.** Se agrega fingerprint del patrón "residuo de port / efecto colateral de build" a `docs/sistema/error_fingerprints.json`. (F6)
- **C11 (MENOR) — Cobertura dependiente de datos.** Documentado: con perfiles ajenos incompletos (server/client_label vacíos, paths genéricos), el catálogo ajeno queda vacío y la Capa C no detecta nada (no es bug; es límite de cobertura). (§2)
- **[ADICIÓN ARQUITECTO] — Allowlist de supresión de residuos por proyecto, editable por UI** (`client_profile.port_residue.allowlist`): válvula human-in-the-loop para el falso positivo inevitable, sin tener que apagar la feature. Default vacío (cero trabajo), backward-compatible. (§4/F2/F3)

---

## Planes relacionados (leer antes de implementar)

- **DEPENDE de Plan 210** — "Gate de build determinista del Developer: fin del falso 'Build OK'" (`Stacky Agents/docs/210_PLAN_GATE_DE_BUILD_DETERMINISTA_DEL_DEVELOPER_FIN_DEL_FALSO_BUILD_OK.md`). Este plan **consume el `BuildVerdict`** (contrato §5 del 210) y se engancha en la **seam de contribuidores de evidencia** que el 210 expone: `dev_build_verify.register_evidence_contributor(fn)` (F5 del 210). Los findings **bloqueantes** que produce este plan **fluyen al `gate_ok`** del 210 (bajan el estado + tiñen el deliverable de rojo) por el mecanismo de re-persistencia del veredicto que ya define el 210 F5. **No implementar 211 sin 210.**
- **DEPENDE (transitivo) de Plan 201** — "Taller de Compilación" (`Stacky Agents/docs/201_PLAN_TALLER_DE_COMPILACION_DETECCION_SLN_BUILD_RELEASE_1CLICK_Y_ARTEFACTOS_DESCARGABLES.md`). La Capa B inspecciona los **project files construidos** que el 210 resolvió (vía el `build.summary.json` + `verdict.solutions` del 201). Reusa el scanner `solution_scanner` (F1 del 201) para mapear `.sln → .csproj` cuando hace falta.
- **Coordina con Plan 208** — igual que el 210: cuando el 208 cablee la transición de estado en runners, el gate del 210 (que este plan alimenta con findings) debe correr en ese path. Sin acción extra en este plan.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** El Plan 210 verifica que el Developer **compiló** (veredicto de máquina). Este plan agrega dos inspecciones **deterministas** que van más allá del exit code de compilación y cierran un agujero real del trabajo multicliente de Stacky: **(Capa B) Inspector post-build** — parsea los archivos de proyecto construidos (`.csproj`/`.sln`) buscando efectos colaterales de build peligrosos (`PostBuildEvent`, `<Target AfterTargets="Build">`, tareas `<Copy>`, `OutputPath`/`OutDir` con rutas **absolutas** o tokens de **otro cliente**) — porque "compila" no garantiza "no copia binarios a la carpeta de otro cliente"; **(Capa C) Barrido de residuos de port** — grep determinista de los archivos que el Developer **tocó** contra un catálogo de tokens de **otros clientes** del registro de perfiles de Stacky (servidores de BD, rutas, `product_name`/`client_label`) — para atrapar residuos tras portar la estructura de un cliente a otro (ej.: quedó un servidor o una ruta de **Ripley** en un cambio de **Pacífico**). Ambas emiten **findings** tipados (warning/bloqueante) que se anexan al deliverable, aparecen en la UI, y — si son bloqueantes — **bajan el `gate_ok` del 210** (el ticket no avanza a "Build OK"). Núcleo 100% determinista, sin LLM, idéntico en los 3 runtimes.

**Gap que cierra.** Hoy nada en Stacky mira los efectos colaterales del build ni detecta residuos de un cliente en otro; con el trabajo multicliente (Ripley/Pacífico/CREA/…) un port trae residuos silenciosos que "compilan" igual y llegan a QA/ADO como "OK".

**KPI / impacto medible (binarios).**
- **KPI-1 — Detección de PostBuildEvents peligrosos:** 100% de los `.csproj` construidos con un `PostBuildEvent`/`<Copy>`/`AfterTargets` con ruta absoluta o token ajeno producen ≥1 finding. Medible: fixtures de F1 + contador `post_build_inspect.blocking`.
- **KPI-2 — Detección de residuos de port:** dado un archivo cambiado con un token **de alta confianza** de otro cliente (servidor tipo `dbripley01`, ruta distintiva), se produce ≥1 finding bloqueante; con un token **corto/común** que matchea como palabra, se produce un **warning** (nunca blocking). Cobertura condicionada a perfiles ajenos configurados (C11). Medible: fixtures de F2 + contador `port_residue.blocking`.
- **KPI-3 — Cero falsos verdes compuestos:** un build que "compila" pero tiene un residuo bloqueante NO obtiene `gate_ok` (el 210 lo baja). Medible: test de integración F4.
- **KPI-4 — Bajo ruido / no bloquear al developer por falso positivo (DX + human-in-the-loop):** match por **límite de palabra** (no substring), bloqueo **solo** para tokens de alta confianza, exclusión del proyecto **del ticket** (no el activo global), y **allowlist por perfil**. Invariante binario: un token corto/común (`crea`) dentro de una palabra (`CrearCliente`) → **0 findings**; como palabra suelta → **warning, no blocking**. Medible: tests `test_word_boundary_not_substring`, `test_short_common_token_is_warning_not_blocking`, `test_scan_own_tokens_zero_findings`, `test_allowlist_suppresses_token`.
- **KPI-5 — Paridad 3 runtimes:** parsing + catálogo + scan + severidad son Python determinista → idéntico en Codex/Claude/Copilot. Cero LLM.
- **KPI-6 — Cero regresión:** ambas flags OFF → el deliverable/estado queda idéntico al del 210 solo. Ningún test existente se rompe.

---

## 2. Por qué ahora / gap que cierra (anclado en evidencia verificada)

Anclas releídas contra el repo el 2026-07-21:

1. **El 210 verifica el exit code, pero no los efectos colaterales del build.** El `BuildVerdict` del 210 (`services/dev_build_verify.py`, contrato §5 del Plan 210) tiene `ok`/`entry_kind`/`returncode`/`summary_path` — dice "compiló", no "el `.csproj` no copia binarios a `C:\OtroCliente\bin`". Un `PostBuildEvent` con `xcopy` a una ruta ajena **compila con returncode 0** y hoy nadie lo mira.
2. **Stacky es multicliente y ya tiene el registro de perfiles necesario para el catálogo de "otros clientes".** `project_manager.get_all_projects()` (`backend/project_manager.py:39`) devuelve la lista de configs (`projects/<dir>/config.json`), y cada config trae su `client_profile` inline — el loader canónico es `services/client_profile.load_client_profile(project_name)` (`backend/services/client_profile.py:266`), y el perfil tiene `terminology.product_name`/`terminology.client_label` (`Developer.agent.md:54`), `database.server` (`azure_devops.json:23-24`) y `code_layout.online_path`/`batch_path` (`azure_devops.json:3-8`). El proyecto activo se obtiene con `runtime_paths._active_workspace_root()` (`runtime_paths.py:66-103`) / `project_manager.get_active_project()` (`project_manager.py:65`). **La materia prima para detectar "esto es un token de OTRO cliente" ya existe; falta el barrido.**
3. **El Developer porta estructura entre clientes de RS (mismo producto, distinto cliente).** Los agentes `rs-techdev-docs`/`ripley-techdev-docs` trabajan el mismo producto RS sobre distintos clientes (Ripley Oracle, Pacífico SQL Server). Portar una pantalla/lote de un cliente a otro deja residuos (servidor, rutas `trunk/OnLine`, nombres) que "compilan" pero apuntan al cliente equivocado. No hay red de seguridad determinista.
4. **El 210 ya expone la seam exacta para colgar estas inspecciones sin re-tocar el publish.** F5 del Plan 210 define `dev_build_verify.register_evidence_contributor(fn)` y la re-persistencia del veredicto con los `blocking_findings` fusionados, de modo que un finding bloqueante de un contribuidor **baja el `gate_ok`** que el gate de estado (F4 del 210, en `api/tickets.py:530` `_apply_task_state`) lee después. **Este plan solo registra dos contribuidores; no modifica `publish_from_execution` ni `_apply_task_state`.**
5. **Hay patrón determinista de parsing de `.csproj`/`.sln` a reusar.** El scanner del 201 (`services/solution_scanner.py`, F1 del 201) ya lee `.sln`, resuelve `.csproj` y lee heads acotados (`_read_head_bytes`) sin red ni LLM, nunca lanza. La Capa B replica ese patrón para inspeccionar los project files.
6. **Hay patrón de enmascarado de secretos reusable** (Plan 188/195: `secret_masking`) por si un residuo aparece en una línea con credenciales — el evidence se enmascara antes de anexarlo al deliverable. Degrada a truncado si no está disponible.

7. **Límite de cobertura (C11) — verificado contra el perfil default.** `client_profile_defaults/azure_devops.json` trae `database.server`, `terminology.product_name`, `terminology.client_label` **vacíos** (`""`) y `code_layout.*_path` **genéricos** (`trunk/OnLine`, `trunk/Batch`, `trunk/lib`) que caen por stoplist/min-len. Por eso el catálogo de tokens ajenos **solo se puebla con perfiles ajenos realmente configurados** (server real, client_label real, workspace distintivo). Con perfiles ajenos incompletos, la Capa C no detecta residuos — **no es un bug, es un límite de cobertura**: la red de seguridad rinde en la medida en que los perfiles de los otros clientes estén completos. Esto NO afecta la seguridad (nunca inventa findings); solo la exhaustividad. Documentado en KPI-2.

**Conclusión:** aditivo, determinista, de bajo riesgo. Dos servicios puros nuevos + dos contribuidores registrados en la seam del 210. Nada nuevo en el publish ni en el gate. El bloqueo de un residuo exige **alta confianza** del token (C1) y se resuelve contra el **proyecto del ticket** (C2), de modo que un falso positivo nunca baja el gate del developer solo.

---

## 3. Principios y guardarraíles (NO negociables)

- **G1 · Determinista, cero LLM.** Parsing, catálogo, scan y severidad son Python puro. Mismo resultado en los 3 runtimes.
- **G2 · Human-in-the-loop.** Solo **inspecciona y reporta**; no edita código del cliente, no borra, no revierte ports. Los bloqueantes **degradan el estado** (vía el gate del 210), no ejecutan ninguna acción. El operador decide.
- **G3 · Bajo ruido / no bloquear al developer por falso positivo (DX + human-in-the-loop).** Match por **límite de palabra** (no substring, C1) + distinctividad (len≥4, stoplist) + exclusión del proyecto **del ticket** (C2) + **allowlist por perfil** (ADICIÓN) + caps. Severidad conservadora: **bloqueante solo para tokens de alta confianza** (`len≥6` o con dígito/separador: hostname/ruta/id; nunca una palabra corta y común). El resto = warning (se ve, no bloquea). **Invariante:** un falso positivo jamás baja el `gate_ok` del developer solo.
- **G4 · Paridad 3 runtimes.** El núcleo no depende del runtime; se ejecuta server-side al publicar/gatear.
- **G5 · Mono-operador sin auth.** Cero RBAC.
- **G6 · No degradar performance/seguridad/estabilidad.** Lecturas acotadas (`_MAX_FILE_BYTES`, cap de archivos y findings). `git` con args de lista (nunca `shell=True`), degradación a `[]` si no hay repo. Evidence enmascarado (secretos). Nunca lanza hacia el publish (todo `try/except`, patrón del 210 F5).
- **G7 · EXCEPCIÓN DURA #3 heredada del 210.** La Capa B solo corre si hubo build (`verdict.solutions`); si el toolchain faltó (`toolchain_missing`) o el 201 no está (`build_workshop_unavailable`), la Capa B no tiene project files construidos → devuelve vacío (no inventa). La Capa C (residuos) corre igual (escanea fuente, no depende del build).
- **G8 · Config vía UI.** Ambas flags visibles/toggleables en Configuración → Arnés → DevOps.

---

## 4. Flags del arnés (dos, default ON) — cableado EXACTO

| Flag | Capa | Categoría | Default |
|------|------|-----------|---------|
| `STACKY_DEV_POST_BUILD_INSPECT_ENABLED` | B (inspector) | `devops` | **ON** |
| `STACKY_DEV_PORT_RESIDUE_SCAN_ENABLED` | C (residuos) | `devops` | **ON** |

Para **cada** flag, los 5 lugares (idéntico patrón al Plan 210 §4; anclas verificadas 2026-07-21):
1. `services/harness_flags.py` — `FlagSpec(key=..., type="bool", label=..., description=..., group="global", default=True)` en `FLAG_REGISTRY` (`harness_flags.py:379`; `FlagSpec` `:21`).
2. `services/harness_flags.py` — agregar la key a la tupla `_CATEGORY_KEYS["devops"]` (`harness_flags.py:117`, tupla `:202`).
3. `tests/test_harness_flags.py` — agregar la key a `_CURATED_DEFAULTS_ON` (`:467`).
4. `config.py` — atributo `Config`: `<KEY>: bool = os.getenv("<KEY>", "true").lower() in ("1","true","yes")` (patrón `config.py:1192-1194`).
5. `api/devops.py` — en `_health_payload()`: `"post_build_inspect_enabled": bool(getattr(cfg,"STACKY_DEV_POST_BUILD_INSPECT_ENABLED",False)),` y `"port_residue_scan_enabled": ...`.

Labels/descriptions:
- `STACKY_DEV_POST_BUILD_INSPECT_ENABLED` — label "Inspector post-build", desc "Detecta PostBuildEvents, tareas Copy y OutputPath con rutas absolutas o de otros clientes en los .csproj construidos por el Developer."
- `STACKY_DEV_PORT_RESIDUE_SCAN_ENABLED` — label "Barrido de residuos de port", desc "Detecta en los archivos que tocó el Developer tokens (servidores, rutas, nombres) de OTROS clientes del registro de perfiles."

> NO hand-editar `harness_defaults.env`. NO hay `requires=` (ambas `bool`). Health key colateral en `/bootstrap` es intencional (paridad).

**[ADICIÓN ARQUITECTO] Campo de perfil nuevo (default seguro): `port_residue.allowlist`** · tipo `list[str]` · **default `[]`**.
- Semántica: válvula **human-in-the-loop** para el falso positivo inevitable. Si el endurecimiento del match (C1) igual reporta un token que en ESTE cliente es legítimo (p.ej. un cliente comparte un fragmento de nombre con otro), el operador lo agrega a la allowlist del perfil y el scanner lo suprime — **sin apagar toda la feature** (G2: amplificar al operador, no reemplazarlo).
- Ubicación: nueva sección `"port_residue": {"allowlist": []}` en `Stacky Agents/backend/services/client_profile_defaults/azure_devops.json`. **No** requiere migración: `scanner.allowlist_for_project` lee `(profile.get("port_residue") or {}).get("allowlist") or []` → perfiles viejos sin la clave = allowlist vacía (backward-compatible, KPI-6).
- Config vía UI: el editor de perfil (`ClientProfileEditor.tsx`) expone el campo como lista editable (chips). Es el ÚNICO input del operador y es opt-in (default vacío = cero trabajo). Cumple la regla dura "toda config del operador por UI".
- Determinista, idéntico 3/3 runtimes (es un filtro de strings server-side).

---

## 5. Arquitectura objetivo

```
BACKEND (Stacky Agents/backend/)
  services/post_build_inspector.py      (F1) PURO — parsea .csproj/.sln → InspectFinding[]
  services/port_residue_scanner.py       (F2/F3) catálogo de tokens ajenos + _changed_files(git) + scan → ResidueFinding[]
  services/dev_build_contributors.py     (F3) los 2 contribuidores que se registran en la seam del 210 + register(fn)
  app.py                                  (F3) +1 bloque: dev_build_contributors.register(dev_build_verify.register_evidence_contributor)

FRONTEND (Stacky Agents/frontend/src/)
  components/portFindingsModel.ts         (F5) helpers PUROS (agrupar/contar/severidad/label)
  components/portFindingsModel.test.ts    (F5) vitest
  components/OutputPanel.tsx              (F5) pane "Inspección post-build / Residuos" desde execution.metadata.build_verdict.{blocking_findings,warnings} (el 210 lo persiste; C4)
```

**Contratos de finding (CONGELADOS por F1/F2):**
```python
@dataclass(frozen=True)
class InspectFinding:
    kind: str        # 'post_build_event' | 'after_targets' | 'copy_task' | 'abs_output_path'(warning) | 'foreign_output_path'(blocking) | 'foreign_token_in_project'
    severity: str    # 'blocking' | 'warning'
    file: str        # ruta del .csproj/.sln
    detail: str      # explicación legible
    evidence: str    # snippet matcheado, truncado a 200 chars

@dataclass(frozen=True)
class ResidueFinding:
    token: str
    kind: str        # 'server' | 'path' | 'workspace' | 'product' | 'client_label'
    severity: str    # 'blocking' | 'warning'
    file: str
    line: int
    evidence: str    # línea matcheada, enmascarada+truncada
    source_project: str   # de qué otro cliente es el token
```
Ambos se serializan a `dict` (via `asdict`) para fluir por la seam del 210 como `{kind,severity,file,detail}` (mapeo: `InspectFinding.detail`→`detail`; `ResidueFinding` compone `detail = f"token '{token}' de {source_project} ({kind})"`).

---

## 6. Fases

> Convención de tests idéntica al Plan 210 §6 (backend por archivo con el venv; frontend vitest por archivo; registrar cada `test_*.py` en `HARNESS_TEST_FILES`, `run_harness_tests.sh:20`).

---

### F0 — Flags + esqueleto de módulos (gate primero)

**Objetivo:** dejar las 2 flags cableadas (5 lugares c/u §4) y `post_build_inspector.py` / `port_residue_scanner.py` / `dev_build_contributors.py` creados con firmas y dataclasses, sin lógica (stubs que devuelven `[]`). Valor: de-riesga la ceremonia.

**Archivos a editar/crear:** los de §4 (harness_flags ×2, test_harness_flags, config, devops.py) + los 3 módulos backend (stubs con los dataclasses de §5 y firmas públicas devolviendo `[]`).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan211_flags.py`:**
- `test_both_flags_registered_and_curated` (ambas keys en `FLAG_REGISTRY`, `_CATEGORY_KEYS["devops"]`, `_CURATED_DEFAULTS_ON`).
- `test_health_exposes_both_flags` (`/api/devops/health` incluye `post_build_inspect_enabled` y `port_residue_scan_enabled`).
- `test_modules_import_clean` (importar los 3 módulos no lanza; `inspect_projects([], workspace_root="x") == []`).
- Registrar en `HARNESS_TEST_FILES`. Correr: `& ".venv\Scripts\python.exe" -m pytest tests\test_plan211_flags.py tests\test_harness_flags.py -q`

**Criterio BINARIO:** comando verde; `grep -rn "STACKY_DEV_POST_BUILD_INSPECT_ENABLED\|STACKY_DEV_PORT_RESIDUE_SCAN_ENABLED" "Stacky Agents/backend/config.py"` → 2 matches.

**Flag:** ambas (default ON). **Runtime:** idéntico 3/3. **Operador:** ninguno.

---

### F1 — Inspector post-build (`post_build_inspector.py`, Capa B)

**Objetivo:** función pura que parsea los project files construidos y emite findings por efectos colaterales peligrosos. Valor: "compila" ya no oculta un `PostBuildEvent` que copia a otro cliente.

**Archivo a editar:** `Stacky Agents/backend/services/post_build_inspector.py`.

**API pública:**
```python
def inspect_projects(project_files: list[str], *, workspace_root: str,
                     foreign_tokens: dict | None = None) -> list[InspectFinding]
```
- `project_files`: rutas de `.csproj`/`.sln` construidos (el contribuidor F3 los deriva de `verdict.solutions` + resolución `.sln→.csproj`).
- `foreign_tokens`: catálogo opcional de la Capa C (para elevar a bloqueante un build event que menciona a otro cliente). Si None, se usa `{}`.

**Constantes:**
```python
_MAX_FILE_BYTES = 262144
_ABS_WIN_RE = re.compile(r'([A-Za-z]:[\\/]|\\\\[^\\/])')     # C:\... o UNC \\server
_POST_BUILD_RE = re.compile(r'(?is)<PostBuildEvent>(.*?)</PostBuildEvent>')
_TARGET_AFTER_RE = re.compile(r'(?is)<Target\b[^>]*\b(?:AfterTargets|BeforeTargets)\s*=\s*"[^"]*Build[^"]*"[^>]*>(.*?)</Target>')
_COPY_RE = re.compile(r'(?is)<Copy\b[^>]*?(DestinationFolder|DestinationFiles)\s*=\s*"([^"]*)"')
_OUTPUT_RE = re.compile(r'(?is)<(OutputPath|OutDir)>([^<]*)</(?:OutputPath|OutDir)>')
```

**Reglas de severidad (deterministas):**
- `<PostBuildEvent>` presente: si su contenido matchea `_ABS_WIN_RE` o `_contains_foreign(content, foreign_tokens)` → `blocking` (`kind="post_build_event"`); si no (relativo, benigno) → `warning`.
- `<Target AfterTargets/BeforeTargets="...Build...">`: si el cuerpo tiene abs path o token ajeno → `blocking` (`kind="after_targets"`); si contiene `<Exec>`/`<Copy>` pero relativo → `warning`; sin tareas relevantes → sin finding.
- `<Copy DestinationFolder|DestinationFiles="X">`: `X` abs o token ajeno → `blocking` (`kind="copy_task"`); relativo → `warning`.
- `<OutputPath>`/`<OutDir>`: valor **absoluto propio** (sin token ajeno) → `warning`, `kind="abs_output_path"` (común y benigno). Valor con **token ajeno** → `blocking`, `kind="foreign_output_path"` (C8: el bloqueante es "ajeno", no "absoluto"). (`_contains_foreign` usa match por límite de palabra, no substring — ver C1.)
- Errores por archivo (no existe, no lee) → se saltan (nunca propaga).

**Helpers:**
```python
def _read_head(path):
    try:
        with open(path, "rb") as fh: return fh.read(_MAX_FILE_BYTES).decode("utf-8", errors="replace")
    except OSError: return ""
def _is_abs(s): return bool(_ABS_WIN_RE.search(s or ""))
def _contains_foreign(text, foreign_tokens):
    low = (text or "").lower()
    for tok in (foreign_tokens or {}):                 # C1: límite de palabra, NO substring crudo
        if re.search(r'(?<![a-z0-9])' + re.escape(tok) + r'(?![a-z0-9])', low):
            return tok
    return None
def _trunc(s, n=200): return (s or "").strip()[:n]
```

**Casos borde:** `project_files` vacío → `[]`; `.csproj` sin eventos → `[]`; `PostBuildEvent` relativo (`copy $(TargetPath) ..\shared`) → `warning`; abs (`xcopy "C:\Ripley\bin"`) → `blocking`; `foreign_tokens` con "ripley" y el evento lo menciona → `blocking` con `kind` acorde.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan211_inspector.py`:** (fixtures `.csproj` en `tmp_path`)
- `test_empty_returns_empty`
- `test_post_build_absolute_is_blocking`
- `test_post_build_relative_is_warning`
- `test_copy_task_absolute_is_blocking`
- `test_after_targets_with_foreign_token_blocking` (pasar `foreign_tokens={"ripley": {...}}`)
- `test_output_path_foreign_token_blocking_vs_own_absolute_warning`
- `test_unreadable_file_skipped_no_crash`
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -nE "import requests|copilot|llm" "Stacky Agents/backend/services/post_build_inspector.py"` → 0 matches.

**Flag:** el servicio no chequea flag (lo hace el contribuidor F3). **Runtime:** idéntico 3/3. **Operador:** ninguno.

---

### F2 — Barrido de residuos de port (`port_residue_scanner.py`, Capa C)

**Objetivo:** construir el catálogo de tokens de **otros clientes** y escanear los archivos que el Developer tocó. Valor: atrapar el residuo Ripley→Pacífico.

**Archivo a editar:** `Stacky Agents/backend/services/port_residue_scanner.py`.

**API pública:**
```python
def build_foreign_token_catalog(ticket_project: str | None) -> dict
# ticket_project = el proyecto del TICKET (NO el activo global). Excluye ESE proyecto del catálogo.
# {token_lower: {"source_project": str, "kind": "server"|"path"|"workspace"|"product"|"client_label"}}
def scan_files_for_foreign_tokens(files: list[str], catalog: dict, *, workspace_root: str,
                                  allowlist: list[str] | None = None) -> list[ResidueFinding]
def allowlist_for_project(project_name: str | None) -> list[str]   # ADICIÓN ARQUITECTO
def changed_files(workspace_root: str | None, *, base_ref: str | None = None) -> list[str]
```
> **C2:** el parámetro se renombró `active_project`→`ticket_project` para clavar la semántica: el catálogo excluye el proyecto **del ticket que corre el developer**, no `get_active_project()` (estado global que puede apuntar a otro cliente).

**Constantes:**
```python
_MIN_TOKEN_LEN = 4
_STOPWORDS = {"online","batch","test","tests","src","app","main","code","data","trunk",
              "azure","devops","http","https","true","false","null","none","core","base",
              "prod","dev","qa","release","debug","windows","system","server","local"}
_SOURCE_EXTS = (".cs",".vb",".csproj",".sln",".config",".sql",".aspx",".cshtml",".razor",".resx")
_MAX_FILE_BYTES = 524288
_MAX_FINDINGS = 200
_SEVERITY = {"server":"blocking","path":"blocking","workspace":"blocking",
             "product":"warning","client_label":"warning"}
# C1 — un token solo puede BLOQUEAR si es de alta confianza (inequívocamente ajeno):
#   len>=6, o contiene un dígito/separador de host/ruta. 'crea','motor' (cortos, comunes) NO bloquean.
_HICONF_LEN = 6
```

**`build_foreign_token_catalog` (deterministic):**
```python
def build_foreign_token_catalog(ticket_project):
    from project_manager import get_all_projects, get_active_project
    # C2: excluir el proyecto DEL TICKET (no el activo global). ticket_project lo pasa el contribuidor F3.
    excl_name = (ticket_project or get_active_project() or "").strip().lower()
    all_cfgs = get_all_projects()                      # cada cfg = projects/<dir>/config.json crudo
    excl_ws = ""                                       # ws del excluido, resuelto desde la MISMA lista (testeable)
    for cfg in all_cfgs:
        if str(cfg.get("name") or cfg.get("project_name") or "").strip().lower() == excl_name:
            excl_ws = os.path.normpath(str(cfg.get("workspace_root") or "")); break
    catalog = {}
    for cfg in all_cfgs:
        name = str(cfg.get("name") or cfg.get("project_name") or "").strip()
        ws = os.path.normpath(str(cfg.get("workspace_root") or ""))
        if (name and name.lower() == excl_name) or (excl_ws and ws == excl_ws):
            continue                                   # excluir el proyecto DEL TICKET (auto-referencias)
        prof = cfg.get("client_profile") or {}
        term = prof.get("terminology") or {}
        db = prof.get("database") or {}
        cl = prof.get("code_layout") or {}
        _add(catalog, db.get("server"), name, "server")
        _add(catalog, term.get("product_name"), name, "product")
        _add(catalog, term.get("client_label"), name, "client_label")
        _add(catalog, os.path.basename(ws) if ws else "", name, "workspace")
        for p in (cl.get("online_path"), cl.get("batch_path"), cl.get("lib_path")):
            _add_path_tokens(catalog, p, name, "path")
    return catalog

def _add(catalog, value, source, kind):
    tok = (value or "").strip().lower()
    if len(tok) >= _MIN_TOKEN_LEN and tok not in _STOPWORDS and re.search(r'[a-z0-9]', tok):
        catalog.setdefault(tok, {"source_project": source, "kind": kind})

def _add_path_tokens(catalog, path, source, kind):
    # separa 'trunk/OnLine' -> ['trunk','online']; los genéricos caen por stoplist/min-len,
    # solo sobreviven los segmentos distintivos (C9: corregido el typo 'onlin e').
    for seg in re.split(r'[\\/]+', (path or "")):
        _add(catalog, seg, source, kind)

def allowlist_for_project(project_name):
    # ADICIÓN ARQUITECTO: supresión human-in-the-loop por perfil (editable por UI). Nunca lanza.
    try:
        from services.client_profile import load_effective_client_profile
        prof = load_effective_client_profile(project_name or "") or {}
    except Exception:
        return []
    val = (prof.get("port_residue") or {}).get("allowlist") or []
    return [str(t).strip().lower() for t in val if str(t).strip()]
```
- Nota: los segmentos comunes (`trunk`, `online`) caen por el stoplist → no se agregan. Sobreviven los distintivos (nombres de cliente, servidores). **C2:** `build_foreign_token_catalog(ticket_project)` excluye el proyecto del ticket por nombre **y** por `workspace_root` normalizado; si `ticket_project` es None, cae a `get_active_project()` solo como último recurso (el contribuidor F3 SIEMPRE le pasa el proyecto del ticket).

**`scan_files_for_foreign_tokens`:**
```python
def scan_files_for_foreign_tokens(files, catalog, *, workspace_root, allowlist=None):
    if not catalog: return []
    allow = set(t.strip().lower() for t in (allowlist or []) if str(t).strip())  # ADICIÓN ARQUITECTO
    out = []
    for rel in files:
        if not rel.lower().endswith(_SOURCE_EXTS): continue
        path = rel if os.path.isabs(rel) else os.path.join(workspace_root, rel)
        text = _read_text(path)                       # <= _MAX_FILE_BYTES, errors='replace', OSError→""
        if not text: continue
        low = text.lower()
        for tok, meta in catalog.items():
            if tok in allow: continue                  # el operador marcó este token como legítimo acá
            if not _word_search(low, tok): continue    # C1: límite de palabra, NO substring crudo
            sev = _effective_severity(meta["kind"], tok)   # C1: blocking solo si token de alta confianza
            ln, evidence = _first_line_with(text, tok)
            out.append(ResidueFinding(
                token=tok, kind=meta["kind"], severity=sev,
                file=path, line=ln, evidence=_mask(_trunc(evidence)),
                source_project=meta["source_project"]))
            if len(out) >= _MAX_FINDINGS: return out
    return out

def _word_search(low_text, tok):
    # C1: match por límite de palabra (no substring). 'crea' NO matchea 'crearcliente'.
    # lookarounds de NO-alfanumérico (mejor que \b para tokens con . - _ / : del host/ruta).
    return re.search(r'(?<![a-z0-9])' + re.escape(tok) + r'(?![a-z0-9])', low_text) is not None

def _high_confidence(tok):
    # inequívocamente ajeno: hostname/ruta/id, no una palabra corta y común.
    return len(tok or "") >= _HICONF_LEN or bool(re.search(r'[0-9._\-\\/:]', tok or ""))

def _effective_severity(kind, tok):
    base = _SEVERITY.get(kind, "warning")
    if base == "blocking" and not _high_confidence(tok):
        return "warning"                               # C1: un token corto/común NUNCA baja el gate del developer
    return base
```
- `_mask(s)`: **C7 — símbolo exacto verificado:** `try: from services.secret_masking import mask_token_values; return mask_token_values(s) except Exception: return s`. El nombre es `mask_token_values` (`services/secret_masking.py:20`), NO `mask_secrets` (no existe → el `except` silencioso publicaría secretos SIN enmascarar, degradando seguridad). El fallback (sin-enmascarar) solo aplica si el módulo entero no está; el nombre correcto NO debe fallar.
- `_first_line_with(text, tok)`: itera líneas, devuelve `(nro_linea_1based, linea)` de la primera que contiene `tok` (case-insensitive).

**`_changed_files` (resolver determinista de archivos tocados — se define acá, lo usa el contribuidor F3):**
```python
def changed_files(workspace_root, *, base_ref=None):
    # Determinista, git-only, degrada a [] si no hay repo. NUNCA lanza. Args de lista (no shell).
    # C3 — árbol COMPARTIDO: el working tree puede traer cambios de OTRA sesión; y si el developer
    #   commiteó (Plan 177 auto-PR), HEAD puede no ser su commit. Estrategia por confianza de autoría:
    #   1) si se conoce base_ref del run -> diff acotado base_ref..HEAD (autoría CONFIABLE).
    #   2) si no -> working tree (porcelain); si vacío, fallback a HEAD. Este conjunto NO tiene autoría
    #      garantizada -> por eso _effective_severity (C1) exige ALTA CONFIANZA para bloquear: un archivo
    #      ajeno jamás voltea el gate por un token dudoso; a lo sumo emite un warning visible.
    if not workspace_root or not os.path.isdir(workspace_root): return []
    if base_ref:
        diff = _git(workspace_root, ["diff","--name-only", f"{base_ref}..HEAD"])
        files = [l.strip() for l in diff.splitlines() if l.strip()]
        if files:
            return [f for f in files if f.lower().endswith(_SOURCE_EXTS)]
    porcelain = _git(workspace_root, ["status","--porcelain","--untracked-files=all"])
    files = _parse_porcelain(porcelain)               # modificados/agregados/untracked (autoría no garantizada)
    if not files:
        last = _git(workspace_root, ["show","--name-only","--pretty=format:","HEAD"])
        files = [l.strip() for l in last.splitlines() if l.strip()]
    return [f for f in files if f.lower().endswith(_SOURCE_EXTS)]

def _git(ws, args):
    try:
        p = subprocess.run(["git","-C",ws,*args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        return p.stdout if p.returncode == 0 else ""
    except Exception:
        return ""

def _parse_porcelain(porcelain):
    # C6 — formato porcelain v1: 'XY <path>' o rename/copy 'XY <old> -> <new>'. Paths con espacios/
    #   unicode vienen ENTRE COMILLAS con C-escapes. Devuelve el path efectivo (el NEW en renames).
    out = []
    for raw in (porcelain or "").splitlines():
        if len(raw) < 4: continue
        entry = raw[3:]                               # saltar 'XY ' (2 chars de estado + espacio)
        if " -> " in entry:                           # rename/copy: quedarse con el destino
            entry = entry.split(" -> ", 1)[1]
        entry = entry.strip()
        if len(entry) >= 2 and entry[0] == '"' and entry[-1] == '"':
            try: entry = entry[1:-1].encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8", "replace")
            except Exception: entry = entry[1:-1]
        if entry: out.append(entry)
    return out
```
> **Nota C3 (autoría no garantizada en árbol compartido):** el contribuidor F3 hoy llama `changed_files(ws)` sin `base_ref` (no existe aún infra que capture el commit base del run). La defensa es la severidad por confianza (C1): en el peor caso, un residuo sobre un archivo ajeno emite **warning** (visible, no bloquea). Capturar un `base_ref` por run del developer es un follow-up que eleva estos warnings a bloqueantes con autoría probada.

> **Nota sobre la identidad del proyecto:** la exclusión del proyecto activo es robusta por el **match de `workspace_root` normalizado** (`ws == active_ws`), independiente de que el `config.json` tenga o no una clave `name`/`project_name`. Si esa clave falta, `source_project` queda `""` (solo cosmético en el label del finding); la exclusión NO se ve afectada. Si se quiere el nombre siempre, el implementador puede enumerar los directorios de `projects/` (el nombre del proyecto = nombre de carpeta) — sub-decisión opcional, no requerida.

**Casos borde:** catálogo vacío (proyecto único) → `[]`; el proyecto **DEL TICKET** no aporta tokens (excluido por nombre+ws) → 0 auto-findings; token corto ajeno como `crea` que aparece dentro de `CrearCliente` → **NO matchea** (límite de palabra, C1); token corto/común que sí matchea como palabra → **warning**, nunca blocking (C1); servidor ajeno de alta confianza (`dbripley01`, `10.10.1.5`) → **blocking**; token en allowlist del perfil → **suprimido** (0 findings); token en stoplist (`online`) → no está en catálogo; archivo no-fuente → se salta; sin git → `changed_files → []` (no crashea); rename en porcelain (`R old -> new`) → toma `new`; path con espacios/comillas → descomillado; línea con credencial → evidence enmascarado con `mask_token_values`.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan211_residue.py`:** (monkeypatch `project_manager.get_all_projects` con 2-3 configs fake — cada uno con `name`, `workspace_root` y `client_profile` inline; `tmp_path` con archivos fuente)
- `test_catalog_excludes_ticket_project` (pasar `ticket_project="pacifico"` con configs de pacifico+ripley → tokens SOLO de ripley; **C2**)
- `test_catalog_excludes_by_workspace_root` (dos configs, excluir por `workspace_root` normalizado aunque el nombre difiera)
- `test_catalog_applies_stoplist_and_minlen` ("online"/"src"/"trunk" NO entran; "ripley"/servidor sí)
- `test_word_boundary_not_substring` (**C1**: catálogo con token `crea`; archivo con `CrearCliente` → **0 findings**; archivo con la palabra ` crea ` → 1 finding)
- `test_short_common_token_is_warning_not_blocking` (**C1**: token `crea` kind `server` que sí matchea como palabra → `severity=="warning"`, NO bloquea)
- `test_high_confidence_server_is_blocking` (**C1**: token `dbripley01`/`10.10.1.5` kind `server` → `severity=="blocking"`)
- `test_allowlist_suppresses_token` (**ADICIÓN**: token ajeno en `allowlist=["ripley"]` → 0 findings)
- `test_scan_flags_foreign_path_blocking` (segmento de ruta distintivo, alta confianza → blocking)
- `test_scan_client_label_is_warning`
- `test_scan_own_tokens_zero_findings` (archivo con tokens del proyecto del ticket → 0 findings)
- `test_changed_files_degrades_without_git` (`workspace_root` sin `.git` → `[]`)
- `test_parse_porcelain_rename_and_quoted` (**C6**: `R  a.cs -> b.cs` → `b.cs`; `"con espacio.cs"` → descomillado)
- `test_evidence_is_masked` (línea con patrón de token/credencial → `mask_token_values` la enmascara; **C7**)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -n "shell=True" "Stacky Agents/backend/services/port_residue_scanner.py"` → 0 matches.

**Flag:** el contribuidor F3 gatea. **Runtime:** idéntico 3/3. **Operador:** ninguno.

---

### F3 — Contribuidores + registro en la seam del 210 (`dev_build_contributors.py`)

**Objetivo:** empaquetar Capa B y Capa C como los dos contribuidores que el 210 invoca al anotar el deliverable, cada uno gateado por su flag. Valor: los findings fluyen al deliverable y al `gate_ok` sin tocar el publish.

**Archivo a crear:** `Stacky Agents/backend/services/dev_build_contributors.py`.

**API:**
```python
_REGISTERED = False   # C5: guard de idempotencia (create_app puede correr >1 vez en tests)

def register(register_fn) -> None:
    # register_fn == dev_build_verify.register_evidence_contributor
    global _REGISTERED
    if _REGISTERED: return                             # C5: no duplicar contribuidores → no duplicar findings
    register_fn(_inspect_contributor)
    register_fn(_residue_contributor)
    _REGISTERED = True

def _ticket_ctx(ado_id):
    # C2: resolver el proyecto DEL TICKET y su workspace con los helpers públicos del 210 (una sola impl).
    project_name = dev_build_verify.project_name_for_ado(ado_id)      # 210 F3
    ws = dev_build_verify.workspace_root_for_ado(ado_id)             # 210 F3
    catalog = port_residue_scanner.build_foreign_token_catalog(project_name)  # excluye el proyecto del ticket
    return project_name, str(ws or ""), catalog

def _inspect_contributor(ado_id: int, verdict) -> dict:
    import config as _config
    if not getattr(_config.config, "STACKY_DEV_POST_BUILD_INSPECT_ENABLED", False):
        return _empty()
    if not verdict.solutions: return _empty()          # G7: sin build no hay project files
    _pn, ws, foreign = _ticket_ctx(ado_id)             # C2: catálogo del proyecto del ticket
    project_files = _project_files_for_solutions(verdict.solutions, ws)  # .sln + .csproj (reusa solution_scanner)
    findings = post_build_inspector.inspect_projects(project_files, workspace_root=ws, foreign_tokens=foreign)
    return _to_contribution("Inspección post-build", findings_to_dicts(findings))

def _residue_contributor(ado_id: int, verdict) -> dict:
    import config as _config
    if not getattr(_config.config, "STACKY_DEV_PORT_RESIDUE_SCAN_ENABLED", False):
        return _empty()
    project_name, ws, catalog = _ticket_ctx(ado_id)    # C2: catálogo del proyecto del ticket
    allowlist = port_residue_scanner.allowlist_for_project(project_name)  # ADICIÓN ARQUITECTO
    files = port_residue_scanner.changed_files(ws)
    findings = port_residue_scanner.scan_files_for_foreign_tokens(
        files, catalog, workspace_root=ws, allowlist=allowlist)
    return _to_contribution("Residuos de port entre clientes", residue_to_dicts(findings))
```
- `_to_contribution(title, dicts)`: separa `blocking = [d for d in dicts if d["severity"]=="blocking"]`, `warnings = [...]`, arma `section_html` (una `<table>` con file/severity/detail; verde/amarillo/rojo según haya blocking) y devuelve `{"title": title, "section_html": html, "blocking": blocking, "warnings": warnings}`.
- `_empty()`: `{"title":"","section_html":"","blocking":[],"warnings":[]}`.
- **Helpers públicos del 210 (una sola implementación, NO replicar):** `dev_build_verify.project_name_for_ado(ado_id) -> str | None` (resuelve `Ticket.stacky_project_name`) y `dev_build_verify.workspace_root_for_ado(ado_id) -> str | None` (resuelve el `workspace_root`). Ambos declarados públicos en el Plan 210 F3. El 211 los importa; **C2:** el `project_name` es lo que se pasa a `build_foreign_token_catalog` (no `None`).
- `_project_files_for_solutions(solutions, ws)`: para cada `.sln`, agregar la `.sln` + sus `.csproj` (via `solution_scanner._parse_sln_projects` o `scan_solutions_ex`); degrada a solo las `.sln` si el scanner no está.

**Registro en `app.py`** (junto al bloque de post-hooks, `app.py:853-855`):
```python
# Plan 211 — inspector post-build + residuos de port como contribuidores de evidencia del build (Plan 210).
from services import dev_build_verify, dev_build_contributors
dev_build_contributors.register(dev_build_verify.register_evidence_contributor)
```

**Casos borde:** flag B OFF → `_inspect_contributor` vacío; flag C OFF → `_residue_contributor` vacío; sin build (`verdict.solutions == []`) → inspector vacío, residuos igual corre; sin git → residuos vacío. Un blocking de cualquiera baja `gate_ok` (mecanismo del 210 F5: `annotate_build_evidence` fusiona `blocking` y re-persiste el veredicto → gate de estado del 210 lo lee).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan211_contributors.py`:** (monkeypatch `post_build_inspector.inspect_projects`, `port_residue_scanner.*`, `dev_build_verify.project_name_for_ado`, `dev_build_verify.workspace_root_for_ado`, `_config.config`)
- `test_inspect_contributor_off_returns_empty`
- `test_residue_contributor_off_returns_empty`
- `test_inspect_skips_when_no_solutions`
- `test_catalog_scoped_to_ticket_project` (**C2**: `project_name_for_ado→"pacifico"`; assert que `build_foreign_token_catalog` se llamó con `"pacifico"`, NO con `None`)
- `test_residue_passes_allowlist` (monkeypatch `allowlist_for_project→["x"]`; assert que `scan_files_for_foreign_tokens` recibió `allowlist=["x"]`)
- `test_contribution_shape` (devuelve keys `title/section_html/blocking/warnings`)
- `test_blocking_finding_present_in_contribution`
- `test_register_calls_register_fn_twice` (un fake `register_fn` recibe 2 callables)
- `test_register_is_idempotent` (**C5**: llamar `register(fake)` dos veces → el fake recibe 2 callables en total, NO 4; reset `_REGISTERED` entre tests)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -rn "dev_build_contributors.register" "Stacky Agents/backend/app.py"` → 1 match.

**Flag:** ambas. **Runtime:** idéntico 3/3. **Operador:** ninguno.

---

### F4 — Integración con el gate del 210 (findings bloquean el "Build OK")

**Objetivo:** verificar de punta a punta que un finding bloqueante de este plan baja el `gate_ok` del 210 y, por ende, el estado no avanza y el deliverable sale en rojo. Valor: el falso verde compuesto ("compila pero tiene residuo") queda cerrado.

**Archivos:** ninguno nuevo (el mecanismo lo provee el 210 F5). Esta fase es **de integración/test**: confirma el cableado.

> **Metadata para la UI (C4 — dependencia dura sobre el 210, NO editar el 210 desde acá):** el 211 **no toca** `annotate_build_evidence` ni la re-persistencia del veredicto (código dueño del 210, seam CONGELADA, con juez propio). El 210 ya persiste un resumen en `execution.metadata["build_verdict"]` (210 F7). La UI del 211 (F5) consume **ese mismo** resumen, extendido con `blocking_findings`/`warnings` — campos que el `BuildVerdict` (contrato §5 del 210) **ya define** y que el 210 F5 **ya fusiona** al re-persistir. **Requisito declarado hacia el 210 (en "Planes relacionados"):** que el resumen `execution.metadata["build_verdict"]` incluya `blocking_findings`/`warnings` (o sus conteos + items cap 50). Es un dato que el 210 ya tiene en mano en `session_scope`; se congela su forma en coordinación con el juez del 210. El 211 NO crea la key `build_findings` ni escribe metadata.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan211_integration.py`:** (usa las funciones reales del 210 `annotate_build_evidence` + `read_verdict`, con contribuidores reales monkeypatcheados para devolver un blocking)
- `test_blocking_residue_flips_gate_ok_false` (verdict inicial `gate_ok True`; registrar un contribuidor que devuelve un `blocking` → tras `annotate_build_evidence`, `read_verdict(...).gate_ok is False` y `blocking_findings` no vacío)
- `test_warning_only_keeps_gate_ok_true` (contribuidor con solo `warnings` → `gate_ok` sigue True, pero el warning aparece en el HTML)
- `test_deliverable_html_lists_findings` (el HTML anotado contiene la tabla de findings)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; un blocking de 211 produce `gate_ok False` en el veredicto re-persistido (el gate de estado del 210 F4 lo lee → downgrade).

**Flag:** ambas. **Runtime:** idéntico 3/3. **Operador:** ninguno.

---

### F5 — Pane de findings en la UI (default ON)

**Objetivo:** mostrar los findings al operador junto al veredicto de build. Valor: el operador ve el residuo/efecto colateral de un vistazo.

**Archivos a crear/editar:**
- `Stacky Agents/frontend/src/components/portFindingsModel.ts` — PUROS: `groupBySeverity(items)`, `severityColor(sev): 'red'|'amber'|'gray'`, `findingLabel(kind): string`, `countBlocking(items): number`. Sin `style={{}}` inline.
- `Stacky Agents/frontend/src/components/portFindingsModel.test.ts` — vitest por función.
- `Stacky Agents/frontend/src/components/OutputPanel.tsx` — leer `execution.metadata.build_verdict?.blocking_findings` / `.warnings` (persistido por el 210; C4) y renderizar un pane con la lista (rojo si hay blocking). Solo `agentType === "developer"` y si hay items. Patrón de los panes auxiliares que cuelgan de `execution.metadata` (`OutputPanel.tsx:140`).

**Casos borde:** sin `build_verdict` o sin findings → pane no aparece (no rompe); solo warnings → pane ámbar; con blocking → pane rojo; si el 210 aún no incluye los findings en el resumen → el pane no aparece (degradación limpia, backward-compatible).

**Tests (TDD) — `portFindingsModel.test.ts`:** un `it` por función (grupos, color, label, conteo). Correr: `npx vitest run src\components\portFindingsModel.test.ts`.

**Criterio BINARIO:** comando verde; `tsc` del frontend sin errores nuevos (memoria `gotcha-rtl-jsdom-structural-gap`: validar con `tsc` + modelo puro, no RTL).

**Flag:** el pane depende de la metadata (poblada con flags ON). **Runtime:** N/A (UI). **Operador:** ninguno; ve el pane solo.

---

### F6 — Huellas de error del patrón (C10, red de seguridad para triage/auto-mejora)

**Objetivo:** registrar en `Stacky Agents/docs/sistema/error_fingerprints.json` las huellas de los dos patrones que este plan detecta, para que el triage/RSI las reconozca. Valor: el sistema aprende a nombrar "residuo de port" y "efecto colateral de build peligroso".

**Archivo a editar:** `Stacky Agents/docs/sistema/error_fingerprints.json`.

**Pasos (deterministas):**
1. **Leer el archivo primero** y respetar su schema exacto (claves/estructura existentes; NO inventar formato). Si el archivo no existe → esta fase es no-op (MENOR; no bloquea el plan).
2. Agregar (sin duplicar por id) dos entradas con el molde de las existentes, p.ej. ids `port_residue_foreign_token` (síntoma: "token de servidor/ruta de OTRO cliente en un archivo tocado por el developer"; señal: finding `kind in {server,path,workspace}` bloqueante) y `build_side_effect_foreign` (síntoma: "PostBuildEvent/Copy/OutputPath con ruta absoluta o token ajeno"; señal: `InspectFinding` bloqueante).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan211_fingerprints.py`:**
- `test_fingerprints_valid_json` (`json.load` del archivo no lanza; si no existe → `pytest.skip`).
- `test_two_fingerprints_present` (los dos ids están; si el archivo no existe → `skip`).
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde (o `skip` documentado si el archivo no existe); el JSON sigue siendo válido.

**Flag:** ninguna (dato estático). **Runtime:** N/A. **Operador:** ninguno.

---

## 5-bis. Orden de implementación

F0 → F1 → F2 → F3 → F4 → F5 → F6. F1 y F2 son independientes entre sí; F3 depende de ambas + de la seam del 210 (F5 del 210); F4 valida la integración; F5 (UI) depende de que el 210 incluya los findings en `execution.metadata["build_verdict"]` (C4, dependencia declarada — degrada limpio si aún no); F6 es independiente (dato estático). **Prerequisito externo duro:** Plan 210 implementado (la seam `register_evidence_contributor`, los helpers públicos `project_name_for_ado`/`workspace_root_for_ado`, y la re-persistencia del veredicto). Si el 210 no está, F3/F4 no tienen dónde engancharse → **no implementar 211 antes que 210.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|-----------|
| R1 | Falsos positivos de residuos (token común de otro cliente que también es legítimo acá). | **C1:** match por **límite de palabra** (no substring) + severidad bloqueante **solo para tokens de alta confianza** (`len≥6` o con dígito/separador) — un token corto/común nunca baja el gate, cae a warning. + stoplist + exclusión del proyecto **del ticket** (C2). + **[ADICIÓN ARQUITECTO] allowlist de supresión por perfil, editable por UI** (ya implementada, no follow-up): el operador marca el token legítimo y se suprime, sin apagar la feature. |
| R2 | El proyecto no es git → Capa C no ve archivos tocados. | `changed_files` degrada a `[]` (Capa C no aplica, no crashea). La Capa B (inspector) no depende de git. |
| R3 | Muchos archivos/tokens → scan lento. | Caps: `_MAX_FILE_BYTES`, `_MAX_FINDINGS`, filtro a `_SOURCE_EXTS`, corte temprano. Corre post-run (no en hot path). |
| R4 | Un residuo aparece en una línea con secretos → se filtra al deliverable. | `_mask` (reuso `secret_masking`) antes de anexar; degrada a truncado. |
| R5 | La Capa B eleva a bloqueante un `OutputPath` absoluto legítimo del propio proyecto. | Regla: `OutputPath` absoluto propio = warning; bloqueante SOLO si contiene token ajeno. Documentado en F1. |
| R6 | Doble registro de contribuidores (app recargada en tests). | `register` es idempotente por identidad de función; los tests que importan `app` no deben duplicar (usar el fake `register_fn`). |
| R7 | Divergencia en la resolución de workspace entre 210 y 211. | El 210 F3 expone `workspace_root_for_ado` **público**; 211 lo importa (F3). Una sola implementación, cero replicación. |
| R8 | **(C2)** El developer corre un ticket de un proyecto que NO es el activo global → el catálogo excluiría el proyecto equivocado (tormenta de falsos positivos sobre el proyecto correcto + ceguera al residuo real). | El catálogo se resuelve con `project_name_for_ado(ado_id)` (proyecto del ticket), no con `get_active_project()`. Exclusión por nombre **y** por `workspace_root` normalizado. Test `test_catalog_scoped_to_ticket_project`. |
| R9 | **(C3)** Árbol compartido / developer que commiteó → `changed_files` trae archivos de otra sesión o de un HEAD ajeno (autoría no garantizada). | `changed_files` soporta `base_ref` para diff acotado (autoría confiable); sin él degrada al working tree, pero la severidad efectiva exige **alta confianza** para bloquear (C1) → un archivo ajeno nunca voltea el gate por un token dudoso (a lo sumo warning). Capturar el `base_ref` por run es follow-up. |

---

## 7. Fuera de scope (explícito)

- **NO** repara ni revierte residuos ni edita `.csproj` (G2: solo reporta).
- **NO** implementa el gate de estado ni el publish (eso es Plan 210; este plan solo aporta findings a la seam).
- **NO** compila nada (usa el build que ya hizo el 210/201).
- **NO** escanea proyectos que no son fuente RS (filtra por `_SOURCE_EXTS`).
- **NO** agrega RBAC/multiusuario (G5).
- **NO** hand-edita `harness_defaults.env`.

---

## 8. Glosario + DoD

**Glosario:**
- **Residuo de port** — token de OTRO cliente (servidor, ruta, nombre) que quedó en el código tras portar estructura entre clientes RS.
- **Catálogo de tokens ajenos** — tokens distintivos de todos los perfiles EXCEPTO el del **ticket que corre el developer** (`build_foreign_token_catalog(ticket_project)`, C2).
- **Efecto colateral de build** — `PostBuildEvent`/`AfterTargets`/`Copy`/`OutputPath` que hace algo más que compilar (copiar binarios, escribir fuera del árbol).
- **Contribuidor de evidencia** — función registrada en la seam del 210 que suma findings/HTML al veredicto de build.
- **Finding bloqueante** — baja el `gate_ok` del 210 → el ticket no avanza a "Build OK".

**Definition of Done (binario):**
1. Los 7 archivos de test (`test_plan211_flags`, `_inspector`, `_residue`, `_contributors`, `_integration`, `_fingerprints`, + `portFindingsModel.test.ts`) → **verdes** (o `skip` documentado en fingerprints si el archivo no existe), por archivo con el venv, todos los `test_plan211_*.py` en `HARNESS_TEST_FILES`.
2. `grep -rn "dev_build_contributors.register" "Stacky Agents/backend/app.py"` → 1 match.
3. `grep -n "shell=True" "Stacky Agents/backend/services/port_residue_scanner.py"` → 0 matches.
4. **(C7)** `grep -n "mask_token_values" "Stacky Agents/backend/services/port_residue_scanner.py"` → 1+ match (masking real, NO `mask_secrets`).
5. **(C1)** `test_word_boundary_not_substring` y `test_short_common_token_is_warning_not_blocking` verdes: ningún token corto/común baja el gate.
6. **(C2)** `test_catalog_scoped_to_ticket_project` verde: `build_foreign_token_catalog` se invoca con el proyecto del ticket, nunca `None`.
7. **(C5)** `test_register_is_idempotent` verde: doble `register` no duplica contribuidores.
8. **(ADICIÓN)** `test_allowlist_suppresses_token` verde: un token en la allowlist del perfil no produce finding.
9. Con ambas flags OFF: el deliverable/estado queda idéntico al del 210 solo (KPI-6); ningún test existente se rompe.
10. Test de integración F4: un blocking de 211 produce `gate_ok False` en el veredicto re-persistido.
11. **Smoke E2E (manual, pendiente):** correr un developer sobre un proyecto con un `.csproj` que tenga un `PostBuildEvent` a ruta absoluta y un archivo con un **servidor de alta confianza** de otro cliente → el deliverable lista ambos findings, el `gate_ok` es False y el ticket no avanza. Repetir con un token corto ajeno dentro de una palabra legítima → **0 findings** (no bloquea). (Depende de 210 + 201 mergeados.)

**Trabajo del operador:** ninguno (opt-in default ON; ambas flags toggleables desde Configuración → Arnés → DevOps; degrada a vacío si no hay build/git).
